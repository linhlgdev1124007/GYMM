from datetime import datetime, date

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


class Branch(Base):
    __tablename__ = "branches"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    address: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(30), default="active")


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
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    customer_code: Mapped[str] = mapped_column(String(40), unique=True)
    mbs_card_code: Mapped[str | None] = mapped_column(String(60), unique=True)
    sales_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    source: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), default="lead")
    notes: Mapped[str | None] = mapped_column(Text)

    person: Mapped[Person] = relationship(back_populates="customer")
    branch: Mapped[Branch | None] = relationship()
    sales_employee: Mapped["Employee | None"] = relationship()
    memberships: Mapped[list["Membership"]] = relationship(back_populates="customer")


class Employee(Base):
    __tablename__ = "employees"

    id: Mapped[int] = mapped_column(primary_key=True)
    person_id: Mapped[int] = mapped_column(ForeignKey("people.id"), unique=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    employee_code: Mapped[str] = mapped_column(String(40), unique=True)
    job_title: Mapped[str | None] = mapped_column(String(80))
    base_salary: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="active")

    person: Mapped[Person] = relationship(back_populates="employee")
    branch: Mapped[Branch | None] = relationship()


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
    paid_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    amount: Mapped[float] = mapped_column(Float, default=0)
    method: Mapped[str] = mapped_column(String(40), default="cash")
    channel: Mapped[str] = mapped_column(String(30), default="counter")
    shift_date: Mapped[date | None] = mapped_column(Date)
    receipt_image_path: Mapped[str | None] = mapped_column(String(255))
    note: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer | None] = relationship()
    membership: Mapped[Membership | None] = relationship(back_populates="payments")
    bank_account: Mapped[BankAccount | None] = relationship()


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
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    opened_by_employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    shift_date: Mapped[date] = mapped_column(Date, default=date.today)
    opened_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    closed_at: Mapped[datetime | None] = mapped_column(DateTime)
    expected_amount: Mapped[float] = mapped_column(Float, default=0)
    counted_amount: Mapped[float] = mapped_column(Float, default=0)
    difference_amount: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(30), default="open")
    note: Mapped[str | None] = mapped_column(Text)

    branch: Mapped[Branch | None] = relationship()
    opened_by: Mapped[Employee | None] = relationship()


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int | None] = mapped_column(ForeignKey("customers.id"))
    employee_id: Mapped[int | None] = mapped_column(ForeignKey("employees.id"))
    checked_in_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    checked_out_at: Mapped[datetime | None] = mapped_column(DateTime)
    source: Mapped[str] = mapped_column(String(30), default="manual")
    result: Mapped[str] = mapped_column(String(50), default="allowed")
    status: Mapped[str] = mapped_column(String(30), default="open")
    note: Mapped[str | None] = mapped_column(Text)

    customer: Mapped[Customer | None] = relationship()
    employee: Mapped[Employee | None] = relationship()


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(primary_key=True)
    branch_id: Mapped[int | None] = mapped_column(ForeignKey("branches.id"))
    code: Mapped[str] = mapped_column(String(40), unique=True)
    name: Mapped[str] = mapped_column(String(160))
    model: Mapped[str | None] = mapped_column(String(80))
    ip_address: Mapped[str | None] = mapped_column(String(60))
    purpose: Mapped[str] = mapped_column(String(30), default="shared")
    status: Mapped[str] = mapped_column(String(30), default="offline")
    pending_jobs: Mapped[int] = mapped_column(Integer, default=0)
    errors_24h: Mapped[int] = mapped_column(Integer, default=0)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)

    branch: Mapped[Branch | None] = relationship()
