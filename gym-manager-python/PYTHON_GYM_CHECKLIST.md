# Python Gym Manager Checklist

Nguyên tắc:
- Tick `[x]` khi đã code xong và đã verify.
- Ghi note ngắn để agent sau tiếp tục không phải đoán lại.
- DAH-1017 tạm hoãn cho đến khi có tài liệu API/webhook/SDK thật.

## 0. Foundation
- [x] Tao project Python rieng tai `gym-manager-python`.
- [x] Chon stack FastAPI + SQLite + Jinja + Tailwind CDN.
- [x] Cai dependencies Python.
- [x] Tao database SQLite va seed data demo.
- [x] Tao script/run instructions.
- [x] Script chạy server `RUN_SERVER.ps1`.

## 1. Data Model
- [x] Branches.
- [x] People.
- [x] Customers.
- [x] Employees.
- [x] Service packages.
- [x] Memberships.
- [x] Invoices/payments summary.
- [x] Customer profile fields: họ tên, điện thoại, giới tính, ngày sinh, mã thẻ MBS, nguồn khách.
- [x] Customer fields: nhân viên sale phụ trách và note chăm sóc.
- [x] Membership finance fields: ngày đăng ký, tiền cọc, dư nợ, hạn dư nợ.
- [x] Payment fields: hình thức thanh toán, số tiền, ảnh phiếu thu.
- [x] Attendance/check-in sessions.
- [x] Device stubs.
- [x] Lịch hẹn khách hàng.
- [x] Lịch hẹn lead/prospect độc lập, chưa cần là khách hàng.
- [x] Nhóm/lớp PT 1:1, 1:2, 1:3.
- [x] Thành viên trong nhóm PT.
- [x] Gán nhân viên sale online, nhân viên chốt trực tiếp, PT chuyển đổi trên gói đăng ký.
- [x] Bút toán hoa hồng/KPI cơ bản.
- [x] Tài khoản nhận chuyển khoản public/private.
- [x] Phiên chốt ca tiền mặt.
- [x] Mở rộng payment: tài khoản nhận tiền, ngày ca, kênh public/private.
- [ ] Sync jobs/raw events stubs.

## 2. UI Shell
- [x] Layout responsive desktop/netbook.
- [x] Sidebar navigation.
- [x] Header/action bar.
- [x] Fitness-themed visual identity.
- [x] Dashboard stat cards.
- [x] Professional tables and badges.

## 3. Screens MVP
- [x] Dashboard.
- [x] Customers list/create.
- [x] Customer detail with related memberships, PT schedule, appointments, payments, check-in history.
- [x] Customer edit form.
- [x] Employees list/create.
- [x] Packages list/create.
- [x] Memberships list/create.
- [x] Debt due soon warning.
- [x] Check-in desk.
- [x] Devices monitor.
- [x] Sync/errors stub.
- [x] Lịch hẹn theo ngày.
- [x] Sửa lịch hẹn và chuyển `Khách chốt` thành khách hàng + đăng ký gói.
- [x] Quản lý nhóm/lớp PT.
- [x] Báo cáo doanh thu.
- [x] Báo cáo công nợ.
- [x] Báo cáo giao dịch chuyển khoản.
- [x] Báo cáo giao dịch tiền mặt/chốt ca.
- [x] Báo cáo hoa hồng sale/PT/lễ tân.

## 4. UX Polish
- [x] Responsive desktop 1440px.
- [x] Responsive netbook 1024px.
- [x] No overlapping text/buttons.
- [x] Forms readable and compact.
- [x] Tables scan-friendly.
- [x] Modal thêm khách từ nút `Thêm`.
- [x] Toast success/error sau các thao tác form.
- [x] Form optional ID/number không trả lỗi JSON `int_parsing` khi gửi chuỗi rỗng.
- [x] Global validation handler chuyển lỗi FastAPI validation thành toast lỗi.
- [ ] Empty/error states.

## 5. Verification
- [x] App starts locally.
- [x] Playwright desktop screenshot.
- [x] Playwright netbook screenshot.
- [x] Fix issues found by screenshots.
- [x] Verify server vẫn chạy sau nhiều request.

## Implementation Notes
- 2026-08-10: Bỏ phân hệ Lịch hẹn khỏi route/navigation; lịch hẹn được quản lý độc lập bằng Google Sheet. Bảng SQLite cũ được giữ để bảo toàn lịch sử.
- 2026-08-10: Bỏ Hoa hồng khỏi route/navigation và ngừng sinh bút toán hoa hồng mới; dữ liệu cũ vẫn được giữ.
- 2026-08-10: Thay quản lý nhóm PT bằng đăng ký PT trực tiếp theo khách, chia ba tab 1:1/1:2/1:3; hỗ trợ coach, số buổi, thời hạn, thứ và giờ tập.
- 2026-08-10: Hồ sơ khách ẩn lịch hẹn/thanh toán riêng, thêm chi tiết gói và cập nhật ảnh phiếu thu; danh sách khách bỏ cột Note.
- 2026-08-10: Gói tập thường được tách khỏi PT; nhân viên bỏ chi nhánh/lương/trạng thái trên UI và có sửa/xóa an toàn.
- 2026-08-05: Laravel version duoc giu lai de tham chieu, Python app moi se la huong chinh.
- 2026-08-05: App FastAPI chay tai `http://127.0.0.1:8100`.
- 2026-08-05: Playwright screenshots pass cho desktop 1440x1000 va netbook 1024x768. Screenshots nam trong `screenshots/`.
- 2026-08-05: Da fix form action tren desktop de nut tao khach/nhan vien khong bi roi xuong dong.
- 2026-08-05: Da Viet hoa UI sang tieng Viet co dau, doi brand sang PulseFit Studio va sua du lieu SQLite bi mojibake bang `update_vietnamese_data.py`.
- 2026-08-05: Da bo sung thong tin khach theo yeu cau: gioi tinh, ngay sinh, ma the MBS, moi khach nhieu goi, ngay dang ky goi, tien coc, du no, han du no, hinh thuc thanh toan va anh phieu thu.
- 2026-08-05: Áp dụng note nghiệp vụ: thêm lịch hẹn, nhóm PT, gán sale/PT chuyển đổi, hoa hồng, báo cáo doanh thu, công nợ, giao dịch chuyển khoản/tiền mặt và chốt ca.
- 2026-08-05: Màn Khách hàng đã chuyển form thêm khách sang modal mở bằng nút `Thêm`.
- 2026-08-05: Bổ sung dữ liệu mẫu phủ tất cả bảng chính: 8 khách, 6 nhân viên, 8 gói, 8 đăng ký, 12 thanh toán, 6 lịch hẹn, 3 nhóm PT, 19 dòng hoa hồng, 3 ca tiền mặt, 15 check-in, 4 thiết bị.
- 2026-08-05: Verify app không tự crash; server test vẫn `Running` sau nhiều request. Đã sửa overflow bảng khách hàng trên netbook.
- 2026-08-05: Đã xử lý lỗi FastAPI validation khi form gửi `""` cho optional int/number như `sales_employee_id`, `bank_account_id`, `employee_id`, `package_id`, `membership_id`, `duration_days`, `session_count`, `price`, `final_price`, `deposit_amount`.
- 2026-08-05: Thêm toast success/error dùng query params sau redirect; bỏ seed tự gán sale cho khách null để trường sale được phép để trống thật.
- 2026-08-05: Thêm `RequestValidationError` handler toàn cục để lỗi validation như `int_parsing` không hiện JSON; sửa khách không gán sale đã test redirect success và giữ sale null.
- 2026-08-05: Sửa logic lịch hẹn theo nghiệp vụ mới: người chưa tập/chưa đăng ký vẫn tạo hẹn; lịch hẹn có tên khách, bộ môn quan tâm, nhân viên chăm sóc bắt buộc, ghi chú, ngày/giờ hẹn, nền tảng, nhân viên hỗ trợ trực tiếp nullable, tình trạng, ghi chú sau tư vấn; thêm sửa lịch hẹn và luồng `Khách chốt` tạo khách + đăng ký gói với ngày đăng ký lấy từ ngày hẹn.
