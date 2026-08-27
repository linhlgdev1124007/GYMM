from datetime import UTC, date, datetime, timedelta
import secrets

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, load_only

from ..models import (
    Appointment, AttendanceSession, BankAccount, CashShift, CommissionLedger,
    Customer, DahCustomerIdentity, DahWebhookEvent, Device, Employee, EmployeeJobTitle, EmployeeShiftOverride, EmployeeShiftSchedule, Membership, Payment, PaymentReceipt, Person, PtDebtInstallment, PtEnrollment, PtEnrollmentCoach, PtGroup, PtSessionLog,
    ServicePackage, User,
)
from .audit_service import record_audit
from .checkin_speech_service import queue_checkin_speech, speech_settings_data
from .dah_service import DAH_MODEL, HEARTBEAT_TIMEOUT_SECONDS
from .employee_shift_attendance import create_employee_shift, create_employee_shifts_bulk, delete_employee_shift, import_employee_shifts, list_employee_shifts, list_employee_shifts_week, preview_employee_shift_excel, replace_employee_shifts_week, update_employee_shift
from .membership_lifecycle import activate_customer_first_checkin
from .serializers import employee_data, membership_data, pagination, payment_data, pt_data
from .training_schedule import WEEKDAYS, normalize_schedule, schedule_data, schedule_storage
from ..timeutils import VIETNAM_TZ, utc_iso, utc_now, utc_vietnam_date, vietnam_day_utc_bounds, vietnam_today

DEFAULT_JOB_TITLES = ("Sale", "Coach", "Marketing")
DEFAULT_PT_TITLES = {"Coach"}
PT_AUDIT_FIELD_LABELS = {
    "coachIds": "Coach phụ trách",
    "coachId": "Coach phụ trách",
    "packageName": "Gói PT/BT",
    "type": "Nhóm PT",
    "startsAt": "Ngày bắt đầu",
    "expiresAt": "Ngày hết hạn",
    "totalSessions": "Tổng buổi",
    "remainingSessions": "Buổi còn lại",
    "schedule": "Lịch tập",
    "scheduleDays": "Ngày tập",
    "scheduleTime": "Giờ tập",
    "finalPrice": "Giá trị gói PT",
    "paidAmount": "Đã thu PT",
    "debtAmount": "Công nợ PT",
    "debtInstallments": "Hạn công nợ PT",
    "status": "Trạng thái",
}


def _as_int(value, default=None):
    try: return int(value) if value not in (None, "") else default
    except (TypeError, ValueError): return default


def _money(value, default=0):
    if value in (None, ""):
        return float(default or 0)
    try:
        return max(float(str(value).replace(",", "")), 0)
    except (TypeError, ValueError):
        return float(default or 0)


def _as_date(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Ngày không hợp lệ. Vui lòng dùng định dạng YYYY-MM-DD.") from exc


def _as_time(value):
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%H:%M").time()
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Giờ không hợp lệ. Vui lòng dùng định dạng HH:MM.") from exc


def _as_datetime(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    try:
        return datetime.fromisoformat(str(value))
    except (TypeError, ValueError) as exc:
        raise HTTPException(422, "Thời điểm không hợp lệ. Vui lòng dùng định dạng ISO.") from exc


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


def _audit_value(value):
    if value in (None, ""):
        return "—"
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, list):
        return ", ".join(str(item) for item in value) if value else "—"
    return str(value)


def _attendance_iso(value, source: str | None):
    if not value:
        return None
    return value.isoformat() if source == "dah" else utc_iso(value)


def _member_access_warning(db: Session, member: Customer | None) -> str | None:
    if not member:
        return None
    today = vietnam_today()
    membership = (
        db.query(Membership)
        .join(ServicePackage)
        .filter(
            Membership.customer_id == member.id,
            ServicePackage.is_pt == False,
        )
        .order_by(Membership.registered_at.desc(), Membership.id.desc())
        .first()
    )
    if not membership:
        return "Khách tiềm năng chưa có gói tập."
    if membership.status == "pending":
        return "Gói đang chờ kích hoạt."
    if membership.status == "suspended":
        return "Gói đang tạm dừng."
    if membership.status == "frozen":
        return "Gói đang bảo lưu."
    if membership.status == "cancelled":
        return "Gói đã hủy."
    if membership.expires_at and membership.expires_at < today:
        return "Gói đã hết hạn."
    if membership.starts_at and membership.starts_at > today:
        return "Gói chưa tới ngày bắt đầu."
    if member.status == "lead":
        return "Hội viên chưa ở trạng thái hoạt động."
    return None


def _membership_access_warning(member_status: str | None, membership: Membership | None) -> str | None:
    if not membership:
        return "Khách tiềm năng chưa có gói tập."
    today = vietnam_today()
    if membership.status == "pending":
        return "Gói đang chờ kích hoạt."
    if membership.status == "suspended":
        return "Gói đang tạm dừng."
    if membership.status == "frozen":
        return "Gói đang bảo lưu."
    if membership.status == "cancelled":
        return "Gói đã hủy."
    if membership.expires_at and membership.expires_at < today:
        return "Gói đã hết hạn."
    if membership.starts_at and membership.starts_at > today:
        return "Gói chưa tới ngày bắt đầu."
    if member_status == "lead":
        return "Hội viên chưa ở trạng thái hoạt động."
    return None


def _member_access_warnings(db: Session, members: list[Customer]) -> dict[int, str | None]:
    if not members:
        return {}
    member_statuses = {row.id: row.status for row in members}
    memberships = (
        db.query(Membership)
        .join(ServicePackage)
        .filter(Membership.customer_id.in_(member_statuses), ServicePackage.is_pt == False)
        .order_by(Membership.customer_id.asc(), Membership.registered_at.desc(), Membership.id.desc())
        .all()
    )
    latest_memberships = {}
    for membership in memberships:
        latest_memberships.setdefault(membership.customer_id, membership)
    return {
        member_id: _membership_access_warning(status, latest_memberships.get(member_id))
        for member_id, status in member_statuses.items()
    }


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
        "lastHeartbeat": utc_iso(row.last_heartbeat_at),
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
            "lastSeenAt": utc_iso(identity.last_seen_at),
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
            "scheduledStartAt": _attendance_iso(row.scheduled_start_at, row.source),
            "scheduledEndAt": _attendance_iso(row.scheduled_end_at, row.source),
            "checkedInAt": _attendance_iso(checked_in, row.source),
            "checkedOutAt": _attendance_iso(checked_out, row.source),
            "durationMinutes": duration_minutes,
            "source": row.source,
            "status": row.status,
        })
    return {"date": target.isoformat(), "items": items}


def _week_start(value: date):
    return value - timedelta(days=value.weekday())


def _attendance_report_range(range_type: str = "today", day: str = "", week_start: str = ""):
    today = vietnam_today()
    kind = (range_type or "today").strip()
    if kind == "yesterday":
        start = today - timedelta(days=1)
        return start, start
    if kind == "date":
        start = _as_date(day) or today
        return start, start
    if kind == "this_week":
        start = _week_start(today)
        return start, start + timedelta(days=6)
    if kind == "last_week":
        start = _week_start(today) - timedelta(days=7)
        return start, start + timedelta(days=6)
    if kind == "week":
        start = _week_start(_as_date(week_start) or today)
        return start, start + timedelta(days=6)
    return today, today


def _event_data(row: DahWebhookEvent):
    return {
        "id": row.id,
        "eventKey": row.event_key,
        "eventTime": _attendance_iso(row.event_time, "dah"),
        "action": row.action,
        "status": row.status,
        "verifyStatus": row.verify_status,
        "similarity": row.similarity,
        "attendanceSessionId": row.attendance_session_id,
        "note": row.note,
    }


def approve_employee_shift_override(db: Session, shift_id: int, payload: dict, actor: User | None = None):
    schedule = (
        db.query(EmployeeShiftSchedule)
        .options(joinedload(EmployeeShiftSchedule.employee).joinedload(Employee.person))
        .filter(EmployeeShiftSchedule.id == shift_id, EmployeeShiftSchedule.status == "active")
        .first()
    )
    if not schedule:
        raise HTTPException(404, "Không tìm thấy ca làm.")
    work_date = _as_date(payload.get("workDate")) or schedule.work_date
    starts = _as_time(payload.get("startTime"))
    ends = _as_time(payload.get("endTime"))
    if not starts or not ends:
        raise HTTPException(422, "Giờ bắt đầu và kết thúc ca đổi là bắt buộc.")
    approved_start_at = datetime.combine(work_date, starts)
    approved_end_at = datetime.combine(work_date, ends)
    if approved_end_at <= approved_start_at:
        raise HTTPException(422, "Giờ kết thúc phải sau giờ bắt đầu.")
    reason = str(payload.get("reason") or "").strip()[:255] or None
    now = utc_now()
    (
        db.query(EmployeeShiftOverride)
        .filter(
            EmployeeShiftOverride.original_shift_schedule_id == schedule.id,
            EmployeeShiftOverride.status == "approved",
        )
        .update({"status": "superseded", "updated_at": now}, synchronize_session=False)
    )
    row = EmployeeShiftOverride(
        employee_id=schedule.employee_id,
        original_shift_schedule_id=schedule.id,
        work_date=work_date,
        original_start_at=schedule.starts_at,
        original_end_at=schedule.ends_at,
        approved_start_at=approved_start_at,
        approved_end_at=approved_end_at,
        status="approved",
        reason=reason,
        requested_by_user_id=actor.id if actor else None,
        approved_by_user_id=actor.id if actor else None,
        approved_at=now,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    employee_name = schedule.employee.person.display_name if schedule.employee and schedule.employee.person else schedule.employee_id
    record_audit(
        db,
        actor,
        "approve",
        "employee_shift_override",
        row.id,
        f"Duyệt đổi ca {employee_name} {schedule.work_date.isoformat()}",
        details={
            "employeeId": schedule.employee_id,
            "shiftId": schedule.id,
            "original": [schedule.starts_at.isoformat(), schedule.ends_at.isoformat()],
            "approved": [approved_start_at.isoformat(), approved_end_at.isoformat()],
            "reason": reason,
        },
    )
    db.commit()
    db.refresh(row)
    return {
        "id": row.id,
        "shiftId": schedule.id,
        "workDate": row.work_date.isoformat(),
        "approvedStartAt": _attendance_iso(row.approved_start_at, "dah"),
        "approvedEndAt": _attendance_iso(row.approved_end_at, "dah"),
        "startTime": row.approved_start_at.strftime("%H:%M"),
        "endTime": row.approved_end_at.strftime("%H:%M"),
        "reason": row.reason,
        "status": row.status,
    }


def update_employee_shift_attendance_events(db: Session, shift_id: int, payload: dict, actor: User | None = None):
    schedule = (
        db.query(EmployeeShiftSchedule)
        .options(joinedload(EmployeeShiftSchedule.employee).joinedload(Employee.person))
        .filter(EmployeeShiftSchedule.id == shift_id, EmployeeShiftSchedule.status == "active")
        .first()
    )
    if not schedule:
        raise HTTPException(404, "Không tìm thấy ca làm.")
    checkin_event_id = _as_int(payload.get("checkinEventId"))
    checkout_event_id = _as_int(payload.get("checkoutEventId"))
    if not checkin_event_id:
        raise HTTPException(422, "Vui lòng chọn event check-in.")
    if checkout_event_id and checkout_event_id == checkin_event_id:
        raise HTTPException(422, "Event check-out phải khác event check-in.")
    day_start = datetime.combine(schedule.work_date, datetime.min.time())
    day_end = day_start + timedelta(days=1)
    event_ids = [checkin_event_id] + ([checkout_event_id] if checkout_event_id else [])
    events = (
        db.query(DahWebhookEvent)
        .filter(
            DahWebhookEvent.id.in_(event_ids),
            DahWebhookEvent.employee_id == schedule.employee_id,
            DahWebhookEvent.event_time >= day_start,
            DahWebhookEvent.event_time < day_end,
        )
        .all()
    )
    by_id = {event.id: event for event in events}
    checkin_event = by_id.get(checkin_event_id)
    checkout_event = by_id.get(checkout_event_id) if checkout_event_id else None
    if not checkin_event or (checkout_event_id and not checkout_event):
        raise HTTPException(422, "Event webhook không hợp lệ cho nhân viên/ ngày làm này.")
    if checkout_event and checkout_event.event_time <= checkin_event.event_time:
        raise HTTPException(422, "Event check-out phải sau event check-in.")
    session = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.employee_shift_schedule_id == schedule.id,
            AttendanceSession.employee_id == schedule.employee_id,
            AttendanceSession.source == "dah",
        )
        .order_by(AttendanceSession.id.desc())
        .first()
    )
    old_checked_in_at = session.checked_in_at if session else None
    old_checked_out_at = session.checked_out_at if session else None
    if not session:
        session = AttendanceSession(
            employee_id=schedule.employee_id,
            employee_shift_schedule_id=schedule.id,
            source="dah",
            result="allowed",
        )
        db.add(session)
        db.flush()
    db.query(DahWebhookEvent).filter(DahWebhookEvent.attendance_session_id == session.id).update(
        {DahWebhookEvent.attendance_session_id: None},
        synchronize_session=False,
    )
    session.scheduled_start_at = schedule.starts_at
    session.scheduled_end_at = schedule.ends_at
    session.checked_in_at = checkin_event.event_time
    session.checked_out_at = checkout_event.event_time if checkout_event else None
    session.status = "closed" if checkout_event else "open"
    session.note = f"Admin chỉnh từ webhook · ca {schedule.starts_at.strftime('%H:%M')}-{schedule.ends_at.strftime('%H:%M')}"
    checkin_event.attendance_session_id = session.id
    if checkout_event:
        checkout_event.attendance_session_id = session.id
    employee_name = schedule.employee.person.display_name if schedule.employee and schedule.employee.person else schedule.employee_id
    record_audit(
        db,
        actor,
        "employee_attendance_adjust",
        "attendance",
        session.id,
        f"Chỉnh chấm công ca {employee_name} {schedule.work_date.isoformat()}",
        details={
            "employeeId": schedule.employee_id,
            "shiftId": schedule.id,
            "checkinEventId": checkin_event.id,
            "checkoutEventId": checkout_event.id if checkout_event else None,
            "oldCheckedInAt": old_checked_in_at,
            "oldCheckedOutAt": old_checked_out_at,
            "newCheckedInAt": session.checked_in_at,
            "newCheckedOutAt": session.checked_out_at,
        },
    )
    db.commit()
    return {
        "ok": True,
        "sessionId": session.id,
        "checkedInAt": _attendance_iso(session.checked_in_at, session.source),
        "checkedOutAt": _attendance_iso(session.checked_out_at, session.source),
        "status": session.status,
    }


def employee_shift_report(
    db: Session,
    range_type: str = "today",
    day: str = "",
    week_start: str = "",
    q: str = "",
    title: str = "all",
    status: str = "all",
    shift_kind: str = "all",
    sort: str = "severity",
    page: int = 1,
    page_size: int = 30,
):
    start_date, end_date = _attendance_report_range(range_type, day, week_start)
    start_at = datetime.combine(start_date, datetime.min.time())
    end_at = datetime.combine(end_date + timedelta(days=1), datetime.min.time())
    schedules = (
        db.query(EmployeeShiftSchedule)
        .options(joinedload(EmployeeShiftSchedule.employee).joinedload(Employee.person))
        .filter(
            EmployeeShiftSchedule.work_date >= start_date,
            EmployeeShiftSchedule.work_date <= end_date,
            EmployeeShiftSchedule.status == "active",
        )
        .order_by(EmployeeShiftSchedule.work_date.asc(), EmployeeShiftSchedule.starts_at.asc(), EmployeeShiftSchedule.id.asc())
        .all()
    )
    if not schedules:
        return {
            "rangeType": range_type or "today",
            "dateFrom": start_date.isoformat(),
            "dateTo": end_date.isoformat(),
            "lateGraceMinutes": 10,
            "items": [],
            "rows": [],
            "summary": {
                "employees": 0, "shifts": 0, "onTime": 0, "late": 0,
                "earlyCheckout": 0, "absent": 0, "missingCheckout": 0,
                "upcoming": 0, "pendingReview": 0, "attendanceRate": 0,
                "onTimeRate": 0,
            },
            "filters": {"titles": []},
            "pagination": pagination(page, page_size, 0),
        }

    schedule_ids = [row.id for row in schedules]
    employee_ids = sorted({row.employee_id for row in schedules})
    overrides = (
        db.query(EmployeeShiftOverride)
        .filter(
            EmployeeShiftOverride.original_shift_schedule_id.in_(schedule_ids),
            EmployeeShiftOverride.status == "approved",
        )
        .order_by(EmployeeShiftOverride.approved_at.desc(), EmployeeShiftOverride.id.desc())
        .all()
    )
    override_by_schedule = {}
    for override in overrides:
        if override.original_shift_schedule_id not in override_by_schedule:
            override_by_schedule[override.original_shift_schedule_id] = override
    sessions = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.employee_id.in_(employee_ids),
            or_(
                AttendanceSession.employee_shift_schedule_id.in_(schedule_ids),
                and_(AttendanceSession.checked_in_at >= start_at, AttendanceSession.checked_in_at < end_at),
                and_(AttendanceSession.scheduled_start_at >= start_at, AttendanceSession.scheduled_start_at < end_at),
            ),
            AttendanceSession.source == "dah",
        )
        .order_by(AttendanceSession.checked_in_at.asc(), AttendanceSession.id.asc())
        .all()
    )
    session_by_schedule = {}
    for session in sessions:
        if session.employee_shift_schedule_id and session.employee_shift_schedule_id not in session_by_schedule:
            session_by_schedule[session.employee_shift_schedule_id] = session

    events = (
        db.query(DahWebhookEvent)
        .filter(
            DahWebhookEvent.employee_id.in_(employee_ids),
            DahWebhookEvent.event_time >= start_at,
            DahWebhookEvent.event_time < end_at,
        )
        .order_by(DahWebhookEvent.event_time.asc(), DahWebhookEvent.id.asc())
        .all()
    )
    events_by_employee_day = {}
    events_by_session = {}
    for event in events:
        if event.event_time:
            key = (event.employee_id, event.event_time.date())
            events_by_employee_day.setdefault(key, []).append(event)
        if event.attendance_session_id:
            events_by_session.setdefault(event.attendance_session_id, []).append(event)

    employees = {}
    for schedule in schedules:
        employee = schedule.employee
        override = override_by_schedule.get(schedule.id)
        effective_starts_at = override.approved_start_at if override else schedule.starts_at
        effective_ends_at = override.approved_end_at if override else schedule.ends_at
        effective_work_date = override.work_date if override else schedule.work_date
        if schedule.employee_id not in employees:
            employees[schedule.employee_id] = {
                "employeeId": schedule.employee_id,
                "employeeCode": employee.employee_code if employee else None,
                "employeeName": employee.person.display_name if employee and employee.person else None,
                "title": employee.job_title if employee else None,
                "days": {},
            }
        day_key = effective_work_date.isoformat()
        day_group = employees[schedule.employee_id]["days"].setdefault(day_key, {
            "workDate": day_key,
            "shifts": [],
            "events": [_event_data(event) for event in events_by_employee_day.get((schedule.employee_id, effective_work_date), [])],
        })
        session = session_by_schedule.get(schedule.id)
        checked_in = session.checked_in_at if session else None
        checked_out = session.checked_out_at if session else None
        checkin_status = "not_checked"
        checkin_status_label = "Chưa chấm công"
        checkout_status = "not_checked"
        checkout_status_label = "Chưa chấm công"
        late_minutes = 0
        early_checkout_minutes = 0
        if checked_in:
            late_minutes = max(int((checked_in - effective_starts_at).total_seconds() // 60), 0)
            early_checkout_minutes = max(int((effective_ends_at - checked_out).total_seconds() // 60), 0) if checked_out else 0
            is_late = checked_in > effective_starts_at + timedelta(minutes=10)
            if is_late:
                checkin_status = "late"
                checkin_status_label = "Check-in trễ"
            else:
                checkin_status = "on_time"
                checkin_status_label = "Check-in đúng giờ"
            if checked_out:
                if checked_out < effective_ends_at:
                    checkout_status = "early_checkout"
                    checkout_status_label = "Check-out sớm"
                else:
                    checkout_status = "on_time"
                    checkout_status_label = "Check-out đúng giờ"
            else:
                checkout_status = "missing_checkout"
                checkout_status_label = "Thiếu check-out"
        composite_status = checkin_status
        composite_status_label = checkin_status_label
        if checkin_status == "late" and checkout_status == "early_checkout":
            composite_status = "late_early_checkout"
            composite_status_label = "Trễ · Checkout sớm"
        elif checkout_status == "early_checkout":
            composite_status = "early_checkout"
            composite_status_label = "Checkout sớm"
        day_group["shifts"].append({
            "scheduleId": schedule.id,
            "overrideId": override.id if override else None,
            "sessionId": session.id if session else None,
            "scheduledStartAt": _attendance_iso(schedule.starts_at, "dah"),
            "scheduledEndAt": _attendance_iso(schedule.ends_at, "dah"),
            "approvedStartAt": _attendance_iso(override.approved_start_at, "dah") if override else None,
            "approvedEndAt": _attendance_iso(override.approved_end_at, "dah") if override else None,
            "originalStartTime": schedule.starts_at.strftime("%H:%M"),
            "originalEndTime": schedule.ends_at.strftime("%H:%M"),
            "startTime": effective_starts_at.strftime("%H:%M"),
            "endTime": effective_ends_at.strftime("%H:%M"),
            "hasOverride": bool(override),
            "overrideReason": override.reason if override else None,
            "checkedInAt": _attendance_iso(checked_in, "dah"),
            "checkedOutAt": _attendance_iso(checked_out, "dah"),
            "status": composite_status,
            "statusLabel": composite_status_label,
            "checkinStatus": checkin_status,
            "checkinStatusLabel": checkin_status_label,
            "checkoutStatus": checkout_status,
            "checkoutStatusLabel": checkout_status_label,
            "lateMinutes": late_minutes,
            "earlyCheckoutMinutes": early_checkout_minutes,
            "events": [_event_data(event) for event in events_by_session.get(session.id if session else None, [])],
        })

    items = []
    for employee in employees.values():
        days = list(employee["days"].values())
        days.sort(key=lambda row: row["workDate"])
        employee["days"] = days
        items.append(employee)
    items.sort(key=lambda row: (row["employeeName"] or "", row["employeeId"]))
    now = datetime.now()
    all_rows = []
    severity = {
        "absent": 0,
        "missing_checkout": 1,
        "late_early_checkout": 2,
        "late": 3,
        "early_checkout": 3,
        "awaiting_checkin": 4,
        "in_progress": 5,
        "upcoming": 6,
        "on_time": 7,
    }
    summary = {
        "employees": len(items),
        "shifts": 0,
        "onTime": 0,
        "late": 0,
        "earlyCheckout": 0,
        "absent": 0,
        "missingCheckout": 0,
        "upcoming": 0,
        "pendingReview": 0,
        "attendanceRate": 0,
        "onTimeRate": 0,
    }
    titles = sorted({employee["title"] for employee in items if employee.get("title")})
    for employee in items:
        for day_group in employee["days"]:
            for shift in day_group["shifts"]:
                effective_start = datetime.fromisoformat(shift["approvedStartAt"] or shift["scheduledStartAt"].replace("Z", "+00:00")).replace(tzinfo=None)
                effective_end = datetime.fromisoformat(shift["approvedEndAt"] or shift["scheduledEndAt"].replace("Z", "+00:00")).replace(tzinfo=None)
                display_status = shift["status"]
                display_label = shift["statusLabel"]
                if not shift["checkedInAt"]:
                    if now < effective_start:
                        display_status, display_label = "upcoming", "Chưa đến ca"
                    elif now <= effective_end:
                        display_status, display_label = "awaiting_checkin", "Đang chờ check-in"
                    else:
                        display_status, display_label = "absent", "Vắng mặt"
                elif not shift["checkedOutAt"]:
                    if now > effective_end:
                        display_status, display_label = "missing_checkout", "Thiếu check-out"
                    else:
                        display_status, display_label = "in_progress", "Đang trong ca"
                shift["displayStatus"] = display_status
                shift["displayStatusLabel"] = display_label
                shift["needsReview"] = display_status in {"absent", "missing_checkout", "late", "early_checkout", "late_early_checkout"}
                shift["severityRank"] = severity.get(display_status, 9)
                summary["shifts"] += 1
                if display_status == "on_time":
                    summary["onTime"] += 1
                if shift["checkinStatus"] == "late":
                    summary["late"] += 1
                if shift["checkoutStatus"] == "early_checkout":
                    summary["earlyCheckout"] += 1
                if display_status == "absent":
                    summary["absent"] += 1
                if display_status == "missing_checkout":
                    summary["missingCheckout"] += 1
                if display_status == "upcoming":
                    summary["upcoming"] += 1
                if shift["needsReview"]:
                    summary["pendingReview"] += 1
                all_rows.append({
                    "scheduleId": shift["scheduleId"],
                    "employeeId": employee["employeeId"],
                    "employeeCode": employee["employeeCode"],
                    "employeeName": employee["employeeName"],
                    "title": employee["title"],
                    "workDate": day_group["workDate"],
                    **shift,
                    "dahEvents": day_group["events"],
                    "dayEvents": day_group["events"],
                })
    completed = summary["shifts"] - summary["upcoming"] - sum(1 for row in all_rows if row["displayStatus"] == "awaiting_checkin")
    attended = sum(1 for row in all_rows if row["checkedInAt"])
    summary["attendanceRate"] = min(round((attended / completed) * 100, 1), 100) if completed > 0 else 0
    summary["onTimeRate"] = round((summary["onTime"] / attended) * 100, 1) if attended else 0

    normalized_q = str(q or "").strip().casefold()
    filtered_rows = []
    for row in all_rows:
        if normalized_q and normalized_q not in f'{row["employeeName"] or ""} {row["employeeCode"] or ""}'.casefold():
            continue
        if title not in {"", "all"} and row["title"] != title:
            continue
        if status == "anomaly" and not row["needsReview"]:
            continue
        if status not in {"", "all", "anomaly"}:
            if status == "late" and row["displayStatus"] not in {"late", "late_early_checkout"}:
                continue
            elif status == "early_checkout" and row["displayStatus"] not in {"early_checkout", "late_early_checkout"}:
                continue
            elif status not in {"late", "early_checkout"} and row["displayStatus"] != status:
                continue
        start_hour = int(row["startTime"].split(":", 1)[0])
        row_shift_kind = "morning" if start_hour < 12 else "afternoon" if start_hour < 18 else "night"
        row["shiftKind"] = row_shift_kind
        if shift_kind not in {"", "all"} and row_shift_kind != shift_kind:
            continue
        filtered_rows.append(row)
    if sort == "late_desc":
        filtered_rows.sort(key=lambda row: (-row["lateMinutes"], row["workDate"], row["employeeName"] or ""))
    elif sort == "early_desc":
        filtered_rows.sort(key=lambda row: (-row["earlyCheckoutMinutes"], row["workDate"], row["employeeName"] or ""))
    elif sort == "employee":
        filtered_rows.sort(key=lambda row: (row["employeeName"] or "", row["workDate"], row["startTime"]))
    elif sort == "employee_desc":
        filtered_rows.sort(key=lambda row: (row["employeeName"] or "", row["workDate"], row["startTime"]), reverse=True)
    elif sort == "planned_asc":
        filtered_rows.sort(key=lambda row: (row["workDate"], row["startTime"], row["employeeName"] or ""))
    elif sort == "planned_desc":
        filtered_rows.sort(key=lambda row: (row["workDate"], row["startTime"], row["employeeName"] or ""), reverse=True)
    elif sort == "date_desc":
        filtered_rows.sort(key=lambda row: (row["workDate"], row["startTime"], row["employeeName"] or ""), reverse=True)
    else:
        filtered_rows.sort(key=lambda row: (row["severityRank"], row["workDate"], -(row["lateMinutes"] + row["earlyCheckoutMinutes"]), row["employeeName"] or ""))
    total = len(filtered_rows)
    page = max(page, 1)
    page_size = min(max(page_size, 10), 1000)
    page_rows = filtered_rows[(page - 1) * page_size:page * page_size]
    return {
        "rangeType": range_type or "today",
        "dateFrom": start_date.isoformat(),
        "dateTo": end_date.isoformat(),
        "lateGraceMinutes": 10,
        "items": items,
        "rows": page_rows,
        "summary": summary,
        "filters": {"titles": titles},
        "pagination": pagination(page, page_size, total),
    }


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


def _pt_installment_status(amount: float, paid_amount: float):
    if paid_amount >= amount:
        return "paid"
    if paid_amount > 0:
        return "partial"
    return "pending"


def _normalize_pt_debt_installments(payload: dict, debt_amount: float):
    rows = payload.get("debtInstallments") or []
    if debt_amount <= 0:
        return []
    if not isinstance(rows, list) or not rows:
        raise HTTPException(422, "Vui lòng thêm ít nhất một hạn công nợ PT.")
    normalized = []
    total = 0.0
    for index, item in enumerate(rows, start=1):
        if not isinstance(item, dict):
            raise HTTPException(422, f"Hạn công nợ PT #{index} không hợp lệ.")
        amount = _money(item.get("amount"))
        due_date = _as_date(item.get("dueDate"))
        if amount <= 0:
            raise HTTPException(422, f"Số tiền hạn công nợ PT #{index} phải lớn hơn 0.")
        if not due_date:
            raise HTTPException(422, f"Vui lòng chọn ngày hạn công nợ PT #{index}.")
        total += amount
        normalized.append({"amount": amount, "dueDate": due_date, "note": str(item.get("note") or "").strip()[:255] or None})
    if round(total, 2) != round(debt_amount, 2):
        raise HTTPException(422, "Tổng các hạn công nợ PT phải bằng số tiền còn nợ.")
    return normalized


def list_pt(db: Session, group_type: str, q: str, assignment: str, page: int, page_size: int, actor: User | None = None):
    if group_type not in ("1:1","1:2","1:3"): group_type="1:1"
    query=db.query(PtEnrollment).options(joinedload(PtEnrollment.customer).joinedload(Customer.person),joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person),joinedload(PtEnrollment.debt_installments),joinedload(PtEnrollment.payments)).filter(PtEnrollment.group_type==group_type)
    if actor and actor.role == "coach":
        if not actor.employee_id:
            query = query.filter(PtEnrollment.id == -1)
        else:
            query = query.filter(PtEnrollment.coach_assignments.any(PtEnrollmentCoach.coach_id == actor.employee_id))
    if q: query=query.join(PtEnrollment.customer).join(Customer.person).filter(or_(Person.display_name.contains(q),Person.phone.contains(q),Customer.customer_code.contains(q)))
    if assignment=="unassigned": query=query.filter(~PtEnrollment.coach_assignments.any())
    elif assignment=="assigned": query=query.filter(PtEnrollment.coach_assignments.any())
    total=query.count();rows=query.order_by(PtEnrollment.status,PtEnrollment.id.desc()).offset((page-1)*page_size).limit(page_size).all()
    count_query = lambda kind: db.query(PtEnrollment).filter(PtEnrollment.group_type == kind)
    counts={}
    for kind in ("1:1","1:2","1:3"):
        counter = count_query(kind)
        if actor and actor.role == "coach":
            counter = counter.filter(PtEnrollment.coach_assignments.any(PtEnrollmentCoach.coach_id == actor.employee_id)) if actor.employee_id else counter.filter(PtEnrollment.id == -1)
        counts[kind] = counter.count()
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
    package_name = str(payload.get("packageName") or "").strip()[:160] or None
    final_price = _money(payload.get("finalPrice"))
    paid_amount = _money(payload.get("paidAmount"))
    if paid_amount > final_price:
        raise HTTPException(422, "Số tiền PT đã thanh toán không thể lớn hơn giá trị gói.")
    debt_amount = max(final_price - paid_amount, 0)
    debt_installments = _normalize_pt_debt_installments(payload, debt_amount)
    paid_at = _parse_paid_at(payload.get("paidAt")) if paid_amount else None
    method = payload.get("paymentMethod") or "cash"
    bank_account_id = _as_int(payload.get("bankAccountId"))
    if paid_amount and method == "bank_transfer" and not bank_account_id:
        raise HTTPException(422, "Vui lòng chọn tài khoản nhận tiền khi thanh toán PT chuyển khoản.")
    row=PtEnrollment(customer_id=member_id,coach_id=coach_ids[0] if coach_ids else None,package_name=package_name,group_type=kind,starts_at=_as_date(payload.get("startsAt")) or vietnam_today(),expires_at=_as_date(payload.get("expiresAt")),total_sessions=sessions,remaining_sessions=sessions,schedule_json=schedule_json,schedule_days=schedule_days,schedule_time=schedule_time,final_price=final_price,paid_amount=paid_amount,debt_amount=debt_amount,status="active")
    if row.expires_at and row.expires_at<row.starts_at: raise HTTPException(422,"Ngày hết hạn phải sau ngày bắt đầu.")
    db.add(row);db.flush()
    row.coach_assignments=[PtEnrollmentCoach(coach_id=coach_id) for coach_id in coach_ids]
    row.debt_installments = [PtDebtInstallment(amount=item["amount"], due_date=item["dueDate"], note=item["note"]) for item in debt_installments]
    if paid_amount:
        payment = Payment(customer_id=member_id, pt_enrollment_id=row.id, bank_account_id=bank_account_id, payment_no=f"PTPAY-{row.id:06d}-001", paid_at=paid_at, amount=paid_amount, method=method, channel="pt", shift_date=utc_vietnam_date(paid_at) or vietnam_today(), note=f"Thanh toán đăng ký PT {package_name or kind}")
        db.add(payment)
    record_audit(db, actor, "create", "pt_enrollment", row.id, f"Đăng ký PT {package_name or kind} · {sessions} buổi", customer_id=member_id, details={"coachIds": coach_ids, "packageName": package_name, "expiresAt": row.expires_at, "finalPrice": final_price, "paidAmount": paid_amount, "debtAmount": debt_amount, "debtInstallments": [{"amount": item["amount"], "dueDate": item["dueDate"].isoformat()} for item in debt_installments]})
    db.commit()
    row=db.query(PtEnrollment).options(joinedload(PtEnrollment.customer).joinedload(Customer.person),joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person),joinedload(PtEnrollment.debt_installments),joinedload(PtEnrollment.payments)).get(row.id);return pt_data(row)


def update_pt(db: Session, enrollment_id: int, payload: dict, actor: User | None = None):
    row=db.query(PtEnrollment).options(joinedload(PtEnrollment.customer).joinedload(Customer.person),joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person),joinedload(PtEnrollment.debt_installments),joinedload(PtEnrollment.payments)).filter(PtEnrollment.id==enrollment_id).first()
    if not row: raise HTTPException(404,"Không tìm thấy đăng ký PT.")
    if actor and actor.role == "coach":
        assigned_coach_ids = {assignment.coach_id for assignment in row.coach_assignments}
        if not actor.employee_id or actor.employee_id not in assigned_coach_ids:
            raise HTTPException(403, "Coach chỉ được cập nhật khách PT do mình phụ trách.")
        coach_fields = {"remainingSessions", "schedule", "scheduleDays", "scheduleTime", "status"}
        if set(payload) - coach_fields:
            raise HTTPException(403, "Coach chỉ được cập nhật lịch tập, số buổi còn lại và trạng thái.")
    old_values = {
        "coachIds": [assignment.coach_id for assignment in row.coach_assignments],
        "packageName": row.package_name,
        "type": row.group_type,
        "startsAt": row.starts_at,
        "expiresAt": row.expires_at,
        "totalSessions": row.total_sessions,
        "remainingSessions": row.remaining_sessions,
        "schedule": row.schedule_json,
        "scheduleDays": row.schedule_days,
        "scheduleTime": row.schedule_time,
        "finalPrice": row.final_price,
        "paidAmount": row.paid_amount,
        "debtAmount": row.debt_amount,
        "status": row.status,
    }
    previous_paid_amount = row.paid_amount or 0
    if "coachIds" in payload or "coachId" in payload:
        raw_ids=payload.get("coachIds") if "coachIds" in payload else ([payload.get("coachId")] if payload.get("coachId") else [])
        coach_ids=list(dict.fromkeys(value for value in (_as_int(value) for value in (raw_ids or [])) if value))
        coaches=db.query(Employee).filter(Employee.id.in_(coach_ids),Employee.status=="active").all() if coach_ids else []
        if len(coaches)!=len(coach_ids): raise HTTPException(422,"Có Coach không hợp lệ hoặc đã ngừng hoạt động.")
        row.coach_id=coach_ids[0] if coach_ids else None
        row.coach_assignments=[PtEnrollmentCoach(coach_id=coach_id) for coach_id in coach_ids]
    if payload.get("type") in ("1:1","1:2","1:3"): row.group_type=payload["type"]
    if "packageName" in payload: row.package_name=str(payload.get("packageName") or "").strip()[:160] or None
    if "startsAt" in payload: row.starts_at=_as_date(payload["startsAt"]) or row.starts_at
    if "expiresAt" in payload: row.expires_at=_as_date(payload["expiresAt"])
    if "totalSessions" in payload: row.total_sessions=max(_as_int(payload["totalSessions"],1),1)
    if "remainingSessions" in payload: row.remaining_sessions=min(max(_as_int(payload["remainingSessions"],0),0),row.total_sessions)
    if any(key in payload for key in ("finalPrice", "paidAmount", "debtInstallments")) and not (actor and actor.role == "coach"):
        next_final_price = _money(payload.get("finalPrice"), row.final_price)
        next_paid_amount = _money(payload.get("paidAmount"), row.paid_amount)
        if next_paid_amount < previous_paid_amount:
            raise HTTPException(422, "Không thể giảm số tiền PT đã thu. Hãy tạo nghiệp vụ hoàn tiền riêng.")
        if next_paid_amount > next_final_price:
            raise HTTPException(422, "Số tiền PT đã thanh toán không thể lớn hơn giá trị gói.")
        next_debt_amount = max(next_final_price - next_paid_amount, 0)
        debt_installments = _normalize_pt_debt_installments(payload, next_debt_amount)
        row.final_price = next_final_price
        row.paid_amount = next_paid_amount
        row.debt_amount = next_debt_amount
        row.debt_installments = [PtDebtInstallment(amount=item["amount"], due_date=item["dueDate"], note=item["note"]) for item in debt_installments]
        payment_delta = next_paid_amount - previous_paid_amount
        if payment_delta > 0:
            paid_at = _parse_paid_at(payload.get("paidAt"))
            method = payload.get("paymentMethod") or "cash"
            bank_account_id = _as_int(payload.get("bankAccountId"))
            if method == "bank_transfer" and not bank_account_id:
                raise HTTPException(422, "Vui lòng chọn tài khoản nhận tiền khi thanh toán PT chuyển khoản.")
            sequence = db.query(Payment).filter(Payment.pt_enrollment_id == row.id).count() + 1
            payment = Payment(customer_id=row.customer_id, pt_enrollment_id=row.id, bank_account_id=bank_account_id, payment_no=f"PTPAY-{row.id:06d}-{sequence:03d}", paid_at=paid_at, amount=payment_delta, method=method, channel="pt", shift_date=utc_vietnam_date(paid_at) or vietnam_today(), note=f"Thanh toán công nợ PT {row.package_name or row.group_type}")
            db.add(payment)
    if any(key in payload for key in ("schedule", "scheduleDays", "scheduleTime")):
        row.schedule_json,row.schedule_days,row.schedule_time=schedule_storage(normalize_schedule(payload))
    if payload.get("status") in ("active","completed","inactive"): row.status=payload["status"]
    if row.expires_at and row.expires_at<row.starts_at: raise HTTPException(422,"Ngày hết hạn phải sau ngày bắt đầu.")
    new_values = {
        "coachIds": [assignment.coach_id for assignment in row.coach_assignments],
        "packageName": row.package_name,
        "type": row.group_type,
        "startsAt": row.starts_at,
        "expiresAt": row.expires_at,
        "totalSessions": row.total_sessions,
        "remainingSessions": row.remaining_sessions,
        "schedule": row.schedule_json,
        "scheduleDays": row.schedule_days,
        "scheduleTime": row.schedule_time,
        "finalPrice": row.final_price,
        "paidAmount": row.paid_amount,
        "debtAmount": row.debt_amount,
        "status": row.status,
    }
    fields = []
    changes = []
    for field in payload.keys():
        normalized = "coachIds" if field == "coachId" else field
        if normalized not in PT_AUDIT_FIELD_LABELS or normalized in fields:
            continue
        if old_values.get(normalized) == new_values.get(normalized):
            continue
        fields.append(normalized)
        changes.append({
            "field": normalized,
            "label": PT_AUDIT_FIELD_LABELS[normalized],
            "old": _audit_value(old_values.get(normalized)),
            "new": _audit_value(new_values.get(normalized)),
        })
    label_suffix = f": {', '.join(change['label'] for change in changes)}" if changes else ""
    record_audit(
        db,
        actor,
        "update",
        "pt_enrollment",
        row.id,
        f"Cập nhật đăng ký PT{label_suffix}",
        customer_id=row.customer_id,
        details={"fields": fields, "fieldLabels": [change["label"] for change in changes], "changes": changes, "coachIds": new_values["coachIds"]},
    )
    db.commit();db.refresh(row);return pt_data(row)


def _pt_log_data(row: PtSessionLog):
    return {
        "id": row.id,
        "enrollmentId": row.enrollment_id,
        "attendanceSessionId": row.attendance_session_id,
        "action": row.action,
        "deltaSessions": row.delta_sessions,
        "remainingBefore": row.remaining_before,
        "remainingAfter": row.remaining_after,
        "trainingDate": row.training_date.isoformat() if row.training_date else None,
        "startedAt": utc_iso(row.started_at) if row.started_at else None,
        "endedAt": utc_iso(row.ended_at) if row.ended_at else None,
        "note": row.note,
        "createdAt": utc_iso(row.created_at),
        "createdBy": row.created_by.display_name if row.created_by else "Hệ thống",
    }


def _record_pt_session_log(
    db: Session,
    enrollment: PtEnrollment,
    action: str,
    delta_sessions: int,
    before: int,
    after: int,
    actor: User | None,
    attendance_session_id: int | None = None,
    note: str | None = None,
    training_date: date | None = None,
    started_at: datetime | None = None,
    ended_at: datetime | None = None,
):
    row = PtSessionLog(
        enrollment_id=enrollment.id,
        attendance_session_id=attendance_session_id,
        action=action,
        delta_sessions=delta_sessions,
        remaining_before=before,
        remaining_after=after,
        training_date=training_date,
        started_at=started_at,
        ended_at=ended_at,
        note=(note or "")[:255] or None,
        created_by_user_id=actor.id if actor else None,
    )
    db.add(row)
    db.flush()
    return row


def adjust_pt_sessions(db: Session, enrollment_id: int, payload: dict, actor: User | None = None):
    row = (
        db.query(PtEnrollment)
        .options(
            joinedload(PtEnrollment.customer).joinedload(Customer.person),
            joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person),
        )
        .filter(PtEnrollment.id == enrollment_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy đăng ký PT.")
    if actor and actor.role == "coach":
        assigned_coach_ids = {assignment.coach_id for assignment in row.coach_assignments}
        if not actor.employee_id or actor.employee_id not in assigned_coach_ids:
            raise HTTPException(403, "Coach chỉ được cập nhật khách PT do mình phụ trách.")
    action = str(payload.get("action") or "").strip().lower()
    if action not in {"add", "subtract"}:
        raise HTTPException(422, "Hành động phải là add hoặc subtract.")
    amount = max(_as_int(payload.get("amount"), 1), 1)
    before = int(row.remaining_sessions or 0)
    if action == "add":
        row.remaining_sessions = before + amount
        row.total_sessions = max(int(row.total_sessions or 0), row.remaining_sessions)
        audit_action = "pt_sessions_add"
        delta = amount
        summary = f"Cộng {amount} buổi PT cho {row.customer.person.display_name}"
    else:
        if before < amount:
            raise HTTPException(422, "Số buổi PT còn lại không đủ để trừ.")
        row.remaining_sessions = before - amount
        audit_action = "pt_sessions_subtract"
        delta = -amount
        summary = f"Trừ {amount} buổi PT của {row.customer.person.display_name}"
    note = str(payload.get("note") or "").strip()[:255] or None
    log = _record_pt_session_log(db, row, audit_action, delta, before, row.remaining_sessions, actor, note=note)
    record_audit(
        db,
        actor,
        audit_action,
        "pt_enrollment",
        row.id,
        summary,
        customer_id=row.customer_id,
        details={
            "amount": amount,
            "deltaSessions": delta,
            "remainingBefore": before,
            "remainingAfter": row.remaining_sessions,
            "note": note,
            "ptSessionLogId": log.id,
        },
    )
    db.commit()
    db.refresh(row)
    return {"enrollment": pt_data(row), "log": _pt_log_data(log)}


def _today_pt_slots(enrollment: PtEnrollment, target: date):
    weekday = WEEKDAYS[target.weekday()]
    return [slot for slot in schedule_data(enrollment) if slot.get("day") == weekday]


def _active_regular_membership_for_processing(db: Session, customer_id: int):
    return (
        db.query(Membership)
        .options(joinedload(Membership.package), joinedload(Membership.freezes))
        .join(ServicePackage)
        .filter(Membership.customer_id == customer_id, ServicePackage.is_pt == False)
        .order_by(Membership.registered_at.desc(), Membership.id.desc())
        .first()
    )


def _membership_danger(summary: dict | None):
    if not summary:
        return True, "Chưa có gói gym."
    status = summary.get("status")
    if status in {"expired", "frozen", "suspended", "cancelled", "inactive", "blocked"}:
        return True, {
            "expired": "Gói đã hết hạn.",
            "frozen": "Gói đang bảo lưu.",
            "suspended": "Gói đang tạm dừng.",
            "cancelled": "Gói đã hủy.",
            "inactive": "Gói tạm ngừng.",
            "blocked": "Hội viên bị khóa.",
        }.get(status, "Gói cần kiểm tra.")
    return False, None


def _member_processing_item(db: Session, session: AttendanceSession, target: date, enrollments: list[PtEnrollment]):
    member = session.customer
    membership = _active_regular_membership_for_processing(db, member.id)
    membership_summary = membership_data(membership) if membership else None
    danger, danger_reason = _membership_danger(membership_summary)
    pt_items = []
    for enrollment in enrollments:
        data = pt_data(enrollment)
        data["todaySlots"] = _today_pt_slots(enrollment, target)
        pt_items.append(data)
    return {
        "sessionId": session.id,
        "checkedInAt": _attendance_iso(session.checked_in_at, session.source),
        "source": session.source,
        "status": session.status,
        "member": {
            "id": member.id,
            "code": member.customer_code,
            "name": member.person.display_name,
            "phone": member.person.phone,
            "status": member.status,
            "avatarImageData": member.avatar_image_data,
        },
        "gymMembership": membership_summary,
        "gymDanger": danger,
        "gymDangerReason": danger_reason,
        "ptEnrollments": pt_items,
        "ptToday": pt_items,
        "decision": session.workout_type or "undecided",
    }


def member_processing_queue(db: Session, day: str = "", page: int = 1, page_size: int = 50):
    target = _as_date(day) or vietnam_today()
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    utc_start, utc_end = vietnam_day_utc_bounds(target)
    is_non_dah = or_(AttendanceSession.source != "dah", AttendanceSession.source == None)
    sessions = (
        db.query(AttendanceSession)
        .options(joinedload(AttendanceSession.customer).joinedload(Customer.person))
        .filter(
            AttendanceSession.customer_id.is_not(None),
            AttendanceSession.processed_at.is_(None),
            or_(
                and_(AttendanceSession.source == "dah", AttendanceSession.checked_in_at >= start, AttendanceSession.checked_in_at < end),
                and_(is_non_dah, AttendanceSession.checked_in_at >= utc_start, AttendanceSession.checked_in_at < utc_end),
            ),
        )
        .order_by(AttendanceSession.checked_in_at.desc(), AttendanceSession.id.desc())
        .all()
    )
    customer_ids = sorted({row.customer_id for row in sessions if row.customer_id})
    enrollments = (
        db.query(PtEnrollment)
        .options(
            joinedload(PtEnrollment.customer).joinedload(Customer.person),
            joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person),
        )
        .filter(
            PtEnrollment.customer_id.in_(customer_ids),
            PtEnrollment.status == "active",
            PtEnrollment.remaining_sessions > 0,
            or_(PtEnrollment.starts_at == None, PtEnrollment.starts_at <= target),
            or_(PtEnrollment.expires_at == None, PtEnrollment.expires_at >= target),
        )
        .all()
    ) if customer_ids else []
    by_customer = {}
    for enrollment in enrollments:
        by_customer.setdefault(enrollment.customer_id, []).append(enrollment)
    filtered = [row for row in sessions if by_customer.get(row.customer_id)]
    total = len(filtered)
    start_index = (page - 1) * page_size
    rows = filtered[start_index:start_index + page_size]
    return {
        "date": target.isoformat(),
        "items": [_member_processing_item(db, row, target, by_customer[row.customer_id]) for row in rows],
        "pagination": pagination(page, page_size, total),
    }


def process_member_checkin(db: Session, session_id: int, payload: dict, actor: User | None = None):
    session = (
        db.query(AttendanceSession)
        .options(joinedload(AttendanceSession.customer).joinedload(Customer.person))
        .filter(AttendanceSession.id == session_id, AttendanceSession.customer_id.is_not(None))
        .first()
    )
    if not session:
        raise HTTPException(404, "Không tìm thấy lượt check-in hội viên.")
    if session.processed_at:
        raise HTTPException(409, "Lượt check-in này đã được xử lý.")
    decision = str(payload.get("decision") or "").strip().lower()
    if decision not in {"pt", "regular"}:
        raise HTTPException(422, "Vui lòng chọn Tập PT hoặc Tập Thường.")
    target = session.checked_in_at.date() if session.source == "dah" else vietnam_today()
    note = str(payload.get("note") or "").strip()[:255] or None
    pt_log = None
    enrollment = None
    before = None
    after = None
    if decision == "pt":
        enrollment_id = _as_int(payload.get("ptEnrollmentId"))
        enrollment = (
            db.query(PtEnrollment)
            .options(
                joinedload(PtEnrollment.customer).joinedload(Customer.person),
                joinedload(PtEnrollment.coach_assignments).joinedload(PtEnrollmentCoach.coach).joinedload(Employee.person),
            )
            .filter(PtEnrollment.id == enrollment_id, PtEnrollment.customer_id == session.customer_id)
            .first()
        )
        if not enrollment:
            raise HTTPException(422, "Gói PT không hợp lệ cho hội viên này.")
        if enrollment.status != "active":
            raise HTTPException(422, "Gói PT không hoạt động.")
        if enrollment.expires_at and enrollment.expires_at < target:
            raise HTTPException(422, "Gói PT đã hết hạn.")
        before = int(enrollment.remaining_sessions or 0)
        if before <= 0:
            raise HTTPException(422, "Gói PT đã hết số buổi.")
        training_date = _as_date(payload.get("trainingDate")) or target
        started_at = _as_datetime(payload.get("startedAt")) or session.checked_in_at
        ended_at = _as_datetime(payload.get("endedAt")) or utc_now()
        if ended_at <= started_at:
            raise HTTPException(422, "Giờ kết thúc buổi PT phải sau giờ bắt đầu.")
        enrollment.remaining_sessions = before - 1
        after = enrollment.remaining_sessions
        session.pt_enrollment_id = enrollment.id
        pt_log = _record_pt_session_log(
            db,
            enrollment,
            "pt_checkin",
            -1,
            before,
            after,
            actor,
            attendance_session_id=session.id,
            note=note or "Xử lý check-in: Tập PT",
            training_date=training_date,
            started_at=started_at,
            ended_at=ended_at,
        )
    session.workout_type = decision
    session.processed_at = utc_now()
    session.processed_by_user_id = actor.id if actor else None
    summary = (
        f"Xử lý check-in PT: {session.customer.person.display_name}"
        if decision == "pt"
        else f"Xử lý check-in tập thường: {session.customer.person.display_name}"
    )
    record_audit(
        db,
        actor,
        "member_processing",
        "attendance",
        session.id,
        summary,
        customer_id=session.customer_id,
        details={
            "decision": decision,
            "ptEnrollmentId": enrollment.id if enrollment else None,
            "ptSessionLogId": pt_log.id if pt_log else None,
            "remainingBefore": before,
            "remainingAfter": after,
            "trainingDate": training_date if decision == "pt" else None,
            "startedAt": started_at if decision == "pt" else None,
            "endedAt": ended_at if decision == "pt" else None,
            "note": note,
        },
    )
    db.commit()
    return {
        "ok": True,
        "sessionId": session.id,
        "decision": decision,
        "ptEnrollment": pt_data(enrollment) if enrollment else None,
        "ptLog": _pt_log_data(pt_log) if pt_log else None,
    }


def checkin_candidates(db: Session, q: str):
    if not q.strip(): return []
    rows=db.query(Customer).options(joinedload(Customer.person),joinedload(Customer.memberships).joinedload(Membership.package)).join(Customer.person).filter(or_(Person.display_name.contains(q),Person.phone.contains(q),Customer.customer_code.contains(q),Customer.mbs_card_code.contains(q))).limit(12).all()
    result=[]
    for member in rows:
        memberships=[m for m in member.memberships if not m.package.is_pt and m.status in ("active", "pending", "suspended")]
        current=sorted(memberships,key=lambda x:x.expires_at or date.max,reverse=True)[0] if memberships else None
        eligible=member.status=="lead" or (bool(current) and (not current.expires_at or current.expires_at>=vietnam_today()))
        result.append({"id":member.id,"code":member.customer_code,"name":member.person.display_name,"phone":member.person.phone,"avatarImageData":member.avatar_image_data,"membership":current.package.name if current else None,"expiresAt":current.expires_at.isoformat() if current and current.expires_at else None,"eligible":eligible,"reason":None if eligible else "Gói tập không hoạt động hoặc đã hết hạn."})
    return result


def recent_checkins(db: Session, day: str = "", person_type: str = "all", page: int = 1, page_size: int = 20):
    target = _as_date(day) or vietnam_today()
    start = datetime.combine(target, datetime.min.time())
    end = start + timedelta(days=1)
    carryover_start = start - timedelta(days=1)
    utc_start, utc_end = vietnam_day_utc_bounds(target)
    utc_carryover_start, _ = vietnam_day_utc_bounds(target - timedelta(days=1))
    is_non_dah = or_(AttendanceSession.source != "dah", AttendanceSession.source == None)
    query = (
        db.query(AttendanceSession)
        .options(
            load_only(
                AttendanceSession.id,
                AttendanceSession.customer_id,
                AttendanceSession.employee_id,
                AttendanceSession.scheduled_start_at,
                AttendanceSession.scheduled_end_at,
                AttendanceSession.checked_in_at,
                AttendanceSession.checked_out_at,
                AttendanceSession.source,
                AttendanceSession.result,
                AttendanceSession.status,
            ),
            joinedload(AttendanceSession.customer)
            .load_only(Customer.id, Customer.customer_code, Customer.status, Customer.avatar_image_data)
            .joinedload(Customer.person)
            .load_only(Person.display_name),
            joinedload(AttendanceSession.employee)
            .load_only(Employee.id, Employee.employee_code)
            .joinedload(Employee.person)
            .load_only(Person.display_name),
        )
        .filter(or_(
            and_(AttendanceSession.source == "dah", AttendanceSession.checked_in_at >= start, AttendanceSession.checked_in_at < end),
            and_(is_non_dah, AttendanceSession.checked_in_at >= utc_start, AttendanceSession.checked_in_at < utc_end),
            and_(
                AttendanceSession.status == "open",
                or_(
                    and_(AttendanceSession.source == "dah", AttendanceSession.checked_in_at >= carryover_start, AttendanceSession.checked_in_at < end),
                    and_(is_non_dah, AttendanceSession.checked_in_at >= utc_carryover_start, AttendanceSession.checked_in_at < utc_end),
                ),
            ),
        ))
    )
    if person_type == "member":
        query = query.filter(AttendanceSession.customer_id.is_not(None))
    elif person_type == "employee":
        query = query.filter(AttendanceSession.employee_id.is_not(None))
    total = query.count()
    active_count = query.filter(AttendanceSession.status == "open").count()
    rows = (
        query.order_by(
            (AttendanceSession.status == "open").desc(),
            AttendanceSession.checked_in_at.desc(),
            AttendanceSession.id.desc(),
        )
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    member_warnings = _member_access_warnings(db, [row.customer for row in rows if row.customer_id and row.customer])
    items = [{
        "id":row.id,
        "personType":"employee" if row.employee_id else "member",
        "memberId":row.customer_id,
        "memberName":row.customer.person.display_name if row.customer else None,
        "memberCode":row.customer.customer_code if row.customer else None,
        "memberStatus":row.customer.status if row.customer else None,
        "memberAccessWarning":member_warnings.get(row.customer_id) if row.customer_id else None,
        "memberAvatarImageData":row.customer.avatar_image_data if row.customer else None,
        "employeeId":row.employee_id,
        "employeeName":row.employee.person.display_name if row.employee else None,
        "employeeCode":row.employee.employee_code if row.employee else None,
        "scheduledStartAt":_attendance_iso(row.scheduled_start_at, row.source),
        "scheduledEndAt":_attendance_iso(row.scheduled_end_at, row.source),
        "checkedInAt":_attendance_iso(row.checked_in_at, row.source),
        "checkedOutAt":_attendance_iso(row.checked_out_at, row.source),
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
    current=db.query(Membership).options(joinedload(Membership.package)).join(Membership.package).filter(Membership.customer_id==member_id,Membership.status=="active",ServicePackage.is_pt==False,or_(Membership.expires_at==None,Membership.expires_at>=vietnam_today())).first()
    if not current:
        current = activate_customer_first_checkin(db, member_id, vietnam_today())
    warning = None
    if member.status != "lead" and member.status != "active":
        raise HTTPException(422,"Hội viên không ở trạng thái hoạt động.")
    if member.status != "lead" and not current:
        warning = _member_access_warning(db, member)
        if not warning:
            raise HTTPException(422,"Hội viên không có gói tập còn hiệu lực.")
    raw_note = str(payload.get("note") or "").strip()
    note = raw_note or None
    if warning:
        note = f"Cảnh báo: {warning}" + (f" · {raw_note}" if raw_note else "")
    row=AttendanceSession(customer_id=member_id,checked_in_at=utc_now(),source="manual",result="warning" if warning else "allowed",status="open",note=note);db.add(row);db.flush()
    record_audit(db, actor, "checkin", "attendance", row.id, f"Check-in {member.person.display_name}", customer_id=member_id)
    queue_checkin_speech(db, row.id, "member", member.person.display_name)
    db.commit();return {"id":row.id,"checkedInAt":utc_iso(row.checked_in_at)}


def checkout(db: Session, session_id: int, actor: User | None = None):
    row=db.get(AttendanceSession,session_id)
    if not row: raise HTTPException(404,"Không tìm thấy phiên check-in.")
    if row.status!="open": raise HTTPException(409,"Phiên này đã được check-out.")
    row.checked_out_at=datetime.now(VIETNAM_TZ).replace(tzinfo=None) if row.source=="dah" else utc_now();row.status="closed"
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


def update_payment(db: Session, payment_id: int, payload: dict, actor: User | None = None):
    row = (
        db.query(Payment)
        .options(
            joinedload(Payment.customer).joinedload(Customer.person),
            joinedload(Payment.membership).joinedload(Membership.package),
            joinedload(Payment.receipts).joinedload(PaymentReceipt.uploaded_by),
        )
        .filter(Payment.id == payment_id)
        .first()
    )
    if not row:
        raise HTTPException(404, "Không tìm thấy phiếu thu.")
    if "paidAt" not in payload:
        raise HTTPException(422, "Ngày nhận thanh toán là bắt buộc.")
    old_paid_at = row.paid_at
    old_shift_date = row.shift_date
    paid_at = _parse_paid_at(payload.get("paidAt"))
    row.paid_at = paid_at
    row.shift_date = utc_vietnam_date(paid_at) or vietnam_today()
    record_audit(
        db,
        actor,
        "update",
        "payment",
        row.id,
        f"Sửa ngày nhận thanh toán {row.payment_no}",
        customer_id=row.customer_id,
        details={
            "paymentNo": row.payment_no,
            "oldPaidAt": old_paid_at,
            "newPaidAt": row.paid_at,
            "oldShiftDate": old_shift_date,
            "newShiftDate": row.shift_date,
        },
    )
    db.commit()
    db.refresh(row)
    return payment_data(row)


def settings(db: Session):
    ensure_employee_job_titles(db)
    device = _primary_dah_device(db)
    db.commit()
    accounts=db.query(BankAccount).filter(BankAccount.status != "deleted").order_by(BankAccount.id).all()
    return {
        "jobTitles": [_job_title_data(row) for row in employee_job_titles(db)],
        "bankAccounts":[_bank_account_data(row) for row in accounts],
        "devices":[device_data(device)],
        "checkinSpeech": speech_settings_data(db),
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
