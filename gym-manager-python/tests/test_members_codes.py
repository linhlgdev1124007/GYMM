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


def test_created_members_can_share_parent_phone(tmp_path):
    from server.models import Customer
    from server.services.members_service import create_member

    db = make_session(tmp_path)
    try:
        phone = "0900000099"
        older = create_member(db, {
            "name": "Anh Nguyen",
            "phone": phone,
        })
        younger = create_member(db, {
            "name": "Em Nguyen",
            "phone": phone,
        })

        assert older["phone"] == phone
        assert younger["phone"] == phone
        assert older["id"] != younger["id"]
        assert db.query(Customer).join(Customer.person).filter_by(phone=phone).count() == 2
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


def test_expired_member_sort_orders_by_days_expired(tmp_path):
    from datetime import date

    from server.models import Customer, Membership, ServicePackage
    from server.services.members_service import list_members
    from server.timeutils import set_test_today

    db = make_session(tmp_path)
    try:
        set_test_today(date(2026, 8, 21))
        plan = ServicePackage(
            code="EXPIRED",
            name="Expired Plan",
            category="Gym",
            duration_days=30,
            price=1000,
            is_pt=False,
        )
        db.add(plan)
        db.commit()

        seed_customer(db, "CUS0000001", "Expired Five Days", "0900000101")
        seed_customer(db, "CUS0000002", "Expired One Day", "0900000102")
        seed_customer(db, "CUS0000003", "Expired Two Days", "0900000103")
        customers = {
            row.customer_code: row
            for row in db.query(Customer).all()
        }
        db.add_all([
            Membership(
                customer_id=customers["CUS0000001"].id,
                package_id=plan.id,
                code="MS-EXPIRED-5",
                registered_at=date(2026, 7, 1),
                starts_at=date(2026, 7, 1),
                expires_at=date(2026, 8, 16),
                status="expired",
            ),
            Membership(
                customer_id=customers["CUS0000002"].id,
                package_id=plan.id,
                code="MS-EXPIRED-1",
                registered_at=date(2026, 7, 1),
                starts_at=date(2026, 7, 1),
                expires_at=date(2026, 8, 20),
                status="expired",
            ),
            Membership(
                customer_id=customers["CUS0000003"].id,
                package_id=plan.id,
                code="MS-EXPIRED-2",
                registered_at=date(2026, 7, 1),
                starts_at=date(2026, 7, 1),
                expires_at=date(2026, 8, 19),
                status="expired",
            ),
        ])
        db.commit()

        data = list_members(
            db,
            q="",
            member_status="expired",
            page=1,
            page_size=20,
            sort="expired_days_asc",
        )

        assert [row["code"] for row in data["items"]] == [
            "CUS0000002",
            "CUS0000003",
            "CUS0000001",
        ]
    finally:
        set_test_today(None)
        db.close()


def test_debt_due_sort_orders_members_before_pagination(tmp_path):
    from datetime import date

    from server.models import Customer, Membership, ServicePackage
    from server.services.members_service import list_members
    from server.timeutils import set_test_today

    db = make_session(tmp_path)
    try:
        set_test_today(date(2026, 8, 17))
        plan = ServicePackage(
            code="REGULAR",
            name="Regular",
            category="Gym",
            duration_days=30,
            price=1000,
            is_pt=False,
        )
        db.add(plan)
        db.commit()

        seed_customer(db, "CUS0000001", "Far Due", "0900000001")
        seed_customer(db, "CUS0000002", "No Debt", "0900000002")
        seed_customer(db, "CUS0000003", "Near Due", "0900000003")
        seed_customer(db, "CUS0000004", "Middle Due", "0900000004")
        seed_customer(db, "CUS0000005", "Debt Without Due Date", "0900000005")
        seed_customer(db, "CUS0000006", "Current Debt Older Than Frozen", "0900000006")

        customers = {
            row.customer_code: row
            for row in db.query(Customer).all()
        }
        memberships = [
            Membership(
                customer_id=customers["CUS0000001"].id,
                package_id=plan.id,
                code="M-FAR",
                registered_at=date(2026, 8, 1),
                starts_at=date(2026, 8, 1),
                expires_at=date(2026, 8, 31),
                final_price=1000,
                paid_amount=500,
                debt_amount=500,
                debt_due_date=date(2026, 8, 30),
                status="active",
            ),
            Membership(
                customer_id=customers["CUS0000002"].id,
                package_id=plan.id,
                code="M-NONE",
                registered_at=date(2026, 8, 1),
                starts_at=date(2026, 8, 1),
                expires_at=date(2026, 8, 31),
                final_price=1000,
                paid_amount=1000,
                debt_amount=0,
                status="active",
            ),
            Membership(
                customer_id=customers["CUS0000003"].id,
                package_id=plan.id,
                code="M-NEAR",
                registered_at=date(2026, 8, 1),
                starts_at=date(2026, 8, 1),
                expires_at=date(2026, 8, 31),
                final_price=1000,
                paid_amount=500,
                debt_amount=500,
                debt_due_date=date(2026, 8, 18),
                status="active",
            ),
            Membership(
                customer_id=customers["CUS0000004"].id,
                package_id=plan.id,
                code="M-MIDDLE",
                registered_at=date(2026, 8, 1),
                starts_at=date(2026, 8, 1),
                expires_at=date(2026, 8, 31),
                final_price=1000,
                paid_amount=500,
                debt_amount=500,
                debt_due_date=date(2026, 8, 25),
                status="active",
            ),
            Membership(
                customer_id=customers["CUS0000005"].id,
                package_id=plan.id,
                code="M-NO-DUE",
                registered_at=date(2026, 8, 1),
                starts_at=date(2026, 8, 1),
                expires_at=date(2026, 8, 31),
                final_price=1000,
                paid_amount=500,
                debt_amount=500,
                debt_due_date=None,
                status="active",
            ),
            Membership(
                customer_id=customers["CUS0000006"].id,
                package_id=plan.id,
                code="M-CURRENT-DEBT",
                registered_at=date(2026, 8, 1),
                starts_at=date(2026, 8, 1),
                expires_at=date(2026, 8, 31),
                final_price=1000,
                paid_amount=500,
                debt_amount=500,
                debt_due_date=date(2026, 8, 20),
                status="active",
            ),
            Membership(
                customer_id=customers["CUS0000006"].id,
                package_id=plan.id,
                code="M-NEWER-FROZEN-NO-DEBT",
                registered_at=date(2026, 8, 2),
                starts_at=date(2026, 8, 2),
                expires_at=date(2026, 8, 31),
                final_price=1000,
                paid_amount=1000,
                debt_amount=0,
                debt_due_date=None,
                status="frozen",
            ),
        ]
        db.add_all(memberships)
        db.commit()

        first_page = list_members(
            db,
            q="",
            member_status="all",
            page=1,
            page_size=4,
            sort="debt_due_asc",
        )
        second_page = list_members(
            db,
            q="",
            member_status="all",
            page=2,
            page_size=4,
            sort="debt_due_asc",
        )

        assert [row["code"] for row in first_page["items"]] == [
            "CUS0000003",
            "CUS0000006",
            "CUS0000004",
            "CUS0000001",
        ]
        assert [row["code"] for row in second_page["items"]] == [
            "CUS0000005",
            "CUS0000002",
        ]

        debt_filter = list_members(
            db,
            q="",
            member_status="all",
            page=1,
            page_size=10,
            payment_status="debt",
            sort="debt_due_asc",
        )

        assert [row["code"] for row in debt_filter["items"]] == [
            "CUS0000003",
            "CUS0000006",
            "CUS0000004",
            "CUS0000001",
            "CUS0000005",
        ]

        due_soon = list_members(
            db,
            q="",
            member_status="all",
            page=1,
            page_size=10,
            payment_status="overdue",
            overdue_days=3,
            sort="debt_due_asc",
        )

        assert [row["code"] for row in due_soon["items"]] == [
            "CUS0000003",
            "CUS0000006",
        ]
    finally:
        set_test_today(None)
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


def test_members_can_reuse_mbs_card_code(tmp_path):
    from server.services.members_service import create_member

    db = make_session(tmp_path)
    try:
        first = create_member(db, {
            "name": "First White Card",
            "phone": "0900000021",
            "mbsCode": "THẺ TRẮNG",
        })
        second = create_member(db, {
            "name": "Second White Card",
            "phone": "0900000022",
            "mbsCode": "THẺ TRẮNG",
        })

        assert first["mbsCode"] == "THẺ TRẮNG"
        assert second["mbsCode"] == "THẺ TRẮNG"
    finally:
        db.close()


def test_plan_without_registrations_can_be_deleted(tmp_path):
    from server.models import ServicePackage
    from server.services.members_service import create_plan, delete_plan, list_plans

    db = make_session(tmp_path)
    try:
        plan = create_plan(db, {
            "name": "Delete Me",
            "category": "Fitness",
            "durationDays": 30,
            "price": 100000,
        })

        listed = list_plans(db, include_inactive=True)
        created = next(row for row in listed if row["id"] == plan["id"])
        assert created["canDelete"] is True
        assert created["registrationCount"] == 0

        result = delete_plan(db, plan["id"])

        assert result == {"deleted": True, "id": plan["id"]}
        assert db.get(ServicePackage, plan["id"]) is None
    finally:
        db.close()


def test_plan_with_any_registration_cannot_be_deleted(tmp_path):
    import pytest
    from fastapi import HTTPException
    from datetime import date
    from server.models import Customer, Membership, Person, ServicePackage
    from server.services.members_service import delete_plan, list_plans

    db = make_session(tmp_path)
    try:
        person = Person(display_name="Registered Member", phone="0900000100", status="active")
        db.add(person)
        db.flush()
        customer = Customer(person_id=person.id, customer_code="CUS0000100", status="active")
        plan = ServicePackage(
            code="REGISTERED-PLAN",
            name="Registered Plan",
            category="Fitness",
            duration_days=30,
            price=100000,
            is_pt=False,
            is_active=True,
        )
        db.add_all([customer, plan])
        db.flush()
        membership = Membership(
            customer_id=customer.id,
            package_id=plan.id,
            code="MS-REGISTERED",
            registered_at=date(2026, 8, 1),
            starts_at=date(2026, 8, 1),
            expires_at=date(2026, 8, 31),
            status="cancelled",
        )
        db.add(membership)
        db.commit()

        listed = list_plans(db, include_inactive=True)
        registered = next(row for row in listed if row["id"] == membership.package_id)
        assert registered["canDelete"] is False
        assert registered["registrationCount"] == 1

        with pytest.raises(HTTPException, match="không thể xóa"):
            delete_plan(db, membership.package_id)
    finally:
        db.close()
