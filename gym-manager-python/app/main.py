from datetime import date, datetime, timedelta
import os
from pathlib import Path
from urllib.parse import urlencode

from fastapi import Depends, FastAPI, File, Form, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from .database import BASE_DIR, Base, engine, get_db
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
    PtEnrollment,
    PtGroup,
    PtGroupMember,
    ServicePackage,
)
from .seed import seed_database

app = FastAPI(title="PulseFit Studio")
STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
RECEIPTS_DIR = STATIC_DIR / "receipts"

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
templates = Jinja2Templates(directory=TEMPLATES_DIR)


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


PT_GROUP_TYPES = ("1:1", "1:2", "1:3")
PT_SESSION_OPTIONS = (12, 24, 36)
WEEKDAY_OPTIONS = ("Thứ 2", "Thứ 3", "Thứ 4", "Thứ 5", "Thứ 6", "Thứ 7", "Chủ nhật")


def normalized_group_type(value: str) -> str:
    return value if value in PT_GROUP_TYPES else "1:1"


def normalized_sessions(option: str, custom_value: str) -> int:
    if option == "other":
        return max(int_value(custom_value, 1), 1)
    parsed = int_value(option, 12)
    return parsed if parsed in PT_SESSION_OPTIONS else 12


def normalized_schedule_days(values: list[str]) -> str | None:
    selected = [day for day in WEEKDAY_OPTIONS if day in values]
    return ", ".join(selected) or None


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
    }

    with engine.begin() as connection:
        for table_name, columns in additions.items():
            existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})")}
            for column_name, definition in columns.items():
                if column_name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")


def seed_business_modules(db: Session) -> None:
    main_branch = db.query(Branch).filter(Branch.code == "MAIN").first() or db.query(Branch).first()
    west_branch = db.query(Branch).filter(Branch.code == "WEST").first() or main_branch

    extra_packages = [
        ("FIT-3M", "Fitness Unlimited 3 tháng", "Fitness", "time", 90, None, 1350000, False),
        ("FIT-6M", "Fitness Unlimited 6 tháng", "Fitness", "time", 180, None, 2500000, False),
        ("YOGA-12", "Yoga Mobility", "Yoga", "time", 60, None, 1200000, False),
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

    customer_specs = [
        ("CUST-0005", "Đặng Gia Bảo", "0908889999", "Nam", "1995-04-12", "MBS-0005", "Instagram", "active", "Muốn giảm mỡ, thích tập buổi sáng.", sales_online, main_branch, "FIT-3M", 1350000, 500000, 80),
        ("CUST-0006", "Võ Nhật Vy", "0912223333", "Nữ", "1998-09-21", "MBS-0006", "TikTok", "active", "Quan tâm PT nhóm đôi, cần nhắc lịch đều.", direct_sale, west_branch, "FIT-3M", 1350000, 500000, 75),
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

    # Preserve old PT data by copying each former group member into the new,
    # customer-centric enrollment model. Old tables remain untouched.
    if not db.query(PtEnrollment).first():
        legacy_members = db.query(PtGroupMember).options(
            joinedload(PtGroupMember.group),
            joinedload(PtGroupMember.membership),
        ).all()
        for legacy_member in legacy_members:
            group = legacy_member.group
            if not group or not group.coach_id:
                continue
            schedule_parts = [part.strip() for part in (group.schedule_label or "").rsplit(",", 1)]
            schedule_days = schedule_parts[0] if schedule_parts else None
            schedule_time = schedule_parts[1] if len(schedule_parts) == 2 and ":" in schedule_parts[1] else None
            membership = legacy_member.membership
            total_sessions = (membership.remaining_sessions if membership and membership.remaining_sessions else 12)
            db.add(PtEnrollment(
                customer_id=legacy_member.customer_id,
                coach_id=group.coach_id,
                group_type=normalized_group_type(group.group_type),
                starts_at=(membership.starts_at if membership and membership.starts_at else legacy_member.joined_at),
                expires_at=membership.expires_at if membership else None,
                total_sessions=total_sessions,
                remaining_sessions=total_sessions,
                schedule_days=schedule_days,
                schedule_time=schedule_time,
                status=legacy_member.status or "active",
            ))
        db.commit()

    if not db.query(PtEnrollment).first() and coach:
        demo_customers = db.query(Customer).filter(Customer.status == "active").limit(3).all()
        demo_specs = [
            ("1:1", 12, "Thứ 2, Thứ 4", "18:30"),
            ("1:2", 24, "Thứ 3, Thứ 5", "19:00"),
            ("1:3", 36, "Thứ 2, Thứ 4, Thứ 6", "07:00"),
        ]
        for customer, (group_type, sessions, schedule_days, schedule_time) in zip(demo_customers, demo_specs):
            db.add(PtEnrollment(
                customer_id=customer.id,
                coach_id=coach.id,
                group_type=group_type,
                starts_at=date.today(),
                expires_at=date.today() + timedelta(days=90),
                total_sessions=sessions,
                remaining_sessions=sessions,
                schedule_days=schedule_days,
                schedule_time=schedule_time,
                status="active",
            ))
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
    if os.getenv("VERCEL"):
        return
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
    packages = db.query(ServicePackage).filter(ServicePackage.is_active == True, ServicePackage.is_pt == False).order_by(ServicePackage.category, ServicePackage.price).all()
    bank_accounts = db.query(BankAccount).filter(BankAccount.status == "active").all()
    memberships = db.query(Membership).options(
        joinedload(Membership.package),
        joinedload(Membership.payments).joinedload(Payment.bank_account),
        joinedload(Membership.sale_online_employee).joinedload(Employee.person),
        joinedload(Membership.direct_sales_employee).joinedload(Employee.person),
    ).join(Membership.package).filter(Membership.customer_id == customer.id, ServicePackage.is_pt == False).order_by(Membership.registered_at.desc()).all()
    pt_enrollments = db.query(PtEnrollment).options(
        joinedload(PtEnrollment.coach).joinedload(Employee.person),
    ).filter(PtEnrollment.customer_id == customer.id).order_by(PtEnrollment.id.desc()).all()
    active_pt_enrollment = next((row for row in pt_enrollments if row.status == "active"), None)
    coaches = db.query(Employee).options(joinedload(Employee.person)).filter(
        Employee.status == "active", Employee.job_title.contains("Coach")
    ).order_by(Employee.id.desc()).all()
    attendances = db.query(AttendanceSession).filter(AttendanceSession.customer_id == customer.id).order_by(AttendanceSession.checked_in_at.desc()).limit(20).all()
    total_paid = db.query(func.sum(Payment.amount)).filter(Payment.customer_id == customer.id).scalar() or 0
    totals = {
        "paid": total_paid,
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
            "pt_enrollments": pt_enrollments,
            "active_pt_enrollment": active_pt_enrollment,
            "coaches": coaches,
            "weekday_options": WEEKDAY_OPTIONS,
            "attendances": attendances,
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
    if not package or package.is_pt or not package.is_active:
        return redirect_with_toast(f"/customers/{customer_id}", "Gói tập đã chọn không hợp lệ.", "error")
    final_price_value = money_value(final_price, package.price if package else 0)
    if final_price_value <= 0 and package:
        final_price_value = package.price
    deposit_amount_value = money_value(deposit_amount)
    debt_amount = max(final_price_value - deposit_amount_value, 0)
    receipt_path = None
    bank_account_pk = optional_int(bank_account_id)
    sale_online_employee_pk = optional_int(sale_online_employee_id)
    direct_sales_employee_pk = optional_int(direct_sales_employee_id)

    if receipt_image and receipt_image.filename:
        suffix = Path(receipt_image.filename).suffix.lower() or ".jpg"
        filename = f"receipt-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{next_id}{suffix}"
        target = RECEIPTS_DIR / filename
        target.write_bytes(await receipt_image.read())
        receipt_path = f"/static/receipts/{filename}"

    membership = Membership(
        customer_id=customer.id,
        package_id=package_pk,
        code=f"MEM-{next_id:04d}",
        registered_at=date.fromisoformat(registered_at) if registered_at else date.today(),
        starts_at=date.fromisoformat(starts_at) if starts_at else date.today(),
        expires_at=date.fromisoformat(expires_at) if expires_at else None,
        remaining_sessions=None,
        final_price=final_price_value,
        deposit_amount=deposit_amount_value,
        paid_amount=deposit_amount_value,
        debt_amount=debt_amount,
        debt_due_date=date.fromisoformat(debt_due_date) if debt_due_date else None,
        sale_online_employee_id=sale_online_employee_pk,
        direct_sales_employee_id=direct_sales_employee_pk,
        pt_converter_employee_id=None,
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

    customer.status = "active"
    db.commit()
    return redirect_with_toast(f"/customers/{customer.id}", "Đã đăng ký gói cho khách.")


@app.post("/customers/{customer_id}/memberships/{membership_id}/edit")
async def update_customer_membership(
    customer_id: int,
    membership_id: int,
    registered_at: str = Form(""),
    starts_at: str = Form(""),
    expires_at: str = Form(""),
    final_price: str = Form("0"),
    deposit_amount: str = Form("0"),
    debt_due_date: str = Form(""),
    payment_method: str = Form("cash"),
    bank_account_id: str = Form(""),
    receipt_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    membership = db.query(Membership).options(joinedload(Membership.package)).filter(
        Membership.id == membership_id,
        Membership.customer_id == customer_id,
    ).first()
    if not membership or (membership.package and membership.package.is_pt):
        return redirect_with_toast(f"/customers/{customer_id}", "Không tìm thấy gói đăng ký.", "error")

    final_price_value = max(money_value(final_price), 0)
    deposit_amount_value = max(money_value(deposit_amount), 0)
    membership.registered_at = date.fromisoformat(registered_at) if registered_at else membership.registered_at
    membership.starts_at = date.fromisoformat(starts_at) if starts_at else None
    membership.expires_at = date.fromisoformat(expires_at) if expires_at else None
    membership.final_price = final_price_value
    membership.deposit_amount = deposit_amount_value
    membership.paid_amount = deposit_amount_value
    membership.debt_amount = max(final_price_value - deposit_amount_value, 0)
    membership.debt_due_date = date.fromisoformat(debt_due_date) if debt_due_date and membership.debt_amount > 0 else None

    payment = db.query(Payment).filter(Payment.membership_id == membership.id).order_by(Payment.paid_at.desc()).first()
    if deposit_amount_value > 0:
        if not payment:
            payment_count = db.query(Payment).filter(Payment.membership_id == membership.id).count() + 1
            payment = Payment(
                customer_id=customer_id,
                membership_id=membership.id,
                payment_no=f"PAY-{membership.id:04d}-{payment_count:03d}",
                paid_at=datetime.utcnow(),
                shift_date=date.today(),
                note="Phiếu thu gói đăng ký",
            )
            db.add(payment)
        payment.amount = deposit_amount_value
        payment.method = payment_method
        payment.bank_account_id = optional_int(bank_account_id)
        payment.channel = "public" if payment.bank_account_id else "counter"
        if receipt_image and receipt_image.filename:
            suffix = Path(receipt_image.filename).suffix.lower() or ".jpg"
            filename = f"receipt-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{membership.id}{suffix}"
            (RECEIPTS_DIR / filename).write_bytes(await receipt_image.read())
            payment.receipt_image_path = f"/static/receipts/{filename}"

    db.commit()
    return redirect_with_toast(f"/customers/{customer_id}", "Đã cập nhật chi tiết gói và phiếu thu.")


@app.post("/customers/{customer_id}/pt-enrollments")
def create_pt_enrollment(
    customer_id: int,
    coach_id: str = Form(""),
    group_type: str = Form("1:1"),
    session_option: str = Form("12"),
    custom_sessions: str = Form(""),
    starts_at: str = Form(""),
    expires_at: str = Form(""),
    schedule_days: list[str] = Form([]),
    schedule_time: str = Form(""),
    db: Session = Depends(get_db),
):
    customer = db.get(Customer, customer_id)
    coach_pk = optional_int(coach_id)
    coach = db.get(Employee, coach_pk) if coach_pk else None
    if not customer or not coach or coach.status != "active":
        return redirect_with_toast(f"/customers/{customer_id}", "Cần chọn khách hàng và coach hợp lệ.", "error")
    if db.query(PtEnrollment).filter(PtEnrollment.customer_id == customer_id, PtEnrollment.status == "active").first():
        return redirect_with_toast(f"/customers/{customer_id}", "Khách đang có một đăng ký PT hoạt động.", "error")

    start_date = date.fromisoformat(starts_at) if starts_at else date.today()
    end_date = date.fromisoformat(expires_at) if expires_at else None
    if end_date and end_date < start_date:
        return redirect_with_toast(f"/customers/{customer_id}", "Ngày hết hạn phải sau ngày bắt đầu.", "error")
    sessions = normalized_sessions(session_option, custom_sessions)
    db.add(PtEnrollment(
        customer_id=customer_id,
        coach_id=coach.id,
        group_type=normalized_group_type(group_type),
        starts_at=start_date,
        expires_at=end_date,
        total_sessions=sessions,
        remaining_sessions=sessions,
        schedule_days=normalized_schedule_days(schedule_days),
        schedule_time=schedule_time or None,
        status="active",
    ))
    customer.status = "active"
    db.commit()
    return redirect_with_toast(f"/customers/{customer_id}", "Đã đăng ký PT cho khách.")


@app.post("/customers/{customer_id}/pt-enrollments/{enrollment_id}/edit")
def update_pt_enrollment(
    customer_id: int,
    enrollment_id: int,
    coach_id: str = Form(""),
    group_type: str = Form("1:1"),
    total_sessions: str = Form("12"),
    remaining_sessions: str = Form("12"),
    starts_at: str = Form(""),
    expires_at: str = Form(""),
    schedule_days: list[str] = Form([]),
    schedule_time: str = Form(""),
    status: str = Form("active"),
    db: Session = Depends(get_db),
):
    enrollment = db.query(PtEnrollment).filter(
        PtEnrollment.id == enrollment_id,
        PtEnrollment.customer_id == customer_id,
    ).first()
    coach_pk = optional_int(coach_id)
    coach = db.get(Employee, coach_pk) if coach_pk else None
    if not enrollment or not coach or coach.status != "active":
        return redirect_with_toast(f"/customers/{customer_id}", "Không tìm thấy đăng ký PT hoặc coach.", "error")

    start_date = date.fromisoformat(starts_at) if starts_at else enrollment.starts_at
    end_date = date.fromisoformat(expires_at) if expires_at else None
    if end_date and end_date < start_date:
        return redirect_with_toast(f"/customers/{customer_id}", "Ngày hết hạn phải sau ngày bắt đầu.", "error")
    enrollment.coach_id = coach.id
    enrollment.group_type = normalized_group_type(group_type)
    enrollment.starts_at = start_date
    enrollment.expires_at = end_date
    enrollment.total_sessions = max(int_value(total_sessions, 1), 1)
    enrollment.remaining_sessions = min(max(int_value(remaining_sessions, 0), 0), enrollment.total_sessions)
    enrollment.schedule_days = normalized_schedule_days(schedule_days)
    enrollment.schedule_time = schedule_time or None
    enrollment.status = status if status in ("active", "completed", "inactive") else "active"
    db.commit()
    return redirect_with_toast(f"/customers/{customer_id}", "Đã cập nhật đăng ký PT.")


@app.get("/employees")
def employees(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").order_by(Employee.id.desc()).all()
    return templates.TemplateResponse("employees.html", {"request": request, "employees": rows, "active": "employees"})


@app.post("/employees")
def create_employee(display_name: str = Form(...), phone: str = Form(""), job_title: str = Form("Coach"), db: Session = Depends(get_db)):
    next_id = (db.query(func.max(Employee.id)).scalar() or 0) + 1
    person = Person(display_name=display_name, phone=phone, status="active", biometric_consent_status="not_requested")
    db.add(person)
    db.flush()
    fallback_branch = db.query(Branch).first()
    db.add(Employee(person_id=person.id, branch_id=fallback_branch.id if fallback_branch else None, employee_code=f"EMP-{next_id:04d}", job_title=job_title, base_salary=0, status="active"))
    db.commit()
    return redirect_with_toast("/employees", "Đã thêm nhân viên.")


@app.post("/employees/{employee_id}/edit")
def update_employee(employee_id: int, display_name: str = Form(...), phone: str = Form(""), job_title: str = Form(""), db: Session = Depends(get_db)):
    employee = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.id == employee_id).first()
    if not employee:
        return redirect_with_toast("/employees", "Không tìm thấy nhân viên.", "error")
    employee.person.display_name = display_name.strip()
    employee.person.phone = phone or None
    employee.job_title = job_title or None
    db.commit()
    return redirect_with_toast("/employees", "Đã cập nhật nhân viên.")


@app.post("/employees/{employee_id}/delete")
def delete_employee(employee_id: int, db: Session = Depends(get_db)):
    employee = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.id == employee_id).first()
    if not employee:
        return redirect_with_toast("/employees", "Không tìm thấy nhân viên.", "error")

    reference_count = sum([
        db.query(Customer).filter(Customer.sales_employee_id == employee_id).count(),
        db.query(Membership).filter(or_(
            Membership.sale_online_employee_id == employee_id,
            Membership.direct_sales_employee_id == employee_id,
            Membership.pt_converter_employee_id == employee_id,
        )).count(),
        db.query(PtEnrollment).filter(PtEnrollment.coach_id == employee_id).count(),
        db.query(PtGroup).filter(PtGroup.coach_id == employee_id).count(),
        db.query(Appointment).filter(or_(Appointment.employee_id == employee_id, Appointment.support_employee_id == employee_id)).count(),
        db.query(AttendanceSession).filter(AttendanceSession.employee_id == employee_id).count(),
        db.query(CashShift).filter(CashShift.opened_by_employee_id == employee_id).count(),
        db.query(CommissionLedger).filter(CommissionLedger.employee_id == employee_id).count(),
    ])
    if reference_count:
        employee.status = "inactive"
        employee.person.status = "inactive"
        db.commit()
        return redirect_with_toast("/employees", "Nhân viên đã có lịch sử dữ liệu nên được ẩn an toàn khỏi danh sách.")

    person = employee.person
    db.delete(employee)
    db.flush()
    db.delete(person)
    db.commit()
    return redirect_with_toast("/employees", "Đã xóa nhân viên.")


@app.get("/packages")
def packages(request: Request, db: Session = Depends(get_db)):
    rows = db.query(ServicePackage).filter(ServicePackage.is_pt == False).order_by(ServicePackage.category, ServicePackage.price).all()
    return templates.TemplateResponse("packages.html", {"request": request, "packages": rows, "active": "packages"})


@app.post("/packages")
def create_package(name: str = Form(...), category: str = Form("Fitness"), price: str = Form("0"), duration_days: str = Form(""), db: Session = Depends(get_db)):
    next_id = (db.query(func.max(ServicePackage.id)).scalar() or 0) + 1
    db.add(ServicePackage(code=f"PKG-{next_id:04d}", name=name, category=category, package_type="time", duration_days=optional_int(duration_days), session_count=None, price=money_value(price), is_pt=False, is_active=True))
    db.commit()
    return redirect_with_toast("/packages", "Đã thêm gói dịch vụ.")


@app.get("/memberships")
def memberships(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Membership).options(
        joinedload(Membership.customer).joinedload(Customer.person),
        joinedload(Membership.package),
        joinedload(Membership.sale_online_employee).joinedload(Employee.person),
        joinedload(Membership.direct_sales_employee).joinedload(Employee.person),
    ).join(Membership.package).filter(ServicePackage.is_pt == False).order_by(Membership.id.desc()).all()
    customers = db.query(Customer).options(joinedload(Customer.person)).order_by(Customer.id.desc()).all()
    packages = db.query(ServicePackage).filter(ServicePackage.is_active == True, ServicePackage.is_pt == False).order_by(ServicePackage.category, ServicePackage.price).all()
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
    receipt_image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    customer_pk = optional_int(customer_id)
    package_pk = optional_int(package_id)
    if not customer_pk or not package_pk:
        return redirect_with_toast("/memberships", "Cần chọn khách hàng và dịch vụ đăng ký.", "error")

    next_id = (db.query(func.max(Membership.id)).scalar() or 0) + 1
    package = db.get(ServicePackage, package_pk)
    if not package or package.is_pt or not package.is_active:
        return redirect_with_toast("/memberships", "Gói tập đã chọn không hợp lệ.", "error")
    final_price_value = money_value(final_price, package.price)
    if final_price_value <= 0:
        final_price_value = package.price
    deposit_amount_value = money_value(deposit_amount)
    debt_amount = max(final_price_value - deposit_amount_value, 0)
    receipt_path = None
    bank_account_pk = optional_int(bank_account_id)
    sale_online_employee_pk = optional_int(sale_online_employee_id)
    direct_sales_employee_pk = optional_int(direct_sales_employee_id)

    if receipt_image and receipt_image.filename:
        suffix = Path(receipt_image.filename).suffix.lower() or ".jpg"
        filename = f"receipt-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{next_id}{suffix}"
        target = RECEIPTS_DIR / filename
        target.write_bytes(await receipt_image.read())
        receipt_path = f"/static/receipts/{filename}"

    membership = Membership(
        customer_id=customer_pk,
        package_id=package_pk,
        code=f"MEM-{next_id:04d}",
        registered_at=date.fromisoformat(registered_at) if registered_at else date.today(),
        starts_at=date.fromisoformat(starts_at) if starts_at else date.today(),
        expires_at=date.fromisoformat(expires_at) if expires_at else None,
        remaining_sessions=None,
        final_price=final_price_value,
        deposit_amount=deposit_amount_value,
        paid_amount=deposit_amount_value,
        debt_amount=debt_amount,
        debt_due_date=date.fromisoformat(debt_due_date) if debt_due_date else None,
        sale_online_employee_id=sale_online_employee_pk,
        direct_sales_employee_id=direct_sales_employee_pk,
        pt_converter_employee_id=None,
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


@app.get("/pt-groups")
def pt_groups(request: Request, tab: str = "1:1", q: str = "", db: Session = Depends(get_db)):
    active_tab = normalized_group_type(tab)
    query = db.query(PtEnrollment).options(
        joinedload(PtEnrollment.customer).joinedload(Customer.person),
        joinedload(PtEnrollment.coach).joinedload(Employee.person),
    ).filter(PtEnrollment.group_type == active_tab)
    if q.strip():
        query = query.join(PtEnrollment.customer).join(Customer.person).filter(or_(
            Person.display_name.contains(q.strip()),
            Person.phone.contains(q.strip()),
            Customer.customer_code.contains(q.strip()),
        ))
    enrollments = query.order_by(PtEnrollment.status, PtEnrollment.id.desc()).all()
    counts = {
        group_type: db.query(PtEnrollment).filter(PtEnrollment.group_type == group_type).count()
        for group_type in PT_GROUP_TYPES
    }
    return templates.TemplateResponse("pt_groups.html", {
        "request": request,
        "enrollments": enrollments,
        "active_tab": active_tab,
        "counts": counts,
        "q": q,
        "active": "pt_groups",
    })


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


@app.get("/devices")
def devices(request: Request, db: Session = Depends(get_db)):
    rows = db.query(Device).options(joinedload(Device.branch)).all()
    return templates.TemplateResponse("devices.html", {"request": request, "devices": rows, "active": "devices"})


@app.get("/sync")
def sync(request: Request, db: Session = Depends(get_db)):
    devices = db.query(Device).options(joinedload(Device.branch)).all()
    return templates.TemplateResponse("sync.html", {"request": request, "devices": devices, "active": "sync"})
