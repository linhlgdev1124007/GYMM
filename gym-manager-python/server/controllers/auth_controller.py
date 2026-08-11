from fastapi import HTTPException, Request, Response, status
from sqlalchemy.orm import Session

from ..models import AuthSession, User
from ..config import settings
from ..middleware.request_security import CSRF_COOKIE, new_csrf_token, set_csrf_cookie
from ..security import create_session, token_digest, verify_password
from ..services.audit_service import record_audit


def login(payload: dict, request: Request, response: Response, db: Session):
    username = str(payload.get("username", "")).strip().lower()[:80]
    password = str(payload.get("password", ""))
    user = db.query(User).filter(User.username == username, User.is_active == True).first()
    if not user or not verify_password(password, user.password_hash):
        record_audit(
            db, None, "login_failed", "auth", user.id if user else None,
            "Đăng nhập thất bại", details={"username": username},
            ip_address=getattr(request.state, "client_ip", None),
        )
        db.commit()
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Tên đăng nhập hoặc mật khẩu không đúng.")
    token = create_session(db, user)
    response.set_cookie(
        "gym_session", token, httponly=True, samesite="strict",
        secure=settings.secure_cookies, max_age=settings.session_days * 86400, path="/",
    )
    set_csrf_cookie(response, new_csrf_token())
    record_audit(
        db, user, "login", "auth", user.id, "Đăng nhập hệ thống",
        ip_address=getattr(request.state, "client_ip", None),
    )
    db.commit()
    return {"user": {"id": user.id, "username": user.username, "displayName": user.display_name, "role": user.role}}


def logout(request: Request, response: Response, db: Session):
    token = request.cookies.get("gym_session")
    if token:
        session = db.query(AuthSession).filter(AuthSession.token_hash == token_digest(token)).first()
        if session:
            record_audit(
                db, session.user, "logout", "auth", session.user_id, "Đăng xuất hệ thống",
                ip_address=getattr(request.state, "client_ip", None),
            )
            db.delete(session)
        db.commit()
    response.delete_cookie("gym_session", path="/")
    response.delete_cookie(CSRF_COOKIE, path="/")
    return {"ok": True}


def me(request: Request, response: Response, user: User):
    if not request.cookies.get(CSRF_COOKIE):
        set_csrf_cookie(response, new_csrf_token())
    return {"id": user.id, "username": user.username, "displayName": user.display_name, "role": user.role}
