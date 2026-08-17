from datetime import UTC, date, datetime

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from ..models import BankAccount, DayPassVisit, Employee, Person, User
from ..timeutils import VIETNAM_TZ, utc_iso, utc_now, utc_vietnam_date, vietnam_day_utc_bounds, vietnam_today
from .audit_service import record_audit
from .serializers import employee_data, pagination

DEFAULT_DAY_PASS_PRICE = 79000
SALES_TITLE_KEYWORDS = ("sale",)


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


def _text(value, limit=255):
    text = str(value or "").strip()
    if not text or text.lower() in {"null", "none", "undefined"}:
        return None
    return text[:limit]


def _parse_date(value, default: date | None = None):
    if not value:
        return default
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Ngày tập không hợp lệ. Vui lòng dùng định dạng YYYY-MM-DD.") from exc


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


def _is_sales_employee(employee: Employee | None) -> bool:
    title = str(employee.job_title if employee else "").casefold()
    return any(keyword in title for keyword in SALES_TITLE_KEYWORDS)


def _employee_id(db: Session, value, *, sales_only: bool = False) -> int | None:
    employee_id = _int(value)
    if not employee_id:
        return None
    employee = db.query(Employee).filter(Employee.id == employee_id, Employee.status == "active").first()
    if not employee:
        raise HTTPException(422, "Nhân viên phụ trách không hợp lệ hoặc đã ngừng hoạt động.")
    if sales_only and not _is_sales_employee(employee):
        raise HTTPException(422, "Sale phải là nhân viên Sale đang hoạt động.")
    return employee.id


def _require_bank_account(db: Session, method: str, bank_account_id: int | None, amount: float):
    if amount <= 0 or method != "bank_transfer":
        return
    if not bank_account_id:
        raise HTTPException(422, "Vui lòng chọn tài khoản nhận tiền khi thanh toán chuyển khoản.")
    account = db.query(BankAccount).filter(BankAccount.id == bank_account_id, BankAccount.status == "active").first()
    if not account:
        raise HTTPException(422, "Tài khoản nhận tiền không hợp lệ hoặc đã tạm ngừng.")


def _net_revenue_filter():
    return or_(
        DayPassVisit.status == "active",
        and_(DayPassVisit.status == "converted", DayPassVisit.conversion_policy == "deducted"),
    )


def day_pass_data(row: DayPassVisit):
    return {
        "id": row.id,
        "guestName": row.guest_name,
        "guestPhone": row.guest_phone,
        "guestGender": row.guest_gender,
        "guestNote": row.guest_note,
        "visitDate": row.visit_date.isoformat() if row.visit_date else None,
        "defaultPrice": row.default_price or DEFAULT_DAY_PASS_PRICE,
        "chargedAmount": row.charged_amount or 0,
        "paidAt": utc_iso(row.paid_at),
        "paymentMethod": row.payment_method,
        "bankAccountId": row.bank_account_id,
        "salesEmployee": employee_data(row.sales_employee),
        "ownerEmployee": employee_data(row.owner_employee),
        "status": row.status,
        "conversionPolicy": row.conversion_policy,
        "conversionAmount": row.conversion_amount or 0,
        "convertedCustomerId": row.converted_customer_id,
        "convertedMembershipId": row.converted_membership_id,
        "convertedAt": utc_iso(row.converted_at),
        "createdAt": utc_iso(row.created_at),
    }


def _query_with_options(db: Session):
    return db.query(DayPassVisit).options(
        joinedload(DayPassVisit.sales_employee).joinedload(Employee.person),
        joinedload(DayPassVisit.owner_employee).joinedload(Employee.person),
    )


def list_day_passes(
    db: Session,
    q: str = "",
    status: str = "all",
    method: str = "all",
    date_from: str = "",
    date_to: str = "",
    page: int = 1,
    page_size: int = 30,
):
    today = vietnam_today()
    start = _parse_date(date_from, today)
    end = _parse_date(date_to, today)
    if start > end:
        start, end = end, start
    query = _query_with_options(db).filter(DayPassVisit.visit_date >= start, DayPassVisit.visit_date <= end)
    if q.strip():
        term = q.strip()
        query = query.filter(or_(DayPassVisit.guest_name.contains(term), DayPassVisit.guest_phone.contains(term)))
    if status != "all":
        query = query.filter(DayPassVisit.status == status)
    if method != "all":
        query = query.filter(DayPassVisit.payment_method == method)
    total = query.count()
    rows = query.order_by(DayPassVisit.visit_date.desc(), DayPassVisit.paid_at.desc(), DayPassVisit.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    summary_query = db.query(
        func.count(DayPassVisit.id),
        func.sum(
            DayPassVisit.charged_amount
        ),
    ).filter(DayPassVisit.visit_date >= start, DayPassVisit.visit_date <= end, _net_revenue_filter())
    count, amount = summary_query.first()
    return {
        "items": [day_pass_data(row) for row in rows],
        "summary": {"activeVisits": count or 0, "netRevenue": float(amount or 0)},
        "pagination": pagination(page, page_size, total),
    }


def get_day_pass(db: Session, day_pass_id: int):
    row = _query_with_options(db).filter(DayPassVisit.id == day_pass_id).first()
    if not row:
        raise HTTPException(404, "Không tìm thấy lượt tập ngày.")
    return day_pass_data(row)


def create_day_pass(db: Session, payload: dict, actor: User):
    name = str(payload.get("guestName", "")).strip()
    if not name:
        raise HTTPException(422, "Vui lòng nhập tên khách tập ngày.")
    visit_date = _parse_date(payload.get("visitDate"), vietnam_today())
    charged_amount = _money(payload.get("chargedAmount"), DEFAULT_DAY_PASS_PRICE)
    if charged_amount <= 0:
        raise HTTPException(422, "Số tiền thu phải lớn hơn 0.")
    method = payload.get("paymentMethod") or "cash"
    bank_account_id = _int(payload.get("bankAccountId"))
    _require_bank_account(db, method, bank_account_id, charged_amount)
    row = DayPassVisit(
        guest_name=name,
        guest_phone=_text(payload.get("guestPhone"), 40),
        guest_gender=_text(payload.get("guestGender"), 20),
        guest_note=_text(payload.get("guestNote"), 1000),
        visit_date=visit_date,
        default_price=DEFAULT_DAY_PASS_PRICE,
        charged_amount=charged_amount,
        paid_at=_parse_paid_at(payload.get("paidAt")),
        payment_method=method,
        bank_account_id=bank_account_id,
        sales_employee_id=_employee_id(db, payload.get("salesEmployeeId"), sales_only=True),
        owner_employee_id=_employee_id(db, payload.get("ownerEmployeeId")),
        status="active",
        created_by_user_id=actor.id if actor else None,
    )
    db.add(row)
    db.flush()
    record_audit(
        db,
        actor,
        "create",
        "day_pass",
        row.id,
        f"Ghi nhận khách tập ngày {row.guest_name}",
        details={"visitDate": row.visit_date, "chargedAmount": row.charged_amount, "paymentMethod": row.payment_method},
    )
    db.commit()
    return get_day_pass(db, row.id)


def update_day_pass(db: Session, day_pass_id: int, payload: dict, actor: User):
    row = db.get(DayPassVisit, day_pass_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy lượt tập ngày.")
    if row.status != "active":
        raise HTTPException(409, "Chỉ có thể sửa lượt tập ngày đang hoạt động.")
    if "guestName" in payload:
        name = str(payload.get("guestName", "")).strip()
        if not name:
            raise HTTPException(422, "Vui lòng nhập tên khách tập ngày.")
        row.guest_name = name
    if "guestPhone" in payload:
        row.guest_phone = _text(payload.get("guestPhone"), 40)
    if "guestGender" in payload:
        row.guest_gender = _text(payload.get("guestGender"), 20)
    if "guestNote" in payload:
        row.guest_note = _text(payload.get("guestNote"), 1000)
    if "visitDate" in payload:
        row.visit_date = _parse_date(payload.get("visitDate"), row.visit_date)
    if "chargedAmount" in payload:
        row.charged_amount = _money(payload.get("chargedAmount"), row.charged_amount)
    if row.charged_amount <= 0:
        raise HTTPException(422, "Số tiền thu phải lớn hơn 0.")
    if "paidAt" in payload:
        row.paid_at = _parse_paid_at(payload.get("paidAt"))
    if "paymentMethod" in payload:
        row.payment_method = payload.get("paymentMethod") or "cash"
    if "bankAccountId" in payload:
        row.bank_account_id = _int(payload.get("bankAccountId"))
    _require_bank_account(db, row.payment_method, row.bank_account_id, row.charged_amount)
    if "salesEmployeeId" in payload:
        row.sales_employee_id = _employee_id(db, payload.get("salesEmployeeId"), sales_only=True)
    if "ownerEmployeeId" in payload:
        row.owner_employee_id = _employee_id(db, payload.get("ownerEmployeeId"))
    row.updated_at = utc_now()
    record_audit(
        db,
        actor,
        "update",
        "day_pass",
        row.id,
        f"Cập nhật lượt tập ngày {row.guest_name}",
        details={"fields": list(payload.keys())},
    )
    db.commit()
    return get_day_pass(db, row.id)


def void_day_pass(db: Session, day_pass_id: int, payload: dict, actor: User):
    row = db.get(DayPassVisit, day_pass_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy lượt tập ngày.")
    if row.status != "active":
        raise HTTPException(409, "Lượt tập ngày này không còn hoạt động.")
    reason = str(payload.get("reason", "")).strip() or "Hủy lượt tập ngày"
    row.status = "void"
    row.updated_at = utc_now()
    record_audit(db, actor, "void", "day_pass", row.id, f"Hủy lượt tập ngày {row.guest_name}", details={"reason": reason})
    db.commit()
    return get_day_pass(db, row.id)


CONVERSION_POLICIES = {
    "refunded": "Hoàn tiền",
    "deducted": "Khấu trừ vào gói",
}


def mark_converted_day_pass(db: Session, day_pass_id: int | None, customer_id: int, membership_id: int, actor: User | None, policy: str = "refunded"):
    if not day_pass_id:
        return None
    if policy not in CONVERSION_POLICIES:
        raise HTTPException(422, "Chính sách xử lý tiền tập ngày không hợp lệ.")
    row = db.query(DayPassVisit).filter(DayPassVisit.id == day_pass_id).first()
    if not row:
        raise HTTPException(404, "Không tìm thấy lượt tập ngày cần chuyển đổi.")
    if row.status != "active":
        raise HTTPException(409, "Lượt tập ngày này đã được xử lý trước đó.")
    row.status = "converted"
    row.conversion_policy = policy
    row.conversion_amount = row.charged_amount or 0
    row.converted_customer_id = customer_id
    row.converted_membership_id = membership_id
    row.converted_at = utc_now()
    row.updated_at = utc_now()
    record_audit(
        db,
        actor,
        "convert",
        "day_pass",
        row.id,
        f"Chuyển khách tập ngày {row.guest_name} sang hội viên: {CONVERSION_POLICIES[policy].lower()} {row.conversion_amount:,.0f} ₫",
        customer_id=customer_id,
        details={
            "membershipId": membership_id,
            "policy": policy,
            "policyLabel": CONVERSION_POLICIES[policy],
            "amount": row.conversion_amount,
        },
    )
    return row


def day_pass_revenue_rows(db: Session, start: date, end: date):
    start_dt, end_dt = vietnam_day_utc_bounds(start, end)
    return _query_with_options(db).filter(
        DayPassVisit.paid_at >= start_dt,
        DayPassVisit.paid_at < end_dt,
        _net_revenue_filter(),
    ).all()


def day_pass_daily_revenue(db: Session, start: date, end: date):
    result = {}
    for row in day_pass_revenue_rows(db, start, end):
        local_day = utc_vietnam_date(row.paid_at)
        result[local_day] = result.get(local_day, 0) + float(row.charged_amount or 0)
    return result
