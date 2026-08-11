from datetime import date
import os
from pathlib import Path
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GYM_ENV", "test")
os.environ.setdefault(
    "GYM_DATABASE_PATH",
    str(Path(tempfile.mkdtemp(prefix="pulsefit-dah-tests-")) / "bootstrap.sqlite3"),
)


def make_session(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'dah.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_member(db, person_uuid="732"):
    from server.models import Customer, Membership, Person, ServicePackage

    person = Person(display_name="TRAN NGUYEN KHAI HOAN", phone="0900000001", status="active")
    db.add(person)
    db.flush()
    customer = Customer(
        person_id=person.id,
        customer_code="MB-000001",
        person_uuid=person_uuid,
        status="active",
        source="Walk-in",
    )
    package = ServicePackage(
        code="FIT-TEST",
        name="Fitness Test",
        category="Fitness",
        duration_days=30,
        price=100000,
        is_pt=False,
        is_active=True,
    )
    db.add_all([customer, package])
    db.flush()
    db.add(Membership(
        customer_id=customer.id,
        package_id=package.id,
        code="MS-000001",
        registered_at=date(2026, 8, 1),
        starts_at=date(2026, 8, 1),
        expires_at=date(2026, 9, 1),
        status="active",
    ))
    db.commit()
    return customer.id


def verify_payload(create_time, file_pos="1"):
    return {
        "operator": "VerifyPush",
        "info": {
            "DeviceID": 2470802,
            "PersonID": 812,
            "PersonUUID": "732",
            "Name": "TRAN NGUYEN KHAI HOAN",
            "CreateTime": create_time,
            "VerifyStatus": 1,
            "Similarity1": 94.17,
            "RFIDCard": "0",
        },
        "dwFileIndex": "9",
        "dwFilePos": file_pos,
        "SanpPic": "data:image/jpeg;base64,ZmFrZS1pbWFnZQ==",
    }


def test_dah_verify_maps_existing_customer_uuid_updates_avatar_and_toggles(tmp_path):
    from server.models import AttendanceSession, DahCustomerIdentity, DahWebhookEvent, Customer
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db)

        checkin = dah_service.verify(db, verify_payload("2026-08-11T09:00:00", "100"))
        assert checkin["action"] == "checkin"
        assert checkin["memberId"] == customer_id
        assert db.query(DahCustomerIdentity).filter_by(person_uuid="732").count() == 1
        assert db.get(Customer, customer_id).avatar_image_data.startswith("data:image/jpeg;base64,")
        assert db.get(DahWebhookEvent, checkin["eventId"]).image_data is None

        duplicate = dah_service.verify(db, verify_payload("2026-08-11T09:00:00", "100"))
        assert duplicate["action"] == "ignored"
        assert db.query(AttendanceSession).filter_by(customer_id=customer_id).count() == 1
        assert db.query(AttendanceSession).filter_by(customer_id=customer_id, status="open").count() == 1

        repeated_scan = dah_service.verify(db, verify_payload("2026-08-11T09:00:30", "101"))
        assert repeated_scan["action"] == "duplicate_scan"
        assert repeated_scan["status"] == "duplicate"
        assert db.query(AttendanceSession).filter_by(customer_id=customer_id).count() == 1
        assert db.query(AttendanceSession).filter_by(customer_id=customer_id, status="open").count() == 1

        checkout = dah_service.verify(db, verify_payload("2026-08-11T09:10:00", "102"))
        assert checkout["action"] == "checkout"
        session = db.query(AttendanceSession).filter_by(customer_id=customer_id).one()
        assert session.status == "closed"
        assert session.checked_out_at.isoformat() == "2026-08-11T09:10:00"
        assert db.get(DahWebhookEvent, checkout["eventId"]).image_data is None
    finally:
        db.close()


def test_dah_candidate_can_be_assigned_when_creating_member(tmp_path):
    from server.models import Customer, DahCustomerIdentity, DahWebhookEvent
    from server.services import dah_service
    from server.services.members_service import create_member

    db = make_session(tmp_path)
    try:
        unknown = dah_service.verify(db, verify_payload("2026-08-11T10:00:00", "200"))
        assert unknown["status"] == "unknown"

        candidates = dah_service.identity_candidates(db)
        assert len(candidates["items"]) == 1
        event_id = candidates["items"][0]["eventId"]
        assert candidates["items"][0]["imageData"].startswith("data:image/jpeg;base64,")

        member = create_member(db, {
            "name": "Khach DAH",
            "phone": "0900000002",
            "status": "active",
            "dahEventId": event_id,
        })
        customer = db.get(Customer, member["id"])
        event = db.get(DahWebhookEvent, event_id)

        assert member["personUuid"] == "732"
        assert customer.avatar_image_data.startswith("data:image/jpeg;base64,")
        assert db.query(DahCustomerIdentity).filter_by(customer_id=customer.id, person_uuid="732").count() == 1
        assert event.status == "linked"
        assert event.image_data is None
        assert dah_service.identity_candidates(db)["items"] == []
    finally:
        db.close()
