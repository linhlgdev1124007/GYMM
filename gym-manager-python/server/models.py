from datetime import datetime, date

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.mysql import LONGTEXT
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base
from .timeutils import utc_now

LONG_TEXT = Text().with_variant(LONGTEXT(), "mysql")


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    username: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(160))
    password_hash: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(30), default="manager", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), unique=True)

    employee: Mapped["Employee | None"] = relationship()


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    actor_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), index=True)
    action: Mapped[str] = mapped_column(String(60), index=True)
    entity_type: Mapped[str] = mapped_column(String(60), index=True)
    entity_id: Mapped[int | None] = mapped_column(Integer, index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    summary: Mapped[str] = mapped_column(String(255))
    details_json: Mapped[str | None] = mapped_column(Text)
    ip_address: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    actor: Mapped["User | None"] = relationship()


class AuthSession(Base):
    __tablename__ = "auth_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    user: Mapped[User] = relationship()


class InventoryProduct(Base):
    __tablename__ = "inventory_products"

    id: Mapped[int] = mapped_column(primary_key=True)
    sku: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(100), index=True)
    name: Mapped[str] = mapped_column(String(180), index=True)
    unit: Mapped[str] = mapped_column(String(40))
    current_stock: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    minimum_stock: Mapped[float] = mapped_column(Numeric(14, 3), default=0)
    average_cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)

    transactions: Mapped[list["InventoryTransaction"]] = relationship(back_populates="product")


class InventoryTransaction(Base):
    __tablename__ = "inventory_transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("inventory_products.id"), index=True)
    transaction_type: Mapped[str] = mapped_column(String(20), index=True)
    occurred_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    quantity: Mapped[float] = mapped_column(Numeric(14, 3))
    unit_cost: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    total_amount: Mapped[float] = mapped_column(Numeric(18, 2), default=0)
    stock_before: Mapped[float] = mapped_column(Numeric(14, 3))
    stock_after: Mapped[float] = mapped_column(Numeric(14, 3))
    note: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    reversed_transaction_id: Mapped[int | None] = mapped_column(ForeignKey("inventory_transactions.id"), index=True)
    status: Mapped[str] = mapped_column(String(20), default="POSTED", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    product: Mapped[InventoryProduct] = relationship(back_populates="transactions")
    created_by: Mapped[User] = relationship(foreign_keys=[created_by_user_id])
    reversed_transaction: Mapped["InventoryTransaction | None"] = relationship(remote_side=[id])


class CheckinSpeechConfig(Base):
    __tablename__ = "checkin_speech_configs"

    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    voice_uri: Mapped[str | None] = mapped_column(String(300))
    voice_name: Mapped[str | None] = mapped_column(String(200))
    volume: Mapped[float] = mapped_column(Float, default=1.0)
    rate: Mapped[float] = mapped_column(Float, default=1.0)
    pitch: Mapped[float] = mapped_column(Float, default=1.0)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)
    updated_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))

    updated_by: Mapped["User | None"] = relationship()


class CheckinSpeechPattern(Base):
    __tablename__ = "checkin_speech_patterns"

    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(String(500))
    person_type: Mapped[str] = mapped_column(String(20), default="all", index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, onupdate=utc_now)


class CheckinSpeechEvent(Base):
    __tablename__ = "checkin_speech_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    attendance_session_id: Mapped[int] = mapped_column(ForeignKey("attendance_sessions.id"), unique=True, index=True)
    person_type: Mapped[str] = mapped_column(String(20), index=True)
    person_name: Mapped[str] = mapped_column(String(180))
    message: Mapped[str] = mapped_column(String(700))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    attendance_session: Mapped["AttendanceSession"] = relationship()


class AlertRead(Base):
    __tablename__ = "alert_reads"
    __table_args__ = (UniqueConstraint("user_id", "alert_key", name="uq_alert_reads_user_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    alert_key: Mapped[str] = mapped_column(String(180), index=True)
    read_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)

    user: Mapped[User] = relationship()


class Person(Base):
    __tablename__ = "people"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(160), index=True)
    phone: Mapped[str | None] = mapped_column(String(40), index=True)
    email: Mapped[str | None] = mapped_column(String(120))
    gender: Mapped[str | None] = mapped_column(String(20))
    date_of_birth: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(30), default="active")
    biometric_consent_status: Mapped[str] = mapped_column(String(40), default="not_requested")

    customer: Mapped["Customer | None"] = relationship(back_populates="person")
    employee: Mapped["Employee | None"] = relationship(back_populates="person")


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), unique=True)
    customer_code: Mapped[str] = mapped_column(String(40), unique=True)
    mbs_card_code: Mapped[str | None] = mapped_column(String(60))
    person_uuid: Mapped[str | None] = mapped_column(String(80), unique=True, index=True)
    avatar_image_data: Mapped[str | None] = mapped_column(LONG_TEXT)
    sales_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    source: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="lead")
    notes: Mapped[str | None] = mapped_column(Text)

    person: Mapped[Person] = relationship(back_populates="customer")
    sales_employee: Mapped["Employee | None"] = relationship()
    memberships: Mapped[list["Membership"]] = relationship(back_populates="customer")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), unique=True)
    employee_code: Mapped[str] = mapped_column(String(40), unique=True)
    job_title: Mapped[str | None] = mapped_column(String(80))
    base_salary: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="active")

    person: Mapped[Person] = relationship(back_populates="employee")


class EmployeeJobTitle(Base):
    __tablename__ = "employee_job_titles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True, index=True)
    is_pt_role: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)


class EmployeeShiftSchedule(Base):
    __tablename__ = "employee_shift_schedules"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    starts_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    ends_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)
    note: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    employee: Mapped[Employee] = relationship()


class EmployeeShiftOverride(Base):
    __tablename__ = "employee_shift_overrides"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), index=True)
    original_shift_schedule_id: Mapped[int | None] = mapped_column(ForeignKey("employee_shift_schedules.id"), index=True)
    work_date: Mapped[date] = mapped_column(Date, index=True)
    original_start_at: Mapped[datetime | None] = mapped_column(DateTime)
    original_end_at: Mapped[datetime | None] = mapped_column(DateTime)
    approved_start_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    approved_end_at: Mapped[datetime] = mapped_column(DateTime, index=True)
    status: Mapped[str] = mapped_column(String(30), default="approved", index=True)
    reason: Mapped[str | None] = mapped_column(String(255))
    requested_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    employee: Mapped[Employee] = relationship()
    original_shift_schedule: Mapped[EmployeeShiftSchedule | None] = relationship()


class ServicePackage(Base):
    __tablename__ = "service_packages"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    category: Mapped[str] = mapped_column(String(80))
    package_type: Mapped[str] = mapped_column(String(30), default="time")
    duration_days: Mapped[int | None] = mapped_column(Integer)
    session_count: Mapped[int | None] = mapped_column(Integer)
    price: Mapped[float] = mapped_column(Float, default=0)
    is_pt: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    package_id: Mapped[int] = mapped_column(ForeignKey("service_packages.id"))
    code: Mapped[str] = mapped_column(String(40), unique=True)
    registered_at: Mapped[date | None] = mapped_column(Date)
    starts_at: Mapped[date | None] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    activated_at: Mapped[date | None] = mapped_column(Date)
    remaining_sessions: Mapped[int | None] = mapped_column(Integer)
    final_price: Mapped[float] = mapped_column(Float, default=0)
    deposit_amount: Mapped[float] = mapped_column(Float, default=0)
    paid_amount: Mapped[float] = mapped_column(Float, default=0)
    debt_amount: Mapped[float] = mapped_column(Float, default=0)
    debt_due_date: Mapped[date | None] = mapped_column(Date)
    sale_online_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    direct_sales_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    pt_converter_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    status: Mapped[str] = mapped_column(String(30), default="active")

    customer: Mapped[Customer] = relationship(back_populates="memberships")
    package: Mapped[ServicePackage] = relationship()
    payments: Mapped[list["Payment"]] = relationship(back_populates="membership")
    sale_online_employee: Mapped[Employee | None] = relationship(foreign_keys=[sale_online_employee_id])
    direct_sales_employee: Mapped[Employee | None] = relationship(foreign_keys=[direct_sales_employee_id])
    pt_converter_employee: Mapped[Employee | None] = relationship(foreign_keys=[pt_converter_employee_id])
    freezes: Mapped[list["MembershipFreeze"]] = relationship(back_populates="membership", cascade="all, delete-orphan")
    events: Mapped[list["MembershipEvent"]] = relationship(back_populates="membership", cascade="all, delete-orphan")


class MembershipFreeze(Base):
    __tablename__ = "membership_freezes"

    id: Mapped[int] = mapped_column(primary_key=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("memberships.id", ondelete="CASCADE"), index=True)
    starts_at: Mapped[date] = mapped_column(Date)
    ends_at: Mapped[date] = mapped_column(Date)
    completed_at: Mapped[date | None] = mapped_column(Date)
    compensated_days: Mapped[int] = mapped_column(Integer)
    reason: Mapped[str] = mapped_column(String(255))
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    membership: Mapped[Membership] = relationship(back_populates="freezes")
    created_by: Mapped["User | None"] = relationship()


class MembershipEvent(Base):
    __tablename__ = "membership_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    membership_id: Mapped[int] = mapped_column(ForeignKey("memberships.id", ondelete="CASCADE"), index=True)
    action: Mapped[str] = mapped_column(String(40), index=True)
    from_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    to_customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    from_package_id: Mapped[int | None] = mapped_column(ForeignKey("service_packages.id"))
    to_package_id: Mapped[int | None] = mapped_column(ForeignKey("service_packages.id"))
    effective_at: Mapped[date] = mapped_column(Date, default=date.today)
    reason: Mapped[str] = mapped_column(String(255))
    details_json: Mapped[str | None] = mapped_column(Text)
    created_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    membership: Mapped[Membership] = relationship(back_populates="events")
    from_customer: Mapped[Customer | None] = relationship(foreign_keys=[from_customer_id])
    to_customer: Mapped[Customer | None] = relationship(foreign_keys=[to_customer_id])
    from_package: Mapped[ServicePackage | None] = relationship(foreign_keys=[from_package_id])
    to_package: Mapped[ServicePackage | None] = relationship(foreign_keys=[to_package_id])
    created_by: Mapped["User | None"] = relationship()


class BankAccount(Base):
    __tablename__ = "bank_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    bank_name: Mapped[str] = mapped_column(String(120))
    account_name: Mapped[str] = mapped_column(String(160))
    account_number: Mapped[str] = mapped_column(String(80))
    visibility: Mapped[str] = mapped_column(String(30), default="public")
    status: Mapped[str] = mapped_column(String(30), default="active")


class Payment(Base):
    __tablename__ = "payments"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    membership_id: Mapped[int | None] = mapped_column(ForeignKey("memberships.id"))
    bank_account_id: Mapped[int | None] = mapped_column(ForeignKey("bank_accounts.id"))
    payment_no: Mapped[str] = mapped_column(String(40), unique=True)
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    amount: Mapped[float] = mapped_column(Float, default=0)
    method: Mapped[str] = mapped_column(String(40), default="cash")
    channel: Mapped[str] = mapped_column(String(30), default="counter")
    shift_date: Mapped[date | None] = mapped_column(Date)
    receipt_image_path: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer | None] = relationship()
    membership: Mapped[Membership | None] = relationship(back_populates="payments")
    bank_account: Mapped[BankAccount | None] = relationship()
    receipts: Mapped[list["PaymentReceipt"]] = relationship(
        back_populates="payment", cascade="all, delete-orphan"
    )


class PaymentReceipt(Base):
    __tablename__ = "payment_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    payment_id: Mapped[int] = mapped_column(ForeignKey("payments.id", ondelete="CASCADE"), index=True)
    file_path: Mapped[str] = mapped_column(String(255))
    original_name: Mapped[str | None] = mapped_column(String(255))
    uploaded_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    uploaded_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    payment: Mapped[Payment] = relationship(back_populates="receipts")
    uploaded_by: Mapped["User | None"] = relationship()


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    support_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    prospect_name: Mapped[str | None] = mapped_column(String(160))
    discipline_interest: Mapped[str | None] = mapped_column(String(100))
    access_platform: Mapped[str | None] = mapped_column(String(80))
    scheduled_at: Mapped[datetime] = mapped_column(DateTime)
    appointment_type: Mapped[str] = mapped_column(String(60), default="Tư vấn")
    status: Mapped[str] = mapped_column(String(30), default="scheduled")
    note: Mapped[str | None] = mapped_column(Text)
    consultation_note: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer] = relationship()
    employee: Mapped[Employee | None] = relationship(foreign_keys=[employee_id])
    support_employee: Mapped[Employee | None] = relationship(foreign_keys=[support_employee_id])


class PtGroup(Base):
    __tablename__ = "pt_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    package_id: Mapped[int | None] = mapped_column(ForeignKey("service_packages.id"))
    name: Mapped[str] = mapped_column(String(160))
    group_type: Mapped[str] = mapped_column(String(20), default="1:1")
    schedule_label: Mapped[str | None] = mapped_column(String(160))
    capacity: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(30), default="active")
    note: Mapped[str | None] = mapped_column(Text)

    coach: Mapped[Employee] = relationship()
    package: Mapped[ServicePackage | None] = relationship()
    members: Mapped[list["PtGroupMember"]] = relationship(back_populates="group")


class PtGroupMember(Base):
    __tablename__ = "pt_group_members"

    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("pt_groups.id"))
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    membership_id: Mapped[int | None] = mapped_column(ForeignKey("memberships.id"))
    joined_at: Mapped[date] = mapped_column(Date, default=date.today)
    status: Mapped[str] = mapped_column(String(30), default="active")

    group: Mapped[PtGroup] = relationship(back_populates="members")
    customer: Mapped[Customer] = relationship()
    membership: Mapped[Membership | None] = relationship()


class PtEnrollment(Base):
    __tablename__ = "pt_enrollments"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"), index=True)
    coach_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    group_type: Mapped[str] = mapped_column(String(20), default="1:1", index=True)
    starts_at: Mapped[date] = mapped_column(Date, default=date.today)
    expires_at: Mapped[date | None] = mapped_column(Date)
    total_sessions: Mapped[int] = mapped_column(Integer, default=12)
    remaining_sessions: Mapped[int] = mapped_column(Integer, default=12)
    schedule_days: Mapped[str | None] = mapped_column(String(120))
    schedule_time: Mapped[str | None] = mapped_column(String(10))
    schedule_json: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(30), default="active", index=True)

    customer: Mapped[Customer] = relationship()
    coach_assignments: Mapped[list["PtEnrollmentCoach"]] = relationship(back_populates="enrollment", cascade="all, delete-orphan")


class PtEnrollmentCoach(Base):
    __tablename__ = "pt_enrollment_coaches"

    enrollment_id: Mapped[int] = mapped_column(ForeignKey("pt_enrollments.id", ondelete="CASCADE"), primary_key=True)
    coach_id: Mapped[int] = mapped_column(ForeignKey("employees.id"), primary_key=True)
    assigned_at: Mapped[date] = mapped_column(Date, default=date.today)

    enrollment: Mapped[PtEnrollment] = relationship(back_populates="coach_assignments")
    coach: Mapped[Employee] = relationship()


class CommissionLedger(Base):
    __tablename__ = "commission_ledger"

    id: Mapped[int] = mapped_column(primary_key=True)
    employee_id: Mapped[int] = mapped_column(ForeignKey("employees.id"))
    membership_id: Mapped[int | None] = mapped_column(ForeignKey("memberships.id"))
    role: Mapped[str] = mapped_column(String(40))
    base_amount: Mapped[float] = mapped_column(Float, default=0)
    rate_percent: Mapped[float] = mapped_column(Float, default=0)
    commission_amount: Mapped[float] = mapped_column(Float, default=0)
    earned_at: Mapped[date] = mapped_column(Date, default=date.today)
    status: Mapped[str] = mapped_column(String(30), default="pending")

    employee: Mapped[Employee] = relationship()
    membership: Mapped[Membership | None] = relationship()


class CashShift(Base):
    __tablename__ = "cash_shifts"

    id: Mapped[int] = mapped_column(primary_key=True)
    opened_by_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    shift_date: Mapped[date] = mapped_column(Date, default=date.today)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    expected_amount: Mapped[float] = mapped_column(Float, default=0)
    counted_amount: Mapped[float] = mapped_column(Float, default=0)
    difference_amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="open")
    note: Mapped[str | None] = mapped_column(Text)

    opened_by: Mapped[Employee | None] = relationship()


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    employee_shift_schedule_id: Mapped[int | None] = mapped_column(ForeignKey("employee_shift_schedules.id"))
    scheduled_start_at: Mapped[datetime | None] = mapped_column(DateTime)
    scheduled_end_at: Mapped[datetime | None] = mapped_column(DateTime)
    checked_in_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    result: Mapped[str] = mapped_column(String(50), default="allowed")
    status: Mapped[str] = mapped_column(String(30), default="open")
    note: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer | None] = relationship()
    employee: Mapped[Employee | None] = relationship()
    employee_shift_schedule: Mapped[EmployeeShiftSchedule | None] = relationship()


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    model: Mapped[str | None] = mapped_column(String(80))
    ip_address: Mapped[str | None] = mapped_column(String(60))
    purpose: Mapped[str] = mapped_column(String(30), default="shared")
    status: Mapped[str] = mapped_column(String(30), default="offline")
    pending_jobs: Mapped[int] = mapped_column(Integer, default=0)
    errors_24h: Mapped[int] = mapped_column(Integer, default=0)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)


class DahCustomerIdentity(Base):
    __tablename__ = "dah_customer_identities"
    __table_args__ = (
        UniqueConstraint("person_uuid", name="uq_dah_customer_identities_person_uuid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), index=True)
    person_uuid: Mapped[str] = mapped_column(String(80), index=True)
    person_id: Mapped[str | None] = mapped_column(String(80), index=True)
    face_name: Mapped[str | None] = mapped_column(String(160))
    rfid_card: Mapped[str | None] = mapped_column(String(80))
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now)

    customer: Mapped[Customer | None] = relationship()
    employee: Mapped[Employee | None] = relationship()
    device: Mapped[Device | None] = relationship()


class DahWebhookEvent(Base):
    __tablename__ = "dah_webhook_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_key: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    operator: Mapped[str] = mapped_column(String(40), index=True)
    device_id: Mapped[int | None] = mapped_column(ForeignKey("devices.id"), index=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"), index=True)
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"), index=True)
    attendance_session_id: Mapped[int | None] = mapped_column(ForeignKey("attendance_sessions.id"))
    person_uuid: Mapped[str | None] = mapped_column(String(80), index=True)
    person_id: Mapped[str | None] = mapped_column(String(80), index=True)
    verify_status: Mapped[int | None] = mapped_column(Integer)
    similarity: Mapped[float | None] = mapped_column(Float)
    event_time: Mapped[datetime | None] = mapped_column(DateTime, index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime, default=utc_now, index=True)
    status: Mapped[str] = mapped_column(String(40), default="received", index=True)
    action: Mapped[str | None] = mapped_column(String(40), index=True)
    note: Mapped[str | None] = mapped_column(String(255))
    image_data: Mapped[str | None] = mapped_column(LONG_TEXT)
    raw_payload: Mapped[str | None] = mapped_column(LONG_TEXT)

    device: Mapped[Device | None] = relationship()
    customer: Mapped[Customer | None] = relationship()
    employee: Mapped[Employee | None] = relationship()
    attendance_session: Mapped[AttendanceSession | None] = relationship()
