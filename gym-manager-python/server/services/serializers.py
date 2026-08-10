from datetime import date, datetime


def iso(value):
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
    if membership.status not in ("active", "pending"):
        return membership.status
    if membership.expires_at:
        days = (membership.expires_at - date.today()).days
        if days < 0:
            return "expired"
        if days <= 14:
            return "expiring"
    return membership.status


def membership_data(membership, include_payments=False):
    data = {
        "id": membership.id,
        "code": membership.code,
        "memberId": membership.customer_id,
        "memberName": membership.customer.person.display_name if getattr(membership, "customer", None) else None,
        "package": package_data(membership.package),
        "registeredAt": iso(membership.registered_at),
        "startsAt": iso(membership.starts_at),
        "expiresAt": iso(membership.expires_at),
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
    return data


def pt_data(enrollment):
    return {
        "id": enrollment.id,
        "memberId": enrollment.customer_id,
        "member": {
            "id": enrollment.customer.id,
            "code": enrollment.customer.customer_code,
            **person_data(enrollment.customer.person),
        } if getattr(enrollment, "customer", None) else None,
        "coach": employee_data(enrollment.coach),
        "type": enrollment.group_type,
        "startsAt": iso(enrollment.starts_at),
        "expiresAt": iso(enrollment.expires_at),
        "totalSessions": enrollment.total_sessions,
        "remainingSessions": enrollment.remaining_sessions,
        "scheduleDays": [value.strip() for value in (enrollment.schedule_days or "").split(",") if value.strip()],
        "scheduleTime": enrollment.schedule_time,
        "status": enrollment.status,
    }


def payment_data(payment):
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
        "status": "paid",
    }


def pagination(page: int, page_size: int, total: int):
    return {"page": page, "pageSize": page_size, "total": total, "pages": max((total + page_size - 1) // page_size, 1)}
