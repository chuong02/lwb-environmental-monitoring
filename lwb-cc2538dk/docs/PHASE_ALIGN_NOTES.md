# PHASE_ALIGN_NOTES — đồng bộ pha tạo gói với vòng LWB

Phạm vi: `apps/lwb-cc2538dk-env` (SOURCE/HOST). Ghi chú này gồm **Bước 0** (đọc code, viết
trước khi sửa) và **Tóm tắt cuối** (cuối file). Mọi số dòng dưới đây là của commit
`6005c3e` ("Moc truoc P2") trước khi sửa.

Quy ước: "chưa xác nhận" = suy ra từ code, chưa đo trên kit.

## Bước 0 — Kết quả đọc code

### 0.1 Source tạo gói ở đâu, enqueue thế nào, hàng đợi chứa bao nhiêu

- Tạo gói: `source_generate()` (`lwb-cc2538dk-env.c:300`). Được gọi từ 2 chỗ:
  1. lúc chuyển `STATE_JOIN → STATE_SEND` (dòng 440): `next_release = clock_time(); source_generate();`
  2. khi `send_et` hết hạn (dòng 408-409). `send_et` được đặt lại ở cuối `source_generate()`
     (dòng 334) với khoảng `next_release - now`, `next_release += (missed+1) * UP_IPI * CLOCK_SECOND`.
- Đây là **etimer IPI thuần theo `clock_time()`**, không có liên hệ pha nào với vòng LWB.
  Pha của gói so với vòng được quyết định bởi lúc `STATE_SEND` bắt đầu (một tick bảo trì 1 s),
  rồi trôi tự do theo chênh lệch xung nhịp. Đó là nguyên nhân gói có thể đứng chờ trong
  hàng đợi tới ~1 vòng (5 s) trước khi tới slot.
- Enqueue: `lwb_queue_packet()` → `lwb_g_rr_queue_packet()` (`net/lwb/lwb-g-rr.c:643`):
  `memb_alloc(&mmb_data_buf)` rồi `list_add(lst_tx_buf_queue)`; `tx_buf_q_size++`. FIFO.
  Hết pool thì trả `LWB_STATUS_FAIL` (app đếm `queue_failed`).
- Sức chứa: `mmb_data_buf` có `LWB_MAX_DATA_BUF_ELEMENTS` phần tử = `DATA_BUFFERS` (Makefile mặc
  định 16; `lwb-default-conf.h` mặc định 5 nếu không override). **Pool này dùng chung TX và RX.**
  SOURCE hầu như không nhận gói gửi cho nó nên thực tế ~16 gói chờ. `tx_buf_q_size` là `uint8_t`.
- Mỗi slot của node chỉ lấy **1 gói** đầu hàng đợi (`prepare_data_packet()`, `lwb-g-rr.c:156`,
  gọi ở dòng 541-542). Stream IPI=5 s trên vòng 5 s cho đúng 1 slot/vòng, nên hàng đợi chỉ
  rút được 1 gói/vòng: gói nào tới trễ hơn slot sẽ ngồi chờ tới vòng sau, và nếu tạo nhanh hơn
  rút thì hàng đợi dồn dần (đây là hiện tượng Bước 2 muốn chặn).
- Việc truy cập hàng đợi từ process (enqueue / `lwb_drop_tx_queue`) **không có khóa** với rtimer
  ISR (ISR lấy gói ở `prepare_data_packet`). An toàn chỉ khi ngoài vòng:
  `lwb_drop_tx_queue()` tự kiểm tra `lwb_background_allowed(30)`; `lwb_queue_packet()` thì không kiểm tra.

### 0.2 Biến/hàm cho biết đã synced và đã có stream ack

| Điều kiện | Hàm / biến | Nơi đặt |
|---|---|---|
| Đã đồng bộ, thời gian mạng hợp lệ | `lwb_time_is_fresh()` = `network_time_valid && (HOST \|\| sync_state==SYNCED)` | `lwb.c:257` |
| Đã có ≥2 vòng fresh liên tiếp | `fresh_rounds` (app), tăng trong `on_sched_end` | `lwb-cc2538dk-env.c:291-297` |
| Đã nhận stream ack | `lwb_get_joining_state() == LWB_JOINING_STATE_JOINED` | đặt ở `process_stream_acks()` `lwb-g-rr.c:348-351` khi danh sách stream request rỗng |
| Có slot được cấp | `lwb_get_n_my_slots() > 0` (đếm từ lịch giải mã gần nhất) | `lwb-g-sync.c:205` |

Điều kiện bắt đầu hiện tại (`lwb-cc2538dk-env.c:436-437`): `now_s >= UP_START_DELAY && fresh_rounds >= 2 &&
JOINED && n_my_slots`. Sau khi bắt đầu, `source_generate()` **không** kiểm tra lại các điều kiện này;
gói tạo lúc mất sync chỉ được đánh dấu `unsynced_generated++` và cờ `UP_TIME_VALID` không bật.
Lưu ý: `lwb_request_stream_mod()` (REJOIN_REQUEST) đưa `joining_state` về `PARTLY_JOINED`
cho tới khi nhận ack mới.

### 0.3 Thời điểm bắt đầu vòng theo đồng hồ cục bộ; chu kỳ vòng

- SOURCE (`net/lwb/lwb-g-sync.c`, `lwb_g_sync_source`): `t_start = RTIMER_TIME(rt)` (dòng 367, sớm hơn
  mốc thật một `t_sync_guard`); sau flood sync `t_sync_ref = GLOSSY_T_REF` (đồng hồ cục bộ, quy về
  mốc của initiator); cuối vòng (dòng 448-452):
  `next_round_ticks = t_sync_ref + round_period*RTIMER_SECOND + round_period*skew - t_sync_guard`
  rồi `round_active = 0` và chờ tới `next_round_ticks`.
- HOST: `t_start = RTIMER_TIME(rt)`, `next_round_ticks = t_start + round_period*RTIMER_SECOND`
  (dòng 190-193).
- Các biến này nằm trong `lwb_context` (định nghĩa `lwb.c:51`, **không** có khai báo `extern` trong header
  công khai). Ứng dụng hiện chỉ gián tiếp dùng chúng qua `lwb_background_allowed()`.
  **Không có API công khai nào trả mốc bắt đầu vòng** → xem 0.7 (phải thêm 1 getter).
- Chu kỳ vòng: `round_period` (giây) nằm trong header lịch (`lwb_sched_info_t.round_period`),
  do `lwb_sched_compute_schedule()` đặt = `period`
  (`lwb-scheduler-static.c`: `LWB_SCHED_PERIOD_START = LWB_SCHED_PERIOD_STEADY = 5`).
  App chỉ biết gián tiếp qua giả định "scheduler tĩnh 5 s" trong `unified-conf.h`.
- Thời gian mạng: `lwb_get_network_time_ticks()` = `RTIMER_NOW() + network_time_offset_ticks`,
  với mốc `sched.time * RTIMER_SECOND` tại `t_sync_ref`; wrap modulo 2^32 (~36 giờ ở 32768 Hz)
  nên **không** dùng "mod 5 s" của thời gian mạng để suy ra pha (sai lệch cố định sau lần wrap đầu).
- Cấu trúc vòng (mặc định `lwb-default-conf.h`, RTIMER_SECOND=32768): sync `T_SYNC_ON`=30 ms;
  khoảng `T_S_R_GAP`=40 ms; mỗi slot `T_RR_ON`+`T_GAP` = 30+40 = 70 ms. Với 1 slot dữ liệu + 1 slot
  tranh chấp, vòng dài ≈ 0,21 s (thêm 70 ms nếu có slot ack, thêm 70 ms mỗi source khác).
  Khoảng rảnh ≈ 4,7 s trong chu kỳ 5 s. Slot đầu tiên của node bắt đầu ≈ 70 ms sau mốc vòng.

### 0.4 Process ứng dụng chạy lúc nào so với vòng LWB

- `lwb_cc2538dk_env_process` là process Contiki thường; nó chạy khi có: `maintenance_et` (1 s),
  `send_et`, `process_poll` từ `observe_tx()` (rtimer ISR, ngay sau slot TX của node).
- Vòng LWB chạy hoàn toàn trong rtimer ISR (mỗi `LWB_WAIT_UNTIL` đặt 1 rtimer rồi thoát).
  Giữa các lần rtimer, vòng lặp chính Contiki **vẫn chạy được**: app có thể chạy giữa các slot,
  không có loại trừ lẫn nhau. Vì vậy mọi tác vụ chặn (I2C, OLED) đều đứng sau
  `lwb_background_allowed(budget_ms)` (`lwb.c:264`: `round_active==0` và còn > budget tới `next_round_ticks`).
- `on_data` / `on_sched_end` KHÔNG chạy trong rtimer ISR: ISR chỉ `process_poll(&lwb_main_process)`,
  rồi `lwb_main_process` gọi callback trong `PROCESS_CONTEXT_BEGIN(init_process)` (`lwb.c:129-151`).
  `on_sched_end` được poll **cuối vòng** (SOURCE: sau slot cuối; `lwb-g-sync.c:440-441`).
  Vì ISR chạy xong (gồm cập nhật `next_round_ticks` và `round_active = 0`, dòng 448-453) trước khi
  vòng lặp chính chạy poll, nên khi `on_sched_end` chạy thì `next_round_ticks` đã là mốc vòng KẾ TIẾP.
  Đây là điểm neo tự nhiên để hẹn thời điểm tạo gói. (suy ra từ code; chưa xác nhận bằng đo).
- Trong `on_sched_end` không nên đọc I2C (đang trong ngữ cảnh `lwb_main_process`); chỉ đặt cờ + `process_poll` app.

### 0.5 Đọc cảm biến I2C mất bao lâu, chạy ở process nào

Tất cả chạy trong `lwb_cc2538dk_env_process`, từ `sample_sensor()` (nhánh bảo trì,
dòng 412-414, điều kiện `now_s - last_sample_s >= UP_SAMPLE_PERIOD && lwb_background_allowed(700)`).
I2C là bit-bang (`i2c_sw.c`, `clock_delay_usec(5)` mỗi pha), chặn bằng vòng chờ bận; ISR vẫn ngắt được.
Ước lượng **từ code driver** (chưa đo):

| Thiết bị | Thành phần thời gian | Ước lượng |
|---|---|---|
| HDC1080 (`hdc1080_read_x10`) | trỏ thanh ghi + `clock_delay_usec(20000)` + đọc 4 byte | ≈ 21–22 ms; tối đa ≈ 3 lần thử ≈ 70 ms |
| Si7021 | tương tự (không dùng ở cấu hình mặc định auto→HDC1080 trước) | chưa đọc kỹ |
| TSL2561 (`tsl2561_read_ch0_raw`) | 2 lần đọc thanh ghi, không chờ tích phân (đọc kết quả chu kỳ trước) | ≈ 1–2 ms |
| BMP180 (`bmp180_read_x10_pa`, OSS=0) | `5000 µs` + `8000 µs` + 2 lần đọc | ≈ 14–15 ms |
| OLED `env_oled_show_env()` (cuối `sample_sensor`) | 64 khối × 18 byte qua SW-I2C | ≈ 150–250 ms (suy ra từ số byte × 26 pha × 5 µs; chưa đo) |

Tổng danh nghĩa ≈ 40 ms cảm biến (+ ~0,2 s nếu OLED bật); xấu nhất có retry/recover ≈ vài trăm ms.
Ngân sách bảo vệ hiện tại `BG_BUDGET_MS = 700` bao trùm các trường hợp này. Khi `OLED=0` còn ≈ 40–150 ms.
Quan trọng: **đọc I2C ngay trước giờ tạo gói có thể làm trễ xử lý etimer của chính app**
(cùng 1 process), nên bản P2 đẩy việc đọc sang ngay sau vòng. *(Đã thay bởi P2b: I2C được đọc ngay trước lúc
enqueue, chỉ OLED còn nằm sau vòng; xem mục "P2b" ở cuối file.)*

### 0.6 Độ rộng seq; PACKETS và REPORT hiện xử lý ra sao

- `seq` trong gói `up_packet_t` rộng **16 bit** (`uint16_t source, seq`). `UP_PACKETS ≤ 2000` nên không
  bao giờ wrap ở chế độ hữu hạn. `env_packet_t.seq` (32 bit) chỉ là cấu trúc cục bộ cho OLED.
  Các bộ đếm trong REPORT (`generated, queued, tx_started, queue_failed, deadline_missed, tx_start_failed`)
  cũng là `uint16_t`. Không đổi được vì không được đổi format 28 byte.
- SOURCE: sau gói thứ `UP_PACKETS` → `STATE_DRAIN`; chờ ≥ `UP_REPORT_WAIT` (15 s) và hàng đợi rỗng
  (hoặc `UP_DRAIN_TIMEOUT` 60 s thì `lwb_drop_tx_queue()` → `discarded`) → `source_close()`:
  in `PERF_SOURCE_SUMMARY`, dựng `final_report` (seq = generated), vào `STATE_CLOSED`, rồi enqueue
  REPORT tối đa `UP_REPORT_REPEAT` (3) lần cách nhau `UP_IPI` s, tối đa `UP_REPORT_REPEAT*4+4` lần thử.
- SOURCE `observe_tx()` (rtimer ISR): ghi sự kiện `PERF_TX` vào vòng 16 phần tử, khử trùng bằng bitmap
  `tx_seen[UP_BITMAP_BYTES]`, chỉ nhận `UP_DATA` với `seq ≤ UP_PACKETS`.
- HOST `on_data()`: DATA → `up_stats_rx()` (bitmap `seen[UP_BITMAP_BYTES]` mỗi source), in `SENSOR_DATA`;
  REPORT → kiểm tra bất biến (`generated == UP_PACKETS`, `seq == UP_PACKETS`,
  `queued+queue_failed+deadline_missed == generated`, `tx_started+tx_start_failed <= queued`,
  `tx_started >= unique`), lưu, in `PERF_REPORT` + `PERF_SUMMARY`. `PERF_SUMMARY` còn in định kỳ mỗi
  `UP_SUMMARY_PERIOD` (30 s) cho mọi source dự kiến; yield = `unique/generated` (`up_ratio`, 16 bit).
- `unified-conf.h` hiện **cấm `PACKETS=0`** (`#error`), `build_node.py` cũng (`1..2000`); `UP_BITMAP_BYTES`
  suy ra từ `UP_PACKETS`.
- `tools/analyze_logs.py` bắt buộc `1 ≤ expected ≤ 2000` (nếu không → `expected_count_unavailable`)
  và kiểm tra `t + tf + discarded == q` ở `PERF_SOURCE_SUMMARY`.

### 0.7 Hệ quả thiết kế (quyết định từ phần đọc code)

1. **Cần 1 getter nhỏ ở `net/lwb`** (bắt buộc, xem Tóm tắt cuối mục "Thay đổi trong net/lwb"). Lý do: mốc bắt đầu vòng theo đồng hồ cục bộ chỉ có trong
   `lwb_context`, không có API công khai; suy từ `lwb_get_network_time_ticks()` thì sai sau khi wrap 2^32.
   Getter nằm sau cờ `LWB_ROUND_TIMING_CONF` (mặc định 0 → `net/lwb` biên dịch y hệt hiện tại).
2. App đã copy gói từ bộ đệm `latest` (không đọc I2C lúc đóng gói); cái cần đổi là *lúc đọc* I2C
   (P2b: đọc ngay trước khi đóng gói, xem cuối file).
3. Giữa `STATE_SEND` và slot, gói chỉ được tạo/xoá ở "cửa sổ an toàn" (`lwb_background_allowed(30)`)
   vì hàng đợi LWB không có khóa với ISR.

## Tóm tắt cuối (sau khi sửa)

### Đã làm theo từng bước

- **GEN_MODE=1** (`lwb-cc2538dk-env.c`: `gen_plan/gen_fire/gen_round_end/gen_service`): sau mỗi vòng
  (`on_sched_end` chỉ đặt cờ `round_end_flag` + `process_poll`), process app lấy mốc vòng kế tiếp bằng
  `lwb_get_next_round_ticks()`, hẹn `gen_et` tới `mốc - GEN_LEAD_MS` (đổi tick rtimer → tick clock, làm tròn lên),
  hết giờ thì `gen_emit()` → `source_emit_data()` copy từ bộ đệm `latest` (không I2C) và enqueue; `tx_network_ticks`
  lấy lúc enqueue như cũ. *(P2: cảm biến I2C + OLED đọc 1 lần/vòng ngay sau vòng. P2b: I2C đọc ngay trước enqueue,
  chỉ OLED còn nằm sau vòng; xem cuối file.)* Chưa biết mốc vòng (vừa join giữa vòng) → tạo ngay nếu đang trong cửa sổ an toàn,
  nếu không thì dời tới cuối vòng. Timer trễ qua mốc vòng → vẫn đúng **1** gói, dời tới cuối vòng (đi ở vòng sau);
  luôn chỉ có tối đa 1 timer đang chờ (`gen_armed`), không thể có 2 gói cho cùng 1 vòng.
  `IPI > 5`: `gen_wait_rounds` bỏ qua `IPI/5 - 1` lần cuối vòng và tự khóa lại pha theo vòng mà node có slot.
- **FRESH_ONLY** (mặc định bằng `GEN_MODE`): `fresh_gate()` (synced `lwb_time_is_fresh()` và `JOINED`) → không tạo gói, không
  tăng seq, in `PERF_GATE`; `fresh_drop_stale()` dùng `lwb_get_tx_queue_len()` + `lwb_drop_tx_queue()` bỏ gói cũ rồi mới
  enqueue gói mới, đếm `superseded`, in `PERF_SUPERSEDE` và thêm `superseded,N,gate_skipped,M` vào `PERF_SOURCE_SUMMARY`.
  Hoạt động ở cả `GEN_MODE=0`.
- **PACKETS=0**: SOURCE phát vô hạn; mỗi `REPORT_EVERY` gói DATA, lượt phát kế tiếp là REPORT cộng dồn
  (`source_emit_report`, in `PERF_REPORT_TX`). `seq` trên dây vẫn 16 bit, chu kỳ 1..65535 (`up_seq_wire`);
  bộ đếm REPORT 16 bit được HOST mở rộng bằng `up_ext16` (delta modulo 2^16); HOST dùng `up_cstats_rx`
  (bộ đếm 32 bit, cửa sổ trượt 32 gói thay cho bitmap). `PERF_CONFIG` in `expected,0`; `PERF_SUMMARY` vẫn định kỳ,
  yield tính từ REPORT đầu tiên tới REPORT mới nhất với số nhận được chụp tại lúc REPORT mới nhất tới.
- **Cờ build**: `GEN_MODE`, `GEN_LEAD_MS`, `FRESH_ONLY`, `REPORT_EVERY` trong `Makefile` (`?=`) và `EXTRA` của
  `tools/build_node.py`; `build_node.py` nhận `--packets 0`. `README_VI.md` có mục "Cập nhật 15/11/2026" với lệnh build
  5 kit (a) RUN_ID=510/PACKETS=100/GEN_MODE=1 và (b) RUN_ID=900/PACKETS=0/GEN_MODE=1.
- Không đổi: format `up_packet_t` 28 byte, scheduler tĩnh/vòng 5 s, không cấp phát động, xuống dòng LF.

### Thay đổi trong `net/lwb` (bắt buộc) và lý do

Chỉ một getter read-only, **sau cờ `LWB_ROUND_TIMING_CONF`** (mặc định 0 → `lwb.c`/`lwb.h` biên dịch y như cũ; Makefile của app
đặt = `GEN_MODE`):

- `net/lwb/lwb.h`: định nghĩa cờ + khai báo `uint8_t lwb_get_next_round_ticks(uint32_t *out)`.
- `net/lwb/lwb.c`: trả `lwb_context.next_round_ticks` khi `!round_active`, `run_state==ACTIVE` và (SOURCE) không ở `BOOTSTRAP`.

Lý do: mốc bắt đầu vòng theo đồng hồ cục bộ chỉ nằm trong `lwb_context` (không có API/`extern` công khai); suy ra từ
`lwb_get_network_time_ticks()` bằng phép "mod 5 s" sai vĩnh viễn sau khi tick mạng wrap 2^32 (~36 giờ), mà chế độ
liên tục chạy lâu hơn thế. Không sửa `net/glossy`, `lwb-g-*.c`, scheduler.

### Delay kỳ vọng (suy ra từ cấu trúc vòng + mô phỏng; **chưa đo trên kit**) — số liệu của P2; P2b đổi, xem cuối file

`delay = rx_slot_end(HOST) - tx_network_ticks(enqueue)`. Với IPI=5, 1 source, `GEN_LEAD_MS=100`:
`≈ 100 ms (lead) + 1 ms (guard) + 30 (sync) + 40 (gap) + 30 (slot) + 1 = 202 ms` (mô phỏng: 194–202 ms; 194 là gói đầu do
làm tròn tick của etimer, ±8 ms). Mỗi slot đứng trước slot của node cộng thêm ~70 ms (slot ack cũng 70 ms); với 4 source
khoảng 0,20 / 0,27 / 0,34 / 0,41 s tuỳ chỉ số slot. Sai số đồng bộ Glossy cộng vào (chưa đo). So với bản cũ: delay phụ
thuộc pha tuỳ ý, trong mô phỏng cùng cấu hình đo được ~4,3 s. Ngoại lệ có chủ ý ≈ 5,0–5,2 s: gói dời tới cuối vòng (timer
trễ/vừa join giữa vòng) và gói đầu tiên khi `IPI > 5`. Nên báo p50/p95, không chỉ mean/max.

### Rủi ro timing

1. Mọi thứ phụ thuộc giả định "khi `on_sched_end` chạy thì `next_round_ticks` đã là vòng kế tiếp" (đọc từ code, 0.4). Nếu sai,
   `remain` âm → app phát ngay cuối vòng → delay ≈ 5 s ở **mọi** gói. Dấu hiệu: `tx_net_ticks` của `PERF_GEN` cách
   `tx_start_ticks` của `PERF_TX` ~4,8 s thay vì ~0,3 s.
2. Etimer có độ phân giải 1/CLOCK_SECOND (~7,8 ms nếu 128 Hz) và có thể sớm tới 1 tick; cửa sổ an toàn cần ≥ 30 ms nên
   `GEN_LEAD_MS` bị chặn tối thiểu 50. Nếu main loop bận (I2C/OLED chạy lố) timer trễ → dời 1 vòng (+5 s).
3. Enqueue/drop hàng đợi chỉ làm trong `lwb_background_allowed(30)` ở GEN_MODE=1 (an toàn với ISR). Ở `GEN_MODE=0` giữ nguyên hành vi cũ
   (enqueue có thể rơi giữa vòng, không khóa). `FRESH_ONLY=1` với `GEN_MODE=0` có thể không bỏ được gói cũ nếu tick rơi giữa vòng.
4. *(P2; đã sửa ở P2b)* Tuổi dữ liệu cảm biến lúc gửi ≈ 4,7 s (đọc ngay sau vòng) thay vì ≤ 1 s. P2b đưa việc đọc I2C về ngay trước
   enqueue (tuổi ≈ 40 ms). Vẫn đúng: OLED của SOURCE làm mới ~5 s; `SAMPLE_PERIOD` bị bỏ qua ở SOURCE khi `GEN_MODE=1`. Thời gian I2C/OLED
   chỉ là ước lượng từ code (0.5).
5. Dòng `PERF_SUMMARY` chế độ liên tục dài tới ~550 ký tự (> `UART_LINE_BUF_LEN`=512 của `uart-checksum.c`, vượt thì dòng bị cắt và checksum
   hỏng); Makefile đặt 768 khi `PACKETS=0` (+256 B RAM). Chưa kiểm tra tổng RAM/flash khi link.
6. Một lượt REPORT thay chỗ một gói DATA nên tải DATA thực ≈ `REPORT_EVERY/(REPORT_EVERY+1)` tải danh nghĩa.

### Chỗ chưa chắc chắn

- Chưa build bằng GCC 4.9.3/Python 3.5, chưa nạp kit; chưa đo delay, RAM, flash, độ ổn định lâu dài.
- `CLOCK_SECOND` không nằm trong repo (giả định 128 của Contiki cc2538); mã chỉ dùng macro nên không phụ thuộc giá trị,
  nhưng số liệu "±8 ms" thì có.
- Thứ tự slot giữa các source (scheduler tĩnh) quyết định phần cộng thêm của delay; chưa kiểm chứng với 4 source.
- `IPI > 5` với `GEN_MODE=1`: khóa pha theo `lwb_get_n_my_slots()` ở cuối vòng chỉ được mô phỏng với mô hình slot "mỗi 2 vòng",
  chưa so với scheduler thật. Gói đầu có thể đợi thêm tới IPI giây.
- `FRESH_ONLY` coi "đã có stream ack" = `LWB_JOINING_STATE_JOINED`. Sau `REJOIN_REQUEST` trạng thái về `PARTLY_JOINED` nên bị gate cho tới khi nhận ack mới.
- Chế độ liên tục: `tools/analyze_logs.py` không phân tích log `expected,0` (trả `expected_count_unavailable`), seq 16 bit quay vòng
  làm `SENSOR_DATA` có seq lặp sau ~91 giờ; dashboard ngoài repo (nếu parse `PERF_SUMMARY`) cần chịu thêm trường `mode,continuous,reports`.
- Cảnh báo `git`: `core.autocrlf=true` trong máy này; mọi file vẫn LF, nhưng nếu `git checkout/stash` rồi copy sang VM, kiểm tra lại Makefile không bị CRLF.

### Đã kiểm tra những gì (và không phải build firmware)

- `gcc 13.2 -fsyntax-only -Wall -Wextra` trên `lwb-cc2538dk-env.c` (stub Contiki trong thư mục tạm) cho 8 tổ hợp cờ, gồm
  cả các `#error` mong đợi (`PACKETS=2001`, `GEN_LEAD_MS=20`, `GEN_MODE=1` thiếu getter); `lwb.c` với `LWB_ROUND_TIMING_CONF=0/1`.
- Mô phỏng host (stub LWB/timer, chạy đúng file ứng dụng): với cờ mặc định log source+host **giống từng byte** commit `6005c3e` trên 6 kịch bản
  (bình thường, mất sync, mất ack, mất slot, timer trễ, IPI=10); GEN_MODE=1: lead 92–100 ms, delay 194–202 ms, mất sync → `gate_skipped`, mất slot
  → `superseded` khớp `queued = tx_started + superseded`, timer trễ → vẫn 1 gói; liên tục: REPORT đúng nhịp, quay vòng seq 65535→1, mở rộng bộ đếm
  16 bit, yield 100%.
- `python -m unittest discover -s tests` → 12 test OK (thêm `test_superseded_queue_entries_are_accounted`); `tools/analyze_logs.py` chạy đúng với log
  cũ và log FRESH_ONLY. Các assert mới trong `tests/test_native.c` (`test_continuous`) đã chạy tách riêng bằng gcc host; **toàn bộ** `tools/check.py` chưa chạy
  (cần cây Contiki).

### Danh sách file đã sửa

```text
README_VI.md                                  mục "Cập nhật 15/11/2026" + bảng tham số
apps/lwb-cc2538dk-env/lwb-cc2538dk-env.c      GEN_MODE, FRESH_ONLY, chế độ liên tục (SOURCE + HOST)
apps/lwb-cc2538dk-env/unified-conf.h          cờ mới, kiểm tra hợp lệ, PACKETS=0, UP_BITMAP_BYTES
apps/lwb-cc2538dk-env/env-perf-stats.h        up_seq_wire/diff, up_cstats_rx, up_ext16, up_ratio32
apps/lwb-cc2538dk-env/Makefile                GEN_MODE/GEN_LEAD_MS/FRESH_ONLY/REPORT_EVERY, LWB_ROUND_TIMING_CONF, UART_LINE_BUF_LEN
net/lwb/lwb.c, net/lwb/lwb.h                  getter lwb_get_next_round_ticks() sau cờ LWB_ROUND_TIMING_CONF
tools/build_node.py                           EXTRA + --packets 0
tools/analyze_logs.py                         cộng superseded vào kiểm tra queued
tests/test_analyzer.py, tests/test_native.c   test mới
docs/PHASE_ALIGN_NOTES.md                     (file mới) tài liệu này
phase_align.diff                              (file mới) kết quả `git diff` (chỉ gồm file đã được git theo dõi)
```

(Các file đã sửa ở P2b: xem cuối file.)

## P2b – đọc cảm biến ngay trước khi gửi

Phạm vi: chỉ `GEN_MODE=1`, SOURCE. `GEN_MODE=0` giữ nguyên (xem "Đã kiểm tra" bên dưới).

### Vấn đề

Ở P2, SOURCE đọc cảm biến (I2C + OLED) ngay **sau** vòng rồi mới đóng gói ~4,7 s sau đó (`GEN_LEAD_MS` trước vòng kế tiếp).
Delay enqueue→HOST chỉ ~0,2 s nhưng giá trị trong gói đã **cũ ~4,9 s** (≈4,7 s chờ + ≈0,2 s truyền).

### Thiết kế

- `sample_sensor()` tách thành `sensor_read()` (I2C: HDC1080/Si7021, TSL2561, BMP180; **không** OLED) và `sensor_oled()`.
  `sample_sensor()` = cả hai (+ `last_sample_s`); vẫn là hàm được gọi ở `GEN_MODE=0`, ở HOST_LOCAL_SENSOR và lúc khởi động.
- Khi `gen_et` tới hạn (`gen_fire()` → `gen_emit()` → `gen_sense()`), sau `fresh_gate()` / `fresh_drop_stale()` và nhánh REPORT:
  - nếu `lwb_background_allowed(GEN_GUARD_MS + SENSOR_BUDGET_MS)` (30 + 150 ms): `sensor_read()` vào bộ đệm `latest`, rồi kiểm tra lại
    `lwb_background_allowed(GEN_GUARD_MS)`; còn cửa sổ thì `source_emit_data()` ngay.
  - ngược lại (còn < 180 ms tới vòng, ví dụ timer bị trễ vì main loop bận): **không đọc**, dùng giá trị cũ trong `latest`, `sensor_stale++`, vẫn enqueue
    nếu còn ≥ 30 ms.
  - nếu vòng đã bắt đầu *trong lúc đọc* (hoặc không còn 30 ms): không enqueue, `gen_deferred = 1`; gói đi ở cuối vòng đó (cơ chế dời có từ P2),
    lúc đó cảm biến được đọc lại (giá trị mới, delay ≈ 5 s, không đếm `sensor_stale`). Lần đọc bị bỏ là lãng phí nhưng vô hại.
- OLED của SOURCE: `gen_round_end()` đặt `oled_due`, `gen_service()` gọi `sensor_oled()` (chỉ OLED, hiển thị `latest` của lần gửi gần nhất)
  khi `lwb_background_allowed(BG_BUDGET_MS=700)`, như `sample_due` trước đây. Với `OLED=0` không có gì chạy sau vòng.
- Gói REPORT (chế độ liên tục) không chứa dữ liệu cảm biến nên không đọc cảm biến và không đếm `sensor_stale`.
- `SENSOR_BUDGET_MS` (Makefile / `--set`, mặc định 150, hợp lệ 20..1000, `#error` ngoài khoảng). `GEN_LEAD_MS` mặc định đổi 100 → 250
  (Makefile, `unified-conf.h`, README); hợp lệ vẫn 50..3000. Lead nhỏ hơn 30 + `SENSOR_BUDGET_MS` + ~20 ms (độ trễ etimer/process) vẫn biên dịch
  được nhưng gần như lần nào cũng dùng giá trị cũ (`sensor_stale` tăng liên tục).
- `PERF_GEN` (UART SOURCE, chỉ khi `GEN_MODE=1`) thêm cuối dòng `,sample_age_ms,N,sensor_stale,M`. `sample_age_ms` = `RTIMER_NOW()` lúc enqueue trừ
  `RTIMER_NOW()` lúc **bắt đầu** lần đọc cảm biến gần nhất (nên gồm cả thời gian I2C; nếu dùng giá trị cũ thì là tuổi của giá trị cũ, có thể nhiều giây).
  `PERF_SOURCE_SUMMARY` thêm `,sensor_stale,N` ở cuối (sau `superseded,gate_skipped` nếu có), chỉ khi `GEN_MODE=1`. Các khóa luôn ghép cặp
  nên `tools/analyze_logs.py` đọc được (đã thử với log mô phỏng) và bỏ qua khóa lạ. Ở `GEN_MODE=0` hai dòng in y hệt trước.

### Delay và tuổi dữ liệu kỳ vọng (mô phỏng; **chưa đo trên kit**)

Timer chạy ở `mốc vòng − GEN_LEAD_MS`; đọc I2C ≈ 22 (HDC1080) + 2 (TSL2561) + 15 (BMP180) ≈ 39 ms; rồi enqueue; slot của node kết thúc ≈ 101 ms sau
mốc vòng (1 source).

| | P2 (lead 100, đọc sau vòng) | P2b (lead 250, đọc trước khi gửi) |
|---|---:|---:|
| `sample_age_ms` (đọc → enqueue) | ≈ 4 700 (chưa in) | ≈ 40 (mô phỏng 38) |
| delay enqueue→HOST (`delay_ms`) | ≈ 202 ms | ≈ 250 − 39 + 101 ≈ **312 ms** (mô phỏng 306–314 tuỳ pha) |
| tuổi dữ liệu tại HOST = tuổi + delay | ≈ 4 900 ms | ≈ **350 ms** |

Cần nói rõ khi báo cáo: `delay_ms` mà analyzer tính **tăng ~110 ms** so với P2 (lead tăng 150 ms, còn thời gian I2C nằm *trước* mốc `tx_network_ticks`),
nhưng tuổi dữ liệu thật giảm ~14 lần. Muốn delay thấp hơn: hạ `GEN_LEAD_MS` (tối thiểu hợp lý ≈ 30 + `SENSOR_BUDGET_MS` + 20 = 200, delay ≈ 262 ms) hoặc hạ
`SENSOR_BUDGET_MS` (HDC1080 chỉ ~22 ms, retry tối đa ≈ 70 ms). Mỗi slot đứng trước slot của node vẫn cộng thêm ~70 ms. Ngoại lệ vẫn là gói bị dời tới
cuối vòng (delay ≈ 4,6–5,0 s, nhưng tuổi dữ liệu nhỏ vì cảm biến được đọc lại lúc đó).

### Rủi ro / chưa chắc chắn của P2b

1. Thời gian I2C thật (≈ 40 ms) và ngân sách 150 ms chỉ là ước lượng từ code. Nếu một lần đọc kéo dài hơn phần còn lại của cửa sổ (cảm biến kẹt,
   `i2c_sw_recover`), vòng bắt đầu giữa chừng và gói bị dời (delay ≈ 4,6 s). Một lần dời lẻ không làm mất gói; nếu lần nào cũng dời thì chỉ còn ≈ 1 gói/2 vòng,
   vì cơ chế dời có từ P2 chỉ hẹn lại timer ở cuối vòng kế tiếp (mô phỏng `hdc_ms=300`: 38 gói/76 vòng). Dấu hiệu: `delay_ms` ≈ 4,5 s và `generated` thấp hơn dự kiến.
2. Dùng giá trị cũ khi `gen_et` tới trễ hơn `GEN_LEAD_MS − 180` ms. Nguyên nhân thực tế duy nhất: OLED/I2C của chính app chạy lố vào cuối chu kỳ (OLED ước tính
   150–250 ms, xa mức 4,5 s). Nếu OLED lớn bất thường thì mọi lần gửi dùng giá trị cũ và `sample_age_ms` tăng dần (mô phỏng OLED 4,7 s).
3. Giữa lần đọc và lần enqueue, ISR rtimer vẫn chạy được (I2C bit-bang không chặn ngắt); chỉ vòng *bắt đầu* mới là vấn đề, và được chặn bằng hai lần kiểm tra
   `lwb_background_allowed` quanh lần đọc.
4. Tuổi dữ liệu tính từ lúc *bắt đầu* đọc (bảo thủ ≈ 40 ms); cảm biến có thời gian chuyển đổi riêng (HDC1080 chờ 20 ms). TSL2561 đọc kết quả của chu kỳ tích phân
   trước (không chờ) nên kênh sáng có thể cũ hơn `sample_age_ms` (chưa kiểm tra cấu hình tích phân thật).
5. OLED của SOURCE hiển thị mẫu của lần gửi gần nhất (cũ ≤ 5 s so với lúc hiển thị) và làm mới ~5 s; `SAMPLE_PERIOD` vẫn bị bỏ qua ở SOURCE khi `GEN_MODE=1`.
6. `sample_age_ms` dùng hiệu `uint32` của `RTIMER_NOW()` nên đúng tới ~36 giờ kể từ lần đọc gần nhất (chỉ sai nếu cảm biến không đọc được lần nào suốt thời gian đó).

### Đã kiểm tra những gì (P2b; không build firmware, không nạp kit)

- `gcc 13.2 -fsyntax-only -Wall -Wextra` (stub Contiki/LWB dựng lại trong thư mục tạm) cho 16 tổ hợp `GEN_MODE{0,1} × OLED{0,1} × PACKETS{100,0} × FRESH_ONLY{0,1}`,
  cấu hình tắt hết cảm biến, và cấu hình không truyền cờ nào (mặc định lấy từ `unified-conf.h`); không có cảnh báo mới (chỉ `newest_seq` unused đã có từ commit trước khi
  `GEN_MODE=0` và `FRESH_ONLY=0`). `#error` đúng cho `GEN_LEAD_MS=49/3001`, `SENSOR_BUDGET_MS=19/1001`, `GEN_MODE=1` thiếu getter, `PACKETS=2001`;
  `GEN_LEAD_MS=50/3000` hợp lệ.
- Mô phỏng host (stub LWB/etimer/rtimer, chạy chính file ứng dụng, vòng 5 s, slot node ở +70 ms, I2C 22+2+15 ms, OLED 200 ms): với `GEN_MODE=0`, log SOURCE
  **giống từng byte** commit `09fab22` ở 4 cấu hình (OLED bật/tắt, `FRESH_ONLY` 0/1, `PACKETS=0`) × 4 pha × 2 mức thời gian cảm biến/OLED (300 s mô phỏng).
  `GEN_MODE=1`: delay 306–314 ms, `sample_age_ms` 38, `sensor_stale` 0, 100/100 gói tới, `PERF_SOURCE_SUMMARY` có `sensor_stale,0`; chế độ liên tục REPORT đúng nhịp.
  Kịch bản ép: OLED 4,7 s → mọi lần dùng giá trị cũ (`sensor_stale` +1/gói, `sample_age_ms` tăng dần); HDC 300 ms → vòng bắt đầu trong lúc đọc, gói dời, delay ≈ 4,57 s,
  tuổi 316 ms. (OLED 4,8 s làm mất nhịp 1 gói/2 vòng ở cả P2 lẫn P2b: hành vi có sẵn, không do P2b.)
- `python -m unittest discover -s tests` → 12 test OK. Chưa chạy `tools/check.py` (cần cây Contiki), chưa build bằng GCC 4.9.3, chưa đo trên kit.

### Danh sách file đã sửa (P2b)

```text
apps/lwb-cc2538dk-env/lwb-cc2538dk-env.c   tách sensor_read/sensor_oled, gen_sense, oled_due, sample_age_ms/sensor_stale
apps/lwb-cc2538dk-env/unified-conf.h       GEN_LEAD_MS 250, SENSOR_BUDGET_MS (20..1000)
apps/lwb-cc2538dk-env/Makefile             GEN_LEAD_MS ?= 250, SENSOR_BUDGET_MS ?= 150, UP_SENSOR_BUDGET_MS
tools/build_node.py                        --set SENSOR_BUDGET_MS
README_VI.md                               bảng tham số + mô tả mục 15/11
docs/PHASE_ALIGN_NOTES.md                  mục này
p2b.diff                                   (file mới) git diff của các file trên, chưa commit
```
