#!/usr/bin/env python3
import argparse
import csv
import json
import sqlite3
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Export LWB gateway events to CSV")
    parser.add_argument("--db", default="/var/lib/lwb-gateway/lwb.db")
    parser.add_argument("--out", required=True)
    parser.add_argument("--type", default=None, help="Optional record type, e.g. PERF_RX")
    args = parser.parse_args()

    conn = sqlite3.connect(args.db)
    conn.row_factory = sqlite3.Row

    if args.type:
        rows = conn.execute(
            "SELECT * FROM events WHERE record_type=? ORDER BY id",
            (args.type,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM events ORDER BY id"
        ).fetchall()

    payload_keys = set()
    parsed = []
    for row in rows:
        try:
            payload = json.loads(row["payload_json"])
        except json.JSONDecodeError:
            payload = {}
        payload_keys.update(payload.keys())
        parsed.append((row, payload))

    fixed = [
        "id", "recv_ts_utc", "record_type", "run", "source", "seq",
        "published", "published_ts_utc", "raw_line",
    ]
    fields = fixed + sorted(payload_keys)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with out_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row, payload in parsed:
            item = {k: row[k] for k in fixed}
            item.update(payload)
            writer.writerow(item)

    print(f"Exported {len(rows)} rows to {out_path}")


if __name__ == "__main__":
    main()
