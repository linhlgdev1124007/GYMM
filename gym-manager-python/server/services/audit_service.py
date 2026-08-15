import json
from datetime import UTC, datetime, time

from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..models import AuditLog, Customer, User
from .serializers import pagination
from ..timeutils import VIETNAM_TZ, utc_iso, vietnam_today


def record_audit(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: int | None,
    summary: str,
    *,
    customer_id: int | None = None,
    details: dict | None = None,
    ip_address: str | None = None,
):
    db.add(
        AuditLog(
            actor_user_id=actor.id if actor else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            customer_id=customer_id,
            summary=summary,
            details_json=json.dumps(details, ensure_ascii=False, default=str) if details else None,
            ip_address=ip_address,
        )
    )


def _customer_data(row: Customer | None):
    if not row:
        return None
    return {
        "id": row.id,
        "name": row.person.display_name,
        "code": row.customer_code,
        "phone": row.person.phone,
        "status": row.status,
        "avatarImageData": row.avatar_image_data,
    }


def audit_data(row: AuditLog, customers: dict[int, Customer] | None = None):
    try:
        details = json.loads(row.details_json) if row.details_json else None
    except (TypeError, ValueError):
        details = None
    return {
        "id": row.id,
        "actor": {
            "id": row.actor.id,
            "name": row.actor.display_name,
            "username": row.actor.username,
            "role": row.actor.role,
        }
        if row.actor
        else {"id": None, "name": "Hệ thống", "username": "system", "role": "system"},
        "action": row.action,
        "entityType": row.entity_type,
        "entityId": row.entity_id,
        "customerId": row.customer_id,
        "customer": _customer_data(customers.get(row.customer_id) if customers and row.customer_id else None),
        "summary": row.summary,
        "details": details,
        "ipAddress": row.ip_address,
        "createdAt": utc_iso(row.created_at),
    }


def list_audit_logs(
    db: Session,
    q: str = "",
    action: str = "all",
    actor_id: int | None = None,
    entity_type: str = "all",
    scope: str = "all",
    page: int = 1,
    page_size: int = 30,
):
    query = db.query(AuditLog).options(joinedload(AuditLog.actor))
    if q.strip():
        term = q.strip()
        query = query.outerjoin(AuditLog.actor).filter(
            or_(
                AuditLog.summary.contains(term),
                AuditLog.entity_type.contains(term),
                User.display_name.contains(term),
                User.username.contains(term),
            )
        )
    if action != "all":
        query = query.filter(AuditLog.action == action)
    if actor_id:
        query = query.filter(AuditLog.actor_user_id == actor_id)
    if entity_type != "all":
        query = query.filter(AuditLog.entity_type == entity_type)
    if scope == "today":
        today = vietnam_today()
        start = datetime.combine(today, time.min, tzinfo=VIETNAM_TZ).astimezone(UTC).replace(tzinfo=None)
        end = datetime.combine(today, time.max, tzinfo=VIETNAM_TZ).astimezone(UTC).replace(tzinfo=None)
        query = query.filter(AuditLog.created_at >= start, AuditLog.created_at <= end)
    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()
    customer_ids = {row.customer_id for row in rows if row.customer_id}
    customers = {
        row.id: row
        for row in db.query(Customer)
        .options(joinedload(Customer.person))
        .filter(Customer.id.in_(customer_ids))
        .all()
    } if customer_ids else {}
    actors = db.query(User).filter(User.id.in_(db.query(AuditLog.actor_user_id))).order_by(User.display_name).all()
    return {
        "items": [audit_data(row, customers) for row in rows],
        "actors": [
            {"id": row.id, "name": row.display_name, "username": row.username}
            for row in actors
        ],
        "pagination": pagination(page, page_size, total),
    }


def member_audit_logs(db: Session, customer_id: int, limit: int = 100):
    rows = db.query(AuditLog).options(joinedload(AuditLog.actor)).filter(
        AuditLog.customer_id == customer_id
    ).order_by(AuditLog.created_at.desc(), AuditLog.id.desc()).limit(limit).all()
    customers = {
        customer_id: db.query(Customer)
        .options(joinedload(Customer.person))
        .filter(Customer.id == customer_id)
        .first()
    }
    return [audit_data(row, customers) for row in rows]
