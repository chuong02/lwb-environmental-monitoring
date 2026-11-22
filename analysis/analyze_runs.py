#!/usr/bin/env python3
"""Phan tich log thuc nghiem LWB (HOST capture bang picocom + script).

Doc analysis/logs/**/*.log (KHONG sua log goc), ghi ket qua vao analysis/out/.
Dinh dang dong: xem lwb-cc2538dk/tools/analyze_logs.py (checksum XOR '*HH' o cuoi dong).

Chay:  python analyze_runs.py            (can matplotlib de ve hinh; thieu thi chi ghi CSV/MD)
"""
import csv
import datetime as dt
import math
import os
import re
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOGS = HERE / "logs"
OUT = HERE / "out"
OUT.mkdir(exist_ok=True)

MARKER = re.compile(r"(PERF_[A-Z_]+|SENSOR_DATA|RELAY_STATS),")
CSUM = re.compile(r"\*([0-9A-Fa-f]{2})\s*$")
BLOCK_S = 30.0       # HOST in khoi PERF_SUMMARY moi 30 s (xem chap3/chap4)
IPI_S = 5.0          # chu ky tao goi cua moi Source (PERF_CONFIG ipi_s)
TICK_HZ = 32768


# ----------------------------------------------------------------- thong ke
def cp_lower(k, n, alpha=0.05):
    """Can duoi Clopper-Pearson hai phia (1-alpha) cua xac suat thanh cong, k/n."""
    if n <= 0 or k <= 0:
        return 0.0
    if k == n:
        return (alpha / 2) ** (1.0 / n)

    def tail(p):  # P(X >= k | n, p)
        return sum(math.comb(n, i) * p ** i * (1 - p) ** (n - i) for i in range(k, n + 1))
    lo, hi = 0.0, 1.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if tail(mid) < alpha / 2:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def pct(x):
    return None if x is None else round(100 * x, 2)


def quantile_nr(xs, q):
    """Nearest-rank, giong analyze_logs.py (p95)."""
    s = sorted(xs)
    return s[max(0, math.ceil(q * len(s)) - 1)]


# ----------------------------------------------------------------- doc log
def parse_log(path):
    raw = path.read_text(errors="replace")
    text = raw.replace("\r", "")
    lines = text.split("\n")
    head = {}
    for l in lines:
        m = re.match(r"Script (started|done) on \w+ (\d+ \w+ \d+ \d+:\d+:\d+ [AP]M) ([+-]\d\d)", l)
        if m:
            t = dt.datetime.strptime(m.group(2), "%d %b %Y %I:%M:%S %p")
            head[m.group(1)] = (t, int(m.group(3)))
    events, bad, nocs = [], 0, 0
    for n, l in enumerate(lines, 1):
        m = MARKER.search(l)
        if not m:
            continue
        s = l[m.start():]
        cm = CSUM.search(s)
        if cm:
            cs = 0
            for ch in s[:cm.start()]:
                cs ^= ord(ch)
            if cs != int(cm.group(1), 16):
                bad += 1
                continue
            body = s[:cm.start()]
        else:
            nocs += 1
            body = s.strip()
        row = body.split(",")
        if len(row) % 2 != 1 or len(set(row[1::2])) != len(row[1::2]):
            bad += 1
            continue
        d = dict(zip(row[1::2], row[2::2]))
        d["tag"] = row[0]
        d["line"] = n
        d["has_cs"] = bool(cm)
        events.append(d)
    return {"events": events, "head": head, "bad": bad, "nocs": nocs,
            "n_reset": text.count("Reset cause:"), "n_lines": len(lines), "raw": text}


def ival(d, k, default=None):
    try:
        return int(d[k])
    except (KeyError, ValueError):
        return default


# ----------------------------------------------------------------- metadata do thuc dia (do tac gia cung cap)
# singlehop/A6/KTX_F1..F4 thuc chat la toa A6, Source cach HOST 1..4 tang; multi-hop: khoang cach node -> HOST (m)
FLOORS = {"F1": 1, "F2": 2, "F3": 3, "F4": 4}
DIST_MULTI = {"A6": {2: 20, 3: 10, 4: 25, 5: 15}, "KTX": {2: 30, 3: 10, 4: 45, 5: 20}, "CS2": {3: 20, 5: 50, 4: 70, 2: 80}}


# ----------------------------------------------------------------- phan loai file
def classify(path):
    rel = path.relative_to(LOGS)
    parts = [p.lower() for p in rel.parts]
    area = "CS2" if any("cs2" in p for p in parts[:-1]) else "A6" if any("a6" in p for p in parts[:-1]) else "KTX" if any("ktx" in p for p in parts[:-1]) else "?"
    kind = "multi" if parts[0] == "multihop" else "single"
    stem = path.stem
    m = re.search(r"(\d+)m$", stem)
    point = (m.group(1) + " m") if m else (re.search(r"(F\d+)$", stem).group(1) if re.search(r"(F\d+)$", stem) else stem)
    dist = int(m.group(1)) if m else None
    return area, kind, point, dist


# ----------------------------------------------------------------- phan tich 1 phien
def analyze_session(path):
    area, kind, point, dist = classify(path)
    P = parse_log(path)
    ev = P["events"]
    cfgs = [e for e in ev if e["tag"] == "PERF_CONFIG"]
    cfg = cfgs[0] if cfgs else {}
    # chi so khoi PERF_SUMMARY -> truc thoi gian xap xi
    blocks_before = 0
    prev_sum_src = None
    last_tag, last_rep_src = None, None
    for e in ev:
        if e["tag"] == "PERF_SUMMARY":
            s = ival(e, "source", -1)
            if last_tag == "PERF_REPORT" and s == last_rep_src:
                # PERF_SUMMARY in ngay sau PERF_REPORT cua cung source = tong ket kich hoat theo su kien, khong phai khoi 30 s
                e["evt"] = True
                e["blk"] = max(blocks_before - 1, 0)
            else:
                if prev_sum_src is None or s <= prev_sum_src:
                    blocks_before += 1
                prev_sum_src = s
                e["blk"] = blocks_before - 1          # khoi thu may (0-based) cua dong nay
        else:
            e["blk"] = blocks_before              # so khoi da in truoc dong nay (SENSOR_DATA xen giua khoi van la cung khoi)
        last_tag = e["tag"]
        last_rep_src = ival(e, "source", None) if e["tag"] == "PERF_REPORT" else None
    n_blocks = blocks_before
    sess = {"file": str(path.relative_to(LOGS)).replace("\\", "/"), "area": area, "kind": kind,
            "point": point, "dist_m": dist, "run": cfg.get("run"), "gen_mode": cfg.get("gen_mode"),
            "gen_lead_ms": cfg.get("gen_lead_ms"), "tx_drive_dbm": cfg.get("tx_drive_dbm"),
            "source_ids": cfg.get("source_ids"), "expected": ival(cfg, "expected", 100),
            "ipi_s": ival(cfg, "ipi_s", 5), "n_perf_config": len(cfgs),
            "n_reset_cause": P["n_reset"], "host_restarts": max(0, P["n_reset"] - 1),
            "summary_blocks": n_blocks, "bad_checksum_lines": P["bad"], "no_checksum_lines": P["nocs"]}
    h = P["head"]
    if "started" in h and "done" in h:
        (t0, z0), (t1, z1) = h["started"], h["done"]
        u0, u1 = t0 - dt.timedelta(hours=z0), t1 - dt.timedelta(hours=z1)
        sess.update(start_vn=t0.strftime("%Y-%m-%d %H:%M:%S"), end_vn=t1.strftime("%Y-%m-%d %H:%M:%S"),
                    start_utc=u0.strftime("%Y-%m-%d %H:%M:%S"), end_utc=u1.strftime("%Y-%m-%d %H:%M:%S"),
                    capture_min=round((u1 - u0).total_seconds() / 60, 1))
    sess["summary_span_min"] = round(n_blocks * BLOCK_S / 60, 1)
    sess["floors"] = FLOORS.get(point) if kind == "single" else None

    # --- thoi gian xap xi cua tung dong SENSOR_DATA: khoi 30 s, dong deu trong khoi
    per_blk = defaultdict(list)
    for e in ev:
        if e["tag"] == "SENSOR_DATA":
            per_blk[e["blk"]].append(e)
    for j, lst in per_blk.items():
        for i, e in enumerate(lst):
            e["t_est"] = BLOCK_S * (max(j, 1) - 1) + BLOCK_S * (i + 0.5) / len(lst)

    expected = sess["expected"]
    sources = sorted({ival(e, "node") for e in ev if e["tag"] == "SENSOR_DATA"} |
                     {int(s) for s in (cfg.get("source_ids") or "").split(":") if s} |
                     {ival(e, "source") for e in ev if e["tag"] in ("PERF_SUMMARY", "PERF_REPORT")} - {None})
    rows, gaps, relay_rows, series, stalls = [], [], [], {}, []
    for src in sources:
        g0, rr0, st0 = len(gaps), len(relay_rows), len(stalls)
        sd = [e for e in ev if e["tag"] == "SENSOR_DATA" and ival(e, "node") == src]
        sm = [e for e in ev if e["tag"] == "PERF_SUMMARY" and ival(e, "source") == src]
        rp = [e for e in ev if e["tag"] == "PERF_REPORT" and ival(e, "source") == src]
        seen, dup_lines, flag0, ooo, hi = {}, 0, 0, 0, 0
        from_mismatch = 0
        for e in sd:
            if ival(e, "from", ival(e, "node")) != ival(e, "node"):
                from_mismatch += 1
            q = ival(e, "seq", 0)
            if not q or q > expected:
                continue
            if ival(e, "unique", 1) == 0:
                flag0 += 1
            if q in seen:
                dup_lines += 1
                continue
            seen[q] = e
            ooo += q < hi
            hi = max(hi, q)
        # --- do tre: chi dong co checksum hop le (da loc) va delay_valid=1
        delays, bad_delay = [], 0
        for q, e in seen.items():
            if ival(e, "delay_valid", 0) != 1:
                continue
            tk, hz = ival(e, "delay_ticks", -1), ival(e, "timer_hz", TICK_HZ)
            tx, rx = ival(e, "tx_net_ticks"), ival(e, "rx_slot_end_ticks")
            if tk < 0 or hz <= 0 or (tx is not None and rx is not None and ((rx - tx) & 0xffffffff) != tk):
                bad_delay += 1
                continue
            delays.append(1000.0 * tk / hz)
        # --- relay / hop
        rc_list = [ival(e, "relay_cnt") for e in seen.values() if ival(e, "hop_est_valid", 0) == 1
                   and 0 <= ival(e, "relay_cnt", 255) <= 254]
        hop_list = [ival(e, "hop_est") for e in seen.values() if ival(e, "hop_est_valid", 0) == 1]
        # --- so lieu tu HOST (counter firmware) va REPORT cua Source
        rec_host = max((ival(e, "received", 0) for e in sm), default=None)
        final_sum = any(ival(e, "final", 0) == 1 for e in sm)
        repset = {tuple(ival(e, k, -1) for k in ("generated", "queued", "tx_started", "queue_failed",
                                                 "deadline_missed", "tx_start_failed", "drain_timeout")) for e in rp}
        rep = list(repset)[0] if len(repset) == 1 else None
        n_rec_log = len(seen)
        r = {"file": sess["file"], "area": area, "kind": kind, "point": point, "dist_m": dist, "source": src,
             "expected": expected, "floors": FLOORS.get(point) if kind == "single" else None,
             "received_log": n_rec_log, "received_host": rec_host,
             "capture_loss_lines": (rec_host - n_rec_log) if rec_host is not None else None,
             "duplicate_lines": dup_lines, "unique0_lines": flag0, "out_of_order": ooo,
             "from_ne_node": from_mismatch, "final_in_summary": int(final_sum), "report_lines": len(rp),
             "report_conflict": int(len(repset) > 1)}
        if rep:
            for k, v in zip(("generated", "queued", "tx_started", "queue_failed", "deadline_missed",
                             "tx_start_failed", "drain_timeout"), rep):
                r["report_" + k] = v
        final = bool(rep) and final_sum
        r["final"] = int(final)
        if kind == "multi":
            r["dist_m"] = DIST_MULTI[area].get(src)
        rcv = rec_host if rec_host is not None else n_rec_log
        r["received_for_prr"] = rcv
        den = rep[2] if rep else None          # tx_started
        if final and den:
            r["prr_pct"] = pct(rcv / den)
            r["prr_cp95_lower_pct"] = pct(cp_lower(rcv, den))
            r["prr_rule_of_three_lower_pct"] = pct(1 - 3 / den) if rcv == den else None
        else:
            r["prr_pct"] = r["prr_cp95_lower_pct"] = r["prr_rule_of_three_lower_pct"] = None
        r["provisional_received_over_expected_pct"] = pct(rcv / expected) if expected else None
        if delays:
            r.update(delay_count=len(delays), delay_min_ms=round(min(delays), 1),
                     delay_p50_ms=round(statistics.median(delays), 1), delay_mean_ms=round(statistics.fmean(delays), 1),
                     delay_p95_ms=round(quantile_nr(delays, 0.95), 1), delay_max_ms=round(max(delays), 1),
                     delay_p50_excl_first_ms=round(statistics.median(
                         [1000.0 * ival(e, "delay_ticks") / ival(e, "timer_hz", TICK_HZ) for q, e in sorted(seen.items())
                          if q != min(seen) and ival(e, "delay_valid", 0) == 1 and ival(e, "delay_ticks", -1) >= 0] or [0]), 1))
        if delays:  # cot theo giay, 3 chu so thap phan, tinh tu gia tri goc (khong lam tron qua ms)
            r.update(delay_min_s=round(min(delays) / 1000.0, 3), delay_p50_s=round(statistics.median(delays) / 1000.0, 3),
                     delay_mean_s=round(statistics.fmean(delays) / 1000.0, 3),
                     delay_p95_s=round(quantile_nr(delays, 0.95) / 1000.0, 3), delay_max_s=round(max(delays) / 1000.0, 3))
        r["delay_invalid_excluded"] = bad_delay
        r["relay_cnt_hist"] = ";".join("%d:%d" % kv for kv in sorted(Counter(rc_list).items()))
        r["hop_est_hist"] = ";".join("%d:%d" % kv for kv in sorted(Counter(hop_list).items()))
        r["relay_gt0_share_pct"] = pct(sum(1 for x in rc_list if x > 0) / len(rc_list)) if rc_list else None

        # --- truc thoi gian: t(seq) = off + 5*seq
        pts = [(q, e["t_est"]) for q, e in seen.items() if "t_est" in e]
        off, resid = None, None
        if pts:
            diffs = [t - IPI_S * q for q, t in pts]
            off = statistics.median(diffs)
            resid = statistics.pstdev(diffs) if len(diffs) > 1 else 0.0
        # --- dung sinh goi (firmware FRESH_ONLY khong cap seq khi mat dong bo / chua duoc xac nhan luong):
        #     x = 30*(chenh lech khoi) - 5*(chenh lech seq); x lon => thoi gian troi qua ma seq khong tang
        recvs = sorted(seen.items())
        stall_lb = stall_est = n_stall = 0
        for (qa, ea), (qb, eb) in zip(recvs, recvs[1:]):
            x = BLOCK_S * (eb["blk"] - ea["blk"]) - IPI_S * (qb - qa)
            if x >= 30:
                stalls.append({"file": sess["file"], "area": area, "kind": kind, "point": point, "source": src,
                               "seq_before": qa, "seq_after": qb, "delta_seq": qb - qa,
                               "excess_time_s": round(x, 1), "stall_lower_bound_s": round(max(0, x - BLOCK_S), 1),
                               "certainty": "chac_chan(>=60s)" if x >= 60 else "co_the(30-60s)",
                               "blk_before": ea["blk"], "blk_after": eb["blk"],
                               "log_line_before": ea["line"], "log_line_after": eb["line"]})
            if x >= 60:
                n_stall += 1
                stall_est += x
                stall_lb += x - BLOCK_S
        r["stall_events_ge60s"] = n_stall
        r["stall_est_s"] = round(stall_est, 1)
        r["stall_lower_bound_s"] = round(stall_lb, 1)
        has_blk = sorted({e["blk"] for e in seen.values()})
        if has_blk:
            silent = [b for b in range(has_blk[0], has_blk[-1] + 1) if b not in set(has_blk)]
            run_, best = 0, 0
            prevb = None
            for b in silent:
                run_ = run_ + 1 if prevb is not None and b == prevb + 1 else 1
                best = max(best, run_)
                prevb = b
            r.update(first_rx_blk=has_blk[0], last_rx_blk=has_blk[-1], silent_blocks=len(silent),
                     longest_silent_blocks=best, rx_span_blocks=has_blk[-1] - has_blk[0] + 1)
        if seen:
            sp = (r["last_rx_blk"] - r["first_rx_blk"]) * BLOCK_S
            r["span_excess_s"] = round(sp - IPI_S * (max(seen) - min(seen)), 1)   # +-30 s: thoi gian troi qua ma seq khong tang
            r["gen_time_fraction_pct"] = pct(min(1.0, IPI_S * (max(seen) - min(seen)) / sp)) if sp > 0 else None
        r["first_seq_rx"] = min(seen) if seen else None
        r["last_seq_rx"] = max(seen) if seen else None
        # --- gap
        got = sorted(seen)
        missing = [q for q in range(1, expected + 1) if q not in seen]
        r["missing_seqs"] = len(missing)
        runs_ = []
        for q in missing:
            if runs_ and runs_[-1][1] == q - 1:
                runs_[-1][1] = q
            else:
                runs_.append([q, q])
        # khoang chenh lech giua counter HOST va so dong trong log, theo khoi 30 s
        mism = {}
        if sm:
            blk_rec = {}
            for e in sm:
                if e.get("evt"):
                    continue
                blk_rec[e["blk"]] = ival(e, "received", 0)
            prev_r, prev_b = 0, -1
            for b in sorted(blk_rec):
                lines_in = sum(1 for e in seen.values() if e["blk"] == b)
                # cac dong co blk==b nam truoc khoi b va duoc dem vao summary cua khoi b
                delta = blk_rec[b] - prev_r
                if delta != lines_in and b - prev_b == 1:
                    mism[b] = delta - lines_in
                prev_r, prev_b = blk_rec[b], b
        r["capture_mismatch_blocks"] = len(mism)
        for a, b in runs_:
            before = max([q for q in got if q < a], default=None)
            after = min([q for q in got if q > b], default=None)
            kind_g = "dau" if before is None else "cuoi" if after is None else "giua"
            t_a = None if off is None else round(off + IPI_S * a, 1)
            t_b = None if off is None else round(off + IPI_S * b, 1)
            # co khoi mismatch (mat dong log) chong len khoang thoi gian nay khong?
            blks = set()
            for q in (before, after):
                if q is not None and q in seen:
                    blks.add(seen[q]["blk"])
            lo_blk = min(blks) if blks else 0
            hi_blk = max(blks) if blks else n_blocks
            if kind_g == "cuoi":
                hi_blk = n_blocks
            if kind_g == "dau":
                lo_blk = 0
            cap = [bk for bk in mism if lo_blk <= bk <= hi_blk]
            xex = None
            if before in seen and after in seen:
                xex = BLOCK_S * (seen[after]["blk"] - seen[before]["blk"]) - IPI_S * (after - before)
            if kind_g == "giua":
                cause = ("dung_sinh_goi+mat" if xex is not None and xex >= 60 else
                         "goi_da_phat_nhung_HOST_khong_nhan" if xex is not None and xex < 30 else "khong_ro(30-60s)")
            elif kind_g == "dau":
                cause = "dau_phien:goi_da_phat_nhung_HOST_chua_nhan"
            else:
                cause = "cuoi_phien:HOST_ngung_nhan_hoac_phien_chua_ket_thuc"
            gaps.append({"file": sess["file"], "area": area, "kind": kind, "point": point, "source": src,
                         "gap_start_seq": a, "gap_end_seq": b, "gap_len": b - a + 1, "position": kind_g,
                         "est_start_s": t_a, "est_end_s": t_b,
                         "prev_rx_seq": before, "next_rx_seq": after,
                         "prev_relay_cnt": ival(seen[before], "relay_cnt") if before in seen else None,
                         "next_relay_cnt": ival(seen[after], "relay_cnt") if after in seen else None,
                         "next_delay_ms": ival(seen[after], "delay_ms") if after in seen else None,
                         "log_line_prev": seen[before]["line"] if before in seen else None,
                         "log_line_next": seen[after]["line"] if after in seen else None,
                         "excess_time_between_neighbors_s": None if xex is None else round(xex, 1),
                         "likely_cause(suy_luan)": cause,
                         "capture_mismatch_in_window": int(bool(cap))})
        r["gap_count"] = len(runs_)
        r["gap_max_len"] = max((b - a + 1 for a, b in runs_), default=0)
        r["gap_single_seq"] = sum(1 for a, b in runs_ if a == b)
        r["lost_in_bursts_ge3"] = sum(b - a + 1 for a, b in runs_ if b - a + 1 >= 3)
        r["lost_total_from_log"] = len(missing)

        # --- PRR theo relay_cnt: P(goi ke tiep bi mat | relay_cnt cua goi truoc)
        if kind == "multi" or any(x > 0 for x in rc_list):
            cls = defaultdict(lambda: [0, 0])
            for q, e in seen.items():
                if ival(e, "hop_est_valid", 0) != 1 or q >= expected:
                    continue
                c = "relay_cnt=0" if ival(e, "relay_cnt", 0) == 0 else "relay_cnt>0"
                cls[c][0] += 1
                cls[c][1] += (q + 1) not in seen
            for c, (nn, kk) in sorted(cls.items()):
                relay_rows.append({"file": sess["file"], "area": area, "point": point, "source": src, "class": c,
                                   "n_received_in_class": nn, "n_followed_by_missing_seq": kk,
                                   "next_loss_rate_pct": pct(kk / nn) if nn else None,
                                   "share_of_received_pct": pct(nn / len(rc_list)) if rc_list else None})
        series[src] = {"blks": {e["blk"] for e in seen.values()}, "blk_counts": dict(Counter(e["blk"] for e in seen.values())), "t": {q: e.get("t_est") for q, e in seen.items()}, "seen": {q: (ival(e, "relay_cnt"), ival(e, "delay_ms")) for q, e in seen.items()},
                       "missing_runs": runs_, "off": off, "rec_host": rec_host, "final": final}
        r["_active"] = n_rec_log > 0 or bool(rec_host)
        rows.append(r)
    # nguon 'tham gia' = co goi nhan, co REPORT hoac co counter HOST > 0; neu khong nguon nao: gia dinh nguon 2
    act = [r for r in rows if r["_active"] or r["report_lines"]]
    assumed = False
    if not act:
        act = [r for r in rows if r["source"] == 2]
        assumed = True
        for r in act:
            r["assumed_source"] = 1
    keep = {r["source"] for r in act}
    sess["inactive_sources"] = ":".join(str(r["source"]) for r in rows if r["source"] not in keep)
    gaps = [g for g in gaps if g["source"] in keep]
    relay_rows = [g for g in relay_rows if g["source"] in keep]
    stalls = [g for g in stalls if g["source"] in keep]
    rows = [r for r in rows if r["source"] in keep]
    series = {k: v for k, v in series.items() if k in keep}
    sess["active_sources"] = ":".join(str(r["source"]) for r in rows) + ("(gia dinh)" if assumed else "")
    # khoi im lang chung: khong nguon nao co goi trong khoi, giua lan nhan dau va cuoi cua ca phien
    allb = set()
    for sr in series.values():
        allb |= {e for e in sr.get("blks", set())}
    if allb:
        lo, hi = min(allb), max(allb)
        sess["blocks_all_silent"] = len([b for b in range(lo, hi + 1) if b not in allb])
        sess["blocks_in_rx_span"] = hi - lo + 1
    sess["t_end_est_s"] = n_blocks * BLOCK_S
    return sess, rows, gaps, relay_rows, series, stalls


# ----------------------------------------------------------------- ghi CSV
def write_csv(path, rows):
    if not rows:
        return
    keys = list(dict.fromkeys(k for r in rows for k in r if not k.startswith("_")))
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main():
    files = sorted(LOGS.rglob("*.log"), key=lambda p: (classify(p)[1], classify(p)[0], classify(p)[3] or 0, p.name))
    S, R, G, RR, SER, ST = [], [], [], [], {}, []
    for f in files:
        s, r, g, rr, ser, st = analyze_session(f)
        ST += st
        S.append(s)
        R += r
        G += g
        RR += rr
        SER[s["file"]] = ser
    write_csv(OUT / "sessions.csv", S)
    write_csv(OUT / "per_source.csv", R)
    write_csv(OUT / "gaps.csv", G)
    write_csv(OUT / "relay_next_loss.csv", RR)
    write_csv(OUT / "stalls.csv", ST)
    import pickle
    with open(OUT / "_cache.pkl", "wb") as f:
        pickle.dump({"S": S, "R": R, "G": G, "RR": RR, "SER": SER, "ST": ST}, f)
    print("sessions:", len(S), "per_source rows:", len(R), "gaps:", len(G))


if __name__ == "__main__":
    main()
