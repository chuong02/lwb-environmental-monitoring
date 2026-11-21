# LWB Mobile V1 - huong dan cai vao he thong hien tai

Phien ban giam sat **noi bo** Flutter + Django/PostgreSQL. Danh sach Node dong,
khong co gioi han hard-code Node 1/2/3. Dinh danh = (gateway_id, node_id).
Day la ma nguon de cai tren may ban, KHONG phai APK da build / dich vu da deploy.

## 1. Pham vi

- Flutter: danh sach 25 Node/trang; tim theo ID/ten Gateway; loc Gateway chinh xac,
  loc trang thai; tong hop Live/Stale/Offline/Never/Clock error.
- Chi tiet: 5 so do, bieu do nhiet do va do am tach rieng de khong nham truc.
  30/60/100 mau; cham bieu do de xem mau thuc. Khong tao du lieu gia.
- Danh sach: 15s khi man hinh danh sach hien thi. Khi mo chi tiet, polling danh
  sach dung; chi tiet lay latest 5s va history 15s. Khoi dong/tai lai thu cong co
  request ngay. Thoi gian thuc te con phu thuoc latency; loi mang tang thoi gian
  retry len toi 60s + jitter toi 1s. Moi tac vu toi da 1 request dang cho.
- App vao nen: dung timers va dong request dang cho. Tro lai: lay du lieu ngay.
- Du lieu cu van hien thi kem timestamp khi API loi; khong danh dong loi API voi
  Node Offline. Doi trang/bo loc thi bo qua phan hoi cu den tre.
- NULL/sentinel hien thi --, khong doi thanh 0. Ap suat Pa chia 100 de ra hPa.
- App khong giu tai khoan MQTT hay ket noi PostgreSQL truc tiep.
- Chua co dang nhap Mobile/JWT, phan quyen tung Gateway, WebSocket, push,
  canh bao nen, dieu khien LED/relay hay APK release. Khong duoc mo public/4G
  voi cau hinh local nay. Day chua phai mot he thong production duoc chung nhan.

## 2. Tach cong de khong lam hong Web cu

Web React: 5173; Django Web cu: 8000; PostgreSQL: 5432; Mobile API test: 8001.
8001 la mot tien trinh Django doc CUNG DATABASES tu config/settings.py cu.
Khong tao database moi. Khong can migrate. Khong thay settings.py, urls.py,
models.py, mqtt_consumer.py cu hay firmware. Web van dung API va chu ky 4/8s cu.

API moi co namespace /api/mobile/v1/. Khong thay JSON list /api/nodes/ cu bang
paginated object vi nhu vay se lam React dang hoat dong bi loi.

## 3. Cai va chay Backend - Ubuntu WSL

Giai nen ZIP de co C:\lwb_setup\LWB_Mobile_V1\.
Giu PostgreSQL, MQTT Consumer va Gateway dang hoat dong nhu truoc.
Trong Ubuntu WSL:

```bash
bash /mnt/c/lwb_setup/LWB_Mobile_V1/backend/start_mobile_api.sh "$HOME/lwb-backend"
```

Script dung .venv co san, kiem tra model, sao luu va chep 7 tep moi, chay 13
Django tests tren SQLite IN-MEMORY (khong cham vao PostgreSQL that), sau do chay:

```bash
python manage.py runserver 127.0.0.1:8001 --settings=config.lwb_mobile_local --noreload
```

Neu tests loi, script DUNG, khong tu sua database. Copy phan loi de doi chieu.
Dich vu 8001 chi doc; giu cua so WSL nay mo. Ctrl+C chi dung Mobile API.
Backend chay 8000 va MQTT Consumer khong bi dung. Khong chay them consumer thu 2.

Kiem tra bang PowerShell tren Windows:

```powershell
Invoke-RestMethod 'http://127.0.0.1:8001/api/mobile/v1/health/'
Invoke-RestMethod 'http://127.0.0.1:8001/api/mobile/v1/nodes/?page=1&page_size=25'
```

Kiem tra tren Chrome TRONG Android Emulator:

```text
http://10.0.2.2:8001/api/mobile/v1/health/
```

10.0.2.2 la alias den host Windows, khong phai Raspberry Pi va khong phai dia
chi cho iPhone/Android that. Truy cap Windows -> WSL con phu thuoc localhost
forwarding cua WSL. Neu Windows truy cap duoc nhung emulator khong duoc, doc
muc khac phuc loi ben duoi truoc khi doi cau hinh firewall.

## 4. Cai ma Flutter - Windows PowerShell

Trong terminal dang flutter run, nhan q de dung app (khong tat emulator).
Khong bam Run trong Android Studio dong thoi voi lenh duoi.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\lwb_setup\LWB_Mobile_V1\scripts\install_mobile.ps1' -ProjectPath 'C:\lwb_mobile'
```

ExecutionPolicy Bypass chi ap dung cho tien trinh PowerShell nay, khong doi
policy toan may. Co the mo script de doc truoc khi chay.

Script se:
1. Sao luu lib/, test/, pubspec va manifest lien quan vao C:\lwb_mobile_backup_<timestamp>.
2. Chep lib/ va cac test. Vo hieu test dem so Flutter Demo mac dinh neu nhan dien duoc.
3. Them quyen INTERNET. Chi ban DEBUG cho HTTP toi 10.0.2.2/localhost/127.0.0.1.
4. Them http va shared_preferences, giu ten/SDK constraints pubspec hien co.
5. Chay dart format, flutter analyze, flutter test test/lwb_v1. Dung neu loi.
6. Khong sua Gradle, NDK, Android SDK hay xoa cache build.

Sau khi checks thanh cong:

```powershell
cd C:\lwb_mobile
flutter run -d emulator-5554
```

App mac dinh dung http://10.0.2.2:8001. Nut banh rang doi Backend URL, chi nhap
dia chi goc (khong them /api). URL duoc luu trong SharedPreferences; khong luu
mat khau/token o day. Uu tien kiem thu Android; Flutter Web can CORS rieng,
khong tat bao mat Chrome de bo qua CORS.

## 5. API contract

Tat ca endpoint chi nhan GET. Gateway query BAT BUOC cho latest/history.

| Endpoint duoi /api/mobile/v1/ | Tham so | Phan hoi |
|---|---|---|
| health/ | khong | api_version, server_time, policy, mode |
| nodes/ | page, page_size<=100, gateway, q, status | summary, count, page, pages, results |
| nodes/status-summary/ | gateway, q | summary |
| nodes/<id>/latest/ | gateway | node, reading (co the null), server_time, policy |
| nodes/<id>/history/ | gateway, limit<=1000 | results theo thu tu thoi gian tang dan |

App dung 25 dong/trang. Summary tinh cho gateway + q, TRUOC loc status; count la
so dong SAU loc status. Node sap xep on dinh theo gateway_id, node_id, pk;
khong doi vi tri moi khi last_seen thay doi. Neu xoa het Node cua trang cu,
server ha so trang ve trang cuoi con hop le.

Node ton tai nhung chua co so do: latest tra 200 voi reading=null. Node khong
ton tai: 404. Gateway thieu/limit sai: 400. Khong co quyen: 401/403.
Cac quy uoc nay chi cho API Mobile V1, khong doi quy uoc cua API React cu.

## 6. Quy tac trang thai

Tinh theo last_seen tu backend, so voi gio server; app uoc luong server time tu
response de giam anh huong lech dong ho dien thoai.
- Live: age <= 15s, tru truong hop timestamp tuong lai >10s.
- Stale: 15s < age <=30s.
- Offline: age >30s. Day la suy luan khong co ban tin, khong phai xac nhan mat nguon.
- Never: last_seen=null.
- Clock error: last_seen > server time +10s.

Nguong la cau hinh khoi dau cho Node gui khoang 5s, KHONG la tieu chuan cong
nghiep. Sua LWB_MOBILE_LIVE_SECONDS/OFFLINE_SECONDS trong config/lwb_mobile_local.py
neu chu ky Node khac. Moi Node co nhip gui khac nhau thi can model/cau hinh timeout
rieng trong dot nang cap sau.

Consumer hien co co the cap nhat last_seen theo timestamp ban tin cu/ban tin lap.
Patch nay KHONG sua Consumer. Can kiem thu replay/dong bo gio va quy tac monotonic
last_seen truoc khi ket luan tinh dung dan cua Live/Offline trong van hanh that.
Bieu do ngat duong khi gap NULL hoac khoang thoi gian > max(20s, 3*median interval).

## 7. Khac phuc loi

- 404 o /api/mobile/v1/: thu health/ day du. Dung dung cong 8001, khong phai8000.
- Khong co Node: kiem tra MQTT Consumer va DB that; bo gateway/status filter de xem tat ca.
- Node Offline: kiem tra last_seen, gio Pi/WSL, UART/MQTT; khong tu tang timeout de che loi.
- 403 local: che do local chi chap nhan REMOTE_ADDR loopback. Khong sua AllowAny
  toan cuc. Gui log request/ket qua health de phan tich networking.
- Network error Android: thu browser emulator truoc. Khong dung localhost de chi
  Windows ben trong emulator. Manifest debug chi cho HTTP toi 3 host noi bo tren.
- Mang WSL: chi khi Windows da doc duoc health, co the thu ADB reverse:

```powershell
& "$env:LOCALAPPDATA\Android\sdk\platform-tools\adb.exe" -s emulator-5554 reverse tcp:8001 tcp:8001
```

  Sau do doi Backend URL trong App thanh http://127.0.0.1:8001. Lenh nay khong
  sua firewall hay mo port ra Internet. Neu van loi, khong tat firewall toan may.
- Gradle lock: dung Run thu hai. Khong goi flutter clean lap lai de sua loi API.
- Pubspec not found: thu muc dung la C:\lwb_mobile.
- Dependencies/test loi: giu nguyen SDK/NDK; doc loi dau tien, khong nang cap tat ca
  package hoac sua Gradle mot cach ngau nhien.

## 8. Checklist nghiem thu tren may ban

[ ] Danh sach doc duoc cac Node thuc; khong hard-code 3 Node.
[ ] Gateway khac nhau co cung node_id van hien thi dung, khong lan du lieu.
[ ] Xem trang 2, loc gateway, xoa loc, tim Node ID.
[ ] So do khop Django; pressure_pa/100 la hPa; null/sentinel la --.
[ ] Biieu do chon 30/60/100 mau; mat du lieu khong ve thanh gia tri 0.
[ ] Tat Node: Stale roi Offline; bat lai: co ban tin moi thi Live.
[ ] Tat API 8001: bao loi API, khong gia vo Node tat nguon; bat lai: tu khoi phuc.
[ ] App vao nen: access log khong con GET tu app; mo lai: GET ngay.
[ ] Doi Node/bo loc nhanh: phan hoi cu khong ghi de man hinh moi.
[ ] React 5173 van hoat dong, API 8000 va MQTT Consumer khong doi.

## 9. Sao luu va khoi phuc

Mobile:
```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File 'C:\lwb_setup\LWB_Mobile_V1\scripts\restore_mobile.ps1' -BackupPath 'C:\lwb_mobile_backup_<timestamp>'
cd C:\lwb_mobile
flutter pub get
```
Dung app truoc khi rollback. Thay timestamp bang thu muc backup script da in.

Backend: dung server8001; cac API Web cu khong can khoi phuc vi khong bi sua.
```bash
python /mnt/c/lwb_setup/LWB_Mobile_V1/backend/apply_backend.py --rollback "$HOME/lwb-backend_mobile_backup_<timestamp>"
```

## 10. Gioi han kiem thu va huong production

Xem VALIDATION.md. 15 tests Python core/installer da chay trong moi truong soan.
Flutter analyze/tests va Django API tests duoc dong goi de chay tren may ban;
khong duoc coi la da pass khi chua chay. Chua build APK hay ket noi du lieu thuc.

Chua benchmark PostgreSQL, chua kiem thu RF hang tram Node, chua chung minh SLA.
Cac buoc production con thieu: HTTPS + production server, token login va quyen
Gateway, monitoring/logging, rate limit, cache/index cho du lieu lon, timestamp
monotonic, backup DB, retention/disk management, load test, deployment server
hoat dong lien tuc. Viec them App khong lam WSL tu chay khi laptop ngu/tat.

API pagination gioi han kich thuoc response va tranh N+1; KHONG bao dam mo rong
vo han. Summary van can dem cac Node phu hop; voi tap du lieu rat lon can do EXPLAIN,
index (node, recv_ts_utc) va caching/materialized latest phu hop. Khong auto tao index
tren PostgreSQL dang chay trong ban nay.

## 11. Co so doi chieu

Repository chuong02/lwb-environmental-monitoring (thu muc backend/): backend/telemetry/models.py, views.py, urls.py da doc qua
GitHub trong luot nay; local code tren WSL co the khac repo. Installer kiem tra
model truoc khi chep, khong ghi de cac file do.
Tai lieu chinh thuc: Flutter app architecture recommendations, networking,
WidgetsBindingObserver lifecycle; Django REST Framework pagination/permissions;
Android emulator networking va Network Security Configuration.
