# PulseFit DAH Windows Agent

Windows helper chạy trong cùng mạng LAN/Wi-Fi với máy DAH.

Chức năng:

- Lưu cấu hình server PulseFit và DAH.
- Long-poll server để nhận lệnh sync.
- Khi sync, mở browser headless, đăng nhập DAH bằng `system/admin`, vào nhật ký kiểm soát, bấm search.
- Kéo lịch sử từ DAH `/webs/getControl`.
- Gửi kết quả về PulseFit server.

Build:

```powershell
cd D:\TOOL_VID\extension
.\build.ps1
```

Exe sau build:

```text
D:\TOOL_VID\extension\app\PulseFitDahAgent.exe
```

Server endpoints agent đang gọi:

```text
POST /api/dah/local-agent/heartbeat
GET  /api/dah/local-agent/jobs/next?agentId=...&timeout=55
POST /api/dah/local-agent/jobs/{jobId}/result
```

Nếu server chưa có các endpoint này, agent vẫn chạy nhưng log sẽ báo lỗi HTTP.
