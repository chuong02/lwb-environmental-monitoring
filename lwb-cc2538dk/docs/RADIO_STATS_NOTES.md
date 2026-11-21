# RADIO_STATS_NOTES — đo radio duty cycle bằng phần mềm

Phạm vi: `apps/lwb-cc2538dk-env` + `net/glossy`. Cờ `RADIO_STATS` (mặc định 0). Mọi số dòng dưới đây là của
cây làm việc sau khi thêm cờ (đã có P2b, commit `a1a6c38`), trừ khi ghi khác. "Chưa xác nhận" = suy ra từ code, chưa đo trên kit.

## 1. Cách dùng

```bash
# thêm vào lệnh build của mọi node (HOST, SOURCE, RELAY):  --set RADIO_STATS=1  [--set RADIO_STATS_PERIOD=12]
python3 tools/build_node.py --contiki ~/contiki --node 2 --role SOURCE --host 1 \
  --sources 2:3:4:5 --run 520 --packets 100 --ipi 5 --set GEN_MODE=1 --set RADIO_STATS=1 --out ~/lwb-build
```

- `RADIO_STATS=0` (mặc định): không có mã nào được biên dịch thêm (`glossy.c`, app đều như cũ), không có dòng UART mới.
- `RADIO_STATS=1`: mỗi `RADIO_STATS_PERIOD` vòng (mặc định 12 = 60 s với vòng 5 s; hợp lệ 1..10000) mỗi node in 1 dòng `PERF_RADIO`
  (chu kỳ vừa qua + tổng từ lúc khởi động). `PERF_CONFIG` có thêm `,radio_stats,1,radio_stats_period,N`.
- Ảnh hưởng tới các node khác: không. Mỗi node tự đo; không thêm byte nào lên không khí (gói vẫn 28 byte).

## 2. Radio BẬT / TẮT ở đâu (đọc từ code)

Radio chỉ được bật/tắt trong `net/glossy/glossy.c` (đã grep toàn repo: `ISRXON/ISTXON/ISRFOFF/RFST` chỉ có ở `glossy.c` và `cc2538-rf.c`):

| Việc | Hàm / dòng | Ghi chú |
|---|---|---|
| **BẬT**, node không phải initiator | `glossy_start()` nhánh else → `radio_on()` (`glossy.c:536`): `ISFLUSHRX` + `ISRXON` | gọi từ rtimer ISR của LWB (`LWB_WAIT_UNTIL` xong thì `glossy_start`); ở slot không phải của mình và slot tranh chấp của HOST bật sớm `T_GUARD`=1 ms; SOURCE ở slot tranh chấp và sync bật đúng/sớm `t_sync_guard` |
| **BẬT**, initiator | `glossy_start()` nhánh `IS_INITIATOR()` → `radio_start_tx()` (`glossy.c:582`): `ISTXON` | "Actual transmission starts after 192 us"; radio vào TX sau ~192 µs |
| **TẮT** (đường 1) | `glossy_stop()` (`glossy.c:1486`) → `radio_off()` (`:548`): `ISRFOFF` nếu `RXENABLE != 0` | do LWB gọi khi hết cửa sổ slot (`T_SYNC_ON`, `T_RR_ON` + guard) |
| **TẮT** (đường 2) | `glossy_tx_ended()` (`:918`) khi `tx_cnt == N_max` → `glossy_stop()` (`:938`) | **trong RF ISR**, ngay sau TX cuối. Đây là cách Glossy tắt sớm khi flood thành công |
| **TẮT** (đường 3) | `process_received_data()` (`:871-875`): nhận thêm một gói khi đã đủ `N_max` lần TX → `radio_abort_tx()` + `glossy_stop()` | **trong RF ISR**, sau quyết định "không cần relay nữa" |
| Không đổi trạng thái bật/tắt | `radio_abort_tx()` (`ISRXON` lại, ép hiệu chỉnh RX), `radio_abort_rx()` (chỉ flush) | radio vẫn bật; thời gian vẫn nằm trong cùng flood |
| Không chạy ở runtime | `cc2538-rf.c:114/121` `cc2838_rf_on()/off()` (`ISRXON`/`ISRFOFF`) | chỉ được `cc2538_rf_set_channel()` gọi khi radio **không** ở trạng thái idle; lúc `glossy_init()` radio đang tắt nên không chạy. `cc2538_rf_init()` không bật radio |

Hệ quả: radio bật đúng từ lúc `glossy_start()` thành công đến lần `glossy_stop()` **đầu tiên** thấy `state == ACTIVE`
(`glossy_stop()` thứ hai của cùng flood trả về sớm ở `state == OFF`, không đụng radio). Mọi chỗ gọi nằm trong `lwb-g-sync.c` / `lwb-g-rr.c`
theo cặp start–stop (đã đếm: 13 `glossy_start` và 13 `glossy_stop()` ở hai file đó). Ngoài Glossy không có gì bật radio, với điều kiện `NETSTACK` rỗng (`LWB_CONF_NULL_NETSTACK=1` trong Makefile;
cây Contiki nằm ngoài repo nên chưa kiểm tra).

Glossy đã tự gọi `ENERGEST_ON/OFF(ENERGEST_TYPE_LISTEN)` ở đúng các điểm trên (kể cả `radio_start_tx()` của initiator, cũng ghi vào `LISTEN`),
và `project-conf.h` bật `ENERGEST_CONF_ON=1`. Tức là cách "Contiki power profiler" của bài LWB cùng khoảng thời gian với cách đo ở đây;
`RADIO_STATS` tồn tại vì Energest cộng 32 bit (quay vòng sau ~36 giờ), không cho số flood, và không in định kỳ.

## 3. Cài đặt (và vì sao không đụng đường relay)

- `net/glossy/glossy-radio-stats.h` (file mới, chỉ số học, không chạm phần cứng): `glossy_rs_on/off/read`.
  Cộng dồn `radio_on_ticks` (uint64, tick rtimer), `floods` (uint32), `tx_count`, và `tx_on_us` (uint64).
- `glossy.c` thêm đúng 3 chỗ, tất cả sau `#if GLOSSY_RADIO_STATS`:
  1. `glossy_start()`: sau khi đã phát lệnh `ISRXON/ISTXON`, 1 lần `RTIMER_NOW()` (đọc sau lệnh nên không làm trễ lệnh).
  2. `glossy_stop()`: dùng luôn `t_now_rt = RTIMER_NOW()` có sẵn, đọc ngay sau `radio_off()`; phép cộng nằm **sau** đoạn đo thời gian tới hạn
     (`t_next_rt` / `t_now_mtt`), nên không đổi độ chính xác `t_ref`.
  3. Hàm đọc `glossy_get_radio_stats()` (seqlock; chỉ gọi từ process).
- **Không chèn gì** vào `cc2538_rf_mt_isr()`, `glossy_rx_ended()` (chỗ `mt_schedule_tx_csp()`), `glossy_tx_started()`, hay đường relay/TX-trigger.
  Mã mới trong ISR chỉ chạy ở `glossy_stop()` khi flood đã kết thúc và radio đã tắt (~vài chục lệnh ARM + cộng số 64 bit), và `RTIMER_NOW()` (4 lần đọc thanh ghi)
  trong `glossy_start()`.
- Wrap RTIMER 32 bit: mọi khoảng tính bằng `(uint32_t)(off - on)` rồi cộng vào 64 bit; đúng khi một flood < 2^32 tick (~36 giờ). Thời gian trôi qua
  (`elapsed`) giữa hai dòng `PERF_RADIO` cũng là hiệu `uint32` (process chạy mỗi ≤ 1 s nên không thể bỏ lỡ một vòng wrap). Tử số và mẫu số cùng tick, nên wrap không ảnh hưởng tỉ lệ.
  Đã thử trong mô phỏng: khởi động rtimer ở `2^32 − 40 s` và `2^32 − 256 tick` cho ra đúng cùng số liệu như không wrap; thêm test `test_radio_stats` (wrap, 10^5 flood, flood dài qua wrap).
- Đọc từ process trong khi ISR ghi: `seq` kiểu seqlock (đọc lại nếu `seq` lẻ hoặc đổi). Hai `glossy_stop()` chồng nhau (RF ISR ưu tiên cao hơn rtimer ISR)
  chỉ đếm một lần nhờ `__atomic_exchange_n` trên cờ `on`. **Chưa xác nhận** GCC 4.9.3 `arm-none-eabi` sinh `ldrexb/strexb` inline cho lệnh này (nên là vậy với Cortex-M3);
  nếu link báo `__atomic_exchange_1`, thay bằng `if(!rs->on) return; rs->on = 0;` (cửa sổ race chỉ vài lệnh và giống cửa sổ có sẵn của `state` trong `glossy_stop()`).
- App: `on_sched_end()` (mọi vai trò, kể cả HOST/RELAY) đếm vòng; tới `RADIO_STATS_PERIOD` thì đặt cờ + `process_poll`. In **trong process app**, chỉ khi
  `lwb_background_allowed(100)` (dòng ~250 ký tự ≈ 22 ms ở 115200 baud), nên không bao giờ rơi giữa vòng. SOURCE chưa đồng bộ (bootstrap, `round_active=1`) sẽ không in cho tới khi sync.
  `printf` 64 bit không dùng (`%llu` không chắc có trong newlib-nano): các tổng 64 bit in qua `u64_dec()`.

## 4. Định dạng dòng `PERF_RADIO`

```
PERF_RADIO,run,<run>,node,<id>,role,<HOST|SOURCE|RELAY>,elapsed_ms,<>,radio_on_ms,<>,duty_x10000,<>,floods,<>,avg_on_per_flood_us,<>,tx_on_ms,<>,
           cum_elapsed_ms,<>,cum_radio_on_ms,<>,cum_duty_x10000,<>,cum_floods,<>,cum_avg_on_per_flood_us,<>,cum_tx_on_ms,<>
```

(một dòng, ≈ 250 ký tự; `UART_LINE_BUF_LEN` = 512)

| Trường | Nghĩa |
|---|---|
| `elapsed_ms` / `cum_elapsed_ms` | thời gian kể từ dòng trước / từ lúc process app khởi động (rtimer, làm tròn ms). Dòng đầu tiên dài hơn 60 s (gồm khởi động + bootstrap) |
| `radio_on_ms` | tổng (tắt − bật) của các flood hoàn tất trong khoảng đó |
| `duty_x10000` | `radio_on / elapsed × 10000` (165 = 1,65 %), tính từ tick chứ không từ ms đã làm tròn |
| `floods` | số cặp bật/tắt radio hoàn tất (sync + slot dữ liệu + slot tranh chấp + ack, **kể cả flood chỉ nghe không thu được gì**) |
| `avg_on_per_flood_us` | `radio_on / floods` |
| `tx_on_ms` | **ước lượng** thời gian phát: `Σ tx_cnt × (6 + tx_rx_len) × 32 µs` (6 = preamble 4 + SFD 1 + PHR 1; 32 µs/byte). Không gồm 192 µs quay đầu TX. Không đo trực tiếp được vì CSP kích hoạt TX trong phần cứng (xem NOTE trong `radio_start_tx()`), nên không đặt mã vào đường TX |
| `cum_*` | cùng ý nghĩa, cộng dồn từ lúc khởi động (`cum_elapsed_ms`, `cum_radio_on_ms`, `cum_tx_on_ms` in qua `u64_dec`) |

## 5. Duty cycle kỳ vọng theo tính toán (chưa đo)

Giả thiết: cấu hình mặc định (`RTIMER_SECOND`=32768, `N_SYNC`=3, `N_DATA_TX`=3, `T_SYNC_ON`=`T_RR_ON`=30,27 ms, `T_GUARD`=0,98 ms, `T_GAP`=39,98 ms, bước slot 70,25 ms),
vòng 5 s, 1 HOST + 4 SOURCE (2:3:4:5), IPI=5 ⇒ mỗi vòng 4 slot dữ liệu (đều có gói) + 1 slot tranh chấp, không slot ack; mọi node nghe được nhau (1 hop);
gói dữ liệu `tx_rx_len` = 1 (id) + 4 (header Glossy) + 34 (1 + 5 + 28) + 2 (FCS) = **41 B**; gói lịch ≈ **18 B** (ước lượng; phụ thuộc nén lịch, ảnh hưởng nhỏ).

Thời gian một frame `A = (6 + len) × 32 µs`; một "nhịp" Glossy `T = A + 50 µs (xử lý) + 192 µs (quay đầu)` = 1,746 ms (dữ liệu), 1,010 ms (lịch).
Với `N` lần TX, 1 hop: initiator bật `0,192 + (2N−2)·T + A`; node nhận (relay) bật `guard + 0,192 + (2N−1)·T + A`.

| Flood | Công thức (N=3) | Thời gian bật |
|---|---|---|
| Sync, HOST (initiator) | 0,192 + 4×1,010 + 0,768 | 5,00 ms |
| Sync, SOURCE | 0,98 + 0,192 + 5×1,010 + 0,768 | 6,99 ms |
| Dữ liệu, chủ slot (initiator) | 0,192 + 4×1,746 + 1,504 | 8,68 ms |
| Dữ liệu, node khác / HOST | 0,98 + 0,192 + 5×1,746 + 1,504 | 11,40 ms |
| Tranh chấp, SOURCE (nghe suốt `T_RR_ON`, không ai phát) | 30,27 | 30,27 ms |
| Tranh chấp, HOST (dậy sớm, ra muộn `T_GUARD`) | 30,27 + 2×0,98 | 32,23 ms |

Mỗi vòng 5 s:

- **SOURCE**: 6,99 + 8,68 + 3×11,40 + 30,27 ≈ **80,1 ms ⇒ 1,60 %** (`duty_x10000` ≈ 160), 6 flood/vòng ⇒ `avg_on_per_flood` ≈ 13,4 ms; TX ước lượng ≈ 20,4 ms (0,41 %).
- **HOST**: 5,00 + 4×11,40 + 32,23 ≈ **82,8 ms ⇒ 1,66 %** (≈ 166), `avg_on_per_flood` ≈ 13,8 ms.
- Nhận xét: slot tranh chấp chiếm ≈ 38 % thời gian bật vì firmware dùng `T_RR_ON` (30 ms) cho cả slot tranh chấp (`T_FREE_ON`=10 ms chỉ được dùng để tính băng thông
  trong `lwb-macros.h`, không dùng khi chạy). Nếu cửa sổ tranh chấp còn 10 ms thì duty ≈ 1,20 %.
- Mỗi slot dữ liệu mà chủ slot **không có gói** làm mọi node khác nghe đủ cửa sổ: +≈ 19–21 ms/node/vòng (≈ +0,4 %).
- `N`=2: SOURCE ≈ 64 ms ≈ 1,28 %. 1 SOURCE (1 slot dữ liệu): SOURCE ≈ 0,92 %, HOST ≈ 0,97 %.
- Nhiều hop làm mỗi flood dài hơn (thêm khoảng 2 nhịp mỗi hop cho node ở xa); số trên là cận dưới cho topo 1 hop. Lệch xung nhịp/guard động (`T_GUARD_1..3` khi mất sync) làm tăng thêm.
- Dòng đầu tiên của SOURCE gồm cả bootstrap (nghe liên tục tới khi nhận được lịch) nên duty cao bất thường; dùng các dòng sau, hoặc hiệu của `cum_*` giữa hai dòng.

Cách đối chiếu khi đo thật: `duty_x10000` kỳ vọng 150–200 cho SOURCE/HOST ở cấu hình trên; `floods` mỗi chu kỳ 12 vòng ≈ 72 (6 × 12);
`avg_on_per_flood_us` ≈ 13 000–14 000; `tx_on_ms` ≈ 245 ms (20,4 × 12). Lệch lớn ⇒ xem có slot rỗng (gói tới trễ), mất sync (guard lớn), hay nhiều hop.

## 6. So sánh với các bài báo

**Bài LWB (con số 1,40 %).** Con số này do bạn nêu; bài báo không có trong repo nên tôi **chưa kiểm chứng** điều kiện của nó và không khẳng định số nào khác.
Muốn so sánh đúng phải căn cho khớp các tham số mà duty cycle phụ thuộc trực tiếp (công thức trên): chu kỳ vòng `T`, số slot dữ liệu mỗi vòng, độ dài gói
(`A`, `T_slot`), `N` (số lần TX), độ dài cửa sổ mỗi slot (ở đây cố định 30 ms), số và độ dài slot tranh chấp, guard, topo (số hop), và định nghĩa: radio-on của
CC2538 (kể cả calibration 192 µs) chia cho tổng thời gian, trung bình trên node nào (HOST hay SOURCE). Với cấu hình mặc định ở đây, 1,6 % là thứ tính được; chênh khoảng 0,2
điểm phần trăm so với 1,40 % nằm trong khoảng mà riêng việc đổi cửa sổ tranh chấp 30 → ~20 ms (−10 ms/vòng) hay `N` 3 → 2 (−16 ms/vòng) đã đủ giải thích, nên **không nên** coi
hai số là cùng điều kiện cho tới khi đối chiếu tham số bài báo. Khi đo thật, báo `duty_x10000` của từng dòng (không chỉ trung bình), kèm cấu hình trên.

**Bài Glossy (radio on-time mỗi flood).** Số gần nhất của ta là `avg_on_per_flood_us`, nhưng khác định nghĩa: ở đây `floods` gồm cả flood chỉ nghe không thu được gì
(slot tranh chấp ≈ 30 ms, slot rỗng) và flood sync, nên **không so thẳng** được với "radio-on time per flood" của bài Glossy (chỉ tính flood đã chạy xong N TX). Để so
cho đúng cần tách theo loại flood (`rx_cnt>0` hay không, theo `GLOSSY_WITH_SYNC` hay không); hiện chưa làm. Bảng ở mục 5 cho giá trị kỳ vọng từng loại: flood dữ liệu
1 hop N=3 ≈ 8,7 ms (initiator) / 11,4 ms (relay), flood sync ≈ 5,0 / 7,0 ms. Công thức kỳ vọng theo `N` ở trên (≈ `(2N−2)·T + A + 0,2` ms cho initiator) cũng là cách đối chiếu xu hướng với bài Glossy
khi đổi `N_SYNC` / `N_DATA_TX`.

## 7. Độ chính xác và giới hạn

- Độ phân giải 1 tick rtimer = 30,5 µs ở mỗi đầu flood (sai số ngẫu nhiên ±1 tick, không thiên lệch có hệ thống); với flood ~10 ms ≈ 0,3 %. Mốc BẬT lấy sau lệnh strobe vài µs,
  mốc TẮT lấy ngay sau `ISRFOFF` (trước vòng chờ tick của `glossy_stop()`), nên sai lệch phần mềm < 5 µs/flood.
- Đo thời gian lệnh bật→tắt, tức gồm cả thời gian hiệu chỉnh/khởi động của radio sau `ISRXON/ISTXON`, giống Energest và bảng dòng điện của RF core; **không** gồm CPU, UART, cảm biến, OLED.
- `tx_on_ms` là ước lượng từ `tx_cnt` (TX hoàn tất): TX đang dở lúc `glossy_stop()` không được tính.
- `SOURCE`/`RELAY` mất sync dài sẽ vào bootstrap (nghe liên tục): duty tiến tới 100 % trong giai đoạn đó, đúng thực tế nhưng làm méo số trung bình.
- Chưa xác nhận trên kit: (1) `__atomic_exchange_n` với toolchain đích; (2) so với `energest_type_time(ENERGEST_TYPE_LISTEN)` (Energest đã bật): hai số nên khớp trong ~`floods` tick;
  (3) tổng RAM/flash (thêm ≈ 100 B RAM, ≈ vài trăm B flash khi bật); (4) ảnh hưởng của vài chục lệnh thêm trong `glossy_stop()` lên `t_ref` (về lý thuyết bằng 0 vì nằm sau phần đo).
- Khi `RADIO_STATS=0`: `GLOSSY_RADIO_STATS=0`, `glossy.c`/`glossy.h` biên dịch ra đúng mã cũ; app không in `PERF_RADIO`, `PERF_CONFIG` không có trường mới (đã kiểm tra bằng mô phỏng, xem dưới).

## 8. Đã kiểm tra những gì (không build firmware, không nạp kit)

- `gcc 13.2 -fsyntax-only -Wall -Wextra` (stub Contiki/LWB dựng lại trong thư mục tạm) cho `RADIO_STATS{0,1} × GEN_MODE{0,1} × ROLE{HOST,SOURCE,RELAY} × PACKETS{100,0}` (24 tổ hợp)
  và cấu hình không truyền cờ radio nào: không lỗi, không cảnh báo mới. `#error` đúng cho `RADIO_STATS=2`, `RADIO_STATS_PERIOD=0/10001`, `RADIO_STATS=1` thiếu hook Glossy; `PERIOD=1/10000` hợp lệ.
  `glossy.c` **không** syntax-check được ở đây (không có toolchain ARM, thiếu CMSIS); 3 chỗ thêm vào được soát bằng mắt (kiểu `uint8_t tx_cnt, tx_rx_len`, `rtimer_clock_t t_now_rt`).
- Mô phỏng host (stub LWB/etimer/rtimer, chạy chính file ứng dụng, mô hình flood: sync 11 ms, slot dữ liệu của mình 8,5 ms, tranh chấp 30 ms): `RADIO_STATS=0` cho log SOURCE **giống từng byte**
  commit `a1a6c38` ở 6 cấu hình (`GEN_MODE` 0/1 × OLED 0/1, `PACKETS=0` với `GEN_MODE` 0/1) × 3 pha × 2 mức thời gian cảm biến/OLED (300 s mô phỏng). `RADIO_STATS=1`: dòng đầu ở 61,2 s, các dòng sau
  cách đúng 60 s, `floods` 36/chu kỳ (3 × 12 vòng), `radio_on_ms` 594 (mô hình 49,5 ms × 12), `tx_on_ms` 85, `duty_x10000` 99; khởi động rtimer gần wrap cho đúng cùng số liệu. Các số này chỉ kiểm tra đường
  dẫn (đếm vòng, chu kỳ, định dạng, wrap, 64 bit), **không** phải số đo radio thật.
- `tests/test_native.c` thêm `test_radio_stats` (bật/tắt, bật hai lần, tắt hai lần, wrap, 10^5 flood, flood dài qua wrap, ước lượng TX); biên dịch với `-std=c99 -Wall -Wextra -Werror` cùng `list.c/memb.c`
  của cây Contiki ở `../Contiki os/core` và chạy PASS (chưa chạy trọn `tools/check.py`: lệnh gọi `python3` và ASan, không dùng ở đây).
- `python -m unittest discover -s tests` → 12 test OK.
- Gateway: xem mục 9.

## 9. Gateway (`gateway/lwb_source/lwb_gateway.py`, nằm ngoài repo `lwb-cc2538dk`)

- Dòng có checksum hợp lệ (`UART_CHECKSUM=1`, mặc định) **luôn được lưu** vào SQLite, `KNOWN_TYPES` không lọc chúng. `KNOWN_TYPES` chỉ dùng cho dòng **không** checksum
  (`legacy_line_looks_valid`): dòng loại không có trong danh sách bị ghi là `UART_BAD`. Đã thêm `"PERF_RADIO"` vào `KNOWN_TYPES` (chỉ sửa danh sách).
- Đã thử bằng hàm của chính gateway với một dòng `PERF_RADIO` mô phỏng: có `*HH` đúng → `ok`, `source`=node, `run`=run, các khóa `cum_*` được nhận; không có `*HH` → được chấp nhận sau khi thêm vào danh sách;
  sai `*HH` → `bad`.
- Không đổi: `mqtt_publisher.py` có danh sách `PERF_TYPES` riêng, **không** có `PERF_RADIO`, nên dòng này nằm trong SQLite nhưng không lên MQTT. Nếu cần đẩy lên cloud thì thêm vào `PERF_TYPES` (chưa làm vì ngoài yêu cầu).
  `PERF_GATE`, `PERF_SUPERSEDE`, `PERF_REPORT_TX` (cờ FRESH_ONLY / `PACKETS=0`) cũng chưa có trong `KNOWN_TYPES`: chỉ ảnh hưởng khi build với `UART_CHECKSUM=0`.
- Giữ build có checksum (mặc định) cho các lượt đo `RADIO_STATS`; dòng ~250 ký tự vẫn dưới 512 của bộ đệm checksum.

## 10. Danh sách file đã sửa

```text
net/glossy/glossy-radio-stats.h            (file mới) số học cộng dồn, wrap-safe, seqlock
net/glossy/glossy.h                        cờ GLOSSY_RADIO_STATS, khai báo glossy_get_radio_stats()
net/glossy/glossy.c                        3 chỗ sau #if GLOSSY_RADIO_STATS: g_rs + getter, glossy_start(), glossy_stop()
apps/lwb-cc2538dk-env/lwb-cc2538dk-env.c   đếm vòng, PERF_RADIO, trường PERF_CONFIG
apps/lwb-cc2538dk-env/unified-conf.h       RADIO_STATS, RADIO_STATS_PERIOD, kiểm tra hợp lệ
apps/lwb-cc2538dk-env/Makefile             RADIO_STATS ?= 0, RADIO_STATS_PERIOD ?= 12, GLOSSY_RADIO_STATS_CONF
tools/build_node.py                        --set RADIO_STATS / RADIO_STATS_PERIOD
tests/test_native.c                        test_radio_stats
README_VI.md                               bảng tham số + ghi chú ngắn
docs/RADIO_STATS_NOTES.md                  (file mới) tài liệu này
radio_stats.diff                           (file mới) git diff + file mới, chưa commit
../gateway/lwb_source/lwb_gateway.py       (ngoài repo) thêm "PERF_RADIO" vào KNOWN_TYPES
```
