#!/usr/bin/env python3
"""Tinh lai he so Pearson giua cac Source (multi-hop) tu bo dem cua HOST, doc lap voi make_report.py.

make_report.py: x_s[k] = so dong SENSOR_DATA hop le cua Source s trong khoi 30 s thu k.
Script nay:     x_s[k] = hieu cua bo dem `received` trong PERF_SUMMARY giua hai khoi lien tiep
                (bo dem cua chinh HOST, khong phu thuoc viec mat dong log).
- Khoi 30 s = mot luot PERF_SUMMARY cua cac Source; PERF_SUMMARY ngay sau PERF_REPORT cua cung Source
  (tong ket theo su kien) khong tinh la khoi.
- Chi giu khoi co du lieu o ca khoi truoc do (delta dung mot khoi 30 s).
- Cap (a, b): lay cac khoi tu max(khoi dau co goi cua a, cua b) den min(khoi cuoi co goi cua a, cua b),
  chi tinh khi hai chuoi deu khong hang so va co hon 3 khoi.
Chay: python corr_check.py  (chi can thu vien chuan; doc logs/Multihop/**/*.log, khong sua log).
"""
import re
import statistics
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = (HERE / "logs" if (HERE / "logs").exists() else HERE.parent / "logs") / "Multihop"
CS = re.compile(r"\*([0-9A-Fa-f]{2})\s*$")


def ok(line):
    m = CS.search(line)
    if not m:
        return True
    x = 0
    for ch in line[:m.start()].rstrip("\r\n").encode("latin-1", "ignore"):
        x ^= ch
    return x == int(m.group(1), 16)


def host_counter_pearson(path):
    """-> {(a, b): (r, n)} theo bo dem received cua HOST."""
    cum, n_blk, seen, last_rep = {}, -1, set(), None
    for raw in path.read_bytes().decode("latin-1").splitlines():
        if raw.startswith("PERF_REPORT,") and ok(raw):
            t = raw.split(",")
            last_rep = dict(zip(t[1::2], t[2::2])).get("source")
            continue
        if not raw.startswith("PERF_SUMMARY,") or not ok(raw):
            if raw.startswith("PERF_"):
                last_rep = None
            continue
        t = raw.split(",")
        d = dict(zip(t[1::2], t[2::2]))
        src_rep, last_rep = last_rep, None
        if "source" not in d or "received" not in d or d["source"] == src_rep:
            continue
        s = int(d["source"])
        if s in seen or n_blk < 0:
            n_blk, seen = n_blk + 1, set()
        seen.add(s)
        cum.setdefault(s, {})[n_blk] = int(d["received"])
    cnt = {}
    for s, c in cum.items():
        cnt[s] = {k: (max(c[k] - c[k - 1], 0) if k - 1 in c else c[k]) for k in sorted(c) if k - 1 in c or k == 0}
    res, srcs = {}, sorted(cnt)
    for i, a in enumerate(srcs):
        for b in srcs[i + 1:]:
            ka = [k for k, v in cnt[a].items() if v > 0]
            kb = [k for k, v in cnt[b].items() if v > 0]
            if not ka or not kb:
                continue
            rng = [k for k in range(max(min(ka), min(kb)), min(max(ka), max(kb)) + 1) if k in cnt[a] and k in cnt[b]]
            xa, xb = [cnt[a][k] for k in rng], [cnt[b][k] for k in rng]
            if len(xa) > 3 and statistics.pstdev(xa) > 0 and statistics.pstdev(xb) > 0:
                res[(a, b)] = (statistics.correlation(xa, xb), len(xa))
    return res


if __name__ == "__main__":
    for f in sorted(LOGS.rglob("*.log")):
        print("==", f.name)
        for (a, b), (r, n) in host_counter_pearson(f).items():
            print("  %d-%d: r = %.2f (n = %d khoi)" % (a, b, r, n))
