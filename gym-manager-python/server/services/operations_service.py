from datetime import date, datetime
import secrets

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ..models import (
    Appointment, AttendanceSession, BankAccount, Branch, CashShift, CommissionLedger,
    Customer, Device, Employee, Membership, Payment, Person, PtEnrollment, PtGroup,
    ServicePackage,
)
from .serializers import employee_data, pagination, payment_data, pt_data


def _as_int(value, default=None):
    try: return int(value) if value not in (None, "") else default
    except (TypeError, ValueError): return default


def _as_date(value):
    return date.fromisoformat(value) if value else None


def list_trainers(db: Session, q: str, page: int, page_size: int):
    query = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active")
    if q: query = query.join(Employee.person).filter(or_(Person.display_name.contains(q), Person.phone.contains(q), Employee.employee_code.contains(q), Employee.job_title.contains(q)))
    total = query.count(); rows = query.order_by(Employee.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    ids = [row.id for row in rows]
    counts = dict(db.query(PtEnrollment.coach_id, func.count(PtEnrollment.id)).filter(PtEnrollment.coach_id.in_(ids), PtEnrollment.status == "active").group_by(PtEnrollment.coach_id).all()) if ids else {}
    sessions = dict(db.query(PtEnrollment.coach_id, func.sum(PtEnrollment.remaining_sessions)).filter(PtEnrollment.coach_id.in_(ids), PtEnrollment.status == "active").group_by(PtEnrollment.coach_id).all()) if ids else {}
    items=[]
    for row in rows:
        item=employee_data(row); item["activeClients"]=counts.get(row.id,0); item["ptSessions"]=sessions.get(row.id,0) or 0; items.append(item)
    return {"items":items,"pagination":pagination(page,page_size,total)}


def create_trainer(db: Session, payload: dict):
    name=str(payload.get("name","")).strip()
    if not name: raise HTTPException(422,"Tên nhân viên là bắt buộc.")
    person=Person(display_name=name,phone=payload.get("phone") or None,email=payload.get("email") or None,status="active",biometric_consent_status="not_requested")
    db.add(person);db.flush()
    branch_id=db.query(Branch.id).order_by(Branch.id).scalar()
    row=Employee(person_id=person.id,branch_id=branch_id,employee_code=f"TMP-{secrets.token_hex(4)}",job_title=payload.get("title") or "Coach",base_salary=0,status="active")
    db.add(row);db.flush();row.employee_code=f"EMP-{row.id:05d}";db.commit();db.refresh(row)
    return employee_data(row)


def update_trainer(db: Session, trainer_id: int, payload: dict):
    row=db.query(Employee).options(joinedload(Employee.person)).filter(Employee.id==trainer_id).first()
    if not row: raise HTTPException(404,"Không tìm thấy nhân viên.")
    if "name" in payload: row.person.display_name=str(payload["name"]).strip() or row.person.display_name
    if "phone" in payload: row.person.phone=payload["phone"] or None
    if "email" in payload: row.person.email=payload["email"] or None
    if "title" in payload: row.job_title=payload["title"] or None
    db.commit();return employee_data(row)


def delete_trainer(db: Session, trainer_id: int):
    row=db.query(Employee).options(joinedload(Employee.person)).filter(Employee.id==trainer_id).first()
    if not row: raise HTTPException(404,"Không tìm thấy nhân viên.")
    references=sum([
        db.query(Customer).filter(Customer.sales_employee_id==trainer_id).count(),
        db.query(Membership).filter(or_(Membership.sale_online_employee_id==trainer_id,Membership.direct_sales_employee_id==trainer_id,Membership.pt_converter_employee_id==trainer_id)).count(),
        db.query(PtEnrollment).filter(PtEnrollment.coach_id==trainer_id).count(),
        db.query(PtGroup).filter(PtGroup.coach_id==trainer_id).count(),
        db.query(Appointment).filter(or_(Appointment.employee_id==trainer_id,Appointment.support_employee_id==trainer_id)).count(),
        db.query(AttendanceSession).filter(AttendanceSession.employee_id==trainer_id).count(),
        db.query(CashShift).filter(CashShift.opened_by_employee_id==trainer_id).count(),
        db.query(CommissionLedger).filter(CommissionLedger.employee_id==trainer_id).count(),
    ])
    if references:
        row.status="inactive";row.person.status="inactive";db.commit();return {"deleted":False,"archived":True}
    person=row.person;db.delete(row);db.flush();db.delete(person);db.commit();return {"deleted":True,"archived":False}


def list_pt(db: Session, group_type: str, q: str, page: int, page_size: int):
    if group_type not in ("1:1","1:2","1:3"): group_type="1:1"
    query=db.query(PtEnrollment).options(joinedload(PtEnrollment.customer).joinedload(Customer.person),joinedload(PtEnrollment.coach).joinedload(Employee.person)).filter(PtEnrollment.group_type==group_type)
    if q: query=query.join(PtEnrollment.customer).join(Customer.person).filter(or_(Person.display_name.contains(q),Person.phone.contains(q),Customer.customer_code.contains(q)))
    total=query.count();rows=query.order_by(PtEnrollment.status,PtEnrollment.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    counts={kind:db.query(PtEnrollment).filter(PtEnrollment.group_type==kind).count() for kind in ("1:1","1:2","1:3")}
    return {"items":[pt_data(row) for row in rows],"counts":counts,"pagination":pagination(page,page_size,total)}


def create_pt(db: Session, member_id: int, payload: dict):
    member=db.get(Customer,member_id);coach=db.get(Employee,_as_int(payload.get("coachId")))
    if not member or not coach or coach.status!="active": raise HTTPException(422,"Hội viên hoặc coach không hợp lệ.")
    if db.query(PtEnrollment).filter(PtEnrollment.customer_id==member_id,PtEnrollment.status=="active").first(): raise HTTPException(409,"Hội viên đang có đăng ký PT hoạt động.")
    kind=payload.get("type") if payload.get("type") in ("1:1","1:2","1:3") else "1:1";sessions=max(_as_int(payload.get("totalSessions"),12),1)
    row=PtEnrollment(customer_id=member_id,coach_id=coach.id,group_type=kind,starts_at=_as_date(payload.get("startsAt")) or date.today(),expires_at=_as_date(payload.get("expiresAt")),total_sessions=sessions,remaining_sessions=sessions,schedule_days=", ".join(payload.get("scheduleDays") or []) or None,schedule_time=payload.get("scheduleTime") or None,status="active")
    if row.expires_at and row.expires_at<row.starts_at: raise HTTPException(422,"Ngày hết hạn phải sau ngày bắt đầu.")
    db.add(row);member.status="active";db.commit()
    row=db.query(PtEnrollment).options(joinedload(PtEnrollment.customer).joinedload(Customer.person),joinedload(PtEnrollment.coach).joinedload(Employee.person)).get(row.id);return pt_data(row)


def update_pt(db: Session, enrollment_id: int, payload: dict):
    row=db.query(PtEnrollment).options(joinedload(PtEnrollment.customer).joinedload(Customer.person),joinedload(PtEnrollment.coach).joinedload(Employee.person)).filter(PtEnrollment.id==enrollment_id).first()
    if not row: raise HTTPException(404,"Không tìm thấy đăng ký PT.")
    if payload.get("coachId"):
        coach=db.get(Employee,_as_int(payload["coachId"]));
        if not coach or coach.status!="active": raise HTTPException(422,"Coach không hợp lệ.")
        row.coach_id=coach.id
    if payload.get("type") in ("1:1","1:2","1:3"): row.group_type=payload["type"]
    if "startsAt" in payload: row.starts_at=_as_date(payload["startsAt"]) or row.starts_at
    if "expiresAt" in payload: row.expires_at=_as_date(payload["expiresAt"])
    if "totalSessions" in payload: row.total_sessions=max(_as_int(payload["totalSessions"],1),1)
    if "remainingSessions" in payload: row.remaining_sessions=min(max(_as_int(payload["remainingSessions"],0),0),row.total_sessions)
    if "scheduleDays" in payload: row.schedule_days=", ".join(payload["scheduleDays"] or []) or None
    if "scheduleTime" in payload: row.schedule_time=payload["scheduleTime"] or None
    if payload.get("status") in ("active","completed","inactive"): row.status=payload["status"]
    if row.expires_at and row.expires_at<row.starts_at: raise HTTPException(422,"Ngày hết hạn phải sau ngày bắt đầu.")
    db.commit();db.refresh(row);return pt_data(row)


def checkin_candidates(db: Session, q: str):
    if not q.strip(): return []
    rows=db.query(Customer).options(joinedload(Customer.person),joinedload(Customer.memberships).joinedload(Membership.package)).join(Customer.person).filter(or_(Person.display_name.contains(q),Person.phone.contains(q),Customer.customer_code.contains(q),Customer.mbs_card_code.contains(q))).limit(12).all()
    result=[]
    for member in rows:
        memberships=[m for m in member.memberships if not m.package.is_pt and m.status=="active"]
        current=sorted(memberships,key=lambda x:x.expires_at or date.max,reverse=True)[0] if memberships else None
        eligible=member.status=="active" and bool(current) and (not current.expires_at or current.expires_at>=date.today())
        result.append({"id":member.id,"code":member.customer_code,"name":member.person.display_name,"phone":member.person.phone,"membership":current.package.name if current else None,"expiresAt":current.expires_at.isoformat() if current and current.expires_at else None,"eligible":eligible,"reason":None if eligible else "Gói tập không hoạt động hoặc đã hết hạn."})
    return result


def recent_checkins(db: Session, limit=30):
    rows=db.query(AttendanceSession).options(joinedload(AttendanceSession.customer).joinedload(Customer.person)).order_by(AttendanceSession.checked_in_at.desc()).limit(limit).all()
    return [{"id":row.id,"memberId":row.customer_id,"memberName":row.customer.person.display_name if row.customer else None,"memberCode":row.customer.customer_code if row.customer else None,"checkedInAt":row.checked_in_at.isoformat(),"checkedOutAt":row.checked_out_at.isoformat() if row.checked_out_at else None,"result":row.result,"status":row.status} for row in rows]


def create_checkin(db: Session, payload: dict):
    member_id=_as_int(payload.get("memberId"));member=db.get(Customer,member_id)
    if not member: raise HTTPException(404,"Không tìm thấy hội viên.")
    if db.query(AttendanceSession).filter(AttendanceSession.customer_id==member_id,AttendanceSession.status=="open").first(): raise HTTPException(409,"Hội viên đã check-in và chưa check-out.")
    current=db.query(Membership).options(joinedload(Membership.package)).join(Membership.package).filter(Membership.customer_id==member_id,Membership.status=="active",ServicePackage.is_pt==False,or_(Membership.expires_at==None,Membership.expires_at>=date.today())).first()
    if member.status!="active" or not current: raise HTTPException(422,"Hội viên không có gói tập còn hiệu lực.")
    row=AttendanceSession(customer_id=member_id,checked_in_at=datetime.utcnow(),source="manual",result="allowed",status="open",note=payload.get("note") or None);db.add(row);db.commit();return {"id":row.id,"checkedInAt":row.checked_in_at.isoformat()}


def checkout(db: Session, session_id: int):
    row=db.get(AttendanceSession,session_id)
    if not row: raise HTTPException(404,"Không tìm thấy phiên check-in.")
    if row.status!="open": raise HTTPException(409,"Phiên này đã được check-out.")
    row.checked_out_at=datetime.utcnow();row.status="closed";db.commit();return {"ok":True}


def list_payments(db: Session, q: str, method: str, date_from: str, date_to: str, page: int, page_size: int):
    query=db.query(Payment).options(joinedload(Payment.customer).joinedload(Customer.person),joinedload(Payment.membership).joinedload(Membership.package))
    if q: query=query.join(Payment.customer).join(Customer.person).filter(or_(Person.display_name.contains(q),Payment.payment_no.contains(q),Customer.customer_code.contains(q)))
    if method and method!="all": query=query.filter(Payment.method==method)
    if date_from: query=query.filter(Payment.paid_at>=datetime.combine(_as_date(date_from),datetime.min.time()))
    if date_to: query=query.filter(Payment.paid_at<=datetime.combine(_as_date(date_to),datetime.max.time()))
    total=query.count();rows=query.order_by(Payment.paid_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"items":[payment_data(row) for row in rows],"pagination":pagination(page,page_size,total)}


def settings(db: Session):
    devices=db.query(Device).options(joinedload(Device.branch)).order_by(Device.id).all();accounts=db.query(BankAccount).order_by(BankAccount.id).all();branches=db.query(Branch).order_by(Branch.id).all()
    return {"branches":[{"id":r.id,"code":r.code,"name":r.name,"address":r.address,"status":r.status} for r in branches],"bankAccounts":[{"id":r.id,"bank":r.bank_name,"accountName":r.account_name,"accountNumber":r.account_number,"visibility":r.visibility,"status":r.status} for r in accounts],"devices":[{"id":r.id,"code":r.code,"name":r.name,"model":r.model,"ip":r.ip_address,"purpose":r.purpose,"status":r.status,"pendingJobs":r.pending_jobs,"errors24h":r.errors_24h,"branch":r.branch.name if r.branch else None,"lastHeartbeat":r.last_heartbeat_at.isoformat() if r.last_heartbeat_at else None} for r in devices]}
