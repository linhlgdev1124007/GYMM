from app.database import SessionLocal
from datetime import date, timedelta

from app.database import Base, engine
from app.models import Branch, Customer, Device, Employee, Membership, Payment, ServicePackage


def main() -> None:
    Base.metadata.create_all(bind=engine)
    additions = {
        "people": {"date_of_birth": "DATE"},
        "customers": {"mbs_card_code": "VARCHAR(60)"},
        "memberships": {
            "registered_at": "DATE",
            "deposit_amount": "FLOAT DEFAULT 0",
            "debt_amount": "FLOAT DEFAULT 0",
            "debt_due_date": "DATE",
        },
    }
    with engine.begin() as connection:
        for table_name, columns in additions.items():
            existing = {row[1] for row in connection.exec_driver_sql(f"PRAGMA table_info({table_name})")}
            for column_name, definition in columns.items():
                if column_name not in existing:
                    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {definition}")

    db = SessionLocal()
    try:
        for code, name, address in [
            ("MAIN", "PulseFit Quận 1", "12 Nguyễn Huệ, Q1"),
            ("WEST", "PulseFit West", "88 Trần Duy Hưng"),
        ]:
            branch = db.query(Branch).filter_by(code=code).first()
            if branch:
                branch.name = name
                branch.address = address

        for old_code, new_code, name, category in [
            ("GYM-1M", "FIT-1M", "Fitness Unlimited 1 tháng", "Fitness"),
            ("GYM-12S", "FIT-12S", "Fitness 12 buổi", "Fitness"),
            ("PT-10", "PT-10", "Huấn luyện cá nhân 10 buổi", "PT"),
        ]:
            package = db.query(ServicePackage).filter_by(code=old_code).first()
            package = package or db.query(ServicePackage).filter_by(code=new_code).first()
            if package:
                package.code = new_code
                package.name = name
                package.category = category

        for code, name, source in [
            ("CUST-0001", "Nguyễn Minh Anh", "Facebook"),
            ("CUST-0002", "Trần Bảo Châu", "Giới thiệu"),
            ("CUST-0003", "Lê Quang Huy", "Khách vãng lai"),
            ("CUST-0004", "Phạm Khánh Linh", "Zalo"),
        ]:
            customer = db.query(Customer).filter_by(customer_code=code).first()
            if customer:
                customer.source = source
                customer.person.display_name = name

        for code, name, title in [
            ("EMP-0001", "Hoàng Đức PT", "Head Coach"),
            ("EMP-0002", "Mai Trang", "Lễ tân"),
            ("EMP-0003", "Đỗ Nam", "Quản lý"),
        ]:
            employee = db.query(Employee).filter_by(employee_code=code).first()
            if employee:
                employee.job_title = title
                employee.person.display_name = name

        for code, name in [
            ("DEV-LOBBY", "Cổng nhận diện quầy"),
            ("DEV-STAFF", "Máy chấm công nhân viên"),
        ]:
            device = db.query(Device).filter_by(code=code).first()
            if device:
                device.name = name

        for membership in db.query(Membership).all():
            membership.registered_at = membership.registered_at or membership.starts_at or date.today()
            membership.deposit_amount = membership.deposit_amount or membership.paid_amount or 0
            membership.debt_amount = max((membership.final_price or 0) - (membership.paid_amount or 0), 0)
            if membership.debt_amount > 0 and not membership.debt_due_date:
                membership.debt_due_date = date.today() + timedelta(days=5)

            if membership.deposit_amount > 0:
                exists = db.query(Payment).filter_by(membership_id=membership.id).first()
                if not exists:
                    db.add(Payment(
                        customer_id=membership.customer_id,
                        membership_id=membership.id,
                        payment_no=f"PAY-{membership.id:04d}-001",
                        amount=membership.deposit_amount,
                        method="cash",
                        note="Tiền cọc dữ liệu mẫu",
                    ))

        db.commit()
    finally:
        db.close()


if __name__ == "__main__":
    main()
