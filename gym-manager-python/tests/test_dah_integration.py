from datetime import date, datetime, timedelta
import os
from pathlib import Path
import tempfile

import pytest
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


def verify_payload_for_uuid(person_uuid, create_time, file_pos="1"):
    payload = verify_payload(create_time, file_pos)
    payload["info"]["PersonUUID"] = person_uuid
    payload["info"]["PersonID"] = person_uuid
    payload["info"]["Name"] = f"FACE {person_uuid}"
    return payload


def verify_payload_for_person_id(person_id, create_time, file_pos="1"):
    payload = verify_payload(create_time, file_pos)
    payload["info"]["PersonUUID"] = " "
    payload["info"]["PersonID"] = person_id
    payload["info"]["Name"] = f"FACE {person_id}"
    return payload


def verify_payload_for_uuid_and_person_id(person_uuid, person_id, create_time, file_pos="1"):
    payload = verify_payload(create_time, file_pos)
    payload["info"]["PersonUUID"] = person_uuid
    payload["info"]["PersonID"] = person_id
    payload["info"]["Name"] = f"FACE {person_uuid}"
    return payload


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
        assert db.get(DahWebhookEvent, checkin["eventId"]).image_data.startswith("data:image/jpeg;base64,")

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
        assert db.get(DahWebhookEvent, checkout["eventId"]).image_data.startswith("data:image/jpeg;base64,")
    finally:
        db.close()


def test_dah_webhook_real_uuid_persists_person_id_on_identity(tmp_path):
    from server.models import DahCustomerIdentity
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db, person_uuid="732")

        result = dah_service.verify(db, verify_payload_for_uuid_and_person_id("732", "812", "2026-08-11T09:00:00", "uuid-id"))

        assert result["status"] == "processed"
        identity = db.query(DahCustomerIdentity).filter_by(customer_id=customer_id, person_uuid="732").one()
        assert identity.person_id == "812"
    finally:
        db.close()


def test_dah_local_sync_backfilled_member_event_rebuilds_checkin_checkout(tmp_path):
    from server.models import AttendanceSession
    from server.services import dah_local_sync_service, dah_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db)

        late = dah_service.verify(db, verify_payload("2026-08-11T10:00:00", "late"))
        assert late["action"] == "checkin"

        result = dah_local_sync_service.import_agent_result(db, {
            "ok": True,
            "agentId": "test-agent",
            "jobId": "test-job",
            "deviceCode": "DAH-192.168.1.60",
            "dahBaseUrl": "http://192.168.1.60:80",
            "events": [{
                "dahUid": "early",
                "dahPersonUid": "812",
                "eventTime": "2026-08-11T07:00:00",
                "rawEventTime": "2026-08-11/07:00:00",
                "status": 1,
                "similarity": 95,
                "name": "TRAN NGUYEN KHAI HOAN",
                "mjCardNo": "1",
                "raw": {},
            }],
        })

        assert result["imported"] == 1
        session = db.query(AttendanceSession).filter_by(customer_id=customer_id, source="dah").one()
        assert session.checked_in_at == datetime(2026, 8, 11, 7, 0)
        assert session.checked_out_at == datetime(2026, 8, 11, 10, 0)
        assert session.status == "closed"
    finally:
        db.close()


def test_dah_agent_result_requires_manual_approval_before_commit(tmp_path):
    from server.models import AttendanceSession, DahCustomerIdentity
    from server.services import dah_local_sync_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db)
        db.add(DahCustomerIdentity(customer_id=customer_id, person_uuid="dah_profile:0/0/1", person_id="812"))
        db.commit()
        payload = {
            "ok": True,
            "agentId": "test-agent",
            "jobId": "approval-job",
            "deviceCode": "DAH-192.168.1.60",
            "events": [{
                "dahUid": "approval-1",
                "dahPersonUid": "812",
                "profileKey": "dah_profile:0/0/1",
                "eventTime": "2026-08-11T07:00:00",
                "status": 1,
                "name": "TRAN NGUYEN KHAI HOAN",
            }],
        }

        posted = dah_local_sync_service.record_result(db, "approval-job", payload)
        batch_id = posted["batch"]["id"]
        assert posted["status"] == "pending_approval"
        assert posted["batch"]["summary"]["matched"] == 1
        assert db.query(AttendanceSession).filter_by(customer_id=customer_id, source="dah").count() == 0

        approved = dah_local_sync_service.approve_batch(db, batch_id, {})
        assert approved["result"]["imported"] == 1
        assert db.query(AttendanceSession).filter_by(customer_id=customer_id, source="dah").count() == 1
    finally:
        db.close()


def test_dah_local_sync_matches_by_person_id_only(tmp_path):
    from server.models import DahCustomerIdentity
    from server.services import dah_local_sync_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db)
        db.add(DahCustomerIdentity(customer_id=customer_id, person_uuid="dah_profile:0/0/75366400", person_id="1149"))
        db.commit()
        preview = dah_local_sync_service.preview_agent_result(db, {
            "ok": True,
            "deviceCode": "DAH-192.168.1.60",
            "events": [{
                "dahUid": "24602",
                "dahPersonUid": "1149",
                "profileKey": "dah_profile:0/0/75366400",
                "eventTime": "2026-08-11T07:00:00",
                "status": 1,
                "name": "LONG",
                "registeredName": "LONG",
                "registeredPhone": "0900000001",
            }],
        })

        event = preview["events"][0]
        assert preview["matched"] == 1
        assert event["customerId"] == customer_id
        assert event["matchSource"] == "person_id"
    finally:
        db.close()


def test_dah_local_sync_treats_person_id_and_time_as_duplicate(tmp_path):
    from server.models import DahCustomerIdentity, DahWebhookEvent
    from server.services import dah_local_sync_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db)
        db.add(DahCustomerIdentity(customer_id=customer_id, person_uuid="732", person_id="1149"))
        db.add(DahWebhookEvent(
            event_key="webhook-existing-hash",
            operator="VerifyPush",
            customer_id=customer_id,
            person_uuid="732",
            person_id="1149",
            verify_status=1,
            event_time=datetime(2026, 8, 11, 7, 0),
            status="processed",
            action="checkin",
            raw_payload="{}",
        ))
        db.commit()

        payload = {
            "ok": True,
            "deviceCode": "DAH-192.168.1.60",
            "events": [{
                "dahUid": "24602",
                "dahPersonUid": "1149",
                "profileKey": "dah_profile:0/0/75366400",
                "eventTime": "2026-08-11T07:00:00",
                "status": 1,
                "name": "LONG",
            }],
        }
        preview = dah_local_sync_service.preview_agent_result(db, payload)
        event_key = preview["events"][0]["eventKey"]

        assert preview["duplicates"] == 1
        assert preview["matched"] == 0
        assert preview["events"][0]["status"] == "duplicate"
        assert preview["events"][0]["willSync"] is False

        result = dah_local_sync_service.import_agent_result(db, payload, selected_event_keys={event_key})
        assert result["duplicates"] == 1
        assert result["imported"] == 0
        assert db.query(DahWebhookEvent).count() == 1
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


def test_dah_person_id_only_event_can_be_assigned_and_processed(tmp_path):
    from server.models import AttendanceSession, Customer, DahCustomerIdentity, DahWebhookEvent
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db, person_uuid=None)
        unknown = dah_service.verify(db, verify_payload_for_person_id("1128", "2026-08-11T10:20:00"))

        assert unknown["status"] == "unknown"
        assert unknown["action"] == "unknown_identity"

        candidates = dah_service.identity_candidates(db, limit=10)["items"]
        candidate = next(row for row in candidates if row["personId"] == "1128")

        assert candidate["personUuid"] == "person_id:1128"
        assert candidate["rawPersonUuid"] is None
        assert candidate["name"] == "FACE 1128"

        linked = dah_service.assign_identity_to_customer(db, customer_id, unknown["eventId"])
        customer = db.get(Customer, customer_id)
        event = db.get(DahWebhookEvent, unknown["eventId"])

        assert linked["personUuid"] == "person_id:1128"
        assert customer.person_uuid == "person_id:1128"
        assert event.status == "linked"
        assert db.query(DahCustomerIdentity).filter_by(
            customer_id=customer_id,
            person_uuid="person_id:1128",
            person_id="1128",
        ).count() == 1

        checkin = dah_service.verify(db, verify_payload_for_person_id("1128", "2026-08-11T10:30:00", "2"))

        assert checkin["status"] == "processed"
        assert checkin["action"] == "checkin"
        assert checkin["memberId"] == customer_id
        assert db.query(AttendanceSession).filter_by(customer_id=customer_id, status="open").count() == 1
    finally:
        db.close()


def test_dah_person_id_fallback_upgrades_to_real_uuid_without_stale_customer_key(tmp_path):
    from server.models import AttendanceSession, Customer, DahCustomerIdentity
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db, person_uuid=None)
        unknown = dah_service.verify(db, verify_payload_for_person_id("1128", "2026-08-11T10:20:00"))
        dah_service.assign_identity_to_customer(db, customer_id, unknown["eventId"])

        checkin = dah_service.verify(
            db,
            verify_payload_for_uuid_and_person_id("real-uuid-1128", "1128", "2026-08-11T10:30:00", "2"),
        )
        customer = db.get(Customer, customer_id)
        identity = db.query(DahCustomerIdentity).filter_by(customer_id=customer_id).one()

        assert checkin["status"] == "processed"
        assert checkin["action"] == "checkin"
        assert checkin["memberId"] == customer_id
        assert customer.person_uuid == "real-uuid-1128"
        assert identity.person_uuid == "real-uuid-1128"
        assert identity.person_id == "1128"
        assert db.query(AttendanceSession).filter_by(customer_id=customer_id, status="open").count() == 1
    finally:
        db.close()


def test_dah_webhook_merges_stale_person_id_alias_into_real_uuid(tmp_path):
    from server.models import Customer, DahCustomerIdentity
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db, person_uuid="person_id:1128")
        db.add(DahCustomerIdentity(customer_id=customer_id, person_uuid="person_id:1128", person_id="1128"))
        db.add(DahCustomerIdentity(person_uuid="real-uuid-1128"))
        db.commit()

        result = dah_service.verify(
            db,
            verify_payload_for_uuid_and_person_id("real-uuid-1128", "1128", "2026-08-11T10:30:00", "merge-alias"),
        )
        customer = db.get(Customer, customer_id)
        identities = db.query(DahCustomerIdentity).filter(DahCustomerIdentity.person_id == "1128").all()

        assert result["status"] == "processed"
        assert result["memberId"] == customer_id
        assert customer.person_uuid == "real-uuid-1128"
        assert len(identities) == 1
        assert identities[0].person_uuid == "real-uuid-1128"
        assert identities[0].customer_id == customer_id
    finally:
        db.close()


def test_dah_real_uuid_does_not_auto_match_different_existing_uuid_by_person_id(tmp_path):
    from server.models import DahCustomerIdentity
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db, person_uuid="old-real-uuid")
        db.add(DahCustomerIdentity(customer_id=customer_id, person_uuid="old-real-uuid", person_id="1128"))
        db.commit()

        result = dah_service.verify(
            db,
            verify_payload_for_uuid_and_person_id("new-real-uuid", "1128", "2026-08-11T10:40:00", "3"),
        )

        assert result["status"] == "unknown"
        assert result["action"] == "unknown_identity"
        assert result["memberId"] is None
    finally:
        db.close()


def test_dah_candidates_include_assignment_tags_and_sort_unlinked_first(tmp_path):
    from server.models import Customer, DahCustomerIdentity, Employee, Person
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        assigned_customer_id = seed_member(db, person_uuid="assigned-member")
        assigned_customer = db.get(Customer, assigned_customer_id)
        db.add(DahCustomerIdentity(customer_id=assigned_customer_id, person_uuid="assigned-member"))

        person = Person(display_name="Coach Linked", phone="0900000010", status="active")
        db.add(person)
        db.flush()
        employee = Employee(person_id=person.id, employee_code="EMP-00010", job_title="Coach", status="active")
        db.add(employee)
        db.flush()
        db.add(DahCustomerIdentity(employee_id=employee.id, person_uuid="assigned-employee"))
        db.commit()

        dah_service.verify(db, verify_payload_for_uuid("assigned-member", "2026-08-11T12:00:00", "710"))
        dah_service.verify(db, verify_payload_for_uuid("assigned-employee", "2026-08-11T11:30:00", "711"))
        dah_service.verify(db, verify_payload_for_uuid("unlinked-member", "2026-08-11T11:00:00", "712"))

        candidates = dah_service.identity_candidates(db, limit=5, target_type="member", include_assigned=True)["items"]

        assert [row["personUuid"] for row in candidates[:3]] == [
            "unlinked-member",
            "assigned-member",
            "assigned-employee",
        ]
        member_candidate = next(row for row in candidates if row["personUuid"] == "assigned-member")
        employee_candidate = next(row for row in candidates if row["personUuid"] == "assigned-employee")

        assert member_candidate["isLinked"] is True
        assert member_candidate["linkedMembers"][0]["id"] == assigned_customer.id
        assert member_candidate["linkedMembers"][0]["name"] == assigned_customer.person.display_name
        assert employee_candidate["isLinked"] is True
        assert employee_candidate["linkedEmployees"][0]["id"] == employee.id
        assert employee_candidate["linkedEmployees"][0]["name"] == "Coach Linked"
    finally:
        db.close()


def test_dah_candidates_are_limited_to_recent_distinct_faces_before_sorting(tmp_path):
    from server.models import Customer, DahCustomerIdentity
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        old_customer_id = seed_member(db, person_uuid="old-linked")
        db.add(DahCustomerIdentity(customer_id=old_customer_id, person_uuid="old-linked"))
        db.commit()

        dah_service.verify(db, verify_payload_for_uuid("old-linked", "2026-08-11T08:00:00", "800"))
        for index in range(11):
            dah_service.verify(
                db,
                verify_payload_for_uuid(
                    f"recent-{index}",
                    f"2026-08-11T09:{index:02d}:00",
                    str(810 + index),
                ),
            )

        candidates = dah_service.identity_candidates(
            db,
            limit=10,
            target_type="member",
            include_assigned=True,
        )["items"]
        uuids = [row["personUuid"] for row in candidates]

        assert len(uuids) == 10
        assert "old-linked" not in uuids
        assert "recent-10" in uuids
        assert "recent-1" in uuids
        assert "recent-0" not in uuids
    finally:
        db.close()


def test_member_dah_candidates_return_recent_unlinked_members_after_filtering_assigned(tmp_path):
    from server.models import Customer, DahCustomerIdentity, Person
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        for index in range(10):
            dah_service.verify(
                db,
                verify_payload_for_uuid(
                    f"unlinked-{index}",
                    f"2026-08-11T09:{index:02d}:00",
                    str(900 + index),
                ),
            )
        for index in range(12):
            person = Person(display_name=f"Assigned {index}", phone=f"09110000{index:02d}", status="active")
            db.add(person)
            db.flush()
            customer = Customer(
                person_id=person.id,
                customer_code=f"MB-A{index:04d}",
                person_uuid=f"assigned-{index}",
                status="active",
            )
            db.add(customer)
            db.flush()
            db.add(DahCustomerIdentity(customer_id=customer.id, person_uuid=f"assigned-{index}"))
            db.commit()
            dah_service.verify(
                db,
                verify_payload_for_uuid(
                    f"assigned-{index}",
                    f"2026-08-11T10:{index:02d}:00",
                    str(920 + index),
                ),
            )

        candidates = dah_service.identity_candidates(db, limit=10, target_type="member")["items"]
        uuids = [row["personUuid"] for row in candidates]

        assert len(uuids) == 10
        assert all(uuid.startswith("unlinked-") for uuid in uuids)
        assert db.query(Customer).count() == 12
    finally:
        db.close()


def test_dah_identity_can_be_reassigned_to_member_with_confirmation(tmp_path):
    from fastapi import HTTPException
    from server.models import Customer, DahCustomerIdentity
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db, person_uuid="old-uuid")
        db.add(DahCustomerIdentity(customer_id=customer_id, person_uuid="old-uuid"))
        db.commit()

        unknown = dah_service.verify(db, verify_payload_for_uuid("new-uuid", "2026-08-11T10:30:00", "250"))
        assert unknown["status"] == "unknown"

        try:
            dah_service.assign_identity_to_customer(db, customer_id, unknown["eventId"])
            assert False, "Expected relink without replace flag to fail"
        except HTTPException as exc:
            assert exc.status_code == 409

        try:
            dah_service.assign_identity_to_customer(
                db,
                customer_id,
                unknown["eventId"],
                replace=True,
                confirmation_text="xac nhan",
            )
            assert False, "Expected relink with wrong confirmation to fail"
        except HTTPException as exc:
            assert exc.status_code == 422

        linked = dah_service.assign_identity_to_customer(
            db,
            customer_id,
            unknown["eventId"],
            replace=True,
            confirmation_text="tôi xác nhận thay đổi",
        )
        customer = db.get(Customer, customer_id)

        assert linked["personUuid"] == "new-uuid"
        assert customer.person_uuid == "new-uuid"
        assert customer.avatar_image_data.startswith("data:image/jpeg;base64,")
        assert db.query(DahCustomerIdentity).filter_by(customer_id=customer_id, person_uuid="new-uuid").count() == 1
        assert db.query(DahCustomerIdentity).filter_by(customer_id=customer_id, person_uuid="old-uuid").count() == 0
    finally:
        db.close()


def test_dah_webhook_image_cleanup_keeps_recent_and_clears_old(tmp_path):
    from server.models import DahWebhookEvent
    from server.services import dah_service
    from server.timeutils import utc_now

    db = make_session(tmp_path)
    try:
        old = DahWebhookEvent(
            event_key="old",
            operator="VerifyPush",
            status="unknown",
            image_data="data:image/jpeg;base64,b2xk",
            received_at=utc_now() - timedelta(days=5),
        )
        recent = DahWebhookEvent(
            event_key="recent",
            operator="VerifyPush",
            status="unknown",
            image_data="data:image/jpeg;base64,cmVjZW50",
            received_at=utc_now() - timedelta(days=2),
        )
        db.add_all([old, recent])
        db.commit()

        assert dah_service.cleanup_webhook_images(db) == 1
        assert db.query(DahWebhookEvent).filter_by(event_key="old").one().image_data is None
        assert db.query(DahWebhookEvent).filter_by(event_key="recent").one().image_data.startswith("data:image/jpeg;base64,")
    finally:
        db.close()


def test_dah_identity_can_be_relinked_to_employee_and_toggles_attendance(tmp_path):
    from server.models import AttendanceSession, DahCustomerIdentity, DahWebhookEvent, Employee, Person
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        person = Person(display_name="Coach DAH", phone="0900000005", status="active")
        db.add(person)
        db.flush()
        employee = Employee(person_id=person.id, employee_code="EMP-00005", job_title="Coach", status="active")
        db.add(employee)
        db.commit()

        unknown = dah_service.verify(db, verify_payload_for_uuid("9001", "2026-08-11T11:00:00", "300"))
        assert unknown["status"] == "unknown"
        event_id = db.query(DahWebhookEvent).filter_by(person_uuid="9001").one().id

        linked = dah_service.assign_identity_to_employee(db, employee.id, event_id)
        assert linked["personUuid"] == "9001"
        assert db.query(DahCustomerIdentity).filter_by(employee_id=employee.id, person_uuid="9001").count() == 1

        checkin = dah_service.verify(db, verify_payload_for_uuid("9001", "2026-08-11T11:05:00", "301"))
        assert checkin["action"] == "checkin"
        assert checkin["employeeId"] == employee.id
        assert db.query(AttendanceSession).filter_by(employee_id=employee.id, status="open").count() == 1

        checkout = dah_service.verify(db, verify_payload_for_uuid("9001", "2026-08-11T11:15:00", "302"))
        assert checkout["action"] == "checkout"
        session = db.query(AttendanceSession).filter_by(employee_id=employee.id).one()
        assert session.status == "closed"
    finally:
        db.close()


def test_employee_dah_attendance_uses_shift_cutoff_for_close_shifts(tmp_path):
    from server.models import AttendanceSession, DahCustomerIdentity, Employee, EmployeeShiftSchedule, Person
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        person = Person(display_name="Close Shift Staff", phone="0900000090", status="active")
        db.add(person)
        db.flush()
        employee = Employee(person_id=person.id, employee_code="EMP-00090", job_title="Coach", status="active")
        db.add(employee)
        db.flush()
        db.add(DahCustomerIdentity(employee_id=employee.id, person_uuid="close-shift"))
        work_date = date(2026, 8, 11)
        db.add_all([
            EmployeeShiftSchedule(
                employee_id=employee.id,
                work_date=work_date,
                starts_at=datetime(2026, 8, 11, 12, 0),
                ends_at=datetime(2026, 8, 11, 13, 0),
            ),
            EmployeeShiftSchedule(
                employee_id=employee.id,
                work_date=work_date,
                starts_at=datetime(2026, 8, 11, 13, 15),
                ends_at=datetime(2026, 8, 11, 14, 15),
            ),
        ])
        db.commit()

        for index, scanned_at in enumerate([
            "2026-08-11T12:01:00",
            "2026-08-11T13:10:00",
            "2026-08-11T13:12:00",
            "2026-08-11T14:20:00",
        ], start=900):
            result = dah_service.verify(db, verify_payload_for_uuid("close-shift", scanned_at, str(index)))
            assert result["status"] == "processed"

        rows = (
            db.query(AttendanceSession)
            .filter_by(employee_id=employee.id)
            .order_by(AttendanceSession.checked_in_at.asc())
            .all()
        )
        assert len(rows) == 2
        assert rows[0].checked_in_at.isoformat() == "2026-08-11T12:01:00"
        assert rows[0].checked_out_at.isoformat() == "2026-08-11T13:10:00"
        assert rows[1].checked_in_at.isoformat() == "2026-08-11T13:12:00"
        assert rows[1].checked_out_at.isoformat() == "2026-08-11T14:20:00"
    finally:
        db.close()


def test_dah_local_sync_employee_event_rebuilds_shift_attendance(tmp_path):
    from server.models import AttendanceSession, DahCustomerIdentity, Employee, EmployeeShiftSchedule, Person
    from server.services import dah_local_sync_service

    db = make_session(tmp_path)
    try:
        person = Person(display_name="Local Sync Coach", phone="0900000091", status="active")
        db.add(person)
        db.flush()
        employee = Employee(person_id=person.id, employee_code="EMP-00091", job_title="Coach", status="active")
        db.add(employee)
        db.flush()
        db.add(DahCustomerIdentity(employee_id=employee.id, person_uuid="dah_profile:0/0/90091", person_id="90091"))
        db.add(EmployeeShiftSchedule(
            employee_id=employee.id,
            work_date=date(2026, 8, 11),
            starts_at=datetime(2026, 8, 11, 7, 0),
            ends_at=datetime(2026, 8, 11, 10, 0),
        ))
        db.commit()

        result = dah_local_sync_service.import_agent_result(db, {
            "ok": True,
            "agentId": "test-agent",
            "jobId": "test-job",
            "deviceCode": "DAH-192.168.1.60",
            "events": [
                {"dahUid": "coach-1", "dahPersonUid": "90091", "profileKey": "dah_profile:0/0/90091", "eventTime": "2026-08-11T10:00:00", "status": 1, "name": "Local Sync Coach"},
                {"dahUid": "coach-2", "dahPersonUid": "90091", "profileKey": "dah_profile:0/0/90091", "eventTime": "2026-08-11T07:00:00", "status": 1, "name": "Local Sync Coach"},
            ],
        })

        assert result["imported"] == 2
        session = db.query(AttendanceSession).filter_by(employee_id=employee.id, source="dah").one()
        assert session.checked_in_at == datetime(2026, 8, 11, 7, 0)
        assert session.checked_out_at == datetime(2026, 8, 11, 10, 0)
        assert session.status == "closed"
    finally:
        db.close()


def test_dah_identity_linked_to_member_and_employee_records_both_attendances(tmp_path):
    from server.models import AttendanceSession, Customer, DahCustomerIdentity, Employee, Person
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        customer_id = seed_member(db, person_uuid=None)
        customer = db.get(Customer, customer_id)
        employee_person = Person(display_name="Coach Member", phone="0900000007", status="active")
        db.add(employee_person)
        db.flush()
        employee = Employee(person_id=employee_person.id, employee_code="EMP-00007", job_title="Coach", status="active")
        db.add(employee)
        db.commit()

        unknown = dah_service.verify(db, verify_payload_for_uuid("dual-uuid", "2026-08-11T13:00:00", "500"))
        assert unknown["status"] == "unknown"
        event_id = unknown["eventId"]

        linked_customer = dah_service.assign_identity_to_customer(db, customer.id, event_id)
        assert linked_customer["personUuid"] == "dual-uuid"
        employee_candidates = dah_service.identity_candidates(db, target_type="employee")
        assert employee_candidates["items"][0]["personUuid"] == "dual-uuid"

        linked_employee = dah_service.assign_identity_to_employee(db, employee.id, event_id)
        assert linked_employee["personUuid"] == "dual-uuid"
        identity = db.query(DahCustomerIdentity).filter_by(person_uuid="dual-uuid").one()
        assert identity.customer_id == customer.id
        assert identity.employee_id == employee.id

        checkin = dah_service.verify(db, verify_payload_for_uuid("dual-uuid", "2026-08-11T13:05:00", "501"))
        assert checkin["action"] == "checkin"
        assert checkin["memberId"] == customer.id
        assert checkin["employeeId"] == employee.id
        assert checkin["memberSessionId"]
        assert checkin["employeeSessionId"]
        assert db.query(AttendanceSession).filter_by(customer_id=customer.id, status="open").count() == 1
        assert db.query(AttendanceSession).filter_by(employee_id=employee.id, status="open").count() == 1

        checkout = dah_service.verify(db, verify_payload_for_uuid("dual-uuid", "2026-08-11T13:15:00", "502"))
        assert checkout["action"] == "checkout"
        assert db.query(AttendanceSession).filter_by(customer_id=customer.id, status="closed").count() == 1
        assert db.query(AttendanceSession).filter_by(employee_id=employee.id, status="closed").count() == 1
    finally:
        db.close()


def test_dah_allows_lead_customer_checkin_without_membership(tmp_path):
    from server.models import AttendanceSession, Customer, Person
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        person = Person(display_name="Lead Customer", phone="0900000006", status="active")
        db.add(person)
        db.flush()
        customer = Customer(
            person_id=person.id,
            customer_code="CUS0009001",
            person_uuid="lead-uuid",
            status="lead",
            source="Walk-in",
        )
        db.add(customer)
        db.commit()

        checkin = dah_service.verify(db, verify_payload_for_uuid("lead-uuid", "2026-08-11T12:00:00", "400"))

        assert checkin["action"] == "checkin"
        assert checkin["memberId"] == customer.id
        assert db.query(AttendanceSession).filter_by(customer_id=customer.id, status="open").count() == 1
    finally:
        db.close()


def test_dah_events_are_paginated(tmp_path):
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        seed_member(db)
        dah_service.verify(db, verify_payload("2026-08-11T12:00:00", "601"))
        dah_service.verify(db, verify_payload("2026-08-11T12:05:00", "602"))
        dah_service.verify(db, verify_payload("2026-08-11T12:10:00", "603"))

        first_page = dah_service.dah_events(db, page=1, page_size=2)
        second_page = dah_service.dah_events(db, page=2, page_size=2)

        assert first_page["pagination"] == {"page": 1, "pageSize": 2, "total": 3, "pages": 2}
        assert len(first_page["items"]) == 2
        assert second_page["pagination"] == {"page": 2, "pageSize": 2, "total": 3, "pages": 2}
        assert len(second_page["items"]) == 1
        assert first_page["items"][0]["eventTime"] > second_page["items"][0]["eventTime"]
    finally:
        db.close()


def test_dah_verify_persists_event_before_processing_failure(tmp_path, monkeypatch):
    from server.models import AttendanceSession, DahWebhookEvent
    from server.services import dah_service

    db = make_session(tmp_path)
    try:
        seed_member(db)

        def fail_speech(*_args, **_kwargs):
            raise RuntimeError("speech queue failed")

        monkeypatch.setattr(dah_service, "queue_checkin_speech", fail_speech)
        with pytest.raises(RuntimeError, match="speech queue failed"):
            dah_service.verify(db, verify_payload("2026-08-11T13:00:00", "701"))

        event = db.query(DahWebhookEvent).one()
        assert event.status == "error"
        assert event.action == "processing_error"
        assert "speech queue failed" in event.note
        assert event.raw_payload
        assert db.query(AttendanceSession).count() == 0
    finally:
        db.close()
