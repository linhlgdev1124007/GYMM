from datetime import date, timedelta

from sqlalchemy.orm import Session, joinedload

from ..models import AlertRead, Customer, Employee, Membership, PtEnrollment, PtEnrollmentCoach, ServicePackage
from ..timeutils import utc_iso, utc_now, vietnam_today


def _active_alerts(db: Session, expiring_days: int = 14, pt_sessions: int = 3, include_financial: bool = True):
    today = vietnam_today()
    soon = today + timedelta(days=expiring_days)
    items = []
    overdue = db.query(Membership).options(
        joinedload(Membership.customer).joinedload(Customer.person),
        joinedload(Membership.package),
    ).join(Membership.package).filter(
        ServicePackage.is_pt == False,
        Membership.debt_amount > 0,
        Membership.debt_due_date != None,
        Membership.debt_due_date < today,
        Membership.status.in_(("active", "pending")),
    ).all() if include_financial else []
    for row in overdue:
        days = (today - row.debt_due_date).days
        items.append({
            "id": f"debt-{row.id}-{row.debt_due_date.isoformat()}", "type": "overdue_debt", "severity": "error",
            "memberId": row.customer_id, "memberName": row.customer.person.display_name,
            "title": f"Nợ quá hạn {days} ngày",
            "description": f"{row.package.name} · {row.debt_amount:,.0f} ₫ · hạn {row.debt_due_date.strftime('%d/%m/%Y')}",
            "sortDate": row.debt_due_date.isoformat(),
            "sortRank": row.debt_due_date.toordinal(),
        })
    expired = db.query(Membership).options(
        joinedload(Membership.customer).joinedload(Customer.person),
        joinedload(Membership.package),
    ).join(Membership.package).filter(
        ServicePackage.is_pt == False,
        Membership.expires_at != None,
        Membership.expires_at < today,
        Membership.status.in_(("active", "expired")),
    ).all()
    for row in expired:
        days = (today - row.expires_at).days
        items.append({
            "id": f"expired-{row.id}-{row.expires_at.isoformat()}", "type": "membership_expired", "severity": "error",
            "memberId": row.customer_id, "memberName": row.customer.person.display_name,
            "title": "Gói đã hết hạn hôm qua" if days == 1 else f"Gói đã hết hạn {days} ngày",
            "description": f"{row.package.name} · hết hạn {row.expires_at.strftime('%d/%m/%Y')}",
            "sortDate": row.expires_at.isoformat(),
            "sortRank": -row.expires_at.toordinal(),
        })
    expiring = db.query(Membership).options(
        joinedload(Membership.customer).joinedload(Customer.person),
        joinedload(Membership.package),
    ).join(Membership.package).filter(
        ServicePackage.is_pt == False,
        Membership.status == "active",
        Membership.expires_at >= today,
        Membership.expires_at <= soon,
    ).all()
    for row in expiring:
        days = (row.expires_at - today).days
        items.append({
            "id": f"expiry-{row.id}-{row.expires_at.isoformat()}", "type": "membership_expiring", "severity": "warning",
            "memberId": row.customer_id, "memberName": row.customer.person.display_name,
            "title": "Gói hết hạn hôm nay" if days == 0 else f"Gói hết hạn sau {days} ngày",
            "description": f"{row.package.name} · đến {row.expires_at.strftime('%d/%m/%Y')}",
            "sortDate": row.expires_at.isoformat(),
            "sortRank": row.expires_at.toordinal(),
        })
    pt_rows = db.query(PtEnrollment).options(
        joinedload(PtEnrollment.customer).joinedload(Customer.person),
        joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person),
    ).filter(
        PtEnrollment.status == "active",
        PtEnrollment.remaining_sessions <= pt_sessions,
    ).all()
    for row in pt_rows:
        coach_names = ", ".join(assignment.coach.person.display_name for assignment in row.coach_assignments) or "Chưa phân Coach"
        items.append({
            "id": f"pt-{row.id}-{row.remaining_sessions}", "type": "pt_low_sessions", "severity": "info",
            "memberId": row.customer_id, "memberName": row.customer.person.display_name,
            "title": f"PT chỉ còn {row.remaining_sessions} buổi",
            "description": f"{row.group_type} · {coach_names}",
            "sortDate": (row.expires_at or date.max).isoformat(),
            "sortRank": (row.expires_at or date.max).toordinal(),
        })
    severity_order = {"error": 0, "warning": 1, "info": 2}
    items.sort(key=lambda item: (severity_order[item["severity"]], item["sortRank"]))
    return items


def alerts(db: Session, user_id: int | None = None, expiring_days: int = 14, pt_sessions: int = 3, limit: int = 30, include_financial: bool = True):
    items = _active_alerts(db, expiring_days, pt_sessions, include_financial)
    reads = {}
    if user_id is not None and items:
        keys = [item["id"] for item in items]
        reads = {
            row.alert_key: row.read_at
            for row in db.query(AlertRead).filter(
                AlertRead.user_id == user_id,
                AlertRead.alert_key.in_(keys),
            )
        }
    for item in items:
        read_at = reads.get(item["id"])
        item["isRead"] = read_at is not None
        item["readAt"] = utc_iso(read_at) if read_at else None
    unread_items = [item for item in items if not item["isRead"]]
    read_items = [item for item in items if item["isRead"]]
    counts = {
        "total": len(items),
        "unread": len(unread_items),
        "expired": sum(item["type"] == "membership_expired" for item in items),
        "expiring": sum(item["type"] == "membership_expiring" for item in items),
        "ptLowSessions": sum(item["type"] == "pt_low_sessions" for item in items),
    }
    if include_financial:
        counts["overdueDebt"] = sum(item["type"] == "overdue_debt" for item in items)
    return {
        "counts": counts,
        "items": unread_items[:limit] + read_items[:limit],
        "generatedAt": vietnam_today().isoformat(),
    }


def mark_read(db: Session, user_id: int, alert_key: str, include_financial: bool = True):
    active_keys = {item["id"] for item in _active_alerts(db, include_financial=include_financial)}
    if alert_key not in active_keys:
        return False
    existing = db.query(AlertRead).filter(
        AlertRead.user_id == user_id,
        AlertRead.alert_key == alert_key,
    ).first()
    if not existing:
        db.add(AlertRead(user_id=user_id, alert_key=alert_key, read_at=utc_now()))
        db.commit()
    return True


def mark_all_read(db: Session, user_id: int, include_financial: bool = True):
    active_keys = {item["id"] for item in _active_alerts(db, include_financial=include_financial)}
    existing_keys = {
        key for (key,) in db.query(AlertRead.alert_key).filter(
            AlertRead.user_id == user_id,
            AlertRead.alert_key.in_(active_keys),
        )
    } if active_keys else set()
    now = utc_now()
    db.add_all([
        AlertRead(user_id=user_id, alert_key=key, read_at=now)
        for key in active_keys - existing_keys
    ])
    db.commit()
    return len(active_keys - existing_keys)
