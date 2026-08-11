from datetime import date, datetime
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import or_
from sqlalchemy.orm import Session, joinedload

from ..models import (
    AttendanceSession, Customer, DahCustomerIdentity, DahWebhookEvent,
    Device, Membership, ServicePackage,
)
from ..timeutils import utc_now

HEARTBEAT_TIMEOUT_SECONDS = 90
DAH_MODEL = "DAH1017"


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
            or_(Membership.expires_at == None, Membership.expires_at >= date.today()),
        )
        .order_by(Membership.expires_at.desc(), Membership.id.desc())
        .first()
    )


def _identity_for_uuid(db: Session, device: Device | None, info: dict, event_time: datetime | None):
    person_uuid = _clean(info.get("PersonUUID"))
    if not person_uuid:
        return None, None, False
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
        customer = db.get(Customer, identity.customer_id)
        if customer and not customer.person_uuid:
            customer.person_uuid = person_uuid
        return identity, customer, False

    customer = db.query(Customer).filter(Customer.person_uuid == person_uuid).first()
    if not customer:
        return None, None, False
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
    return identity, customer, True


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
        image_data=None,
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
    identity, customer, identity_created = _identity_for_uuid(db, device, info, event_time)
    status = "received"
    action = None
    note = None
    session_id = None

    if verify_status != 1:
        status = "rejected"
        action = "verify_failed"
        note = "DAH xác thực không thành công."
    elif not _clean(info.get("PersonUUID")):
        status = "unknown"
        action = "missing_person_uuid"
        note = "Webhook không có PersonUUID."
    elif not customer:
        status = "unknown"
        action = "unknown_identity"
        note = "PersonUUID chưa khớp hội viên."
    else:
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
            status = "processed"
            action = "checkout"
            session_id = open_session.id
        elif not _active_regular_membership(db, customer.id):
            status = "denied"
            action = "denied"
            note = "Hội viên không có gói tập còn hiệu lực."
        elif customer.status != "active":
            status = "denied"
            action = "denied"
            note = "Hội viên không ở trạng thái hoạt động."
        else:
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
            status = "processed"
            action = "checkin"
            session_id = session.id

    event_image = image if status == "unknown" and action == "unknown_identity" else None
    event = DahWebhookEvent(
        event_key=key,
        operator=operator,
        device_id=device.id if device else None,
        customer_id=customer.id if customer else None,
        attendance_session_id=session_id,
        person_uuid=_clean(info.get("PersonUUID")),
        person_id=_clean(info.get("PersonID")),
        verify_status=verify_status,
        similarity=similarity,
        event_time=event_time,
        status=status,
        action=action,
        note=note,
        image_data=event_image,
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
        "sessionId": session_id,
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


def identity_candidates(db: Session, limit=12):
    assigned_identity = (
        db.query(DahCustomerIdentity.id)
        .filter(DahCustomerIdentity.person_uuid == DahWebhookEvent.person_uuid)
        .exists()
    )
    assigned_customer = (
        db.query(Customer.id)
        .filter(Customer.person_uuid == DahWebhookEvent.person_uuid)
        .exists()
    )
    rows = (
        db.query(DahWebhookEvent)
        .options(joinedload(DahWebhookEvent.device))
        .filter(
            DahWebhookEvent.operator == "VerifyPush",
            DahWebhookEvent.person_uuid.is_not(None),
            ~assigned_identity,
            ~assigned_customer,
        )
        .order_by(DahWebhookEvent.event_time.desc(), DahWebhookEvent.received_at.desc())
        .limit(max(min(int(limit or 12), 30), 1))
        .all()
    )
    seen = set()
    candidates = []
    for row in rows:
        if row.person_uuid in seen:
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
    return {"items": candidates}


def assign_identity_to_customer(db: Session, customer_id: int, event_id: int):
    customer = db.get(Customer, customer_id)
    if not customer:
        raise HTTPException(404, "Không tìm thấy hội viên.")
    event = db.query(DahWebhookEvent).filter(DahWebhookEvent.id == event_id).first()
    if not event or event.operator != "VerifyPush" or not event.person_uuid:
        raise HTTPException(422, "Định danh DAH không hợp lệ.")
    duplicate_identity = db.query(DahCustomerIdentity).filter(DahCustomerIdentity.person_uuid == event.person_uuid).first()
    duplicate_customer = db.query(Customer).filter(Customer.person_uuid == event.person_uuid, Customer.id != customer.id).first()
    if duplicate_identity or duplicate_customer:
        raise HTTPException(409, "PersonUUID này đã được gán cho hội viên khác.")
    if customer.person_uuid and customer.person_uuid != event.person_uuid:
        raise HTTPException(409, "Hội viên đã có định danh DAH khác.")

    identity = DahCustomerIdentity(
        customer_id=customer.id,
        device_id=event.device_id,
        person_uuid=event.person_uuid,
        person_id=event.person_id,
        face_name=_event_face_name(event),
        last_seen_at=event.event_time or event.received_at,
    )
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
