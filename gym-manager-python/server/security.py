from datetime import timedelta
import hashlib
import hmac
import os
import secrets

from sqlalchemy.orm import Session

from .config import settings
from .models import AuthSession, User
from .timeutils import utc_now

PBKDF2_ITERATIONS = 310_000
SESSION_DAYS = settings.session_days


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PBKDF2_ITERATIONS)
    return f"{PBKDF2_ITERATIONS}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        iterations, salt_hex, digest_hex = encoded.split("$", 2)
        candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations))
        return hmac.compare_digest(candidate.hex(), digest_hex)
    except (TypeError, ValueError):
        return False


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_session(db: Session, user: User) -> str:
    now = utc_now()
    db.query(AuthSession).filter(AuthSession.expires_at <= now).delete(synchronize_session=False)
    existing = db.query(AuthSession).filter(AuthSession.user_id == user.id).order_by(
        AuthSession.created_at.desc(), AuthSession.id.desc()
    ).all()
    for old_session in existing[settings.max_sessions_per_user - 1:]:
        db.delete(old_session)
    raw_token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=token_digest(raw_token), expires_at=now + timedelta(days=SESSION_DAYS)))
    db.commit()
    return raw_token


def ensure_admin_user(db: Session) -> None:
    if db.query(User).first():
        return
    username = os.getenv("GYM_ADMIN_USERNAME", "admin")
    password = os.getenv("GYM_ADMIN_PASSWORD", "PulseFit@2026")
    db.add(User(username=username, display_name="Gym Manager", password_hash=hash_password(password), role="admin", is_active=True))
    db.commit()
