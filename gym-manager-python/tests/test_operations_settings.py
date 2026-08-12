import os
from pathlib import Path
import tempfile
from datetime import date, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GYM_ENV", "test")
os.environ.setdefault(
    "GYM_DATABASE_PATH",
    str(Path(tempfile.mkdtemp(prefix="pulsefit-operations-tests-")) / "bootstrap.sqlite3"),
)


def make_session(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'settings.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def active_titles(db):
    from server.models import EmployeeJobTitle

    return {
        row.name
        for row in db.query(EmployeeJobTitle)
        .filter(EmployeeJobTitle.is_active == True)
        .all()
    }


def test_renaming_default_job_title_does_not_recreate_old_name(tmp_path):
    from server.models import EmployeeJobTitle
    from server.services.operations_service import (
        ensure_employee_job_titles,
        update_job_title,
    )

    db = make_session(tmp_path)
    try:
        ensure_employee_job_titles(db)
        db.commit()
        sale = db.query(EmployeeJobTitle).filter(EmployeeJobTitle.name == "Sale").one()

        update_job_title(db, sale.id, {"name": "sale f", "renameEmployees": True})
        ensure_employee_job_titles(db)
        db.commit()

        names = active_titles(db)
        assert "sale f" in names
        assert "Sale" not in names
    finally:
        db.close()


def test_deleting_default_job_title_does_not_recreate_it(tmp_path):
    from server.models import EmployeeJobTitle
    from server.services.operations_service import (
        delete_job_title,
        ensure_employee_job_titles,
    )

    db = make_session(tmp_path)
    try:
        ensure_employee_job_titles(db)
        db.commit()
        marketing = db.query(EmployeeJobTitle).filter(EmployeeJobTitle.name == "Marketing").one()

        delete_job_title(db, marketing.id)
        ensure_employee_job_titles(db)
        db.commit()

        assert "Marketing" not in active_titles(db)
    finally:
        db.close()


def test_settings_returns_single_dah1017_with_heartbeat_status(tmp_path):
    from server.models import Device
    from server.services.operations_service import settings
    from server.timeutils import utc_now

    db = make_session(tmp_path)
    try:
        db.add(Device(code="OLD-GATE", name="Old Gate", model="Other", status="online"))
        db.add(Device(code="DAH-2470802", name="DAH 2470802", model="DAH1017", status="online", last_heartbeat_at=utc_now() - timedelta(seconds=120)))
        db.commit()

        data = settings(db)
        assert len(data["devices"]) == 1
        assert data["devices"][0]["name"] == "DAH1017"
        assert data["devices"][0]["status"] == "offline"

        db.query(Device).filter(Device.code == "DAH-2470802").one().last_heartbeat_at = utc_now()
        db.commit()
        assert settings(db)["devices"][0]["status"] == "online"
    finally:
        db.close()


def test_trainers_show_pt_client_status_counts_only_for_pt_roles(tmp_path):
    from server.models import Customer, Employee, Person, PtEnrollment, PtEnrollmentCoach
    from server.services.operations_service import ensure_employee_job_titles, list_trainers

    db = make_session(tmp_path)
    try:
        coach_person = Person(display_name="Coach One", phone="0900000001", status="active")
        sale_person = Person(display_name="Sale One", phone="0900000002", status="active")
        active_member_person = Person(display_name="Active PT Member", phone="0900000003", status="active")
        expired_member_person = Person(display_name="Expired PT Member", phone="0900000004", status="active")
        db.add_all([coach_person, sale_person, active_member_person, expired_member_person])
        db.flush()

        coach = Employee(person_id=coach_person.id, employee_code="EMP-00001", job_title="Coach", status="active")
        sale = Employee(person_id=sale_person.id, employee_code="EMP-00002", job_title="Sale", status="active")
        active_member = Customer(person_id=active_member_person.id, customer_code="CUS0000001", status="active")
        expired_member = Customer(person_id=expired_member_person.id, customer_code="CUS0000002", status="active")
        db.add_all([coach, sale, active_member, expired_member])
        db.flush()

        active = PtEnrollment(
            customer_id=active_member.id,
            group_type="1:1",
            starts_at=date(2026, 8, 1),
            expires_at=date(2026, 9, 1),
            total_sessions=12,
            remaining_sessions=12,
            status="active",
        )
        expired = PtEnrollment(
            customer_id=expired_member.id,
            group_type="1:1",
            starts_at=date(2026, 6, 1),
            expires_at=date(2026, 7, 1),
            total_sessions=12,
            remaining_sessions=0,
            status="active",
        )
        db.add_all([active, expired])
        db.flush()
        db.add_all([
            PtEnrollmentCoach(enrollment_id=active.id, coach_id=coach.id),
            PtEnrollmentCoach(enrollment_id=expired.id, coach_id=coach.id),
        ])
        ensure_employee_job_titles(db)
        db.commit()

        rows = {row["name"]: row for row in list_trainers(db, q="", title="all", page=1, page_size=20)["items"]}

        assert rows["Coach One"]["isPtRole"] is True
        assert rows["Coach One"]["registeredPtClients"] == 2
        assert rows["Coach One"]["activePtClients"] == 1
        assert rows["Coach One"]["expiredPtClients"] == 1
        assert "ptSessions" not in rows["Coach One"]
        assert rows["Sale One"]["isPtRole"] is False
        assert rows["Sale One"]["registeredPtClients"] is None
        assert rows["Sale One"]["activePtClients"] is None
        assert rows["Sale One"]["expiredPtClients"] is None
    finally:
        db.close()


def test_employee_attendance_returns_multiple_shifts_in_one_day(tmp_path):
    from server.models import AttendanceSession, Employee, Person
    from server.services.operations_service import employee_attendance

    db = make_session(tmp_path)
    try:
        person = Person(display_name="Coach Shift", phone="0900000010", status="active")
        db.add(person)
        db.flush()
        employee = Employee(person_id=person.id, employee_code="EMP-00010", job_title="Coach", status="active")
        db.add(employee)
        db.flush()
        db.add_all([
            AttendanceSession(
                employee_id=employee.id,
                checked_in_at=datetime(2026, 8, 12, 8, 0),
                checked_out_at=datetime(2026, 8, 12, 12, 0),
                source="dah",
                status="closed",
            ),
            AttendanceSession(
                employee_id=employee.id,
                checked_in_at=datetime(2026, 8, 12, 14, 0),
                checked_out_at=datetime(2026, 8, 12, 18, 30),
                source="dah",
                status="closed",
            ),
        ])
        db.commit()

        data = employee_attendance(db, "2026-08-12")

        assert [row["shiftNo"] for row in data["items"]] == [1, 2]
        assert [row["durationMinutes"] for row in data["items"]] == [240, 270]
        assert all(row["employeeId"] == employee.id for row in data["items"])
    finally:
        db.close()


def test_recent_checkins_filters_by_day_and_paginates(tmp_path):
    from server.models import AttendanceSession, Customer, Person
    from server.services.operations_service import recent_checkins

    db = make_session(tmp_path)
    try:
        person = Person(display_name="Checkin Member", phone="0900000020", status="active")
        db.add(person)
        db.flush()
        member = Customer(person_id=person.id, customer_code="CUS0000020", status="active")
        db.add(member)
        db.flush()
        db.add_all([
            AttendanceSession(
                customer_id=member.id,
                checked_in_at=datetime(2026, 8, 12, 9, 0),
                source="dah",
                status="open",
            ),
            AttendanceSession(
                customer_id=member.id,
                checked_in_at=datetime(2026, 8, 12, 8, 0),
                checked_out_at=datetime(2026, 8, 12, 10, 0),
                source="dah",
                status="closed",
            ),
            AttendanceSession(
                customer_id=member.id,
                checked_in_at=datetime(2026, 8, 11, 9, 0),
                source="dah",
                status="closed",
            ),
            AttendanceSession(
                customer_id=member.id,
                checked_in_at=datetime(2026, 8, 11, 22, 0),
                source="dah",
                status="open",
            ),
            AttendanceSession(
                customer_id=member.id,
                checked_in_at=datetime(2026, 8, 10, 22, 0),
                source="dah",
                status="open",
            ),
        ])
        db.commit()

        first_page = recent_checkins(db, day="2026-08-12", page=1, page_size=2)
        second_page = recent_checkins(db, day="2026-08-12", page=2, page_size=2)

        assert first_page["date"] == "2026-08-12"
        assert first_page["activeCount"] == 2
        assert first_page["pagination"]["total"] == 3
        assert [row["status"] for row in first_page["items"]] == ["open", "open"]
        assert second_page["items"][0]["status"] == "closed"
        assert recent_checkins(db, day="2026-08-11", page=1, page_size=20)["pagination"]["total"] == 3
    finally:
        db.close()


def test_recent_checkins_flags_members_with_membership_warnings(tmp_path):
    from server.models import AttendanceSession, Customer, Membership, Person, ServicePackage
    from server.services.operations_service import recent_checkins

    db = make_session(tmp_path)
    try:
        person = Person(display_name="Pending Checkin", phone="0900000021", status="active")
        db.add(person)
        db.flush()
        member = Customer(person_id=person.id, customer_code="CUS0000021", status="lead")
        plan = ServicePackage(
            code="FIT-WARN",
            name="Fitness Warning",
            category="Fitness",
            duration_days=30,
            price=100000,
            is_pt=False,
            is_active=True,
        )
        db.add_all([member, plan])
        db.flush()
        membership = Membership(
            customer_id=member.id,
            package_id=plan.id,
            code="MS-WARN",
            registered_at=date(2026, 8, 1),
            starts_at=date(2026, 8, 20),
            expires_at=date(2026, 9, 19),
            activated_at=None,
            status="pending",
        )
        checkin = AttendanceSession(
            customer_id=member.id,
            checked_in_at=datetime(2026, 8, 12, 9, 0),
            source="dah",
            status="open",
        )
        db.add_all([membership, checkin])
        db.commit()

        data = recent_checkins(db, day="2026-08-12", page=1, page_size=20)

        assert data["items"][0]["memberAccessWarning"] == "Gói đang chờ kích hoạt."
    finally:
        db.close()
