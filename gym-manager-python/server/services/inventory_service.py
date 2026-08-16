from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation

from fastapi import HTTPException
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, joinedload

from ..models import InventoryProduct, InventoryTransaction, User
from ..timeutils import VIETNAM_TZ, utc_iso, utc_now, vietnam_today
from .audit_service import record_audit
from .serializers import pagination


ZERO = Decimal("0")


def _decimal(value, field: str, *, allow_zero: bool = True) -> Decimal:
    try:
        result = Decimal(str(value if value not in (None, "") else 0))
    except (InvalidOperation, ValueError):
        raise HTTPException(422, f"{field} không hợp lệ.")
    if result < 0 or (not allow_zero and result == 0):
        raise HTTPException(422, f"{field} phải {'lớn hơn 0' if not allow_zero else 'từ 0 trở lên'}.")
    return result


def _local_to_utc(value: str | None) -> datetime:
    if not value:
        return utc_now()
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(422, "Ngày giao dịch không hợp lệ.")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=VIETNAM_TZ)
    return parsed.astimezone(UTC).replace(tzinfo=None)


def _product_data(row: InventoryProduct):
    stock = float(row.current_stock or 0)
    minimum = float(row.minimum_stock or 0)
    average = float(row.average_cost or 0)
    stock_status = "out" if stock <= 0 else "low" if minimum > 0 and stock <= minimum else "in_stock"
    return {
        "id": row.id,
        "sku": row.sku,
        "category": row.category,
        "name": row.name,
        "unit": row.unit,
        "currentStock": stock,
        "minimumStock": minimum,
        "averageCost": average,
        "inventoryValue": round(stock * average, 2),
        "stockStatus": stock_status,
        "isActive": row.is_active,
        "createdAt": utc_iso(row.created_at),
        "updatedAt": utc_iso(row.updated_at),
    }


def _transaction_data(row: InventoryTransaction):
    return {
        "id": row.id,
        "productId": row.product_id,
        "productName": row.product.name if row.product else None,
        "sku": row.product.sku if row.product else None,
        "category": row.product.category if row.product else None,
        "unit": row.product.unit if row.product else None,
        "type": row.transaction_type,
        "occurredAt": utc_iso(row.occurred_at),
        "quantity": float(row.quantity or 0),
        "unitCost": float(row.unit_cost or 0),
        "totalAmount": float(row.total_amount or 0),
        "stockBefore": float(row.stock_before or 0),
        "stockAfter": float(row.stock_after or 0),
        "note": row.note,
        "status": row.status,
        "reversedTransactionId": row.reversed_transaction_id,
        "createdBy": row.created_by.display_name if row.created_by else None,
        "createdAt": utc_iso(row.created_at),
    }


def _product_summary(db: Session):
    rows = db.query(InventoryProduct).filter(InventoryProduct.is_active == True).all()
    values = [_product_data(row) for row in rows]
    return {
        "products": len(values),
        "inventoryValue": round(sum(row["inventoryValue"] for row in values), 2),
        "lowStock": sum(row["stockStatus"] == "low" for row in values),
        "outOfStock": sum(row["stockStatus"] == "out" for row in values),
    }


def list_products(db: Session, q: str = "", category: str = "all", stock_status: str = "all", active: str = "active", page: int = 1, page_size: int = 30):
    query = db.query(InventoryProduct)
    if q.strip():
        term = q.strip()
        query = query.filter(or_(InventoryProduct.name.contains(term), InventoryProduct.sku.contains(term)))
    if category not in {"", "all"}:
        query = query.filter(InventoryProduct.category == category)
    if active == "active":
        query = query.filter(InventoryProduct.is_active == True)
    elif active == "inactive":
        query = query.filter(InventoryProduct.is_active == False)
    if stock_status == "out":
        query = query.filter(InventoryProduct.current_stock <= 0)
    elif stock_status == "low":
        query = query.filter(InventoryProduct.current_stock > 0, InventoryProduct.minimum_stock > 0, InventoryProduct.current_stock <= InventoryProduct.minimum_stock)
    elif stock_status == "in_stock":
        query = query.filter(or_(InventoryProduct.minimum_stock <= 0, InventoryProduct.current_stock > InventoryProduct.minimum_stock))
    total = query.count()
    page, page_size = max(page, 1), min(max(page_size, 10), 100)
    rows = query.order_by(InventoryProduct.is_active.desc(), InventoryProduct.name.asc()).offset((page - 1) * page_size).limit(page_size).all()
    categories = [value for (value,) in db.query(InventoryProduct.category).distinct().order_by(InventoryProduct.category).all() if value]
    return {"items": [_product_data(row) for row in rows], "summary": _product_summary(db), "filters": {"categories": categories}, "pagination": pagination(page, page_size, total)}


def _post_transaction(db: Session, product: InventoryProduct, transaction_type: str, quantity: Decimal, unit_cost: Decimal, occurred_at: datetime, note: str | None, actor: User, reversed_id: int | None = None):
    before = Decimal(str(product.current_stock or 0))
    average = Decimal(str(product.average_cost or 0))
    if transaction_type == "OUT":
        if quantity > before:
            raise HTTPException(409, f"Tồn kho {product.name} chỉ còn {float(before):g} {product.unit}.")
        after = before - quantity
        effective_cost = average
    else:
        after = before + quantity
        effective_cost = unit_cost
        if transaction_type == "IN":
            product.average_cost = ((before * average) + (quantity * unit_cost)) / after if after > 0 else ZERO
    row = InventoryTransaction(
        product_id=product.id,
        transaction_type=transaction_type,
        occurred_at=occurred_at,
        quantity=quantity,
        unit_cost=effective_cost,
        total_amount=quantity * effective_cost,
        stock_before=before,
        stock_after=after,
        note=note or None,
        created_by_user_id=actor.id,
        reversed_transaction_id=reversed_id,
        status="POSTED",
    )
    product.current_stock = after
    db.add(row)
    db.flush()
    return row


def create_product(db: Session, payload: dict, actor: User):
    name = str(payload.get("name") or "").strip()
    category = str(payload.get("category") or "").strip()
    unit = str(payload.get("unit") or "").strip()
    if not name or not category or not unit:
        raise HTTPException(422, "Tên hàng, danh mục và đơn vị tính là bắt buộc.")
    if db.query(InventoryProduct).filter(func.lower(InventoryProduct.name) == name.lower()).first():
        raise HTTPException(409, "Tên hàng hóa đã tồn tại.")
    sku = str(payload.get("sku") or "").strip().upper()
    if sku and db.query(InventoryProduct).filter(InventoryProduct.sku == sku).first():
        raise HTTPException(409, "Mã hàng đã tồn tại.")
    initial_stock = _decimal(payload.get("initialStock"), "Tồn đầu kỳ")
    initial_cost = _decimal(payload.get("initialCost"), "Đơn giá đầu kỳ")
    if initial_stock > 0 and initial_cost <= 0:
        raise HTTPException(422, "Cần nhập đơn giá khi có tồn đầu kỳ.")
    row = InventoryProduct(sku=sku or f"TMP-{utc_now().timestamp()}", category=category, name=name, unit=unit, current_stock=0, minimum_stock=_decimal(payload.get("minimumStock"), "Mức tồn tối thiểu"), average_cost=0, is_active=True)
    db.add(row)
    db.flush()
    if not sku:
        row.sku = f"INV-{row.id:05d}"
    if initial_stock > 0:
        _post_transaction(db, row, "IN", initial_stock, initial_cost, utc_now(), str(payload.get("note") or "Tồn đầu kỳ").strip(), actor)
    record_audit(db, actor, "create", "inventory_product", row.id, f"Thêm hàng hóa {row.name}", details={"sku": row.sku, "initialStock": float(initial_stock)})
    db.commit()
    db.refresh(row)
    return _product_data(row)


def update_product(db: Session, product_id: int, payload: dict, actor: User):
    row = db.get(InventoryProduct, product_id)
    if not row:
        raise HTTPException(404, "Không tìm thấy hàng hóa.")
    for field, key in (("name", "name"), ("category", "category"), ("unit", "unit")):
        if key in payload:
            value = str(payload.get(key) or "").strip()
            if not value:
                raise HTTPException(422, "Tên hàng, danh mục và đơn vị tính không được để trống.")
            if key == "name" and db.query(InventoryProduct).filter(func.lower(InventoryProduct.name) == value.lower(), InventoryProduct.id != row.id).first():
                raise HTTPException(409, "Tên hàng hóa đã tồn tại.")
            setattr(row, field, value)
    if "sku" in payload:
        sku = str(payload.get("sku") or "").strip().upper()
        if not sku:
            raise HTTPException(422, "Mã hàng không được để trống.")
        duplicate = db.query(InventoryProduct).filter(InventoryProduct.sku == sku, InventoryProduct.id != row.id).first()
        if duplicate:
            raise HTTPException(409, "Mã hàng đã tồn tại.")
        row.sku = sku
    if "minimumStock" in payload:
        row.minimum_stock = _decimal(payload.get("minimumStock"), "Mức tồn tối thiểu")
    if "isActive" in payload:
        row.is_active = bool(payload.get("isActive"))
    record_audit(db, actor, "update", "inventory_product", row.id, f"Cập nhật hàng hóa {row.name}", details={"fields": list(payload.keys())})
    db.commit()
    db.refresh(row)
    return _product_data(row)


def list_transactions(db: Session, q: str = "", transaction_type: str = "all", category: str = "all", product_id: int | None = None, date_from: str = "", date_to: str = "", page: int = 1, page_size: int = 30):
    query = db.query(InventoryTransaction).options(joinedload(InventoryTransaction.product), joinedload(InventoryTransaction.created_by)).join(InventoryTransaction.product)
    if q.strip():
        term = q.strip()
        query = query.filter(or_(InventoryProduct.name.contains(term), InventoryProduct.sku.contains(term), InventoryTransaction.note.contains(term)))
    if transaction_type in {"IN", "OUT"}:
        query = query.filter(InventoryTransaction.transaction_type == transaction_type)
    if category not in {"", "all"}:
        query = query.filter(InventoryProduct.category == category)
    if product_id:
        query = query.filter(InventoryTransaction.product_id == product_id)
    if date_from:
        query = query.filter(InventoryTransaction.occurred_at >= _local_to_utc(f"{date_from}T00:00:00"))
    if date_to:
        query = query.filter(InventoryTransaction.occurred_at < _local_to_utc(f"{date_to}T00:00:00") + timedelta(days=1))
    total = query.count()
    page, page_size = max(page, 1), min(max(page_size, 10), 1000)
    rows = query.order_by(InventoryTransaction.occurred_at.desc(), InventoryTransaction.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_transaction_data(row) for row in rows], "pagination": pagination(page, page_size, total)}


def create_transaction(db: Session, payload: dict, actor: User):
    transaction_type = str(payload.get("type") or "").upper()
    if transaction_type not in {"IN", "OUT"}:
        raise HTTPException(422, "Loại giao dịch phải là Nhập hoặc Xuất.")
    try:
        product_id = int(payload.get("productId"))
    except (TypeError, ValueError):
        raise HTTPException(422, "Hàng hóa không hợp lệ.")
    product = db.query(InventoryProduct).filter(InventoryProduct.id == product_id).with_for_update().first()
    if not product or not product.is_active:
        raise HTTPException(404, "Hàng hóa không tồn tại hoặc đã ngừng sử dụng.")
    quantity = _decimal(payload.get("quantity"), "Số lượng", allow_zero=False)
    unit_cost = _decimal(payload.get("unitCost"), "Đơn giá") if transaction_type == "IN" else Decimal(str(product.average_cost or 0))
    if transaction_type == "IN" and unit_cost <= 0:
        raise HTTPException(422, "Đơn giá nhập phải lớn hơn 0.")
    row = _post_transaction(db, product, transaction_type, quantity, unit_cost, _local_to_utc(payload.get("occurredAt")), str(payload.get("note") or "").strip(), actor)
    record_audit(db, actor, "create", "inventory_transaction", row.id, f"{'Nhập' if transaction_type == 'IN' else 'Xuất'} {float(quantity):g} {product.unit} {product.name}", details={"productId": product.id, "stockAfter": float(product.current_stock)})
    db.commit()
    saved = db.query(InventoryTransaction).options(joinedload(InventoryTransaction.product), joinedload(InventoryTransaction.created_by)).filter(InventoryTransaction.id == row.id).one()
    return _transaction_data(saved)


def reverse_transaction(db: Session, transaction_id: int, payload: dict, actor: User):
    original = db.query(InventoryTransaction).options(joinedload(InventoryTransaction.product)).filter(InventoryTransaction.id == transaction_id).with_for_update().first()
    if not original:
        raise HTTPException(404, "Không tìm thấy giao dịch.")
    if original.status == "REVERSED" or db.query(InventoryTransaction).filter(InventoryTransaction.reversed_transaction_id == original.id).first():
        raise HTTPException(409, "Giao dịch đã được hoàn trước đó.")
    reverse_type = "OUT" if original.transaction_type == "IN" else "IN"
    note = str(payload.get("note") or "").strip()
    if not note:
        raise HTTPException(422, "Cần nhập lý do hoàn giao dịch.")
    row = _post_transaction(db, original.product, reverse_type, Decimal(str(original.quantity)), Decimal(str(original.unit_cost)), utc_now(), f"Hoàn giao dịch #{original.id}: {note}", actor, original.id)
    original.status = "REVERSED"
    record_audit(db, actor, "reverse", "inventory_transaction", original.id, f"Hoàn giao dịch kho #{original.id}", details={"reversalId": row.id, "reason": note})
    db.commit()
    saved = db.query(InventoryTransaction).options(joinedload(InventoryTransaction.product), joinedload(InventoryTransaction.created_by)).filter(InventoryTransaction.id == row.id).one()
    return _transaction_data(saved)


def _report_range(period: str, anchor: str):
    try:
        current = date.fromisoformat(anchor) if anchor else vietnam_today()
    except ValueError:
        raise HTTPException(422, "Mốc thời gian không hợp lệ.")
    if period == "day":
        start, end = current, current
    elif period == "week":
        start = current - timedelta(days=current.weekday())
        end = start + timedelta(days=6)
    elif period == "year":
        start, end = date(current.year, 1, 1), date(current.year, 12, 31)
    else:
        start = date(current.year, current.month, 1)
        next_month = date(current.year + (current.month == 12), 1 if current.month == 12 else current.month + 1, 1)
        end = next_month - timedelta(days=1)
        period = "month"
    return period, start, end


def inventory_report(db: Session, period: str = "month", anchor: str = "", category: str = "all", product_id: int | None = None):
    period, start, end = _report_range(period, anchor)
    start_at = _local_to_utc(f"{start.isoformat()}T00:00:00")
    end_at = _local_to_utc(f"{end.isoformat()}T00:00:00") + timedelta(days=1)
    query = db.query(InventoryTransaction).options(joinedload(InventoryTransaction.product)).join(InventoryTransaction.product)
    if category not in {"", "all"}:
        query = query.filter(InventoryProduct.category == category)
    if product_id:
        query = query.filter(InventoryTransaction.product_id == product_id)
    before = query.filter(InventoryTransaction.occurred_at < start_at).all()
    rows = query.filter(InventoryTransaction.occurred_at >= start_at, InventoryTransaction.occurred_at < end_at).order_by(InventoryTransaction.occurred_at).all()
    effect = lambda row: Decimal(str(row.quantity or 0)) * (Decimal("1") if row.transaction_type == "IN" else Decimal("-1"))
    opening = sum((effect(row) for row in before), ZERO)
    inbound = sum((Decimal(str(row.quantity or 0)) for row in rows if row.transaction_type == "IN"), ZERO)
    outbound = sum((Decimal(str(row.quantity or 0)) for row in rows if row.transaction_type == "OUT"), ZERO)
    inbound_cost = sum((Decimal(str(row.total_amount or 0)) for row in rows if row.transaction_type == "IN"), ZERO)
    outbound_cost = sum((Decimal(str(row.total_amount or 0)) for row in rows if row.transaction_type == "OUT"), ZERO)
    series = defaultdict(lambda: {"inQuantity": ZERO, "outQuantity": ZERO, "inCost": ZERO, "outCost": ZERO})
    category_costs = defaultdict(Decimal)
    product_usage = defaultdict(lambda: {"quantity": ZERO, "value": ZERO, "product": None})
    running = opening
    for row in rows:
        local_day = row.occurred_at.replace(tzinfo=UTC).astimezone(VIETNAM_TZ).date()
        bucket = local_day.strftime("%Y-%m") if period == "year" else local_day.isoformat()
        direction = "in" if row.transaction_type == "IN" else "out"
        series[bucket][f"{direction}Quantity"] += Decimal(str(row.quantity or 0))
        series[bucket][f"{direction}Cost"] += Decimal(str(row.total_amount or 0))
        running += effect(row)
        series[bucket]["closingStock"] = running
        if row.transaction_type == "OUT":
            category_costs[row.product.category] += Decimal(str(row.total_amount or 0))
            item = product_usage[row.product_id]
            item["product"] = row.product
            item["quantity"] += Decimal(str(row.quantity or 0))
            item["value"] += Decimal(str(row.total_amount or 0))
    chart = [{"bucket": key, **{name: float(value) for name, value in values.items()}} for key, values in sorted(series.items())]
    categories = [{"category": key, "value": float(value)} for key, value in sorted(category_costs.items(), key=lambda item: item[1], reverse=True)]
    top_usage = [{"productId": key, "productName": value["product"].name, "unit": value["product"].unit, "quantity": float(value["quantity"]), "value": float(value["value"])} for key, value in sorted(product_usage.items(), key=lambda item: item[1]["value"], reverse=True)[:10]]
    return {
        "period": period,
        "dateFrom": start.isoformat(),
        "dateTo": end.isoformat(),
        "summary": {"inboundCost": float(inbound_cost), "outboundCost": float(outbound_cost), "openingStock": float(opening), "closingStock": float(opening + inbound - outbound), "netMovement": float(inbound - outbound), **_product_summary(db)},
        "series": chart,
        "categoryCosts": categories,
        "topUsage": top_usage,
    }
