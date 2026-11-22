#!/usr/bin/env python3
"""Ghep out/_tables.md (do make_report.py sinh) va phan nhan xet thanh out/SUMMARY.md."""
from pathlib import Path

OUT = Path(__file__).resolve().parent / "out"
tables = (OUT / "_tables.md").read_text(encoding="utf-8")
parts = {}
cur = None
for line in tables.split("\n"):
    if line.startswith("### "):
        cur = line[4:].strip()
        parts[cur] = []
    elif cur:
        parts[cur].append(line)


def T(key):
    for k, v in parts.items():
        if k.startswith(key):
            return "\n".join(v).strip("\n")
    raise KeyError(key)


HEAD = """# Phân tích log thực nghiệm LWB (`analysis\\logs`)

Nguồn: 18 file log HOST (picocom + `script`), tất cả `run 510`, `expected 100`, chu kỳ 5 s, kênh 26, drive 7 dBm, `gen_mode 1`, `gen_lead_ms 250`, `fresh_only 1`.
Script: `analysis\\analyze_runs.py` (đọc log, không sửa) → `make_report.py` (hình, bảng) → `build_summary.py` (file này).
Quy ước: **[Đo]** là số liệu đọc trực tiếp từ log (đã lọc checksum `*HH`); **[Suy luận]** là diễn giải của tôi, chưa được log chứng minh.

## 0. Điểm cần biết trước khi đọc số

1. **Không có dấu thời gian trong từng dòng.** Thời gian duy nhất là dòng `Script started/done` của `script`. Tôi dựng trục thời gian từ các khối `PERF_SUMMARY` (HOST in mỗi 30 s, mặc định `SUMMARY_PERIOD ?= 30` ở `Makefile`; PERF_CONFIG không ghi chu kỳ này). Kiểm tra: số khối × 30 s lệch độ dài phiên `script` tối đa 0,5 phút ở cả 12 phiên (ví dụ 21,5 so với 21,6 phút), nên đồng hồ này đáng tin ở độ phân giải ±30 s. Mọi thời điểm “phút” trong hình và bảng đều là xấp xỉ.
2. **Chỉ có log phía HOST.** Không có UART của các Source nên không có `PERF_GATE`, `PERF_SUPERSEDE`, `PERF_SOURCE_SUMMARY`, `Reset cause` của Source. Vì vậy không thể đối chiếu trực tiếp “mất đồng bộ / rejoin” như bạn yêu cầu; tôi suy ra từ quan hệ seq và thời gian (mục 3).
3. **Cả 18 phiên có cùng `run 510`**, mỗi file đúng một `PERF_CONFIG` và đúng một `Reset cause: External reset`, nên không có HOST khởi động lại giữa phiên. Hệ quả: phải phân biệt phiên theo tên file và giờ, không theo `run` (`analyze_logs.py` nạp nhiều file cùng `run` sẽ gộp lại).
4. **Thư mục `singlehop\\A6` chứa file đặt tên `KTX_F1..F4`.** Theo tác giả, đây là tòa A6 và Source cách HOST 1, 2, 3, 4 tầng. Khoảng cách tới HOST trong các phiên multi-hop (theo tác giả): A6 node 2/3/4/5 = 20/10/25/15 m; KTX = 30/10/45/20 m; CS2 node 3/5/4/2 = 20/50/70/80 m. Khoảng cách single-hop CS2 lấy từ tên file (10, 30, 50, 70, 80 m). Không có file `DIAG_4near*.log` trong `analysis\\logs`: phép đo 4 Source cùng ở gần chưa có. Các số này được ghép trong `analyze_runs.py` (không có trong log).
5. Mỗi điểm đo chỉ có **một phiên** (một lần chạy 100 gói). Cận Clopper–Pearson coi các gói độc lập; ở nhiều phiên mất gói theo cụm (mục 3) nên khoảng tin cậy thực tế rộng hơn các cận đã tính.
6. Các nguồn không tham gia (3, 4, 5 trong các phiên single-hop) có `received = 0` và không có `PERF_REPORT`; tôi loại khỏi `per_source.csv` và liệt kê trong `sessions.csv` (cột `inactive_sources`). Phiên `KTX_50m` không có Source nào nhận được gói, tôi giả định Source 2 như các phiên single-hop khác (đánh dấu `assumed_source`).

## 1. Các phiên đo

"""

AFTER_SESS = """
Nhận xét **[Đo]**: 18 phiên, không phiên nào có HOST khởi động lại, không dòng nào `unique = 0` hay trùng seq, không `queue_failed`, `deadline_missed`, `tx_start_failed` hay `drain_timeout` nào ở mọi `PERF_REPORT` (Source nào gửi được báo cáo cuối đều ghi `generated = queued = tx_started = 100`). Dòng bị loại vì sai checksum hoặc sai cấu trúc rất ít (tổng 14 dòng trong 18 file; tối đa 3 dòng ở một file), làm mất tối đa 3 dòng dữ liệu (HOST đếm nhiều hơn log 1 gói ở A6 node 4, KTX multi node 4 và KTX 45 m). Vì vậy mất gói trong log chủ yếu là mất ở tầng vô tuyến/đồng bộ, không phải lỗi UART.

Phiên `KTX_30m` dài 40,9 phút trong khi các phiên khác 10–25 phút, và `KTX_20m` ghi lúc 21:32 giữa hai điểm khác (30 m lúc 19:11, 40 m lúc 20:34). Thứ tự đo không theo khoảng cách nên khác biệt môi trường theo giờ là một yếu tố gây nhiễu chưa kiểm soát.

## 2. Kết quả theo từng Source

"""

AFTER_SRC = """
**[Đo]** Single-hop KTX: PRR 100 % (10 m), 97 % (20 m), 55 % (30 m), 38 % (40 m); ở 45 m chỉ nhận 10 gói và phiên chưa final; ở 50 m không nhận gói nào. Single-hop A6: 100, 97, 99 và 66 % (F1–F4). Multi-hop: A6 node 3 đạt 99 %, các node còn lại 45–54 %; KTX 62 % (node 3), 48 % (node 5), 44 và 51 % tạm (node 2, 4).
Độ trễ (enqueue → cuối slot HOST) ở single-hop gần như không đổi: p50 từ 316 đến 320 ms ở mọi điểm đo, kể cả điểm mất 62 % gói. Ở multi-hop độ trễ theo từng node: 301–302 ms (node 3), 381 / 452 ms (node 4, A6 / KTX), 468 / 397 ms (node 5), 520 ms (node 2); mỗi bước nhảy giữa hai node là 50–100 ms, cùng cỡ một slot 70 ms. **[Suy luận]** độ trễ do vị trí slot trong lịch của Source quyết định, không phụ thuộc khoảng cách hay số hop; log không đủ để kiểm tra thứ tự slot. Hai Source có gói đầu tiên trễ khoảng 4,8 s (A6 node 3 seq 1: 4883 ms; KTX node 2: 4821 ms), còn lại mọi gói ≤ 540 ms.

## 3. Phân tích mất gói

**Cách đọc các bảng gap** (firmware `lwb-cc2538dk-env.c:500-512`, `fresh_gate`): khi Source chưa đồng bộ hoặc chưa được xác nhận luồng, firmware **không tạo gói và không tiêu thụ seq**. Do đó có hai kiểu “thiếu” trong log HOST:
- thiếu **seq** nhưng thời gian vẫn đúng 5 s/seq: gói đã tạo và đã phát (`tx_started`) nhưng HOST không nhận; **[Suy luận]** mất trong flood hoặc ở thu của HOST, Source vẫn đồng bộ;
- thời gian trôi qua nhiều hơn 5 s × số seq: Source **không tạo gói** trong khoảng đó, **[Suy luận]** nó đang mất đồng bộ hoặc đang xin tham gia lại. Cột “Dừng sinh gói” đo phần thời gian này (sai số ±30 s).

Bảng “Nguồn gốc các gói mất” phân loại từng gap theo hai kiểu trên (dựa vào thời gian giữa hai gói nhận được ở hai đầu gap; ≥ 60 s là có dừng, < 30 s là không). Vì không có `PERF_GATE` ở log HOST, đây là suy luận và chưa được xác nhận bằng log Source.

"""

AFTER_GAPS = """
**Kết luận theo phiên (nhãn [Suy luận] nếu không ghi khác):**

| Phiên | Mô tả mất gói | Nguyên nhân khả dĩ |
|---|---|---|
| KTX 10 m, A6 F1 | **[Đo]** 0 gói mất | Liên kết tốt, không có dấu hiệu mất. |
| KTX 20 m, A6 F2, A6 F3 | **[Đo]** 1–3 gói, đều là gap một gói, không có dừng sinh gói | Mất rải rác thỉnh thoảng (1–3 %); nằm trong cận CP95 dưới 91,5–96,4 %, chưa đủ chứng cứ cho nguyên nhân cụ thể. |
| A6 F4 | **[Đo]** 66 %, 34 gói mất; 8 gói đầu mất trước khi HOST nhận lần đầu (seq 9); 20 gap so với 23 kỳ vọng nếu mất độc lập; dừng sinh gói ≈ 55 s (trong sai số) | Liên kết ở biên: mất rải rác khoảng một phần ba số gói, Source vẫn đồng bộ. Giống một liên kết yếu hơn là mất đồng bộ. |
| KTX 30 m | **[Đo]** 55 %, 45 gói mất, 21 gap (25 kỳ vọng nếu độc lập), 11/33 khối 30 s không nhận gói nào (dài nhất 4 khối), dừng sinh gói ≈ 465 s | Cả hai: mất rải rác khi đồng bộ và nhiều đợt Source không tạo gói (tổng ≈ 465 s trong khoảng nhận ≈ 16,5 phút). Hợp với liên kết hai chiều gần ngưỡng: Source nhiều lần mất đồng bộ rồi vào lại. |
| KTX 40 m | **[Đo]** 38 %, 62 gói mất theo cụm (13 gap so với 24 kỳ vọng; gap dài nhất 13), 25/42 khối im lặng (dài nhất 11 khối ≈ 5,5 phút), dừng sinh gói ≈ 735 s trên khoảng nhận ≈ 21 phút | Mất đồng bộ là cơ chế chính (Source phần lớn thời gian không tạo gói), cộng thêm mất khi đồng bộ. |
| KTX 45 m | **[Đo]** nhận 10 gói (seq 2–20) trong ≈ 4 phút đầu rồi không nhận gì thêm đến hết phiên 24,6 phút; không có `PERF_REPORT`; 3 dòng sai checksum | Phiên không hoàn tất. Sau giai đoạn đầu HOST không còn nghe Source; có thể Source mất đồng bộ không vào lại được. Cuối phiên (seq 21–100) không có thông tin thời gian nên không xác định được Source còn tạo gói hay không. |
| KTX 50 m | **[Đo]** không nhận gói nào trong 10,2 phút, mọi khối `PERF_SUMMARY` có `received = 0` | Source không vào được mạng hoặc HOST không nghe được Source ở khoảng cách này. Không có log Source để phân biệt hai khả năng. |
| A6 multi, node 3 | **[Đo]** 99 %, 1 gói mất, relay_cnt = 0 ở 98/99 gói | Liên kết trực tiếp tốt, tương tự single-hop ≤ 20 m. |
| A6 multi, node 2, 4, 5 | **[Đo]** 45–54 %, 13–16 gap so với 25 kỳ vọng nếu độc lập (mất theo cụm, gap dài 15–18); số gói nhận mỗi khối giữa node 2, 4, 5 tương quan mạnh (r = 0,78–0,87), trong khi node 3 không tương quan | **[Suy luận]** có nguyên nhân chung theo thời gian cho ba node này (nhiễu, thay đổi môi trường, hoặc một đường chuyển tiếp dùng chung), không phải lỗi riêng từng Source. Với node 2, dừng sinh gói ≈ 120 s; node 4 và 5 không đáng kể. |
| A6 multi, node 4 | **[Đo]** 15 gói đầu (seq 1–15) mất; firmware chỉ tạo gói khi đã được xác nhận luồng nên **[Suy luận]** Source đã được cấp luồng | **[Suy luận]** yêu cầu tham gia (slot tranh chấp) đã đến được HOST nhưng dữ liệu ở các slot sau không tới trong ≈ 75 s; chưa kiểm chứng được. |
| A6 multi, node 2 | **[Đo]** gói seq 5 (dòng 802, relay_cnt 2) đến HOST khoảng 1,7 phút **trước** seq 2 (dòng 847); HOST báo `out_of_order = 2` | **[Suy luận]** Source 2 có thể đã khởi động lại giữa phiên (seq đếm lại từ 1); khi đó PRR 50 % bao gồm một gói của lần chạy cũ. Cần log UART của Source để xác nhận. |
| KTX multi, node 2, 3, 4, 5 | **[Đo]** 44–62 %, mất gần như rải rác ở node 2, 3, 5 (23/24/21 gap, kỳ vọng 25/24/25) và theo cụm ở node 4 (17 gap, dài nhất 18); không có khối 30 s nào mà cả bốn Source cùng im lặng; tương quan giữa các cặp 0,22–0,74; dừng sinh gói ≈ 135 s ở node 3 và 5, ≈ 0 ở node 2 và 4 | **[Suy luận]** mất do liên kết chập chờn từng node là chính, ít nguyên nhân chung hơn so với A6; một phần thời gian node 3 và 5 mất đồng bộ. |

Hình: `seq_vs_time_multihop_a6.png`, `seq_vs_time_multihop_ktx.png`, `seq_vs_time_singlehop.png` (đoạn nằm ngang = Source không tạo gói; chấm đỏ = gói mất, thời gian nội suy giữa hai gói lân cận; chấm đỏ nhạt ở đầu/cuối là ngoại suy 5 s/seq nên không chắc).

**Đối chiếu với `PERF_GATE`, `PERF_SUPERSEDE`, rejoin, `PERF_CONFIG` xuất hiện lại, `Reset cause`:** log HOST không chứa `PERF_GATE`, `PERF_SUPERSEDE` hay các sự kiện rejoin; `PERF_CONFIG` và `Reset cause` mỗi file chỉ xuất hiện đúng một lần ở đầu phiên (HOST không khởi động lại). Đối chiếu trực tiếp chỉ làm được khi có log UART của các Source (tool `capture` ghi `node-<id>.log`).

## 4. So sánh single-hop và multi-hop

"""

AFTER_REL = """
**(a) Single-hop và multi-hop cùng khu vực.** **[Đo]** Ở KTX, so từng khoảng cách: 10 m: single-hop 100 % so với multi-hop 62 % (node 3); 20 m: 97 % so với 48 % (node 5); 30 m: 55 % so với 44 % tạm (node 2); 45 m: 10 gói rồi mất hẳn (single-hop, ngày 18/11 lúc 17:28) so với 51 gói tạm (node 4, ngày 18/11 lúc 18:50). Ở A6, node 3 (10 m) đạt 99 %, còn node 5 (15 m), node 2 (20 m), node 4 (25 m) đạt 54, 50, 45 % (tạm). **PRR multi-hop thấp hơn single-hop ở cùng khoảng cách (10 và 20 m)**, trong khi ở khoảng cách lớn nhất (45 m) multi-hop nhận được nhiều gói hơn single-hop. **[Suy luận]** chuyển tiếp qua node khác có thể mở rộng vùng phủ nhưng làm giảm độ tin cậy ở khoảng cách gần; chưa thể tách riêng ảnh hưởng này vì mỗi điểm chỉ có một phiên, thời điểm đo khác nhau, và ở multi-hop có bốn Source cùng phát (tương tác giữa các node không có trong phép đo single-hop). Độ trễ khác nhau giữa hai kiểu đo không nói lên hiệu quả multi-hop: single-hop chỉ có một Source trong lịch (≈ 317 ms) còn multi-hop có bốn Source (301–520 ms theo vị trí slot, **[Suy luận]**).

**(b) PRR theo relay_cnt.** PRR theo `relay_cnt` **không tính được**, vì gói mất không có `relay_cnt`. Thay thế: bảng “Gói mất kế tiếp theo relay_cnt” cho biết xác suất gói kế tiếp (seq + 1) bị mất sau một gói nhận được có `relay_cnt = 0` so với `> 0`. **[Đo]** kết quả không nhất quán: A6 node 2: 18,8 % (n = 32) so với 44,4 % (n = 18); KTX node 4: 23,5 % (n = 17) so với 40,6 % (n = 32); KTX node 5: 14,3 % (n = 7) so với 50,0 % (n = 40); nhưng KTX node 3: 39,6 % (n = 48) so với 38,5 % (n = 13) và A6 node 5: 40,0 % (n = 5) so với 20,4 % (n = 49). Cỡ mẫu nhỏ nên **không đủ để kết luận** `relay_cnt > 0` đi kèm đường truyền kém hơn. Thông tin khác từ `relay_cnt`:
- **[Đo]** tỷ trọng gói có `relay_cnt > 0` tăng khi liên kết xấu đi ở single-hop: 1 % (KTX 10 m), 5 % (20 m), 31 % (30 m), 21 % (40 m), 11 % (45 m); A6 F1–F4: 3, 3, 7, 23 %.
- **[Đo]** `relay_cnt > 0` cũng xuất hiện ở các phiên single-hop. `relay_cnt`/`hop_est` chỉ cho biết số lần chuyển tiếp của bản sao HOST nhận được, không chứng minh topology multi-hop (cùng cảnh báo trong ghi chú của `analyze_logs.py`).
- **[Đo]** Ở multi-hop, node 2, 4, 5 có tỷ trọng `relay_cnt > 0` từ 36 đến 100 %, `relay_cnt` lên tới 7–8; node 3 phần lớn bằng 0 (99 % ở A6, 79 % ở KTX).

## 4b. Cơ Sở 2 (CS2), ngày 21/11

Sáu phiên mới, đo bằng firmware hiện hành (run 510, `gen_mode 1`, 7 dBm, kênh 26): single-hop 10, 30, 50, 70, 80 m và một phiên multi-hop (Host và bốn Source cách 20, 50, 70, 80 m: node 3, 5, 4, 2). Mọi phiên hoàn tất (`final=1`).

**[Đo] Single-hop CS2.** PRR 100 % (10 m, CP95 dưới 96,4 %), 97 % (30 m; 91,5 %), 90 % (50 m; 82,4 %), 83,8 % (70 m; 75,1 %), 83 % (80 m; 74,2 %). Ở 70 m `PERF_REPORT` ghi `tx_started = 99` (một gói tạo ra nhưng chưa bắt đầu phát) nên PRR = 83/99. Độ trễ p50 317 ms và p95 320–321 ms ở mọi điểm; max không quá 328 ms. Mất gói: 30 m có 3 gap (ngắn, đơn lẻ), 50 m có 10 gap (kỳ vọng 9 nếu độc lập), 70 m có 14 gap (kỳ vọng 12), cả hai đều rải rác; 80 m có 11 gap (kỳ vọng 14), dài nhất 4, và đáng chú ý là dừng sinh gói ≈ 860 s, 24/46 khối 30 s không nhận gói nào (dài nhất 8 khối). `relay_cnt` chỉ nhận giá trị 0 và 2 ở mọi điểm.

**[Đo] Multi-hop CS2.** PRR 100 % (node 3, 20 m; node 5, 50 m; node 2, 80 m) và 99 % (node 4, 70 m), CP95 dưới 96,4 % (94,5 % với node 4); không có dừng sinh gói đáng kể, không khối 30 s nào mà cả bốn Source cùng im lặng, 1 gap duy nhất (node 4). Độ trễ p50 302, 398, 452 và 520 ms (node 3, 5, 4, 2). `relay_cnt` lẻ xuất hiện ở node 2 (13/100 gói, đều bằng 1) và node 4 (16/99 gói, 15 gói bằng 1 và một gói bằng 5); node 3 và 5 chỉ có giá trị 0 và 2. Tương quan giữa các node không có ý nghĩa (r từ −0,11 đến −0,07) vì hầu như không có mất gói để so.

**[Đo] So với single-hop cùng khoảng cách.** Tại 80 m: multi-hop 100 % so với single-hop 83 % (hai phiên cách nhau khoảng 1,5 giờ, cùng ngày 21/11); tại 70 m: 99 % so với 83,8 %; tại 50 m: 100 % so với 90 %; tại 20 m: 100 % (không có điểm single-hop 20 m; 10 m và 30 m là 100 % và 97 %). Ở multi-hop, 84/100 gói của node 2 (80 m) vẫn có `relay_cnt = 0` (nhận trực tiếp bản phát đầu của Source), còn 13 gói có `relay_cnt = 1` (qua một node thứ ba).

**[Suy luận]** Kết quả CS2 không ủng hộ giả thuyết rằng nhiều node phát đồng thời trên CC2538 tự nó làm giảm độ tin cậy: bốn Source cùng hoạt động nhưng PRR 99–100 %, và node xa nhận tốt hơn so với single-hop cùng khoảng cách. Hai điểm khác biệt giữa CS2 và A6/KTX là môi trường (sân ngoài trời rộng, ít vật cản so với A6 và KTX có cây và công trình) và điều kiện của từng phiên; log không cho phép tách riêng. Việc node 2 và 4 có gói đến qua chuyển tiếp cùng PRR cao hơn single-hop là dấu hiệu phù hợp với việc chuyển tiếp giúp ở liên kết xa, nhưng chỉ có một phiên mỗi loại nên chưa đủ để khẳng định.

## 5. Tóm tắt nguyên nhân mất gói

1. **[Đo]** PRR single-hop giảm nhanh từ 97 % (20 m) xuống 55 % (30 m) và 38 % (40 m), rồi gần như 0 (45–50 m), trong cùng cấu hình (7 dBm, N = 3, kênh 26).
2. **[Suy luận]** Ở 30–45 m mất gói gồm hai phần: mất rải rác khi vẫn đồng bộ, và các đợt Source không tạo gói do mất đồng bộ hoặc chưa được xác nhận luồng. Phần thứ hai chiếm phần lớn thời gian ở 40 m (≈ 735 s) và 30 m (≈ 465 s), nên lỗi không chỉ nằm ở đường lên của gói dữ liệu mà ở cả khả năng giữ liên lạc hai chiều với HOST.
3. **[Đo, suy luận]** Ở multi-hop, hầu hết gói mất là gói đã được tạo và phát (thời gian khớp 5 s/seq), tức mất trong flood hoặc ở thu của HOST. A6 có dấu hiệu nguyên nhân chung cho node 2, 4, 5; KTX nhiều node mất độc lập hơn.
4. **[Đo]** Mất ở tầng UART (dòng sai checksum) không đáng kể (≤ 3 dòng/phiên). Không có bằng chứng của quá tải hàng đợi hay deadline ở phía Source (mọi `PERF_REPORT`: `queue_failed = deadline_missed = tx_start_failed = 0`).

## 6. Hạn chế và việc nên làm thêm

- Bổ sung giờ thực tế HOST khởi động (hiện chỉ có giờ bắt đầu và kết thúc của phiên `script`).
- Ghi thêm log UART từ các Source (tool capture) để kiểm chứng suy luận về mất đồng bộ bằng `PERF_GATE`/`PERF_SUPERSEDE`.
- Mỗi điểm chỉ một phiên, ghi không theo thứ tự khoảng cách; 45 m và 50 m không hoàn tất. Nếu đưa vào luận văn nên ghi rõ đây là kết quả từ một lần đo mỗi điểm và PRR ở 45–50 m là “không hoàn tất”.
- Khoảng tin cậy CP95 giả định các gói độc lập, không đúng với phiên mất theo cụm; số liệu `KTX 30 m/40 m` và `A6 multi` nên đọc kèm hình seq theo thời gian.

## 7. File sinh ra (`analysis\\out`)

| File | Nội dung |
|---|---|
| `sessions.csv` | 18 phiên: khu, loại, điểm đo, cấu hình, giờ VN/UTC, số HOST restart, số dòng sai checksum, Source tham gia |
| `per_source.csv` | Mỗi Source: nhận, PRR, CP95, REPORT, độ trễ, relay/hop, gap, dừng sinh gói |
| `gaps.csv` | Từng gap theo seq: độ dài, vị trí, thời gian ước lượng, nguyên nhân suy luận |
| `stalls.csv` | Các cặp gói liên tiếp có khoảng thời gian dư ≥ 30 s (Source không tạo gói) |
| `relay_next_loss.csv` | Gói mất kế tiếp theo `relay_cnt` |
| `prr_vs_distance.png`, `delay_vs_distance.png` | PRR và độ trễ theo điểm đo |
| `seq_vs_time_multihop_a6.png`, `seq_vs_time_multihop_ktx.png`, `seq_vs_time_singlehop.png` | Seq nhận được theo thời gian |
"""

doc = (HEAD + T("Bảng phiên đo") + "\n" + AFTER_SESS + T("Bảng theo Source") + "\n" + AFTER_SRC +
       "### 3.1 Phân bố gap\n\n" + T("Phân bố khoảng trống") + "\n\n### 3.2 Nguồn gốc các gói mất\n\n" +
       T("Nguồn gốc") + "\n\n### 3.3 Tương quan giữa các Source (multi-hop)\n\n" + T("Tương quan") + "\n" +
       AFTER_GAPS + "### 4.1 Gói mất kế tiếp theo relay_cnt\n\n" + T("Gói mất kế tiếp") + "\n\n" + AFTER_REL)
(OUT / "SUMMARY.md").write_text(doc, encoding="utf-8")
print("SUMMARY.md", len(doc), "chars")
