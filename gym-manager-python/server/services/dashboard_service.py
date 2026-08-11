from datetime import date, datetime, timedelta

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ..models import AttendanceSession, Customer, Employee, Membership, Payment, ServicePackage


def active_membership_member_count(db: Session):
    return db.query(func.count(func.distinct(Membership.customer_id))).join(Membership.package).filter(
        ServicePackage.is_pt == False,
        Membership.status == "active",
    ).scalar() or 0


def dashboard(db: Session):
    today=date.today();month_start=today.replace(day=1);soon=today+timedelta(days=14)
    active_members=active_membership_member_count(db)
    total_members=db.query(Customer).count()
    checkins_today=db.query(AttendanceSession).filter(func.date(AttendanceSession.checked_in_at)==today.isoformat()).count()
    expiring=db.query(Membership).join(Membership.package).filter(ServicePackage.is_pt==False,Membership.status=="active",Membership.expires_at>=today,Membership.expires_at<=soon).count()
    revenue=db.query(func.sum(Payment.amount)).filter(Payment.paid_at>=datetime.combine(month_start,datetime.min.time())).scalar() or 0
    debt=db.query(func.sum(Membership.debt_amount)).scalar() or 0
    activity=[]
    for offset in range(6,-1,-1):
        day=today-timedelta(days=offset)
        count=db.query(AttendanceSession).filter(func.date(AttendanceSession.checked_in_at)==day.isoformat()).count()
        activity.append({"date":day.isoformat(),"label":day.strftime("%d/%m"),"checkins":count})
    status_counts={"active":0,"expiring":0,"expired":0,"pending":0}
    memberships=db.query(Membership).options(joinedload(Membership.package)).join(Membership.package).filter(ServicePackage.is_pt==False).all()
    for row in memberships:
        if row.expires_at and row.expires_at<today: key="expired"
        elif row.expires_at and row.expires_at<=soon: key="expiring"
        elif row.status=="active": key="active"
        else:key="pending"
        status_counts[key]+=1
    attention_rows=db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person),joinedload(Membership.package)).join(Membership.package).filter(ServicePackage.is_pt==False,or_(Membership.debt_amount>0,Membership.expires_at<=soon)).order_by(Membership.debt_due_date,Membership.expires_at).limit(8).all()
    attention=[]
    for row in attention_rows:
        if row.debt_amount and row.debt_amount>0: issue=f"Còn nợ {row.debt_amount:,.0f} đ"
        elif row.expires_at and row.expires_at<today:issue="Gói đã hết hạn"
        else:issue=f"Hết hạn {row.expires_at.strftime('%d/%m/%Y')}"
        attention.append({"memberId":row.customer_id,"member":row.customer.person.display_name,"code":row.customer.customer_code,"issue":issue})
    recent=db.query(AttendanceSession).options(joinedload(AttendanceSession.customer).joinedload(Customer.person)).order_by(AttendanceSession.checked_in_at.desc()).limit(8).all()
    return {"metrics":{"totalMembers":total_members,"activeMembers":active_members,"checkinsToday":checkins_today,"expiringSoon":expiring,"revenueMonth":revenue,"outstanding":debt},"activity":activity,"membershipStatus":status_counts,"attention":attention,"recentCheckins":[{"id":r.id,"memberId":r.customer_id,"member":r.customer.person.display_name if r.customer else None,"code":r.customer.customer_code if r.customer else None,"time":r.checked_in_at.isoformat(),"status":r.status} for r in recent]}


def reports(db: Session, date_from: str | None, date_to: str | None):
    start=date.fromisoformat(date_from) if date_from else date.today().replace(day=1)
    end=date.fromisoformat(date_to) if date_to else date.today()
    start_dt=datetime.combine(start,datetime.min.time());end_dt=datetime.combine(end,datetime.max.time())
    payments=db.query(Payment).filter(Payment.paid_at>=start_dt,Payment.paid_at<=end_dt).all()
    revenue=sum(row.amount or 0 for row in payments)
    by_method={}
    for row in payments:by_method[row.method]=by_method.get(row.method,0)+(row.amount or 0)
    checkins=db.query(AttendanceSession).filter(AttendanceSession.checked_in_at>=start_dt,AttendanceSession.checked_in_at<=end_dt).count()
    active=active_membership_member_count(db)
    debts=db.query(Membership).options(joinedload(Membership.customer).joinedload(Customer.person),joinedload(Membership.package)).filter(Membership.debt_amount>0).order_by(Membership.debt_due_date).all()
    return {"period":{"from":start.isoformat(),"to":end.isoformat()},"summary":{"revenue":revenue,"payments":len(payments),"activeMembers":active,"checkins":checkins},"revenueByMethod":[{"method":key,"amount":value} for key,value in by_method.items()],"debts":[{"membershipId":r.id,"memberId":r.customer_id,"member":r.customer.person.display_name,"memberCode":r.customer.customer_code,"package":r.package.name,"amount":r.debt_amount or 0,"dueDate":r.debt_due_date.isoformat() if r.debt_due_date else None,"overdue":bool(r.debt_due_date and r.debt_due_date<date.today())} for r in debts]}
