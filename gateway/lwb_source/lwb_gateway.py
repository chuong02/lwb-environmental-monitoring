#!/usr/bin/env python3
import json
import logging
import logging.handlers
import os
import re
import signal
import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import serial


STOP = False


def utc_now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def env(name, default=None):
    value = os.getenv(name)
    return default if value is None or value == "" else value


SERIAL_PORT = env("SERIAL_PORT", "/dev/ttyUSB0")
SERIAL_BAUD = int(env("SERIAL_BAUD", "115200"))
SERIAL_TIMEOUT = float(env("SERIAL_TIMEOUT", "1.0"))
RECONNECT_SEC = float(env("SERIAL_RECONNECT_SEC", "3"))

DB_PATH = Path(env("DB_PATH", "/var/lib/lwb-gateway/lwb.db"))
LOG_DIR = Path(env("LOG_DIR", "/var/log/lwb-gateway"))
APP_LOG = LOG_DIR / "gateway.log"
RAW_LOG = LOG_DIR / "serial_raw.log"
STATS_SEC = float(env("UART_STATS_SEC", "60"))


def ensure_dirs():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def build_logger():
    logger = logging.getLogger("lwb_gateway")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()

    console = logging.StreamHandler()
    console.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s"
    ))

    app_file = logging.handlers.TimedRotatingFileHandler(
        APP_LOG, when="midnight", backupCount=14, encoding="utf-8", utc=True
    )
    app_file.setFormatter(logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s"
    ))

    logger.addHandler(console)
    logger.addHandler(app_file)

    raw = logging.getLogger("lwb_raw")
    raw.setLevel(logging.INFO)
    raw.handlers.clear()
    raw.propagate = False
    raw_file = logging.handlers.TimedRotatingFileHandler(
        RAW_LOG, when="midnight", backupCount=14, encoding="utf-8", utc=True
    )
    raw_file.setFormatter(logging.Formatter("%(message)s"))
    raw.addHandler(raw_file)

    return logger, raw


def open_db():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recv_ts_utc TEXT NOT NULL,
            record_type TEXT NOT NULL,
            run INTEGER,
            source INTEGER,
            seq INTEGER,
            raw_line TEXT NOT NULL,
            payload_json TEXT NOT NULL,
            published INTEGER NOT NULL DEFAULT 0,
            published_ts_utc TEXT
        )
    """)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(events)")}
    if "checksum" not in cols:
        # ok | bad | none ; added in place, old rows stay NULL
        conn.execute("ALTER TABLE events ADD COLUMN checksum TEXT")
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_unpublished
        ON events(published, id)
    """)
    conn.execute("""
        CREATE INDEX IF NOT EXISTS idx_events_lookup
        ON events(record_type, run, source, seq)
    """)
    conn.commit()
    return conn


def convert_value(value):
    value = value.strip()
    if value == "":
        return ""
    try:
        return int(value, 10)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


KNOWN_TYPES = {
    "SENSOR_DATA", "LOCAL", "PERF_CONFIG", "PERF_RX", "PERF_TX", "PERF_GEN",
    "PERF_SUMMARY", "PERF_SOURCE_SUMMARY", "PERF_HOP_SUMMARY", "PERF_REPORT",
    "PERF_REPORT_END", "PERF_START", "PERF_ABORT", "PERF_ERR",
    "PERF_RELEASE_SKIP", "REJOIN_REQUEST", "SENSOR_STATUS", "RX_CALLBACK",
    "PERF_RADIO",
}
TYPE_RE = re.compile(r"^[A-Z][A-Z0-9_]{1,40}$")
CHECKSUM_RE = re.compile(r"\*([0-9A-Fa-f]{2})$")


def check_line(line):
    """Return (status, body).

    status = "ok"   : line ended with *HH and the XOR checksum matched
             "bad"  : *HH present but wrong, or unreadable characters
             "none" : no checksum (old firmware / boot banner)
    """
    if any(ord(ch) < 32 or ord(ch) > 126 for ch in line):
        return "bad", line
    m = CHECKSUM_RE.search(line)
    if not m:
        return "none", line
    body = line[:m.start()]
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return ("ok" if cs == int(m.group(1), 16) else "bad"), body


def legacy_line_looks_valid(record_type, payload):
    """Accept an un-checksummed line only if it is structurally clean."""
    return (record_type in KNOWN_TYPES and "_parser_warning" not in payload
            and all(TYPE_RE.match(k.upper()) for k in payload))


def parse_line(line):
    """
    Parses records such as:
      PERF_RX,run,250,from,2,seq,11,unique,1,...
      PERF_SUMMARY,run,250,source,2,final,0,expected,100,...

    The parser is deliberately generic: any key/value field added by the
    CC2538 firmware later will be preserved without changing this program.
    """
    parts = [p.strip() for p in line.split(",")]
    if not parts or not parts[0]:
        return "EMPTY", {"_parser_error": "empty record"}

    record_type = parts[0]
    tokens = parts[1:]
    payload = {}

    if len(tokens) % 2 != 0:
        payload["_parser_warning"] = "odd number of key/value tokens"
        payload["_tokens"] = tokens
        return record_type, payload

    for i in range(0, len(tokens), 2):
        key = tokens[i]
        value = tokens[i + 1]
        if not key:
            key = f"_unnamed_{i}"
        payload[key] = convert_value(value)

    return record_type, payload


def normalized_fields(record_type, payload):
    """Return the common metadata stored in SQLite.

    Environmental frames use ``from`` and ``node`` while performance frames
    may use ``source`` or ``from``.  Accept all aliases so the database keeps
    one normalized ``source`` column without changing the original payload.
    """
    run = payload.get("run")
    seq = payload.get("seq")

    source = payload.get("source")
    if source is None:
        source = payload.get("from")
    if source is None:
        source = payload.get("node_id")
    if source is None:
        source = payload.get("node")

    def as_int_or_none(v):
        try:
            return int(v)
        except (TypeError, ValueError):
            return None

    return (
        as_int_or_none(run),
        as_int_or_none(source),
        as_int_or_none(seq),
    )


def insert_event(conn, recv_ts_utc, record_type, payload, raw_line, checksum):
    run, source, seq = normalized_fields(record_type, payload)
    # Corrupted lines are kept for evidence but never published.
    published = 0 if record_type != "UART_BAD" else 3

    conn.execute(
        """
        INSERT INTO events(
            recv_ts_utc, record_type, run, source, seq,
            raw_line, payload_json, published, checksum
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            recv_ts_utc,
            record_type,
            run,
            source,
            seq,
            raw_line,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
            published,
            checksum,
        ),
    )
    conn.commit()


def stop_handler(signum, frame):
    global STOP
    STOP = True


def main():
    global STOP
    ensure_dirs()
    logger, raw_logger = build_logger()
    conn = open_db()

    signal.signal(signal.SIGTERM, stop_handler)
    signal.signal(signal.SIGINT, stop_handler)

    logger.info(
        "Starting LWB serial gateway port=%s baud=%s db=%s",
        SERIAL_PORT, SERIAL_BAUD, DB_PATH
    )

    stats = {"ok": 0, "none": 0, "bad": 0}
    stats_t0 = time.monotonic()

    while not STOP:
        ser = None
        try:
            logger.info("Opening serial port %s", SERIAL_PORT)
            ser = serial.Serial(
                SERIAL_PORT,
                SERIAL_BAUD,
                timeout=SERIAL_TIMEOUT,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
            )
            logger.info("Serial connected")

            while not STOP:
                raw_bytes = ser.readline()
                if not raw_bytes:
                    continue

                recv_ts = utc_now_iso()
                line = raw_bytes.decode("utf-8", errors="replace").strip("\r\n")

                if not line:
                    continue

                raw_logger.info("%s\t%s", recv_ts, line)

                status, body = check_line(line)
                record_type, payload = parse_line(body)
                if status == "bad" or (
                        status == "none" and not legacy_line_looks_valid(record_type, payload)):
                    stats["bad"] += 1
                    insert_event(conn, recv_ts, "UART_BAD", {"checksum": status}, line, "bad")
                    continue
                stats[status] += 1
                insert_event(conn, recv_ts, record_type, payload, line, status)

                now = time.monotonic()
                if now - stats_t0 >= STATS_SEC:
                    total = stats["ok"] + stats["none"] + stats["bad"]
                    logger.info(
                        "UART lines last %.0fs: ok=%d legacy=%d bad=%d (%.1f%% bad)",
                        now - stats_t0, stats["ok"], stats["none"], stats["bad"],
                        100.0 * stats["bad"] / total if total else 0.0,
                    )
                    stats = {"ok": 0, "none": 0, "bad": 0}
                    stats_t0 = now

                # Keep console logging concise for long-running operation.
                if record_type in (
                    "SENSOR_DATA", "LOCAL", "PERF_RX",
                    "PERF_SUMMARY", "PERF_HOP_SUMMARY"
                ):
                    _, source, seq = normalized_fields(record_type, payload)
                    logger.info(
                        "RX type=%s run=%s source=%s seq=%s",
                        record_type,
                        payload.get("run"),
                        source,
                        seq,
                    )
                else:
                    logger.info("RX type=%s", record_type)

        except serial.SerialException as exc:
            logger.error("Serial error: %s", exc)
        except Exception:
            logger.exception("Unexpected gateway error")
        finally:
            if ser is not None:
                try:
                    ser.close()
                except Exception:
                    pass

        if not STOP:
            logger.info("Reconnecting serial in %.1f s", RECONNECT_SEC)
            time.sleep(RECONNECT_SEC)

    logger.info("Gateway stopping")
    conn.close()


if __name__ == "__main__":
    main()

