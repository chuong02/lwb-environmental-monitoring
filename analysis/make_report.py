#!/usr/bin/env python3
"""Doc out/_cache.pkl (do analyze_runs.py tao) -> ve PNG + bang Markdown (out/_tables.md)."""
import math
import pickle
import statistics
from collections import defaultdict
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = Path(__file__).resolve().parent
OUT = HERE / "out"
D = pickle.load(open(OUT / "_cache.pkl", "rb"))
S, R, G, RR, SER, ST = D["S"], D["R"], D["G"], D["RR"], D["SER"], D["ST"]
plt.rcParams.update({"font.size": 9, "axes.grid": True, "grid.alpha": 0.3, "figure.dpi": 130})


def f(x, nd=1, none="–"):
    return none if x is None or x == "" else (("%." + str(nd) + "f") % x)


def label(s):
    return "%s %s" % (s["area"], s["point"])


def rl(r):
    if r["kind"] == "multi":
        return "%s multi, node %s (%s m)" % (r["area"], r["source"], r["dist_m"])
    if r.get("floors"):
        return "%s, %s tầng (%s)" % (r["area"], r["floors"], r["point"])
    return "%s %s" % (r["area"], r["point"])


# ============================================================ BANG
md = []
md.append("### Bảng phiên đo\n")
md.append("| # | File | Khu | Loại | Điểm đo | Run | gen_mode / lead | Drive dBm | Source tham gia | Bắt đầu VN | Kết thúc VN | Bắt đầu UTC | Kết thúc UTC | Phút | HOST restart | Dòng sai checksum |")
md.append("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
for i, s in enumerate(S, 1):
    md.append("| %d | `%s` | %s | %s | %s | %s | %s / %s | %s | %s | %s | %s | %s | %s | %s | %d | %d |" % (
        i, s["file"].split("/")[-1], s["area"], "multi-hop" if s["kind"] == "multi" else "single-hop", s["point"],
        s["run"], s["gen_mode"], s["gen_lead_ms"], s["tx_drive_dbm"], s["active_sources"],
        s["start_vn"][5:], s["end_vn"][11:], s["start_utc"][5:], s["end_utc"][11:], f(s["capture_min"]),
        s["host_restarts"], s["bad_checksum_lines"]))
md.append("")
md.append("Cấu hình giống nhau ở mọi phiên: run 510, expected 100, ipi 5 s, kênh 26, `source_ids=2:3:4:5`, N = 3, `fresh_only=1`, `report_every=60`.")
md.append("")

md.append("### Bảng theo Source\n")
md.append("| Phiên | Src | Nhận (HOST) | Nhận (log) | Final | PRR % | CP95 dưới % | Generated/Queued/TX | Delay min / p50 / mean / p95 / max (ms) | Gap (số / dài nhất) | Dừng sinh gói (ước, s) |")
md.append("|---|---|---|---|---|---|---|---|---|---|---|")
for r in R:
    rep = "%s/%s/%s" % (r.get("report_generated", "–"), r.get("report_queued", "–"), r.get("report_tx_started", "–")) if r.get("report_generated") is not None else "–"
    prr = f(r["prr_pct"]) if r.get("prr_pct") is not None else "(tạm) %s" % f(r["provisional_received_over_expected_pct"])
    ex = r.get("span_excess_s")
    md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s / %s | %s |" % (
        rl(r), r["source"], r["received_host"], r["received_log"], "có" if r["final"] else "không",
        prr, f(r["prr_cp95_lower_pct"]), rep,
        "%s / %s / %s / %s / %s" % (f(r.get("delay_min_ms"), 0), f(r.get("delay_p50_ms"), 0), f(r.get("delay_mean_ms"), 0),
                                    f(r.get("delay_p95_ms"), 0), f(r.get("delay_max_ms"), 0)) if r.get("delay_count") else "–",
        r["gap_count"], r["gap_max_len"], f(None if ex is None else max(0, ex), 0)))
md.append("")
md.append("PRR = nhận / `tx_started` chỉ khi Source đã gửi `PERF_REPORT` và HOST báo `final=1`; nếu chưa final, ô PRR ghi “(tạm)” = nhận / 100. "
          "CP95 dưới = cận dưới Clopper–Pearson hai phía 95 %. Khi nhận 100/100: cận dưới 96,38 % (rule of three, một phía: 97 %). "
          "“Dừng sinh gói” = (thời gian giữa khối nhận đầu và khối nhận cuối) − 5 s × (seq cuối − seq đầu), âm thì ghi 0; thời gian lấy từ đồng hồ khối PERF_SUMMARY 30 s nên sai số ±30 s, và các giá trị dưới 60 s coi là không có dừng.")
md.append("")

# ---- gap
md.append("### Phân bố khoảng trống (gap) theo Source\n")
md.append("| Phiên | Src | Gói mất (log) | Số gap | Gap kỳ vọng nếu mất độc lập | Gap đơn (1 gói) | Gói mất trong cụm ≥ 3 | Gap dài nhất | Mất ở đầu | Mất ở cuối | Khối 30 s im lặng / khoảng nhận | Im lặng dài nhất (khối) |")
md.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
for r in R:
    gl = [g for g in G if g["file"] == r["file"] and g["source"] == r["source"]]
    lead = sum(g["gap_len"] for g in gl if g["position"] == "dau")
    tail = sum(g["gap_len"] for g in gl if g["position"] == "cuoi")
    N = r["expected"]
    pl = r["lost_total_from_log"] / N
    expg = (N - 1) * pl * (1 - pl) + pl
    md.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s / %s | %s |" % (
        rl(r), r["source"], r["lost_total_from_log"], r["gap_count"], f(expg, 0), r["gap_single_seq"],
        r["lost_in_bursts_ge3"], r["gap_max_len"], lead, tail, r.get("silent_blocks", "–"), r.get("rx_span_blocks", "–"),
        r.get("longest_silent_blocks", "–")))
md.append("")
md.append("“Gap kỳ vọng nếu mất độc lập” = (N−1)·p·(1−p) + p với p = gói mất / 100 (số đoạn mất liên tiếp kỳ vọng khi mỗi gói mất độc lập với xác suất p). Quan sát ít hơn nhiều so với kỳ vọng nghĩa là mất theo cụm; gần bằng nghĩa là mất rải rác. Đây là so sánh thô, không phải kiểm định thống kê.")
md.append("")

# ---- phan loai nguyen nhan gap theo seq-time
cause_tot = defaultdict(lambda: defaultdict(int))
for g in G:
    cause_tot[(g["file"], g["source"])][g["likely_cause(suy_luan)"]] += g["gap_len"]
md.append("### Nguồn gốc các gói mất (suy luận từ seq và thời gian)\n")
md.append("| Phiên | Src | HOST đã nhận nhưng log thiếu (mất dòng UART) | Gói đã phát, HOST không nhận (thời gian khớp, giữa phiên) | Gap có dừng sinh gói ≥ 60 s | Không rõ (30–60 s) | Đầu phiên | Cuối phiên |")
md.append("|---|---|---|---|---|---|---|---|")
for r in R:
    c = cause_tot[(r["file"], r["source"])]
    md.append("| %s | %s | %s | %s | %s | %s | %s | %s |" % (
        rl(r), r["source"], r["capture_loss_lines"] or 0,
        c.get("goi_da_phat_nhung_HOST_khong_nhan", 0), c.get("dung_sinh_goi+mat", 0), c.get("khong_ro(30-60s)", 0),
        c.get("dau_phien:goi_da_phat_nhung_HOST_chua_nhan", 0), c.get("cuoi_phien:HOST_ngung_nhan_hoac_phien_chua_ket_thuc", 0)))
md.append("")

# ---- tuong quan giua cac source (multi-hop)
md.append("### Tương quan mất gói giữa các Source (multi-hop)\n")
for s in S:
    if s["kind"] != "multi":
        continue
    ser = SER[s["file"]]
    srcs = sorted(ser)
    pairs = []
    for i, a in enumerate(srcs):
        for b in srcs[i + 1:]:
            ka, kb = sorted(ser[a]["blk_counts"]), sorted(ser[b]["blk_counts"])
            lo2, hi2 = max(ka[0], kb[0], 1), min(ka[-1], kb[-1])
            rng2 = list(range(lo2, hi2 + 1))
            xa = [ser[a]["blk_counts"].get(k, 0) for k in rng2]
            xb = [ser[b]["blk_counts"].get(k, 0) for k in rng2]
            if len(rng2) > 3 and statistics.pstdev(xa) > 0 and statistics.pstdev(xb) > 0:
                pairs.append("%d–%d: r = %s (n = %d khối)" % (a, b, f(statistics.correlation(xa, xb), 2), len(rng2)))
    allb = sorted(set().union(*[set(ser[x]["blk_counts"]) for x in srcs]))
    rng = [b for b in range(max(allb[0], 1), allb[-1] + 1)]
    md.append("**%s** — %d khối 30 s; HOST không nhận gói nào của bất kỳ Source nào trong %s khối." % (
        label(s), len(rng), s.get("blocks_all_silent", "?")))
    md.append("Hệ số tương quan Pearson của số gói nhận mỗi khối 30 s giữa các cặp Source, chỉ tính trong đoạn cả hai cùng đang chạy: " + "; ".join(pairs) + ".")
    md.append("")

# ---- relay next loss
md.append("### Gói mất kế tiếp theo relay_cnt của gói nhận được liền trước (không phải PRR theo relay)\n")
md.append("PRR theo relay_cnt không xác định được vì gói mất không có `relay_cnt`. Cách thay thế: với mỗi gói nhận được (seq s, `hop_est_valid=1`), xét seq s+1 có mất không.\n")
md.append("| Phiên | Src | Lớp | Số gói nhận | Tỷ trọng % | Sau đó mất s+1 | Tỷ lệ mất % |")
md.append("|---|---|---|---|---|---|---|")
for x in RR:
    if x["file"].find("ultihop") < 0:
        continue
    md.append("| %s | %s | %s | %s | %s | %s | %s |" % (x["area"] + " " + x["point"], x["source"], x["class"],
              x["n_received_in_class"], f(x["share_of_received_pct"]), x["n_followed_by_missing_seq"], f(x["next_loss_rate_pct"])))
md.append("")
md.append("Histogram relay_cnt (giá trị:số gói) của các Source:\n")
md.append("| Phiên | Src | relay_cnt | hop_est |")
md.append("|---|---|---|---|")
for r in R:
    md.append("| %s | %s | %s | %s |" % (rl(r), r["source"], r["relay_cnt_hist"] or "–", r["hop_est_hist"] or "–"))
md.append("")
(OUT / "_tables.md").write_text("\n".join(md), encoding="utf-8")

# ============================================================ HINH
def prr_pt(r):
    if r.get("prr_pct") is not None:
        return r["prr_pct"], r["prr_cp95_lower_pct"], True
    return r["provisional_received_over_expected_pct"], None, False


single = [(s, [r for r in R if r["file"] == s["file"]]) for s in S if s["kind"] == "single"]
multi = [(s, [r for r in R if r["file"] == s["file"]]) for s in S if s["kind"] == "multi"]


def errbar(ax, x, r, color, marker, ms=6, label=None):
    y, lo, fin = prr_pt(r)
    y = y or 0
    ax.errorbar([x], [y], yerr=[[y - lo] if lo is not None else [0], [0]], fmt=marker, mfc=color if fin else "white",
                color=color, capsize=3, ms=ms, label=label)
    ax.annotate("%.0f" % y, (x, y), textcoords="offset points", xytext=(0, 7), ha="center", fontsize=8)


# ---------------- PRR theo khoang cach: KTX va CS2 (single + multi), A6 single (tang), A6 multi (m)
AREA_COL = {"KTX": ("C0", "C3"), "CS2": ("C4", "C5"), "A6": ("C1", "C2")}
fig, ax = plt.subplots(2, 2, figsize=(11, 8.2))
ax = ax.flatten()
for k, area in enumerate(("KTX", "CS2")):
    cs, cm = AREA_COL[area]
    pts = sorted([(s["dist_m"], r) for s, rs in single if s["area"] == area for r in rs], key=lambda t: t[0])
    ax[k].plot([d for d, _ in pts], [(prr_pt(r)[0] or 0) for _, r in pts], color=cs, lw=0.8, alpha=0.5)
    for i, (d, r) in enumerate(pts):
        errbar(ax[k], d, r, cs, "o", label="single-hop" if i == 0 else None)
    for s, rs in multi:
        if s["area"] != area:
            continue
        for i, r in enumerate(sorted(rs, key=lambda x: x["dist_m"])):
            errbar(ax[k], r["dist_m"], r, cm, "s", ms=7, label="multi-hop" if i == 0 else None)
            ax[k].annotate("node %d" % r["source"], (r["dist_m"], prr_pt(r)[0] or 0), textcoords="offset points", xytext=(0, -13), ha="center", fontsize=7, color=cm)
    ax[k].set_title({"KTX": "Ký túc xá khu A (KTX)", "CS2": "Cơ sở 2 (CS2)"}[area])
    ax[k].set_xlabel("Khoảng cách tới HOST (m)")
    ax[k].set_ylim(-5, 112)
    ax[k].legend(loc="lower left", fontsize=8)
ax[0].set_ylabel("PRR (%)")
a6s = sorted([x for x in single if x[0]["area"] == "A6"], key=lambda t: t[0]["floors"])
for s, rs in a6s:
    errbar(ax[2], s["floors"], rs[0], "C1", "o")
ax[2].set_xticks([1, 2, 3, 4])
ax[2].set_xlabel("Số tầng giữa Source và HOST")
ax[2].set_title("A6, single-hop")
ax[2].set_ylim(-5, 112)
for s, rs in multi:
    if s["area"] != "A6":
        continue
    for r in sorted(rs, key=lambda x: x["dist_m"]):
        errbar(ax[3], r["dist_m"], r, "C2", "s", ms=7)
        ax[3].annotate("node %d" % r["source"], (r["dist_m"], prr_pt(r)[0] or 0), textcoords="offset points", xytext=(0, -13), ha="center", fontsize=7, color="C2")
ax[3].set_xlabel("Khoảng cách tới HOST (m)")
ax[3].set_title("A6, multi-hop")
ax[3].set_xlim(5, 30)
ax[3].set_ylim(-5, 112)
fig.suptitle("PRR theo điểm đo; thanh = cận dưới Clopper–Pearson 95 %; ký hiệu rỗng = phiên chưa final (tạm = nhận/100)", fontsize=9)
fig.tight_layout()
fig.savefig(OUT / "prr_vs_distance.png")
plt.close(fig)

# ---------------- do tre theo khoang cach
fig, ax = plt.subplots(2, 2, figsize=(11, 8.2))
ax = ax.flatten()


def draw_delay(a, x, r, col, marker="o"):
    if not r.get("delay_count"):
        return
    a.vlines(x, r["delay_min_ms"], r["delay_p95_ms"], color=col, lw=2)
    a.plot([x], [r["delay_p50_ms"]], marker, color=col)
    a.plot([x], [r["delay_max_ms"]], "x", color=col)


for s, rs in single:
    if s["area"] in ("KTX", "CS2"):
        draw_delay(ax[0 if s["area"] == "KTX" else 1], s["dist_m"], rs[0], AREA_COL[s["area"]][0])
    else:
        draw_delay(ax[2], s["floors"], rs[0], "C1")
for s, rs in multi:
    for r in rs:
        if s["area"] in ("KTX", "CS2"):
            draw_delay(ax[0 if s["area"] == "KTX" else 1], r["dist_m"], r, AREA_COL[s["area"]][1], "s")
        else:
            draw_delay(ax[3], r["dist_m"], r, "C2", "s")
ax[0].set_title("KTX (tròn: single-hop, vuông: multi-hop)")
ax[1].set_title("CS2 (tròn: single-hop, vuông: multi-hop)")
for a in (ax[0], ax[1], ax[3]):
    a.set_xlabel("Khoảng cách tới HOST (m)")
ax[0].set_ylabel("Độ trễ (ms)")
ax[2].set_title("A6, single-hop")
ax[2].set_xlabel("Số tầng")
ax[2].set_xticks([1, 2, 3, 4])
ax[3].set_title("A6, multi-hop")
for a in ax:
    a.set_ylim(0, 700)
fig.suptitle("Độ trễ (enqueue → cuối slot HOST), dòng checksum hợp lệ: thanh = min…p95, chấm = p50, × = max (kẹp ở 700 ms; max ngoài khung là gói đầu tiên ~4,8 s)", fontsize=9)
fig.tight_layout()
fig.savefig(OUT / "delay_vs_distance.png")
plt.close(fig)


# ---------------- relay_cnt: ty trong rc=2 theo khoang cach (single-hop) + histogram multi-hop
def hist_of(r):
    d = {}
    for kv in (r["relay_cnt_hist"] or "").split(";"):
        if kv:
            k, v = kv.split(":")
            d[int(k)] = int(v)
    return d


fig, ax = plt.subplots(2, 2, figsize=(11, 7.6))
ax = ax.flatten()
for area in ("KTX", "CS2"):
    xs, ys, ns = [], [], []
    for s, rs in single:
        if s["area"] == area and rs[0].get("received_host"):
            h = hist_of(rs[0])
            n = sum(h.values())
            xs.append(s["dist_m"])
            ys.append(100.0 * h.get(2, 0) / n)
            ns.append(n)
    ax[0].plot(xs, ys, "o-", color=AREA_COL[area][0], label=area)
    for x_, y_, n_ in zip(xs, ys, ns):
        ax[0].annotate("%.0f%%" % y_, (x_, y_), textcoords="offset points", xytext=(0, 6), ha="center", fontsize=7)
ax[0].legend(fontsize=7)
ax[0].set_title("Single-hop: tỷ trọng relay_cnt = 2")
ax[0].set_xlabel("Khoảng cách (m)")
ax[0].set_ylabel("% số gói nhận")
ax[0].set_ylim(0, 45)
for a, area in ((ax[1], "A6"), (ax[2], "KTX"), (ax[3], "CS2")):
    mrs = [r for s, rs in multi if s["area"] == area for r in rs]
    width = 0.2
    for i, r in enumerate(sorted(mrs, key=lambda x: x["source"])):
        h = hist_of(r)
        a.bar([k + (i - 1.5) * width for k in range(9)], [h.get(k, 0) for k in range(9)], width,
              label="node %d (%s m)" % (r["source"], r["dist_m"]))
    a.set_xticks(range(9))
    a.set_xlabel("relay_cnt")
    a.set_ylabel("Số gói")
    a.set_title("%s, multi-hop" % area)
    a.legend(fontsize=7)
fig.tight_layout()
fig.savefig(OUT / "relay_cnt_hist.png")
plt.close(fig)


# seq theo thoi gian
def seqtime(ax, s, src, color_by_relay=True):
    r = [x for x in R if x["file"] == s["file"] and x["source"] == src][0]
    ser = SER[s["file"]][src]
    seen, tm = ser["seen"], ser["t"]
    xs = {q: tm[q] / 60 for q in seen if tm.get(q) is not None}
    got = sorted(xs)
    for lab, cond, col in (("relay_cnt = 0", lambda c: c == 0, "C0"), ("relay_cnt > 0", lambda c: c and c > 0, "C1")):
        qq = [q for q in got if cond(seen[q][0])]
        ax.plot([xs[q] for q in qq], qq, "o", ms=3, color=col, label=lab)
    # goi mat: noi suy thoi gian giua hai goi lan can
    mx, my, ex_, ey = [], [], [], []
    for a, b in ser["missing_runs"]:
        before = max([q for q in got if q < a], default=None)
        after = min([q for q in got if q > b], default=None)
        for q in range(a, b + 1):
            if before is not None and after is not None:
                t = xs[before] + (xs[after] - xs[before]) * (q - before) / (after - before)
                mx.append(t)
                my.append(q)
                continue
            elif before is not None:
                t = xs[before] + 5 * (q - before) / 60
            elif after is not None:
                t = xs[after] - 5 * (after - q) / 60
            else:
                continue
            ex_.append(t)
            ey.append(q)
    ax.plot(mx, my, "x", ms=3.5, color="red", label="seq mất (thời gian nội suy)")
    ax.plot(ex_, ey, "x", ms=3.5, color="#d9a0a0", label="seq mất đầu/cuối phiên (thời gian ngoại suy, 5 s/seq, không chắc)")
    ax.set_ylim(0, 102)
    ax.set_ylabel("seq")
    ax.set_title("node %d%s: nhận %s/100, %d gap, dừng sinh gói ≈ %s s" % (src, (" (%s m)" % r["dist_m"]) if r["kind"] == "multi" else "", r["received_host"], r["gap_count"], f(None if r.get("span_excess_s") is None else max(0, r["span_excess_s"]), 0)), fontsize=8)


for s, rs in multi:
    srcs = sorted(x["source"] for x in rs)
    fig, axs = plt.subplots(len(srcs), 1, figsize=(10, 2.2 * len(srcs) + 0.8), sharex=True)
    for a, src in zip(axs, srcs):
        seqtime(a, s, src)
    axs[0].legend(loc="lower right", fontsize=6, ncol=2)
    axs[-1].set_xlabel("Thời gian từ khi HOST khởi động (phút, ước lượng theo khối PERF_SUMMARY 30 s, sai số ±30 s)")
    fig.suptitle("Seq nhận được theo thời gian — %s (multi-hop)" % s["area"], fontsize=10)
    fig.tight_layout()
    fig.savefig(OUT / ("seq_vs_time_multihop_%s.png" % s["area"].lower()))
    plt.close(fig)

# single-hop: 10 phien trong 1 hinh
act = [(s, rs[0]["source"]) for s, rs in single if rs[0].get("received_host")]
fig, axs = plt.subplots(math.ceil(len(act) / 2), 2, figsize=(11, 2.1 * math.ceil(len(act) / 2) + 0.8))
axs = axs.flatten()
for a, (s, src) in zip(axs, act):
    seqtime(a, s, src)
    a.set_title("%s: " % label(s) + a.get_title(), fontsize=8)
for a in axs[len(act):]:
    a.axis("off")
axs[0].legend(loc="lower right", fontsize=6)
fig.suptitle("Seq nhận được theo thời gian — single-hop (Source 2); trục x: phút từ khi HOST khởi động", fontsize=10)
fig.tight_layout()
fig.savefig(OUT / "seq_vs_time_singlehop.png")
plt.close(fig)

sel = [(s, rs[0]["source"]) for s, rs in single if s["area"] == "KTX" and s["dist_m"] in (30, 40)]
fig, axs = plt.subplots(len(sel), 1, figsize=(9, 2.6 * len(sel) + 0.8), sharex=False)
for a, (s, src) in zip(axs, sel):
    seqtime(a, s, src)
    a.set_title("KTX %s: " % s["point"] + a.get_title(), fontsize=8)
    a.set_xlabel("Thời gian từ khi HOST khởi động (phút, xấp xỉ ±30 s)")
axs[0].legend(loc="lower right", fontsize=6)
fig.tight_layout()
fig.savefig(OUT / "seq_vs_time_ktx_30_40.png")
plt.close(fig)
print("ok")
