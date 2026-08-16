import math
import random

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models import CheckinSpeechConfig, CheckinSpeechEvent, CheckinSpeechPattern, User
from ..timeutils import utc_iso
from .audit_service import record_audit


DEFAULT_PATTERNS = [
    "Chào {name}, chúc bạn có một buổi tập thật sung sức!",
    "{name} đã check-in. Hôm nay mình cùng cố gắng nhé!",
    "Xin chào {name}, một buổi tập tốt đang chờ bạn!",
]


def _number_setting(payload: dict, key: str, minimum: float, maximum: float, default: float):
    try:
        value = float(payload.get(key, default))
    except (TypeError, ValueError):
        raise HTTPException(422, f"Giá trị {key} không hợp lệ.")
    if not math.isfinite(value) or value < minimum or value > maximum:
        raise HTTPException(422, f"Giá trị {key} phải từ {minimum:g} đến {maximum:g}.")
    return round(value, 2)


def ensure_checkin_speech_settings(db: Session):
    config = db.get(CheckinSpeechConfig, 1)
    if not config:
        config = CheckinSpeechConfig(id=1, enabled=False)
        db.add(config)
    if db.query(CheckinSpeechPattern).count() == 0:
        db.add_all([
            CheckinSpeechPattern(text=text, person_type="all", is_active=True, sort_order=index)
            for index, text in enumerate(DEFAULT_PATTERNS)
        ])
    db.flush()
    return config


def speech_settings_data(db: Session):
    config = ensure_checkin_speech_settings(db)
    patterns = db.query(CheckinSpeechPattern).order_by(CheckinSpeechPattern.sort_order, CheckinSpeechPattern.id).all()
    return {
        "enabled": config.enabled,
        "voiceUri": config.voice_uri or "",
        "voiceName": config.voice_name or "",
        "volume": config.volume if config.volume is not None else 1.0,
        "rate": config.rate if config.rate is not None else 1.0,
        "pitch": config.pitch if config.pitch is not None else 1.0,
        "placeholder": "{name}",
        "patterns": [{
            "id": row.id,
            "text": row.text,
            "personType": row.person_type,
            "active": row.is_active,
        } for row in patterns],
        "updatedAt": utc_iso(config.updated_at),
    }


def update_speech_settings(db: Session, payload: dict, actor: User):
    config = ensure_checkin_speech_settings(db)
    voice_uri = str(payload.get("voiceUri") or "").strip()[:300]
    voice_name = str(payload.get("voiceName") or "").strip()[:200]
    volume = _number_setting(payload, "volume", 0, 1, 1)
    rate = _number_setting(payload, "rate", 0.5, 2, 1)
    pitch = _number_setting(payload, "pitch", 0.5, 2, 1)
    raw_patterns = payload.get("patterns")
    if not isinstance(raw_patterns, list):
        raise HTTPException(422, "Danh sách câu nói không hợp lệ.")
    normalized = []
    for index, item in enumerate(raw_patterns):
        text = str((item or {}).get("text") or "").strip()
        if not text:
            continue
        if len(text) > 500:
            raise HTTPException(422, f"Câu nói số {index + 1} vượt quá 500 ký tự.")
        unknown_tokens = [part.split("}", 1)[0] for part in text.split("{")[1:] if "}" in part and part.split("}", 1)[0] != "name"]
        if unknown_tokens:
            raise HTTPException(422, f"Câu nói số {index + 1} có biến không hỗ trợ. Chỉ dùng {{name}}.")
        normalized.append({"id": item.get("id"), "text": text, "active": bool(item.get("active", True))})
    if not normalized:
        raise HTTPException(422, "Cần giữ lại ít nhất một câu nói.")
    if bool(payload.get("enabled")) and not any(row["active"] for row in normalized):
        raise HTTPException(422, "Cần bật ít nhất một câu nói trước khi bật phát âm.")
    existing = {row.id: row for row in db.query(CheckinSpeechPattern).all()}
    retained = set()
    for index, item in enumerate(normalized):
        pattern_id = item["id"]
        row = existing.get(int(pattern_id)) if str(pattern_id or "").isdigit() else None
        if not row:
            row = CheckinSpeechPattern(
                text=item["text"],
                person_type="all",
                is_active=item["active"],
                sort_order=index,
            )
            db.add(row)
            db.flush()
        row.text = item["text"]
        row.is_active = item["active"]
        row.sort_order = index
        retained.add(row.id)
    for row_id, row in existing.items():
        if row_id not in retained:
            db.delete(row)
    config.enabled = bool(payload.get("enabled"))
    config.voice_uri = voice_uri or None
    config.voice_name = voice_name or None
    config.volume = volume
    config.rate = rate
    config.pitch = pitch
    config.updated_by_user_id = actor.id
    record_audit(db, actor, "update", "checkin_speech", config.id, "Cập nhật lời chào check-in", details={"enabled": config.enabled, "voiceName": config.voice_name, "volume": volume, "rate": rate, "pitch": pitch, "patterns": len(normalized), "activePatterns": sum(row["active"] for row in normalized)})
    db.commit()
    return speech_settings_data(db)


def queue_checkin_speech(db: Session, attendance_session_id: int | None, person_type: str, person_name: str | None):
    if not attendance_session_id or not person_name:
        return None
    if db.query(CheckinSpeechEvent).filter(CheckinSpeechEvent.attendance_session_id == attendance_session_id).first():
        return None
    config = ensure_checkin_speech_settings(db)
    if not config.enabled:
        return None
    patterns = db.query(CheckinSpeechPattern).filter(
        CheckinSpeechPattern.is_active == True,
        CheckinSpeechPattern.person_type.in_(("all", person_type)),
    ).all()
    if not patterns:
        return None
    pattern = random.choice(patterns)
    message = pattern.text.replace("{name}", person_name).strip()
    row = CheckinSpeechEvent(attendance_session_id=attendance_session_id, person_type=person_type, person_name=person_name, message=message)
    db.add(row)
    db.flush()
    return row


def speech_event_data(row: CheckinSpeechEvent):
    return {"id": row.id, "sessionId": row.attendance_session_id, "personType": row.person_type, "personName": row.person_name, "message": row.message, "createdAt": utc_iso(row.created_at)}
