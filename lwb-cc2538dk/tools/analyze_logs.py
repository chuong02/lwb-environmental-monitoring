#!/usr/bin/env python3
"""Analyze env_perf_v1 logs. Unknown denominators stay null, never max(seq)."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import re
import sys

MARKER = re.compile(r"(PERF_[A-Z_]+|SENSOR_DATA),")
COUNTS = ("generated", "queued", "tx_started", "queue_failed", "deadline_missed", "tx_start_failed")


CHECKSUM = re.compile(r"\*([0-9A-Fa-f]{2})\s*$")
CHECKSUM_STATS = Counter()


def strip_checksum(text):
    """Return text without '*HH', or None if the UART checksum is wrong.

    Firmware with UART_CHECKSUM=1 appends XOR of all bytes before '*'.
    Lines without a checksum (older firmware) are accepted unchanged.
    """
    m = CHECKSUM.search(text)
    if not m:
        CHECKSUM_STATS["no_checksum"] += 1
        return text.strip()
    body = text[:m.start()]
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    if cs != int(m.group(1), 16):
        CHECKSUM_STATS["bad"] += 1
        return None
    CHECKSUM_STATS["ok"] += 1
    return body.strip()


def parse_lines(lines, origin="log"):
    for line_no, line in enumerate(lines, 1):
        match = MARKER.search(line)
        if not match:
            continue
        text = strip_checksum(line[match.start():].rstrip("\r\n"))
        if text is None:
            continue
        row = next(csv.reader([text]))
        if len(row) % 2 != 1 or len(set(row[1::2])) != len(row[1::2]):
            raise ValueError("Malformed event at %s:%d" % (origin, line_no))
        d = dict(zip(row[1::2], row[2::2]))
        d.update(tag=row[0], location="%s:%d" % (origin, line_no))
        yield d


def integer(d, key, default=None):
    try:
        return int(d[key]) if key in d else default
    except ValueError:
        raise ValueError("Noninteger %s at %s" % (key, d.get("location", "event")))


def percentage(k, n):
    return round(100 * k / n, 6) if n else None


def wilson(k, n):
    if not n:
        return None
    z = 1.959963984540054
    p = k / n
    c = (p + z * z / (2 * n)) / (1 + z * z / n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return [round(100 * max(0, c - h), 6), round(100 * min(1, c + h), 6)]


def analyze(host_events, source_events=(), planned_sources=(), expected=None, run=None,
            coverage_confirmed=False):
    """Return one record per run/source; raise on malformed log structure."""
    hs = list(host_events)
    ss = list(source_events)
    configs = defaultdict(list)
    host_configs = defaultdict(list)
    keys = set()
    for event in hs + ss:
        r = integer(event, "run")
        if r is None or (run is not None and r != run):
            continue
        if event["tag"] == "PERF_CONFIG":
            node = integer(event, "node")
            configs[r, node].append(event)
            if event.get("role") == "HOST" and event in hs:
                host_configs[r].append(event)
            for s in event.get("source_ids", "").split(":"):
                if s:
                    keys.add((r, int(s)))
        source = integer(event, "source", integer(event, "node") if event["tag"] == "SENSOR_DATA" else None)
        if source is not None:
            keys.add((r, source))
    runs = {r for r, _ in keys} | set(host_configs)
    if run is not None:
        runs.add(run)
    for r in runs:
        keys.update((r, int(s)) for s in planned_sources)
    output = []
    for r, source in sorted(keys):
        problems = []
        hc = host_configs.get(r, [])
        if len(hc) != 1:
            problems.append("host_config_missing_or_repeated")
        if len(configs.get((r, source), [])) > 1:
            problems.append("source_reboot_or_repeated_capture")
        hconfig = hc[0] if hc else {}
        sc = configs.get((r, source), [])
        if sc and sc[0].get("role") != "SOURCE":
            problems.append("configured_source_role_mismatch")
        for other in sc:
            for field in ("expected", "ipi_s", "channel", "payload_bytes", "timer_hz", "n_sync", "n_data_tx", "tx_drive_dbm", "source_ids", "protocol"):
                if field in hconfig and field in other and hconfig[field] != other[field]:
                    problems.append("configuration_mismatch_" + field)
        n = expected if expected is not None else integer(hconfig, "expected")
        if n is None and sc:
            n = integer(sc[0], "expected")
        if n is None or not 1 <= n <= 2000:
            problems.append("expected_count_unavailable")
            n = None
        if expected is not None and integer(hconfig, "expected", expected) != expected:
            problems.append("expected_override_mismatch")
        relevant_host = [d for d in hs if integer(d, "run") == r and
                         integer(d, "source", integer(d, "node") if d["tag"] == "SENSOR_DATA" else None) == source]
        relevant_source = [d for d in ss if integer(d, "run") == r and
                           integer(d, "source") == source]
        received, delays, relays = {}, [], []
        duplicates, out_of_order, highest = 0, 0, 0
        for d in relevant_host:
            if d["tag"] != "SENSOR_DATA":
                continue
            seq = integer(d, "seq", 0)
            if not seq or (n is not None and seq > n):
                problems.append("received_sequence_out_of_range")
                continue
            if seq in received:
                duplicates += 1
                if integer(d, "unique", 0) != 0:
                    problems.append("duplicate_capture_or_firmware_restart")
                continue
            if integer(d, "unique", 1) != 1:
                problems.append("capture_missing_first_reception")
            received[seq] = d
            out_of_order += seq < highest
            highest = max(highest, seq)
            if integer(d, "delay_valid", 0):
                ticks = integer(d, "delay_ticks", -1)
                hz = integer(d, "timer_hz", integer(hconfig, "timer_hz", 32768))
                tx, rx = integer(d, "tx_net_ticks"), integer(d, "rx_slot_end_ticks")
                if ticks < 0 or hz <= 0 or (tx is not None and rx is not None and ((rx - tx) & 0xffffffff) != ticks):
                    problems.append("invalid_delay_metadata")
                else:
                    delays.append(1000 * ticks / hz)
            if integer(d, "hop_est_valid", 0):
                rc = integer(d, "relay_cnt", 255)
                if not 0 <= rc <= 254 or integer(d, "hop_est", rc + 1) != rc + 1:
                    problems.append("invalid_relay_metadata")
                else:
                    relays.append(rc)
        summaries = [d for d in relevant_host if d["tag"] == "PERF_SUMMARY"]
        if summaries and max(integer(d, "received", 0) for d in summaries) > len(received):
            problems.append("host_log_missing_data_lines")
        reports = [d for d in relevant_host if d["tag"] == "PERF_REPORT"]
        host_report_present = bool(reports)
        reports += [d for d in relevant_source if d["tag"] == "PERF_SOURCE_SUMMARY"]
        counts = None
        count_origin = None
        for d in reports:
            c = {name: integer(d, name, -1) for name in COUNTS}
            c["drain_timeout"] = integer(d, "drain_timeout", 0)
            g, q, t, f, m, tf = [c[name] for name in COUNTS]
            if (min(g, q, t, f, m, tf) < 0 or (n is not None and g != n) or
                    q + f + m != g or t + tf > q or len(received) > t):
                problems.append("inconsistent_final_counts")
            if counts is not None and c != counts:
                problems.append("conflicting_final_reports")
            counts = c
            if d["tag"] == "PERF_SOURCE_SUMMARY":
                count_origin = "source_uart"
                discarded = integer(d, "discarded", 0)
                # FRESH_ONLY firmware: stale queue entries replaced by a fresh packet were
                # queued but never sent. Older logs have no such field (0).
                superseded = integer(d, "superseded", 0)
                if t + tf + discarded + superseded != q:
                    problems.append("unaccounted_source_queue_entries")
            elif count_origin is None:
                count_origin = "over_air_report"
        aborted = any(d["tag"] == "PERF_ABORT" for d in relevant_source)
        if counts and not host_report_present and not coverage_confirmed:
            problems.append("host_end_coverage_unverified")
        if aborted and (counts or received):
            problems.append("abort_conflicts_with_data")
        if not counts and aborted:
            counts = dict.fromkeys(COUNTS, 0)
            counts["drain_timeout"] = 0
            count_origin = "source_abort_uart"
        problems = sorted(set(problems))
        final = counts is not None and not problems
        status = "invalid" if problems else "join_failed" if aborted else "final" if final else "incomplete"
        result = {"run": r, "source": source, "status": status, "issues": problems,
                  "expected": n, "received_unique": len(received), "duplicates": duplicates,
                  "out_of_order": out_of_order, "denominator_origin": count_origin,
                  "counts": counts, "planned_receipt_pct": percentage(len(received), n) if final else None,
                  "application_yield_pct": None, "enqueue_delivery_pct": None,
                  "flood_delivery_pct": None, "flood_delivery_wilson95_pct": None,
                  "delay_endpoint": "enqueue_to_host_slot_end", "delay_count": len(delays),
                  "delay_min_ms": min(delays) if delays else None,
                  "delay_mean_ms": sum(delays) / len(delays) if delays else None,
                  "delay_p95_ms": sorted(delays)[math.ceil(.95 * len(delays)) - 1] if delays else None,
                  "delay_max_ms": max(delays) if delays else None,
                  "relay_counter_samples": len(relays),
                  "relay_counter_histogram": dict(sorted(Counter(relays).items())),
                  "multihop_proven": None}
        if final:
            result["application_yield_pct"] = percentage(len(received), counts["generated"])
            result["enqueue_delivery_pct"] = percentage(len(received), counts["queued"])
            result["flood_delivery_pct"] = percentage(len(received), counts["tx_started"])
            result["flood_delivery_wilson95_pct"] = wilson(len(received), counts["tx_started"])
        output.append(result)
    return output


def read_events(paths):
    for path in paths:
        with path.open(errors="replace") as f:
            yield from parse_lines(f, str(path))


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--host", nargs="+", required=True, type=Path)
    ap.add_argument("--source", nargs="*", default=[], type=Path)
    ap.add_argument("--sources", default="", help="Expected IDs, colon-separated, includes zero-reception nodes")
    ap.add_argument("--packets", type=int)
    ap.add_argument("--run", type=int)
    ap.add_argument("--capture-complete", action="store_true",
                    help="Explicitly confirm manual HOST capture spans the whole SOURCE test")
    ap.add_argument("--out", type=Path, required=True, help="JSON result; a companion CSV is created")
    args = ap.parse_args()
    if args.out.suffix != ".json":
        ap.error("--out must use a .json filename")
    all_paths = [p.resolve() for p in args.host + args.source]
    if len(set(all_paths)) != len(all_paths):
        ap.error("Do not load the same capture twice")
    coverage = args.capture_complete
    parents = {p.parent for p in all_paths}
    if len(parents) == 1 and args.source:
        meta_path = next(iter(parents)) / "capture.json"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text())
                covered = {"node-" + str(x) + ".log" for x in meta.get("ports", {})}
                coverage = coverage or ("end_utc" in meta and not meta.get("error") and
                                       all(p.name in covered for p in all_paths))
            except (ValueError, OSError):
                pass
    try:
        result = analyze(read_events(args.host), read_events(args.source),
                         [int(x) for x in args.sources.split(":") if x], args.packets, args.run,
                         coverage_confirmed=coverage)
    except (ValueError, OSError) as exc:
        ap.error(str(exc))
    if not result:
        ap.error("No matching run/source records")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps({"schema": "lwb_analysis_v1", "results": result,
        "uart_checksum": dict(CHECKSUM_STATS),
        "notes": ["uart_checksum.bad = lines dropped because the UART checksum failed (not radio loss).",
                  "Delay is enqueue to Host slot end; invalid/unsynchronized delays are excluded.",
                  "Wilson intervals assume independent trials; correlated losses require per-run analysis.",
                  "Relay counters do not establish a physical shortest path or prove multihop."]}, indent=2) + "\n")
    csv_path = args.out.with_suffix(".csv")
    if csv_path == args.out:
        ap.error("--out must use a .json filename")
    rows = []
    for result_row in result:
        row = {k: v for k, v in result_row.items() if k not in ("counts", "relay_counter_histogram")}
        row["issues"] = ";".join(row["issues"])
        row.update({"source_" + k: v for k, v in (result_row["counts"] or {}).items()})
        rows.append(row)
    fields = list(dict.fromkeys(k for row in rows for k in row))
    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    print("Results:", args.out, csv_path)
    for r in result:
        print("run=%s source=%s status=%s received=%s flood_delivery_pct=%s" %
              (r["run"], r["source"], r["status"], r["received_unique"], r["flood_delivery_pct"]))
    if any(r["status"] == "invalid" for r in result):
        sys.exit(2)


if __name__ == "__main__":
    main()
