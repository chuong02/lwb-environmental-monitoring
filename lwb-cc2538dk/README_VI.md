# Firmware LWB ENV thống nhất — bản 1

## Cập nhật 15/11/2026: đồng bộ pha tạo gói với vòng LWB, chống dồn hàng đợi, chế độ liên tục

**Vấn đề.** Trước đây SOURCE tạo gói bằng etimer chu kỳ `IPI`, pha của nó so với vòng LWB (5 s) là
ngẫu nhiên và trôi theo thời gian, nên gói có thể ngồi trong hàng đợi gần một vòng trước khi tới slot
(delay đo được phụ thuộc pha, không phụ thuộc đường truyền). Các cờ dưới đây xử lý việc đó. **Mặc định
các cờ đều tắt: firmware chạy y như bản 12/11** (đã đối chiếu log mô phỏng trên máy dev, xem
`docs/PHASE_ALIGN_NOTES.md`).

| Make variable | Mặc định | Ý nghĩa |
|---|---:|---|
| `GEN_MODE` | 0 | 0 = etimer IPI như cũ. 1 = tạo gói `GEN_LEAD_MS` ms **trước khi vòng kế tiếp bắt đầu**; cảm biến I2C được đọc **ngay trước khi enqueue** (nếu đủ thời gian, xem `SENSOR_BUDGET_MS`), OLED chỉ cập nhật ngay **sau** mỗi vòng |
| `GEN_LEAD_MS` | 250 | Chỉ dùng khi `GEN_MODE=1`; 50..3000. Phải chừa chỗ cho lần đọc I2C: nên ≥ 30 + `SENSOR_BUDGET_MS` + ~20. `tx_network_ticks` vẫn lấy lúc enqueue (sau khi đọc cảm biến) |
| `SENSOR_BUDGET_MS` | 150 | Chỉ dùng khi `GEN_MODE=1`; 20..1000. Chỉ đọc I2C nếu còn > 30 + `SENSOR_BUDGET_MS` ms tới vòng kế tiếp; nếu không, dùng giá trị cũ và đếm `sensor_stale` |
| `FRESH_ONLY` | = `GEN_MODE` | 1 = không tạo gói (không tăng seq) khi chưa synced hoặc chưa có stream ack; nếu hàng đợi còn gói cũ thì bỏ gói cũ, giữ gói mới |
| `PACKETS` | 100 | **0 = chế độ liên tục**: phát vô hạn, không có bước chốt/drain |
| `REPORT_EVERY` | 60 | Chỉ khi `PACKETS=0`: cứ mỗi `REPORT_EVERY` gói DATA, một lượt phát kế tiếp dành cho REPORT cộng dồn (5..10000) |
| `RADIO_STATS` | 0 | 1 = đo radio duty cycle bằng phần mềm: cộng thời gian radio bật giữa `glossy_start()` và `glossy_stop()` của mọi flood; in `PERF_RADIO` mỗi `RADIO_STATS_PERIOD` vòng. 0 = không có mã thêm, không có dòng mới |
| `RADIO_STATS_PERIOD` | 12 | Chỉ khi `RADIO_STATS=1`: số vòng giữa hai dòng `PERF_RADIO` (1..10000; 12 vòng = 60 s) |

Khác biệt cần biết:

- `GEN_MODE=1` cần getter `lwb_get_next_round_ticks()` trong `net/lwb/lwb.c` (chỉ được biên dịch khi
  `LWB_ROUND_TIMING_CONF=1`, Makefile tự đặt theo `GEN_MODE`). Delay kỳ vọng (enqueue → HOST) với IPI=5, 1 source,
  `GEN_LEAD_MS=250`: ≈ `GEN_LEAD_MS` − thời gian đọc I2C (~40 ms) + ~100 ms (sync + slot) ≈ 0,31 s; thêm ~70 ms cho mỗi slot đứng trước.
  Tuổi dữ liệu cảm biến lúc enqueue ≈ 40 ms (trước P2b ≈ 4,7 s), tức tuổi tại HOST ≈ 0,35 s thay vì ≈ 4,9 s; đổi lại `delay_ms`
  tăng ~0,1 s so với `GEN_LEAD_MS=100`. Nếu timer bị trễ
  tới giữa vòng, hoặc node bắt đầu đo đúng lúc đang giữa vòng (chưa biết mốc vòng), gói vẫn được tạo đúng 1 lần nhưng
  dời tới cuối vòng đó (hàng đợi LWB không an toàn với ISR) nên đi ở vòng sau với delay ≈ 5 s: ngoại lệ có chủ ý,
  dùng p95/median khi đọc delay. Với `IPI>5` gói đầu tiên có thể chờ thêm tới `IPI` giây để vào đúng vòng có slot.
- Với `GEN_MODE=1`, `SAMPLE_PERIOD` bị bỏ qua ở SOURCE: cảm biến I2C (HDC1080/Si7021, TSL2561, BMP180, không OLED) được đọc 1 lần ngay trước mỗi lần
  enqueue; OLED chỉ cập nhật 1 lần/vòng ngay sau vòng (hiển thị mẫu của lần gửi gần nhất) nên làm mới mỗi ~5 s thay vì 1 s.
  HOST với `HOST_LOCAL_SENSOR=1` giữ chu kỳ cũ. Nếu lúc timer tới hạn còn ít hơn 30 + `SENSOR_BUDGET_MS` ms tới vòng kế tiếp (timer bị trễ), SOURCE
  không đọc mà dùng giá trị cũ trong bộ đệm và tăng `sensor_stale`; nếu vòng bắt đầu giữa lúc đọc thì gói dời tới cuối vòng (đọc lại lúc đó).
  `PERF_GEN` thêm cuối dòng `sample_age_ms` (từ lúc bắt đầu đọc cảm biến tới lúc enqueue) và `sensor_stale`; `PERF_SOURCE_SUMMARY` thêm `sensor_stale` ở cuối
  (chỉ khi `GEN_MODE=1`). Với `GEN_MODE=0` hai dòng này không đổi.
- `FRESH_ONLY=1` thêm dòng UART `PERF_GATE` (bỏ lượt vì chưa sync/chưa ack), `PERF_SUPERSEDE` (bỏ gói cũ) và
  hai trường `superseded`, `gate_skipped` ở cuối `PERF_SOURCE_SUMMARY`. Quan hệ chốt mới:
  `queued = tx_started + tx_start_failed + discarded + superseded`; `tools/analyze_logs.py` đã tính
  `superseded` (log cũ không có trường này vẫn chạy như trước).
- Chế độ liên tục: `PERF_CONFIG` in `expected,0`; `PERF_SUMMARY` vẫn in định kỳ với bộ đếm 32 bit và thêm
  `mode,continuous,reports,N`; `generated/queued/tx_started` và các yield tính **từ REPORT đầu tiên HOST nhận được** đến REPORT
  mới nhất (số nhận được lấy tại lúc REPORT mới nhất tới). `seq` trên dây vẫn 16 bit, quay vòng 1..65535
  (không dùng 0); HOST mở rộng bằng số học serial. Một lượt REPORT thay chỗ một gói DATA (stream chỉ có 1 slot/vòng),
  không tiêu seq. `tools/analyze_logs.py` chưa phân tích log liên tục (`expected,0` → `expected_count_unavailable`);
  dùng `PERF_SUMMARY`/`PERF_REPORT` để giám sát. Với `PACKETS=0` Makefile đặt `UART_LINE_BUF_LEN=768` (dòng `PERF_SUMMARY` dài hơn 512 ký tự).
- Mọi node (HOST, SOURCE, RELAY) trong một lượt phải build với **cùng** `PACKETS`, `GEN_MODE`, `FRESH_ONLY`, `REPORT_EVERY`.
- `RADIO_STATS=1` thêm hook ở hai đầu mỗi flood trong `net/glossy/glossy.c` (không chạm đường relay/TX-trigger) và dòng
  `PERF_RADIO,run,..,node,..,role,..,elapsed_ms,..,radio_on_ms,..,duty_x10000,..,floods,..,avg_on_per_flood_us,..,tx_on_ms,..,cum_*`
  (chu kỳ vừa qua + cộng dồn từ lúc khởi động; `tx_on_ms` là ước lượng). Có thể bật trên từng node độc lập (không đổi gói/giao thức). Duty cycle tính toán cho 1 HOST + 4 SOURCE,
  vòng 5 s, N=3 ≈ 1,6 % (chưa đo); công thức, điểm bật/tắt radio, cách so với bài LWB/Glossy: `docs/RADIO_STATS_NOTES.md`. Gateway: thêm `PERF_RADIO` vào `KNOWN_TYPES`.

**Build cho 5 kit** (HOST=1, SOURCE=2..5; sửa `--contiki`, `--out` cho đúng máy build):

```bash
# (a) Đo hiệu năng có đồng bộ pha: RUN_ID=510, 100 gói/source, GEN_MODE=1 (FRESH_ONLY bật theo)
for n in 2 3 4 5; do
  python3 tools/build_node.py --contiki ~/contiki --node $n --role SOURCE --host 1 \
    --sources 2:3:4:5 --run 510 --packets 100 --ipi 5 --set GEN_MODE=1 --out ~/lwb-build
done
python3 tools/build_node.py --contiki ~/contiki --node 1 --role HOST --host 1 \
  --sources 2:3:4:5 --run 510 --packets 100 --ipi 5 --set GEN_MODE=1 --out ~/lwb-build

# (b) Giám sát liên tục: RUN_ID=900, PACKETS=0, GEN_MODE=1 (REPORT mỗi 60 gói ≈ 5 phút)
for n in 2 3 4 5; do
  python3 tools/build_node.py --contiki ~/contiki --node $n --role SOURCE --host 1 \
    --sources 2:3:4:5 --run 900 --packets 0 --ipi 5 --set GEN_MODE=1 --out ~/lwb-build
done
python3 tools/build_node.py --contiki ~/contiki --node 1 --role HOST --host 1 \
  --sources 2:3:4:5 --run 900 --packets 0 --ipi 5 --set GEN_MODE=1 --out ~/lwb-build
```

Muốn HOST hiện nhiệt độ/độ ẩm khi giám sát liên tục: thêm `--set HOST_LOCAL_SENSOR=1` vào lệnh build HOST.
Dùng `--set GEN_LEAD_MS=...`, `--set SENSOR_BUDGET_MS=...`, `--set FRESH_ONLY=0`, `--set REPORT_EVERY=...` để đổi các giá trị trên.

**Trạng thái kiểm tra:** chưa build bằng GCC 4.9.3, chưa nạp kit. Đã kiểm tra cú pháp bằng gcc host,
chạy mô phỏng logic (stub LWB) và `tests/test_analyzer.py`. Đo delay/ổn định thật trên kit vẫn cần làm.
Chi tiết, rủi ro timing và điểm chưa chắc chắn: `docs/PHASE_ALIGN_NOTES.md`.

## Cập nhật 12/11/2026: checksum UART + lệnh build cho 5 kit

**Checksum UART.** Mỗi dòng in ra UART giờ có dạng `<dòng>*HH`, với `HH` = XOR mọi byte trước `*`
(file `apps/lwb-cc2538dk-env/uart-checksum.c`, bật bằng `UART_CHECKSUM=1`, mặc định).
Gateway và `tools/analyze_logs.py` bỏ dòng sai checksum và đếm riêng (`uart_checksum.bad` trong
results.json). Nhờ vậy **mất do UART không bị tính thành mất gói radio**. Tắt: `--set UART_CHECKSUM=0`.
Đã build thử HOST/RELAY/SOURCE bằng arm-none-eabi-gcc 13.2 và chạy `tools/check.py` (PASS);
chưa chạy trên kit.

**Build cho 5 kit (demo dashboard + đo, cùng một RUN_ID):**

```bash
# Demo liên tục: 2000 gói x 5 s ≈ 2,8 giờ (giới hạn tối đa của firmware)
for n in 2 3 4 5; do
  python3 tools/build_node.py --contiki ~/contiki --node $n --role SOURCE --host 1 \
    --sources 2:3:4:5 --run 501 --packets 2000 --ipi 5 --out ~/lwb-build
done
python3 tools/build_node.py --contiki ~/contiki --node 1 --role HOST --host 1 \
  --sources 2:3:4:5 --run 501 --packets 2000 --ipi 5 --out ~/lwb-build
```

- HOST mặc định không đọc cảm biến (`HOST_LOCAL_SENSOR=0`). Khi chạy demo dashboard, thêm `--set HOST_LOCAL_SENSOR=1` vào lệnh build HOST để Node 01 hiện nhiệt độ/độ ẩm. Khi đo range/multi-hop chính thức thì giữ 0 để HOST không chạy I2C.
- `--sources` phải liệt kê **mọi** SOURCE, nếu không HOST từ chối node đó (`PERF_ERR,bad_identity`).
- Bật gateway (Pi) **trước**, rồi mới reset HOST, để không mất dòng `PERF_CONFIG` lúc khởi động.
- Đo multi-hop: đổi 1 kit thành `--role RELAY` (node đó **không** nằm trong `--sources`), xem mục 7.
- RELAY không gửi dữ liệu nên không xuất hiện trên dashboard; xem nó qua UART riêng của kit đó.


Bản này sửa trên `lwb-cc2538dk(6).rar`, dùng cây Contiki được ghép từ
`Contiki os.rar` và `contiki-bo-sung.tar.gz` bạn cung cấp. Ứng dụng chính là
`apps/lwb-cc2538dk-env`; một bộ source tạo firmware HOST, SOURCE hoặc RELAY bằng build.

Đã kiểm tra biên dịch; chưa chạy trên kit hoặc đo RF ngoài thực địa. Xem
`VALIDATION.md` để phân biệt việc đã kiểm tra với việc cần xác nhận trên phần cứng.
Đây là quy trình đo có đối chứng cho port hiện tại, không phải một chứng nhận
“test chuẩn” áp dụng cho mọi phần cứng hay bản tái hiện toàn bộ kết quả bài báo LWB.

## 1. HOST / SOURCE / RELAY có nghĩa gì?

LWB trao đổi bằng các flood Glossy theo lịch. Những node tham gia flood có thể
chuyển tiếp tín hiệu đồng bộ và DATA. Không có route cố định, next-hop hay bảng
định tuyến trong ứng dụng này. `RELAY` là lựa chọn của ứng dụng: chạy LWB non-host,
tham gia flood, nhưng không xin stream và không sinh dữ liệu cảm biến.
SOURCE cũng tham gia chuyển tiếp flood của node khác.

| Vai trò build | Giá trị `ROLE` | Hành vi |
|---|---:|---|
| HOST | 1 | Phát schedule, nhận DATA, in thống kê từng source dự kiến |
| SOURCE | 2 | Đọc sensor, xin stream, tạo N lượt dữ liệu với chu kỳ IPI |
| RELAY | 3 | Tham gia flood; không đọc sensor/OLED, không phát DATA riêng |
| AUTO, tương thích | 0 | `NODEID == HOST_ID` là HOST, còn lại là SOURCE |

Trong bài đo ba kit: HOST=1, RELAY=2, SOURCE=3, `SOURCE_IDS=3` trên cả ba.
Gói gửi đích HOST vẫn được flood qua các node; lọc địa chỉ sau flood không ngăn
một node trở thành relay. Việc chỉ bỏ gói trong callback không tạo ra topology RF.

Port giữ scheduler tĩnh vòng 5 giây, không triển khai scheduler thích nghi của
bài báo gốc. Phạm vi kết luận phù hợp: “đánh giá port LWB/Glossy này trên bộ kit
CC2538 + CC2592 với cấu hình đã ghi lại”.

## 2. Chuẩn bị cây Contiki và chép source

Giải nén bản này vào một thư mục mới để giữ bản cũ đối chiếu. Ví dụ đặt thư mục
`lwb-cc2538dk` tại `~/contiki/examples/lwb-cc2538dk-unified/`. Không chép đè cả cây
Contiki bằng thư mục project này.

Cây Contiki cần có ít nhất:

```text
Makefile.include
core/
platform/cc2538dk/
cpu/cc2538/
cpu/arm/common/
cpu/cc253x/usb/common/
lib/newlib/
tools/
```

Trong archive Contiki bạn gửi, thư mục `cc2538` nằm ở root; tại cây dùng để build
nó phải là `cpu/cc2538`. Bản bổ sung vừa gửi cung cấp hai thư mục `cpu/arm/common`
và `cpu/cc253x/usb/common`. Nếu máy bạn đã có đúng cây `~/contiki`, dùng cây đó.

Chạy tại thư mục project:

```bash
python3 tools/apply_contiki_fixes.py ~/contiki
arm-none-eabi-gcc --version
```

Script chỉ sửa hai chỗ đã phát hiện trong port được cung cấp:

| File Contiki | Sửa |
|---|---|
| `cpu/cc2538/rtimer-arch.h` | `32768S` → `32768UL`: hậu tố cũ không hợp lệ |
| `cpu/cc2538/cc2538.lds` | `FLASH_FW= 0` → `FLASH_FW = 0`: khoảng trắng để linker mới phân tích đúng |

Hai patch văn bản tương ứng nằm trong `contiki-patches/`. Script có thể chạy lại.
Nếu nó báo cây port khác, đọc chỗ khác biệt trước khi áp dụng thủ công.

## 3. Build ba firmware

Nên dùng script dưới đây: mỗi lần build dùng một bản sao tạm sạch để tránh
object cũ giữ `NODEID`, vai trò hoặc cấu hình của lần build trước. Script không nạp kit.
Chạy từ root project:

```bash
python3 tools/build_node.py --contiki ~/contiki --node 1 --role HOST \
  --host 1 --sources 3 --run 301 --packets 100 --ipi 5 --out ~/lwb-build

python3 tools/build_node.py --contiki ~/contiki --node 2 --role RELAY \
  --host 1 --sources 3 --run 301 --packets 100 --ipi 5 --out ~/lwb-build

python3 tools/build_node.py --contiki ~/contiki --node 3 --role SOURCE \
  --host 1 --sources 3 --run 301 --packets 100 --ipi 5 --out ~/lwb-build
```

Kết quả là ba thư mục `run-301_node-1_host`, `run-301_node-2_relay`,
`run-301_node-3_source`, mỗi thư mục có `firmware.elf`, `.hex`, `.bin`, build log,
map và manifest chứa cấu hình, phiên bản compiler, hash source và firmware.
Nạp đúng file cho từng kit bằng công cụ nạp bạn đang dùng. `firmware.bin` cần
địa chỉ nạp theo quy trình CC2538 của bạn; `.hex` đã mang địa chỉ. Không tự đổi
flash layout chỉ dựa vào kích thước file `.bin`.

`RUN_ID` phải giống nhau trên các node trong một lượt. Đổi RUN_ID cho lượt mới,
sau bất kỳ reboot/mất điện nào hoặc sau khi đổi topology/cấu hình. Bản này không
tự tiếp tục một bài đo qua reboot. Không ghép các file log có cùng RUN_ID từ hai lượt khác nhau.

Nếu build trực tiếp bằng make, từ `apps/lwb-cc2538dk-env`:

```bash
make clean TARGET=cc2538dk CONTIKI="$HOME/contiki"
make TARGET=cc2538dk CONTIKI="$HOME/contiki" NODEID=3 ROLE=2 HOST_ID=1 \
  SOURCE_IDS=3 RUN_ID=301 PACKETS=100 IPI=5
```

Luôn clean trước khi đổi tham số. Khuyến nghị script `build_node.py` vì bản
Contiki cũ không tự theo dõi mọi thay đổi của cờ compiler.

### Tham số thường dùng

| Make variable | Mặc định | Ý nghĩa |
|---|---:|---|
| `PACKETS` | 100 | Số lượt tạo dữ liệu theo lịch, 1..2000; dùng 100 để chạy thử. `0` = chế độ liên tục (xem mục "Cập nhật 15/11") |
| `RADIO_STATS`, `RADIO_STATS_PERIOD` | 0, 12 | Đo radio duty cycle bằng phần mềm (`PERF_RADIO`); xem `docs/RADIO_STATS_NOTES.md` |
| `GEN_MODE`, `GEN_LEAD_MS`, `SENSOR_BUDGET_MS`, `FRESH_ONLY`, `REPORT_EVERY` | 0, 250, 150, `GEN_MODE`, 60 | Đồng bộ pha tạo gói / chống dồn hàng đợi / REPORT liên tục; xem mục "Cập nhật 15/11" |
| `IPI` | 5 | Giây giữa hai lượt; 5..3600, bội số của 5 với scheduler hiện tại |
| `SOURCE_IDS` | 2 | Danh sách nguồn dự kiến, ví dụ `3` hoặc `3:4:5` |
| `MAX_NODE_ID` | 6 | Giới hạn ID dùng cấp phát thống kê; tối đa 32, phải kiểm tra RAM khi tăng |
| `CHANNEL` | 26 | Kênh radio, tất cả node phải giống nhau |
| `TX_POWER_DBM` | 7 | Mức drive CC2538 đưa vào CC2592; không phải EIRP tại anten |
| `N_SYNC`, `N_DATA_TX` | 3, 3 | Giới hạn phát Glossy cho schedule và các slot DATA/điều khiển RR |
| `DATA_BUFFERS` | 16 | Pool chung TX/RX của LWB; không phải 16 slot cho mỗi hướng |
| `START_DELAY` | 20 | Thời gian chờ tối thiểu trước đo, tính từ clock uptime của ứng dụng |
| `JOIN_TIMEOUT` | 120 | Nếu chưa có sync/stream/slot thì ghi `PERF_ABORT` |
| `REPORT_WAIT` | 15 | Chờ tối thiểu sau lượt cuối trước khi chốt nếu queue đã rỗng |
| `DRAIN_TIMEOUT` | 60 | Hết thời gian này chốt lượt, bỏ DATA còn trong queue và ghi số bỏ |
| `REPORT_REPEAT` | 3 | Số bản REPORT cuối được đưa vào queue, không có ACK cho REPORT |
| `SAMPLE_PERIOD` | 1 | Chu kỳ yêu cầu đọc sensor; chỉ đọc khi có khoảng rảnh đủ dài |
| `OLED` | 1 | OLED ở SOURCE; dùng 0 để kiểm tra ảnh hưởng giao diện |
| `HOST_LOCAL_SENSOR` | 0 | Nếu 1, HOST in `LOCAL`; không tính vào bài đo source |
| `TEMP_RH_SENSOR` | 0 | 0=auto theo driver cũ, 1=SI7021, 2=HDC1080 |
| `I2C_SCL`, `I2C_SDA` | 3, 4 | SW-I2C PB3/PB4 của source gốc |
| `USE_TEMP_RH`, `USE_LIGHT`, `USE_BMP` | 1 | Bật nhóm sensor tương ứng |

Với script build, truyền tùy chọn qua `--set OLED=0 --set TEMP_RH_SENSOR=2`, v.v.
Mức `TX_POWER_DBM` phải thuộc bảng drive của port: 7, 5, 3, 1, 0, -1, -3, -5,
-7, -9, -11, -13, -15 hoặc -24. Không dùng một số tùy ý rồi cho rằng radio đã
phát đúng mức đó. Mức tại anten sau CC2592 cần đo/hiệu chuẩn riêng.
Giữ các tham số radio, sensor, OLED, buffer, tải và compiler cố định khi so sánh
khoảng cách/topology. Thay một yếu tố trong mỗi phép so sánh.

Mapping CC2592 kế thừa source được gửi: PA_EN=PC3, LNA_EN=PC2, HGM=PD2.
Đối chiếu kit trước khi nạp. Không bật `LWB_DEBUG_GPIO` hiện tại nếu chưa đổi mapping:
pin debug PD2 trùng HGM. Không bật GPIO debug Glossy tùy tiện trên các chân I2C/UART.

## 4. Dữ liệu và cách đếm

Wire protocol mới `env_perf_v1` có DATA/REPORT cùng kích thước application payload
28 byte. Tất cả node phải dùng bản này; không trộn ứng dụng ENV cũ.
`env_packet_t` cũ thực tế 18 byte, nay chỉ dùng nội bộ cho sensor/OLED.
28 byte không phải toàn bộ frame radio: header Glossy/LWB, FCS và piggyback điều
khiển vẫn làm tăng kích thước trên không.

SOURCE chờ ít nhất hai callback round có trạng thái SYNCED liên tiếp, đã được
nhận stream và có slot, rồi mới bắt đầu lịch tạo dữ liệu. Mỗi lượt lấy mẫu sensor
mới nhất đã đọc được. `sensor_mask`: bit0=temp/RH, bit1=light, bit2=BMP180.
Giá trị invalid dùng sentinel của driver cũ; light là raw, không suy diễn thành lux.
Ngay cả khi mọi sensor lỗi, DATA vẫn được tạo với mask=0 để lỗi sensor không
làm thay đổi tải mạng. Thời gian đo bắt đầu tại enqueue, không phải lúc sensor đo.

| Counter | Định nghĩa |
|---|---|
| `generated` | Số lượt tạo theo lịch đã đi qua, gồm cả lượt bị bỏ vì xử lý muộn |
| `deadline_missed` | Lượt bỏ do process không chạy kịp; không dồn phát bù thành burst |
| `queued` | Số DATA được `lwb_queue_packet()` chấp nhận |
| `queue_failed` | DATA thử enqueue một lần nhưng thất bại |
| `tx_started` | Số DATA riêng biệt mà `glossy_start` thành công và có ít nhất một TX kết thúc tại radio |
| `tx_start_failed` | DATA đã lấy khỏi queue nhưng không đạt điều kiện TX trên |
| `discarded` | DATA còn trong queue bị bỏ khi hết drain timeout |
| `received_unique` | Số `(RUN_ID, source, seq)` riêng biệt HOST đưa lên callback |

Các quan hệ khi chốt source:

```text
generated = queued + queue_failed + deadline_missed = PACKETS
queued = tx_started + tx_start_failed + discarded
```

Không có application ACK hay phát lại DATA theo seq. Những lần phát lặp trong
một flood Glossy vẫn giữ nguyên theo `N_DATA_TX`; LWB vẫn có stream request/ACK.
REPORT gửi sau khi chốt, có thể mất như DATA và không tính vào số DATA.

Các tỷ lệ được đặt tên riêng:

| Chỉ số | Công thức |
|---|---|
| Application yield | unique nhận / generated |
| Enqueue delivery | unique nhận / queued |
| Flood delivery | unique nhận / tx_started |
| Planned receipt | unique nhận / PACKETS, chỉ chốt khi có bằng chứng lượt đã kết thúc |

Không gọi tất cả các tỷ lệ này chung là PRR. Flood delivery ở đây tính đến đường
nhận lên ứng dụng, nên còn bao gồm mất do RX queue/phần mềm; chưa tách riêng
xác suất thu RF thuần túy. Không dùng `max(seq)` làm mẫu số: mất gói cuối lượt
sẽ khiến cách đó báo tỷ lệ cao sai lệch. Mẫu số 0 hoặc chưa biết được xuất `null`.

### Delay

`delay_ticks = HOST_rx_slot_end_network_ticks - SOURCE_enqueue_network_ticks`
theo modulo 2^32, với RTIMER=32768 Hz. Một tick khoảng 30,52 microsecond chỉ là
độ phân giải danh nghĩa, không phải độ chính xác đồng bộ đã được đo.
Metadata HOST được chụp khi xử lý slot kết thúc rồi giữ cùng gói trong RX queue;
không lấy thời điểm printf/callback làm lúc nhận.

Delay này gồm thời gian chờ queue/lịch và đến cuối slot, không phải thời gian
truyền RF thuần túy, không phải timestamp SFD đầu tiên, không gồm tuổi mẫu sensor.
Chỉ dùng delay khi SOURCE tại enqueue và HOST tại slot có timebase hợp lệ; giá trị
âm biểu diễn qua wrap, quá `MAX_DELAY_S=120` hoặc mất validity bị loại. Số 0 là
delay hợp lệ nếu các cờ validity hợp lệ. `delay_count` có thể nhỏ hơn received.
P95 tính nearest-rank trên các DATA unique có delay hợp lệ.

### Relay counter và số hop

Đã sửa getter Glossy: trước đây nó đọc biến phục vụ time-reference, chỉ được cập
nhật khi bật đồng bộ. DATA dùng `GLOSSY_ONLY_RELAY_CNT` nên có thể luôn báo 0.
Getter mới lưu relay counter của RX hợp lệ đầu tiên ở cả DATA và schedule.

`relay_cnt` là raw counter trong flood; `hop_est=relay_cnt+1` là chỉ dấu lan truyền
của flood. Một link trực tiếp có thể được nhận muộn qua lần lặp và cho counter
lớn hơn 0. Counter không cho biết route, node nào chuyển tiếp, hay số hop vật lý
ngắn nhất. Analyzer cố ý không tự kết luận `multihop_proven`.

## 5. Thu log và phân tích

UART 115200, 8N1. Dùng một máy thu đồng thời HOST và SOURCE, mở log trước khi reset
các kit. Không mở terminal khác giữ cùng cổng. Ví dụ đổi cổng theo máy bạn:

```bash
python3 tools/capture_uart.py --port 1=/dev/ttyUSB0 --port 3=/dev/ttyUSB1 \
  --out ~/lwb-logs/run-301 --seconds 1200
```

Với 100 gói, IPI 5 giây, chạy khoảng 8 phút 15 giây từ lượt đầu đến lượt cuối,
cộng thời gian join, drain và REPORT. Với 1000 gói cần khoảng 83 phút 15 giây
chỉ riêng phần tạo dữ liệu; tăng `--seconds`, ví dụ 6000. Có thể Ctrl-C sau khi
các source đã có `PERF_SOURCE_SUMMARY`, gửi REPORT và HOST đã in summary cập nhật.
RELAY không có DATA/REPORT riêng; có thể thu thêm UART của nó để lưu cấu hình.

```bash
python3 tools/analyze_logs.py --host ~/lwb-logs/run-301/node-1.log \
  --source ~/lwb-logs/run-301/node-3.log --sources 3 --run 301 \
  --out ~/lwb-logs/run-301/results.json
```

Sinh JSON và CSV, mỗi run/source một dòng. Nếu REPORT mất nhưng log SOURCE có
summary cuối, analyzer dùng mẫu số từ SOURCE UART. Với log thu chung bằng script,
`capture.json` giúp xác nhận HOST và SOURCE được thu cùng cửa sổ thời gian.
Nếu dùng terminal/logger riêng, chỉ thêm `--capture-complete` sau khi bạn đã xác
nhận log HOST bắt đầu trước bài đo và kéo dài qua lúc SOURCE chốt lượt.
Nếu chưa có bằng chứng đó, analyzer để tỷ lệ unavailable và ghi issue; việc
HOST logger dừng sớm không được tự biến thành mất gói RF.

Trạng thái kết quả:

| Status | Ý nghĩa |
|---|---|
| `final` | Có bộ đếm cuối và không phát hiện mâu thuẫn/cửa sổ thu thiếu |
| `join_failed` | SOURCE có log join timeout; không có mẫu số DATA phát để tính flood delivery |
| `incomplete` | Chưa có bộ đếm cuối; vẫn xuất số gói đã thấy |
| `invalid` | Reboot lặp RUN_ID, cấu hình lệch, bộ đếm mâu thuẫn hoặc thiếu bằng chứng thu đầy đủ |

`final` không phải bảo đảm logger không mất byte hay RF đúng: vẫn cần kiểm tra
log nguyên bản và phần cứng. Nguồn dự kiến nhận 0 gói vẫn có dòng kết quả.
Nguồn không xuất hiện trong `SOURCE_IDS` bị HOST từ chối để tránh trộn bài đo.
Wilson 95% được cung cấp như khoảng tham khảo của tỷ lệ nhị thức; khi loss có
tương quan thời gian, không dùng nó thay cho độ biến thiên giữa các lượt độc lập.

## 6. Range test một hop

1. Chỉ bật HOST và một SOURCE. Tắt toàn bộ node LWB khác, kể cả kit nằm gần bàn
   thử. Giữ nguyên anten, hướng, độ cao, nguồn cấp, kênh, drive, sensor/OLED và tải.
2. Chạy 100 gói gần nhau để kiểm tra join, sensor mask, counter và log. Chưa dùng
   lượt kiểm tra này để kết luận tầm xa.
3. Chọn trước các mốc khoảng cách, môi trường LOS/NLOS và tiêu chí cần đạt, ví dụ
   flood delivery >=95% cùng yêu cầu join. 95% là tiêu chí của đề tài, không phải
   một ngưỡng LWB bắt buộc. Ghi cả khoảng tin cậy và dữ liệu từng lượt.
4. Ở mỗi mốc, dùng RUN_ID mới, cold-start đúng thứ tự đã quy định, N và IPI như
   nhau. Gợi ý khảo sát chính 1000 lượt/source và ít nhất 5 lần lặp độc lập nếu
   thời gian cho phép; quyết định cỡ mẫu theo độ chính xác và thời lượng bạn cần.
5. Ghi nhận cả những lượt không join được. Báo riêng xác suất join và tỷ lệ
   delivery của các lượt đã phát; không loại join failure rồi gọi phần còn lại
   là toàn bộ độ tin cậy của giao thức.
6. Đổi thứ tự mốc hoặc đo lặp chiều đi/chiều về để giảm ảnh hưởng nhiễu thay đổi
   theo giờ. Ghi vị trí, khoảng cách đo được, điều kiện, vật cản và nguồn nhiễu.

Đây là range vận hành LWB hai chiều: SOURCE phải nhận schedule và đăng ký stream
trước khi DATA về HOST. Nó không thay thế phép đo độ nhạy thu hay link PDR một
chiều ở tầng RF. Không ước tính khoảng cách từ RSSI hoặc chỉ báo OLED.

## 7. Multi-hop test có đối chứng

Với ba kit, mục tiêu là có liên kết HOST↔RELAY và RELAY↔SOURCE, trong khi liên kết
HOST↔SOURCE bị suy hao đủ lớn hoặc được cô lập vật lý. Ưu tiên topology RF có
thể kiểm soát bằng che chắn/attenuator phù hợp nếu phần cứng cho phép; bố trí
ngoài trời chỉ cung cấp bằng chứng theo điều kiện đã ghi, không chứng minh loại
bỏ mọi đường trực tiếp.

| Lượt | Node hoạt động | Mục đích |
|---|---|---|
| Kiểm tra từng cạnh | Một HOST và một SOURCE tạm ở vị trí hai đầu cạnh | Xác nhận từng link kế cận hoạt động, sau đó khôi phục đúng firmware ba vai trò |
| A: relay OFF | HOST 1 + SOURCE 3 | Đo đường trực tiếp và khả năng cold-start không có relay |
| B: relay ON | HOST 1 + RELAY 2 + SOURCE 3 | Đo hiệu năng khi có node chuyển tiếp |
| C: thử sự cố, lượt riêng | Cả ba; tắt/bật RELAY trong lúc SOURCE đang đo | Quan sát mất sync, queue failure và khôi phục; không trộn với baseline ổn định |

Cho A và B có cùng N, IPI, tham số radio, nguồn/anten, sensor và vị trí. Dùng RUN_ID
riêng cho mỗi lượt, lặp nhiều lần và đảo thứ tự A/B. Nếu A không join thì báo
join_failed; không giả lập mẫu số 1000 gói đã phát. Nếu A vẫn delivery tốt thì
topology chưa buộc truyền qua relay, dù B có `hop_est > 1`.

Bằng chứng thuyết phục gồm kiểm chứng RF của topology, kết quả từng cạnh,
relay OFF/ON lặp lại, loss/join theo run và relay counter hỗ trợ. Không sửa ứng
dụng bỏ packet SOURCE tại HOST để “ép hop”: Glossy đã relay trước callback.
Không viết forwarding tầng ứng dụng hay thêm ACK/retry để thay cơ chế Glossy.
Với nhiều relay, cùng nguyên tắc nhưng phải loại các đường RF tắt không mong muốn.

Mẫu biểu ghi thí nghiệm nằm trong `experiments/`. Các file mẫu trống; không có
dữ liệu đo thực được tạo sẵn trong gói này.

## 8. Kiểm tra trên kit trước khảo sát chính

Chạy lần lượt: hai kit gần nhau → có sensor lỗi/ngắt sensor → ba kit gần nhau →
topology có đối chứng. Xác nhận `PERF_CONFIG` đúng node/role/run, Source phát đủ
N lượt, quan hệ counters đúng, REPORT có thể đối chiếu UART và DATA có sensor thật.
Thử dừng HOST giữa lượt để kiểm tra drain timeout và việc queue failure vẫn được
đếm. Dùng run riêng cho từng tình huống.

I2C/OLED chạy ngoài round khi còn ít nhất 700 ms đến round kế tiếp, dựa trên dự
toán các driver hiện có. Đây chưa phải WCET đo được. Cần kiểm tra bằng logic
analyzer/oscilloscope trên kit: thời gian đọc sensor/OLED, SFD, tín hiệu PA/LNA,
sync và slot timing. So sánh OLED=0/1 để phát hiện ảnh hưởng giao diện; không thay
đổi tùy ý giữa các lượt chính. ISR radio không in UART và không gọi I2C.

Độ phân giải timer và một lần build thành công không chứng minh độ chính xác
delay, constructive interference hay độ tin cậy RF. Gói này chưa xuất năng lượng,
RSSI/LQI hoặc jitter SFD đã được kiểm chứng. Để đánh giá năng lượng CC2592, cần
đo dòng/điện áp thực, không chuyển ENERGEST thành mJ bằng dòng danh nghĩa chưa đo.

## 9. RTC, pin CR2032 và mất điện

CR2032 riêng có thể duy trì RTC khi mất nguồn chính nếu mạch backup và RTC đang
hoạt động đúng. Nó không tự lưu RAM của CC2538, queue LWB hoặc toàn bộ mẫu sensor.
`node_id_burn()` của port này chỉ gán RAM, không phải ghi flash; NODEID được khôi
phục từ cấu hình build khi khởi động.

Bản này chưa tích hợp RTC hoặc lưu log bền vững trên kit: `rtc_integrated=0`.
Không đoán model chip hoặc bus RTC từ việc có CR2032. Cần xác nhận mã chip và
sơ đồ nối để viết driver và kiểm tra cờ thời gian hợp lệ sau mất nguồn.
RTC phù hợp để gắn ngày giờ tuyệt đối; phép đo delay giữa node vẫn dùng thời
gian mạng Glossy/LWB. Không dùng phép trừ đồng hồ RTC độc lập để đo delay ngắn.

Nếu cần lưu sensor qua mất điện, bước tiếp theo là log flash/FRAM/SD có record
version, CRC và cơ chế commit; đặt ngoài khoảng radio. Dữ liệu phát lại sau reboot
phải có dấu replay và ID phiên riêng, tránh trộn vào phép đo delivery trực tiếp.
Hiện tại log đã thu trên máy tính được giữ lại; bài đo trên kit phải chạy lại với
RUN_ID mới sau mất điện.

## 10. File đã sửa và tham khảo

| Nhóm | Thay đổi chính |
|---|---|
| Ứng dụng ENV | Vai trò build, sensor + test trong cùng app, tải hữu hạn, REPORT, log |
| `env-perf-packet.h`, `env-perf-stats.h` | Wire format 28 B, bitmap unique, wrap-aware delay, thống kê |
| `glossy.c/.h` | Counter RX đầu của DATA; getter TX kết thúc để đếm flood đã phát |
| `lwb-g-rr.c` | Metadata gắn từng RX, observer sau TX, bounds cho DATA/piggyback, purge queue |
| `lwb.c/.h`, `lwb-common.h` | API validity/background/metadata và trường context |
| `lwb-g-sync.c`, codec | Kiểm tra schedule, giải nén thành công cả lịch rỗng và có DATA |
| Scheduler, macros | Ghi nhận slot index 0; kiểm tra đúng bit poll flag |
| Makefiles/config | Build roles/ID/run/radio/sensor, giữ null NETSTACK cho LWB |
| `tools/`, `tests/` | Build sạch, thu UART, phân tích và kiểm tra tự động |

`changes-from-v6.patch` giúp xem khác biệt phần C/header/config so với source gốc.
Các example `lwb-test`/`glossy-test` được giữ để tham khảo, không nằm trong ma trận
kiểm tra của ứng dụng thống nhất. Ba README ENV cũ có mô tả kích thước/đếm không
còn đúng đã được thay bằng tài liệu này.

Nguồn gốc cơ chế: Ferrari và cộng sự, *Low-Power Wireless Bus*, SenSys 2012,
https://patpannuto.com/papers/ferrari2012lwb.pdf ; luận án Ferrari,
https://pub.tik.ee.ethz.ch/people/thiele/paper/diss_ferrari.pdf .
Các quy ước counter, kích thước payload và scheduler trong tài liệu này được
đối chiếu trực tiếp với port được cung cấp; không suy ra chúng từ tên bài báo.
