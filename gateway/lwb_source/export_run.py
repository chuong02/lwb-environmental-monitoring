#!/usr/bin/env python3
"""Export one measurement run from the gateway SQLite DB for analyze_logs.py.

Writes <out>/host-run<run>.log (raw HOST lines, with their *HH checksum so the
analyzer can verify them again) and <out>/uart-quality.json, then prints the
analyze_logs.py command to run next.  Standard library only.

--capture-complete is added to the printed command only when the capture
checks pass (or --force-capture-complete is given).
"""
import argparse
import json
import shlex
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

DEFAULT_DB = "/var/lib/lwb-gateway/lwb.db"
DEFAULT_MAX_GAP_S = 90.0


def parse_ts(text):
    # Stored as e.g. 2026-11-12T10:00:01.000Z (UTC); fromisoformat on older
    # Python (Raspberry Pi OS) does not accept the trailing 'Z'.
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def row_source(source, payload_json):
    """Source ID of a row: the normalized column, else the payload aliases."""
    if source is not None:
        return int(source)
    try:
        p = json.loads(payload_json)
    except (ValueError, TypeError):
        return None
    for key in ("source", "from", "node_id", "node"):
        if p.get(key) is not None:
            try:
                return int(p[key])
            except (ValueError, TypeError):
                return None
    return None


def check_capture(rows, max_gap_s):
    """rows: (recv_ts_utc, record_type, source, payload_json) in id order.

    Returns (capture_check dict, list of human-readable problems).
    """
    problems = []

    # (a) PERF_CONFIG must come before the first SENSOR_DATA.
    types = [r[1] for r in rows]
    perf_config_idx = types.index("PERF_CONFIG") if "PERF_CONFIG" in types else None
    sensor_idx = types.index("SENSOR_DATA") if "SENSOR_DATA" in types else None
    if perf_config_idx is None:
        perf_config_ok = False
        problems.append("không có dòng PERF_CONFIG trong run")
    elif sensor_idx is not None and sensor_idx < perf_config_idx:
        perf_config_ok = False
        problems.append("SENSOR_DATA đầu tiên (%s) đứng trước PERF_CONFIG (%s)"
                        % (rows[sensor_idx][0], rows[perf_config_idx][0]))
    else:
        perf_config_ok = True

    # (b) Gap between consecutive PERF_SUMMARY rows of each source.
    last_seen = {}
    worst_gap = {}
    gaps = []
    for recv_ts, record_type, source, payload_json in rows:
        if record_type != "PERF_SUMMARY":
            continue
        src = row_source(source, payload_json)
        if src is None:
            continue
        now = parse_ts(recv_ts)
        if src in last_seen:
            prev_ts, prev = last_seen[src]
            gap = (now - prev).total_seconds()
            worst_gap[src] = max(worst_gap.get(src, 0.0), gap)
            if gap > max_gap_s:
                gaps.append({"source": src, "gap_s": round(gap, 3),
                             "from_utc": prev_ts, "to_utc": recv_ts})
                problems.append("source %d: khoảng trống %.1f s giữa %s và %s (tối đa %.0f s)"
                                % (src, gap, prev_ts, recv_ts, max_gap_s))
        last_seen[src] = (recv_ts, now)

    check = {
        "perf_config_before_sensor": perf_config_ok,
        "max_summary_gap_s": max_gap_s,
        "max_summary_gap_s_by_source": {str(k): round(v, 3) for k, v in sorted(worst_gap.items())},
        "summary_gaps_over_limit": gaps,
        "passed": not problems,
    }
    return check, problems


def source_ids(rows):
    """Source IDs from the run's PERF_SUMMARY rows (sorted, unique)."""
    ids = set()
    for _, record_type, source, payload_json in rows:
        if record_type == "PERF_SUMMARY":
            src = row_source(source, payload_json)
            if src is not None:
                ids.add(src)
    return sorted(ids)


def main():
    # Vietnamese messages must print on consoles that default to a legacy codepage.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--db", default=DEFAULT_DB, help="gateway SQLite DB (default: %(default)s)")
    ap.add_argument("--run", type=int, required=True, help="run number to export")
    ap.add_argument("--out", type=Path, required=True, help="output directory")
    ap.add_argument("--max-gap-s", type=float, default=DEFAULT_MAX_GAP_S,
                    help="max seconds between consecutive PERF_SUMMARY rows of a source "
                         "(default: %(default)s; HOST prints one every 30 s)")
    ap.add_argument("--force-capture-complete", action="store_true",
                    help="add --capture-complete even if the capture checks fail (you confirm the capture)")
    args = ap.parse_args()

    if not Path(args.db).exists():
        ap.error("database not found: %s" % args.db)
    # Read-only so the live gateway is never disturbed.
    conn = sqlite3.connect("file:%s?mode=ro" % Path(args.db).resolve().as_posix(), uri=True, timeout=30)
    try:
        rows = conn.execute(
            "SELECT recv_ts_utc, record_type, source, payload_json, raw_line FROM events "
            "WHERE run = ? AND record_type != 'UART_BAD' ORDER BY id", (args.run,)).fetchall()
        if not rows:
            print("No rows found for run %d in %s" % (args.run, args.db), file=sys.stderr)
            return 1

        args.out.mkdir(parents=True, exist_ok=True)
        log_path = args.out / ("host-run%d.log" % args.run)
        with log_path.open("w", encoding="utf-8", newline="\n") as f:
            for *_, raw_line in rows:
                f.write(raw_line + "\n")

        first_ts, last_ts = rows[0][0], rows[-1][0]
        # ISO-8601 UTC with fixed width: string comparison is chronological.
        # Rows that are not UART_BAD are "ok" (checksum verified) or "legacy"
        # (no checksum; NULL from rows written before the column existed).
        ok, legacy, bad = 0, 0, 0
        for is_bad, checksum, n in conn.execute(
                "SELECT record_type = 'UART_BAD', checksum, COUNT(*) FROM events "
                "WHERE recv_ts_utc >= ? AND recv_ts_utc <= ? "
                "GROUP BY record_type = 'UART_BAD', checksum", (first_ts, last_ts)):
            if is_bad:
                bad += n
            elif checksum == "ok":
                ok += n
            else:
                legacy += n
        total = ok + legacy + bad

        check, problems = check_capture([r[:4] for r in rows], args.max_gap_s)
        forced = args.force_capture_complete and not check["passed"]
        check["forced"] = args.force_capture_complete
        check["capture_complete_applied"] = check["passed"] or args.force_capture_complete

        quality = {
            "run": args.run,
            "window_start_utc": first_ts,
            "window_end_utc": last_ts,
            "ok": ok,
            "legacy": legacy,
            "bad": bad,
            "total": total,
            "bad_pct": round(100.0 * bad / total, 4) if total else 0.0,
            "capture_check": check,
        }
        (args.out / "uart-quality.json").write_text(json.dumps(quality, indent=2) + "\n")

        sources = source_ids([r[:4] for r in rows])
    finally:
        conn.close()

    print("Exported %d lines -> %s" % (len(rows), log_path))
    print("UART quality: ok=%d legacy=%d bad=%d (%.2f%% bad) -> %s"
          % (ok, legacy, bad, quality["bad_pct"], args.out / "uart-quality.json"))
    if not sources:
        print("WARNING: no PERF_SUMMARY rows for this run; fill in --sources yourself.", file=sys.stderr)
    for p in problems:
        print("WARNING capture check: %s" % p, file=sys.stderr)
    if forced:
        print("NOTE: --force-capture-complete: bạn tự xác nhận capture đầy đủ dù kiểm tra thất bại.")
    elif not check["passed"]:
        print("NOTE: capture checks thất bại, lệnh bên dưới KHÔNG có --capture-complete.")

    cmd = ["python3", "lwb-cc2538dk/tools/analyze_logs.py",
           "--host", str(log_path),
           "--sources", ":".join(str(s) for s in sources),
           "--run", str(args.run)]
    if check["capture_complete_applied"]:
        cmd.append("--capture-complete")
    cmd += ["--out", str(args.out / "results.json")]
    print("\nNext:")
    print(" ".join(shlex.quote(c) for c in cmd))
    return 0


if __name__ == "__main__":
    sys.exit(main())
