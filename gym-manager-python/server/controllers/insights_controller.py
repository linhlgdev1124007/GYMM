from sqlalchemy.orm import Session
from ..services import alerts_service, dashboard_service

def dashboard(db: Session): return dashboard_service.dashboard(db)
def reports(db: Session, date_from: str | None, date_to: str | None): return dashboard_service.reports(db, date_from, date_to)
def alerts(db: Session, expiring_days: int, pt_sessions: int, limit: int): return alerts_service.alerts(db, expiring_days, pt_sessions, limit)
