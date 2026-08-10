from datetime import datetime, timedelta
import hashlib
import hmac
import os
import secrets

from sqlalchemy.orm import Session

from .models import AuthSession, User

PBKDF2_ITERATIONS = 310_000
SESSION_DAYS = 7


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
    raw_token = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=token_digest(raw_token), expires_at=datetime.utcnow() + timedelta(days=SESSION_DAYS)))
    db.commit()
    return raw_token


def ensure_admin_user(db: Session) -> None:
    if db.query(User).first():
        return
    username = os.getenv("GYM_ADMIN_USERNAME", "admin")
    password = os.getenv("GYM_ADMIN_PASSWORD", "PulseFit@2026")
    db.add(User(username=username, display_name="Gym Manager", password_hash=hash_password(password), role="admin", is_active=True))
    db.commit()
