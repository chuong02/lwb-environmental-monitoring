# LWB Gateway starter for CC2538 + Raspberry Pi 3

## Cập nhật 12/11/2026 (đọc trước)

1. **Checksum UART.** Firmware mới (`UART_CHECKSUM=1`, mặc định) thêm `*HH` (XOR) vào cuối mỗi dòng.
   `lwb_gateway.py` kiểm tra lại: dòng hỏng được lưu với `record_type='UART_BAD'`, `published=3`,
   **không** gửi lên cloud. Mỗi 60 s log `UART lines ... ok=.. bad=..` (xem bằng journalctl).
   Dòng không có checksum (firmware cũ) chỉ được nhận nếu đúng cấu trúc.
2. **Publisher nhanh hơn.** Gửi cả lô 50 bản tin rồi chờ PUBACK; **ưu tiên dữ liệu mới nhất**;
   gửi thêm `PERF_*` lên `.../nodes/<id>/perf`; mỗi 15 s gửi trạng thái gateway (retained)
   lên `.../gateway/<GATEWAY_ID>/status` (tỷ lệ dòng UART lỗi, số bản tin tồn).
   Bản ghi cũ hơn `PUBLISH_MAX_AGE_HOURS` (24 h) không gửi nữa (`published=2`) nhưng vẫn nằm trong SQLite.
3. **Kiểm tra lỗi UART trên Pi trước khi đo:**
   ```bash
   vcgencmd get_throttled            # phải là throttled=0x0, khác 0 = thiếu áp nguồn
   sudo lsof /dev/ttyUSB0            # chỉ được có 1 tiến trình python (lwb_gateway)
   systemctl is-active ModemManager  # nếu "active": sudo systemctl disable --now ModemManager
   ```
4. **Xem SQLite trên Pi bằng trình duyệt (Datasette):**
   ```bash
   /opt/lwb-gateway/.venv/bin/pip install datasette
   sudo cp datasette-metadata.json /opt/lwb-gateway/
   sudo cp lwb-datasette.service /etc/systemd/system/
   sudo systemctl daemon-reload && sudo systemctl enable --now lwb-datasette
   ```
   Mở `http://<IP-Pi-hoặc-Tailscale>:8001` → có sẵn các truy vấn: chất lượng UART, node mới nhất,
   PERF_SUMMARY run mới nhất, backlog MQTT.
5. **Thử không cần kit:** `python3 simulate_host.py --pty` tạo cổng serial giả (dữ liệu GIẢ LẬP,
   chỉ để kiểm tra phần mềm, không dùng làm kết quả đo).
6. **Cập nhật file lên Pi:** copy `lwb_gateway.py`, `mqtt_publisher.py` vào `/opt/lwb-gateway/`, thêm các
   biến mới trong `gateway.env.example` vào `/etc/lwb-gateway/gateway.env`, rồi
   `sudo systemctl restart lwb-gateway lwb-mqtt`.
7. **Xuất một run để phân tích: `export_run.py`** (chỉ dùng thư viện chuẩn, đọc DB ở chế độ chỉ-đọc nên
   chạy được khi gateway đang chạy):
   ```bash
   python3 export_run.py --run 501 --out ~/run501            # --db mặc định /var/lib/lwb-gateway/lwb.db
   ```
   - `host-run501.log`: cột `raw_line` của run (bỏ `UART_BAD`), theo thứ tự `id`, giữ nguyên `*HH`
     để `analyze_logs.py` tự kiểm lại checksum.
   - `uart-quality.json`: số dòng `ok` / `legacy` (không checksum) / `bad` (`UART_BAD`) và `bad_pct`,
     tính trong khoảng `recv_ts_utc` từ dòng đầu đến dòng cuối của run.
   - Cuối cùng script in sẵn lệnh phân tích, danh sách `--sources` lấy từ các dòng `PERF_SUMMARY`:
     ```bash
     python3 lwb-cc2538dk/tools/analyze_logs.py --host ~/run501/host-run501.log \
       --sources 2:3:4 --run 501 --capture-complete --out ~/run501/results.json
     ```
   - `--capture-complete` chỉ được thêm vào lệnh in ra khi kiểm tra capture đạt:
     (a) có dòng `PERF_CONFIG` đứng trước `SENSOR_DATA` đầu tiên của run (nếu có `SENSOR_DATA`);
     (b) với mỗi source, khoảng cách `recv_ts_utc` giữa 2 dòng `PERF_SUMMARY` liên tiếp không vượt
     `--max-gap-s` (mặc định 90 s; HOST in `PERF_SUMMARY` mỗi 30 s).
     Nếu trượt, script in `WARNING` nêu rõ source, khoảng trống (s) và thời điểm, rồi bỏ cờ đó khỏi lệnh.
     Kết quả nằm trong `uart-quality.json` ở khoá `capture_check`.
   - Khi bạn tự xác nhận capture đầy đủ dù kiểm tra trượt, thêm `--force-capture-complete`; script sẽ
     thêm `--capture-complete` và ghi `forced: true` vào `capture_check`.
   - Ví dụ: `python3 export_run.py --run 501 --out ~/run501 --max-gap-s 90`

## Architecture

CC2538 Source(s) --LWB--> CC2538 Host --CP2102 UART/USB--> Raspberry Pi 3

On the Pi:

1. `lwb_gateway.py` owns the serial port.
2. Every received line is timestamped in UTC.
3. The original serial line is preserved in a rotating raw log.
4. Parsed events are written to SQLite (`events` table).
5. `mqtt_publisher.py` reads unpublished rows from SQLite.
6. MQTT publish uses QoS 1.
7. Only after successful publish is a row marked as published.

This gives a durable local outbox so loss of Internet/MQTT does not stop serial acquisition.

## Why SQLite instead of CSV as the primary store?

CSV is useful for analysis/export but is weak as a durable queue:
- no transaction
- hard to track "published/not published"
- difficult to recover cleanly from network outages
- schema changes are awkward

Therefore SQLite is the system-of-record at the edge. `export_csv.py` creates CSV files when needed.

---

## 0. Important: stop Minicom first

Only one process should own `/dev/ttyUSB0`.

Exit Minicom before running the gateway.

Check:

```bash
sudo fuser /dev/ttyUSB0
```

No output = port is free.

---

## 1. Find a stable serial device path

```bash
ls -l /dev/serial/by-id/
```

If available, prefer that path instead of `/dev/ttyUSB0`, because ttyUSB numbers can change after reboot/replug.

The CC2538 host currently appears as Silicon Labs CP2102.

---

## 2. Install

```bash
sudo apt update
sudo apt install -y python3-venv

sudo mkdir -p /opt/lwb-gateway
sudo mkdir -p /var/lib/lwb-gateway
sudo mkdir -p /var/log/lwb-gateway
sudo mkdir -p /etc/lwb-gateway

sudo chown -R pi:pi /opt/lwb-gateway
sudo chown -R pi:pi /var/lib/lwb-gateway
sudo chown -R pi:pi /var/log/lwb-gateway
```

Copy these files into `/opt/lwb-gateway`:
- `lwb_gateway.py`
- `mqtt_publisher.py`
- `export_csv.py`
- `requirements.txt`

Then:

```bash
cd /opt/lwb-gateway
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
chmod +x lwb_gateway.py mqtt_publisher.py export_csv.py
```

Copy config:

```bash
sudo cp gateway.env.example /etc/lwb-gateway/gateway.env
sudo chown root:root /etc/lwb-gateway/gateway.env
sudo chmod 600 /etc/lwb-gateway/gateway.env
sudo nano /etc/lwb-gateway/gateway.env
```

Update `SERIAL_PORT` if `/dev/serial/by-id/...` exists.

---

## 3. Test serial collector manually

```bash
set -a
source /etc/lwb-gateway/gateway.env
set +a

cd /opt/lwb-gateway
.venv/bin/python lwb_gateway.py
```

You should see log lines such as:

```text
RX type=PERF_RX run=250 source=2 seq=11
```

Stop with `Ctrl+C`.

Inspect DB:

```bash
sqlite3 /var/lib/lwb-gateway/lwb.db \
'select id,recv_ts_utc,record_type,run,source,seq,published from events order by id desc limit 20;'
```

If sqlite3 CLI is not installed:

```bash
sudo apt install -y sqlite3
```

Raw serial forensic log:

```bash
tail -f /var/log/lwb-gateway/serial_raw.log
```

---

## 4. Export CSV

All data:

```bash
/opt/lwb-gateway/.venv/bin/python /opt/lwb-gateway/export_csv.py \
  --out /home/pi/lwb_all.csv
```

Only PERF_RX:

```bash
/opt/lwb-gateway/.venv/bin/python /opt/lwb-gateway/export_csv.py \
  --type PERF_RX \
  --out /home/pi/lwb_perf_rx.csv
```

---

## 5. Install serial service

```bash
sudo cp lwb-gateway.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lwb-gateway
```

Status:

```bash
systemctl status lwb-gateway
```

Live log:

```bash
journalctl -u lwb-gateway -f
```

---

## 6. MQTT development test

For a quick local broker on the Pi:

```bash
sudo apt install -y mosquitto mosquitto-clients
sudo systemctl enable --now mosquitto
```

Keep development config:

```text
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_TLS=false
```

Terminal A, subscribe:

```bash
mosquitto_sub -h 127.0.0.1 -t 'company/site1/lwb/#' -v
```

Terminal B, run publisher:

```bash
set -a
source /etc/lwb-gateway/gateway.env
set +a

cd /opt/lwb-gateway
.venv/bin/python mqtt_publisher.py
```

Expected topics include:

```text
company/site1/lwb/nodes/2/telemetry
company/site1/lwb/nodes/2/summary
```

---

## 7. Install MQTT publisher service

After MQTT testing is successful:

```bash
sudo cp lwb-mqtt.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lwb-mqtt
```

Check:

```bash
systemctl status lwb-mqtt
journalctl -u lwb-mqtt -f
```

---

## Production recommendations

Do NOT use a public anonymous MQTT broker for enterprise deployment.

Use:
- private Mosquitto/EMQX/HiveMQ/AWS IoT/etc.
- TLS
- authentication
- per-gateway credentials
- ACLs restricting publish topics
- monitoring and alerting

QoS 1 is "at least once"; duplicate MQTT delivery is possible. Every message therefore contains a stable `event_id` and `gateway_id`. The cloud/database should enforce idempotency on `(gateway_id, event_id)`.

## Power warning

Earlier Raspberry Pi logs reported repeated `Undervoltage detected!`.

Before 24/7 operation check:

```bash
vcgencmd get_throttled
```

For a production gateway, fix the power supply/cable before treating the system as reliable.
