from __future__ import annotations

from datetime import date, datetime, timedelta
import hashlib
import json
import threading
import time
import unicodedata
from uuid import uuid4

from sqlalchemy import and_, or_
from sqlalchemy.orm import Session, joinedload

from ..models import AttendanceSession, Customer, DahCustomerIdentity, DahLocalSyncDay, DahWebhookEvent, Device, Employee
from ..timeutils import VIETNAM_TZ, utc_iso, utc_now, vietnam_today
from . import dah_service
from .employee_shift_attendance import rebuild_employee_attendance_for_day


DEFAULT_LOOKBACK_HOURS = 24
MAX_LOOKBACK_HOURS = 24 * 14
MAX_EVENTS_PER_RESULT = 5000
JOB_TTL_SECONDS = 60 * 60 * 24
SCAN_START_DATE = date(2026, 8, 19)

_lock = threading.RLock()
_jobs: dict[str, dict] = {}
_pending: list[str] = []
_agent_state: dict = {
    "agentId": None,
    "status": "offline",
    "lastSeenAt": None,
    "lastHeartbeat": None,
    "lastError": None,
    "lastJobId": None,
}
_pending_batches: dict[str, dict] = {}


def _clean(value, limit: int = 255) -> str | None:
    text = str(value).strip() if value is not None else ""
    if not text or text.lower() in {"null", "none", "undefined"}:
        return None
    return text[:limit]


def _parse_datetime(value) -> datetime | None:
    text = _clean(value, 80)
    if not text:
        return None
    text = text.replace("/", "T", 1) if "/" in text and "T" not in text else text
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo:
        parsed = parsed.astimezone().replace(tzinfo=None)
    return parsed


def _job_public(row: dict) -> dict:
    return {
        "id": row["id"],
        "status": row["status"],
        "type": row["type"],
        "createdAt": row["createdAt"],
        "startedAt": row.get("startedAt"),
        "completedAt": row.get("completedAt"),
        "agentId": row.get("agentId"),
        "lookbackHours": row.get("lookbackHours"),
        "range": row.get("range"),
        "result": row.get("result"),
        "error": row.get("error"),
    }


def _batch_public(row: dict, include_events: bool = False) -> dict:
    result = {
        "id": row["id"],
        "jobId": row.get("jobId"),
        "agentId": row.get("agentId"),
        "deviceCode": row.get("deviceCode"),
        "dahBaseUrl": row.get("dahBaseUrl"),
        "createdAt": row.get("createdAt"),
        "workDate": row.get("workDate"),
        "range": row.get("range"),
        "status": row.get("status"),
        "totalCount": row.get("totalCount"),
        "failCount": row.get("failCount"),
        "eventCount": len(row.get("events") or []),
        "summary": row.get("summary"),
    }
    if include_events:
        result["events"] = row.get("events") or []
    return result


def _prune_jobs(now: datetime | None = None) -> None:
    now = now or utc_now()
    expired = []
    for job_id, row in _jobs.items():
        created = _parse_datetime(row.get("createdAt"))
        if created and (now - created).total_seconds() > JOB_TTL_SECONDS:
            expired.append(job_id)
    for job_id in expired:
        _jobs.pop(job_id, None)
        if job_id in _pending:
            _pending.remove(job_id)


def heartbeat(payload: dict) -> dict:
    now = utc_now()
    with _lock:
        _agent_state.update({
            "agentId": _clean(payload.get("agentId"), 80) or _agent_state.get("agentId"),
            "status": "online",
            "lastSeenAt": utc_iso(now),
            "lastHeartbeat": payload,
            "lastError": None,
        })
        _prune_jobs(now)
        return status()


def status() -> dict:
    with _lock:
        last_seen = _parse_datetime(_agent_state.get("lastSeenAt"))
        online = bool(last_seen and (utc_now() - last_seen).total_seconds() <= 120)
        recent = sorted(_jobs.values(), key=lambda row: row.get("createdAt") or "", reverse=True)[:10]
        state = dict(_agent_state)
        state["status"] = "online" if online else "offline"
        return {
            "agent": state,
            "pendingCount": len(_pending),
            "pendingBatchCount": len([row for row in _pending_batches.values() if row.get("status") == "pending"]),
            "recentJobs": [_job_public(row) for row in recent],
        }


def _scan_day_public(row: DahLocalSyncDay) -> dict:
    return {
        "workDate": row.work_date.isoformat(),
        "status": row.status,
        "range": {
            "begin": row.range_start.isoformat(timespec="seconds") if row.range_start else None,
            "end": row.range_end.isoformat(timespec="seconds") if row.range_end else None,
        },
        "agentId": row.agent_id,
        "deviceCode": row.device_code,
        "lastScannedAt": utc_iso(row.last_scanned_at) if row.last_scanned_at else None,
        "total": row.total_count,
        "duplicates": row.duplicate_count,
        "matchedMissUnapproved": row.matched_miss_count,
        "unknown": row.unknown_count,
        "rejected": row.rejected_count,
        "failCount": row.fail_count,
        "pendingBatchId": row.pending_batch_id,
    }


def scan_days(db: Session, limit: int = 14) -> dict:
    rows = (
        db.query(DahLocalSyncDay)
        .order_by(DahLocalSyncDay.work_date.desc())
        .limit(max(1, min(int(limit or 14), 60)))
        .all()
    )
    return {"items": [_scan_day_public(row) for row in rows]}


def pending_batches() -> dict:
    with _lock:
        rows = sorted(_pending_batches.values(), key=lambda row: row.get("createdAt") or "", reverse=True)
        return {"items": [_batch_public(row) for row in rows if row.get("status") == "pending"]}


def pending_batch(batch_id: str) -> dict:
    with _lock:
        row = _pending_batches.get(batch_id)
        if not row or row.get("status") != "pending":
            return {"item": None}
        return {"item": _batch_public(row, include_events=True)}


def create_sync_job(payload: dict | None = None, actor=None) -> dict:
    payload = payload or {}
    lookback = int(payload.get("lookbackHours") or DEFAULT_LOOKBACK_HOURS)
    lookback = max(1, min(lookback, MAX_LOOKBACK_HOURS))
    now = utc_now()
    end = now
    begin = now - timedelta(hours=lookback)
    job = {
        "id": uuid4().hex,
        "type": "sync",
        "status": "pending",
        "createdAt": utc_iso(now),
        "createdByUserId": getattr(actor, "id", None),
        "lookbackHours": lookback,
        "range": {"begin": begin.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds")},
    }
    with _lock:
        _prune_jobs(now)
        _jobs[job["id"]] = job
        _pending.append(job["id"])
        return _job_public(job)


def _parse_date(value) -> date | None:
    text = _clean(value, 40)
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _day_range(work_date: date, now: datetime | None = None) -> tuple[datetime, datetime]:
    start = datetime.combine(work_date, datetime.min.time())
    end = start + timedelta(days=1)
    now = now or datetime.now(VIETNAM_TZ).replace(tzinfo=None)
    if work_date == now.date() and now < end:
        end = now
    return start, end


def scan_plan(db: Session, payload: dict | None = None) -> dict:
    payload = payload or {}
    now = datetime.now(VIETNAM_TZ).replace(tzinfo=None)
    start_date = _parse_date(payload.get("from") or payload.get("fromDate")) or SCAN_START_DATE
    end_date = _parse_date(payload.get("to") or payload.get("toDate")) or vietnam_today()
    if start_date < SCAN_START_DATE:
        start_date = SCAN_START_DATE
    if end_date > vietnam_today():
        end_date = vietnam_today()
    if end_date < start_date:
        return {"items": []}
    existing = {
        row.work_date: row
        for row in db.query(DahLocalSyncDay)
        .filter(DahLocalSyncDay.work_date >= start_date, DahLocalSyncDay.work_date <= end_date)
        .all()
    }
    items = []
    current = start_date
    while current <= end_date:
        row = existing.get(current)
        include = row is None or current == now.date() or int(row.fail_count or 0) > 0
        if include:
            begin, end = _day_range(current, now)
            reason = "not_scanned" if row is None else "today" if current == now.date() else "has_failures"
            items.append({
                "workDate": current.isoformat(),
                "range": {"begin": begin.isoformat(timespec="seconds"), "end": end.isoformat(timespec="seconds")},
                "reason": reason,
                "failCount": int(row.fail_count or 0) if row else None,
            })
        current += timedelta(days=1)
    return {"items": items, "from": start_date.isoformat(), "to": end_date.isoformat()}


def next_job(agent_id: str | None, timeout: int = 55) -> dict | None:
    deadline = time.monotonic() + max(0, min(int(timeout or 0), 55))
    agent_id = _clean(agent_id, 80) or "unknown-agent"
    while True:
        with _lock:
            now = utc_now()
            _agent_state.update({"agentId": agent_id, "status": "online", "lastSeenAt": utc_iso(now)})
            _prune_jobs(now)
            if _pending:
                job_id = _pending.pop(0)
                job = _jobs.get(job_id)
                if job:
                    job.update({"status": "running", "startedAt": utc_iso(now), "agentId": agent_id})
                    _agent_state["lastJobId"] = job_id
                    return {
                        "id": job["id"],
                        "type": job["type"],
                        "range": job["range"],
                        "lookbackHours": job["lookbackHours"],
                    }
        if time.monotonic() >= deadline:
            return None
        time.sleep(0.5)


def _name_key(value: str | None) -> str | None:
    text = _clean(value, 160)
    if not text:
        return None
    normalized = unicodedata.normalize("NFD", text)
    no_marks = "".join(ch for ch in normalized if unicodedata.category(ch) != "Mn")
    return " ".join(no_marks.lower().split())


def _profile_key(event: dict) -> str | None:
    direct = _clean(event.get("profileKey"), 120)
    if direct:
        return direct
    ref = event.get("profileImageRef") if isinstance(event.get("profileImageRef"), dict) else None
    if not ref:
        return None
    try:
        return f"dah_profile:{int(ref.get('fileType'))}/{int(ref.get('fileIndex'))}/{int(ref.get('filePos'))}"
    except (TypeError, ValueError):
        return None


def _identity_match(db: Session, event: dict):
    dah_person_uid = _clean(event.get("dahPersonUid"), 80)
    if not dah_person_uid:
        return None
    return (
        db.query(DahCustomerIdentity)
        .filter(DahCustomerIdentity.person_id == dah_person_uid)
        .order_by(DahCustomerIdentity.id.desc())
        .first()
    )


def _match_people(db: Session, event: dict):
    identity = _identity_match(db, event)
    if identity:
        return identity.customer, identity.employee, "person_id"
    return None, None, None


def _upsert_identity_for_match(
    db: Session,
    event: dict,
    device: Device | None,
    customer: Customer | None,
    employee: Employee | None,
    event_time: datetime,
    identity_cache: dict[str, DahCustomerIdentity] | None = None,
) -> None:
    profile = _profile_key(event)
    dah_person_uid = _clean(event.get("dahPersonUid"), 80)
    if not profile or not (customer or employee):
        return
    identity = identity_cache.get(profile) if identity_cache is not None else None
    if not identity:
        identity = (
            db.query(DahCustomerIdentity)
            .filter(DahCustomerIdentity.person_uuid == profile)
            .order_by(DahCustomerIdentity.id.desc())
            .first()
        )
    if not identity:
        identity = DahCustomerIdentity(person_uuid=profile)
        db.add(identity)
    if identity_cache is not None:
        identity_cache[profile] = identity
    identity.customer_id = customer.id if customer else identity.customer_id
    identity.employee_id = employee.id if employee else identity.employee_id
    identity.device_id = device.id if device else identity.device_id
    identity.person_id = dah_person_uid or identity.person_id
    identity.face_name = _clean(event.get("registeredName") or event.get("name"), 160) or identity.face_name
    identity.rfid_card = _clean(event.get("mjCardNo"), 80) or identity.rfid_card
    identity.last_seen_at = event_time


def _device(db: Session, payload: dict) -> Device | None:
    code = _clean(payload.get("deviceCode"), 40) or "DAH-LOCAL"
    row = db.query(Device).filter(Device.code == code).first()
    if not row:
        row = Device(
            code=code,
            name="DAH Local Agent",
            model=dah_service.DAH_MODEL,
            ip_address=_clean(payload.get("dahBaseUrl"), 60),
            purpose="shared",
            status="online",
        )
        db.add(row)
        db.flush()
    row.status = "online"
    row.last_heartbeat_at = utc_now()
    return row


def _event_key(payload: dict, event: dict) -> str:
    raw = "|".join([
        "LocalPull",
        _clean(payload.get("deviceCode"), 80) or "",
        _clean(event.get("dahUid"), 120) or "",
        _clean(event.get("rawEventTime") or event.get("eventTime"), 120) or "",
        _clean(event.get("name"), 160) or "",
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _existing_event_by_person_time(db: Session, person_id: str | None, event_time: datetime | None) -> DahWebhookEvent | None:
    person_id = _clean(person_id, 80)
    if not person_id or not event_time:
        return None
    return (
        db.query(DahWebhookEvent)
        .filter(
            DahWebhookEvent.person_id == person_id,
            DahWebhookEvent.event_time == event_time,
        )
        .order_by(DahWebhookEvent.id.desc())
        .first()
    )


def _existing_duplicate_event(db: Session, key: str, person_id: str | None, event_time: datetime | None) -> DahWebhookEvent | None:
    existing = db.query(DahWebhookEvent).filter(DahWebhookEvent.event_key == key).first()
    return existing or _existing_event_by_person_time(db, person_id, event_time)


def _event_payload(payload: dict, event: dict) -> str:
    compact = dict(event)
    return json.dumps({
        "source": "local-agent",
        "agentId": payload.get("agentId"),
        "jobId": payload.get("jobId"),
        "dahBaseUrl": payload.get("dahBaseUrl"),
        "event": compact,
    }, ensure_ascii=False, default=str, separators=(",", ":"))


def _day_bounds(work_date: date) -> tuple[datetime, datetime]:
    start = datetime.combine(work_date, datetime.min.time())
    return start, start + timedelta(days=1)


def _rebuild_customer_day(db: Session, customer_id: int, work_date: date) -> int:
    customer = db.query(Customer).options(joinedload(Customer.person)).filter(Customer.id == customer_id).first()
    if not customer:
        return 0
    start, end = _day_bounds(work_date)
    existing = (
        db.query(AttendanceSession)
        .filter(
            AttendanceSession.customer_id == customer_id,
            AttendanceSession.source == "dah",
            or_(
                and_(AttendanceSession.checked_in_at >= start, AttendanceSession.checked_in_at < end),
                and_(AttendanceSession.checked_out_at >= start, AttendanceSession.checked_out_at < end),
            ),
        )
        .all()
    )
    protected_session_ids = {row.id for row in existing if row.processed_at}
    rebuildable = [row for row in existing if not row.processed_at]
    rebuildable_ids = [row.id for row in rebuildable]
    if rebuildable_ids:
        db.query(DahWebhookEvent).filter(DahWebhookEvent.attendance_session_id.in_(rebuildable_ids)).update(
            {DahWebhookEvent.attendance_session_id: None},
            synchronize_session=False,
        )
    for row in rebuildable:
        db.delete(row)
    db.flush()

    rows = (
        db.query(DahWebhookEvent)
        .filter(
            DahWebhookEvent.customer_id == customer_id,
            DahWebhookEvent.event_time >= start,
            DahWebhookEvent.event_time < end,
            DahWebhookEvent.verify_status == 1,
            DahWebhookEvent.status.in_(("processed", "duplicate")),
            DahWebhookEvent.action.in_(("checkin", "checkout", "mixed", "local_sync", "duplicate_scan")),
        )
        .order_by(DahWebhookEvent.event_time.asc(), DahWebhookEvent.id.asc())
        .all()
    )
    last_accepted: datetime | None = None
    open_session: AttendanceSession | None = None
    changed = 0
    for row in rows:
        if not row.event_time:
            continue
        if row.attendance_session_id in protected_session_ids:
            continue
        if last_accepted and abs((row.event_time - last_accepted).total_seconds()) <= dah_service.DUPLICATE_SCAN_SECONDS:
            row.status = "duplicate"
            row.action = "duplicate_scan"
            row.note = f"Quét lại trong {dah_service.DUPLICATE_SCAN_SECONDS} giây."
            row.attendance_session_id = open_session.id if open_session else None
            changed += 1
            continue
        membership = dah_service._active_regular_membership(db, customer_id)
        latest = membership or dah_service._latest_regular_membership(db, customer_id)
        warning = dah_service._membership_warning(latest)
        if customer.status != "lead" and not membership and not warning:
            row.status = "denied"
            row.action = "denied"
            row.note = "Hội viên không có gói tập còn hiệu lực."
            row.attendance_session_id = None
            changed += 1
            continue
        if customer.status not in {"active", "lead"}:
            row.status = "denied"
            row.action = "denied"
            row.note = "Hội viên không ở trạng thái hoạt động."
            row.attendance_session_id = None
            changed += 1
            continue
        if open_session:
            open_session.checked_out_at = row.event_time
            open_session.status = "closed"
            row.status = "processed"
            row.action = "checkout"
            row.note = "Check-out hội viên."
            row.attendance_session_id = open_session.id
            open_session = None
        else:
            open_session = AttendanceSession(
                customer_id=customer_id,
                checked_in_at=row.event_time,
                source="dah",
                result="warning" if warning else "allowed",
                status="open",
                note=(f"DAH local sync · Cảnh báo: {warning}" if warning else "DAH local sync")[:255],
            )
            db.add(open_session)
            db.flush()
            row.status = "processed"
            row.action = "checkin"
            row.note = warning or "Check-in hội viên."
            row.attendance_session_id = open_session.id
        last_accepted = row.event_time
        changed += 1
    return changed


def _relink_employee_events(db: Session, employee_id: int, work_date: date) -> int:
    sessions = rebuild_employee_attendance_for_day(db, employee_id, work_date)
    start, end = _day_bounds(work_date)
    rows = (
        db.query(DahWebhookEvent)
        .filter(
            DahWebhookEvent.employee_id == employee_id,
            DahWebhookEvent.event_time >= start,
            DahWebhookEvent.event_time < end,
            DahWebhookEvent.verify_status == 1,
            DahWebhookEvent.status == "processed",
        )
        .order_by(DahWebhookEvent.event_time.asc(), DahWebhookEvent.id.asc())
        .all()
    )
    changed = 0
    for row in rows:
        for session in sessions:
            if session.checked_in_at == row.event_time:
                row.attendance_session_id = session.id
                row.action = "checkin"
                row.note = "Đã đồng bộ chấm công nhân viên theo ca."
                changed += 1
                break
            if session.checked_out_at == row.event_time:
                row.attendance_session_id = session.id
                row.action = "checkout"
                row.note = "Đã đồng bộ chấm công nhân viên theo ca."
                changed += 1
                break
    return changed


def preview_agent_result(db: Session, payload: dict) -> dict:
    if not payload.get("ok", True):
        return {"ok": False, "imported": 0, "duplicates": 0, "unknown": 0, "error": _clean(payload.get("error"), 255)}
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    if len(events) > MAX_EVENTS_PER_RESULT:
        events = events[:MAX_EVENTS_PER_RESULT]
    items = []
    duplicates = unknown = rejected = matched = 0

    for item in events:
        if not isinstance(item, dict):
            continue
        key = _event_key(payload, item)
        event_time = _parse_datetime(item.get("eventTime") or item.get("rawEventTime")) or utc_now()
        person_id = _clean(item.get("dahPersonUid"), 80) or _clean(item.get("mjCardNo"), 80)
        if _existing_duplicate_event(db, key, person_id, event_time):
            duplicates += 1
            duplicate = True
        else:
            duplicate = False
        verify_status = dah_service._int(item.get("status"))
        customer, employee, match_source = _match_people(db, item)
        status = "duplicate" if duplicate else "matched" if verify_status == 1 and (customer or employee) else "unknown"
        if verify_status not in (None, 1):
            status = "rejected"
            rejected += 1
        elif status == "unknown":
            unknown += 1
        elif status == "matched":
            matched += 1
        items.append({
            "eventKey": key,
            "eventTime": event_time.isoformat(timespec="seconds"),
            "name": _clean(item.get("name"), 160),
            "status": status,
            "verifyStatus": verify_status,
            "similarity": dah_service._float(item.get("similarity")),
            "customerId": customer.id if customer else None,
            "customerName": customer.person.display_name if customer and customer.person else None,
            "employeeId": employee.id if employee else None,
            "employeeName": employee.person.display_name if employee and employee.person else None,
            "matchSource": match_source,
            "dahUid": _clean(item.get("dahUid"), 80),
            "dahPersonUid": _clean(item.get("dahPersonUid"), 80),
            "profileKey": _profile_key(item),
            "registeredName": _clean(item.get("registeredName"), 160),
            "registeredPhone": _clean(item.get("registeredPhone"), 40),
            "mjCardNo": _clean(item.get("mjCardNo"), 80),
            "willSync": status in {"matched", "unknown"},
            "raw": item,
        })
    return {
        "ok": True,
        "received": len(events),
        "matched": matched,
        "duplicates": duplicates,
        "unknown": unknown,
        "rejected": rejected,
        "events": items,
    }


def import_agent_result(db: Session, payload: dict, selected_event_keys: set[str] | None = None) -> dict:
    if not payload.get("ok", True):
        return {"ok": False, "imported": 0, "duplicates": 0, "unknown": 0, "error": _clean(payload.get("error"), 255)}
    events = payload.get("events") if isinstance(payload.get("events"), list) else []
    if len(events) > MAX_EVENTS_PER_RESULT:
        events = events[:MAX_EVENTS_PER_RESULT]
    device = _device(db, payload)
    affected_customers: set[tuple[int, date]] = set()
    affected_employees: set[tuple[int, date]] = set()
    identity_cache: dict[str, DahCustomerIdentity] = {}
    imported = duplicates = unknown = rejected = skipped = 0

    for item in events:
        if not isinstance(item, dict):
            continue
        key = _event_key(payload, item)
        if selected_event_keys is not None and key not in selected_event_keys:
            skipped += 1
            continue
        event_time = _parse_datetime(item.get("eventTime") or item.get("rawEventTime")) or utc_now()
        person_id = _clean(item.get("dahPersonUid"), 80) or _clean(item.get("mjCardNo"), 80)
        if _existing_duplicate_event(db, key, person_id, event_time):
            duplicates += 1
            continue
        verify_status = dah_service._int(item.get("status"))
        similarity = dah_service._float(item.get("similarity"))
        customer, employee, match_source = _match_people(db, item)
        status = "processed" if verify_status == 1 and (customer or employee) else "unknown"
        action = "local_sync" if status == "processed" else "unknown_identity"
        note = "Đã nhận từ DAH local agent." if status == "processed" else "Không khớp person id với hội viên/nhân viên."
        if verify_status not in (None, 1):
            status = "rejected"
            action = "verify_failed"
            note = "DAH xác thực không thành công."
            rejected += 1
        elif status == "unknown":
            unknown += 1
        row = DahWebhookEvent(
            event_key=key,
            operator="LocalPull",
            device_id=device.id if device else None,
            customer_id=customer.id if customer else None,
            employee_id=employee.id if employee else None,
            person_uuid=_profile_key(item),
            person_id=person_id,
            verify_status=verify_status,
            similarity=similarity,
            event_time=event_time,
            status=status,
            action=action,
            note=note,
            raw_payload=_event_payload(payload, item),
        )
        db.add(row)
        if status == "processed":
            _upsert_identity_for_match(db, item, device, customer, employee, event_time, identity_cache)
        imported += 1
        if status == "processed":
            if customer:
                affected_customers.add((customer.id, event_time.date()))
            if employee:
                affected_employees.add((employee.id, event_time.date()))
    db.flush()

    relinked_members = sum(_rebuild_customer_day(db, customer_id, work_date) for customer_id, work_date in affected_customers)
    relinked_employees = sum(_relink_employee_events(db, employee_id, work_date) for employee_id, work_date in affected_employees)
    db.commit()
    return {
        "ok": True,
        "received": len(events),
        "imported": imported,
        "duplicates": duplicates,
        "unknown": unknown,
        "rejected": rejected,
        "skipped": skipped,
        "relinkedMembers": relinked_members,
        "relinkedEmployees": relinked_employees,
    }


def _summary_with_fail(preview: dict) -> dict:
    matched = int(preview.get("matched") or 0)
    unknown = int(preview.get("unknown") or 0)
    rejected = int(preview.get("rejected") or 0)
    return {
        "received": int(preview.get("received") or 0),
        "matched": matched,
        "matchedMissUnapproved": matched,
        "duplicates": int(preview.get("duplicates") or 0),
        "unknown": unknown,
        "rejected": rejected,
        "failCount": matched + unknown + rejected,
    }


def _upsert_scan_day(db: Session, payload: dict, preview: dict, batch_id: str | None = None) -> DahLocalSyncDay | None:
    work_date = _parse_date(payload.get("workDate"))
    if not work_date:
        range_payload = payload.get("range") if isinstance(payload.get("range"), dict) else {}
        work_date = (_parse_datetime(range_payload.get("begin")) or utc_now()).date()
    range_payload = payload.get("range") if isinstance(payload.get("range"), dict) else {}
    range_start = _parse_datetime(range_payload.get("begin"))
    range_end = _parse_datetime(range_payload.get("end"))
    summary = _summary_with_fail(preview)
    row = db.query(DahLocalSyncDay).filter(DahLocalSyncDay.work_date == work_date).first()
    if not row:
        row = DahLocalSyncDay(work_date=work_date)
        db.add(row)
    row.range_start = range_start
    row.range_end = range_end
    row.status = "needs_review" if summary["failCount"] > 0 else "clean"
    row.agent_id = _clean(payload.get("agentId"), 80)
    row.device_code = _clean(payload.get("deviceCode"), 80)
    row.last_scanned_at = utc_now()
    row.total_count = summary["received"]
    row.duplicate_count = summary["duplicates"]
    row.matched_miss_count = summary["matchedMissUnapproved"]
    row.unknown_count = summary["unknown"]
    row.rejected_count = summary["rejected"]
    row.fail_count = summary["failCount"]
    row.pending_batch_id = batch_id if summary["failCount"] > 0 else None
    row.updated_at = utc_now()
    db.commit()
    return row


def record_result(db: Session, job_id: str, payload: dict) -> dict:
    preview = preview_agent_result(db, payload)
    now = utc_now()
    batch_id = uuid4().hex
    summary = _summary_with_fail(preview)
    batch = {
        "id": batch_id,
        "jobId": job_id,
        "agentId": _clean(payload.get("agentId"), 80),
        "deviceCode": _clean(payload.get("deviceCode"), 80),
        "dahBaseUrl": _clean(payload.get("dahBaseUrl"), 120),
        "createdAt": utc_iso(now),
        "workDate": _clean(payload.get("workDate"), 20),
        "range": payload.get("range"),
        "status": "pending" if preview.get("ok") else "failed",
        "totalCount": payload.get("totalCount"),
        "failCount": summary["failCount"],
        "events": preview.get("events") or [],
        "rawPayload": payload,
        "summary": summary,
    }
    with _lock:
        _pending_batches[batch_id] = batch
        job = _jobs.get(job_id)
        if not job:
            job = {
                "id": job_id,
                "type": "sync",
                "createdAt": utc_iso(now),
                "lookbackHours": None,
                "range": payload.get("range"),
            }
            _jobs[job_id] = job
        job.update({
            "status": "pending_approval" if preview.get("ok") else "failed",
            "completedAt": utc_iso(now),
            "agentId": _clean(payload.get("agentId"), 80) or job.get("agentId"),
            "range": payload.get("range") or job.get("range"),
            "result": {**batch["summary"], "batchId": batch_id, "pendingApproval": preview.get("ok")},
            "error": preview.get("error"),
        })
        _agent_state.update({
            "agentId": job.get("agentId") or _agent_state.get("agentId"),
            "status": "online",
            "lastSeenAt": utc_iso(now),
            "lastJobId": job_id,
            "lastError": preview.get("error"),
        })
        return {**_job_public(job), "batch": _batch_public(batch)}


def record_day_scan_result(db: Session, payload: dict) -> dict:
    preview = preview_agent_result(db, payload)
    now = utc_now()
    summary = _summary_with_fail(preview)
    batch_id = uuid4().hex if summary["failCount"] > 0 and preview.get("ok") else None
    work_date = _clean(payload.get("workDate"), 20)
    batch = None
    if batch_id:
        batch = {
            "id": batch_id,
            "jobId": _clean(payload.get("jobId"), 80) or f"scan-{work_date or uuid4().hex}",
            "agentId": _clean(payload.get("agentId"), 80),
            "deviceCode": _clean(payload.get("deviceCode"), 80),
            "dahBaseUrl": _clean(payload.get("dahBaseUrl"), 120),
            "createdAt": utc_iso(now),
            "workDate": work_date,
            "range": payload.get("range"),
            "status": "pending",
            "totalCount": payload.get("totalCount"),
            "failCount": summary["failCount"],
            "events": preview.get("events") or [],
            "rawPayload": payload,
            "summary": summary,
        }
    scan_day = _upsert_scan_day(db, payload, preview, batch_id=batch_id)
    with _lock:
        if work_date:
            for existing in _pending_batches.values():
                if existing.get("status") == "pending" and existing.get("workDate") == work_date:
                    existing["status"] = "superseded"
                    existing["supersededAt"] = utc_iso(now)
        if batch:
            _pending_batches[batch_id] = batch
        _agent_state.update({
            "agentId": _clean(payload.get("agentId"), 80) or _agent_state.get("agentId"),
            "status": "online",
            "lastSeenAt": utc_iso(now),
            "lastError": preview.get("error"),
        })
    return {
        "ok": bool(preview.get("ok")),
        "scanDay": _scan_day_public(scan_day) if scan_day else None,
        "batch": _batch_public(batch) if batch else None,
        "summary": summary,
    }


def approve_batch(db: Session, batch_id: str, payload: dict | None = None, actor=None) -> dict:
    payload = payload or {}
    with _lock:
        batch = _pending_batches.get(batch_id)
        if not batch or batch.get("status") != "pending":
            return {"ok": False, "error": "Không tìm thấy batch đang chờ duyệt."}
        selected = payload.get("eventKeys")
        selected_keys = {str(key) for key in selected} if isinstance(selected, list) else {
            row["eventKey"] for row in batch.get("events") or [] if row.get("willSync")
        }
        raw_payload = dict(batch["rawPayload"])
    result = import_agent_result(db, raw_payload, selected_event_keys=selected_keys)
    refreshed_scan_day = None
    if raw_payload.get("workDate"):
        refreshed_preview = preview_agent_result(db, raw_payload)
        refreshed_scan_day = _upsert_scan_day(db, raw_payload, refreshed_preview, batch_id=None)
    with _lock:
        batch["status"] = "approved"
        batch["approvedAt"] = utc_iso(utc_now())
        batch["approvedByUserId"] = getattr(actor, "id", None)
        batch["commitResult"] = result
        job = _jobs.get(batch.get("jobId"))
        if job:
            job["status"] = "completed"
            job["result"] = {**result, "batchId": batch_id}
    return {"ok": True, "batch": _batch_public(batch), "result": result, "scanDay": _scan_day_public(refreshed_scan_day) if refreshed_scan_day else None}


def reject_batch(batch_id: str, actor=None) -> dict:
    with _lock:
        batch = _pending_batches.get(batch_id)
        if not batch or batch.get("status") != "pending":
            return {"ok": False, "error": "Không tìm thấy batch đang chờ duyệt."}
        batch["status"] = "rejected"
        batch["rejectedAt"] = utc_iso(utc_now())
        batch["rejectedByUserId"] = getattr(actor, "id", None)
        job = _jobs.get(batch.get("jobId"))
        if job:
            job["status"] = "rejected"
            job["result"] = {"batchId": batch_id, "rejected": True}
        return {"ok": True, "batch": _batch_public(batch)}
