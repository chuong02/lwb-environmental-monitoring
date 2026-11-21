# Chạy backend + dashboard trực tiếp trên Windows (không Docker, không Ubuntu)

## Cài lần đầu

1. Cài **Python 3.12 trở lên** từ python.org, nhớ tick **Add python.exe to PATH**.
2. Bấm đúp **`setup_windows.bat`**. Script sẽ tạo `.venv-win`, cài thư viện, tạo database SQLite
   `lwb_backend.sqlite3` và hỏi tạo tài khoản admin.
3. Mở file `.env` (cùng thư mục) và kiểm tra:
   - `MQTT_HOST`, `MQTT_USERNAME`, `MQTT_PASSWORD`: tài khoản EMQX của backend.
   - `MQTT_BASE_TOPIC=warehouse/site1/lwb` (phải trùng với gateway trên Pi).
   - `MQTT_CA=` để trống (Windows tự dùng kho chứng chỉ của hệ điều hành).
   - `LWB_READING_RETENTION_MINUTES=15`: số phút giữ dữ liệu cảm biến.

## Mỗi lần dùng

Bấm đúp **`run_windows.bat`**. Ba cửa sổ sẽ mở ra:

| Cửa sổ | Việc của nó |
|---|---|
| LWB mqtt consumer | Nhận bản tin từ EMQX, ghi vào SQLite, xóa bản ghi cảm biến cũ hơn 15 phút |
| LWB web server | Dashboard `http://127.0.0.1:8000/`, admin `http://127.0.0.1:8000/admin/`, API `/api/...` |
| LWB mobile api | Mobile API chỉ đọc cho app Android, cổng 8001 (`/api/mobile/v1/`) |

Muốn dừng thì đóng ba cửa sổ đó. Không mở hai consumer cùng lúc, vì cùng `MQTT_CLIENT_ID` sẽ đá nhau.

## App mobile

App Flutter (`mobileapp/lwb_mobile`) chạy trên điện thoại Android và **chỉ đọc** dữ liệu qua Mobile API
(cửa sổ "LWB mobile api", cổng 8001) trên laptop này, đi qua Tailscale.

1. Cài **Tailscale** trên điện thoại và trên laptop, đăng nhập cùng một tài khoản.
2. Trên laptop xem IP Tailscale: `tailscale ip -4` (dạng `100.x.y.z`).
3. Trong app nhập URL: `http://<IP Tailscale của laptop>:8001`.
4. Lần đầu chạy `run_windows.bat`, Windows hiện hộp thoại Firewall cho cửa sổ Python: bấm **Allow**.

Hai biến trong `.env` điều khiển truy cập (đều có mặc định, không bắt buộc khai báo):

| Biến | Mặc định | Ý nghĩa |
|---|---|---|
| `LWB_MOBILE_ALLOWED_HOSTS` | `127.0.0.1,localhost,10.0.2.2,[::1]` | `ALLOWED_HOSTS` của Mobile API; cho phép `*`. `run_windows.bat` đặt `*` cho cửa sổ này vì điện thoại gọi bằng IP Tailscale. |
| `LWB_MOBILE_ALLOWED_NETS` | `100.64.0.0/10` | Danh sách CIDR (ngăn cách bằng dấu phẩy), ngoài loopback, được phép gọi API: dải IP của Tailscale. Địa chỉ khác (ví dụ mạng LAN `192.168.x.x`) bị từ chối HTTP 403. |

Server không tin header `X-Forwarded-For`; chỉ dùng địa chỉ kết nối thật. Không đưa cổng 8001 ra Internet
(port forwarding, tunnel công khai).

## Xem trên iPhone/Android bằng trình duyệt

Không cần app: điện thoại có Tailscale mở được dashboard web của laptop.

1. Cài **Tailscale** trên điện thoại và trên laptop, đăng nhập cùng một tài khoản; bật Tailscale trước khi chạy `run_windows.bat`.
2. `run_windows.bat` tự lấy IP Tailscale (`tailscale ip -4`) và mở thêm cửa sổ **"LWB web (Tailscale)"**
   (`runserver <IP Tailscale>:8000`, `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,<IP Tailscale>` chỉ đặt riêng cho cửa sổ này).
   Cửa sổ "LWB web server" ở `127.0.0.1:8000` giữ nguyên. Nếu không có Tailscale thì bước này bị bỏ qua và script in thông báo.
3. Trên điện thoại mở trình duyệt: `http://<IP Tailscale của laptop>:8000`. Cuối `run_windows.bat` có in sẵn địa chỉ.
4. Lần đầu chạy, Windows Firewall hỏi thì chọn **Allow** cho **Private networks**.

| Cổng | Dùng cho |
|---|---|
| 8000 | Dashboard web (trình duyệt trên điện thoại hoặc laptop) |
| 8001 | Chỉ là API cho app Flutter (`http://<IP Tailscale>:8001` nhập trong app); không mở bằng trình duyệt để xem dashboard |

## Chia sẻ public (Tailscale Funnel)

Dùng khi muốn gửi link dashboard cho người **không** có Tailscale. Chỉ chia sẻ cổng **8000** (dashboard + API
đọc dữ liệu). **Không public cổng 8001** (Mobile API cho app Flutter).

1. **Bật Funnel trong trang quản trị Tailscale** (một lần): đăng nhập https://login.tailscale.com/admin →
   *Access controls*, thêm thuộc tính `funnel` cho thiết bị/người dùng (Funnel cũng cần bật *MagicDNS* và *HTTPS certificates*
   ở mục *DNS*). Chỉ khi đó lệnh `tailscale funnel` mới chạy được.
2. Trong `.env` đặt `DJANGO_SECRET_KEY` bằng một giá trị **thật** (chế độ public từ chối giá trị mặc định
   `django-insecure-...`). Tạo khóa: `.venv-win\Scripts\python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"`.
3. Bấm đúp **`run_public.bat`** (thay cho `run_windows.bat`, không chạy cùng lúc). Script đặt `LWB_PUBLIC=1`,
   `DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost,.ts.net`, `LWB_PUBLIC_ORIGINS=https://<tên máy>.ts.net`, rồi chạy consumer và
   `runserver 127.0.0.1:8000`. Ở chế độ này: `DEBUG` tắt, **`/admin/` không tồn tại** (404), dashboard, `/assets/` và
   `/api/overview|perf|nodes` vẫn hoạt động.
4. Mở một cửa sổ khác và bật Funnel (script **không** tự bật):
   ```
   tailscale funnel --bg 127.0.0.1:8000
   tailscale funnel status
   ```
   Lệnh `status` hiện link `https://<tên máy>.ts.net`.
5. **Khi xong phải tắt Funnel**: `tailscale funnel reset`, rồi đóng hai cửa sổ "(public)".

Rủi ro: **bất kỳ ai có link đều xem được** dữ liệu cảm biến và kết quả đo (dashboard không có đăng nhập), và link nằm trên Internet
công khai cho đến khi bạn tắt Funnel. Không gửi link ở nơi công khai; tắt ngay khi không cần.

Biến môi trường của chế độ này: `LWB_PUBLIC=1`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` (cho phép `.ts.net`),
`LWB_PUBLIC_ORIGINS` (danh sách origin HTTPS, ngăn cách bằng dấu phẩy, dùng cho `CSRF_TRUSTED_ORIGINS`).

## Xem database

- **Django admin**: `/admin/`, có các bảng Gateway, Node, SensorReading, PerfEvent.
- **DB Browser for SQLite** (sqlitebrowser.org): mở file `lwb_backend.sqlite3`, nên chọn *Read Only*
  khi hệ thống đang chạy.

## Luồng dữ liệu

`CC2538 HOST → UART → Raspberry Pi (lwb_gateway.py → SQLite → mqtt_publisher.py) → EMQX Cloud →
mqtt_consumer (máy này) → lwb_backend.sqlite3 → Django REST API → dashboard (tự gọi API mỗi 2 s)`

## API

| Đường dẫn | Nội dung |
|---|---|
| `/api/overview/` (`?online=1`) | Mọi node: online/offline, bản tin mới nhất, delay/hop 5 phút gần nhất, trạng thái gateway |
| `/api/perf/` (`?run=501`) | Kết quả đo LWB theo từng source, lấy từ PERF_SUMMARY của HOST |
| `/api/nodes/<id>/history/?limit=60` | Lịch sử bản tin của một node |

## Sửa giao diện

Code giao diện nằm ở `frontend/src/App.jsx`. Bản đã build nằm ở `frontend/dist`, do Django phục vụ
trực tiếp. Sửa giao diện xong thì cần Node.js để build lại: `cd frontend && npm install && npm run build`.

## PostgreSQL (tùy chọn)

Đặt `DB_ENGINE=postgresql` và điền `DB_*` trong `.env`, cài thêm `pip install "psycopg[binary]"`.
Docker (`docker-compose.yml`) không còn cần cho chạy local.
