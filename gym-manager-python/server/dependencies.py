from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session, joinedload

from .database import get_db
from .models import AuthSession, User
from .security import token_digest
from .timeutils import utc_now


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get("gym_session")
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    session = db.query(AuthSession).options(joinedload(AuthSession.user)).filter(
        AuthSession.token_hash == token_digest(token),
        AuthSession.expires_at > utc_now(),
    ).first()
    if not session or not session.user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session expired")
    return session.user


def require_roles(*roles: str):
    def dependency(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="You do not have permission to perform this action")
        return user
    return dependency
