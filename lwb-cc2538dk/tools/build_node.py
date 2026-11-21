#!/usr/bin/env python3
"""Build one node in a fresh temporary copy; preserve configuration and hashes."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROLES = {"HOST": 1, "SOURCE": 2, "RELAY": 3}
EXTRA = {"CHANNEL", "TX_POWER_DBM", "N_SYNC", "N_DATA_TX", "DATA_BUFFERS",
         "MAX_NODE_ID", "START_DELAY", "JOIN_TIMEOUT", "REPORT_WAIT",
         "DRAIN_TIMEOUT", "REPORT_REPEAT", "SUMMARY_PERIOD", "MAX_DELAY_S",
         "SAMPLE_PERIOD", "OLED", "HOST_LOCAL_SENSOR", "USE_TEMP_RH", "UART_CHECKSUM",
         "USE_LIGHT", "USE_BMP", "TEMP_RH_SENSOR", "I2C_SCL", "I2C_SDA",
         "GEN_MODE", "GEN_LEAD_MS", "FRESH_ONLY", "REPORT_EVERY", "SENSOR_BUDGET_MS",
         "RADIO_STATS", "RADIO_STATS_PERIOD"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--contiki", required=True, type=Path)
    ap.add_argument("--node", required=True, type=int)
    ap.add_argument("--role", required=True, choices=ROLES)
    ap.add_argument("--run", required=True, type=int)
    ap.add_argument("--sources", default="3", help="Colon-separated node IDs")
    ap.add_argument("--host", type=int, default=1)
    ap.add_argument("--packets", type=int, default=100)
    ap.add_argument("--ipi", type=int, default=5)
    ap.add_argument("--set", action="append", default=[], metavar="KEY=INTEGER")
    ap.add_argument("--out", type=Path, default=Path("build"))
    ap.add_argument("--jobs", type=int, default=2)
    args = ap.parse_args()
    try:
        sources = [int(s) for s in args.sources.split(":")]
    except ValueError:
        ap.error("--sources must contain IDs separated by ':'")
    config = {"NODEID": args.node, "ROLE": ROLES[args.role], "HOST_ID": args.host,
              "RUN_ID": args.run, "PACKETS": args.packets, "IPI": args.ipi,
              "SOURCE_IDS": args.sources}
    for item in args.set:
        key, sep, value = item.partition("=")
        valid_number = bool(re.fullmatch(r"-?\d+", value)) if key == "TX_POWER_DBM" else value.isdecimal()
        if not sep or key not in EXTRA or not valid_number:
            ap.error("Unsupported --set; use a documented key and an integer (only TX_POWER_DBM may be negative)")
        config[key] = int(value)
    maximum = config.get("MAX_NODE_ID", 6)
    if (not 2 <= maximum <= 32 or not 1 <= args.node <= maximum or
            not 1 <= args.host <= maximum or not sources or
            any(s < 1 or s > maximum or s == args.host for s in sources) or
            len(set(sources)) != len(sources)):
        ap.error("Invalid host/source IDs or MAX_NODE_ID")
    if ((args.role == "HOST") != (args.node == args.host) or
            (args.role == "SOURCE" and args.node not in sources) or
            (args.role == "RELAY" and args.node in sources)):
        ap.error("Role and node/source IDs disagree")
    if not 1 <= args.run <= 0xffffffff or not 0 <= args.packets <= 2000:
        ap.error("run must be 1..4294967295 and packets 0..2000 (0 = continuous)")
    if not 5 <= args.ipi <= 3600 or args.ipi % 5 or args.jobs < 1:
        ap.error("ipi must be a multiple of 5 in 5..3600; jobs must be positive")
    contiki = args.contiki.expanduser().resolve()
    required = ["Makefile.include", "core", "platform/cc2538dk", "cpu/cc2538",
                "cpu/arm/common", "cpu/cc253x/usb/common", "lib/newlib"]
    missing = [p for p in required if not (contiki / p).exists()]
    if missing:
        ap.error("Missing Contiki files: " + ", ".join(missing))
    project = Path(__file__).resolve().parents[1]
    out = Path(os.path.abspath(str(args.out.expanduser()))) / ("run-%d_node-%d_%s" %
                                              (args.run, args.node, args.role.lower()))
    if out.exists():
        ap.error("Output already exists; choose a fresh --out or RUN_ID: " + str(out))
    version = subprocess.check_output(["arm-none-eabi-gcc", "--version"], universal_newlines=True).splitlines()[0]
    out.mkdir(parents=True)
    hashes = {}
    for p in sorted(project.rglob("*")):
        if p.is_file() and (p.suffix in (".c", ".h", ".patch") or p.name.startswith("Makefile")):
            if "build" not in p.relative_to(project).parts:
                hashes[str(p.relative_to(project))] = hashlib.sha256(p.read_bytes()).hexdigest()
    command = ["make", "-j" + str(args.jobs), "TARGET=cc2538dk", "CONTIKI=" + str(contiki)]
    command += ["%s=%s" % (k, v) for k, v in config.items()]
    manifest = {"configuration": config, "compiler": version, "command": command,
                "source_sha256": hashes, "hardware_tested": False, "build_ok": False}
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    with tempfile.TemporaryDirectory(prefix="lwb-node-") as tmp:
        work = Path(tmp) / "lwb-cc2538dk"
        shutil.copytree(str(project), str(work), ignore=shutil.ignore_patterns(
            "obj_*", "build", "__pycache__", "*.elf", "*.bin", "*.hex", "*.map",
            "*.cc2538dk", "*.co", "*.o", "*.d"))
        app = work / "apps/lwb-cc2538dk-env"
        with (out / "build.log").open("w") as log:
            result = subprocess.run(command, cwd=str(app), stdout=log, stderr=subprocess.STDOUT)
        if result.returncode:
            raise SystemExit("Build failed; see " + str(out / "build.log"))
        for suffix in ("elf", "hex", "bin"):
            p = app / ("lwb-cc2538dk-env." + suffix)
            target = out / ("firmware." + suffix)
            shutil.copy2(str(p), str(target))
            manifest.setdefault("firmware_sha256", {})[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
        mapfile = app / "lwb-cc2538dk-env-cc2538dk.map"
        if mapfile.exists():
            shutil.copy2(str(mapfile), str(out / "firmware.map"))
        size = subprocess.check_output(["arm-none-eabi-size", str(out / "firmware.elf")], universal_newlines=True)
        manifest["build_ok"] = True
        manifest["size"] = size.strip()
        (out / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
        print(size, end="")
        print("Built:", out)


if __name__ == "__main__":
    main()
