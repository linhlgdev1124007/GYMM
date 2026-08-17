from datetime import UTC, date, datetime, timedelta
from pathlib import Path
import secrets
import json

from fastapi import HTTPException, UploadFile, status
from sqlalchemy import Integer, and_, case, cast, func, or_
from sqlalchemy.orm import Session, aliased, joinedload

from ..database import ROOT_DIR
from ..models import (
    AttendanceSession, BankAccount, Customer, DahCustomerIdentity, DahWebhookEvent, Employee, EmployeeJobTitle, Membership,
    MembershipEvent, MembershipFreeze, Payment, PaymentReceipt, Person, PtEnrollment, PtEnrollmentCoach, PtSessionLog, ServicePackage, User, DayPassVisit,
)
from .audit_service import member_audit_logs, record_audit
from .day_passes_service import mark_converted_day_pass
from . import dah_service
from .membership_lifecycle import activate_membership, _complete_freeze, freeze_affects_day, freeze_compensation_days, refresh_membership_lifecycle
from .serializers import employee_data, membership_data, membership_event_data, package_data, pagination, person_data, pt_data, payment_data
from .training_schedule import normalize_schedule, schedule_storage
from ..timeutils import VIETNAM_TZ, utc_iso, utc_now, utc_vietnam_date, vietnam_today

RECEIPT_DIR = ROOT_DIR / "server" / "uploads" / "receipts"
RECEIPT_DIR.mkdir(parents=True, exist_ok=True)
ALLOWED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}
CUSTOMER_CODE_PREFIX = "CUS"
CUSTOMER_CODE_WIDTH = 7
SALES_TITLE_KEYWORDS = ("sale",)
MEMBER_AUDIT_FIELD_LABELS = {
    "name": "Họ tên",
    "phone": "SĐT",
    "email": "Email",
    "gender": "Giới tính",
    "dateOfBirth": "Ngày sinh",
    "mbsCode": "Mã MBS",
    "personUuid": "Định danh DAH",
    "source": "Nguồn khách",
    "notes": "Ghi chú",
    "salesEmployeeId": "Nhân viên phụ trách",
}
MEMBERSHIP_AUDIT_FIELD_LABELS = {
    "startsAt": "Ngày bắt đầu",
    "expiresAt": "Ngày hết hạn",
    "finalPrice": "Giá gói",
    "paidAmount": "Đã thanh toán",
    "debtDueDate": "Hạn thanh toán",
    "status": "Trạng thái",
    "activationDate": "Ngày kích hoạt",
}


def _parse_date(value):
    if not value:
        return None
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Ngày không hợp lệ. Vui lòng dùng định dạng YYYY-MM-DD.") from exc


def _parse_paid_at(value):
    if not value:
        return utc_now()
    text = str(value).strip()
    if not text:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Ngày thu thực tế không hợp lệ.") from exc
    if parsed.tzinfo:
        return parsed.astimezone(UTC).replace(tzinfo=None)
    return parsed.replace(tzinfo=VIETNAM_TZ).astimezone(UTC).replace(tzinfo=None)


def _attendance_iso(value, source: str | None):
    if not value:
        return None
    return value.isoformat() if source == "dah" else utc_iso(value)


def _int(value):
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _text(value, limit=255):
    text = str(value or "").strip()
    if not text or text.lower() in {"null", "none", "undefined"}:
        return None
    return text[:limit]


def _money(value, default=0):
    try:
        return max(float(value), 0) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def _day_pass_conversion_context(db: Session, day_pass_id: int | None, policy: str):
    if not day_pass_id or policy != "deducted":
        return 0
    row = db.query(DayPassVisit).filter(DayPassVisit.id == day_pass_id).first()
    if not row:
        raise HTTPException(404, "Không tìm thấy lượt tập ngày cần chuyển đổi.")
    if row.status != "active":
        raise HTTPException(409, "Lượt tập ngày này đã được xử lý trước đó.")
    return float(row.charged_amount or 0)


def _audit_display_value(value):
    if value in (None, ""):
        return "—"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _employee_display_name(db: Session, employee_id: int | None):
    if not employee_id:
        return None
    employee = db.get(Employee, employee_id)
    return employee.person.display_name if employee and employee.person else f"Nhân viên #{employee_id}"


def _bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _customer_code_number(code: str | None) -> int | None:
    if not code or not code.startswith(CUSTOMER_CODE_PREFIX):
        return None
    suffix = code[len(CUSTOMER_CODE_PREFIX):]
    return int(suffix) if suffix.isdigit() else None


def _next_customer_code(db: Session) -> str:
    max_number = 0
    for (code,) in db.query(Customer.customer_code).filter(
        Customer.customer_code.like(f"{CUSTOMER_CODE_PREFIX}%")
    ):
        max_number = max(max_number, _customer_code_number(code) or 0)
    next_number = max_number + 1
    width = max(CUSTOMER_CODE_WIDTH, len(str(next_number)))
    return f"{CUSTOMER_CODE_PREFIX}{next_number:0{width}d}"


def _customer_code_sort_expression(db: Session):
    suffix = func.substr(Customer.customer_code, len(CUSTOMER_CODE_PREFIX) + 1)
    number = cast(suffix, Integer)
    if db.bind and db.bind.dialect.name == "mysql":
        is_customer_code = Customer.customer_code.op("REGEXP")(f"^{CUSTOMER_CODE_PREFIX}[0-9]+$")
    else:
        is_customer_code = Customer.customer_code.op("GLOB")(f"{CUSTOMER_CODE_PREFIX}[0-9]*")
    return case((is_customer_code, number), else_=0)


def _is_sales_employee(employee: Employee | None) -> bool:
    title = str(employee.job_title if employee else "").casefold()
    return any(keyword in title for keyword in SALES_TITLE_KEYWORDS)


def _sales_employee_id(db: Session, value) -> int | None:
    employee_id = _int(value)
    if not employee_id:
        return None
    employee = db.query(Employee).filter(Employee.id == employee_id, Employee.status == "active").first()
    if not _is_sales_employee(employee):
        raise HTTPException(status_code=422, detail="Nhân viên phụ trách phải là nhân viên Sale đang hoạt động.")
    return employee.id


def _require_bank_account_for_payment(db: Session, method: str, bank_account_id: int | None, amount: float):
    if amount <= 0 or method != "bank_transfer":
        return
    if not bank_account_id:
        raise HTTPException(status_code=422, detail="Vui lòng chọn tài khoản nhận tiền khi thanh toán chuyển khoản.")
    account = db.query(BankAccount).filter(BankAccount.id == bank_account_id, BankAccount.status == "active").first()
    if not account:
        raise HTTPException(status_code=422, detail="Tài khoản nhận tiền không hợp lệ hoặc đã tạm ngừng.")


def _latest_same_category_expiry(db: Session, member_id: int, plan: ServicePackage) -> date | None:
    return db.query(func.max(Membership.expires_at)).join(ServicePackage).filter(
        Membership.customer_id == member_id,
        ServicePackage.is_pt == False,
        ServicePackage.category == plan.category,
        Membership.status.in_(("active", "pending", "frozen", "suspended")),
        Membership.expires_at != None,
    ).scalar()


def _scheduled_membership_window(
    db: Session,
    member_id: int,
    plan: ServicePackage,
    starts_at: date,
    activate_now: bool,
    activation_date: date | None,
) -> tuple[date, date | None, str, bool]:
    effective_start = starts_at if activate_now else (activation_date or starts_at)
    latest_same_category_expiry = _latest_same_category_expiry(db, member_id, plan)
    if latest_same_category_expiry and latest_same_category_expiry >= effective_start:
        effective_start = latest_same_category_expiry + timedelta(days=1)
        return effective_start, effective_start, "pending", True
    if activate_now:
        return effective_start, effective_start, "active", False
    return effective_start, activation_date, "pending", False


def _sync_member_status_from_memberships(db: Session, member: Customer) -> None:
    if member.status == "cancelled":
        return
    today = vietnam_today()
    active_exists = db.query(Membership.id).join(ServicePackage).filter(
        Membership.customer_id == member.id,
        ServicePackage.is_pt == False,
        Membership.status == "active",
        or_(Membership.expires_at == None, Membership.expires_at >= today),
    ).first()
    if active_exists:
        member.status = "active"
        return
    usable_exists = db.query(Membership.id).join(ServicePackage).filter(
        Membership.customer_id == member.id,
        ServicePackage.is_pt == False,
        Membership.status.in_(("pending", "frozen", "suspended")),
    ).first()
    member.status = "lead" if usable_exists else "inactive"


def _sync_customer_statuses(db: Session, *customer_ids: int | None) -> None:
    for customer_id in dict.fromkeys(customer_id for customer_id in customer_ids if customer_id):
        customer = db.get(Customer, customer_id)
        if customer:
            _sync_member_status_from_memberships(db, customer)


def normalize_cancelled_members(db: Session) -> int:
    changed = 0
    rows = (
        db.query(Customer)
        .options(joinedload(Customer.memberships).joinedload(Membership.package))
        .filter(
            Customer.status == "inactive",
        )
        .all()
    )
    for customer in rows:
        regular = [membership for membership in customer.memberships if membership.package and not membership.package.is_pt]
        latest = sorted(regular, key=_membership_sort_key)[0] if regular else None
        if latest and latest.status == "cancelled":
            customer.status = "cancelled"
            changed += 1
    return changed


def _membership_sort_key(row: Membership):
    today = vietnam_today()
    if row.status == "active" and (not row.expires_at or row.expires_at >= today) and (not row.starts_at or row.starts_at <= today):
        priority = 0
    elif row.status in ("frozen", "suspended"):
        priority = 1
    elif row.status == "pending":
        priority = 2
    else:
        priority = 3
    return (priority, -(row.starts_at or date.min).toordinal(), -row.id)


async def save_receipt(upload: UploadFile | None) -> str | None:
    if not upload or not upload.filename:
        return None
    suffix = Path(upload.filename).suffix.lower()
    if suffix not in ALLOWED_IMAGE_SUFFIXES:
        raise HTTPException(status_code=400, detail="Phiếu thu phải là ảnh JPG, PNG hoặc WebP.")
    content = await upload.read(5 * 1024 * 1024 + 1)
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="Ảnh phiếu thu không được vượt quá 5 MB.")
    image_type = None
    if content.startswith(b"\xff\xd8\xff"):
        image_type = "jpeg"
    elif content.startswith(b"\x89PNG\r\n\x1a\n"):
        image_type = "png"
    elif len(content) >= 12 and content[:4] == b"RIFF" and content[8:12] == b"WEBP":
        image_type = "webp"
    expected_type = "jpeg" if suffix in {".jpg", ".jpeg"} else suffix.lstrip(".")
    if image_type != expected_type:
        raise HTTPException(status_code=400, detail="Nội dung phiếu thu không phải ảnh hợp lệ hoặc không khớp định dạng file.")
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
    today = vietnam_today()
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
    current_membership_priority = case(
        (
            and_(
                Membership.status == "active",
                or_(Membership.expires_at == None, Membership.expires_at >= today),
                or_(Membership.starts_at == None, Membership.starts_at <= today),
            ),
            0,
        ),
        (Membership.status.in_(("frozen", "suspended")), 1),
        (Membership.status == "pending", 2),
        else_=3,
    )
    current_regular_id = db.query(Membership.id).join(ServicePackage).filter(
        Membership.customer_id == Customer.id, ServicePackage.is_pt == False
    ).order_by(
        current_membership_priority.asc(),
        Membership.starts_at.desc(),
        Membership.id.desc(),
    ).limit(1).correlate(Customer).scalar_subquery()
    status_membership = aliased(Membership)
    def current_status_exists(*conditions):
        return db.query(status_membership.id).filter(status_membership.id == current_regular_id, *conditions).exists()
    cancelled_member = Customer.status == "cancelled"
    if view == "cancelled" or member_status == "cancelled":
        query = query.filter(cancelled_member)
    else:
        query = query.filter(Customer.status != "cancelled")
    if member_status == "active":
        query = query.filter(current_status_exists(status_membership.status == "active", or_(status_membership.expires_at == None, status_membership.expires_at >= today)))
    elif member_status == "expired":
        query = query.filter(current_status_exists(status_membership.expires_at < today))
    elif member_status == "expiring":
        query = query.filter(current_status_exists(status_membership.status == "active", status_membership.expires_at >= today, status_membership.expires_at <= today + timedelta(days=expiring_days)))
    elif member_status == "pending":
        query = query.filter(current_status_exists(status_membership.status == "pending"))
    elif member_status == "frozen":
        query = query.filter(current_status_exists(status_membership.status == "frozen"))
    elif member_status == "inactive":
        query = query.filter(Customer.status == "inactive")
    if payment_status == "overdue":
        query = query.filter(current_status_exists(
            status_membership.debt_amount > 0,
            status_membership.debt_due_date != None,
            status_membership.debt_due_date <= today + timedelta(days=overdue_days),
        ))
    elif payment_status == "debt":
        query = query.filter(current_status_exists(status_membership.debt_amount > 0))
    if view == "active":
        query = query.filter(current_status_exists(status_membership.status == "active", or_(status_membership.expires_at == None, status_membership.expires_at >= today)))
    elif view == "expiring":
        query = query.filter(current_status_exists(status_membership.status == "active", status_membership.expires_at >= today, status_membership.expires_at <= today + timedelta(days=14)))
    elif view == "debt":
        query = query.filter(current_status_exists(status_membership.debt_amount > 0))
    elif view == "no_pt":
        query = query.filter(~db.query(PtEnrollment.id).filter(PtEnrollment.customer_id == Customer.id, PtEnrollment.status == "active").exists())
    if package_id:
        query = query.filter(current_status_exists(status_membership.package_id == package_id))
    if trainer_id:
        query = query.filter(db.query(PtEnrollmentCoach.enrollment_id).join(PtEnrollment).filter(PtEnrollment.customer_id == Customer.id, PtEnrollmentCoach.coach_id == trainer_id).exists())
    total = query.count()
    latest_debt_amount = db.query(Membership.debt_amount).filter(
        Membership.id == current_regular_id
    ).correlate(Customer).scalar_subquery()
    latest_debt_due_date = db.query(Membership.debt_due_date).filter(
        Membership.id == current_regular_id
    ).correlate(Customer).scalar_subquery()
    debt_due_group = case(
        (and_(latest_debt_amount > 0, latest_debt_due_date != None), 0),
        (latest_debt_amount > 0, 1),
        else_=2,
    )
    if sort == "name":
        orderings = [Person.display_name.asc(), Customer.id.desc()]
    elif sort == "status":
        orderings = [Customer.status.asc(), Customer.id.desc()]
    elif sort == "debt_due_asc":
        orderings = [
            debt_due_group.asc(),
            latest_debt_due_date.asc(),
            _customer_code_sort_expression(db).desc(),
            Customer.id.desc(),
        ]
    elif sort == "debt_due_desc":
        orderings = [
            debt_due_group.asc(),
            latest_debt_due_date.desc(),
            _customer_code_sort_expression(db).desc(),
            Customer.id.desc(),
        ]
    else:
        orderings = [_customer_code_sort_expression(db).desc(), Customer.id.desc()]
    rows = query.order_by(*orderings).offset((page - 1) * page_size).limit(page_size).all()
    ids = [row.id for row in rows]
    last_checkins = {}
    trainers = {}
    active_training = {}
    if ids:
        checkins = db.query(AttendanceSession).filter(AttendanceSession.customer_id.in_(ids)).order_by(AttendanceSession.checked_in_at.desc()).all()
        for checkin in checkins:
            last_checkins.setdefault(checkin.customer_id, _attendance_iso(checkin.checked_in_at, checkin.source))
        training_rows = db.query(PtEnrollment).options(joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person)).filter(PtEnrollment.customer_id.in_(ids), PtEnrollment.status == "active").order_by(PtEnrollment.id.desc()).all()
        for training in training_rows:
            active_training.setdefault(training.customer_id, training)
            assigned = trainers.setdefault(training.customer_id, [])
            for assignment in training.coach_assignments:
                if not assignment.coach:
                    continue
                if not any(item["id"] == assignment.coach.id for item in assigned):
                    assigned.append({"id": assignment.coach.id, "name": assignment.coach.person.display_name})
    items = []
    for member in rows:
        regular = [m for m in member.memberships if not m.package.is_pt]
        current = sorted(regular, key=_membership_sort_key)[0] if regular else None
        items.append({
            "id": member.id,
            "code": member.customer_code,
            "mbsCode": member.mbs_card_code,
            "personUuid": member.person_uuid,
            "avatarImageData": member.avatar_image_data,
            **person_data(member.person),
            "source": member.source,
            "status": member.status,
            "salesEmployee": employee_data(member.sales_employee),
            "trainer": (trainers.get(member.id) or [None])[0],
            "trainers": trainers.get(member.id, []),
            "ptGroup": active_training.get(member.id).group_type if active_training.get(member.id) else None,
            "activeTraining": pt_data(active_training[member.id]) if member.id in active_training else None,
            "membership": membership_data(current) if current else None,
            "lastCheckin": last_checkins.get(member.id),
        })
    return {"items": items, "pagination": pagination(page, page_size, total)}


def member_options(db: Session):
    employees = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active").order_by(Employee.id).all()
    accounts = db.query(BankAccount).filter(BankAccount.status == "active").order_by(BankAccount.bank_name).all()
    pt_titles = {
        row.name for row in db.query(EmployeeJobTitle)
        .filter(EmployeeJobTitle.is_active == True, EmployeeJobTitle.is_pt_role == True)
        .all()
    } or {"Coach"}
    return {
        "employees": [{"id": row.id, "code": row.employee_code, "name": row.person.display_name, "title": row.job_title, "isPtRole": row.job_title in pt_titles} for row in employees],
        "salesEmployees": [{"id": row.id, "code": row.employee_code, "name": row.person.display_name, "title": row.job_title} for row in employees if _is_sales_employee(row)],
        "ptRoleTitles": sorted(pt_titles, key=str.casefold),
        "plans": list_plans(db),
        "bankAccounts": [{"id": row.id, "label": f"{row.bank_name} · {row.account_number}", "visibility": row.visibility} for row in accounts],
    }


def get_member(db: Session, member_id: int, include_audit: bool = False):
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
    pt_session_logs = db.query(PtSessionLog).options(
        joinedload(PtSessionLog.enrollment).joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person),
        joinedload(PtSessionLog.attendance_session),
        joinedload(PtSessionLog.created_by),
    ).join(PtSessionLog.enrollment).filter(PtEnrollment.customer_id == member_id).order_by(PtSessionLog.created_at.desc(), PtSessionLog.id.desc()).limit(100).all()
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
        "personUuid": member.person_uuid,
        "avatarImageData": member.avatar_image_data,
        **person_data(member.person), "source": member.source, "status": member.status,
        "notes": member.notes,
        "salesEmployeeId": member.sales_employee_id,
        "salesEmployee": member.sales_employee.person.display_name if member.sales_employee else None,
        "memberships": [membership_data(row, include_payments=True, include_history=include_audit) for row in sorted([row for row in memberships if not row.package.is_pt], key=_membership_sort_key)],
        "membershipEvents": [membership_event_data(row) for row in membership_events] if include_audit else [],
        "training": [pt_data(row) for row in pt_rows],
        "ptSessionLogs": [{
            "id": row.id,
            "enrollmentId": row.enrollment_id,
            "attendanceSessionId": row.attendance_session_id,
            "action": row.action,
            "deltaSessions": row.delta_sessions,
            "remainingBefore": row.remaining_before,
            "remainingAfter": row.remaining_after,
            "note": row.note,
            "createdAt": utc_iso(row.created_at),
            "createdBy": row.created_by.display_name if row.created_by else "Hệ thống",
            "checkedInAt": _attendance_iso(row.attendance_session.checked_in_at, row.attendance_session.source) if row.attendance_session else None,
            "checkedOutAt": _attendance_iso(row.attendance_session.checked_out_at, row.attendance_session.source) if row.attendance_session else None,
            "ptType": row.enrollment.group_type if row.enrollment else None,
            "coaches": [employee_data(assignment.coach) for assignment in row.enrollment.coach_assignments] if row.enrollment else [],
        } for row in pt_session_logs],
        "checkins": [{"id": row.id, "checkedInAt": _attendance_iso(row.checked_in_at, row.source), "checkedOutAt": _attendance_iso(row.checked_out_at, row.source), "result": row.result, "status": row.status, "source": row.source} for row in checkins],
        "payments": [payment_data(row) for row in payments],
        "auditLogs": member_audit_logs(db, member_id) if include_audit else [],
    }


def create_member(db: Session, payload: dict, actor: User | None = None):
    name = str(payload.get("name", "")).strip()
    phone = str(payload.get("phone", "")).strip()
    if not name or not phone:
        raise HTTPException(status_code=422, detail="Họ tên và số điện thoại là bắt buộc.")
    if db.query(Person).filter(Person.phone == phone).first():
        raise HTTPException(status_code=409, detail="Số điện thoại này đã tồn tại.")
    dah_event_id = _int(payload.get("dahEventId"))
    dah_event = db.get(DahWebhookEvent, dah_event_id) if dah_event_id else None
    if dah_event_id:
        event_identity_key = dah_service._event_identity_key(dah_event) if dah_event else None
        if not dah_event or dah_event.operator != "VerifyPush" or not event_identity_key:
            raise HTTPException(status_code=422, detail="Định danh DAH không hợp lệ.")
        if dah_service._identity_query(db, dah_event.person_uuid, dah_event.person_id):
            raise HTTPException(status_code=409, detail="Định danh DAH này đã được gán cho hội viên khác.")
    person_uuid = _text(payload.get("personUuid"), 80) or (dah_service._event_identity_key(dah_event) if dah_event else None)
    if person_uuid and db.query(Customer).filter(Customer.person_uuid == person_uuid).first():
        raise HTTPException(status_code=409, detail="Định danh DAH này đã được gán cho hội viên khác.")
    person = Person(display_name=name, phone=phone, email=payload.get("email") or None, gender=payload.get("gender") or None, date_of_birth=_parse_date(payload.get("dateOfBirth")), status="active", biometric_consent_status="not_requested")
    db.add(person); db.flush()
    member = Customer(person_id=person.id, customer_code=f"TMP-{secrets.token_hex(6)}", mbs_card_code=payload.get("mbsCode") or None, person_uuid=person_uuid, avatar_image_data=dah_event.image_data if dah_event else None, sales_employee_id=_sales_employee_id(db, payload.get("salesEmployeeId")), source=_text(payload.get("source"), 80), status="lead", notes=payload.get("notes") or None)
    db.add(member); db.flush()
    member.customer_code = _next_customer_code(db)
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
        record_audit(
            db, actor, "create", "pt_enrollment", enrollment.id,
            f"Đăng ký PT {kind} · {sessions} buổi cùng lúc tạo hội viên",
            customer_id=member.id,
            details={"coachIds": coach_ids, "schedule": json.loads(schedule_json) if schedule_json else []},
        )
    membership_payload = payload.get("membership")
    if isinstance(membership_payload, dict) and _int(membership_payload.get("planId")):
        plan = db.query(ServicePackage).filter(
            ServicePackage.id == _int(membership_payload.get("planId")),
            ServicePackage.is_pt == False,
            ServicePackage.is_active == True,
        ).first()
        if not plan:
            raise HTTPException(status_code=422, detail="Gói tập không hợp lệ hoặc đã tạm ngừng.")
        starts_at = _parse_date(membership_payload.get("startsAt")) or vietnam_today()
        activate_now = _bool(membership_payload.get("activateNow"), True)
        activation_date = _parse_date(membership_payload.get("activationDate"))
        effective_start, scheduled_activation, initial_status, shifted_by_category = _scheduled_membership_window(
            db,
            member.id,
            plan,
            starts_at,
            activate_now,
            activation_date,
        )
        expires_at = None if shifted_by_category else _parse_date(membership_payload.get("expiresAt"))
        if expires_at and expires_at < effective_start and plan.duration_days:
            expires_at = effective_start + timedelta(days=plan.duration_days)
        expires_at = expires_at or (
            effective_start + timedelta(days=plan.duration_days) if plan.duration_days else None
        )
        if expires_at and expires_at < effective_start:
            raise HTTPException(status_code=422, detail="Ngày hết hạn gói phải sau ngày bắt đầu.")
        final_price = _money(membership_payload.get("finalPrice"), plan.price or 0)
        day_pass_id = _int(payload.get("sourceDayPassId"))
        conversion_policy = payload.get("sourceDayPassConversionPolicy") or "refunded"
        conversion_credit = _day_pass_conversion_context(db, day_pass_id, conversion_policy)
        cash_paid = _money(membership_payload.get("paidAmount"))
        paid = cash_paid + conversion_credit
        if paid > final_price:
            raise HTTPException(status_code=422, detail="Số tiền đã thanh toán không thể lớn hơn tổng tiền của gói.")
        debt = max(final_price - paid, 0)
        debt_due_date = _parse_date(membership_payload.get("debtDueDate")) if debt else None
        if debt and not debt_due_date:
            raise HTTPException(status_code=422, detail="Vui lòng chọn hạn thanh toán cho phần công nợ.")
        method = membership_payload.get("paymentMethod") or "cash"
        bank_account_id = _int(membership_payload.get("bankAccountId"))
        _require_bank_account_for_payment(db, method, bank_account_id, cash_paid)
        membership = Membership(
            customer_id=member.id,
            package_id=plan.id,
            code=f"TMP-{secrets.token_hex(6)}",
            registered_at=vietnam_today(),
            starts_at=effective_start,
            expires_at=expires_at,
            activated_at=scheduled_activation,
            remaining_sessions=None,
            final_price=final_price,
            deposit_amount=paid,
            paid_amount=paid,
            debt_amount=debt,
            debt_due_date=debt_due_date,
            sale_online_employee_id=_int(membership_payload.get("saleOnlineEmployeeId")),
            direct_sales_employee_id=_int(membership_payload.get("directSaleEmployeeId")),
            status=initial_status,
        )
        db.add(membership); db.flush(); membership.code = f"MS-{membership.id:06d}"
        if cash_paid:
            payment = Payment(
                customer_id=member.id,
                membership_id=membership.id,
                bank_account_id=bank_account_id,
                payment_no=f"PAY-{membership.id:06d}-001",
                paid_at=utc_now(),
                amount=cash_paid,
                method=method,
                channel="counter",
                shift_date=vietnam_today(),
                note="Thanh toán đăng ký gói cùng lúc tạo hội viên",
            )
            db.add(payment); db.flush()
            record_audit(db, actor, "payment", "payment", payment.id, f"Ghi nhận thanh toán {cash_paid:,.0f} ₫", customer_id=member.id, details={"membershipId": membership.id, "source": "member_create"})
        db.flush()
        _sync_member_status_from_memberships(db, member)
        record_audit(db, actor, "create", "membership", membership.id, f"Đăng ký gói {plan.name} cùng lúc tạo hội viên", customer_id=member.id, details={"startsAt": starts_at, "expiresAt": expires_at, "finalPrice": final_price, "paidAmount": paid, "cashPaidAmount": cash_paid, "dayPassCredit": conversion_credit})
        mark_converted_day_pass(
            db,
            day_pass_id,
            member.id,
            membership.id,
            actor,
            conversion_policy,
        )
    db.commit()
    if dah_event_id:
        dah_service.assign_identity_to_customer(db, member.id, dah_event_id)
    return get_member(db, member.id)


def update_member(db: Session, member_id: int, payload: dict, actor: User | None = None):
    member = db.query(Customer).options(joinedload(Customer.person)).filter(Customer.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội viên.")
    if "name" in payload and not str(payload["name"]).strip():
        raise HTTPException(status_code=422, detail="Họ tên không được để trống.")
    old_values = {
        "name": member.person.display_name,
        "phone": member.person.phone,
        "email": member.person.email,
        "gender": member.person.gender,
        "dateOfBirth": member.person.date_of_birth,
        "mbsCode": member.mbs_card_code,
        "personUuid": member.person_uuid,
        "source": member.source,
        "notes": member.notes,
        "salesEmployeeId": member.sales_employee_id,
    }
    member.person.display_name = str(payload.get("name", member.person.display_name)).strip()
    for source, target in [("phone", "phone"), ("email", "email"), ("gender", "gender")]:
        if source in payload:
            setattr(member.person, target, payload[source] or None)
    if "dateOfBirth" in payload:
        member.person.date_of_birth = _parse_date(payload.get("dateOfBirth"))
    if "mbsCode" in payload: member.mbs_card_code = payload.get("mbsCode") or None
    if "personUuid" in payload:
        person_uuid = _text(payload.get("personUuid"), 80)
        if person_uuid:
            duplicate = db.query(Customer).filter(Customer.person_uuid == person_uuid, Customer.id != member.id).first()
            if duplicate:
                raise HTTPException(status_code=409, detail="PersonUUID này đã được gán cho hội viên khác.")
        member.person_uuid = person_uuid
    if "source" in payload: member.source = payload.get("source") or None
    if "notes" in payload: member.notes = payload.get("notes") or None
    if "salesEmployeeId" in payload: member.sales_employee_id = _sales_employee_id(db, payload.get("salesEmployeeId"))
    candidate_fields = [field for field in payload.keys() if field in MEMBER_AUDIT_FIELD_LABELS]
    new_values = {
        "name": member.person.display_name,
        "phone": member.person.phone,
        "email": member.person.email,
        "gender": member.person.gender,
        "dateOfBirth": member.person.date_of_birth,
        "mbsCode": member.mbs_card_code,
        "personUuid": member.person_uuid,
        "source": member.source,
        "notes": member.notes,
        "salesEmployeeId": member.sales_employee_id,
    }
    changes = []
    for field in candidate_fields:
        old_value = old_values.get(field)
        new_value = new_values.get(field)
        if old_value == new_value:
            continue
        if field == "salesEmployeeId":
            old_value = _employee_display_name(db, old_value)
            new_value = _employee_display_name(db, new_value)
        changes.append({
            "field": field,
            "label": MEMBER_AUDIT_FIELD_LABELS[field],
            "old": _audit_display_value(old_value),
            "new": _audit_display_value(new_value),
        })
    changed_fields = [change["field"] for change in changes]
    changed_labels = [change["label"] for change in changes]
    summary_suffix = f": {', '.join(changed_labels)}" if changed_labels else ""
    record_audit(
        db,
        actor,
        "update",
        "member",
        member.id,
        f"Cập nhật hồ sơ {member.person.display_name}{summary_suffix}",
        customer_id=member.id,
        details={
            "fields": changed_fields,
            "fieldLabels": changed_labels,
            "changes": changes,
            "previousName": old_values["name"],
        },
    )
    db.commit()
    return get_member(db, member_id, include_audit=bool(actor and actor.role == "admin"))


def reactivate_cancelled_member(db: Session, member_id: int, actor: User | None = None):
    member = db.query(Customer).options(joinedload(Customer.person)).filter(Customer.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Không tìm thấy hội viên.")
    if member.status != "cancelled":
        raise HTTPException(status_code=409, detail="Chỉ hội viên đã hủy mới cần kích hoạt lại.")
    member.status = "lead"
    if member.person:
        member.person.status = "active"
    record_audit(
        db,
        actor,
        "reactivate",
        "member",
        member.id,
        f"Kích hoạt lại hồ sơ {member.person.display_name}",
        customer_id=member.id,
        details={"previousStatus": "cancelled", "newStatus": "lead", "membershipsRestored": False},
    )
    db.commit()
    return get_member(db, member_id)


def list_plans(db: Session, include_inactive=False):
    query = db.query(ServicePackage).filter(ServicePackage.is_pt == False)
    if not include_inactive: query = query.filter(ServicePackage.is_active == True)
    rows = query.order_by(ServicePackage.category, ServicePackage.price).all()
    counts = dict(db.query(Membership.package_id, func.count(Membership.id)).filter(Membership.package_id.in_([row.id for row in rows]), Membership.status == "active").group_by(Membership.package_id).all()) if rows else {}
    registration_counts = dict(db.query(Membership.package_id, func.count(Membership.id)).filter(Membership.package_id.in_([row.id for row in rows])).group_by(Membership.package_id).all()) if rows else {}
    return [
        {
            **package_data(row),
            "memberCount": counts.get(row.id, 0),
            "registrationCount": registration_counts.get(row.id, 0),
            "canDelete": registration_counts.get(row.id, 0) == 0,
        }
        for row in rows
    ]


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


def delete_plan(db: Session, plan_id: int, actor: User | None = None):
    plan = db.query(ServicePackage).filter(ServicePackage.id == plan_id, ServicePackage.is_pt == False).first()
    if not plan:
        raise HTTPException(status_code=404, detail="Không tìm thấy gói tập.")
    registrations = db.query(Membership).filter(Membership.package_id == plan.id).count()
    if registrations:
        raise HTTPException(status_code=409, detail="Gói này đã có hội viên đăng ký nên không thể xóa. Hãy chuyển sang tạm ngừng sử dụng.")
    record_audit(db, actor, "delete", "plan", plan.id, f"Xóa gói tập {plan.name}", details={"code": plan.code, "price": plan.price, "durationDays": plan.duration_days})
    db.delete(plan)
    db.commit()
    return {"deleted": True, "id": plan_id}


def list_memberships(db: Session, q: str, membership_status: str, page: int, page_size: int):
    today = vietnam_today()
    query = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package), joinedload(Membership.sale_online_employee).joinedload(Employee.person), joinedload(Membership.direct_sales_employee).joinedload(Employee.person)).join(Membership.package).filter(ServicePackage.is_pt == False)
    if q:
        query = query.join(Membership.customer).join(Customer.person).filter(or_(Person.display_name.contains(q), Membership.code.contains(q), ServicePackage.name.contains(q)))
    if membership_status == "expiring":
        query = query.filter(Membership.status == "active", Membership.expires_at >= today, Membership.expires_at <= today + timedelta(days=14))
    elif membership_status == "expired":
        query = query.filter(Membership.expires_at < today)
    elif membership_status and membership_status != "all":
        query = query.filter(Membership.status == membership_status)
    total = query.count(); rows = query.order_by(Membership.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [membership_data(row) for row in rows]
    return {"items": items, "pagination": pagination(page, page_size, total)}


async def create_membership(db: Session, form: dict, receipts: list[UploadFile], actor: User | None = None):
    member = db.get(Customer, _int(form.get("memberId")))
    plan = db.query(ServicePackage).filter(ServicePackage.id == _int(form.get("planId")), ServicePackage.is_pt == False, ServicePackage.is_active == True).first()
    if not member or not plan: raise HTTPException(status_code=422, detail="Hội viên hoặc gói tập không hợp lệ.")
    if member.status == "cancelled":
        raise HTTPException(status_code=409, detail="Hội viên đã hủy cần được kích hoạt lại trước khi đăng ký gói mới.")
    starts_at = _parse_date(form.get("startsAt")) or vietnam_today()
    activate_now = _bool(form.get("activateNow"), True)
    activation_date = _parse_date(form.get("activationDate"))
    effective_start, scheduled_activation, initial_status, shifted_by_category = _scheduled_membership_window(
        db,
        member.id,
        plan,
        starts_at,
        activate_now,
        activation_date,
    )
    final_price = _money(form.get("finalPrice"), plan.price or 0)
    day_pass_id = _int(form.get("dayPassId") or form.get("sourceDayPassId"))
    conversion_policy = form.get("dayPassConversionPolicy") or form.get("sourceDayPassConversionPolicy") or "refunded"
    conversion_credit = _day_pass_conversion_context(db, day_pass_id, conversion_policy)
    cash_paid = _money(form.get("paidAmount"))
    paid = cash_paid + conversion_credit
    if paid > final_price:
        raise HTTPException(status_code=422, detail="Số tiền đã thanh toán không thể lớn hơn tổng tiền của gói.")
    debt = max(final_price - paid, 0)
    debt_due_date = _parse_date(form.get("debtDueDate")) if debt else None
    if debt and not debt_due_date:
        raise HTTPException(status_code=422, detail="Vui lòng chọn hạn thanh toán cho phần công nợ.")
    method = form.get("paymentMethod") or "cash"
    bank_account_id = _int(form.get("bankAccountId"))
    _require_bank_account_for_payment(db, method, bank_account_id, cash_paid)
    expires_at = None if shifted_by_category else _parse_date(form.get("expiresAt"))
    if expires_at and expires_at < effective_start and plan.duration_days:
        expires_at = effective_start + timedelta(days=plan.duration_days)
    expires_at = expires_at or (effective_start + timedelta(days=plan.duration_days) if plan.duration_days else None)
    if expires_at and expires_at < effective_start:
        raise HTTPException(status_code=422, detail="Ngày hết hạn gói phải sau ngày bắt đầu.")
    row = Membership(customer_id=member.id, package_id=plan.id, code=f"TMP-{secrets.token_hex(6)}", registered_at=vietnam_today(), starts_at=effective_start, expires_at=expires_at, activated_at=scheduled_activation, remaining_sessions=None, final_price=final_price, deposit_amount=paid, paid_amount=paid, debt_amount=debt, debt_due_date=debt_due_date, sale_online_employee_id=_int(form.get("saleOnlineEmployeeId")), direct_sales_employee_id=_int(form.get("directSaleEmployeeId")), status=initial_status)
    db.add(row); db.flush(); row.code = f"MS-{row.id:06d}"
    if cash_paid:
        payment = Payment(customer_id=member.id, membership_id=row.id, bank_account_id=bank_account_id, payment_no=f"PAY-{row.id:06d}-001", paid_at=utc_now(), amount=cash_paid, method=method, channel="counter", shift_date=vietnam_today(), note="Thanh toán đăng ký gói")
        db.add(payment)
        await attach_receipts(payment, receipts, actor)
        db.flush()
    record_audit(db, actor, "create", "membership", row.id, f"Đăng ký gói {plan.name}", customer_id=member.id, details={"startsAt": row.starts_at, "expiresAt": row.expires_at, "finalPrice": final_price, "paidAmount": paid, "cashPaidAmount": cash_paid, "dayPassCredit": conversion_credit})
    if cash_paid:
        record_audit(db, actor, "payment", "payment", payment.id, f"Ghi nhận thanh toán {cash_paid:,.0f} ₫", customer_id=member.id, details={"membershipId": row.id, "receiptCount": len(receipts)})
    mark_converted_day_pass(
        db,
        day_pass_id,
        member.id,
        row.id,
        actor,
        conversion_policy,
    )
    db.flush()
    _sync_member_status_from_memberships(db, member)
    db.commit()
    row = db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person), joinedload(Membership.package), joinedload(Membership.sale_online_employee).joinedload(Employee.person), joinedload(Membership.direct_sales_employee).joinedload(Employee.person)).get(row.id)
    return membership_data(row)


async def update_membership(db: Session, membership_id: int, form: dict, receipts: list[UploadFile], actor: User | None = None):
    row = db.query(Membership).options(joinedload(Membership.package)).filter(Membership.id == membership_id).first()
    if not row or row.package.is_pt: raise HTTPException(status_code=404, detail="Không tìm thấy đăng ký gói.")
    old_values = {
        "startsAt": row.starts_at,
        "expiresAt": row.expires_at,
        "finalPrice": row.final_price,
        "paidAmount": row.paid_amount,
        "debtAmount": row.debt_amount,
        "debtDueDate": row.debt_due_date,
        "status": row.status,
        "activationDate": row.activated_at,
    }
    row.starts_at = _parse_date(form.get("startsAt")) or row.starts_at
    row.expires_at = _parse_date(form.get("expiresAt"))
    row.final_price = _money(form.get("finalPrice"), row.final_price)
    previous_paid = row.paid_amount or 0
    next_paid = _money(form.get("paidAmount"), previous_paid)
    if next_paid < previous_paid:
        raise HTTPException(status_code=422, detail="Không thể giảm số tiền đã thu. Hãy tạo nghiệp vụ hoàn tiền riêng.")
    if next_paid > row.final_price:
        raise HTTPException(status_code=422, detail="Số tiền đã thanh toán không thể lớn hơn tổng tiền của gói.")
    method = form.get("paymentMethod") or "cash"
    bank_account_id = _int(form.get("bankAccountId"))
    _require_bank_account_for_payment(db, method, bank_account_id, next_paid - previous_paid)
    row.paid_amount = next_paid
    row.deposit_amount = row.paid_amount
    row.debt_amount = max(row.final_price - row.paid_amount, 0)
    row.debt_due_date = _parse_date(form.get("debtDueDate")) if row.debt_amount else None
    if row.debt_amount and not row.debt_due_date:
        raise HTTPException(status_code=422, detail="Vui lòng chọn hạn thanh toán cho phần công nợ.")
    if form.get("status") in ("active", "pending", "frozen", "cancelled", "suspended", "expired"): row.status = form["status"]
    if "activationDate" in form:
        row.activated_at = _parse_date(form.get("activationDate"))
    delta = next_paid - previous_paid
    payment = None
    if delta > 0:
        sequence = db.query(Payment).filter(Payment.membership_id == row.id).count() + 1
        paid_at = _parse_paid_at(form.get("paidAt"))
        payment = Payment(customer_id=row.customer_id, membership_id=row.id, payment_no=f"PAY-{row.id:06d}-{sequence:03d}", paid_at=paid_at, shift_date=utc_vietnam_date(paid_at) or vietnam_today(), note="Thanh toán gói", amount=delta, method=method, bank_account_id=bank_account_id)
        db.add(payment)
        await attach_receipts(payment, receipts, actor)
        db.flush()
        record_audit(db, actor, "payment", "payment", payment.id, f"Ghi nhận thanh toán {delta:,.0f} ₫", customer_id=row.customer_id, details={"membershipId": row.id, "receiptCount": len(receipts), "paidAt": utc_iso(paid_at)})
    new_values = {
        "startsAt": row.starts_at,
        "expiresAt": row.expires_at,
        "finalPrice": row.final_price,
        "paidAmount": row.paid_amount,
        "debtAmount": row.debt_amount,
        "debtDueDate": row.debt_due_date,
        "status": row.status,
        "activationDate": row.activated_at,
    }
    fields = []
    changes = []
    for field in form.keys():
        if field not in MEMBERSHIP_AUDIT_FIELD_LABELS or field in fields:
            continue
        if old_values.get(field) == new_values.get(field):
            continue
        fields.append(field)
        changes.append({
            "field": field,
            "label": MEMBERSHIP_AUDIT_FIELD_LABELS[field],
            "old": _audit_display_value(old_values.get(field)),
            "new": _audit_display_value(new_values.get(field)),
        })
    if old_values.get("debtAmount") != new_values.get("debtAmount"):
        fields.append("debtAmount")
        changes.append({
            "field": "debtAmount",
            "label": "Công nợ",
            "old": _audit_display_value(old_values.get("debtAmount")),
            "new": _audit_display_value(new_values.get("debtAmount")),
        })
    label_suffix = f": {', '.join(change['label'] for change in changes)}" if changes else ""
    record_audit(
        db,
        actor,
        "update",
        "membership",
        row.id,
        f"Cập nhật gói {row.package.name}{label_suffix}",
        customer_id=row.customer_id,
        details={
            "fields": fields,
            "fieldLabels": [change["label"] for change in changes],
            "changes": changes,
            "expiresAt": row.expires_at,
            "paymentMethod": method,
            "bankAccountId": bank_account_id,
            "receiptCount": len(receipts),
        },
    )
    _sync_customer_statuses(db, row.customer_id)
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


def _membership_for_freeze(db: Session, membership_id: int):
    row = db.query(Membership).options(
        joinedload(Membership.package),
        joinedload(Membership.customer).joinedload(Customer.person),
    ).filter(Membership.id == membership_id).first()
    if not row or row.package.is_pt:
        raise HTTPException(404, "Không tìm thấy đăng ký gói.")
    if row.status == "cancelled":
        raise HTTPException(422, "Không thể bảo lưu gói đã hủy.")
    if not row.expires_at:
        raise HTTPException(422, "Gói không có ngày hết hạn nên không thể cộng bù tự động.")
    return row


def _freeze_payload(payload: dict):
    starts_at = _parse_date(payload.get("startsAt"))
    ends_at = _parse_date(payload.get("endsAt"))
    reason = str(payload.get("reason", "")).strip()
    if not starts_at or not ends_at or ends_at <= starts_at:
        raise HTTPException(422, "Ngày hết bảo lưu phải sau ngày bắt đầu bảo lưu.")
    if not reason:
        raise HTTPException(422, "Vui lòng nhập lý do bảo lưu.")
    return starts_at, ends_at, reason


def _ensure_freeze_not_overlapping(
    db: Session,
    membership_id: int,
    starts_at: date,
    ends_at: date,
    ignore_freeze_id: int | None = None,
):
    query = db.query(MembershipFreeze).filter(
        MembershipFreeze.membership_id == membership_id,
        MembershipFreeze.starts_at < ends_at,
        MembershipFreeze.ends_at > starts_at,
    )
    if ignore_freeze_id is not None:
        query = query.filter(MembershipFreeze.id != ignore_freeze_id)
    if query.first():
        raise HTTPException(409, "Thời gian này trùng với một lần bảo lưu đã có.")


def _revert_completed_freeze_days(membership: Membership, freeze: MembershipFreeze):
    days = freeze.compensated_days or 0
    if days and membership.expires_at:
        membership.expires_at = membership.expires_at - timedelta(days=days)
    freeze.completed_at = None
    freeze.compensated_days = 0


def _apply_freeze_status(membership: Membership, starts_at: date, ends_at: date):
    if freeze_affects_day(membership, starts_at, ends_at, vietnam_today()):
        membership.status = "frozen"
        if membership.customer:
            membership.customer.status = "lead"


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
    row = _membership_for_freeze(db, membership_id)
    starts_at, ends_at, reason = _freeze_payload(payload)
    _ensure_freeze_not_overlapping(db, row.id, starts_at, ends_at)
    planned_days = (ends_at - starts_at).days
    previous_expiry = row.expires_at
    _apply_freeze_status(row, starts_at, ends_at)
    freeze = MembershipFreeze(
        membership_id=row.id,
        starts_at=starts_at,
        ends_at=ends_at,
        compensated_days=0,
        reason=reason,
        created_by_user_id=actor.id if actor else None,
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
        created_by_user_id=actor.id if actor else None,
        details_json=json.dumps({"startsAt": str(starts_at), "endsAt": str(ends_at), "plannedDays": planned_days, "effectiveDays": freeze_compensation_days(row, starts_at, ends_at), "compensatedDays": 0, "previousExpiry": str(previous_expiry), "newExpiry": str(row.expires_at)}, ensure_ascii=False),
    )
    db.add_all([freeze, event])
    db.flush()
    if ends_at < vietnam_today():
        _complete_freeze(db, row, freeze, ends_at, actor, reason="Hoàn tất bảo lưu nhập bù")
    record_audit(db, actor, "freeze", "membership", row.id, f"Bảo lưu gói {row.package.name} trong {planned_days} ngày", customer_id=row.customer_id, details={"startsAt": starts_at, "endsAt": ends_at, "plannedDays": planned_days, "compensatedDays": 0, "previousExpiry": previous_expiry, "newExpiry": row.expires_at})
    db.commit()
    return get_member(db, row.customer_id)


def update_membership_freeze(db: Session, membership_id: int, freeze_id: int, payload: dict, actor: User):
    row = _membership_for_freeze(db, membership_id)
    freeze = db.query(MembershipFreeze).filter(
        MembershipFreeze.id == freeze_id,
        MembershipFreeze.membership_id == row.id,
    ).first()
    if not freeze:
        raise HTTPException(404, "Không tìm thấy lịch bảo lưu.")
    starts_at, ends_at, reason = _freeze_payload(payload)
    _ensure_freeze_not_overlapping(db, row.id, starts_at, ends_at, ignore_freeze_id=freeze.id)
    previous = {
        "startsAt": freeze.starts_at,
        "endsAt": freeze.ends_at,
        "completedAt": freeze.completed_at,
        "compensatedDays": freeze.compensated_days or 0,
        "reason": freeze.reason,
        "expiry": row.expires_at,
    }
    if freeze.completed_at:
        _revert_completed_freeze_days(row, freeze)
    freeze.starts_at = starts_at
    freeze.ends_at = ends_at
    freeze.reason = reason
    _apply_freeze_status(row, starts_at, ends_at)
    if ends_at < vietnam_today():
        _complete_freeze(db, row, freeze, ends_at, actor, reason="Hoàn tất bảo lưu sau khi chỉnh sửa")
    record_audit(
        db,
        actor,
        "update_freeze",
        "membership_freeze",
        freeze.id,
        f"Cập nhật lịch bảo lưu gói {row.package.name}",
        customer_id=row.customer_id,
        details={
            "previous": previous,
            "startsAt": starts_at,
            "endsAt": ends_at,
            "plannedDays": (ends_at - starts_at).days,
            "effectiveDays": freeze_compensation_days(row, starts_at, ends_at),
            "newExpiry": row.expires_at,
        },
    )
    refresh_membership_lifecycle(db)
    db.commit()
    return get_member(db, row.customer_id)


def delete_membership_freeze(db: Session, membership_id: int, freeze_id: int, actor: User):
    row = _membership_for_freeze(db, membership_id)
    freeze = db.query(MembershipFreeze).filter(
        MembershipFreeze.id == freeze_id,
        MembershipFreeze.membership_id == row.id,
    ).first()
    if not freeze:
        raise HTTPException(404, "Không tìm thấy lịch bảo lưu.")
    details = {
        "startsAt": freeze.starts_at,
        "endsAt": freeze.ends_at,
        "completedAt": freeze.completed_at,
        "compensatedDays": freeze.compensated_days or 0,
        "previousExpiry": row.expires_at,
        "reason": freeze.reason,
    }
    if freeze.completed_at:
        _revert_completed_freeze_days(row, freeze)
    details["newExpiry"] = row.expires_at
    record_audit(
        db,
        actor,
        "cancel_freeze",
        "membership_freeze",
        freeze.id,
        f"Hủy lịch bảo lưu gói {row.package.name}",
        customer_id=row.customer_id,
        details=details,
    )
    db.delete(freeze)
    refresh_membership_lifecycle(db)
    db.commit()
    return get_member(db, row.customer_id)


def membership_action(db: Session, membership_id: int, payload: dict, actor: User):
    row = db.query(Membership).options(joinedload(Membership.package), joinedload(Membership.customer).joinedload(Customer.person)).filter(Membership.id == membership_id).first()
    if not row or row.package.is_pt:
        raise HTTPException(404, "Không tìm thấy đăng ký gói.")
    action = payload.get("action")
    reason = str(payload.get("reason", "")).strip()
    if action not in ("activate", "suspend", "transfer", "change", "upgrade", "adjust_days", "cancel"):
        raise HTTPException(422, "Nghiệp vụ gói không hợp lệ.")
    if not reason:
        raise HTTPException(422, "Vui lòng nhập lý do để lưu lịch sử đối soát.")
    old_customer_id, old_package_id = row.customer_id, row.package_id
    old_customer_name, old_package_name = row.customer.person.display_name, row.package.name
    details = {}
    summary = ""
    if action == "activate":
        if row.status == "cancelled":
            raise HTTPException(422, "Gói đã hủy không thể kích hoạt lại. Hãy đăng ký dịch vụ mới.")
        activate_membership(db, row, _parse_date(payload.get("activatedAt")) or vietnam_today(), actor, reason)
        summary = f"Kích hoạt gói {old_package_name} của {old_customer_name}"
        db.commit()
        return {"membershipId": row.id, "customerId": row.customer_id, "action": action, "summary": summary}
    if action == "suspend":
        suspended_at = _parse_date(payload.get("suspendedAt")) or vietnam_today()
        if suspended_at < vietnam_today():
            raise HTTPException(422, "Ngày tạm dừng không được ở quá khứ.")
        row.status = "suspended"
        row.customer.status = "lead"
        summary = f"Tạm dừng gói {old_package_name} của {old_customer_name}"
        details = {"suspendedAt": str(suspended_at), "previousActivatedAt": str(row.activated_at) if row.activated_at else None}
        event = MembershipEvent(
            membership_id=row.id,
            action=action,
            from_customer_id=old_customer_id,
            to_customer_id=old_customer_id,
            from_package_id=old_package_id,
            to_package_id=old_package_id,
            effective_at=suspended_at,
            reason=reason,
            details_json=json.dumps(details, ensure_ascii=False),
            created_by_user_id=actor.id if actor else None,
        )
        db.add(event)
        record_audit(db, actor, action, "membership", row.id, summary, customer_id=old_customer_id, details={**details, "reason": reason})
        _sync_customer_statuses(db, old_customer_id)
        db.commit()
        return {"membershipId": row.id, "customerId": old_customer_id, "action": action, "summary": summary}
    if action == "adjust_days":
        if row.status == "cancelled":
            raise HTTPException(409, "Gói đã hủy không thể cộng/trừ ngày. Hãy đăng ký dịch vụ mới.")
        days = _int(payload.get("days"))
        if not days:
            raise HTTPException(422, "Vui lòng nhập số ngày cần cộng hoặc trừ.")
        if not row.expires_at:
            raise HTTPException(422, "Gói không có ngày hết hạn nên không thể cộng/trừ ngày.")
        new_expiry = row.expires_at + timedelta(days=days)
        if row.starts_at and new_expiry < row.starts_at:
            raise HTTPException(422, "Ngày hết hạn mới không được trước ngày bắt đầu gói.")
        previous_expiry = row.expires_at
        row.expires_at = new_expiry
        if row.status == "active" and new_expiry < vietnam_today():
            row.status = "expired"
        if row.status == "expired" and new_expiry >= vietnam_today():
            row.status = "active"
            row.customer.status = "active"
        summary = f"{'Cộng' if days > 0 else 'Trừ'} {abs(days)} ngày cho gói {old_package_name} của {old_customer_name}"
        details = {
            "days": days,
            "previousExpiry": str(previous_expiry),
            "newExpiry": str(new_expiry),
        }
        event = MembershipEvent(
            membership_id=row.id,
            action=action,
            from_customer_id=old_customer_id,
            to_customer_id=old_customer_id,
            from_package_id=old_package_id,
            to_package_id=old_package_id,
            effective_at=vietnam_today(),
            reason=reason,
            details_json=json.dumps(details, ensure_ascii=False),
            created_by_user_id=actor.id if actor else None,
        )
        db.add(event)
        record_audit(db, actor, action, "membership", row.id, summary, customer_id=old_customer_id, details={**details, "reason": reason})
        _sync_customer_statuses(db, old_customer_id)
        db.commit()
        return {"membershipId": row.id, "customerId": old_customer_id, "action": action, "summary": summary}
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
        row.customer.status = "cancelled"
        summary = f"Hủy dịch vụ {old_package_name} và chuyển {old_customer_name} vào danh sách đã hủy"
        details = {"paidAmount": row.paid_amount, "debtAmount": row.debt_amount, "refundCreated": False, "memberStatus": "cancelled"}
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
        created_by_user_id=actor.id if actor else None,
    )
    db.add(event)
    record_audit(db, actor, action, "membership", row.id, summary, customer_id=new_customer_id, details={**details, "reason": reason})
    if action == "transfer":
        record_audit(db, actor, action, "membership", row.id, summary, customer_id=old_customer_id, details={**details, "reason": reason})
    if action != "cancel":
        _sync_customer_statuses(db, old_customer_id, new_customer_id)
    db.commit()
    return {"membershipId": row.id, "customerId": new_customer_id, "action": action, "summary": summary}
