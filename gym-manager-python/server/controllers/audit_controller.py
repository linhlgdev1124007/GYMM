from sqlalchemy.orm import Session

from ..services import audit_service


def list_logs(db: Session, **params):
    return audit_service.list_audit_logs(db, **params)
