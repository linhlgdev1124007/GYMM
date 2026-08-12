from datetime import date, datetime, timedelta
import json

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..models import Customer, Membership, MembershipEvent, ServicePackage, User
from ..timeutils import vietnam_today
from .audit_service import record_audit


def business_date(value: date | datetime | None = None) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return vietnam_today()


def current_regular_membership(db: Session, customer_id: int, include_pending: bool = True):
    statuses = ("active", "pending", "frozen", "suspended") if include_pending else ("active",)
    return (
        db.query(Membership)
        .options(joinedload(Membership.package), joinedload(Membership.events))
        .join(ServicePackage)
        .filter(
            Membership.customer_id == customer_id,
            Membership.status.in_(statuses),
            ServicePackage.is_pt == False,
            or_(Membership.expires_at == None, Membership.expires_at >= business_date()),
        )
        .order_by(Membership.registered_at.desc(), Membership.id.desc())
        .first()
    )


def _latest_suspend_event(membership: Membership):
    events = [
        event for event in getattr(membership, "events", [])
        if event.action == "suspend" and event.details_json
    ]
    return sorted(events, key=lambda row: row.created_at, reverse=True)[0] if events else None


def _suspended_at(event) -> date | None:
    if not event:
        return None
    try:
        details = json.loads(event.details_json or "{}")
    except (TypeError, ValueError):
        return None
    try:
        return date.fromisoformat(details.get("suspendedAt") or "")
    except (TypeError, ValueError):
        return None


def activate_membership(
    db: Session,
    membership: Membership,
    activated_on: date | datetime | None = None,
    actor: User | None = None,
    reason: str = "Kích hoạt lần đầu tập",
):
    day = business_date(activated_on)
    if membership.status == "active" and membership.activated_at:
        return False

    previous_status = membership.status
    previous_starts_at = membership.starts_at
    previous_expires_at = membership.expires_at
    suspended_event = _latest_suspend_event(membership)
    suspended_at = _suspended_at(suspended_event)
    compensated_days = 0

    if suspended_at and day >= suspended_at:
        compensated_days = (day - suspended_at).days + 1
        if membership.expires_at:
            membership.expires_at = membership.expires_at + timedelta(days=compensated_days)

    membership.status = "active"
    membership.activated_at = day
    if previous_status != "suspended" and (not membership.starts_at or membership.starts_at < day):
        membership.starts_at = day
        if membership.package.duration_days:
            membership.expires_at = day + timedelta(days=membership.package.duration_days)
            if compensated_days:
                membership.expires_at = membership.expires_at + timedelta(days=compensated_days)

    if membership.customer:
        membership.customer.status = "active"

    event = MembershipEvent(
        membership_id=membership.id,
        action="activate",
        from_customer_id=membership.customer_id,
        to_customer_id=membership.customer_id,
        from_package_id=membership.package_id,
        to_package_id=membership.package_id,
        effective_at=day,
        reason=reason,
        created_by_user_id=actor.id if actor else None,
        details_json=json.dumps({
            "previousStatus": previous_status,
            "previousStartsAt": str(previous_starts_at) if previous_starts_at else None,
            "previousExpiresAt": str(previous_expires_at) if previous_expires_at else None,
            "activatedAt": str(day),
            "compensatedDays": compensated_days,
        }, ensure_ascii=False),
    )
    db.add(event)
    record_audit(
        db,
        actor,
        "activate",
        "membership",
        membership.id,
        f"Kích hoạt gói {membership.package.name}",
        customer_id=membership.customer_id,
        details={"activatedAt": day, "previousStatus": previous_status},
    )
    return True


def activate_customer_first_checkin(db: Session, customer_id: int, checked_in_at: date | datetime | None = None):
    membership = current_regular_membership(db, customer_id)
    if not membership or membership.status not in ("pending", "suspended"):
        return None
    activate_membership(db, membership, checked_in_at, reason="Kích hoạt khi check-in lần đầu")
    return membership


def refresh_membership_lifecycle(db: Session, today: date | None = None):
    day = today or vietnam_today()
    rows = (
        db.query(Membership)
        .options(joinedload(Membership.package), joinedload(Membership.customer))
        .join(ServicePackage)
        .filter(ServicePackage.is_pt == False)
        .all()
    )
    changed = 0
    touched_customer_ids = set()
    for row in rows:
        if row.status == "pending" and row.activated_at and row.activated_at <= day:
            if activate_membership(db, row, row.activated_at, reason="Tự động kích hoạt theo ngày hẹn"):
                changed += 1
        elif row.status == "active" and row.expires_at and row.expires_at < day:
            row.status = "expired"
            changed += 1
        touched_customer_ids.add(row.customer_id)

    for customer_id in touched_customer_ids:
        customer = db.get(Customer, customer_id)
        current = current_regular_membership(db, customer_id)
        if not customer:
            continue
        if current:
            customer.status = "active" if current.status == "active" else "lead"
        elif customer.status not in ("blocked", "inactive"):
            customer.status = "inactive"
    db.commit()
    return changed
