from datetime import date, timedelta

from sqlalchemy.orm import Session, joinedload

from ..models import Customer, Employee, Membership, PtEnrollment, PtEnrollmentCoach, ServicePackage


def alerts(db: Session, expiring_days: int = 14, pt_sessions: int = 3, limit: int = 30):
    today = date.today()
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
    ).all()
    for row in overdue:
        days = (today - row.debt_due_date).days
        items.append({
            "id": f"debt-{row.id}", "type": "overdue_debt", "severity": "error",
            "memberId": row.customer_id, "memberName": row.customer.person.display_name,
            "title": f"Nợ quá hạn {days} ngày",
            "description": f"{row.package.name} · {row.debt_amount:,.0f} ₫ · hạn {row.debt_due_date.strftime('%d/%m/%Y')}",
            "sortDate": row.debt_due_date.isoformat(),
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
            "id": f"expiry-{row.id}", "type": "membership_expiring", "severity": "warning",
            "memberId": row.customer_id, "memberName": row.customer.person.display_name,
            "title": "Gói hết hạn hôm nay" if days == 0 else f"Gói hết hạn sau {days} ngày",
            "description": f"{row.package.name} · đến {row.expires_at.strftime('%d/%m/%Y')}",
            "sortDate": row.expires_at.isoformat(),
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
            "id": f"pt-{row.id}", "type": "pt_low_sessions", "severity": "info",
            "memberId": row.customer_id, "memberName": row.customer.person.display_name,
            "title": f"PT chỉ còn {row.remaining_sessions} buổi",
            "description": f"{row.group_type} · {coach_names}",
            "sortDate": (row.expires_at or date.max).isoformat(),
        })
    severity_order = {"error": 0, "warning": 1, "info": 2}
    items.sort(key=lambda item: (severity_order[item["severity"]], item["sortDate"]))
    counts = {
        "total": len(items),
        "overdueDebt": sum(item["type"] == "overdue_debt" for item in items),
        "expiring": sum(item["type"] == "membership_expiring" for item in items),
        "ptLowSessions": sum(item["type"] == "pt_low_sessions" for item in items),
    }
    return {"counts": counts, "items": items[:limit], "generatedAt": date.today().isoformat()}
