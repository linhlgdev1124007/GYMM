from datetime import date, datetime, timedelta
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..models import (
    AttendanceSession, Customer, DahCustomerIdentity, DahWebhookEvent,
    Device, Employee, Membership, ServicePackage,
)
from ..timeutils import utc_now, vietnam_today
from .membership_lifecycle import activate_customer_first_checkin

HEARTBEAT_TIMEOUT_SECONDS = 90
DAH_MODEL = "DAH1017"
DUPLICATE_SCAN_SECONDS = 60
WEBHOOK_IMAGE_RETENTION_DAYS = 4


def _clean(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"null", "none", "undefined"}:
        return None
    return text[:255]


def _int(value) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _float(value) -> float | None:
    try:
        return float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _parse_time(value) -> datetime | None:
    text = _clean(value)
    if not text or text.startswith("0000-00-00"):
        return None
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _payload_json(payload: dict) -> str:
    compact = dict(payload)
    for key in ("SanpPic", "SnapPic", "SnapPicData"):
        if key in compact:
            compact[key] = "[omitted:image_data]"
    return json.dumps(compact, ensure_ascii=False, default=str, separators=(",", ":"))


def _image_data(payload: dict) -> str | None:
    raw = payload.get("SanpPic") or payload.get("SnapPic") or payload.get("SnapPicData")
    image = str(raw or "").strip()
    if not image or image.lower() in {"null", "none", "undefined"}:
        return None
    return image if image and image.startswith("data:image/") else image


def _event_key(operator: str, info: dict, payload: dict, image: str | None) -> str:
    device_id = _clean(info.get("DeviceID"))
    person_uuid = _clean(info.get("PersonUUID"))
    person_id = _clean(info.get("PersonID"))
    event_time = _clean(info.get("CreateTime") or info.get("Time"))
    file_index = _clean(payload.get("dwFileIndex"))
    file_pos = _clean(payload.get("dwFilePos"))
    image_digest = hashlib.sha256((image or "").encode("utf-8")).hexdigest()[:16] if image else ""
    raw = "|".join([
        operator or "",
        device_id or "",
        person_uuid or "",
        person_id or "",
        event_time or "",
        file_index or "",
        file_pos or "",
        image_digest,
    ])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _device(db: Session, info: dict) -> Device | None:
    device_identifier = _clean(info.get("DeviceID"))
    if not device_identifier:
        return None
    code = f"DAH-{device_identifier}"
    row = db.query(Device).filter(Device.code == code).first()
    if not row:
        row = db.query(Device).filter(Device.code == DAH_MODEL, Device.model == DAH_MODEL).first()
        if row:
            row.code = code
        else:
            row = Device(
                code=code,
                name=DAH_MODEL,
                model=DAH_MODEL,
                purpose="shared",
                status="online",
            )
            db.add(row)
            db.flush()
    row.name = DAH_MODEL
    row.model = DAH_MODEL
    return row


def _active_regular_membership(db: Session, customer_id: int):
    return (
        db.query(Membership)
        .options(joinedload(Membership.package))
        .join(ServicePackage)
        .filter(
            Membership.customer_id == customer_id,
            Membership.status == "active",
            ServicePackage.is_pt == False,
            or_(Membership.expires_at == None, Membership.expires_at >= vietnam_today()),
        )
        .order_by(Membership.expires_at.desc(), Membership.id.desc())
        .first()
    )


def _identity_for_uuid(db: Session, device: Device | None, info: dict, event_time: datetime | None):
    person_uuid = _clean(info.get("PersonUUID"))
    if not person_uuid:
        return None, None, None, False
    person_id = _clean(info.get("PersonID"))
    face_name = _clean(info.get("Name"))
    rfid = _clean(info.get("RFIDCard")) or _clean(info.get("MjCardNo"))
    identity = db.query(DahCustomerIdentity).filter(DahCustomerIdentity.person_uuid == person_uuid).first()
    if identity:
        identity.device_id = device.id if device else identity.device_id
        identity.person_id = person_id or identity.person_id
        identity.face_name = face_name or identity.face_name
        identity.rfid_card = rfid or identity.rfid_card
        identity.last_seen_at = event_time or utc_now()
        customer = db.get(Customer, identity.customer_id) if identity.customer_id else None
        employee = db.get(Employee, identity.employee_id) if identity.employee_id else None
        if customer and not customer.person_uuid:
            customer.person_uuid = person_uuid
        return identity, customer, employee, False

    customer = db.query(Customer).filter(Customer.person_uuid == person_uuid).first()
    if not customer:
        return None, None, None, False
    identity = DahCustomerIdentity(
        customer_id=customer.id,
        device_id=device.id if device else None,
        person_uuid=person_uuid,
        person_id=person_id,
        face_name=face_name,
        rfid_card=rfid,
        last_seen_at=event_time or utc_now(),
    )
    db.add(identity)
    db.flush()
    return identity, customer, None, True


def _recent_duplicate_scan(db: Session, person_uuid: str | None, event_time: datetime) -> bool:
    if not person_uuid:
        return False
    recent_processed = (
        db.query(DahWebhookEvent)
        .filter(
            DahWebhookEvent.person_uuid == person_uuid,
            DahWebhookEvent.status == "processed",
            DahWebhookEvent.action.in_(("checkin", "checkout", "mixed")),
        )
        .order_by(DahWebhookEvent.event_time.desc(), DahWebhookEvent.received_at.desc())
        .first()
    )
    return bool(
        recent_processed and recent_processed.event_time and
        abs((event_time - recent_processed.event_time).total_seconds()) <= DUPLICATE_SCAN_SECONDS
    )


def _toggle_employee_attendance(db: Session, employee: Employee, event_time: datetime, device: Device | None) -> dict:
    if employee.status != "active":
        return {"status": "denied", "action": "denied", "note": "Nhân viên không ở trạng thái hoạt động.", "session_id": None}
    open_session = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.employee_id == employee.id, AttendanceSession.status == "open")
        .order_by(AttendanceSession.checked_in_at.desc(), AttendanceSession.id.desc())
        .first()
    )
    if open_session:
        open_session.checked_out_at = event_time
        open_session.status = "closed"
        open_session.note = (open_session.note or "DAH employee auto")[:255]
        return {"status": "processed", "action": "checkout", "note": "Check-out nhân viên.", "session_id": open_session.id}
    session = AttendanceSession(
        employee_id=employee.id,
        checked_in_at=event_time,
        source="dah",
        result="allowed",
        status="open",
        note=f"DAH {device.code}" if device else "DAH",
    )
    db.add(session)
    db.flush()
    return {"status": "processed", "action": "checkin", "note": "Check-in nhân viên.", "session_id": session.id}


def _toggle_customer_attendance(
    db: Session,
    customer: Customer,
    event_time: datetime,
    device: Device | None,
    image: str | None,
    identity_created: bool,
) -> dict:
    if image and (identity_created or not customer.avatar_image_data):
        customer.avatar_image_data = image
    open_session = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.customer_id == customer.id, AttendanceSession.status == "open")
        .order_by(AttendanceSession.checked_in_at.desc(), AttendanceSession.id.desc())
        .first()
    )
    if open_session:
        open_session.checked_out_at = event_time
        open_session.status = "closed"
        open_session.note = (open_session.note or "DAH auto")[:255]
        return {"status": "processed", "action": "checkout", "note": "Check-out hội viên.", "session_id": open_session.id}
    if customer.status == "lead":
        session = AttendanceSession(
            customer_id=customer.id,
            checked_in_at=event_time,
            source="dah",
            result="allowed",
            status="open",
            note=f"DAH {device.code} · Khách tiềm năng" if device else "DAH · Khách tiềm năng",
        )
        db.add(session)
        db.flush()
        return {"status": "processed", "action": "checkin", "note": "Check-in khách tiềm năng.", "session_id": session.id}
    membership = _active_regular_membership(db, customer.id)
    if not membership:
        activated = activate_customer_first_checkin(db, customer.id, event_time)
        if activated:
            membership = activated
    if not membership:
        return {"status": "denied", "action": "denied", "note": "Hội viên không có gói tập còn hiệu lực.", "session_id": None}
    if customer.status != "active":
        return {"status": "denied", "action": "denied", "note": "Hội viên không ở trạng thái hoạt động.", "session_id": None}
    session = AttendanceSession(
        customer_id=customer.id,
        checked_in_at=event_time,
        source="dah",
        result="allowed",
        status="open",
        note=f"DAH {device.code}" if device else "DAH",
    )
    db.add(session)
    db.flush()
    return {"status": "processed", "action": "checkin", "note": "Check-in hội viên.", "session_id": session.id}


def heartbeat(db: Session, payload: dict):
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    device = _device(db, info)
    if device:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        operator_info = data.get("OperatorInfo") if isinstance(data.get("OperatorInfo"), dict) else {}
        errors = operator_info.get("errorInfo") if isinstance(operator_info.get("errorInfo"), list) else []
        device.status = "online"
        device.last_heartbeat_at = utc_now()
        device.pending_jobs = _int(data.get("TaskId")) or 0
        device.errors_24h = sum(1 for error in errors if _int(error.get("errorcode")) not in (None, 0))
    db.commit()
    return {"code": 0, "message": "OK", "device": device.code if device else None}


def snap(db: Session, payload: dict):
    return _store_non_attendance_event(db, payload, default_operator="SnapPush", status="snapshot", action="snapshot")


def _store_non_attendance_event(db: Session, payload: dict, default_operator: str, status: str, action: str):
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    operator = _clean(payload.get("operator")) or default_operator
    image = _image_data(payload)
    key = _event_key(operator, info, payload, image)
    existing = db.query(DahWebhookEvent).filter(DahWebhookEvent.event_key == key).first()
    if existing:
        return {"code": 0, "message": "DUPLICATE", "eventId": existing.id, "action": "ignored"}
    device = _device(db, info)
    event = DahWebhookEvent(
        event_key=key,
        operator=operator,
        device_id=device.id if device else None,
        person_uuid=_clean(info.get("PersonUUID")),
        person_id=_clean(info.get("PersonID")),
        event_time=_parse_time(info.get("CreateTime") or info.get("Time")),
        status=status,
        action=action,
        image_data=image,
        raw_payload=_payload_json(payload),
    )
    db.add(event)
    db.commit()
    return {"code": 0, "message": "OK", "eventId": event.id, "action": action}


def verify(db: Session, payload: dict):
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    operator = _clean(payload.get("operator")) or "VerifyPush"
    image = _image_data(payload)
    key = _event_key(operator, info, payload, image)
    existing = db.query(DahWebhookEvent).filter(DahWebhookEvent.event_key == key).first()
    if existing:
        return {"code": 0, "message": "DUPLICATE", "eventId": existing.id, "action": "ignored"}

    device = _device(db, info)
    event_time = _parse_time(info.get("CreateTime")) or utc_now()
    verify_status = _int(info.get("VerifyStatus"))
    similarity = _float(info.get("Similarity1"))
    identity, customer, employee, identity_created = _identity_for_uuid(db, device, info, event_time)
    status = "received"
    action = None
    note = None
    session_id = None
    member_session_id = None
    employee_session_id = None

    if verify_status != 1:
        status = "rejected"
        action = "verify_failed"
        note = "DAH xác thực không thành công."
    elif not _clean(info.get("PersonUUID")):
        status = "unknown"
        action = "missing_person_uuid"
        note = "Webhook không có PersonUUID."
    elif not customer and not employee:
        status = "unknown"
        action = "unknown_identity"
        note = "PersonUUID chưa khớp hội viên hoặc nhân viên."
    else:
        if _recent_duplicate_scan(db, _clean(info.get("PersonUUID")), event_time):
            status = "duplicate"
            action = "duplicate_scan"
            note = f"Quét lại trong {DUPLICATE_SCAN_SECONDS} giây."
        else:
            results = []
            if employee:
                employee_result = _toggle_employee_attendance(db, employee, event_time, device)
                employee_session_id = employee_result["session_id"]
                results.append(employee_result)
            if customer:
                customer_result = _toggle_customer_attendance(db, customer, event_time, device, image, identity_created)
                member_session_id = customer_result["session_id"]
                results.append(customer_result)

            processed = [row for row in results if row["status"] == "processed"]
            if processed:
                status = "processed"
                processed_actions = {row["action"] for row in processed}
                action = processed[0]["action"] if len(processed_actions) == 1 else "mixed"
                session_id = member_session_id or employee_session_id
                notes = [row["note"] for row in results if row.get("note")]
                note = " ".join(notes)[:255] if notes else None
            else:
                denied = results[0] if results else {"note": "Không có đối tượng để xử lý."}
                status = denied.get("status") or "denied"
                action = denied.get("action") or "denied"
                note = denied.get("note")

    event = DahWebhookEvent(
        event_key=key,
        operator=operator,
        device_id=device.id if device else None,
        customer_id=customer.id if customer else None,
        employee_id=employee.id if employee else None,
        attendance_session_id=session_id,
        person_uuid=_clean(info.get("PersonUUID")),
        person_id=_clean(info.get("PersonID")),
        verify_status=verify_status,
        similarity=similarity,
        event_time=event_time,
        status=status,
        action=action,
        note=note,
        image_data=image,
        raw_payload=_payload_json(payload),
    )
    db.add(event)
    db.commit()
    return {
        "code": 0,
        "message": "OK",
        "eventId": event.id,
        "action": action,
        "status": status,
        "memberId": customer.id if customer else None,
        "employeeId": employee.id if employee else None,
        "sessionId": session_id,
        "memberSessionId": member_session_id,
        "employeeSessionId": employee_session_id,
    }


def _event_face_name(event: DahWebhookEvent) -> str | None:
    if not event.raw_payload:
        return None
    try:
        payload = json.loads(event.raw_payload)
    except (TypeError, ValueError):
        return None
    info = payload.get("info") if isinstance(payload.get("info"), dict) else {}
    return _clean(info.get("Name"))


def _event_customer_name(event: DahWebhookEvent) -> str | None:
    return event.customer.person.display_name if getattr(event, "customer", None) and event.customer.person else None


def _event_customer_code(event: DahWebhookEvent) -> str | None:
    return event.customer.customer_code if getattr(event, "customer", None) else None


def _event_customer_avatar(event: DahWebhookEvent) -> str | None:
    return event.customer.avatar_image_data if getattr(event, "customer", None) else None


def _event_employee_name(event: DahWebhookEvent) -> str | None:
    return event.employee.person.display_name if getattr(event, "employee", None) and event.employee.person else None


def _event_employee_code(event: DahWebhookEvent) -> str | None:
    return event.employee.employee_code if getattr(event, "employee", None) else None


def _event_data(row: DahWebhookEvent):
    face_name = _event_face_name(row)
    return {
        "id": row.id,
        "operator": row.operator,
        "device": row.device.code if row.device else None,
        "memberId": row.customer_id,
        "memberName": _event_customer_name(row),
        "memberCode": _event_customer_code(row),
        "memberAvatarImageData": _event_customer_avatar(row),
        "employeeId": row.employee_id,
        "employeeName": _event_employee_name(row),
        "employeeCode": _event_employee_code(row),
        "faceName": face_name,
        "personUuid": row.person_uuid,
        "personId": row.person_id,
        "verifyStatus": row.verify_status,
        "similarity": row.similarity,
        "eventTime": row.event_time.isoformat() if row.event_time else None,
        "receivedAt": row.received_at.isoformat() if row.received_at else None,
        "status": row.status,
        "action": row.action,
        "note": row.note,
        "imageData": row.image_data,
    }


def dah_events(db: Session, view="all", limit=50):
    query = (
        db.query(DahWebhookEvent)
        .options(
            joinedload(DahWebhookEvent.device),
            joinedload(DahWebhookEvent.customer).joinedload(Customer.person),
            joinedload(DahWebhookEvent.employee).joinedload(Employee.person),
        )
        .order_by(DahWebhookEvent.event_time.desc(), DahWebhookEvent.received_at.desc())
    )
    if view == "allowed":
        query = query.filter(DahWebhookEvent.status == "processed")
    elif view == "denied":
        query = query.filter(DahWebhookEvent.status.in_(("denied", "rejected")))
    elif view == "unknown":
        query = query.filter(DahWebhookEvent.status == "unknown")
    elif view == "duplicates":
        query = query.filter(DahWebhookEvent.action == "duplicate_scan")
    elif view == "snapshots":
        query = query.filter(DahWebhookEvent.operator == "SnapPush")
    rows = query.limit(max(min(int(limit or 50), 100), 1)).all()
    return {"items": [_event_data(row) for row in rows]}


def cleanup_webhook_images(db: Session, retention_days: int = WEBHOOK_IMAGE_RETENTION_DAYS):
    cutoff = utc_now() - timedelta(days=max(int(retention_days or WEBHOOK_IMAGE_RETENTION_DAYS), 1))
    count = (
        db.query(DahWebhookEvent)
        .filter(
            DahWebhookEvent.image_data.is_not(None),
            DahWebhookEvent.received_at < cutoff,
        )
        .update({DahWebhookEvent.image_data: None}, synchronize_session=False)
    )
    db.commit()
    return count


def identity_candidates(db: Session, limit=12, target_type="member"):
    limit = max(min(int(limit or 12), 30), 1)
    target_type = target_type if target_type in {"member", "employee"} else "member"
    rows = (
        db.query(DahWebhookEvent)
        .options(joinedload(DahWebhookEvent.device))
        .filter(
            DahWebhookEvent.operator == "VerifyPush",
            DahWebhookEvent.person_uuid.is_not(None),
        )
        .order_by(DahWebhookEvent.event_time.desc(), DahWebhookEvent.received_at.desc())
        .limit(limit * 5)
        .all()
    )
    uuids = {row.person_uuid for row in rows if row.person_uuid}
    assigned = set()
    if uuids:
        if target_type == "employee":
            assigned.update(
                uuid for (uuid,) in db.query(DahCustomerIdentity.person_uuid)
                .filter(DahCustomerIdentity.employee_id.is_not(None), DahCustomerIdentity.person_uuid.in_(uuids))
                .all()
            )
        else:
            assigned.update(
                uuid for (uuid,) in db.query(DahCustomerIdentity.person_uuid)
                .filter(DahCustomerIdentity.customer_id.is_not(None), DahCustomerIdentity.person_uuid.in_(uuids))
                .all()
            )
            assigned.update(
                uuid for (uuid,) in db.query(Customer.person_uuid)
                .filter(Customer.person_uuid.in_(uuids))
                .all()
            )
    seen = set()
    candidates = []
    for row in rows:
        if row.person_uuid in seen or row.person_uuid in assigned:
            continue
        seen.add(row.person_uuid)
        candidates.append({
            "eventId": row.id,
            "personUuid": row.person_uuid,
            "personId": row.person_id,
            "name": _event_face_name(row),
            "device": row.device.code if row.device else None,
            "similarity": row.similarity,
            "eventTime": row.event_time.isoformat() if row.event_time else None,
            "imageData": row.image_data,
        })
        if len(candidates) >= limit:
            break
    return {"items": candidates}


def assign_identity_to_customer(db: Session, customer_id: int, event_id: int):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Không tìm thấy hội viên.")
    event = db.query(DahWebhookEvent).filter(DahWebhookEvent.id == event_id).first()
    if not event or event.operator != "VerifyPush" or not event.person_uuid:
        raise HTTPException(422, "Định danh DAH không hợp lệ.")
    existing_identity = db.query(DahCustomerIdentity).filter(DahCustomerIdentity.person_uuid == event.person_uuid).first()
    duplicate_customer = db.query(Customer).filter(Customer.person_uuid == event.person_uuid, Customer.id != customer.id).first()
    if (existing_identity and existing_identity.customer_id and existing_identity.customer_id != customer.id) or duplicate_customer:
        raise HTTPException(409, "PersonUUID này đã được gán cho hội viên khác.")
    if customer.person_uuid and customer.person_uuid != event.person_uuid:
        raise HTTPException(409, "Hội viên đã có định danh DAH khác.")

    identity = existing_identity or DahCustomerIdentity(person_uuid=event.person_uuid)
    identity.customer_id = customer.id
    identity.device_id = event.device_id or identity.device_id
    identity.person_id = event.person_id or identity.person_id
    identity.face_name = _event_face_name(event) or identity.face_name
    identity.last_seen_at = event.event_time or event.received_at
    customer.person_uuid = event.person_uuid
    if event.image_data:
        customer.avatar_image_data = event.image_data
    event.customer_id = customer.id
    event.status = "linked"
    event.action = "identity_linked"
    event.note = "Định danh DAH đã được gán thủ công."
    event.image_data = None
    db.add(identity)
    db.commit()
    return {
        "memberId": customer.id,
        "personUuid": customer.person_uuid,
        "avatarImageData": customer.avatar_image_data,
    }


def assign_identity_to_employee(db: Session, employee_id: int, event_id: int):
    employee = db.query(Employee).options(joinedload(Employee.person)).filter(Employee.id == employee_id).first()
    if not employee:
        raise HTTPException(404, "Không tìm thấy nhân viên.")
    event = db.query(DahWebhookEvent).filter(DahWebhookEvent.id == event_id).first()
    if not event or event.operator != "VerifyPush" or not event.person_uuid:
        raise HTTPException(422, "Định danh DAH không hợp lệ.")
    existing_identity = db.query(DahCustomerIdentity).filter(DahCustomerIdentity.person_uuid == event.person_uuid).first()
    if existing_identity and existing_identity.employee_id and existing_identity.employee_id != employee.id:
        raise HTTPException(409, "PersonUUID này đã được gán cho nhân viên khác.")

    old_links = db.query(DahCustomerIdentity).filter(DahCustomerIdentity.employee_id == employee.id).all()
    for old_link in old_links:
        if old_link.person_uuid == event.person_uuid:
            continue
        if old_link.customer_id:
            old_link.employee_id = None
        else:
            db.delete(old_link)

    identity = existing_identity or DahCustomerIdentity(person_uuid=event.person_uuid)
    identity.employee_id = employee.id
    identity.device_id = event.device_id or identity.device_id
    identity.person_id = event.person_id or identity.person_id
    identity.face_name = _event_face_name(event) or identity.face_name
    identity.last_seen_at = event.event_time or event.received_at
    event.employee_id = employee.id
    event.status = "linked"
    event.action = "employee_identity_linked"
    event.note = "Định danh DAH đã được gán cho nhân viên."
    event.image_data = None
    db.add(identity)
    db.commit()
    return {
        "employeeId": employee.id,
        "employeeName": employee.person.display_name,
        "personUuid": identity.person_uuid,
        "personId": identity.person_id,
        "faceName": identity.face_name,
    }
