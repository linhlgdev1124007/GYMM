from datetime import date, datetime, timedelta
import json

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..models import Customer, Membership, MembershipEvent, MembershipFreeze, ServicePackage, User
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
    rows = (
        db.query(Membership)
        .options(joinedload(Membership.package), joinedload(Membership.events))
        .join(ServicePackage)
        .filter(
            Membership.customer_id == customer_id,
            Membership.status.in_(statuses),
            ServicePackage.is_pt == False,
            or_(Membership.expires_at == None, Membership.expires_at >= business_date()),
        )
        .order_by(Membership.starts_at.desc(), Membership.id.desc())
        .all()
    )
    today = business_date()

    def sort_key(row: Membership):
        if row.status == "active" and (not row.starts_at or row.starts_at <= today):
            priority = 0
        elif row.status in ("frozen", "suspended"):
            priority = 1
        elif row.status == "pending":
            priority = 2
        else:
            priority = 3
        return (priority, -(row.starts_at or date.min).toordinal(), -row.id)

    return sorted(rows, key=sort_key)[0] if rows else None


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


def _pending_freezes(membership: Membership):
    return [
        freeze for freeze in getattr(membership, "freezes", [])
        if not freeze.completed_at
    ]


def _freeze_for_day(membership: Membership, day: date):
    freezes = [
        freeze for freeze in _pending_freezes(membership)
        if freeze.starts_at <= day
    ]
    return sorted(freezes, key=lambda row: (row.starts_at, row.id), reverse=True)[0] if freezes else None


def _complete_freeze(
    db: Session,
    membership: Membership,
    freeze: MembershipFreeze,
    completed_on: date,
    actor: User | None = None,
    reason: str = "Kết thúc bảo lưu",
):
    actual_end = min(completed_on, freeze.ends_at)
    if actual_end < freeze.starts_at:
        return 0
    previous_expiry = membership.expires_at
    planned_end = freeze.ends_at
    actual_days = max((actual_end - freeze.starts_at).days, 0)
    freeze.ends_at = actual_end
    freeze.completed_at = actual_end
    freeze.compensated_days = actual_days
    if membership.expires_at and actual_days:
        membership.expires_at = membership.expires_at + timedelta(days=actual_days)
    membership.status = "active"
    if membership.customer:
        membership.customer.status = "active"
    event = MembershipEvent(
        membership_id=membership.id,
        action="unfreeze",
        from_customer_id=membership.customer_id,
        to_customer_id=membership.customer_id,
        from_package_id=membership.package_id,
        to_package_id=membership.package_id,
        effective_at=actual_end,
        reason=reason,
        created_by_user_id=actor.id if actor else None,
        details_json=json.dumps({
            "startsAt": str(freeze.starts_at),
            "plannedEndsAt": str(planned_end),
            "actualEndsAt": str(actual_end),
            "compensatedDays": actual_days,
            "previousExpiry": str(previous_expiry) if previous_expiry else None,
            "newExpiry": str(membership.expires_at) if membership.expires_at else None,
        }, ensure_ascii=False),
    )
    db.add(event)
    record_audit(
        db,
        actor,
        "unfreeze",
        "membership",
        membership.id,
        f"Kết thúc bảo lưu gói {membership.package.name} · cộng {actual_days} ngày",
        customer_id=membership.customer_id,
        details={
            "startsAt": freeze.starts_at,
            "plannedEndsAt": planned_end,
            "actualEndsAt": actual_end,
            "compensatedDays": actual_days,
            "previousExpiry": previous_expiry,
            "newExpiry": membership.expires_at,
        },
    )
    return actual_days


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
    remaining_days = None
    compensated_days = 0

    if previous_status == "frozen":
        freeze = _freeze_for_day(membership, day)
        if freeze:
            compensated_days = _complete_freeze(db, membership, freeze, day, actor, reason)
        membership.status = "active"
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
            f"Kích hoạt lại gói {membership.package.name} từ bảo lưu",
            customer_id=membership.customer_id,
            details={"activatedAt": day, "previousStatus": previous_status, "compensatedDays": compensated_days},
        )
        return True

    if previous_status == "suspended" and suspended_at and previous_expires_at:
        remaining_days = max((previous_expires_at - suspended_at).days, 0)
        compensated_days = remaining_days

    membership.status = "active"
    membership.activated_at = day
    membership.starts_at = day
    if previous_status == "suspended" and remaining_days is not None:
        membership.expires_at = day + timedelta(days=remaining_days)
    elif membership.package.duration_days:
        membership.expires_at = day + timedelta(days=membership.package.duration_days)

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
            "remainingDays": remaining_days,
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
        .options(joinedload(Membership.package), joinedload(Membership.customer), joinedload(Membership.freezes))
        .join(ServicePackage)
        .filter(ServicePackage.is_pt == False)
        .all()
    )
    changed = 0
    touched_customer_ids = set()
    for row in rows:
        freeze = _freeze_for_day(row, day)
        if freeze and freeze.ends_at < day:
            changed += 1 if _complete_freeze(db, row, freeze, freeze.ends_at, reason="Tự động kết thúc bảo lưu") else 0
        elif freeze and freeze.starts_at <= day <= freeze.ends_at and row.status == "active":
            row.status = "frozen"
            if row.customer:
                row.customer.status = "lead"
            changed += 1
        elif row.status == "pending" and row.activated_at and row.activated_at <= day:
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
