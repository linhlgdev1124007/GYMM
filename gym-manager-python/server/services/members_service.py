from datetime import date, datetime, timedelta
from pathlib import Path
import secrets

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, aliased, joinedload

from ..database import ROOT_DIR
from ..models import (
    AttendanceSession, BankAccount, Branch, Customer, Employee, Membership,
    Payment, Person, PtEnrollment, PtEnrollmentCoach, ServicePackage,
)
from .serializers import membership_data, package_data, pagination, person_data, pt_data, payment_data

RECEIPT_DIR = ROOT_DIR / "server" / "uploads" / "receipts"
RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


def _parse_date(value):
    return date.fromisoformat(value) if value else None


def _int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _money(value, default=0):
    try:
        return max(float(value), 0) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


async def save_receipt(upload: UploadFile | None) -> str | None:
    if not upload or not upload.filename:
        return None
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Phiếu thu phải là ảnh JPG, PNG hoặc WebP.")
    content = await upload.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ảnh phiếu thu không được vượt quá 5 MB.")
    filename = f"receipt-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}{suffix}"
    (RECEIPT_DIR / filename).write_bytes(content)
    return f"/uploads/receipts/{filename}"


def list_members(db: Session, q: str, member_status: str, page: int, page_size: int, sort: str = "newest", view: str = "all", package_id: int | None = None, trainer_id: int | None = None, expiring_days: int = 14, payment_status: str = "all", overdue_days: int = 7):
    query = db.query(Customer).options(
        joinedload(Customer.person),
        joinedload(Customer.sales_employee).joinedload(Employee.person),
        joinedload(Customer.memberships).joinedload(Membership.package),
    ).join(Customer.person)
    if q:
        term = q.strip()
        query = query.filter(or_(
            Person.display_name.contains(term), Person.phone.contains(term),
            Person.email.contains(term), Customer.customer_code.contains(term), Customer.mbs_card_code.contains(term),
        ))
    latest_regular_id = db.query(Membership.id).join(ServicePackage).filter(
        Membership.customer_id == Customer.id, ServicePackage.is_pt == False
    ).order_by(Membership.registered_at.desc(), Membership.id.desc()).limit(1).correlate(Customer).scalar_subquery()
    status_membership = aliased(Membership)
    def latest_status_exists(*conditions):
        return db.query(status_membership.id).filter(status_membership.id == latest_regular_id, *conditions).exists()
    if member_status == "active":
        query = query.filter(latest_status_exists(status_membership.status == "active", or_(status_membership.expires_at == None, status_membership.expires_at >= date.today())))
    elif member_status == "expired":
        query = query.filter(latest_status_exists(status_membership.expires_at < date.today()))
    elif member_status == "expiring":
        query = query.filter(latest_status_exists(status_membership.status == "active", status_membership.expires_at >= date.today(), status_membership.expires_at <= date.today() + timedelta(days=expiring_days)))
    elif member_status == "frozen":
        query = query.filter(latest_status_exists(status_membership.status == "frozen"))
    elif member_status == "inactive":
        query = query.filter(or_(Customer.status == "inactive", latest_status_exists(status_membership.status == "cancelled")))
    if payment_status == "overdue":
        query = query.filter(latest_status_exists(
            status_membership.debt_amount > 0,
            status_membership.debt_due_date != None,
            status_membership.debt_due_date < date.today(),
            status_membership.debt_due_date >= date.today() - timedelta(days=overdue_days),
        ))
    if view == "active":
        query = query.filter(latest_status_exists(status_membership.status == "active", or_(status_membership.expires_at == None, status_membership.expires_at >= date.today())))
    elif view == "expiring":
        query = query.filter(latest_status_exists(status_membership.status == "active", status_membership.expires_at >= date.today(), status_membership.expires_at <= date.today() + timedelta(days=14)))
    elif view == "debt":
        query = query.filter(latest_status_exists(status_membership.debt_amount > 0))
    elif view == "no_pt":
        query = query.filter(~db.query(PtEnrollment.id).filter(PtEnrollment.customer_id == Customer.id, PtEnrollment.status == "active").exists())
    if package_id:
        query = query.filter(latest_status_exists(status_membership.package_id == package_id))
    if trainer_id:
        query = query.filter(db.query(PtEnrollmentCoach.enrollment_id).join(PtEnrollment).filter(PtEnrollment.customer_id == Customer.id, PtEnrollmentCoach.coach_id == trainer_id, PtEnrollment.status == "active").exists())
    total = query.count()
    ordering = Person.display_name.asc() if sort == "name" else (Customer.status.asc() if sort == "status" else Customer.id.desc())
    rows = query.order_by(ordering).offset((page - 1) * page_size).limit(page_size).all()
    ids = [row.id for row in rows]
    last_checkins = {}
    trainers = {}
    if ids:
        checkins = db.query(AttendanceSession).filter(AttendanceSession.customer_id.in_(ids)).order_by(AttendanceSession.checked_in_at.desc()).all()
        for checkin in checkins:
            last_checkins.setdefault(checkin.customer_id, checkin.checked_in_at.isoformat())
        training_rows = db.query(PtEnrollment).options(joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person)).filter(PtEnrollment.customer_id.in_(ids), PtEnrollment.status == "active").all()
        for training in training_rows:
            assigned = trainers.setdefault(training.customer_id, [])
            for assignment in training.coach_assignments:
                if not any(item["id"] == assignment.coach.id for item in assigned):
                    assigned.append({"id": assignment.coach.id, "name": assignment.coach.person.display_name})
    items = []
    for member in rows:
        regular = [m for m in member.memberships if not m.package.is_pt]
        current = sorted(regular, key=lambda row: (row.registered_at or date.min, row.id), reverse=True)[0] if regular else None
        items.append({
            "id": member.id,
            "code": member.customer_code,
            "mbsCode": member.mbs_card_code,
            **person_data(member.person),
            "source": member.source,
            "status": member.status,
            "trainer": (trainers.get(member.id) or [None])[0],
            "trainers": trainers.get(member.id, []),
            "membership": membership_data(current) if current else None,
            "lastCheckin": last_checkins.get(member.id),
        })
    return {"items": items, "pagination": pagination(page, page_size, total)}


def member_options(db: Session):
    branches = db.query(Branch).filter(Branch.status == "active").order_by(Branch.name).all()
    employees = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").order_by(Employee.id).all()
    accounts = db.query(BankAccount).filter(BankAccount.status == "active").order_by(BankAccount.bank_name).all()
    return {
        "branches": [{"id": row.id, "name": row.name} for row in branches],
        "employees": [{"id": row.id, "name": row.person.display_name, "title": row.job_title} for row in employees],
        "plans": list_plans(db),
        "bankAccounts": [{"id": row.id, "label": f"{row.bank_name} · {row.account_number}", "visibility": row.visibility} for row in accounts],
    }


def get_member(db: Session, member_id: int):
    member = db.query(Customer).options(
        joinedload(Customer.person), joinedload(Customer.branch),
        joinedload(Customer.sales_employee).joinedload(Employee.person),
    ).filter(Customer.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội viên.")
    memberships = db.query(Membership).options(
        joinedload(Membership.package), joinedload(Membership.payments).joinedload(Payment.bank_account),
        joinedload(Membership.sale_online_employee).joinedload(Employee.person),
        joinedload(Membership.direct_sales_employee).joinedload(Employee.person),
    ).filter(Membership.customer_id == member_id).order_by(Membership.registered_at.desc(), Membership.id.desc()).all()
    pt_rows = db.query(PtEnrollment).options(joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person), joinedload(PtEnrollment.customer).joinedload(Customer.person)).filter(PtEnrollment.customer_id == member_id).order_by(PtEnrollment.id.desc()).all()
    checkins = db.query(AttendanceSession).filter(AttendanceSession.customer_id == member_id).order_by(AttendanceSession.checked_in_at.desc()).limit(100).all()
    payments = db.query(Payment).options(joinedload(Payment.customer).joinedload(Customer.person), joinedload(Payment.membership).joinedload(Membership.package)).filter(Payment.customer_id == member_id).order_by(Payment.paid_at.desc()).all()
    return {
        "id": member.id, "code": member.customer_code, "mbsCode": member.mbs_card_code,
        **person_data(member.person), "source": member.source, "status": member.status,
        "notes": member.notes, "branch": member.branch.name if member.branch else None,
        "salesEmployeeId": member.sales_employee_id,
        "salesEmployee": member.sales_employee.person.display_name if member.sales_employee else None,
        "memberships": [membership_data(row, include_payments=True) for row in memberships if not row.package.is_pt],
        "training": [pt_data(row) for row in pt_rows],
        "checkins": [{"id": row.id, "checkedInAt": row.checked_in_at.isoformat(), "checkedOutAt": row.checked_out_at.isoformat() if row.checked_out_at else None, "result": row.result, "status": row.status, "source": row.source} for row in checkins],
        "payments": [payment_data(row) for row in payments],
    }


def create_member(db: Session, payload: dict):
    name = str(payload.get("name", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    if not name or not phone:
        raise HTTPException(status_code=422, detail="Họ tên và số điện thoại là bắt buộc.")
    if db.query(Person).filter(Person.phone == phone).first():
        raise HTTPException(status_code=409, detail="Số điện thoại này đã tồn tại.")
    person = Person(display_name=name, phone=phone, email=payload.get("email") or None, gender=payload.get("gender") or None, date_of_birth=_parse_date(payload.get("dateOfBirth")), status="active", biometric_consent_status="not_requested")
    db.add(person); db.flush()
    branch_id = _int(payload.get("branchId")) or (db.query(Branch.id).order_by(Branch.id).scalar())
    member = Customer(person_id=person.id, branch_id=branch_id, customer_code=f"TMP-{secrets.token_hex(6)}", mbs_card_code=payload.get("mbsCode") or None, sales_employee_id=_int(payload.get("salesEmployeeId")), source=payload.get("source") or "Walk-in", status=payload.get("status") or "lead", notes=payload.get("notes") or None)
    db.add(member); db.flush()
    member.customer_code = f"MB-{member.id:06d}"
    db.commit()
    return get_member(db, member.id)


def update_member(db: Session, member_id: int, payload: dict):
    member = db.query(Customer).options(joinedload(Customer.person)).filter(Customer.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội viên.")
    if "name" in payload and not str(payload["name"]).strip():
        raise HTTPException(status_code=422, detail="Họ tên không được để trống.")
    member.person.display_name = str(payload.get("name", member.person.display_name)).strip()
    for source, target in [("phone", "phone"), ("email", "email"), ("gender", "gender")]:
        if source in payload:
            setattr(member.person, target, payload[source] or None)
    if "dateOfBirth" in payload:
        member.person.date_of_birth = _parse_date(payload.get("dateOfBirth"))
    if "mbsCode" in payload: member.mbs_card_code = payload.get("mbsCode") or None
    if "source" in payload: member.source = payload.get("source") or None
    if "notes" in payload: member.notes = payload.get("notes") or None
    if "salesEmployeeId" in payload: member.sales_employee_id = _int(payload.get("salesEmployeeId"))
    if payload.get("status") in ("lead", "active", "blocked", "inactive", "frozen"): member.status = payload["status"]
    db.commit()
    return get_member(db, member_id)


def list_plans(db: Session, include_inactive=False):
    query = db.query(ServicePackage).filter(ServicePackage.is_pt == False)
    if not include_inactive: query = query.filter(ServicePackage.is_active == True)
    rows = query.order_by(ServicePackage.category, ServicePackage.price).all()
    counts = dict(db.query(Membership.package_id, func.count(Membership.id)).filter(Membership.package_id.in_([row.id for row in rows]), Membership.status == "active").group_by(Membership.package_id).all()) if rows else {}
    return [{**package_data(row), "memberCount": counts.get(row.id, 0)} for row in rows]


def create_plan(db: Session, payload: dict):
    name = str(payload.get("name", "")).strip()
    if not name: raise HTTPException(status_code=422, detail="Tên gói là bắt buộc.")
    plan = ServicePackage(code=f"PLAN-{secrets.token_hex(4).upper()}", name=name, category=payload.get("category") or "Fitness", package_type="time", duration_days=max(_int(payload.get("durationDays")) or 1, 1), session_count=None, price=_money(payload.get("price")), is_pt=False, is_active=True)
    db.add(plan); db.commit(); db.refresh(plan)
    return package_data(plan)


def update_plan(db: Session, plan_id: int, payload: dict):
    plan = db.query(ServicePackage).filter(ServicePackage.id == plan_id, ServicePackage.is_pt == False).first()
    if not plan: raise HTTPException(status_code=404, detail="Không tìm thấy gói tập.")
    if "name" in payload: plan.name = str(payload["name"]).strip() or plan.name
    if "category" in payload: plan.category = payload["category"] or plan.category
    if "durationDays" in payload: plan.duration_days = max(_int(payload["durationDays"]) or 1, 1)
    if "price" in payload: plan.price = _money(payload["price"])
    if "active" in payload: plan.is_active = bool(payload["active"])
    db.commit(); return package_data(plan)


def list_memberships(db: Session, q: str, membership_status: str, page: int, page_size: int):
    query = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package), joinedload(Membership.sale_online_employee).joinedload(Employee.person), joinedload(Membership.direct_sales_employee).joinedload(Employee.person)).join(Membership.package).filter(ServicePackage.is_pt == False)
    if q:
        query = query.join(Membership.customer).join(Customer.person).filter(or_(Person.display_name.contains(q), Membership.code.contains(q), ServicePackage.name.contains(q)))
    if membership_status == "expiring":
        query = query.filter(Membership.status == "active", Membership.expires_at >= date.today(), Membership.expires_at <= date.today() + timedelta(days=14))
    elif membership_status == "expired":
        query = query.filter(Membership.expires_at < date.today())
    elif membership_status and membership_status != "all":
        query = query.filter(Membership.status == membership_status)
    total = query.count(); rows = query.order_by(Membership.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [membership_data(row) for row in rows]
    return {"items": items, "pagination": pagination(page, page_size, total)}


async def create_membership(db: Session, form: dict, receipt: UploadFile | None):
    member = db.get(Customer, _int(form.get("memberId")))
    plan = db.query(ServicePackage).filter(ServicePackage.id == _int(form.get("planId")), ServicePackage.is_pt == False, ServicePackage.is_active == True).first()
    if not member or not plan: raise HTTPException(status_code=422, detail="Hội viên hoặc gói tập không hợp lệ.")
    starts_at = _parse_date(form.get("startsAt")) or date.today()
    final_price = _money(form.get("finalPrice"), plan.price or 0)
    paid = _money(form.get("paidAmount"))
    row = Membership(customer_id=member.id, package_id=plan.id, code=f"TMP-{secrets.token_hex(6)}", registered_at=date.today(), starts_at=starts_at, expires_at=_parse_date(form.get("expiresAt")) or (starts_at + timedelta(days=plan.duration_days) if plan.duration_days else None), remaining_sessions=None, final_price=final_price, deposit_amount=paid, paid_amount=paid, debt_amount=max(final_price-paid, 0), debt_due_date=_parse_date(form.get("debtDueDate")), sale_online_employee_id=_int(form.get("saleOnlineEmployeeId")), direct_sales_employee_id=_int(form.get("directSaleEmployeeId")), status="active")
    db.add(row); db.flush(); row.code = f"MS-{row.id:06d}"
    if paid:
        receipt_path = await save_receipt(receipt)
        db.add(Payment(customer_id=member.id, membership_id=row.id, bank_account_id=_int(form.get("bankAccountId")), payment_no=f"PAY-{row.id:06d}-001", paid_at=datetime.utcnow(), amount=paid, method=form.get("paymentMethod") or "cash", channel="counter", shift_date=date.today(), receipt_image_path=receipt_path, note="Thanh toán đăng ký gói"))
    member.status = "active"; db.commit()
    row = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package), joinedload(Membership.sale_online_employee).joinedload(Employee.person), joinedload(Membership.direct_sales_employee).joinedload(Employee.person)).get(row.id)
    return membership_data(row)


async def update_membership(db: Session, membership_id: int, form: dict, receipt: UploadFile | None):
    row = db.query(Membership).options(joinedload(Membership.package)).filter(Membership.id == membership_id).first()
    if not row or row.package.is_pt: raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký gói.")
    row.starts_at = _parse_date(form.get("startsAt")) or row.starts_at
    row.expires_at = _parse_date(form.get("expiresAt"))
    row.final_price = _money(form.get("finalPrice"), row.final_price)
    row.paid_amount = _money(form.get("paidAmount"), row.paid_amount)
    row.deposit_amount = row.paid_amount
    row.debt_amount = max(row.final_price - row.paid_amount, 0)
    row.debt_due_date = _parse_date(form.get("debtDueDate")) if row.debt_amount else None
    if form.get("status") in ("active", "pending", "frozen", "cancelled"): row.status = form["status"]
    payment = db.query(Payment).filter(Payment.membership_id == row.id).order_by(Payment.paid_at.desc()).first()
    if row.paid_amount and not payment:
        payment = Payment(customer_id=row.customer_id, membership_id=row.id, payment_no=f"PAY-{row.id:06d}-001", paid_at=datetime.utcnow(), shift_date=date.today(), note="Thanh toán gói")
        db.add(payment)
    if payment:
        payment.amount = row.paid_amount; payment.method = form.get("paymentMethod") or payment.method; payment.bank_account_id = _int(form.get("bankAccountId"))
        receipt_path = await save_receipt(receipt)
        if receipt_path: payment.receipt_image_path = receipt_path
    db.commit()
    row = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package), joinedload(Membership.sale_online_employee).joinedload(Employee.person), joinedload(Membership.direct_sales_employee).joinedload(Employee.person)).get(row.id)
    return membership_data(row)


def update_debt_due_date(db: Session, membership_id: int, payload: dict):
    row = db.query(Membership).options(joinedload(Membership.package)).filter(Membership.id == membership_id).first()
    if not row or row.package.is_pt:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký gói.")
    if not row.debt_amount or row.debt_amount <= 0:
        raise HTTPException(status_code=422, detail="Gói này hiện không có công nợ.")
    due_date = _parse_date(payload.get("debtDueDate"))
    if not due_date:
        raise HTTPException(status_code=422, detail="Vui lòng chọn hạn thanh toán.")
    row.debt_due_date = due_date
    db.commit()
    row = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package), joinedload(Membership.sale_online_employee).joinedload(Employee.person), joinedload(Membership.direct_sales_employee).joinedload(Employee.person)).get(row.id)
    return membership_data(row)
