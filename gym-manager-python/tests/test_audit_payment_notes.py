import asyncio
import base64
from datetime import date
from io import BytesIO
import json

from starlette.datastructures import UploadFile

from test_membership_lifecycle import make_session, seed_member_with_plan


def test_payment_notes_are_snapshots_for_all_membership_payment_paths(tmp_path):
    from server.models import AuditLog, Membership
    from server.services.members_service import create_member, create_membership, update_membership
    from server.services.audit_service import member_audit_logs

    with make_session(tmp_path) as db:
        _, original = seed_member_with_plan(db)
        note = "Ưu đãi voucher 20 tháng 10"
        member = create_member(db, {
            "name": "Voucher Member", "phone": "0900000002",
            "membership": {
                "planId": original.package_id, "startsAt": "2026-10-20",
                "paidAmount": 50000, "debtDueDate": "2026-11-20",
                "paymentMethod": "cash", "pricingNote": note,
            },
        })
        membership = db.query(Membership).filter_by(customer_id=member["id"]).one()
        asyncio.run(update_membership(db, membership.id, {
            "paidAmount": 100000, "paymentMethod": "cash",
        }, [], None))
        asyncio.run(create_membership(db, {
            "memberId": member["id"], "planId": original.package_id,
            "startsAt": "2026-12-01", "paidAmount": 100000,
            "paymentMethod": "cash", "pricingNote": "Ưu đãi gia hạn",
        }, [], None))
        logs = db.query(AuditLog).filter_by(customer_id=member["id"], action="payment").order_by(AuditLog.id).all()
        assert [json.loads(row.details_json)["pricingNote"] for row in logs] == [note, note, "Ưu đãi gia hạn"]
        membership.pricing_note = "Ghi chú mới"
        db.commit()
        items = member_audit_logs(db, member["id"])
        payments = [item for item in items if item["action"] == "payment"]
        assert all("currentPricingNote" not in item for item in payments)
        assert payments[-1]["details"]["pricingNote"] == note


def test_old_payment_note_fallback_does_not_rewrite_history_or_replace_empty_snapshot(tmp_path):
    from server.models import AuditLog, Payment
    from server.services.audit_service import list_audit_logs, member_audit_logs, record_audit

    with make_session(tmp_path) as db:
        customer, membership = seed_member_with_plan(db)
        membership.pricing_note = "Ghi chú giá hiện tại"
        payment = Payment(customer_id=customer.id, membership_id=membership.id, payment_no="NOTE-OLD", amount=100)
        db.add(payment)
        db.flush()
        for details in ({"membershipId": membership.id}, {"pricingNote": None}, {"pricingNote": ""}, {"pricingNote": "Snapshot cũ"}):
            record_audit(db, None, "payment", "payment", payment.id, "Thu tiền", customer_id=customer.id, details=details)
        record_audit(db, None, "payment", "payment", 999999, "Giao dịch thiếu", customer_id=customer.id)
        record_audit(db, None, "upload_receipt", "payment", payment.id, "Tải ảnh", customer_id=customer.id)
        db.commit()
        before = {row.id: row.details_json for row in db.query(AuditLog)}
        for items in (list_audit_logs(db)["items"], member_audit_logs(db, customer.id)):
            fallback = [item for item in items if "currentPricingNote" in item]
            assert len(fallback) == 1
            assert fallback[0]["currentPricingNote"] == "Ghi chú giá hiện tại"
            assert "pricingNote" not in fallback[0]["details"]
        assert {row.id: row.details_json for row in db.query(AuditLog)} == before
        membership.pricing_note = None
        db.commit()
        assert all("currentPricingNote" not in item for item in member_audit_logs(db, customer.id))


def test_receipts_survive_reload_and_stay_with_the_correct_payment(tmp_path, monkeypatch):
    from server.models import Payment
    from server.services import members_service
    from server.services.serializers import payment_data

    monkeypatch.setattr(members_service, "RECEIPT_DIR", tmp_path)
    png = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=")
    with make_session(tmp_path) as db:
        customer, membership = seed_member_with_plan(db)
        first = Payment(customer_id=customer.id, membership_id=membership.id, payment_no="RECEIPT-1", amount=100)
        second = Payment(customer_id=customer.id, membership_id=membership.id, payment_no="RECEIPT-2", amount=200)
        legacy = Payment(customer_id=customer.id, membership_id=membership.id, payment_no="RECEIPT-OLD", amount=300, receipt_image_path="/uploads/receipts/legacy.png")
        db.add_all([first, second, legacy])
        db.commit()
        for name in ("first.png", "clipboard.png"):
            asyncio.run(members_service.upload_payment_receipts(db, first.id, [UploadFile(BytesIO(png), filename=name)]))
        db.expire_all()
        data = members_service.get_member(db, customer.id, include_audit=True)
        payments = {row["id"]: row for row in data["payments"]}
        assert payments[first.id]["receiptCount"] == 2
        assert payments[second.id]["receiptCount"] == 0
        assert payments[legacy.id]["receiptCount"] == 1
        assert payment_data(legacy)["receipts"][0]["url"].endswith("legacy.png")
        uploads = [item for item in data["auditLogs"] if item["action"] == "upload_receipt"]
        assert len(uploads) == 2
        assert all(item["entityId"] == first.id for item in uploads)
        for receipt in payments[first.id]["receipts"]:
            assert (tmp_path / receipt["url"].split("/")[-1]).read_bytes() == png


def test_freeze_audit_preserves_reason(tmp_path):
    from server.models import AuditLog, User
    from server.services.members_service import freeze_membership
    with make_session(tmp_path) as db:
        _, membership = seed_member_with_plan(db, status="active", starts_at=date(2030, 1, 1))
        actor = User(username="audit-test", password_hash="unused", display_name="Admin", role="admin")
        db.add(actor)
        db.commit()
        freeze_membership(db, membership.id, {"startsAt": "2030-01-05", "endsAt": "2030-01-10", "reason": "Đi công tác"}, actor)
        audit = db.query(AuditLog).filter_by(action="freeze").one()
        assert json.loads(audit.details_json)["reason"] == "Đi công tác"
