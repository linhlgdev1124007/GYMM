import csv
from io import StringIO

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..dependencies import require_roles
from ..models import User
from ..services import inventory_service


router = APIRouter(prefix="/api/inventory", tags=["inventory"])
admin_only = require_roles("admin")


@router.get("/products")
def products(
    q: str = "",
    category: str = "all",
    stockStatus: str = "all",
    active: str = "active",
    page: int = Query(1, ge=1),
    pageSize: int = Query(30, ge=10, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(admin_only),
):
    return inventory_service.list_products(db, q, category, stockStatus, active, page, pageSize)


@router.post("/products")
def create_product(payload: dict, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return inventory_service.create_product(db, payload, user)


@router.patch("/products/{product_id}")
def update_product(product_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return inventory_service.update_product(db, product_id, payload, user)


@router.get("/transactions")
def transactions(
    q: str = "",
    type: str = "all",
    category: str = "all",
    productId: int | None = None,
    dateFrom: str = "",
    dateTo: str = "",
    page: int = Query(1, ge=1),
    pageSize: int = Query(30, ge=10, le=100),
    db: Session = Depends(get_db),
    _user: User = Depends(admin_only),
):
    return inventory_service.list_transactions(db, q, type, category, productId, dateFrom, dateTo, page, pageSize)


@router.post("/transactions")
def create_transaction(payload: dict, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return inventory_service.create_transaction(db, payload, user)


@router.post("/transactions/{transaction_id}/reverse")
def reverse_transaction(transaction_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(admin_only)):
    return inventory_service.reverse_transaction(db, transaction_id, payload, user)


@router.get("/reports")
def report(
    period: str = "month",
    anchor: str = "",
    category: str = "all",
    productId: int | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(admin_only),
):
    return inventory_service.inventory_report(db, period, anchor, category, productId)


@router.get("/export")
def export_transactions(
    type: str = "all",
    category: str = "all",
    productId: int | None = None,
    dateFrom: str = "",
    dateTo: str = "",
    db: Session = Depends(get_db),
    _user: User = Depends(admin_only),
):
    data = inventory_service.list_transactions(db, "", type, category, productId, dateFrom, dateTo, 1, 1000)
    output = StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(["Ngày tháng", "Mã hàng", "Tên hàng", "Danh mục", "Loại", "Số lượng", "Đơn vị", "Đơn giá", "Tổng tiền", "Ghi chú", "Người tạo"])
    for row in data["items"]:
        writer.writerow([row["occurredAt"], row["sku"], row["productName"], row["category"], "Nhập" if row["type"] == "IN" else "Xuất", row["quantity"], row["unit"], row["unitCost"], row["totalAmount"], row["note"] or "", row["createdBy"] or ""])
    return StreamingResponse(iter([output.getvalue()]), media_type="text/csv; charset=utf-8", headers={"Content-Disposition": 'attachment; filename="inventory-transactions.csv"'})
