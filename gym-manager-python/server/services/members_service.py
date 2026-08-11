from datetime import date, timedelta
from pathlib import Path
import secrets
import json

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, aliased, joinedload

from ..database import ROOT_DIR
from ..models import (
    AttendanceSession, BankAccount, Customer, Employee, Membership,
    MembershipEvent, MembershipFreeze, Payment, PaymentReceipt, Person, PtEnrollment, PtEnrollmentCoach, ServicePackage, User,
)
from .audit_service import member_audit_logs, record_audit
from .serializers import employee_data, membership_data, membership_event_data, package_data, pagination, person_data, pt_data, payment_data
from .training_schedule import normalize_schedule, schedule_storage
from ..timeutils import utc_now

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
    filename = f"receipt-{utc_now().strftime('%Y%m%d%H%M%S')}-{secrets.token_hex(4)}{suffix}"
    (RECEIPT_DIR / filename).write_bytes(content)
    return f"/uploads/receipts/{filename}"


async def attach_receipts(payment: Payment, uploads: list[UploadFile], actor: User | None):
    if len(uploads) > 10:
        raise HTTPException(status_code=400, detail="Mỗi lần chỉ được tải tối đa 10 ảnh chứng từ.")
    saved = []
    for upload in uploads:
        path = await save_receipt(upload)
        if path:
            payment.receipts.append(
                PaymentReceipt(
                    file_path=path,
                    original_name=upload.filename,
                    uploaded_by_user_id=actor.id if actor else None,
                )
            )
            saved.append(path)
    if saved and not payment.receipt_image_path:
        payment.receipt_image_path = saved[0]
    return saved


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
            "salesEmployee": employee_data(member.sales_employee),
            "trainer": (trainers.get(member.id) or [None])[0],
            "trainers": trainers.get(member.id, []),
            "membership": membership_data(current) if current else None,
            "lastCheckin": last_checkins.get(member.id),
        })
    return {"items": items, "pagination": pagination(page, page_size, total)}


def member_options(db: Session):
    employees = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").order_by(Employee.id).all()
    accounts = db.query(BankAccount).filter(BankAccount.status == "active").order_by(BankAccount.bank_name).all()
    return {
        "employees": [{"id": row.id, "code": row.employee_code, "name": row.person.display_name, "title": row.job_title} for row in employees],
        "plans": list_plans(db),
        "bankAccounts": [{"id": row.id, "label": f"{row.bank_name} · {row.account_number}", "visibility": row.visibility} for row in accounts],
    }


def get_member(db: Session, member_id: int):
    member = db.query(Customer).options(
        joinedload(Customer.person),
        joinedload(Customer.sales_employee).joinedload(Employee.person),
    ).filter(Customer.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội viên.")
    memberships = db.query(Membership).options(
        joinedload(Membership.package), joinedload(Membership.payments).joinedload(Payment.bank_account),
        joinedload(Membership.payments).joinedload(Payment.receipts).joinedload(PaymentReceipt.uploaded_by),
        joinedload(Membership.freezes).joinedload(MembershipFreeze.created_by),
        joinedload(Membership.events).joinedload(MembershipEvent.created_by),
        joinedload(Membership.events).joinedload(MembershipEvent.from_customer).joinedload(Customer.person),
        joinedload(Membership.events).joinedload(MembershipEvent.to_customer).joinedload(Customer.person),
        joinedload(Membership.events).joinedload(MembershipEvent.from_package),
        joinedload(Membership.events).joinedload(MembershipEvent.to_package),
        joinedload(Membership.sale_online_employee).joinedload(Employee.person),
        joinedload(Membership.direct_sales_employee).joinedload(Employee.person),
    ).filter(Membership.customer_id == member_id).order_by(Membership.registered_at.desc(), Membership.id.desc()).all()
    pt_rows = db.query(PtEnrollment).options(joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person), joinedload(PtEnrollment.customer).joinedload(Customer.person)).filter(PtEnrollment.customer_id == member_id).order_by(PtEnrollment.id.desc()).all()
    checkins = db.query(AttendanceSession).filter(AttendanceSession.customer_id == member_id).order_by(AttendanceSession.checked_in_at.desc()).limit(100).all()
    payments = db.query(Payment).options(joinedload(Payment.customer).joinedload(Customer.person), joinedload(Payment.membership).joinedload(Membership.package), joinedload(Payment.receipts).joinedload(PaymentReceipt.uploaded_by)).filter(Payment.customer_id == member_id).order_by(Payment.paid_at.desc()).all()
    membership_events = db.query(MembershipEvent).options(
        joinedload(MembershipEvent.created_by),
        joinedload(MembershipEvent.from_customer).joinedload(Customer.person),
        joinedload(MembershipEvent.to_customer).joinedload(Customer.person),
        joinedload(MembershipEvent.from_package), joinedload(MembershipEvent.to_package),
    ).filter(or_(MembershipEvent.from_customer_id == member_id, MembershipEvent.to_customer_id == member_id)).order_by(MembershipEvent.created_at.desc()).all()
    return {
        "id": member.id, "code": member.customer_code, "mbsCode": member.mbs_card_code,
        **person_data(member.person), "source": member.source, "status": member.status,
        "notes": member.notes,
        "salesEmployeeId": member.sales_employee_id,
        "salesEmployee": member.sales_employee.person.display_name if member.sales_employee else None,
        "memberships": [membership_data(row, include_payments=True, include_history=True) for row in memberships if not row.package.is_pt],
        "membershipEvents": [membership_event_data(row) for row in membership_events],
        "training": [pt_data(row) for row in pt_rows],
        "checkins": [{"id": row.id, "checkedInAt": row.checked_in_at.isoformat(), "checkedOutAt": row.checked_out_at.isoformat() if row.checked_out_at else None, "result": row.result, "status": row.status, "source": row.source} for row in checkins],
        "payments": [payment_data(row) for row in payments],
        "auditLogs": member_audit_logs(db, member_id),
    }


def create_member(db: Session, payload: dict, actor: User | None = None):
    name = str(payload.get("name", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    if not name or not phone:
        raise HTTPException(status_code=422, detail="Họ tên và số điện thoại là bắt buộc.")
    if db.query(Person).filter(Person.phone == phone).first():
        raise HTTPException(status_code=409, detail="Số điện thoại này đã tồn tại.")
    person = Person(display_name=name, phone=phone, email=payload.get("email") or None, gender=payload.get("gender") or None, date_of_birth=_parse_date(payload.get("dateOfBirth")), status="active", biometric_consent_status="not_requested")
    db.add(person); db.flush()
    member = Customer(person_id=person.id, customer_code=f"TMP-{secrets.token_hex(6)}", mbs_card_code=payload.get("mbsCode") or None, sales_employee_id=_int(payload.get("salesEmployeeId")), source=payload.get("source") or "Walk-in", status=payload.get("status") or "lead", notes=payload.get("notes") or None)
    db.add(member); db.flush()
    member.customer_code = f"MB-{member.id:06d}"
    record_audit(db, actor, "create", "member", member.id, f"Tạo hội viên {name}", customer_id=member.id, details={"code": member.customer_code, "phone": phone})
    pt_payload = payload.get("ptEnrollment")
    if isinstance(pt_payload, dict):
        raw_coach_ids = pt_payload.get("coachIds") or []
        coach_ids = list(dict.fromkeys(value for value in (_int(item) for item in raw_coach_ids) if value))
        coaches = db.query(Employee).filter(Employee.id.in_(coach_ids), Employee.status == "active").all() if coach_ids else []
        if len(coaches) != len(coach_ids):
            raise HTTPException(422, "Có Coach không hợp lệ hoặc đã ngừng hoạt động.")
        kind = pt_payload.get("type") if pt_payload.get("type") in ("1:1", "1:2", "1:3") else "1:1"
        sessions = max(_int(pt_payload.get("totalSessions")) or 12, 1)
        starts_at = _parse_date(pt_payload.get("startsAt")) or date.today()
        expires_at = _parse_date(pt_payload.get("expiresAt"))
        if expires_at and expires_at < starts_at:
            raise HTTPException(422, "Ngày hết hạn PT phải sau ngày bắt đầu.")
        schedule_json, schedule_days, schedule_time = schedule_storage(normalize_schedule(pt_payload))
        enrollment = PtEnrollment(
            customer_id=member.id,
            coach_id=coach_ids[0] if coach_ids else None,
            group_type=kind,
            starts_at=starts_at,
            expires_at=expires_at,
            total_sessions=sessions,
            remaining_sessions=sessions,
            schedule_json=schedule_json,
            schedule_days=schedule_days,
            schedule_time=schedule_time,
            status="active",
        )
        db.add(enrollment); db.flush()
        enrollment.coach_assignments = [PtEnrollmentCoach(coach_id=coach_id) for coach_id in coach_ids]
        member.status = "active"
        record_audit(
            db, actor, "create", "pt_enrollment", enrollment.id,
            f"Đăng ký PT {kind} · {sessions} buổi cùng lúc tạo hội viên",
            customer_id=member.id,
            details={"coachIds": coach_ids, "schedule": json.loads(schedule_json) if schedule_json else []},
        )
    db.commit()
    return get_member(db, member.id)


def update_member(db: Session, member_id: int, payload: dict, actor: User | None = None):
    member = db.query(Customer).options(joinedload(Customer.person)).filter(Customer.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội viên.")
    if "name" in payload and not str(payload["name"]).strip():
        raise HTTPException(status_code=422, detail="Họ tên không được để trống.")
    old_name = member.person.display_name
    changed_fields = list(payload.keys())
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
    record_audit(db, actor, "update", "member", member.id, f"Cập nhật hồ sơ {member.person.display_name}", customer_id=member.id, details={"fields": changed_fields, "previousName": old_name})
    db.commit()
    return get_member(db, member_id)


def list_plans(db: Session, include_inactive=False):
    query = db.query(ServicePackage).filter(ServicePackage.is_pt == False)
    if not include_inactive: query = query.filter(ServicePackage.is_active == True)
    rows = query.order_by(ServicePackage.category, ServicePackage.price).all()
    counts = dict(db.query(Membership.package_id, func.count(Membership.id)).filter(Membership.package_id.in_([row.id for row in rows]), Membership.status == "active").group_by(Membership.package_id).all()) if rows else {}
    return [{**package_data(row), "memberCount": counts.get(row.id, 0)} for row in rows]


def create_plan(db: Session, payload: dict, actor: User | None = None):
    name = str(payload.get("name", "")).strip()
    if not name: raise HTTPException(status_code=422, detail="Tên gói là bắt buộc.")
    plan = ServicePackage(code=f"PLAN-{secrets.token_hex(4).upper()}", name=name, category=payload.get("category") or "Fitness", package_type="time", duration_days=max(_int(payload.get("durationDays")) or 1, 1), session_count=None, price=_money(payload.get("price")), is_pt=False, is_active=True)
    db.add(plan); db.flush()
    record_audit(db, actor, "create", "plan", plan.id, f"Tạo gói tập {plan.name}", details={"price": plan.price, "durationDays": plan.duration_days})
    db.commit(); db.refresh(plan)
    return package_data(plan)


def update_plan(db: Session, plan_id: int, payload: dict, actor: User | None = None):
    plan = db.query(ServicePackage).filter(ServicePackage.id == plan_id, ServicePackage.is_pt == False).first()
    if not plan: raise HTTPException(status_code=404, detail="Không tìm thấy gói tập.")
    if "name" in payload: plan.name = str(payload["name"]).strip() or plan.name
    if "category" in payload: plan.category = payload["category"] or plan.category
    if "durationDays" in payload: plan.duration_days = max(_int(payload["durationDays"]) or 1, 1)
    if "price" in payload: plan.price = _money(payload["price"])
    if "active" in payload: plan.is_active = bool(payload["active"])
    record_audit(db, actor, "update", "plan", plan.id, f"Cập nhật gói tập {plan.name}", details={"fields": list(payload.keys())})
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


async def create_membership(db: Session, form: dict, receipts: list[UploadFile], actor: User | None = None):
    member = db.get(Customer, _int(form.get("memberId")))
    plan = db.query(ServicePackage).filter(ServicePackage.id == _int(form.get("planId")), ServicePackage.is_pt == False, ServicePackage.is_active == True).first()
    if not member or not plan: raise HTTPException(status_code=422, detail="Hội viên hoặc gói tập không hợp lệ.")
    starts_at = _parse_date(form.get("startsAt")) or date.today()
    final_price = _money(form.get("finalPrice"), plan.price or 0)
    paid = _money(form.get("paidAmount"))
    row = Membership(customer_id=member.id, package_id=plan.id, code=f"TMP-{secrets.token_hex(6)}", registered_at=date.today(), starts_at=starts_at, expires_at=_parse_date(form.get("expiresAt")) or (starts_at + timedelta(days=plan.duration_days) if plan.duration_days else None), remaining_sessions=None, final_price=final_price, deposit_amount=paid, paid_amount=paid, debt_amount=max(final_price-paid, 0), debt_due_date=_parse_date(form.get("debtDueDate")), sale_online_employee_id=_int(form.get("saleOnlineEmployeeId")), direct_sales_employee_id=_int(form.get("directSaleEmployeeId")), status="active")
    db.add(row); db.flush(); row.code = f"MS-{row.id:06d}"
    if paid:
        payment = Payment(customer_id=member.id, membership_id=row.id, bank_account_id=_int(form.get("bankAccountId")), payment_no=f"PAY-{row.id:06d}-001", paid_at=utc_now(), amount=paid, method=form.get("paymentMethod") or "cash", channel="counter", shift_date=date.today(), note="Thanh toán đăng ký gói")
        db.add(payment)
        await attach_receipts(payment, receipts, actor)
        db.flush()
    record_audit(db, actor, "create", "membership", row.id, f"Đăng ký gói {plan.name}", customer_id=member.id, details={"startsAt": row.starts_at, "expiresAt": row.expires_at, "finalPrice": final_price, "paidAmount": paid})
    if paid:
        record_audit(db, actor, "payment", "payment", payment.id, f"Ghi nhận thanh toán {paid:,.0f} ₫", customer_id=member.id, details={"membershipId": row.id, "receiptCount": len(receipts)})
    member.status = "active"; db.commit()
    row = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package), joinedload(Membership.sale_online_employee).joinedload(Employee.person), joinedload(Membership.direct_sales_employee).joinedload(Employee.person)).get(row.id)
    return membership_data(row)


async def update_membership(db: Session, membership_id: int, form: dict, receipts: list[UploadFile], actor: User | None = None):
    row = db.query(Membership).options(joinedload(Membership.package)).filter(Membership.id == membership_id).first()
    if not row or row.package.is_pt: raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký gói.")
    row.starts_at = _parse_date(form.get("startsAt")) or row.starts_at
    row.expires_at = _parse_date(form.get("expiresAt"))
    row.final_price = _money(form.get("finalPrice"), row.final_price)
    previous_paid = row.paid_amount or 0
    next_paid = _money(form.get("paidAmount"), previous_paid)
    if next_paid < previous_paid:
        raise HTTPException(status_code=422, detail="Không thể giảm số tiền đã thu. Hãy tạo nghiệp vụ hoàn tiền riêng.")
    row.paid_amount = next_paid
    row.deposit_amount = row.paid_amount
    row.debt_amount = max(row.final_price - row.paid_amount, 0)
    row.debt_due_date = _parse_date(form.get("debtDueDate")) if row.debt_amount else None
    if form.get("status") in ("active", "pending", "frozen", "cancelled"): row.status = form["status"]
    delta = next_paid - previous_paid
    payment = None
    if delta > 0:
        sequence = db.query(Payment).filter(Payment.membership_id == row.id).count() + 1
        payment = Payment(customer_id=row.customer_id, membership_id=row.id, payment_no=f"PAY-{row.id:06d}-{sequence:03d}", paid_at=utc_now(), shift_date=date.today(), note="Thanh toán gói", amount=delta, method=form.get("paymentMethod") or "cash", bank_account_id=_int(form.get("bankAccountId")))
        db.add(payment)
        await attach_receipts(payment, receipts, actor)
        db.flush()
        record_audit(db, actor, "payment", "payment", payment.id, f"Ghi nhận thanh toán {delta:,.0f} ₫", customer_id=row.customer_id, details={"membershipId": row.id, "receiptCount": len(receipts)})
    record_audit(db, actor, "update", "membership", row.id, f"Cập nhật gói {row.package.name}", customer_id=row.customer_id, details={"fields": list(form.keys()), "expiresAt": row.expires_at})
    db.commit()
    row = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package), joinedload(Membership.sale_online_employee).joinedload(Employee.person), joinedload(Membership.direct_sales_employee).joinedload(Employee.person)).get(row.id)
    return membership_data(row)


def update_debt_due_date(db: Session, membership_id: int, payload: dict, actor: User | None = None):
    row = db.query(Membership).options(joinedload(Membership.package)).filter(Membership.id == membership_id).first()
    if not row or row.package.is_pt:
        raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký gói.")
    if not row.debt_amount or row.debt_amount <= 0:
        raise HTTPException(status_code=422, detail="Gói này hiện không có công nợ.")
    due_date = _parse_date(payload.get("debtDueDate"))
    if not due_date:
        raise HTTPException(status_code=422, detail="Vui lòng chọn hạn thanh toán.")
    row.debt_due_date = due_date
    record_audit(db, actor, "update", "membership", row.id, f"Đặt hạn thanh toán {due_date.strftime('%d/%m/%Y')}", customer_id=row.customer_id, details={"debtDueDate": due_date})
    db.commit()
    row = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package), joinedload(Membership.sale_online_employee).joinedload(Employee.person), joinedload(Membership.direct_sales_employee).joinedload(Employee.person)).get(row.id)
    return membership_data(row)


async def upload_payment_receipts(db: Session, payment_id: int, receipts: list[UploadFile], actor: User | None = None):
    payment = db.query(Payment).options(joinedload(Payment.customer).joinedload(Customer.person), joinedload(Payment.membership).joinedload(Membership.package), joinedload(Payment.receipts).joinedload(PaymentReceipt.uploaded_by)).filter(Payment.id == payment_id).first()
    if not payment:
        raise HTTPException(status_code=404, detail="Không tìm thấy giao dịch thanh toán.")
    if not receipts:
        raise HTTPException(status_code=422, detail="Vui lòng chọn ít nhất một ảnh chứng từ.")
    saved = await attach_receipts(payment, receipts, actor)
    record_audit(db, actor, "upload_receipt", "payment", payment.id, f"Thêm {len(saved)} chứng từ cho {payment.payment_no}", customer_id=payment.customer_id, details={"files": [upload.filename for upload in receipts]})
    db.commit()
    db.refresh(payment)
    return payment_data(payment)


def freeze_membership(db: Session, membership_id: int, payload: dict, actor: User):
    row = db.query(Membership).options(joinedload(Membership.package), joinedload(Membership.customer).joinedload(Customer.person)).filter(Membership.id == membership_id).first()
    if not row or row.package.is_pt:
        raise HTTPException(404, "Không tìm thấy đăng ký gói.")
    if row.status in ("cancelled", "expired"):
        raise HTTPException(422, "Không thể bảo lưu gói đã hủy hoặc hết hạn.")
    starts_at = _parse_date(payload.get("startsAt"))
    ends_at = _parse_date(payload.get("endsAt"))
    reason = str(payload.get("reason", "")).strip()
    if not starts_at or not ends_at or ends_at < starts_at:
        raise HTTPException(422, "Khoảng thời gian bảo lưu chưa hợp lệ.")
    if starts_at < date.today():
        raise HTTPException(422, "Ngày bắt đầu bảo lưu không được ở quá khứ.")
    if not reason:
        raise HTTPException(422, "Vui lòng nhập lý do bảo lưu.")
    overlap = db.query(MembershipFreeze).filter(
        MembershipFreeze.membership_id == row.id,
        MembershipFreeze.starts_at <= ends_at,
        MembershipFreeze.ends_at >= starts_at,
    ).first()
    if overlap:
        raise HTTPException(409, "Thời gian này trùng với một lần bảo lưu đã có.")
    if not row.expires_at:
        raise HTTPException(422, "Gói không có ngày hết hạn nên không thể cộng bù tự động.")
    days = (ends_at - starts_at).days + 1
    previous_expiry = row.expires_at
    row.expires_at = row.expires_at + timedelta(days=days)
    freeze = MembershipFreeze(
        membership_id=row.id,
        starts_at=starts_at,
        ends_at=ends_at,
        compensated_days=days,
        reason=reason,
        created_by_user_id=actor.id,
    )
    event = MembershipEvent(
        membership_id=row.id,
        action="freeze",
        from_customer_id=row.customer_id,
        to_customer_id=row.customer_id,
        from_package_id=row.package_id,
        to_package_id=row.package_id,
        effective_at=starts_at,
        reason=reason,
        created_by_user_id=actor.id,
        details_json=json.dumps({"startsAt": str(starts_at), "endsAt": str(ends_at), "compensatedDays": days, "previousExpiry": str(previous_expiry), "newExpiry": str(row.expires_at)}, ensure_ascii=False),
    )
    db.add_all([freeze, event])
    db.flush()
    record_audit(db, actor, "freeze", "membership", row.id, f"Bảo lưu gói {row.package.name} trong {days} ngày", customer_id=row.customer_id, details={"startsAt": starts_at, "endsAt": ends_at, "previousExpiry": previous_expiry, "newExpiry": row.expires_at})
    db.commit()
    return get_member(db, row.customer_id)


def membership_action(db: Session, membership_id: int, payload: dict, actor: User):
    row = db.query(Membership).options(joinedload(Membership.package), joinedload(Membership.customer).joinedload(Customer.person)).filter(Membership.id == membership_id).first()
    if not row or row.package.is_pt:
        raise HTTPException(404, "Không tìm thấy đăng ký gói.")
    action = payload.get("action")
    reason = str(payload.get("reason", "")).strip()
    if action not in ("transfer", "change", "upgrade", "cancel"):
        raise HTTPException(422, "Nghiệp vụ gói không hợp lệ.")
    if not reason:
        raise HTTPException(422, "Vui lòng nhập lý do để lưu lịch sử đối soát.")
    old_customer_id, old_package_id = row.customer_id, row.package_id
    old_customer_name, old_package_name = row.customer.person.display_name, row.package.name
    details = {}
    summary = ""
    if action == "transfer":
        target_id = _int(payload.get("targetMemberId"))
        target = db.query(Customer).options(joinedload(Customer.person)).filter(Customer.id == target_id).first()
        if not target or target.id == row.customer_id:
            raise HTTPException(422, "Hội viên nhận chuyển nhượng không hợp lệ.")
        existing = db.query(Membership).join(ServicePackage).filter(
            Membership.customer_id == target.id,
            Membership.status == "active",
            ServicePackage.is_pt == False,
            or_(Membership.expires_at == None, Membership.expires_at >= date.today()),
        ).first()
        if existing:
            raise HTTPException(409, "Hội viên nhận đang có một gói hoạt động.")
        row.customer_id = target.id
        summary = f"Chuyển gói {old_package_name} từ {old_customer_name} sang {target.person.display_name}"
        details = {"fromMember": old_customer_name, "toMember": target.person.display_name}
        new_customer_id, new_package_id = target.id, old_package_id
    elif action in ("change", "upgrade"):
        plan = db.query(ServicePackage).filter(ServicePackage.id == _int(payload.get("planId")), ServicePackage.is_pt == False, ServicePackage.is_active == True).first()
        if not plan or plan.id == row.package_id:
            raise HTTPException(422, "Vui lòng chọn một gói tập khác.")
        new_price = _money(payload.get("finalPrice"), plan.price or 0)
        if new_price < (row.paid_amount or 0):
            raise HTTPException(422, "Giá gói mới không được thấp hơn số tiền đã thu.")
        previous_price = row.final_price
        row.package_id = plan.id
        row.final_price = new_price
        row.debt_amount = max(new_price - (row.paid_amount or 0), 0)
        if payload.get("expiresAt"):
            row.expires_at = _parse_date(payload.get("expiresAt"))
        summary = f"{'Nâng cấp' if action == 'upgrade' else 'Đổi'} gói {old_package_name} sang {plan.name}"
        details = {"fromPackage": old_package_name, "toPackage": plan.name, "previousPrice": previous_price, "newPrice": new_price, "newDebt": row.debt_amount}
        new_customer_id, new_package_id = old_customer_id, plan.id
    else:
        if row.status == "cancelled":
            raise HTTPException(409, "Gói này đã được hủy trước đó.")
        row.status = "cancelled"
        summary = f"Hủy gói {old_package_name} của {old_customer_name}"
        details = {"paidAmount": row.paid_amount, "debtAmount": row.debt_amount, "refundCreated": False}
        new_customer_id, new_package_id = old_customer_id, old_package_id
    event = MembershipEvent(
        membership_id=row.id,
        action=action,
        from_customer_id=old_customer_id,
        to_customer_id=new_customer_id,
        from_package_id=old_package_id,
        to_package_id=new_package_id,
        effective_at=_parse_date(payload.get("effectiveAt")) or date.today(),
        reason=reason,
        details_json=json.dumps(details, ensure_ascii=False, default=str),
        created_by_user_id=actor.id,
    )
    db.add(event)
    record_audit(db, actor, action, "membership", row.id, summary, customer_id=new_customer_id, details={**details, "reason": reason})
    if action == "transfer":
        record_audit(db, actor, action, "membership", row.id, summary, customer_id=old_customer_id, details={**details, "reason": reason})
    db.commit()
    return {"membershipId": row.id, "customerId": new_customer_id, "action": action, "summary": summary}
