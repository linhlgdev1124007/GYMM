from datetime import date, datetime
import json

from ..timeutils import utc_iso, vietnam_today


def iso(value):
    if isinstance(value, datetime):
        return utc_iso(value)
    if isinstance(value, date):
        return value.isoformat()
    return value.isoformat() if value else None


def person_data(person):
    return {
        "name": person.display_name,
        "phone": person.phone,
        "email": person.email,
        "gender": person.gender,
        "dateOfBirth": iso(person.date_of_birth),
    }


def employee_data(employee):
    if not employee:
        return None
    return {
        "id": employee.id,
        "code": employee.employee_code,
        "name": employee.person.display_name,
        "phone": employee.person.phone,
        "email": employee.person.email,
        "title": employee.job_title,
        "status": employee.status,
    }


def package_data(package):
    return {
        "id": package.id,
        "code": package.code,
        "name": package.name,
        "category": package.category,
        "durationDays": package.duration_days,
        "price": package.price or 0,
        "active": package.is_active,
    }


def membership_status(membership) -> str:
    today = vietnam_today()
    if membership.status not in ("active", "pending"):
        return membership.status
    if any(
        not freeze.completed_at and freeze.starts_at <= today <= freeze.ends_at
        for freeze in getattr(membership, "freezes", [])
    ):
        return "frozen"
    if membership.expires_at:
        days = (membership.expires_at - today).days
        if days < 0:
            return "expired"
    return membership.status


def freeze_data(freeze):
    today = vietnam_today()
    status = "active" if freeze.starts_at <= today <= freeze.ends_at else ("scheduled" if today < freeze.starts_at else "completed")
    return {
        "id": freeze.id,
        "startsAt": iso(freeze.starts_at),
        "endsAt": iso(freeze.ends_at),
        "completedAt": iso(freeze.completed_at),
        "compensatedDays": freeze.compensated_days,
        "reason": freeze.reason,
        "status": "completed" if freeze.completed_at else status,
        "createdAt": iso(freeze.created_at),
        "createdBy": freeze.created_by.display_name if freeze.created_by else "Hệ thống",
    }


def membership_event_data(event):
    try:
        details = json.loads(event.details_json) if event.details_json else None
    except (TypeError, ValueError):
        details = None
    return {
        "id": event.id,
        "membershipId": event.membership_id,
        "action": event.action,
        "effectiveAt": iso(event.effective_at),
        "reason": event.reason,
        "fromMember": event.from_customer.person.display_name if event.from_customer else None,
        "toMember": event.to_customer.person.display_name if event.to_customer else None,
        "fromPackage": event.from_package.name if event.from_package else None,
        "toPackage": event.to_package.name if event.to_package else None,
        "createdAt": iso(event.created_at),
        "createdBy": event.created_by.display_name if event.created_by else "Hệ thống",
        "details": details,
    }


def membership_data(membership, include_payments=False, include_history=False):
    data = {
        "id": membership.id,
        "code": membership.code,
        "memberId": membership.customer_id,
        "memberName": membership.customer.person.display_name if getattr(membership, "customer", None) else None,
        "package": package_data(membership.package),
        "registeredAt": iso(membership.registered_at),
        "startsAt": iso(membership.starts_at),
        "expiresAt": iso(membership.expires_at),
        "activatedAt": iso(membership.activated_at),
        "finalPrice": membership.final_price or 0,
        "depositAmount": membership.deposit_amount or 0,
        "paidAmount": membership.paid_amount or 0,
        "debtAmount": membership.debt_amount or 0,
        "debtDueDate": iso(membership.debt_due_date),
        "status": membership_status(membership),
        "saleOnline": employee_data(membership.sale_online_employee),
        "directSale": employee_data(membership.direct_sales_employee),
    }
    if include_payments:
        data["payments"] = [payment_data(payment) for payment in sorted(membership.payments, key=lambda row: row.paid_at, reverse=True)]
    if include_history:
        data["freezes"] = [freeze_data(row) for row in sorted(membership.freezes, key=lambda row: row.starts_at, reverse=True)]
        data["events"] = [membership_event_data(row) for row in sorted(membership.events, key=lambda row: row.created_at, reverse=True)]
    return data


def pt_data(enrollment):
    from .training_schedule import schedule_data

    coaches = [employee_data(assignment.coach) for assignment in enrollment.coach_assignments]
    schedule = schedule_data(enrollment)
    return {
        "id": enrollment.id,
        "memberId": enrollment.customer_id,
        "member": {
            "id": enrollment.customer.id,
            "code": enrollment.customer.customer_code,
            **person_data(enrollment.customer.person),
        } if getattr(enrollment, "customer", None) else None,
        "coach": coaches[0] if coaches else None,
        "coaches": coaches,
        "type": enrollment.group_type,
        "startsAt": iso(enrollment.starts_at),
        "expiresAt": iso(enrollment.expires_at),
        "totalSessions": enrollment.total_sessions,
        "remainingSessions": enrollment.remaining_sessions,
        "schedule": schedule,
        # Kept in responses during the transition for older clients.
        "scheduleDays": [slot["day"] for slot in schedule],
        "scheduleTime": schedule[0]["time"] if schedule and len({slot["time"] for slot in schedule}) == 1 else None,
        "status": enrollment.status,
    }


def payment_data(payment):
    receipts = [
        {
            "id": receipt.id,
            "url": receipt.file_path,
            "name": receipt.original_name or f"Chứng từ {index + 1}",
            "uploadedAt": iso(receipt.uploaded_at),
            "uploadedBy": receipt.uploaded_by.display_name
            if getattr(receipt, "uploaded_by", None)
            else None,
        }
        for index, receipt in enumerate(
            sorted(getattr(payment, "receipts", []), key=lambda row: row.uploaded_at)
        )
    ]
    if not receipts and payment.receipt_image_path:
        receipts = [{"id": None, "url": payment.receipt_image_path, "name": "Chứng từ", "uploadedAt": iso(payment.paid_at), "uploadedBy": None}]
    return {
        "id": payment.id,
        "number": payment.payment_no,
        "memberId": payment.customer_id,
        "memberName": payment.customer.person.display_name if getattr(payment, "customer", None) else None,
        "membershipId": payment.membership_id,
        "description": payment.membership.package.name if getattr(payment, "membership", None) and payment.membership.package else payment.note,
        "amount": payment.amount or 0,
        "method": payment.method,
        "channel": payment.channel,
        "paidAt": iso(payment.paid_at),
        "receiptUrl": payment.receipt_image_path,
        "receipts": receipts,
        "receiptCount": len(receipts),
        "status": "paid",
    }


def pagination(page: int, page_size: int, total: int):
    return {"page": page, "pageSize": page_size, "total": total, "pages": max((total + page_size - 1) // page_size, 1)}
