from datetime import date, datetime, timedelta

from sqlalchemy.orm import Session

from .models import (
    AttendanceSession,
    Branch,
    Customer,
    Device,
    Employee,
    Membership,
    Person,
    ServicePackage,
)


def seed_database(db: Session) -> None:
    if db.query(Branch).first():
        return

    main = Branch(code="MAIN", name="PulseFit Quận 1", address="12 Nguyễn Huệ, Q1", status="active")
    west = Branch(code="WEST", name="PulseFit West", address="88 Trần Duy Hưng", status="active")
    db.add_all([main, west])
    db.flush()

    packages = [
        ServicePackage(code="FIT-1M", name="Fitness Unlimited 1 tháng", category="Fitness", package_type="time", duration_days=30, session_count=None, price=500000, is_pt=False),
        ServicePackage(code="FIT-12S", name="Fitness 12 buổi", category="Fitness", package_type="time", duration_days=60, session_count=None, price=700000, is_pt=False),
    ]
    db.add_all(packages)
    db.flush()

    customer_rows = [
        ("CUST-0001", "Nguyễn Minh Anh", "0901112222", "Facebook", "active", packages[0], 30, 500000, 500000),
        ("CUST-0002", "Trần Bảo Châu", "0903334444", "Giới thiệu", "active", packages[0], None, 500000, 250000),
        ("CUST-0003", "Lê Quang Huy", "0905556666", "Khách vãng lai", "lead", packages[1], 12, 700000, 0),
        ("CUST-0004", "Phạm Khánh Linh", "0907778888", "Zalo", "blocked", packages[0], None, 500000, 500000),
    ]

    for index, (code, name, phone, source, status, package, remaining, final_price, paid) in enumerate(customer_rows, start=1):
        person = Person(display_name=name, phone=phone, email=None, gender=None, status="active", biometric_consent_status="accepted")
        db.add(person)
        db.flush()
        customer = Customer(person_id=person.id, branch_id=main.id, customer_code=code, source=source, status=status)
        db.add(customer)
        db.flush()
        membership = Membership(
            customer_id=customer.id,
            package_id=package.id,
            code=f"MEM-{index:04d}",
            registered_at=date.today() - timedelta(days=8),
            starts_at=date.today() - timedelta(days=8),
            expires_at=date.today() + timedelta(days=22 + index),
            remaining_sessions=remaining,
            final_price=final_price,
            deposit_amount=paid,
            paid_amount=paid,
            debt_amount=max(final_price - paid, 0),
            debt_due_date=date.today() + timedelta(days=5) if final_price > paid else None,
            status="active" if status == "active" else "pending",
        )
        db.add(membership)

    for code, name, phone, title in [
        ("EMP-0001", "Hoàng Đức PT", "0911111111", "Head Coach"),
        ("EMP-0002", "Mai Trang", "0922222222", "Lễ tân"),
        ("EMP-0003", "Đỗ Nam", "0933333333", "Quản lý"),
    ]:
        person = Person(display_name=name, phone=phone, email=None, gender=None, status="active", biometric_consent_status="accepted")
        db.add(person)
        db.flush()
        db.add(Employee(person_id=person.id, branch_id=main.id, employee_code=code, job_title=title, base_salary=9000000, status="active"))

    db.add_all([
        Device(branch_id=main.id, code="DEV-LOBBY", name="Cổng nhận diện quầy", model="DAH-1017", ip_address="192.168.1.70", purpose="shared", status="offline", pending_jobs=3, errors_24h=1),
        Device(branch_id=main.id, code="DEV-STAFF", name="Máy chấm công nhân viên", model="DAH-1017", ip_address="192.168.1.71", purpose="employee", status="maintenance", pending_jobs=0, errors_24h=0),
    ])

    db.add(AttendanceSession(customer_id=1, checked_in_at=datetime.utcnow() - timedelta(minutes=42), source="manual", result="allowed", status="open"))
    db.commit()
