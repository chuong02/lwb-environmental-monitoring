# Kiểm tra thực hiện cho bản giao này

Phạm vi: source thống nhất tại `apps/lwb-cc2538dk-env`, core LWB/Glossy đi kèm,
cây Contiki được ghép từ các archive người dùng cung cấp, và hai sửa đổi nhỏ tại
`contiki-patches/`. Không dùng phần cứng CC2538 trong môi trường kiểm tra này.

## Biên dịch thật, không chỉ make dry-run

Compiler chính khớp output người dùng đã gửi:

```text
arm-none-eabi-gcc (15:4.9.3+svn231177-1) 4.9.3 20150529 (prerelease)
```

Mỗi cấu hình dưới đây được build từ bản sao tạm sạch bằng `tools/build_node.py`.
Tất cả dùng HOST_ID=1, SOURCE_IDS=3, RUN_ID=301, IPI=5; mặc định OLED=1,
TX_POWER_DBM=7, CHANNEL=26, N_SYNC=3, N_DATA_TX=3, DATA_BUFFERS=16.

| Compiler | Vai trò / NODEID | PACKETS | Khác mặc định | Kết quả | text | data | bss |
|---|---|---:|---|---|---:|---:|---:|
| GCC 4.9.3 | HOST / 1 | 100 | Không | PASS, 0 compiler warning | 39239 | 208 | 11605 |
| GCC 4.9.3 | SOURCE / 3 | 100 | Không | PASS, 0 compiler warning | 39243 | 208 | 11605 |
| GCC 4.9.3 | RELAY / 2 | 100 | Không | PASS, 0 compiler warning | 39243 | 208 | 11605 |
| GCC 4.9.3 | SOURCE / 3 | 1000 | OLED=0, drive=-3 | PASS, 0 compiler warning | 37457 | 208 | 11477 |
| GCC 14.2.1 | HOST / 1 | 100 | Không | PASS, 30 compiler warning trong mã Contiki cũ | 37967 | 208 | 11597 |

`text/data/bss` là byte từ GNU `size`; không phải đo stack high-water mark,
năng lượng hay dung lượng flash thực tế của từng kit. OLED=0 bỏ framebuffer nên
cấu hình 1000 gói có thể dùng ít RAM hơn cấu hình OLED=1 dù bitmap lớn hơn.

GCC 14.2.1 dùng để kiểm tra thêm tính tương thích, không thay compiler chính.
Cảnh báo của nó tập trung ở truy cập bảng ROM của CC2538 và `const` lặp trong
USB legacy; chúng được giữ trong log, chưa được chứng minh là vô hại trên kit.
Makefile Contiki khi thiếu `.git` có thể in lỗi tra phiên bản git, nhưng các lệnh
compile/link/objcopy trong ma trận đã trả exit code 0.

Build log và manifest tương ứng nằm trong `validation/builds/`. Manifest ghi
tham số, compiler và SHA-256 các file C/header/Makefile đã dùng; không có kết quả
RF thực trong các file này. Firmware biên dịch thử không được phát hành như một
binary đã kiểm tra trên board; hãy build source với đúng cấu hình kit của bạn.

## Kiểm tra logic trên máy

Chạy lại tại root project:

```bash
python3 tools/check.py --contiki ~/contiki
```

Yêu cầu Python 3, host C compiler và thư viện sanitizer của host. Script chạy:

1. 11 test Python cho analyzer: mất gói cuối, mẫu số chưa biết, REPORT mất nhưng
   có SOURCE UART, kiểm tra cửa sổ log, source nhận 0, duplicate/out-of-order,
   queue failure, deadline miss, reboot trùng RUN_ID, bộ đếm mâu thuẫn, log thiếu,
   delay invalid, join timeout và cấu trúc key/value.
2. Test C dùng đúng `env-perf-packet.h`, `env-perf-stats.h`, codec và scheduler
   của bản giao, cùng `list.c`/`memb.c` của Contiki. Kiểm tra payload 28 B, số 0 và
   wrap của timestamp, bitmap, duplicate, out-of-order, tổng delay vượt 32 bit,
   schedule rỗng/1/2/17/40 slot, node ID 16 bit, lịch bị cắt/bitwidth sai,
   thu hồi stream khi slot index 0 mất liên tục, reset missed counter khi có DATA,
   và phép kiểm tra đúng từng bit poll flag.
3. AddressSanitizer + UndefinedBehaviorSanitizer cho test C. LeakSanitizer tắt
   vì môi trường chạy có tracing; các module được test dùng pool tĩnh.

Cả hai nhóm đã PASS. Python scripts cũng đã được `py_compile` thành công.
CLI analyzer đã được chạy với log **tổng hợp dành riêng cho test** và kiểm tra
JSON/CSV, không được coi là dữ liệu thí nghiệm vô tuyến.

Stub trong `tests/stubs/` chỉ cung cấp kiểu timer/enum và cấu hình tối thiểu
cho phép compile trên host. Nó không mô phỏng radio, rtimer interrupt, I2C,
quá trình đồng bộ Glossy hay toàn bộ event loop của firmware.

## Những việc chưa thể xác nhận tại đây

- Nạp, boot và hoạt động thực trên các kit; model cảm biến và mapping chân thực.
- Timing ISR/SFD, chuyển PA/LNA của CC2592 và đồng bộ trên RF.
- Độ chính xác delay hoặc giá trị relay counter trên topology thực tế.
- Tính đầy đủ UART ngoài thực địa, I2C/OLED WCET và stack high-water mark.
- Delivery/range/multi-hop, năng lượng và ảnh hưởng nhiễu môi trường.
- RTC, thời gian tuyệt đối, duy trì RAM/log hoặc khôi phục test qua mất điện.

Thứ tự chạy trên kit, định nghĩa chỉ số và các phép đối chứng ở `README_VI.md`.
Không có số liệu range, PRR hay chứng nhận multi-hop nào được suy ra từ build/test
logic trong tài liệu này.
