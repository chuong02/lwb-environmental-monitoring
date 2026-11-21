#!/usr/bin/env python3
"""Capture several Linux UARTs concurrently, preserving raw firmware log lines."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import selectors
import termios
import time
import tty


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--port", action="append", required=True, metavar="NODE=/dev/ttyUSB0")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--seconds", type=float, default=1200)
    args = ap.parse_args()
    if args.seconds <= 0:
        ap.error("--seconds must be positive")
    ports = {}
    for item in args.port:
        name, sep, dev = item.partition("=")
        if not sep or not name.isdecimal() or name in ports:
            ap.error("Use a distinct numeric NODE=/dev/... for each --port")
        ports[name] = dev
    out = args.out.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=False)
    opened, sel = [], selectors.DefaultSelector()
    meta = {"ports": ports, "baud": 115200, "start_utc": datetime.now(timezone.utc).isoformat(),
            "duration_requested_s": args.seconds, "completed": False}
    (out / "capture.json").write_text(json.dumps(meta, indent=2) + "\n")
    try:
        for name, dev in ports.items():
            fd = os.open(dev, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
            old = termios.tcgetattr(fd)
            log = (out / ("node-" + name + ".log")).open("wb")
            opened.append((fd, old, log))
            tty.setraw(fd)
            cfg = termios.tcgetattr(fd)
            cfg[2] |= termios.CLOCAL | termios.CREAD
            cfg[4] = cfg[5] = termios.B115200
            termios.tcsetattr(fd, termios.TCSANOW, cfg)
            sel.register(fd, selectors.EVENT_READ, log)
        print("Recording. Reset/start the boards now; Ctrl-C stops and closes the logs.")
        end = time.monotonic() + args.seconds
        while time.monotonic() < end:
            for key, _ in sel.select(timeout=min(1, max(0, end - time.monotonic()))):
                try:
                    block = os.read(key.fd, 65536)
                except BlockingIOError:
                    continue
                if block:
                    key.data.write(block)
                    key.data.flush()
                else:
                    raise RuntimeError("UART disconnected; this capture is incomplete")
        meta["completed"] = True
    except KeyboardInterrupt:
        meta["stopped_by_user"] = True
    except Exception as exc:
        meta["error"] = str(exc)
        raise
    finally:
        for fd, old, log in opened:
            try:
                termios.tcsetattr(fd, termios.TCSANOW, old)
            except termios.error:
                pass
            os.close(fd)
            log.flush()
            os.fsync(log.fileno())
            log.close()
        sel.close()
        meta["end_utc"] = datetime.now(timezone.utc).isoformat()
        (out / "capture.json").write_text(json.dumps(meta, indent=2) + "\n")
        print("Logs:", out)


if __name__ == "__main__":
    main()
