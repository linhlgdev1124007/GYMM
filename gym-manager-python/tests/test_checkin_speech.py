import os
from pathlib import Path
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GYM_ENV", "test")
os.environ.setdefault("GYM_DATABASE_PATH", str(Path(tempfile.mkdtemp(prefix="pulsefit-speech-tests-")) / "bootstrap.sqlite3"))


def make_session(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'speech.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_checkin_speech_is_disabled_by_default_and_replaces_name(tmp_path, monkeypatch):
    from server.models import AttendanceSession, CheckinSpeechEvent, User
    from server.services.checkin_speech_service import queue_checkin_speech, speech_settings_data, update_speech_settings
    from server.timeutils import utc_now

    db = make_session(tmp_path)
    try:
        actor = User(username="speech-admin", display_name="Speech Admin", password_hash="test", role="admin", is_active=True)
        session = AttendanceSession(checked_in_at=utc_now(), source="manual", result="allowed", status="open")
        db.add_all([actor, session])
        db.commit()

        assert queue_checkin_speech(db, session.id, "member", "Trần An") is None
        update_speech_settings(db, {
            "enabled": True,
            "voiceUri": "voice:vi-VN-test",
            "voiceName": "Vietnamese Test Voice",
            "volume": 0.65,
            "rate": 1.15,
            "pitch": 0.9,
            "patterns": [{"text": "Xin chào {name}, tập tốt nhé!", "active": True}],
        }, actor)
        settings = speech_settings_data(db)
        assert settings["voiceUri"] == "voice:vi-VN-test"
        assert settings["voiceName"] == "Vietnamese Test Voice"
        assert settings["volume"] == pytest.approx(0.65)
        assert settings["rate"] == pytest.approx(1.15)
        assert settings["pitch"] == pytest.approx(0.9)
        monkeypatch.setattr("server.services.checkin_speech_service.random.choice", lambda rows: rows[0])
        event = queue_checkin_speech(db, session.id, "member", "Trần An")
        db.commit()

        assert event.message == "Xin chào Trần An, tập tốt nhé!"
        assert db.query(CheckinSpeechEvent).count() == 1
        assert queue_checkin_speech(db, session.id, "member", "Trần An") is None
    finally:
        db.close()


def test_checkin_speech_rejects_unknown_placeholders_and_inactive_list(tmp_path):
    from fastapi import HTTPException
    from server.models import User
    from server.services.checkin_speech_service import update_speech_settings

    db = make_session(tmp_path)
    try:
        actor = User(username="speech-admin-2", display_name="Speech Admin", password_hash="test", role="admin", is_active=True)
        db.add(actor)
        db.commit()
        with pytest.raises(HTTPException) as unknown:
            update_speech_settings(db, {"enabled": True, "patterns": [{"text": "Chào {phone}", "active": True}]}, actor)
        assert unknown.value.status_code == 422
        db.rollback()
        with pytest.raises(HTTPException) as inactive:
            update_speech_settings(db, {"enabled": True, "patterns": [{"text": "Chào {name}", "active": False}]}, actor)
        assert inactive.value.status_code == 422
        db.rollback()
        with pytest.raises(HTTPException) as invalid_volume:
            update_speech_settings(db, {"enabled": True, "volume": 1.5, "patterns": [{"text": "Chào {name}", "active": True}]}, actor)
        assert invalid_volume.value.status_code == 422
    finally:
        db.close()
