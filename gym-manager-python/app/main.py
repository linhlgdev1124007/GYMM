from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from .database import Base, engine, get_db
from .models import (
    Appointment,
    AttendanceSession,
    BankAccount,
    Branch,
    CashShift,
    CommissionLedger,
    Customer,
    Device,
    Employee,
    Membership,
    Payment,
    Person,
    PtGroup,
    PtGroupMember,
    ServicePackage,
)
from .seed import seed_database

app = FastAPI(title="PulseFit Studio")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
Path("app/static/receipts").mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory="app/templates")


def optional_int(value: str | int | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def int_value(value: str | int | None, default: int = 0) -> int:
    parsed = optional_int(value)
    return default if parsed is None else parsed


def money_value(value: str | float | int | None, default: float = 0) -> float:
    if value is None or value == "":
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def redirect_with_toast(path: str, message: str, toast_type: str = "success") -> RedirectResponse:
    separator = "&" if "?" in path else "?"
    return RedirectResponse(f"{path}{separator}{urlencode({'toast': message, 'toast_type': toast_type})}", status_code=303)


def wants_json(request: Request) -> bool:
    return request.headers.get("x-requested-with") == "fetch"


def pt_groups_context(db: Session, q: str = "", status: str = "active") -> dict:
    all_groups = db.query(PtGroup).options(
        joinedload(PtGroup.coach).joinedload(Employee.person),
        joinedload(PtGroup.package),
        joinedload(PtGroup.members).joinedload(PtGroupMember.customer).joinedload(Customer.person),
        joinedload(PtGroup.members).joinedload(PtGroupMember.membership).joinedload(Membership.package),
    ).order_by(PtGroup.id.desc()).all()
    normalized_q = q.strip().lower()
    groups = all_groups
    if status != "all":
        groups = [group for group in groups if group.status == status]
    if normalized_q:
        groups = [
            group for group in groups
            if normalized_q in " ".join([
                group.name or "",
                group.group_type or "",
                group.schedule_label or "",
                group.coach.person.display_name if group.coach else "",
            ]).lower()
        ]
    coaches = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").order_by(Employee.id.desc()).all()
    packages = db.query(ServicePackage).filter(ServicePackage.is_pt == True).order_by(ServicePackage.name).all()
    customers = db.query(Customer).options(joinedload(Customer.person)).filter(Customer.status.in_(["active", "lead"])).order_by(Customer.id.desc()).all()
    memberships = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package)).order_by(Membership.id.desc()).all()
    return {
        "groups": groups,
        "coaches": coaches,
        "packages": packages,
        "customers": customers,
        "memberships": memberships,
        "q": q,
        "status": status,
        "counts": {
            "active": sum(1 for group in all_groups if group.status == "active"),
            "inactive": sum(1 for group in all_groups if group.status == "inactive"),
            "all": len(all_groups),
        },
    }


def render_pt_groups_fragment(db: Session, request: Request, q: str = "", status: str = "active") -> str:
    context = pt_groups_context(db, q, status)
    context["request"] = request
    return templates.env.get_template("_pt_groups_list.html").render(context)


def pt_groups_json(db: Session, request: Request, message: str, q: str = "", status: str = "active") -> JSONResponse:
    return JSONResponse({
        "ok": True,
        "message": message,
        "target": "#pt-groups-list",
        "fragment": render_pt_groups_fragment(db, request, q, status),
    })


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError) -> RedirectResponse:
    referer = request.headers.get("referer")
    has_path_error = any((error.get("loc") or [None])[0] == "path" for error in exc.errors())
    if referer and referer.startswith(str(request.base_url).rstrip("/")):
        target = referer
    elif has_path_error:
        target = "/"
    else:
        target = str(request.url.path)
    return redirect_with_toast(target, "Dữ liệu nhập chưa hợp lệ. Vui lòng kiểm tra lại các trường trong form.", "error")


def ensure_schema() -> None:
    additions = {
        "people": {
            "date_of_birth": "DATE",
        },
        "customers": {
            "mbs_card_code": "VARCHAR(60)",
            "sales_employee_id": "INTEGER",
        },
        "memberships": {
            "registered_at": "DATE",
            "deposit_amount": "FLOAT DEFAULT 0",
            "debt_amount": "FLOAT DEFAULT 0",
            "debt_due_date": "DATE",
            "sale_online_employee_id": "INTEGER",
            "direct_sales_employee_id": "INTEGER",
            "pt_converter_employee_id": "INTEGER",
        },
        "payments": {
            "bank_account_id": "INTEGER",
            "channel": "VARCHAR(30) DEFAULT 'counter'",
            "shift_date": "DATE",
        },
        "appointments": {
            "support_employee_id": "INTEGER",
            "prospect_name": "VARCHAR(160)",
            "discipline_interest": "VARCHAR(100)",
            "access_platform": "VARCHAR(80)",
            "consultation_note": "TEXT",
        },
    }

    with engine.begin() as connection:
        appointment_columns = {row[1]: row for row in connection.exec_driver_sql("PRAGMA table_info(appointments)")}
        if appointment_columns and appointment_columns.get("customer_id") and appointment_columns["customer_id"][3] == 1:
            connection.exec_driver_sql("ALTER TABLE appointments RENAME TO appointments_old")
            connection.exec_driver_sql("""
                CREATE TABLE appointments (
                    id INTEGER NOT NULL PRIMARY KEY,
                    customer_id INTEGER,
                    employee_id INTEGER,
                    support_employee_id INTEGER,
                    prospect_name VARCHAR(160),
                    discipline_interest VARCHAR(100),
                    access_platform VARCHAR(80),
                    scheduled_at DATETIME NOT NULL,
                    appointment_type VARCHAR(60) NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    note TEXT,
                    consultation_note TEXT,
                    FOREIGN KEY(customer_id) REFERENCES customers (id),
                    FOREIGN KEY(employee_id) REFERENCES employees (id),
                    FOREIGN KEY(support_employee_id) REFERENCES employees (id)
                )
            """)
            connection.exec_driver_sql("""
                INSERT INTO appointments (
                    id, customer_id, employee_id, scheduled_at, appointment_type, status, note,
                    prospect_name, discipline_interest, access_platform
                )
                SELECT
                    a.id,
                    a.customer_id,
                    a.employee_id,
                    a.scheduled_at,
                    a.appointment_type,
                    a.status,
                    a.note,
                    p.display_name,
                    a.appointment_type,
                    c.source
                FROM appointments_old a
                LEFT JOIN customers c ON c.id = a.customer_id
                LEFT JOIN people p ON p.id = c.person_id
            """)
            connection.exec_driver_sql("DROP TABLE appointments_old")

        for table_name, columns in additions.items():
            existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})")}
            for column_name, definition in columns.items():
                if column_name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

        connection.exec_driver_sql("UPDATE appointments SET status = 'Đã lên lịch' WHERE status IN ('scheduled', 'chưa')")


def seed_business_modules(db: Session) -> None:
    main_branch = db.query(Branch).filter(Branch.code == "MAIN").first() or db.query(Branch).first()
    west_branch = db.query(Branch).filter(Branch.code == "WEST").first() or main_branch

    extra_packages = [
        ("FIT-3M", "Fitness Unlimited 3 tháng", "Fitness", "time", 90, None, 1350000, False),
        ("FIT-6M", "Fitness Unlimited 6 tháng", "Fitness", "time", 180, None, 2500000, False),
        ("YOGA-12", "Yoga Mobility 12 buổi", "Yoga", "sessions", 60, 12, 1200000, False),
        ("PT-24", "Huấn luyện cá nhân 24 buổi", "PT", "sessions", 120, 24, 6500000, True),
        ("PT-DUO-12", "PT nhóm đôi 12 buổi", "PT", "sessions", 90, 12, 4200000, True),
    ]
    for code, name, category, package_type, duration_days, session_count, price, is_pt in extra_packages:
        if not db.query(ServicePackage).filter(ServicePackage.code == code).first():
            db.add(ServicePackage(code=code, name=name, category=category, package_type=package_type, duration_days=duration_days, session_count=session_count, price=price, is_pt=is_pt, is_active=True))
    db.commit()

    extra_employees = [
        ("EMP-0004", "Ngọc Hân", "0944444444", "Sale online", 8500000, main_branch),
        ("EMP-0005", "Vũ Minh Khoa", "0955555555", "Coach", 11000000, west_branch),
        ("EMP-0006", "Bùi Thanh Tâm", "0966666666", "Lễ tân", 8000000, west_branch),
    ]
    for code, name, phone, title, salary, branch in extra_employees:
        if not db.query(Employee).filter(Employee.employee_code == code).first():
            person = Person(display_name=name, phone=phone, email=None, gender=None, status="active", biometric_consent_status="accepted")
            db.add(person)
            db.flush()
            db.add(Employee(person_id=person.id, branch_id=branch.id if branch else None, employee_code=code, job_title=title, base_salary=salary, status="active"))
    db.commit()

    first_sale = db.query(Employee).filter(Employee.job_title.contains("Lễ tân")).first() or db.query(Employee).first()
    sales_online = db.query(Employee).filter(Employee.job_title.contains("Sale online")).first() or first_sale
    direct_sale = db.query(Employee).filter(Employee.job_title.contains("Lễ tân")).first() or first_sale
    coach = db.query(Employee).filter(Employee.job_title.contains("Coach")).first() or first_sale

    for appointment in db.query(Appointment).all():
        if appointment.status in ("scheduled", "chưa"):
            appointment.status = "Đã lên lịch"
        if not appointment.employee_id and direct_sale:
            appointment.employee_id = direct_sale.id
        if not appointment.prospect_name and appointment.customer:
            appointment.prospect_name = appointment.customer.person.display_name
        if not appointment.discipline_interest:
            appointment.discipline_interest = appointment.appointment_type or "GYM tự tập"
        if not appointment.access_platform and appointment.customer:
            appointment.access_platform = appointment.customer.source
    db.commit()

    customer_specs = [
        ("CUST-0005", "Đặng Gia Bảo", "0908889999", "Nam", "1995-04-12", "MBS-0005", "Instagram", "active", "Muốn giảm mỡ, thích tập buổi sáng.", sales_online, main_branch, "FIT-3M", 1350000, 500000, 80),
        ("CUST-0006", "Võ Nhật Vy", "0912223333", "Nữ", "1998-09-21", "MBS-0006", "TikTok", "active", "Quan tâm PT nhóm đôi, cần nhắc lịch đều.", direct_sale, west_branch, "PT-DUO-12", 4200000, 2000000, 75),
        ("CUST-0007", "Huỳnh Quốc Thái", "0924445555", "Nam", "1990-01-08", "MBS-0007", "Referral", "lead", "Đã xem phòng, chờ quyết định gói 6 tháng.", sales_online, main_branch, "FIT-6M", 2500000, 0, 180),
        ("CUST-0008", "Lâm An Nhiên", "0936667777", "Nữ", "2001-07-30", "MBS-0008", "Walk-in", "active", "Tập yoga phục hồi vai gáy.", direct_sale, west_branch, "YOGA-12", 1200000, 1200000, 60),
    ]
    for code, name, phone, gender, birthday, mbs, source, status, notes, sale_employee, branch, package_code, final_price, paid, expire_days in customer_specs:
        if not db.query(Customer).filter(Customer.customer_code == code).first():
            person = Person(display_name=name, phone=phone, email=None, gender=gender, date_of_birth=date.fromisoformat(birthday), status="active", biometric_consent_status="accepted")
            db.add(person)
            db.flush()
            customer = Customer(person_id=person.id, branch_id=branch.id if branch else None, customer_code=code, mbs_card_code=mbs, sales_employee_id=sale_employee.id if sale_employee else None, source=source, status=status, notes=notes)
            db.add(customer)
            db.flush()
            package = db.query(ServicePackage).filter(ServicePackage.code == package_code).first()
            if package:
                membership_id = (db.query(func.max(Membership.id)).scalar() or 0) + 1
                db.add(Membership(
                    customer_id=customer.id,
                    package_id=package.id,
                    code=f"MEM-{membership_id:04d}",
                    registered_at=date.today() - timedelta(days=10),
                    starts_at=date.today() - timedelta(days=8),
                    expires_at=date.today() + timedelta(days=expire_days),
                    remaining_sessions=package.session_count,
                    final_price=final_price,
                    deposit_amount=paid,
                    paid_amount=paid,
                    debt_amount=max(final_price - paid, 0),
                    debt_due_date=date.today() + timedelta(days=6) if final_price > paid else None,
                    sale_online_employee_id=sales_online.id if sales_online else None,
                    direct_sales_employee_id=direct_sale.id if direct_sale else None,
                    pt_converter_employee_id=coach.id if package.is_pt and coach else None,
                    status="active" if status == "active" else "pending",
                ))
    db.commit()

    if not db.query(BankAccount).first():
        db.add_all([
            BankAccount(code="VCB-PUBLIC", bank_name="Vietcombank", account_name="PULSEFIT STUDIO", account_number="1023456789", visibility="public", status="active"),
            BankAccount(code="MB-PRIVATE", bank_name="MB Bank", account_name="NGUYEN VAN CHU", account_number="8899001122", visibility="private", status="active"),
        ])
        db.commit()

    if not db.query(Appointment).first():
        employee = db.query(Employee).filter(Employee.job_title.contains("Lễ tân")).first() or db.query(Employee).first()
        if employee:
            db.add(Appointment(prospect_name="Nguyễn Minh Anh", employee_id=employee.id, discipline_interest="GYM tự tập", access_platform="Facebook", scheduled_at=datetime.utcnow() + timedelta(hours=4), appointment_type="Tư vấn", status="Đã lên lịch", note="Khách hẹn xem phòng và đo InBody."))
            db.commit()

    if db.query(Appointment).count() < 6:
        appointment_names = [
            ("Phạm Tuấn Kiệt", "PT 1:1", "TikTok", "Muốn giảm mỡ nhanh, hỏi lịch coach nam."),
            ("Trần Gia Hân", "Dance kid", "Facebook", "Phụ huynh hỏi lớp cuối tuần."),
            ("Lê Bảo Ngọc", "Yoga Mobility", "Instagram", "Đau vai gáy, muốn tập nhẹ."),
            ("Đỗ Minh Quân", "GYM tự tập", "Walk-in", "Gần nhà, cần xem giá 6 tháng."),
            ("Vũ Khánh Vy", "PT nhóm 1:2", "Zalo", "Đi cùng bạn, cân nhắc gói đôi."),
        ]
        for index, (name, discipline, platform, note) in enumerate(appointment_names, start=1):
            if not db.query(Appointment).filter(Appointment.prospect_name == name).first():
                db.add(Appointment(
                    customer_id=None,
                    employee_id=(direct_sale.id if direct_sale else None),
                    support_employee_id=(coach.id if index % 2 == 0 and coach else None),
                    prospect_name=name,
                    discipline_interest=discipline,
                    access_platform=platform,
                    scheduled_at=datetime.utcnow() + timedelta(days=index, hours=2),
                    appointment_type="Tư vấn",
                    status="Đã lên lịch" if index < 4 else "suy nghĩ thêm",
                    note=note,
                    consultation_note="",
                ))
        db.commit()

    if not db.query(Payment).first():
        public_account = db.query(BankAccount).filter(BankAccount.visibility == "public").first()
        memberships = db.query(Membership).limit(3).all()
        for index, membership in enumerate(memberships, start=1):
            method = "bank_transfer" if index == 2 else "cash"
            db.add(Payment(
                customer_id=membership.customer_id,
                membership_id=membership.id,
                bank_account_id=public_account.id if method == "bank_transfer" and public_account else None,
                payment_no=f"PAY-SEED-{index:03d}",
                paid_at=datetime.utcnow() - timedelta(days=index),
                amount=membership.deposit_amount or membership.paid_amount or 0,
                method=method,
                channel="public" if method == "bank_transfer" else "counter",
                shift_date=date.today() - timedelta(days=index),
                note="Phiếu thu demo từ dữ liệu nghiệp vụ",
            ))
        db.commit()

    if not db.query(Payment).filter(Payment.method == "bank_transfer").first():
        public_account = db.query(BankAccount).filter(BankAccount.visibility == "public").first()
        membership = db.query(Membership).order_by(Membership.id.desc()).first()
        if membership:
            db.add(Payment(
                customer_id=membership.customer_id,
                membership_id=membership.id,
                bank_account_id=public_account.id if public_account else None,
                payment_no=f"PAY-BANK-{membership.id:04d}",
                paid_at=datetime.utcnow() - timedelta(hours=2),
                amount=max((membership.deposit_amount or membership.paid_amount or 500000), 1),
                method="bank_transfer",
                channel="public",
                shift_date=date.today(),
                note="Giao dịch chuyển khoản demo để đối chiếu sao kê",
            ))
            db.commit()

    if db.query(Payment).count() < 10:
        public_account = db.query(BankAccount).filter(BankAccount.visibility == "public").first()
        private_account = db.query(BankAccount).filter(BankAccount.visibility == "private").first()
        methods = ["cash", "bank_transfer", "card", "apple_pay"]
        memberships = db.query(Membership).order_by(Membership.id.desc()).limit(8).all()
        for index, membership in enumerate(memberships, start=1):
            payment_no = f"PAY-DEMO-{membership.id:04d}"
            if db.query(Payment).filter(Payment.payment_no == payment_no).first():
                continue
            method = methods[index % len(methods)]
            account = public_account if method == "bank_transfer" else (private_account if method == "apple_pay" else None)
            amount = min(membership.final_price or 500000, max(membership.deposit_amount or 500000, 300000))
            db.add(Payment(
                customer_id=membership.customer_id,
                membership_id=membership.id,
                bank_account_id=account.id if account else None,
                payment_no=payment_no,
                paid_at=datetime.utcnow() - timedelta(days=index),
                amount=amount,
                method=method,
                channel=(account.visibility if account else "counter"),
                shift_date=date.today() - timedelta(days=index),
                note=f"Thanh toán mẫu bằng {method}",
            ))
        db.commit()

    if not db.query(PtGroup).first():
        coach = db.query(Employee).filter(Employee.job_title.contains("Coach")).first()
        pt_package = db.query(ServicePackage).filter(ServicePackage.is_pt == True).first()
        customer = db.query(Customer).filter(Customer.status == "active").first()
        membership = db.query(Membership).filter(Membership.customer_id == (customer.id if customer else 0)).first()
        if coach and customer:
            group = PtGroup(coach_id=coach.id, package_id=pt_package.id if pt_package else None, name="PT Sức mạnh buổi tối", group_type="1:2", schedule_label="Thứ 2-4-6, 19:00", capacity=2, status="active")
            db.add(group)
            db.flush()
            db.add(PtGroupMember(group_id=group.id, customer_id=customer.id, membership_id=membership.id if membership else None, status="active"))
            db.commit()

    if db.query(PtGroup).count() < 3 and coach:
        pt_packages = db.query(ServicePackage).filter(ServicePackage.is_pt == True).all()
        group_specs = [
            ("PT Duo Core 19h", "1:2", "Thứ 3-5, 19:00", 2),
            ("PT Strength 7h", "1:3", "Thứ 2-4-6, 07:00", 3),
        ]
        for index, (name, group_type, schedule, capacity) in enumerate(group_specs):
            if not db.query(PtGroup).filter(PtGroup.name == name).first():
                group = PtGroup(coach_id=coach.id, package_id=pt_packages[index % len(pt_packages)].id if pt_packages else None, name=name, group_type=group_type, schedule_label=schedule, capacity=capacity, status="active")
                db.add(group)
                db.flush()
                candidates = db.query(Customer).filter(Customer.status == "active").limit(capacity).all()
                for candidate in candidates:
                    if not db.query(PtGroupMember).filter(PtGroupMember.group_id == group.id, PtGroupMember.customer_id == candidate.id).first():
                        membership = db.query(Membership).filter(Membership.customer_id == candidate.id).first()
                        db.add(PtGroupMember(group_id=group.id, customer_id=candidate.id, membership_id=membership.id if membership else None, status="active"))
        db.commit()

    if not db.query(CashShift).first():
        branch = db.query(Branch).first()
        employee = db.query(Employee).filter(Employee.job_title.contains("Lễ tân")).first() or db.query(Employee).first()
        cash_total = db.query(func.sum(Payment.amount)).filter(Payment.method == "cash").scalar() or 0
        db.add(CashShift(branch_id=branch.id if branch else None, opened_by_employee_id=employee.id if employee else None, shift_date=date.today(), expected_amount=cash_total, counted_amount=cash_total, difference_amount=0, status="open"))
        db.commit()

    if db.query(CashShift).count() < 3:
        branches = [branch for branch in [main_branch, west_branch] if branch]
        for index, branch in enumerate(branches, start=1):
            shift_date = date.today() - timedelta(days=index)
            if not db.query(CashShift).filter(CashShift.branch_id == branch.id, CashShift.shift_date == shift_date).first():
                expected = db.query(func.sum(Payment.amount)).filter(Payment.method == "cash", Payment.shift_date == shift_date).scalar() or 750000
                counted = expected - (50000 if index == 2 else 0)
                db.add(CashShift(branch_id=branch.id, opened_by_employee_id=direct_sale.id if direct_sale else None, shift_date=shift_date, expected_amount=expected, counted_amount=counted, difference_amount=counted - expected, status="closed"))
        db.commit()

    if not db.query(CommissionLedger).first():
        sale = db.query(Employee).filter(Employee.job_title.contains("Lễ tân")).first() or db.query(Employee).first()
        coach = db.query(Employee).filter(Employee.job_title.contains("Coach")).first() or db.query(Employee).first()
        membership = db.query(Membership).first()
        if sale and membership:
            db.add(CommissionLedger(employee_id=sale.id, membership_id=membership.id, role="direct_sale", base_amount=membership.final_price or 0, rate_percent=4, commission_amount=(membership.final_price or 0) * 0.04, earned_at=date.today(), status="pending"))
        if coach and membership:
            db.add(CommissionLedger(employee_id=coach.id, membership_id=membership.id, role="pt_convert", base_amount=membership.final_price or 0, rate_percent=3, commission_amount=(membership.final_price or 0) * 0.03, earned_at=date.today(), status="pending"))
        db.commit()

    if db.query(CommissionLedger).count() < 10:
        memberships = db.query(Membership).limit(8).all()
        for membership in memberships:
            specs = [
                (membership.sale_online_employee_id or (sales_online.id if sales_online else None), "sale_online", 2.0),
                (membership.direct_sales_employee_id or (direct_sale.id if direct_sale else None), "direct_sale", 4.0),
                (membership.pt_converter_employee_id or (coach.id if coach and membership.package and membership.package.is_pt else None), "pt_convert", 3.0),
            ]
            for employee_id, role, rate in specs:
                if not employee_id:
                    continue
                exists = db.query(CommissionLedger).filter(CommissionLedger.membership_id == membership.id, CommissionLedger.employee_id == employee_id, CommissionLedger.role == role).first()
                if exists:
                    continue
                base_amount = membership.final_price or 0
                db.add(CommissionLedger(employee_id=employee_id, membership_id=membership.id, role=role, base_amount=base_amount, rate_percent=rate, commission_amount=base_amount * rate / 100, earned_at=membership.registered_at or date.today(), status="pending"))
        db.commit()

    if db.query(AttendanceSession).count() < 12:
        customers = db.query(Customer).filter(Customer.status.in_(["active", "lead"])).all()
        for index, customer in enumerate(customers, start=1):
            for visit in range(2):
                checked_in = datetime.utcnow() - timedelta(days=index + visit, hours=visit + 1)
                exists = db.query(AttendanceSession).filter(AttendanceSession.customer_id == customer.id, AttendanceSession.checked_in_at == checked_in).first()
                if exists:
                    continue
                db.add(AttendanceSession(customer_id=customer.id, checked_in_at=checked_in, checked_out_at=checked_in + timedelta(hours=1, minutes=20), source="manual", result="allowed" if customer.status == "active" else "need_review", status="closed", note="Check-in mẫu"))
        db.commit()

    extra_devices = [
        ("DEV-WEST-LOBBY", west_branch, "Cổng nhận diện West", "DAH-1017", "192.168.2.70", "shared", "online", 0, 0),
        ("DEV-TURNSTILE", main_branch, "Cổng xoay phòng tạ", "DAH-1017", "192.168.1.72", "customer", "online", 1, 0),
    ]
    for code, branch, name, model, ip, purpose, status, pending_jobs, errors in extra_devices:
        if not db.query(Device).filter(Device.code == code).first():
            db.add(Device(branch_id=branch.id if branch else None, code=code, name=name, model=model, ip_address=ip, purpose=purpose, status=status, pending_jobs=pending_jobs, errors_24h=errors, last_heartbeat_at=datetime.utcnow()))
    db.commit()


@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema()
    with next(get_db()) as db:
        seed_database(db)
        seed_business_modules(db)


@app.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    soon = today + timedelta(days=7)
    stats = {
        "active_customers": db.query(Customer).filter(Customer.status == "active").count(),
        "active_memberships": db.query(Membership).filter(Membership.status == "active").count(),
        "open_sessions": db.query(AttendanceSession).filter(AttendanceSession.status == "open").count(),
        "employees": db.query(Employee).filter(Employee.status == "active").count(),
        "debt": db.query(func.sum(Membership.debt_amount)).scalar() or 0,
        "debt_due_soon": db.query(Membership).filter(Membership.debt_amount > 0, Membership.debt_due_date <= soon).count(),
        "device_errors": db.query(func.sum(Device.errors_24h)).scalar() or 0,
    }
    recent_sessions = (
        db.query(AttendanceSession)
        .options(joinedload(AttendanceSession.customer).joinedload(Customer.person))
        .order_by(AttendanceSession.checked_in_at.desc())
        .limit(6)
        .all()
    )
    expiring = (
        db.query(Membership)
        .options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package))
        .order_by(Membership.expires_at.asc())
        .limit(6)
        .all()
    )
    devices = db.query(Device).options(joinedload(Device.branch)).order_by(Device.errors_24h.desc()).all()
    return templates.TemplateResponse(
        "dashboard.html",
        {"request": request, "stats": stats, "recent_sessions": recent_sessions, "expiring": expiring, "devices": devices, "active": "dashboard"},
    )


@app.get("/customers")
def customers(request: Request, q: str = "", db: Session = Depends(get_db)):
    query = db.query(Customer).options(joinedload(Customer.person), joinedload(Customer.branch), joinedload(Customer.sales_employee).joinedload(Employee.person))
    if q:
        query = query.join(Customer.person).filter(or_(Person.display_name.contains(q), Person.phone.contains(q), Customer.customer_code.contains(q)))
    rows = query.order_by(Customer.id.desc()).all()
    branches = db.query(Branch).all()
    employees = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").order_by(Employee.id.desc()).all()
    return templates.TemplateResponse("customers.html", {"request": request, "customers": rows, "branches": branches, "employees": employees, "q": q, "active": "customers"})


@app.post("/customers")
def create_customer(
    display_name: str = Form(...),
    phone: str = Form(""),
    gender: str = Form(""),
    date_of_birth: str = Form(""),
    mbs_card_code: str = Form(""),
    sales_employee_id: str = Form(""),
    branch_id: str = Form(""),
    source: str = Form("Khách vãng lai"),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    next_id = (db.query(func.max(Customer.id)).scalar() or 0) + 1
    birthday = date.fromisoformat(date_of_birth) if date_of_birth else None
    person = Person(display_name=display_name, phone=phone, gender=gender or None, date_of_birth=birthday, status="active", biometric_consent_status="not_requested")
    db.add(person)
    db.flush()
    fallback_branch = db.query(Branch).first()
    branch_pk = optional_int(branch_id) or (fallback_branch.id if fallback_branch else None)
    db.add(Customer(person_id=person.id, branch_id=branch_pk, customer_code=f"CUST-{next_id:04d}", mbs_card_code=mbs_card_code or None, sales_employee_id=optional_int(sales_employee_id), source=source, notes=notes or None, status="lead"))
    db.commit()
    return redirect_with_toast("/customers", "Đã thêm khách hàng mới.")


@app.get("/customers/{customer_id}")
def customer_detail(customer_id: int, request: Request, db: Session = Depends(get_db)):
    customer = db.query(Customer).options(
        joinedload(Customer.person),
        joinedload(Customer.branch),
        joinedload(Customer.sales_employee).joinedload(Employee.person),
        joinedload(Customer.memberships).joinedload(Membership.package),
    ).filter(Customer.id == customer_id).first()
    if not customer:
        return redirect_with_toast("/customers", "Không tìm thấy khách hàng.", "error")

    branches = db.query(Branch).all()
    employees = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").order_by(Employee.id.desc()).all()
    packages = db.query(ServicePackage).filter(ServicePackage.is_active == True).order_by(ServicePackage.category, ServicePackage.price).all()
    bank_accounts = db.query(BankAccount).filter(BankAccount.status == "active").all()
    memberships = db.query(Membership).options(
        joinedload(Membership.package),
        joinedload(Membership.sale_online_employee).joinedload(Employee.person),
        joinedload(Membership.direct_sales_employee).joinedload(Employee.person),
        joinedload(Membership.pt_converter_employee).joinedload(Employee.person),
    ).filter(Membership.customer_id == customer.id).order_by(Membership.registered_at.desc()).all()
    appointments = db.query(Appointment).options(joinedload(Appointment.employee).joinedload(Employee.person)).filter(Appointment.customer_id == customer.id).order_by(Appointment.scheduled_at.desc()).all()
    pt_memberships = db.query(PtGroupMember).options(joinedload(PtGroupMember.group).joinedload(PtGroup.coach).joinedload(Employee.person), joinedload(PtGroupMember.membership).joinedload(Membership.package)).filter(PtGroupMember.customer_id == customer.id).order_by(PtGroupMember.joined_at.desc()).all()
    attendances = db.query(AttendanceSession).filter(AttendanceSession.customer_id == customer.id).order_by(AttendanceSession.checked_in_at.desc()).limit(20).all()
    payments = db.query(Payment).options(joinedload(Payment.membership).joinedload(Membership.package), joinedload(Payment.bank_account)).filter(Payment.customer_id == customer.id).order_by(Payment.paid_at.desc()).all()
    totals = {
        "paid": sum(payment.amount or 0 for payment in payments),
        "debt": sum(membership.debt_amount or 0 for membership in memberships),
        "active_memberships": sum(1 for membership in memberships if membership.status == "active"),
        "visits": len(attendances),
    }
    return templates.TemplateResponse(
        "customer_detail.html",
        {
            "request": request,
            "customer": customer,
            "branches": branches,
            "employees": employees,
            "packages": packages,
            "bank_accounts": bank_accounts,
            "memberships": memberships,
            "appointments": appointments,
            "pt_memberships": pt_memberships,
            "attendances": attendances,
            "payments": payments,
            "totals": totals,
            "today": date.today(),
            "active": "customers",
        },
    )


@app.post("/customers/{customer_id}")
def update_customer(
    customer_id: int,
    display_name: str = Form(...),
    phone: str = Form(""),
    gender: str = Form(""),
    date_of_birth: str = Form(""),
    mbs_card_code: str = Form(""),
    sales_employee_id: str = Form(""),
    branch_id: str = Form(""),
    source: str = Form("Khách vãng lai"),
    status: str = Form("lead"),
    notes: str = Form(""),
    db: Session = Depends(get_db),
):
    customer = db.query(Customer).options(joinedload(Customer.person)).filter(Customer.id == customer_id).first()
    if not customer:
        return redirect_with_toast("/customers", "Không tìm thấy khách hàng.", "error")

    customer.person.display_name = display_name
    customer.person.phone = phone or None
    customer.person.gender = gender or None
    customer.person.date_of_birth = date.fromisoformat(date_of_birth) if date_of_birth else None
    customer.mbs_card_code = mbs_card_code or None
    customer.sales_employee_id = optional_int(sales_employee_id)
    fallback_branch = db.query(Branch).first()
    customer.branch_id = optional_int(branch_id) or (fallback_branch.id if fallback_branch else None)
    customer.source = source or None
    customer.status = status
    customer.notes = notes or None
    db.commit()
    return redirect_with_toast(f"/customers/{customer_id}", "Đã lưu thông tin khách hàng.")


@app.post("/customers/{customer_id}/memberships")
async def create_customer_membership(
    customer_id: int,
    package_id: str = Form(""),
    registered_at: str = Form(""),
    starts_at: str = Form(""),
    expires_at: str = Form(""),
    final_price: str = Form("0"),
    deposit_amount: str = Form("0"),
    debt_due_date: str = Form(""),
    payment_method: str = Form("cash"),
    bank_account_id: str = Form(""),
    sale_online_employee_id: str = Form(""),
    direct_sales_employee_id: str = Form(""),
    pt_converter_employee_id: str = Form(""),
    receipt_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    customer = db.get(Customer, customer_id)
    package_pk = optional_int(package_id)
    if not customer:
        return redirect_with_toast("/customers", "Không tìm thấy khách hàng.", "error")
    if not package_pk:
        return redirect_with_toast(f"/customers/{customer_id}", "Cần chọn gói đăng ký.", "error")

    next_id = (db.query(func.max(Membership.id)).scalar() or 0) + 1
    package = db.get(ServicePackage, package_pk)
    final_price_value = money_value(final_price, package.price if package else 0)
    if final_price_value <= 0 and package:
        final_price_value = package.price
    deposit_amount_value = money_value(deposit_amount)
    debt_amount = max(final_price_value - deposit_amount_value, 0)
    receipt_path = None
    bank_account_pk = optional_int(bank_account_id)
    sale_online_employee_pk = optional_int(sale_online_employee_id)
    direct_sales_employee_pk = optional_int(direct_sales_employee_id)
    pt_converter_employee_pk = optional_int(pt_converter_employee_id)

    if receipt_image and receipt_image.filename:
        suffix = Path(receipt_image.filename).suffix.lower() or ".jpg"
        filename = f"receipt-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{next_id}{suffix}"
        target = Path("app/static/receipts") / filename
        target.write_bytes(await receipt_image.read())
        receipt_path = f"/static/receipts/{filename}"

    membership = Membership(
        customer_id=customer.id,
        package_id=package_pk,
        code=f"MEM-{next_id:04d}",
        registered_at=date.fromisoformat(registered_at) if registered_at else date.today(),
        starts_at=date.fromisoformat(starts_at) if starts_at else date.today(),
        expires_at=date.fromisoformat(expires_at) if expires_at else None,
        remaining_sessions=package.session_count if package else None,
        final_price=final_price_value,
        deposit_amount=deposit_amount_value,
        paid_amount=deposit_amount_value,
        debt_amount=debt_amount,
        debt_due_date=date.fromisoformat(debt_due_date) if debt_due_date else None,
        sale_online_employee_id=sale_online_employee_pk,
        direct_sales_employee_id=direct_sales_employee_pk,
        pt_converter_employee_id=pt_converter_employee_pk,
        status="active",
    )
    db.add(membership)
    db.flush()

    if deposit_amount_value > 0:
        db.add(Payment(
            customer_id=customer.id,
            membership_id=membership.id,
            payment_no=f"PAY-{membership.id:04d}-001",
            paid_at=datetime.utcnow(),
            amount=deposit_amount_value,
            method=payment_method,
            bank_account_id=bank_account_pk,
            channel="public" if bank_account_pk else "counter",
            shift_date=date.today(),
            receipt_image_path=receipt_path,
            note="Tiền cọc đăng ký gói",
        ))

    commission_specs = [
        (sale_online_employee_pk, "sale_online", 2.0),
        (direct_sales_employee_pk, "direct_sale", 4.0),
        (pt_converter_employee_pk, "pt_convert", 3.0),
    ]
    for employee_id, role, rate in commission_specs:
        if employee_id:
            db.add(CommissionLedger(
                employee_id=employee_id,
                membership_id=membership.id,
                role=role,
                base_amount=final_price_value,
                rate_percent=rate,
                commission_amount=final_price_value * rate / 100,
                earned_at=date.today(),
                status="pending",
            ))

    customer.status = "active"
    db.commit()
    return redirect_with_toast(f"/customers/{customer.id}", "Đã đăng ký gói cho khách.")


@app.get("/employees")
def employees(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Employee).options(joinedload(Employee.person), joinedload(Employee.branch)).order_by(Employee.id.desc()).all()
    branches = db.query(Branch).all()
    return templates.TemplateResponse("employees.html", {"request": request, "employees": rows, "branches": branches, "active": "employees"})


@app.post("/employees")
def create_employee(display_name: str = Form(...), phone: str = Form(""), job_title: str = Form("Coach"), branch_id: str = Form(""), db: Session = Depends(get_db)):
    next_id = (db.query(func.max(Employee.id)).scalar() or 0) + 1
    person = Person(display_name=display_name, phone=phone, status="active", biometric_consent_status="not_requested")
    db.add(person)
    db.flush()
    fallback_branch = db.query(Branch).first()
    db.add(Employee(person_id=person.id, branch_id=optional_int(branch_id) or (fallback_branch.id if fallback_branch else None), employee_code=f"EMP-{next_id:04d}", job_title=job_title, base_salary=0, status="active"))
    db.commit()
    return redirect_with_toast("/employees", "Đã thêm nhân viên.")


@app.get("/packages")
def packages(request: Request, db: Session = Depends(get_db)):
    rows = db.query(ServicePackage).order_by(ServicePackage.category, ServicePackage.price).all()
    return templates.TemplateResponse("packages.html", {"request": request, "packages": rows, "active": "packages"})


@app.post("/packages")
def create_package(name: str = Form(...), category: str = Form("Fitness"), package_type: str = Form("time"), price: str = Form("0"), duration_days: str = Form(""), session_count: str = Form(""), db: Session = Depends(get_db)):
    next_id = (db.query(func.max(ServicePackage.id)).scalar() or 0) + 1
    db.add(ServicePackage(code=f"PKG-{next_id:04d}", name=name, category=category, package_type=package_type, duration_days=optional_int(duration_days), session_count=optional_int(session_count), price=money_value(price), is_pt=category.upper() == "PT", is_active=True))
    db.commit()
    return redirect_with_toast("/packages", "Đã thêm gói dịch vụ.")


@app.get("/memberships")
def memberships(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Membership).options(
        joinedload(Membership.customer).joinedload(Customer.person),
        joinedload(Membership.package),
        joinedload(Membership.sale_online_employee).joinedload(Employee.person),
        joinedload(Membership.direct_sales_employee).joinedload(Employee.person),
        joinedload(Membership.pt_converter_employee).joinedload(Employee.person),
    ).order_by(Membership.id.desc()).all()
    customers = db.query(Customer).options(joinedload(Customer.person)).order_by(Customer.id.desc()).all()
    packages = db.query(ServicePackage).filter(ServicePackage.is_active == True).order_by(ServicePackage.category, ServicePackage.price).all()
    employees = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").all()
    bank_accounts = db.query(BankAccount).filter(BankAccount.status == "active").all()
    return templates.TemplateResponse("memberships.html", {"request": request, "memberships": rows, "customers": customers, "packages": packages, "employees": employees, "bank_accounts": bank_accounts, "active": "memberships", "today": date.today()})


@app.post("/memberships")
async def create_membership(
    customer_id: str = Form(""),
    package_id: str = Form(""),
    registered_at: str = Form(""),
    starts_at: str = Form(""),
    expires_at: str = Form(""),
    final_price: str = Form("0"),
    deposit_amount: str = Form("0"),
    debt_due_date: str = Form(""),
    payment_method: str = Form("cash"),
    bank_account_id: str = Form(""),
    sale_online_employee_id: str = Form(""),
    direct_sales_employee_id: str = Form(""),
    pt_converter_employee_id: str = Form(""),
    receipt_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    customer_pk = optional_int(customer_id)
    package_pk = optional_int(package_id)
    if not customer_pk or not package_pk:
        return redirect_with_toast("/memberships", "Cần chọn khách hàng và dịch vụ đăng ký.", "error")

    next_id = (db.query(func.max(Membership.id)).scalar() or 0) + 1
    package = db.get(ServicePackage, package_pk)
    final_price_value = money_value(final_price)
    deposit_amount_value = money_value(deposit_amount)
    debt_amount = max(final_price_value - deposit_amount_value, 0)
    receipt_path = None
    bank_account_pk = optional_int(bank_account_id)
    sale_online_employee_pk = optional_int(sale_online_employee_id)
    direct_sales_employee_pk = optional_int(direct_sales_employee_id)
    pt_converter_employee_pk = optional_int(pt_converter_employee_id)

    if receipt_image and receipt_image.filename:
        suffix = Path(receipt_image.filename).suffix.lower() or ".jpg"
        filename = f"receipt-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{next_id}{suffix}"
        target = Path("app/static/receipts") / filename
        target.write_bytes(await receipt_image.read())
        receipt_path = f"/static/receipts/{filename}"

    membership = Membership(
        customer_id=customer_pk,
        package_id=package_pk,
        code=f"MEM-{next_id:04d}",
        registered_at=date.fromisoformat(registered_at) if registered_at else date.today(),
        starts_at=date.fromisoformat(starts_at) if starts_at else date.today(),
        expires_at=date.fromisoformat(expires_at) if expires_at else None,
        remaining_sessions=package.session_count if package else None,
        final_price=final_price_value,
        deposit_amount=deposit_amount_value,
        paid_amount=deposit_amount_value,
        debt_amount=debt_amount,
        debt_due_date=date.fromisoformat(debt_due_date) if debt_due_date else None,
        sale_online_employee_id=sale_online_employee_pk,
        direct_sales_employee_id=direct_sales_employee_pk,
        pt_converter_employee_id=pt_converter_employee_pk,
        status="active",
    )
    db.add(membership)
    db.flush()

    if deposit_amount_value > 0:
        db.add(Payment(
            customer_id=customer_pk,
            membership_id=membership.id,
            payment_no=f"PAY-{membership.id:04d}-001",
            paid_at=datetime.utcnow(),
            amount=deposit_amount_value,
            method=payment_method,
            bank_account_id=bank_account_pk,
            channel="public" if bank_account_pk else "counter",
            shift_date=date.today(),
            receipt_image_path=receipt_path,
            note="Tiền cọc đăng ký gói",
        ))

    commission_specs = [
        (sale_online_employee_pk, "sale_online", 2.0),
        (direct_sales_employee_pk, "direct_sale", 4.0),
        (pt_converter_employee_pk, "pt_convert", 3.0),
    ]
    for employee_id, role, rate in commission_specs:
        if employee_id:
            db.add(CommissionLedger(
                employee_id=employee_id,
                membership_id=membership.id,
                role=role,
                base_amount=final_price_value,
                rate_percent=rate,
                commission_amount=final_price_value * rate / 100,
                earned_at=date.today(),
                status="pending",
            ))

    db.commit()
    return redirect_with_toast("/memberships", "Đã đăng ký gói cho khách.")


@app.get("/check-in")
def check_in(request: Request, db: Session = Depends(get_db)):
    customers = db.query(Customer).options(joinedload(Customer.person)).filter(Customer.status.in_(["active", "lead"])).all()
    sessions = db.query(AttendanceSession).options(joinedload(AttendanceSession.customer).joinedload(Customer.person)).order_by(AttendanceSession.checked_in_at.desc()).limit(12).all()
    return templates.TemplateResponse("checkin.html", {"request": request, "customers": customers, "sessions": sessions, "active": "checkin"})


@app.post("/check-in")
def create_check_in(customer_id: str = Form(""), note: str = Form(""), db: Session = Depends(get_db)):
    customer_pk = optional_int(customer_id)
    if not customer_pk:
        return redirect_with_toast("/check-in", "Cần chọn khách hàng để check-in.", "error")
    customer = db.get(Customer, customer_pk)
    result = "allowed" if customer and customer.status == "active" else "need_review"
    db.add(AttendanceSession(customer_id=customer_pk, checked_in_at=datetime.utcnow(), source="manual", result=result, status="open", note=note))
    db.commit()
    return redirect_with_toast("/check-in", "Đã ghi nhận check-in.")


@app.post("/check-in/{session_id}/checkout")
def checkout(session_id: int, db: Session = Depends(get_db)):
    session = db.get(AttendanceSession, session_id)
    if session:
        session.checked_out_at = datetime.utcnow()
        session.status = "closed"
        db.commit()
    return redirect_with_toast("/check-in", "Đã checkout phiên tập.")


@app.get("/appointments")
def appointments(request: Request, tab: str = "pending", db: Session = Depends(get_db)):
    active_tab = "closed" if tab == "closed" else "pending"
    query = db.query(Appointment).options(
        joinedload(Appointment.customer).joinedload(Customer.person),
        joinedload(Appointment.employee).joinedload(Employee.person),
        joinedload(Appointment.support_employee).joinedload(Employee.person),
    )
    if active_tab == "closed":
        query = query.filter(Appointment.status == "đã chốt")
    else:
        query = query.filter(Appointment.status != "đã chốt")
    rows = query.order_by(Appointment.scheduled_at.asc()).all()
    counts = {
        "pending": db.query(Appointment).filter(Appointment.status != "đã chốt").count(),
        "closed": db.query(Appointment).filter(Appointment.status == "đã chốt").count(),
    }
    employees = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").all()
    return templates.TemplateResponse("appointments.html", {"request": request, "appointments": rows, "employees": employees, "counts": counts, "active_tab": active_tab, "active": "appointments"})


@app.post("/appointments")
def create_appointment(
    prospect_name: str = Form(""),
    discipline_interest: str = Form(""),
    employee_id: str = Form(""),
    note: str = Form(""),
    appointment_date: str = Form(""),
    appointment_time: str = Form(""),
    access_platform: str = Form(""),
    db: Session = Depends(get_db),
):
    employee_pk = optional_int(employee_id)
    if not prospect_name.strip() or not discipline_interest.strip() or not employee_pk or not appointment_date or not appointment_time:
        return redirect_with_toast("/appointments", "Cần nhập tên khách, bộ môn, nhân viên chăm sóc, ngày và giờ hẹn.", "error")
    db.add(Appointment(
        prospect_name=prospect_name.strip(),
        discipline_interest=discipline_interest.strip(),
        employee_id=employee_pk,
        support_employee_id=None,
        scheduled_at=datetime.fromisoformat(f"{appointment_date}T{appointment_time}"),
        appointment_type="Tư vấn",
        status="Đã lên lịch",
        note=note or None,
        access_platform=access_platform or None,
        consultation_note=None,
    ))
    db.commit()
    return redirect_with_toast("/appointments", "Đã tạo lịch hẹn.")


@app.get("/appointments/{appointment_id}/process")
@app.get("/appointments/{appointment_id}/edit")
def process_appointment(appointment_id: int, request: Request, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).options(
        joinedload(Appointment.employee).joinedload(Employee.person),
        joinedload(Appointment.support_employee).joinedload(Employee.person),
        joinedload(Appointment.customer).joinedload(Customer.person),
    ).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return redirect_with_toast("/appointments", "Không tìm thấy lịch hẹn.", "error")
    employees = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").all()
    return templates.TemplateResponse("appointment_edit.html", {"request": request, "appointment": appointment, "employees": employees, "active": "appointments"})


@app.post("/appointments/{appointment_id}/process")
@app.post("/appointments/{appointment_id}/edit")
def update_appointment(
    appointment_id: int,
    prospect_name: str = Form(""),
    discipline_interest: str = Form(""),
    employee_id: str = Form(""),
    note: str = Form(""),
    appointment_date: str = Form(""),
    appointment_time: str = Form(""),
    access_platform: str = Form(""),
    support_employee_id: str = Form(""),
    status: str = Form("Đã lên lịch"),
    consultation_note: str = Form(""),
    action: str = Form("save"),
    db: Session = Depends(get_db),
):
    appointment = db.get(Appointment, appointment_id)
    employee_pk = optional_int(employee_id)
    if not appointment:
        return redirect_with_toast("/appointments", "Không tìm thấy lịch hẹn.", "error")
    if not prospect_name.strip() or not discipline_interest.strip() or not employee_pk or not appointment_date or not appointment_time:
        return redirect_with_toast(f"/appointments/{appointment_id}/process", "Cần nhập tên khách, bộ môn, nhân viên chăm sóc, ngày và giờ hẹn.", "error")
    appointment.prospect_name = prospect_name.strip()
    appointment.discipline_interest = discipline_interest.strip()
    appointment.employee_id = employee_pk
    appointment.support_employee_id = optional_int(support_employee_id)
    appointment.scheduled_at = datetime.fromisoformat(f"{appointment_date}T{appointment_time}")
    appointment.access_platform = access_platform or None
    appointment.status = status
    appointment.note = note or None
    appointment.consultation_note = consultation_note or None
    db.commit()
    if action == "closed":
        return redirect_with_toast(f"/appointments/{appointment_id}/convert", "Đã lưu lịch hẹn. Tiếp tục tạo khách từ lịch hẹn.")
    return redirect_with_toast("/appointments", "Đã cập nhật lịch hẹn.")


@app.get("/appointments/{appointment_id}/convert")
def convert_appointment_form(appointment_id: int, request: Request, db: Session = Depends(get_db)):
    appointment = db.query(Appointment).options(joinedload(Appointment.employee).joinedload(Employee.person)).filter(Appointment.id == appointment_id).first()
    if not appointment:
        return redirect_with_toast("/appointments", "Không tìm thấy lịch hẹn.", "error")
    packages = db.query(ServicePackage).filter(ServicePackage.is_active == True).order_by(ServicePackage.category, ServicePackage.price).all()
    employees = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").all()
    source_value = appointment.access_platform or ""
    source_options = ["Facebook", "TikTok", "Instagram", "Zalo", "Walk-in", "Giới thiệu", "Website", "Hotline", "Khác"]
    if source_value and source_value not in source_options:
        source_options = [source_value, *source_options]
    return templates.TemplateResponse("appointment_convert.html", {"request": request, "appointment": appointment, "packages": packages, "employees": employees, "source_options": source_options, "source_value": source_value, "active": "appointments"})


@app.post("/appointments/{appointment_id}/convert")
def convert_appointment(
    appointment_id: int,
    display_name: str = Form(""),
    phone: str = Form(""),
    gender: str = Form(""),
    date_of_birth: str = Form(""),
    mbs_card_code: str = Form(""),
    sales_employee_id: str = Form(""),
    source: str = Form(""),
    notes: str = Form(""),
    package_ids: list[str] = Form([]),
    deposit_amount: str = Form("0"),
    debt_due_date: str = Form(""),
    payment_method: str = Form("cash"),
    db: Session = Depends(get_db),
):
    appointment = db.get(Appointment, appointment_id)
    package_pks = [package_pk for package_pk in (optional_int(value) for value in package_ids) if package_pk]
    if not appointment:
        return redirect_with_toast("/appointments", "Không tìm thấy lịch hẹn.", "error")
    if not display_name.strip() or not package_pks:
        return redirect_with_toast(f"/appointments/{appointment_id}/convert", "Cần nhập tên khách và chọn ít nhất một gói đăng ký.", "error")

    selected_packages = db.query(ServicePackage).filter(ServicePackage.id.in_(package_pks), ServicePackage.is_active == True).all()
    selected_by_id = {package.id: package for package in selected_packages}
    ordered_packages = [selected_by_id[package_pk] for package_pk in package_pks if package_pk in selected_by_id]
    if not ordered_packages:
        return redirect_with_toast(f"/appointments/{appointment_id}/convert", "Danh sách gói đăng ký không hợp lệ.", "error")

    try:
        next_customer_id = (db.query(func.max(Customer.id)).scalar() or 0) + 1
        birthday = date.fromisoformat(date_of_birth) if date_of_birth else None
        person = Person(display_name=display_name.strip(), phone=phone or None, gender=gender or None, date_of_birth=birthday, status="active", biometric_consent_status="not_requested")
        db.add(person)
        db.flush()

        fallback_branch = db.query(Branch).first()
        customer = Customer(
            person_id=person.id,
            branch_id=fallback_branch.id if fallback_branch else None,
            customer_code=f"CUST-{next_customer_id:04d}",
            mbs_card_code=mbs_card_code or None,
            sales_employee_id=optional_int(sales_employee_id),
            source=source or appointment.access_platform,
            notes=notes or appointment.note,
            status="active",
        )
        db.add(customer)
        db.flush()

        total_price = sum(package.price or 0 for package in ordered_packages)
        deposit_amount_value = money_value(deposit_amount)
        next_membership_id = (db.query(func.max(Membership.id)).scalar() or 0) + 1
        remaining_deposit = min(deposit_amount_value, total_price)
        created_memberships = []
        direct_sales_employee_id = optional_int(sales_employee_id) or appointment.employee_id
        for offset, package in enumerate(ordered_packages):
            package_price = package.price or 0
            paid_for_package = min(remaining_deposit, package_price)
            remaining_deposit -= paid_for_package
            membership = Membership(
                customer_id=customer.id,
                package_id=package.id,
                code=f"MEM-{next_membership_id + offset:04d}",
                registered_at=appointment.scheduled_at.date(),
                starts_at=appointment.scheduled_at.date(),
                expires_at=appointment.scheduled_at.date() + timedelta(days=package.duration_days) if package.duration_days else None,
                remaining_sessions=package.session_count,
                final_price=package_price,
                deposit_amount=paid_for_package,
                paid_amount=paid_for_package,
                debt_amount=max(package_price - paid_for_package, 0),
                debt_due_date=date.fromisoformat(debt_due_date) if debt_due_date and package_price > paid_for_package else None,
                direct_sales_employee_id=direct_sales_employee_id,
                status="active",
            )
            db.add(membership)
            db.flush()
            created_memberships.append(membership)

            if paid_for_package > 0:
                db.add(Payment(
                    customer_id=customer.id,
                    membership_id=membership.id,
                    bank_account_id=None,
                    payment_no=f"PAY-{membership.id:04d}-001",
                    paid_at=datetime.utcnow(),
                    amount=paid_for_package,
                    method=payment_method,
                    channel="counter",
                    shift_date=date.today(),
                    note="Tiền cọc từ lịch hẹn đã chốt",
                ))

        appointment.customer_id = customer.id
        appointment.status = "đã chốt"
        appointment.consultation_note = appointment.consultation_note or f"Đã chuyển thành khách hàng và đăng ký {len(created_memberships)} gói."
        db.commit()
    except Exception:
        db.rollback()
        return redirect_with_toast(f"/appointments/{appointment_id}/convert", "Tạo khách chưa thành công, lịch hẹn vẫn giữ nguyên trạng thái.", "error")
    return redirect_with_toast(f"/customers/{customer.id}", "Đã chốt lịch hẹn và tạo khách hàng.")


@app.get("/pt-groups")
def pt_groups(request: Request, q: str = "", status: str = "active", partial: str = "", db: Session = Depends(get_db)):
    if partial:
        return JSONResponse({"ok": True, "fragment": render_pt_groups_fragment(db, request, q, status), "target": "#pt-groups-list"})
    context = pt_groups_context(db, q, status)
    context["request"] = request
    context["active"] = "pt_groups"
    return templates.TemplateResponse("pt_groups.html", context)


@app.post("/pt-groups")
def create_pt_group(request: Request, q: str = "", status: str = "active", coach_id: str = Form(""), package_id: str = Form(""), name: str = Form(...), group_type: str = Form("1:1"), schedule_label: str = Form(""), capacity: str = Form("1"), db: Session = Depends(get_db)):
    coach_pk = optional_int(coach_id)
    if not coach_pk:
        if wants_json(request):
            return JSONResponse({"ok": False, "message": "Cần chọn coach cho nhóm PT."}, status_code=400)
        return redirect_with_toast("/pt-groups", "Cần chọn coach cho nhóm PT.", "error")
    db.add(PtGroup(coach_id=coach_pk, package_id=optional_int(package_id), name=name, group_type=group_type, schedule_label=schedule_label or None, capacity=int_value(capacity, 1), status="active"))
    db.commit()
    if wants_json(request):
        return pt_groups_json(db, request, "Đã tạo nhóm PT.", q, status)
    return redirect_with_toast("/pt-groups", "Đã tạo nhóm PT.")


@app.post("/pt-groups/{group_id}/edit")
def update_pt_group(
    group_id: int,
    request: Request,
    q: str = "",
    status_filter: str = "active",
    coach_id: str = Form(""),
    package_id: str = Form(""),
    name: str = Form(...),
    group_type: str = Form("1:1"),
    schedule_label: str = Form(""),
    capacity: str = Form("1"),
    status: str = Form("active"),
    db: Session = Depends(get_db),
):
    group = db.get(PtGroup, group_id)
    coach_pk = optional_int(coach_id)
    if not group:
        if wants_json(request):
            return JSONResponse({"ok": False, "message": "Không tìm thấy nhóm PT."}, status_code=404)
        return redirect_with_toast("/pt-groups", "Không tìm thấy nhóm PT.", "error")
    if not coach_pk:
        if wants_json(request):
            return JSONResponse({"ok": False, "message": "Cần chọn coach cho nhóm PT."}, status_code=400)
        return redirect_with_toast("/pt-groups", "Cần chọn coach cho nhóm PT.", "error")
    group.name = name.strip()
    group.coach_id = coach_pk
    group.package_id = optional_int(package_id)
    group.group_type = group_type
    group.schedule_label = schedule_label or None
    group.capacity = max(int_value(capacity, 1), 1)
    group.status = status if status in ["active", "inactive"] else "active"
    db.commit()
    if wants_json(request):
        return pt_groups_json(db, request, "Đã cập nhật nhóm PT.", q, status_filter)
    return redirect_with_toast("/pt-groups", "Đã cập nhật nhóm PT.")


@app.post("/pt-groups/{group_id}/deactivate")
def deactivate_pt_group(group_id: int, request: Request, q: str = "", status: str = "active", db: Session = Depends(get_db)):
    group = db.get(PtGroup, group_id)
    if not group:
        if wants_json(request):
            return JSONResponse({"ok": False, "message": "Không tìm thấy nhóm PT."}, status_code=404)
        return redirect_with_toast("/pt-groups", "Không tìm thấy nhóm PT.", "error")
    group.status = "inactive"
    db.commit()
    if wants_json(request):
        return pt_groups_json(db, request, "Đã vô hiệu hóa nhóm PT.", q, status)
    return redirect_with_toast("/pt-groups", "Đã vô hiệu hóa nhóm PT.")


@app.post("/pt-groups/{group_id}/members")
def add_pt_group_member(group_id: int, request: Request, q: str = "", status: str = "active", customer_id: str = Form(""), membership_id: str = Form(""), db: Session = Depends(get_db)):
    group = db.get(PtGroup, group_id)
    customer_pk = optional_int(customer_id)
    if not group:
        if wants_json(request):
            return JSONResponse({"ok": False, "message": "Không tìm thấy nhóm PT."}, status_code=404)
        return redirect_with_toast("/pt-groups", "Không tìm thấy nhóm PT.", "error")
    if not customer_pk:
        if wants_json(request):
            return JSONResponse({"ok": False, "message": "Cần chọn học viên để thêm vào nhóm."}, status_code=400)
        return redirect_with_toast("/pt-groups", "Cần chọn học viên để thêm vào nhóm.", "error")
    active_members = [member for member in group.members if member.status == "active"]
    if any(member.customer_id == customer_pk for member in active_members):
        if wants_json(request):
            return JSONResponse({"ok": False, "message": "Học viên này đã có trong nhóm."}, status_code=400)
        return redirect_with_toast("/pt-groups", "Học viên này đã có trong nhóm.", "error")
    if len(active_members) >= group.capacity:
        if wants_json(request):
            return JSONResponse({"ok": False, "message": "Nhóm đã đủ sức chứa."}, status_code=400)
        return redirect_with_toast("/pt-groups", "Nhóm đã đủ sức chứa.", "error")
    db.add(PtGroupMember(group_id=group_id, customer_id=customer_pk, membership_id=optional_int(membership_id), joined_at=date.today(), status="active"))
    db.commit()
    if wants_json(request):
        return pt_groups_json(db, request, "Đã thêm học viên vào nhóm PT.", q, status)
    return redirect_with_toast("/pt-groups", "Đã thêm học viên vào nhóm PT.")


@app.post("/pt-groups/{group_id}/members/{member_id}/remove")
def remove_pt_group_member(group_id: int, member_id: int, request: Request, q: str = "", status: str = "active", db: Session = Depends(get_db)):
    member = db.query(PtGroupMember).filter(PtGroupMember.id == member_id, PtGroupMember.group_id == group_id).first()
    if not member:
        if wants_json(request):
            return JSONResponse({"ok": False, "message": "Không tìm thấy học viên trong nhóm."}, status_code=404)
        return redirect_with_toast("/pt-groups", "Không tìm thấy học viên trong nhóm.", "error")
    db.delete(member)
    db.commit()
    if wants_json(request):
        return pt_groups_json(db, request, "Đã xóa học viên khỏi nhóm PT.", q, status)
    return redirect_with_toast("/pt-groups", "Đã xóa học viên khỏi nhóm PT.")


@app.get("/reports/revenue")
def revenue_report(request: Request, db: Session = Depends(get_db)):
    total = db.query(func.sum(Payment.amount)).scalar() or 0
    by_method = db.query(Payment.method, func.sum(Payment.amount)).group_by(Payment.method).all()
    rows = db.query(Payment).options(joinedload(Payment.customer).joinedload(Customer.person), joinedload(Payment.membership).joinedload(Membership.package), joinedload(Payment.bank_account)).order_by(Payment.paid_at.desc()).limit(80).all()
    return templates.TemplateResponse("report_revenue.html", {"request": request, "total": total, "by_method": by_method, "payments": rows, "active": "reports"})


@app.get("/reports/debts")
def debt_report(request: Request, db: Session = Depends(get_db)):
    today = date.today()
    rows = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package)).filter(Membership.debt_amount > 0).order_by(Membership.debt_due_date.asc()).all()
    total = sum(row.debt_amount or 0 for row in rows)
    overdue = sum(1 for row in rows if row.debt_due_date and row.debt_due_date < today)
    return templates.TemplateResponse("report_debts.html", {"request": request, "memberships": rows, "total": total, "overdue": overdue, "today": today, "active": "reports"})


@app.get("/reports/bank-transactions")
def bank_transactions_report(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Payment).options(joinedload(Payment.customer).joinedload(Customer.person), joinedload(Payment.bank_account)).filter(Payment.method == "bank_transfer").order_by(Payment.paid_at.desc()).all()
    accounts = db.query(BankAccount).order_by(BankAccount.visibility, BankAccount.bank_name).all()
    total = sum(row.amount or 0 for row in rows)
    return templates.TemplateResponse("report_bank.html", {"request": request, "payments": rows, "accounts": accounts, "total": total, "active": "reports"})


@app.get("/reports/cash")
def cash_report(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Payment).options(joinedload(Payment.customer).joinedload(Customer.person)).filter(Payment.method == "cash").order_by(Payment.paid_at.desc()).all()
    shifts = db.query(CashShift).options(joinedload(CashShift.branch), joinedload(CashShift.opened_by).joinedload(Employee.person)).order_by(CashShift.shift_date.desc()).all()
    total = sum(row.amount or 0 for row in rows)
    return templates.TemplateResponse("report_cash.html", {"request": request, "payments": rows, "shifts": shifts, "total": total, "active": "reports"})


@app.get("/commissions")
def commissions(request: Request, db: Session = Depends(get_db)):
    rows = db.query(CommissionLedger).options(joinedload(CommissionLedger.employee).joinedload(Employee.person), joinedload(CommissionLedger.membership).joinedload(Membership.customer).joinedload(Customer.person)).order_by(CommissionLedger.earned_at.desc()).all()
    total = sum(row.commission_amount or 0 for row in rows)
    return templates.TemplateResponse("commissions.html", {"request": request, "commissions": rows, "total": total, "active": "commissions"})


@app.get("/devices")
def devices(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Device).options(joinedload(Device.branch)).all()
    return templates.TemplateResponse("devices.html", {"request": request, "devices": rows, "active": "devices"})


@app.get("/sync")
def sync(request: Request, db: Session = Depends(get_db)):
    devices = db.query(Device).options(joinedload(Device.branch)).all()
    return templates.TemplateResponse("sync.html", {"request": request, "devices": devices, "active": "sync"})
