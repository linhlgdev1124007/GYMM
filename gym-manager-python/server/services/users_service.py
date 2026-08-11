import re

from fastapi import HTTPException
from sqlalchemy.orm import Session, joinedload

from ..models import Employee, User
from ..security import hash_password
from .audit_service import record_audit
from .serializers import employee_data

ROLES = {
    "admin": "Toàn quyền hệ thống, tài khoản và phân quyền",
    "manager": "Quản lý hội viên, gói tập, nhân viên, báo cáo và nhật ký",
    "receptionist": "Hội viên, đăng ký gói, thanh toán và check-in",
    "coach": "Hồ sơ hội viên và vận hành PT",
}


def user_data(user: User):
    return {
        "id": user.id,
        "username": user.username,
        "displayName": user.display_name,
        "role": user.role,
        "active": user.is_active,
        "employee": employee_data(user.employee) if user.employee else None,
        "createdAt": user.created_at.isoformat(),
    }


def list_users(db: Session):
    rows = db.query(User).options(
        joinedload(User.employee).joinedload(Employee.person)
    ).order_by(User.is_active.desc(), User.display_name).all()
    linked_ids = {row.employee_id for row in rows if row.employee_id}
    employees = db.query(Employee).options(joinedload(Employee.person)).filter(
        Employee.status == "active"
    ).order_by(Employee.person_id).all()
    return {
        "items": [user_data(row) for row in rows],
        "employees": [employee_data(row) for row in employees if row.id not in linked_ids],
        "roles": [{"value": key, "label": key.title(), "description": value} for key, value in ROLES.items()],
    }


def _validate(payload: dict, *, creating=False):
    username = str(payload.get("username", "")).strip().lower()
    if creating and not re.fullmatch(r"[a-z0-9._-]{3,40}", username):
        raise HTTPException(422, "Tên đăng nhập cần 3–40 ký tự: chữ thường, số, dấu chấm, gạch ngang hoặc gạch dưới.")
    password = str(payload.get("password", ""))
    if (creating or password) and len(password) < 8:
        raise HTTPException(422, "Mật khẩu phải có ít nhất 8 ký tự.")
    role = payload.get("role")
    if role not in ROLES:
        raise HTTPException(422, "Vai trò tài khoản không hợp lệ.")
    return username, password, role


def create_user(db: Session, payload: dict, actor: User):
    username, password, role = _validate(payload, creating=True)
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(409, "Tên đăng nhập này đã tồn tại.")
    employee_id = payload.get("employeeId") or None
    employee = db.get(Employee, int(employee_id)) if employee_id else None
    if employee_id and not employee:
        raise HTTPException(422, "Nhân viên được chọn không hợp lệ.")
    if employee_id and db.query(User).filter(User.employee_id == employee.id).first():
        raise HTTPException(409, "Nhân viên này đã có tài khoản đăng nhập.")
    display_name = str(payload.get("displayName", "")).strip()
    if not display_name and employee:
        display_name = employee.person.display_name
    if not display_name:
        raise HTTPException(422, "Tên hiển thị là bắt buộc.")
    row = User(
        username=username,
        display_name=display_name,
        password_hash=hash_password(password),
        role=role,
        is_active=True,
        employee_id=employee.id if employee else None,
    )
    db.add(row)
    db.flush()
    record_audit(db, actor, "create", "user", row.id, f"Tạo tài khoản {username}", details={"displayName": display_name, "role": role, "employeeId": row.employee_id})
    db.commit()
    return user_data(row)


def update_user(db: Session, user_id: int, payload: dict, actor: User):
    row = db.query(User).options(joinedload(User.employee).joinedload(Employee.person)).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(404, "Không tìm thấy tài khoản.")
    role = payload.get("role", row.role)
    if role not in ROLES:
        raise HTTPException(422, "Vai trò tài khoản không hợp lệ.")
    active = bool(payload.get("active", row.is_active))
    if row.id == actor.id and not active:
        raise HTTPException(422, "Bạn không thể tự khóa tài khoản đang đăng nhập.")
    if row.role == "admin" and (role != "admin" or not active):
        active_admins = db.query(User).filter(User.role == "admin", User.is_active == True).count()
        if active_admins <= 1:
            raise HTTPException(422, "Hệ thống phải luôn có ít nhất một tài khoản Admin hoạt động.")
    employee_id = payload.get("employeeId", row.employee_id) or None
    if employee_id:
        employee_id = int(employee_id)
        if not db.get(Employee, employee_id):
            raise HTTPException(422, "Nhân viên được chọn không hợp lệ.")
        linked = db.query(User).filter(User.employee_id == employee_id, User.id != row.id).first()
        if linked:
            raise HTTPException(409, "Nhân viên này đã có tài khoản đăng nhập.")
    password = str(payload.get("password", ""))
    if password and len(password) < 8:
        raise HTTPException(422, "Mật khẩu mới phải có ít nhất 8 ký tự.")
    row.display_name = str(payload.get("displayName", row.display_name)).strip() or row.display_name
    row.role = role
    row.is_active = active
    row.employee_id = employee_id
    if password:
        row.password_hash = hash_password(password)
    record_audit(db, actor, "update", "user", row.id, f"Cập nhật tài khoản {row.username}", details={"fields": list(payload.keys()), "role": role, "active": active, "passwordReset": bool(password)})
    db.commit()
    db.refresh(row)
    return user_data(row)
