import os
from pathlib import Path
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GYM_ENV", "test")
os.environ.setdefault(
    "GYM_DATABASE_PATH",
    str(Path(tempfile.mkdtemp(prefix="pulsefit-member-code-tests-")) / "bootstrap.sqlite3"),
)


def make_session(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'members.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_customer(db, code, name, phone):
    from server.models import Customer, Person

    person = Person(display_name=name, phone=phone, status="active")
    db.add(person)
    db.flush()
    db.add(Customer(person_id=person.id, customer_code=code, status="active"))
    db.commit()


def test_created_member_uses_next_timesoft_style_customer_code(tmp_path):
    from server.models import Customer
    from server.services.members_service import create_member

    db = make_session(tmp_path)
    try:
        seed_customer(db, "CUS0001368", "Existing Member", "0900000001")
        seed_customer(db, "CUST-9999", "Legacy Local", "0900000002")
        seed_customer(db, "MB-999999", "Old App Code", "0900000003")

        member = create_member(db, {
            "name": "New Member",
            "phone": "0900000004",
            "status": "active",
        })

        assert member["code"] == "CUS0001369"
        assert member["source"] is None
        assert db.get(Customer, member["id"]).customer_code == "CUS0001369"
    finally:
        db.close()


def test_newest_sort_uses_customer_code_number(tmp_path):
    from server.services.members_service import list_members

    db = make_session(tmp_path)
    try:
        seed_customer(db, "CUS0001368", "Newest Code", "0900000001")
        seed_customer(db, "CUS0000002", "Older Code", "0900000002")
        seed_customer(db, "MB-999999", "Old App Code", "0900000003")

        data = list_members(db, q="", member_status="all", page=1, page_size=20, sort="newest")

        assert [row["code"] for row in data["items"]] == [
            "CUS0001368",
            "CUS0000002",
            "MB-999999",
        ]
    finally:
        db.close()


def test_created_member_without_regular_membership_stays_lead(tmp_path):
    from server.models import Customer, Employee, Person
    from server.services.members_service import create_member

    db = make_session(tmp_path)
    try:
        member = create_member(db, {
            "name": "No Package",
            "phone": "0900000010",
        })
        assert member["status"] == "lead"
        assert db.get(Customer, member["id"]).status == "lead"

        coach_person = Person(display_name="Coach Only", phone="0900000011", status="active")
        db.add(coach_person)
        db.flush()
        coach = Employee(person_id=coach_person.id, employee_code="EMP-00001", job_title="Coach", status="active")
        db.add(coach)
        db.commit()

        pt_member = create_member(db, {
            "name": "PT Only",
            "phone": "0900000012",
            "ptEnrollment": {
                "coachIds": [coach.id],
                "type": "1:1",
                "totalSessions": 12,
                "startsAt": "2026-08-01",
            },
        })
        assert pt_member["status"] == "lead"
        assert db.get(Customer, pt_member["id"]).status == "lead"
    finally:
        db.close()
