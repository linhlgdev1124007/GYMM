import os
from pathlib import Path
import tempfile

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GYM_ENV", "test")
os.environ.setdefault("GYM_DATABASE_PATH", str(Path(tempfile.mkdtemp(prefix="pulsefit-inventory-tests-")) / "bootstrap.sqlite3"))


def make_session(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'inventory.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def admin(db):
    from server.models import User

    row = User(username="inventory-admin", display_name="Inventory Admin", password_hash="test", role="admin", is_active=True)
    db.add(row)
    db.commit()
    return row


def test_inventory_flow_keeps_stock_and_weighted_cost_consistent(tmp_path):
    from server.services.inventory_service import create_product, create_transaction, inventory_report

    db = make_session(tmp_path)
    try:
        actor = admin(db)
        product = create_product(db, {
            "name": "Nước suối 500ml",
            "category": "Đồ uống",
            "unit": "Chai",
            "initialStock": 10,
            "initialCost": 4000,
            "minimumStock": 3,
        }, actor)
        create_transaction(db, {
            "productId": product["id"], "type": "IN", "quantity": 10,
            "unitCost": 6000, "occurredAt": "2026-08-16T09:00:00",
        }, actor)
        outbound = create_transaction(db, {
            "productId": product["id"], "type": "OUT", "quantity": 4,
            "occurredAt": "2026-08-16T10:00:00", "note": "Sử dụng trong ngày",
        }, actor)
        report = inventory_report(db, "day", "2026-08-16")

        assert outbound["stockBefore"] == 20
        assert outbound["stockAfter"] == 16
        assert outbound["unitCost"] == 5000
        assert outbound["totalAmount"] == 20000
        assert report["summary"]["inboundCost"] == 100000
        assert report["summary"]["outboundCost"] == 20000
        assert report["summary"]["openingStock"] == 0
        assert report["summary"]["closingStock"] == 16
    finally:
        db.close()


def test_inventory_rejects_negative_stock_and_reversal_is_auditable(tmp_path):
    from fastapi import HTTPException
    from server.models import AuditLog, InventoryTransaction
    from server.services.inventory_service import create_product, create_transaction, reverse_transaction

    db = make_session(tmp_path)
    try:
        actor = admin(db)
        product = create_product(db, {
            "name": "Khăn lau", "category": "Vệ sinh", "unit": "Cái",
            "initialStock": 5, "initialCost": 10000,
        }, actor)
        with pytest.raises(HTTPException) as error:
            create_transaction(db, {"productId": product["id"], "type": "OUT", "quantity": 6}, actor)
        assert error.value.status_code == 409
        db.rollback()

        outbound = create_transaction(db, {"productId": product["id"], "type": "OUT", "quantity": 2}, actor)
        reversal = reverse_transaction(db, outbound["id"], {"note": "Nhập nhầm số lượng"}, actor)
        original = db.get(InventoryTransaction, outbound["id"])

        assert reversal["type"] == "IN"
        assert reversal["stockAfter"] == 5
        assert reversal["reversedTransactionId"] == outbound["id"]
        assert original.status == "REVERSED"
        assert db.query(AuditLog).filter(AuditLog.action == "reverse", AuditLog.entity_type == "inventory_transaction").count() == 1
    finally:
        db.close()
