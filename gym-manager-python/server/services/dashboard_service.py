from datetime import date, datetime, timedelta

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload

from ..models import AttendanceSession, Customer, Employee, Membership, Payment, ServicePackage
from ..timeutils import utc_iso, utc_now, vietnam_today


def _attendance_iso(value, source: str | None):
    if not value:
        return None
    return value.isoformat() if source == "dah" else utc_iso(value)


def active_membership_member_count(db: Session):
    today = vietnam_today()
    return db.query(func.count(func.distinct(Membership.customer_id))).join(Membership.package).filter(
        ServicePackage.is_pt == False,
        Membership.status == "active",
        or_(Membership.expires_at == None, Membership.expires_at >= today),
    ).scalar() or 0


def _sum(query):
    return float(query.scalar() or 0)


def _owner_name(row):
    employee = row.direct_sales_employee or row.sale_online_employee or row.customer.sales_employee
    return employee.person.display_name if employee and employee.person else "Chưa phân công"


def _sale_owner(membership: Membership | None):
    if not membership:
        return None, "Chưa phân công", None
    employee = (
        membership.direct_sales_employee
        or membership.sale_online_employee
        or (membership.customer.sales_employee if membership.customer else None)
    )
    if not employee or not employee.person:
        return None, "Chưa phân công", None
    return employee.id, employee.person.display_name, employee.job_title


def dashboard(db: Session):
    today = vietnam_today()
    yesterday = today - timedelta(days=1)
    month_start = today.replace(day=1)
    previous_month_end = month_start - timedelta(days=1)
    previous_month_start = previous_month_end.replace(day=1)
    previous_mtd_end = min(previous_month_start + timedelta(days=today.day), month_start)
    soon_7 = today + timedelta(days=7)
    soon_14 = today + timedelta(days=14)
    recent_expiry_start = today - timedelta(days=30)
    active_members = active_membership_member_count(db)
    total_members = db.query(Customer).count()

    attendance_start = today - timedelta(days=13)
    attendance_rows = db.query(
        func.date(AttendanceSession.checked_in_at),
        func.count(AttendanceSession.id),
    ).filter(
        func.date(AttendanceSession.checked_in_at) >= attendance_start.isoformat(),
        func.date(AttendanceSession.checked_in_at) <= today.isoformat(),
    ).group_by(func.date(AttendanceSession.checked_in_at)).all()
    attendance_counts = {str(day): count for day, count in attendance_rows}
    checkins_today = attendance_counts.get(today.isoformat(), 0)
    checkins_yesterday = attendance_counts.get(yesterday.isoformat(), 0)
    open_visits = db.query(AttendanceSession).filter(AttendanceSession.status == "open").count()
    activity = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        previous_day = day - timedelta(days=7)
        activity.append({
            "date": day.isoformat(),
            "label": day.strftime("%d/%m"),
            "checkins": attendance_counts.get(day.isoformat(), 0),
            "previousCheckins": attendance_counts.get(previous_day.isoformat(), 0),
        })

    memberships = db.query(Membership).options(joinedload(Membership.package)).join(Membership.package).filter(ServicePackage.is_pt == False).all()
    health = {
        "activeStable": 0,
        "expiring7": 0,
        "expiring8To14": 0,
        "expiredRecent": 0,
        "expiredOlder": 0,
        "pending": 0,
        "suspended": 0,
        "other": 0,
    }
    for row in memberships:
        if row.status == "suspended":
            health["suspended"] += 1
        elif row.status == "pending":
            health["pending"] += 1
        elif row.expires_at and row.expires_at < today:
            health["expiredRecent" if row.expires_at >= recent_expiry_start else "expiredOlder"] += 1
        elif row.status == "active" and row.expires_at and row.expires_at <= soon_7:
            health["expiring7"] += 1
        elif row.status == "active" and row.expires_at and row.expires_at <= soon_14:
            health["expiring8To14"] += 1
        elif row.status == "active":
            health["activeStable"] += 1
        else:
            health["other"] += 1
    status_counts = {
        "active": health["activeStable"],
        "expiring": health["expiring7"] + health["expiring8To14"],
        "expired": health["expiredRecent"] + health["expiredOlder"],
        "pending": health["pending"],
    }

    expiring = health["expiring7"] + health["expiring8To14"]
    today_start = datetime.combine(today, datetime.min.time())
    today_end = datetime.combine(today, datetime.max.time())
    month_start_dt = datetime.combine(month_start, datetime.min.time())
    revenue_today = _sum(db.query(func.sum(Payment.amount)).filter(Payment.paid_at >= today_start, Payment.paid_at <= today_end))
    revenue_month = _sum(db.query(func.sum(Payment.amount)).filter(Payment.paid_at >= month_start_dt, Payment.paid_at <= today_end))
    revenue_previous_mtd = _sum(db.query(func.sum(Payment.amount)).filter(
        Payment.paid_at >= datetime.combine(previous_month_start, datetime.min.time()),
        Payment.paid_at < datetime.combine(previous_mtd_end, datetime.min.time()),
    ))
    debt = _sum(db.query(func.sum(Membership.debt_amount)))
    overdue_debt = _sum(db.query(func.sum(Membership.debt_amount)).filter(
        Membership.debt_amount > 0,
        Membership.debt_due_date != None,
        Membership.debt_due_date < today,
    ))

    debt_aging = {
        "notDue": {"count": 0, "amount": 0},
        "days1To7": {"count": 0, "amount": 0},
        "days8To30": {"count": 0, "amount": 0},
        "over30": {"count": 0, "amount": 0},
        "noDueDate": {"count": 0, "amount": 0},
    }
    for amount, due_date in db.query(Membership.debt_amount, Membership.debt_due_date).filter(Membership.debt_amount > 0):
        if not due_date:
            bucket = "noDueDate"
        elif due_date >= today:
            bucket = "notDue"
        else:
            overdue_days = (today - due_date).days
            bucket = "days1To7" if overdue_days <= 7 else "days8To30" if overdue_days <= 30 else "over30"
        debt_aging[bucket]["count"] += 1
        debt_aging[bucket]["amount"] += float(amount or 0)

    attention_candidates = db.query(Membership).options(
        joinedload(Membership.customer).joinedload(Customer.person),
        joinedload(Membership.customer).joinedload(Customer.sales_employee).joinedload(Employee.person),
        joinedload(Membership.package),
        joinedload(Membership.direct_sales_employee).joinedload(Employee.person),
        joinedload(Membership.sale_online_employee).joinedload(Employee.person),
    ).join(Membership.package).filter(
        ServicePackage.is_pt == False,
        Membership.status.in_(("active", "pending", "expired")),
        or_(
            Membership.debt_amount > 0,
            Membership.expires_at.between(recent_expiry_start, soon_14),
        ),
    ).all()

    def attention_priority(row):
        if row.debt_amount and row.debt_amount > 0 and row.debt_due_date and row.debt_due_date < today:
            return (0, row.debt_due_date.toordinal(), -row.id)
        if row.expires_at and row.expires_at < today:
            return (1, -row.expires_at.toordinal(), -row.id)
        if row.expires_at and row.expires_at <= soon_7:
            return (2, row.expires_at.toordinal(), -row.id)
        if row.debt_amount and row.debt_amount > 0:
            return (3, (row.debt_due_date or date.max).toordinal(), -row.id)
        return (4, (row.expires_at or date.max).toordinal(), -row.id)

    attention_rows = []
    seen_customer_ids = set()
    for row in sorted(attention_candidates, key=attention_priority):
        if row.customer_id in seen_customer_ids:
            continue
        seen_customer_ids.add(row.customer_id)
        attention_rows.append(row)
        if len(attention_rows) >= 10:
            break

    attention = []
    for row in attention_rows:
        if row.debt_amount and row.debt_amount > 0 and row.debt_due_date and row.debt_due_date < today:
            age_days = (today - row.debt_due_date).days
            issue_type, issue, priority = "overdue_debt", "Nợ quá hạn", "critical"
            timing = f"Quá hạn {age_days} ngày"
            value = float(row.debt_amount)
            action_label = "Thu tiền"
        elif row.expires_at and row.expires_at < today:
            age_days = (today - row.expires_at).days
            issue_type, issue = "expired", "Gói vừa hết hạn"
            priority = "critical" if age_days <= 7 else "high"
            timing = f"Đã hết hạn {age_days} ngày"
            value = None
            action_label = "Gia hạn"
        elif row.expires_at and row.expires_at <= soon_14:
            days_left = (row.expires_at - today).days
            issue_type, issue = "expiring", "Gói sắp hết hạn"
            priority = "high" if days_left <= 7 else "medium"
            timing = "Hết hạn hôm nay" if days_left == 0 else f"Còn {days_left} ngày"
            value = None
            action_label = "Gia hạn"
        else:
            issue_type, issue, priority = "debt", "Còn công nợ", "medium"
            timing = f"Hạn {row.debt_due_date.strftime('%d/%m/%Y')}" if row.debt_due_date else "Chưa có hạn thu"
            value = float(row.debt_amount or 0)
            action_label = "Thu tiền"
        attention.append({
            "id": f"{issue_type}-{row.id}",
            "memberId": row.customer_id,
            "member": row.customer.person.display_name,
            "code": row.customer.customer_code,
            "membershipCode": row.code,
            "package": row.package.name,
            "issueType": issue_type,
            "issue": issue,
            "priority": priority,
            "timing": timing,
            "value": value,
            "owner": _owner_name(row),
            "actionLabel": action_label,
        })

    recent = db.query(AttendanceSession).options(joinedload(AttendanceSession.customer).joinedload(Customer.person)).order_by(AttendanceSession.checked_in_at.desc()).limit(8).all()
    return {
        "generatedAt": utc_iso(utc_now()),
        "metrics": {
            "totalMembers": total_members,
            "activeMembers": active_members,
            "activeRate": round((active_members / total_members * 100), 1) if total_members else 0,
            "checkinsToday": checkins_today,
            "checkinsYesterday": checkins_yesterday,
            "openVisits": open_visits,
            "expiring7": health["expiring7"],
            "expiringSoon": expiring,
            "newlyExpired30": health["expiredRecent"],
            "revenueToday": revenue_today,
            "revenueMonth": revenue_month,
            "revenuePreviousMtd": revenue_previous_mtd,
            "outstanding": debt,
            "overdueDebt": overdue_debt,
        },
        "activity": activity,
        "membershipStatus": status_counts,
        "membershipHealth": {**health, "totalContracts": len(memberships)},
        "financialHealth": {"debtAging": debt_aging},
        "attention": attention,
        "recentCheckins": [{
            "id": r.id,
            "memberId": r.customer_id,
            "member": r.customer.person.display_name if r.customer else None,
            "code": r.customer.customer_code if r.customer else None,
            "time": _attendance_iso(r.checked_in_at, r.source),
            "status": r.status,
        } for r in recent],
    }


def reports(db: Session, date_from: str | None, date_to: str | None):
    today = vietnam_today()
    start=date.fromisoformat(date_from) if date_from else today.replace(day=1)
    end=date.fromisoformat(date_to) if date_to else today
    if start > end:
        start, end = end, start
    start_dt=datetime.combine(start,datetime.min.time());end_dt=datetime.combine(end,datetime.max.time())
    period_days = (end - start).days + 1
    previous_end = start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=period_days - 1)
    previous_start_dt = datetime.combine(previous_start, datetime.min.time())
    previous_end_dt = datetime.combine(previous_end, datetime.max.time())
    payments=db.query(Payment).options(
        joinedload(Payment.customer).joinedload(Customer.person),
        joinedload(Payment.membership).joinedload(Membership.package),
        joinedload(Payment.membership).joinedload(Membership.customer).joinedload(Customer.sales_employee).joinedload(Employee.person),
        joinedload(Payment.membership).joinedload(Membership.direct_sales_employee).joinedload(Employee.person),
        joinedload(Payment.membership).joinedload(Membership.sale_online_employee).joinedload(Employee.person),
    ).filter(Payment.paid_at>=start_dt,Payment.paid_at<=end_dt).order_by(Payment.paid_at.desc(), Payment.id.desc()).all()
    revenue=sum(row.amount or 0 for row in payments)
    previous_revenue = _sum(db.query(func.sum(Payment.amount)).filter(
        Payment.paid_at >= previous_start_dt,
        Payment.paid_at <= previous_end_dt,
    ))
    by_method={}
    for row in payments:by_method[row.method]=by_method.get(row.method,0)+(row.amount or 0)
    by_sale={}
    revenue_items=[]
    for row in payments:
        sale_id, sale_name, sale_title = _sale_owner(row.membership)
        key = sale_id or "unassigned"
        if key not in by_sale:
            by_sale[key] = {
                "saleEmployeeId": sale_id,
                "saleName": sale_name,
                "saleTitle": sale_title,
                "amount": 0,
                "payments": 0,
            }
        by_sale[key]["amount"] += float(row.amount or 0)
        by_sale[key]["payments"] += 1
        revenue_items.append({
            "paymentId": row.id,
            "paymentNo": row.payment_no,
            "paidAt": utc_iso(row.paid_at),
            "memberId": row.customer_id,
            "member": row.customer.person.display_name if row.customer and row.customer.person else None,
            "memberCode": row.customer.customer_code if row.customer else None,
            "membershipId": row.membership_id,
            "membershipCode": row.membership.code if row.membership else None,
            "package": row.membership.package.name if row.membership and row.membership.package else row.note,
            "saleEmployeeId": sale_id,
            "saleName": sale_name,
            "saleTitle": sale_title,
            "amount": row.amount or 0,
            "method": row.method,
            "channel": row.channel,
            "note": row.note,
        })
    revenue_by_sale = sorted(by_sale.values(), key=lambda item: (-item["amount"], item["saleName"] or ""))
    attendance_rows = db.query(AttendanceSession.checked_in_at).filter(
        AttendanceSession.checked_in_at>=start_dt,
        AttendanceSession.checked_in_at<=end_dt,
    ).all()
    checkins=len(attendance_rows)
    previous_checkins=db.query(AttendanceSession).filter(
        AttendanceSession.checked_in_at>=previous_start_dt,
        AttendanceSession.checked_in_at<=previous_end_dt,
    ).count()
    active=active_membership_member_count(db)
    debts=db.query(Membership).options(
        joinedload(Membership.customer).joinedload(Customer.person),
        joinedload(Membership.customer).joinedload(Customer.sales_employee).joinedload(Employee.person),
        joinedload(Membership.package),
        joinedload(Membership.direct_sales_employee).joinedload(Employee.person),
        joinedload(Membership.sale_online_employee).joinedload(Employee.person),
    ).filter(
        Membership.debt_amount>0,
        or_(Membership.debt_due_date == None, and_(Membership.debt_due_date>=start, Membership.debt_due_date<=end)),
    ).order_by(Membership.debt_due_date).all()
    debt_total=sum(row.debt_amount or 0 for row in debts)
    debt_items = []
    for row in debts:
        sale_id, sale_name, sale_title = _sale_owner(row)
        debt_items.append({
            "membershipId": row.id,
            "membershipCode": row.code,
            "memberId": row.customer_id,
            "member": row.customer.person.display_name if row.customer and row.customer.person else None,
            "memberCode": row.customer.customer_code if row.customer else None,
            "phone": row.customer.person.phone if row.customer and row.customer.person else None,
            "package": row.package.name if row.package else None,
            "saleEmployeeId": sale_id,
            "saleName": sale_name,
            "saleTitle": sale_title,
            "amount": row.debt_amount or 0,
            "dueDate": row.debt_due_date.isoformat() if row.debt_due_date else None,
            "overdue": bool(row.debt_due_date and row.debt_due_date < today),
        })
    revenue_daily = {start + timedelta(days=offset): {"amount": 0, "payments": 0, "checkins": 0} for offset in range(period_days)}
    for row in payments:
        local_day = row.paid_at.date()
        if local_day in revenue_daily:
            revenue_daily[local_day]["amount"] += float(row.amount or 0)
            revenue_daily[local_day]["payments"] += 1
    for checked_in_at, in attendance_rows:
        local_day = checked_in_at.date()
        if local_day in revenue_daily:
            revenue_daily[local_day]["checkins"] += 1
    overdue_amount = sum(float(row["amount"] or 0) for row in debt_items if row["dueDate"] and row["dueDate"] < today.isoformat())
    overdue_count = sum(1 for row in debt_items if row["dueDate"] and row["dueDate"] < today.isoformat())
    due_soon_amount = sum(
        float(row["amount"] or 0)
        for row in debt_items
        if row["dueDate"] and today.isoformat() <= row["dueDate"] <= (today + timedelta(days=7)).isoformat()
    )
    collection_base = revenue + debt_total
    return {
        "generatedAt": utc_iso(utc_now()),
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "comparisonPeriod": {"from": previous_start.isoformat(), "to": previous_end.isoformat()},
        "summary": {
            "revenue": revenue,
            "previousRevenue": previous_revenue,
            "payments": len(payments),
            "activeMembers": active,
            "checkins": checkins,
            "previousCheckins": previous_checkins,
            "debt": debt_total,
            "overdueDebt": overdue_amount,
            "overdueCount": overdue_count,
            "dueSoonDebt": due_soon_amount,
            "receivable": collection_base,
            "collectionRate": round((revenue / collection_base) * 100, 1) if collection_base else 0,
        },
        "daily": [
            {"date": day.isoformat(), **values}
            for day, values in revenue_daily.items()
        ],
        "revenueByMethod": [
            {"method": key, "amount": value, "share": round((value / revenue) * 100, 1) if revenue else 0}
            for key, value in sorted(by_method.items(), key=lambda item: -item[1])
        ],
        "revenueBySale": revenue_by_sale,
        "revenueItems": revenue_items,
        "debts": debt_items,
    }
