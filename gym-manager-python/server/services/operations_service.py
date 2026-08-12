from datetime import date, datetime, timedelta
import secrets

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ..models import (
    Appointment, AttendanceSession, BankAccount, CashShift, CommissionLedger,
    Customer, DahCustomerIdentity, Device, Employee, EmployeeJobTitle, Membership, Payment, PaymentReceipt, Person, PtEnrollment, PtEnrollmentCoach, PtGroup,
    ServicePackage, User,
)
from .audit_service import record_audit
from .dah_service import DAH_MODEL, HEARTBEAT_TIMEOUT_SECONDS
from .serializers import employee_data, pagination, payment_data, pt_data
from .training_schedule import normalize_schedule, schedule_storage
from ..timeutils import utc_now

DEFAULT_JOB_TITLES = ("Sale", "Coach", "Marketing")
DEFAULT_PT_TITLES = {"Coach"}


def _as_int(value, default=None):
    try: return int(value) if value not in (None, "") else default
    except (TypeError, ValueError): return default


def _as_date(value):
    return date.fromisoformat(value) if value else None


def _job_title(value, default="Coach"):
    title = str(value or "").strip()
    if not title:
        return default
    return title[:80]


def _bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _bank_account_data(row: BankAccount):
    return {
        "id": row.id,
        "code": row.code,
        "bank": row.bank_name,
        "accountName": row.account_name,
        "accountNumber": row.account_number,
        "visibility": row.visibility,
        "status": row.status,
    }


def _job_title_data(row: EmployeeJobTitle):
    return {
        "id": row.id,
        "name": row.name,
        "isPtRole": row.is_pt_role,
        "active": row.is_active,
    }


def _device_online(row: Device | None):
    return bool(
        row and row.last_heartbeat_at and
        row.last_heartbeat_at >= utc_now() - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)
    )


def _primary_dah_device(db: Session):
    row = (
        db.query(Device)
        .filter(or_(Device.model == DAH_MODEL, Device.code.like("DAH-%"), Device.code == DAH_MODEL))
        .order_by(Device.last_heartbeat_at.desc(), Device.id.desc())
        .first()
    )
    if row:
        row.name = DAH_MODEL
        row.model = DAH_MODEL
        row.status = "online" if _device_online(row) else "offline"
        return row
    row = Device(
        code=DAH_MODEL,
        name=DAH_MODEL,
        model=DAH_MODEL,
        purpose="shared",
        status="offline",
    )
    db.add(row)
    db.flush()
    return row


def device_data(row: Device):
    online = _device_online(row)
    row.status = "online" if online else "offline"
    return {
        "id": row.id,
        "code": row.code,
        "name": DAH_MODEL,
        "model": DAH_MODEL,
        "ip": row.ip_address,
        "purpose": row.purpose,
        "status": row.status,
        "pendingJobs": row.pending_jobs,
        "errors24h": row.errors_24h,
        "lastHeartbeat": row.last_heartbeat_at.isoformat() if row.last_heartbeat_at else None,
        "heartbeatTimeoutSeconds": HEARTBEAT_TIMEOUT_SECONDS,
    }


def ensure_employee_job_titles(db: Session):
    existing_names = {
        name for (name,) in db.query(EmployeeJobTitle.name).all()
    }
    names = set(DEFAULT_JOB_TITLES) if not existing_names else set()
    names.update(
        title for (title,) in db.query(Employee.job_title)
        .filter(Employee.status == "active", Employee.job_title.is_not(None), Employee.job_title != "")
        .distinct()
        .all()
        if title
    )
    for name in sorted(names, key=str.casefold):
        normalized = _job_title(name, default="")
        if normalized and normalized not in existing_names:
            db.add(EmployeeJobTitle(
                name=normalized,
                is_pt_role=normalized in DEFAULT_PT_TITLES or "pt" in normalized.lower(),
                is_active=True,
            ))
            existing_names.add(normalized)
    db.flush()


def employee_job_titles(db: Session):
    ensure_employee_job_titles(db)
    return db.query(EmployeeJobTitle).filter(EmployeeJobTitle.is_active == True).order_by(EmployeeJobTitle.name).all()


def pt_role_names(db: Session):
    return {row.name for row in employee_job_titles(db) if row.is_pt_role}


def list_trainers(db: Session, q: str, page: int, page_size: int, title: str = "all"):
    ensure_employee_job_titles(db)
    pt_titles = pt_role_names(db)
    query = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.status == "active")
    if q: query = query.join(Employee.person).filter(or_(Person.display_name.contains(q), Person.phone.contains(q), Employee.employee_code.contains(q), Employee.job_title.contains(q)))
    if title and title != "all":
        query = query.filter(Employee.job_title == title)
    total = query.count(); rows = query.order_by(Employee.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    ids = [row.id for row in rows]
    registered_counts = dict(db.query(PtEnrollmentCoach.coach_id, func.count(func.distinct(PtEnrollment.customer_id))).join(PtEnrollment).filter(PtEnrollmentCoach.coach_id.in_(ids)).group_by(PtEnrollmentCoach.coach_id).all()) if ids else {}
    active_counts = dict(db.query(PtEnrollmentCoach.coach_id, func.count(func.distinct(PtEnrollment.customer_id))).join(PtEnrollment).filter(PtEnrollmentCoach.coach_id.in_(ids), PtEnrollment.status == "active", or_(PtEnrollment.expires_at == None, PtEnrollment.expires_at >= date.today())).group_by(PtEnrollmentCoach.coach_id).all()) if ids else {}
    expired_counts = dict(db.query(PtEnrollmentCoach.coach_id, func.count(func.distinct(PtEnrollment.customer_id))).join(PtEnrollment).filter(PtEnrollmentCoach.coach_id.in_(ids), or_(PtEnrollment.expires_at < date.today(), PtEnrollment.status.in_(("completed", "inactive")))).group_by(PtEnrollmentCoach.coach_id).all()) if ids else {}
    items=[]
    identities = {
        row.employee_id: row for row in db.query(DahCustomerIdentity)
        .filter(DahCustomerIdentity.employee_id.in_(ids))
        .all()
    } if ids else {}
    for row in rows:
        item=employee_data(row)
        item["isPtRole"] = row.job_title in pt_titles
        item["registeredPtClients"] = registered_counts.get(row.id, 0) if item["isPtRole"] else None
        item["activePtClients"] = active_counts.get(row.id, 0) if item["isPtRole"] else None
        item["expiredPtClients"] = expired_counts.get(row.id, 0) if item["isPtRole"] else None
        identity = identities.get(row.id)
        item["dahIdentity"] = {
            "personUuid": identity.person_uuid,
            "personId": identity.person_id,
            "faceName": identity.face_name,
            "lastSeenAt": identity.last_seen_at.isoformat() if identity.last_seen_at else None,
        } if identity else None
        items.append(item)
    return {"items":items,"pagination":pagination(page,page_size,total),"jobTitles":[_job_title_data(row) for row in employee_job_titles(db)]}


def employee_attendance(db: Session, day: str = ""):
    target = _as_date(day) or date.today()
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    rows = (
        db.query(AttendanceSession)
        .options(joinedload(AttendanceSession.employee).joinedload(Employee.person))
        .filter(
            AttendanceSession.employee_id.is_not(None),
            AttendanceSession.checked_in_at >= start,
            AttendanceSession.checked_in_at < end,
        )
        .order_by(AttendanceSession.checked_in_at.asc(), AttendanceSession.id.asc())
        .all()
    )
    items = []
    shift_numbers = {}
    for row in rows:
        employee = row.employee
        shift_numbers[row.employee_id] = shift_numbers.get(row.employee_id, 0) + 1
        checked_in = row.checked_in_at
        checked_out = row.checked_out_at
        duration_minutes = None
        if checked_in and checked_out:
            duration_minutes = max(int((checked_out - checked_in).total_seconds() // 60), 0)
        items.append({
            "id": row.id,
            "date": target.isoformat(),
            "employeeId": row.employee_id,
            "employeeCode": employee.employee_code if employee else None,
            "employeeName": employee.person.display_name if employee and employee.person else None,
            "phone": employee.person.phone if employee and employee.person else None,
            "title": employee.job_title if employee else None,
            "shiftNo": shift_numbers[row.employee_id],
            "checkedInAt": checked_in.isoformat() if checked_in else None,
            "checkedOutAt": checked_out.isoformat() if checked_out else None,
            "durationMinutes": duration_minutes,
            "source": row.source,
            "status": row.status,
        })
    return {"date": target.isoformat(), "items": items}


def create_trainer(db: Session, payload: dict, actor: User | None = None):
    name=str(payload.get("name","")).strip()
    if not name: raise HTTPException(422,"Tên nhân viên là bắt buộc.")
    person=Person(display_name=name,phone=payload.get("phone") or None,email=payload.get("email") or None,status="active",biometric_consent_status="not_requested")
    db.add(person);db.flush()
    row=Employee(person_id=person.id,employee_code=f"TMP-{secrets.token_hex(4)}",job_title=_job_title(payload.get("title")),base_salary=0,status="active")
    db.add(row);db.flush();row.employee_code=f"EMP-{row.id:05d}"
    record_audit(db, actor, "create", "employee", row.id, f"Thêm nhân viên {name}", details={"code": row.employee_code, "title": row.job_title})
    db.commit();db.refresh(row)
    return employee_data(row)


def update_trainer(db: Session, trainer_id: int, payload: dict, actor: User | None = None):
    row=db.query(Employee).options(joinedload(Employee.person)).filter(Employee.id==trainer_id).first()
    if not row: raise HTTPException(404,"Không tìm thấy nhân viên.")
    if "name" in payload: row.person.display_name=str(payload["name"]).strip() or row.person.display_name
    if "phone" in payload: row.person.phone=payload["phone"] or None
    if "email" in payload: row.person.email=payload["email"] or None
    if "title" in payload: row.job_title=_job_title(payload["title"], default="")
    record_audit(db, actor, "update", "employee", row.id, f"Cập nhật nhân viên {row.person.display_name}", details={"fields": list(payload.keys())})
    db.commit();return employee_data(row)


def delete_trainer(db: Session, trainer_id: int, actor: User | None = None):
    row=db.query(Employee).options(joinedload(Employee.person)).filter(Employee.id==trainer_id).first()
    if not row: raise HTTPException(404,"Không tìm thấy nhân viên.")
    references=sum([
        db.query(Customer).filter(Customer.sales_employee_id==trainer_id).count(),
        db.query(Membership).filter(or_(Membership.sale_online_employee_id==trainer_id,Membership.direct_sales_employee_id==trainer_id,Membership.pt_converter_employee_id==trainer_id)).count(),
        db.query(PtEnrollmentCoach).filter(PtEnrollmentCoach.coach_id==trainer_id).count(),
        db.query(PtGroup).filter(PtGroup.coach_id==trainer_id).count(),
        db.query(Appointment).filter(or_(Appointment.employee_id==trainer_id,Appointment.support_employee_id==trainer_id)).count(),
        db.query(AttendanceSession).filter(AttendanceSession.employee_id==trainer_id).count(),
        db.query(CashShift).filter(CashShift.opened_by_employee_id==trainer_id).count(),
        db.query(CommissionLedger).filter(CommissionLedger.employee_id==trainer_id).count(),
    ])
    if references:
        row.status="inactive";row.person.status="inactive"
        record_audit(db, actor, "archive", "employee", row.id, f"Lưu trữ nhân viên {row.person.display_name}", details={"references": references})
        db.commit();return {"deleted":False,"archived":True}
    person=row.person
    record_audit(db, actor, "delete", "employee", row.id, f"Xóa nhân viên {row.person.display_name}")
    db.delete(row);db.flush();db.delete(person);db.commit();return {"deleted":True,"archived":False}


def list_pt(db: Session, group_type: str, q: str, assignment: str, page: int, page_size: int):
    if group_type not in ("1:1","1:2","1:3"): group_type="1:1"
    query=db.query(PtEnrollment).options(joinedload(PtEnrollment.customer).joinedload(Customer.person),joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person)).filter(PtEnrollment.group_type==group_type)
    if q: query=query.join(PtEnrollment.customer).join(Customer.person).filter(or_(Person.display_name.contains(q),Person.phone.contains(q),Customer.customer_code.contains(q)))
    if assignment=="unassigned": query=query.filter(~PtEnrollment.coach_assignments.any())
    elif assignment=="assigned": query=query.filter(PtEnrollment.coach_assignments.any())
    total=query.count();rows=query.order_by(PtEnrollment.status,PtEnrollment.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    counts={kind:db.query(PtEnrollment).filter(PtEnrollment.group_type==kind).count() for kind in ("1:1","1:2","1:3")}
    return {"items":[pt_data(row) for row in rows],"counts":counts,"pagination":pagination(page,page_size,total)}


def create_pt(db: Session, member_id: int, payload: dict, actor: User | None = None):
    member=db.get(Customer,member_id)
    if not member: raise HTTPException(422,"Hội viên không hợp lệ.")
    if db.query(PtEnrollment).filter(PtEnrollment.customer_id==member_id,PtEnrollment.status=="active").first(): raise HTTPException(409,"Hội viên đang có đăng ký PT hoạt động.")
    coach_ids=list(dict.fromkeys(_as_int(value) for value in (payload.get("coachIds") or ([payload.get("coachId")] if payload.get("coachId") else []))))
    coach_ids=[value for value in coach_ids if value]
    coaches=db.query(Employee).filter(Employee.id.in_(coach_ids),Employee.status=="active").all() if coach_ids else []
    if len(coaches)!=len(coach_ids): raise HTTPException(422,"Có Coach không hợp lệ hoặc đã ngừng hoạt động.")
    kind=payload.get("type") if payload.get("type") in ("1:1","1:2","1:3") else "1:1";sessions=max(_as_int(payload.get("totalSessions"),12),1)
    schedule_json,schedule_days,schedule_time=schedule_storage(normalize_schedule(payload))
    row=PtEnrollment(customer_id=member_id,coach_id=coach_ids[0] if coach_ids else None,group_type=kind,starts_at=_as_date(payload.get("startsAt")) or date.today(),expires_at=_as_date(payload.get("expiresAt")),total_sessions=sessions,remaining_sessions=sessions,schedule_json=schedule_json,schedule_days=schedule_days,schedule_time=schedule_time,status="active")
    if row.expires_at and row.expires_at<row.starts_at: raise HTTPException(422,"Ngày hết hạn phải sau ngày bắt đầu.")
    db.add(row);db.flush()
    row.coach_assignments=[PtEnrollmentCoach(coach_id=coach_id) for coach_id in coach_ids]
    member.status="active"
    record_audit(db, actor, "create", "pt_enrollment", row.id, f"Đăng ký PT {kind} · {sessions} buổi", customer_id=member_id, details={"coachIds": coach_ids, "expiresAt": row.expires_at})
    db.commit()
    row=db.query(PtEnrollment).options(joinedload(PtEnrollment.customer).joinedload(Customer.person),joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person)).get(row.id);return pt_data(row)


def update_pt(db: Session, enrollment_id: int, payload: dict, actor: User | None = None):
    row=db.query(PtEnrollment).options(joinedload(PtEnrollment.customer).joinedload(Customer.person),joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person)).filter(PtEnrollment.id==enrollment_id).first()
    if not row: raise HTTPException(404,"Không tìm thấy đăng ký PT.")
    if "coachIds" in payload or "coachId" in payload:
        raw_ids=payload.get("coachIds") if "coachIds" in payload else ([payload.get("coachId")] if payload.get("coachId") else [])
        coach_ids=list(dict.fromkeys(value for value in (_as_int(value) for value in (raw_ids or [])) if value))
        coaches=db.query(Employee).filter(Employee.id.in_(coach_ids),Employee.status=="active").all() if coach_ids else []
        if len(coaches)!=len(coach_ids): raise HTTPException(422,"Có Coach không hợp lệ hoặc đã ngừng hoạt động.")
        row.coach_id=coach_ids[0] if coach_ids else None
        row.coach_assignments=[PtEnrollmentCoach(coach_id=coach_id) for coach_id in coach_ids]
    if payload.get("type") in ("1:1","1:2","1:3"): row.group_type=payload["type"]
    if "startsAt" in payload: row.starts_at=_as_date(payload["startsAt"]) or row.starts_at
    if "expiresAt" in payload: row.expires_at=_as_date(payload["expiresAt"])
    if "totalSessions" in payload: row.total_sessions=max(_as_int(payload["totalSessions"],1),1)
    if "remainingSessions" in payload: row.remaining_sessions=min(max(_as_int(payload["remainingSessions"],0),0),row.total_sessions)
    if any(key in payload for key in ("schedule", "scheduleDays", "scheduleTime")):
        row.schedule_json,row.schedule_days,row.schedule_time=schedule_storage(normalize_schedule(payload))
    if payload.get("status") in ("active","completed","inactive"): row.status=payload["status"]
    if row.expires_at and row.expires_at<row.starts_at: raise HTTPException(422,"Ngày hết hạn phải sau ngày bắt đầu.")
    record_audit(db, actor, "update", "pt_enrollment", row.id, "Cập nhật đăng ký PT", customer_id=row.customer_id, details={"fields": list(payload.keys()), "coachIds": [assignment.coach_id for assignment in row.coach_assignments]})
    db.commit();db.refresh(row);return pt_data(row)


def checkin_candidates(db: Session, q: str):
    if not q.strip(): return []
    rows=db.query(Customer).options(joinedload(Customer.person),joinedload(Customer.memberships).joinedload(Membership.package)).join(Customer.person).filter(or_(Person.display_name.contains(q),Person.phone.contains(q),Customer.customer_code.contains(q),Customer.mbs_card_code.contains(q))).limit(12).all()
    result=[]
    for member in rows:
        memberships=[m for m in member.memberships if not m.package.is_pt and m.status=="active"]
        current=sorted(memberships,key=lambda x:x.expires_at or date.max,reverse=True)[0] if memberships else None
        eligible=member.status=="lead" or (member.status=="active" and bool(current) and (not current.expires_at or current.expires_at>=date.today()))
        result.append({"id":member.id,"code":member.customer_code,"name":member.person.display_name,"phone":member.person.phone,"avatarImageData":member.avatar_image_data,"membership":current.package.name if current else None,"expiresAt":current.expires_at.isoformat() if current and current.expires_at else None,"eligible":eligible,"reason":None if eligible else "Gói tập không hoạt động hoặc đã hết hạn."})
    return result


def recent_checkins(db: Session, day: str = "", page: int = 1, page_size: int = 20):
    target = _as_date(day) or date.today()
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    query = (
        db.query(AttendanceSession)
        .options(
            joinedload(AttendanceSession.customer).joinedload(Customer.person),
            joinedload(AttendanceSession.employee).joinedload(Employee.person),
        )
        .filter(AttendanceSession.checked_in_at >= start, AttendanceSession.checked_in_at < end)
    )
    total = query.count()
    active_count = query.filter(AttendanceSession.status == "open").count()
    rows = (
        query.order_by(AttendanceSession.checked_in_at.desc(), AttendanceSession.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    items = [{
        "id":row.id,
        "personType":"employee" if row.employee_id else "member",
        "memberId":row.customer_id,
        "memberName":row.customer.person.display_name if row.customer else None,
        "memberCode":row.customer.customer_code if row.customer else None,
        "memberStatus":row.customer.status if row.customer else None,
        "memberAvatarImageData":row.customer.avatar_image_data if row.customer else None,
        "employeeId":row.employee_id,
        "employeeName":row.employee.person.display_name if row.employee else None,
        "employeeCode":row.employee.employee_code if row.employee else None,
        "checkedInAt":row.checked_in_at.isoformat(),
        "checkedOutAt":row.checked_out_at.isoformat() if row.checked_out_at else None,
        "result":row.result,
        "status":row.status,
    } for row in rows]
    return {
        "date": target.isoformat(),
        "activeCount": active_count,
        "lastEventAt": items[0]["checkedInAt"] if items else None,
        "items": items,
        "pagination": pagination(page, page_size, total),
    }


def create_checkin(db: Session, payload: dict, actor: User | None = None):
    member_id=_as_int(payload.get("memberId"));member=db.get(Customer,member_id)
    if not member: raise HTTPException(404,"Không tìm thấy hội viên.")
    if db.query(AttendanceSession).filter(AttendanceSession.customer_id==member_id,AttendanceSession.status=="open").first(): raise HTTPException(409,"Hội viên đã check-in và chưa check-out.")
    current=db.query(Membership).options(joinedload(Membership.package)).join(Membership.package).filter(Membership.customer_id==member_id,Membership.status=="active",ServicePackage.is_pt==False,or_(Membership.expires_at==None,Membership.expires_at>=date.today())).first()
    if member.status != "lead" and (member.status!="active" or not current): raise HTTPException(422,"Hội viên không có gói tập còn hiệu lực.")
    row=AttendanceSession(customer_id=member_id,checked_in_at=utc_now(),source="manual",result="allowed",status="open",note=payload.get("note") or None);db.add(row);db.flush()
    record_audit(db, actor, "checkin", "attendance", row.id, f"Check-in {member.person.display_name}", customer_id=member_id)
    db.commit();return {"id":row.id,"checkedInAt":row.checked_in_at.isoformat()}


def checkout(db: Session, session_id: int, actor: User | None = None):
    row=db.get(AttendanceSession,session_id)
    if not row: raise HTTPException(404,"Không tìm thấy phiên check-in.")
    if row.status!="open": raise HTTPException(409,"Phiên này đã được check-out.")
    row.checked_out_at=utc_now();row.status="closed"
    record_audit(db, actor, "checkout", "attendance", row.id, "Check-out nhân viên" if row.employee_id else "Check-out hội viên", customer_id=row.customer_id)
    db.commit();return {"ok":True}


def list_payments(db: Session, q: str, method: str, date_from: str, date_to: str, page: int, page_size: int):
    query=db.query(Payment).options(joinedload(Payment.customer).joinedload(Customer.person),joinedload(Payment.membership).joinedload(Membership.package),joinedload(Payment.receipts).joinedload(PaymentReceipt.uploaded_by))
    if q: query=query.join(Payment.customer).join(Customer.person).filter(or_(Person.display_name.contains(q),Payment.payment_no.contains(q),Customer.customer_code.contains(q)))
    if method and method!="all": query=query.filter(Payment.method==method)
    if date_from: query=query.filter(Payment.paid_at>=datetime.combine(_as_date(date_from),datetime.min.time()))
    if date_to: query=query.filter(Payment.paid_at<=datetime.combine(_as_date(date_to),datetime.max.time()))
    total=query.count();rows=query.order_by(Payment.paid_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"items":[payment_data(row) for row in rows],"pagination":pagination(page,page_size,total)}


def settings(db: Session):
    ensure_employee_job_titles(db)
    device = _primary_dah_device(db)
    db.commit()
    accounts=db.query(BankAccount).filter(BankAccount.status != "deleted").order_by(BankAccount.id).all()
    return {
        "jobTitles": [_job_title_data(row) for row in employee_job_titles(db)],
        "bankAccounts":[_bank_account_data(row) for row in accounts],
        "devices":[device_data(device)],
    }


def create_job_title(db: Session, payload: dict, actor: User | None = None):
    name = _job_title(payload.get("name"), default="")
    if not name:
        raise HTTPException(422, "Tên chức vụ là bắt buộc.")
    existing = db.query(EmployeeJobTitle).filter(EmployeeJobTitle.name == name).first()
    if existing:
        if existing.is_active:
            raise HTTPException(409, "Chức vụ này đã tồn tại.")
        existing.is_active = True
        existing.is_pt_role = _bool(payload.get("isPtRole"), existing.is_pt_role)
        record_audit(db, actor, "restore", "job_title", existing.id, f"Khôi phục chức vụ {name}", details={"isPtRole": existing.is_pt_role})
        db.commit()
        return _job_title_data(existing)
    row = EmployeeJobTitle(name=name, is_pt_role=_bool(payload.get("isPtRole")), is_active=True)
    db.add(row); db.flush()
    record_audit(db, actor, "create", "job_title", row.id, f"Thêm chức vụ {name}", details={"isPtRole": row.is_pt_role})
    db.commit(); db.refresh(row)
    return _job_title_data(row)


def update_job_title(db: Session, title_id: int, payload: dict, actor: User | None = None):
    row = db.get(EmployeeJobTitle, title_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy chức vụ.")
    if "name" in payload:
        name = _job_title(payload.get("name"), default="")
        if not name:
            raise HTTPException(422, "Tên chức vụ là bắt buộc.")
        duplicate = db.query(EmployeeJobTitle).filter(EmployeeJobTitle.name == name, EmployeeJobTitle.id != row.id).first()
        if duplicate:
            raise HTTPException(409, "Chức vụ này đã tồn tại.")
        old_name = row.name
        row.name = name
        if payload.get("renameEmployees"):
            db.query(Employee).filter(Employee.job_title == old_name).update({Employee.job_title: name}, synchronize_session=False)
    if "isPtRole" in payload:
        row.is_pt_role = _bool(payload.get("isPtRole"))
    if "active" in payload:
        active = _bool(payload.get("active"), row.is_active)
        if not active and db.query(Employee).filter(Employee.job_title == row.name, Employee.status == "active").count():
            raise HTTPException(409, "Chức vụ đang có nhân viên hoạt động nên chưa thể ẩn.")
        row.is_active = active
    record_audit(db, actor, "update", "job_title", row.id, f"Cập nhật chức vụ {row.name}", details={"fields": list(payload.keys()), "isPtRole": row.is_pt_role})
    db.commit(); db.refresh(row)
    return _job_title_data(row)


def delete_job_title(db: Session, title_id: int, actor: User | None = None):
    row = db.get(EmployeeJobTitle, title_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy chức vụ.")
    active_employees = db.query(Employee).filter(Employee.job_title == row.name, Employee.status == "active").count()
    if active_employees:
        raise HTTPException(409, f"Chức vụ đang có {active_employees} nhân viên hoạt động nên chưa thể xóa.")
    row.is_active = False
    row.is_pt_role = False
    record_audit(db, actor, "delete", "job_title", row.id, f"Xóa chức vụ {row.name}")
    db.commit()
    return {"deleted": True, "id": row.id}


def create_bank_account(db: Session, payload: dict, actor: User | None = None):
    bank = str(payload.get("bank") or "").strip()
    account_name = str(payload.get("accountName") or "").strip()
    account_number = str(payload.get("accountNumber") or "").strip()
    if not bank or not account_name or not account_number:
        raise HTTPException(422, "Ngân hàng, chủ tài khoản và số tài khoản là bắt buộc.")
    existing = db.query(BankAccount).filter(BankAccount.account_number == account_number).first()
    if existing and existing.status != "deleted":
        raise HTTPException(409, "Số tài khoản này đã tồn tại.")
    if existing:
        existing.bank_name = bank[:120]
        existing.account_name = account_name[:160]
        existing.visibility = payload.get("visibility") if payload.get("visibility") in ("public", "private") else "public"
        existing.status = payload.get("status") if payload.get("status") in ("active", "inactive") else "active"
        record_audit(db, actor, "restore", "bank_account", existing.id, f"Khôi phục tài khoản nhận tiền {bank}", details={"accountNumber": account_number})
        db.commit(); db.refresh(existing)
        return _bank_account_data(existing)
    row = BankAccount(
        code=f"BANK-{secrets.token_hex(4).upper()}",
        bank_name=bank[:120],
        account_name=account_name[:160],
        account_number=account_number[:80],
        visibility=payload.get("visibility") if payload.get("visibility") in ("public", "private") else "public",
        status=payload.get("status") if payload.get("status") in ("active", "inactive") else "active",
    )
    db.add(row); db.flush()
    record_audit(db, actor, "create", "bank_account", row.id, f"Thêm tài khoản nhận tiền {bank}", details={"accountNumber": account_number})
    db.commit(); db.refresh(row)
    return _bank_account_data(row)


def update_bank_account(db: Session, account_id: int, payload: dict, actor: User | None = None):
    row = db.get(BankAccount, account_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy tài khoản nhận tiền.")
    if "bank" in payload:
        row.bank_name = str(payload.get("bank") or "").strip()[:120] or row.bank_name
    if "accountName" in payload:
        row.account_name = str(payload.get("accountName") or "").strip()[:160] or row.account_name
    if "accountNumber" in payload:
        account_number = str(payload.get("accountNumber") or "").strip()
        if not account_number:
            raise HTTPException(422, "Số tài khoản là bắt buộc.")
        duplicate = db.query(BankAccount).filter(BankAccount.account_number == account_number, BankAccount.id != row.id).first()
        if duplicate:
            raise HTTPException(409, "Số tài khoản này đã tồn tại.")
        row.account_number = account_number[:80]
    if payload.get("visibility") in ("public", "private"):
        row.visibility = payload["visibility"]
    if payload.get("status") in ("active", "inactive"):
        row.status = payload["status"]
    record_audit(db, actor, "update", "bank_account", row.id, f"Cập nhật tài khoản nhận tiền {row.bank_name}", details={"fields": list(payload.keys())})
    db.commit(); db.refresh(row)
    return _bank_account_data(row)


def delete_bank_account(db: Session, account_id: int, actor: User | None = None):
    row = db.get(BankAccount, account_id)
    if not row or row.status == "deleted":
        raise HTTPException(404, "Không tìm thấy tài khoản nhận tiền.")
    payments = db.query(Payment).filter(Payment.bank_account_id == account_id).count()
    record_audit(db, actor, "delete", "bank_account", row.id, f"Xóa tài khoản nhận tiền {row.bank_name}", details={"payments": payments})
    if payments:
        row.status = "deleted"
        db.commit()
        return {"deleted": True, "archived": True, "id": row.id}
    db.delete(row)
    db.commit()
    return {"deleted": True, "archived": False, "id": account_id}
