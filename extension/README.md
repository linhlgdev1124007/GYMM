# PulseFit DAH Windows Agent

Windows helper chạy trong cùng mạng LAN/Wi-Fi với máy DAH (máy nhận diện khuôn mặt / chấm công / kiểm soát ra vào).

## Tính năng nâng cao:

1. **Yêu cầu quyền Administrator tự động (UAC Elevation)**:
   - Tự động kích hoạt hộp thoại UAC xin quyền Admin khi khởi động.
   - File thực thi `.exe` được gán manifest `requireAdministrator`.

2. **Tự động Auto-Startup khi mở máy (Task Scheduler - Highest Privileges)**:
   - Tự động đăng ký tác vụ trong Windows Task Scheduler (`schtasks`) với quyền Admin cao nhất (`/rl highest`) chạy khi đăng nhập (`/sc onlogon`).
   - Khởi động cùng Windows mượt mà mà không bị UAC chặn hay hỏi lại mỗi lần boot máy.

3. **Tự động kích hoạt (Auto Start Worker)**:
   - Tự động bật tiến trình kết nối & đồng bộ dữ liệu ngay khi ứng dụng mở lên.

4. **Chống tắt / Chạy ngầm trong khay hệ thống (System Tray - Không thể vô tình tắt)**:
   - Chặn nút `X` (đóng cửa sổ) và Alt+F4: Tự động ẩn giao diện xuống khay hệ thống (System Tray cạnh đồng hồ Windows).
   - Icon khay hệ thống hỗ trợ mở lại giao diện, kích hoạt sync nhanh, và yêu cầu hộp thoại xác nhận cảnh báo nghiêm ngặt nếu muốn thoát.

5. **Trình gỡ cài đặt chuyên dụng (`uninstall.exe`)**:
   - Dừng toàn bộ tiến trình chạy ngầm `PulseFitDahAgent.exe`.
   - Xóa tác vụ tự khởi động trong Task Scheduler & Start Menu Startup.
   - Xóa các file dữ liệu cấu hình, log và dọn sạch file chương trình.

## Build EXE:

```powershell
cd D:\TOOL_VID\extension
.\build.ps1
```

Sản phẩm sau khi build nằm trong thư mục `app/`:

```text
D:\TOOL_VID\extension\app\PulseFitDahAgent.exe  (Ứng dụng chính)
D:\TOOL_VID\extension\app\uninstall.exe         (Ứng dụng gỡ cài đặt)
```

## Server Endpoints agent đang gọi:

```text
POST /api/dah/local-agent/heartbeat
GET  /api/dah/local-agent/jobs/next?agentId=...&timeout=55
POST /api/dah/local-agent/jobs/{jobId}/result
POST /api/dah/local-agent/scan-plan
POST /api/dah/local-agent/day-scan-result
```
