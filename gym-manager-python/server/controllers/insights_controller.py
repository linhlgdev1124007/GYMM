from sqlalchemy.orm import Session
from ..services import alerts_service, dashboard_service

def dashboard(db: Session): return dashboard_service.dashboard(db)
def reports(db: Session, date_from: str | None, date_to: str | None): return dashboard_service.reports(db, date_from, date_to)
def alerts(db: Session, user_id: int, expiring_days: int, pt_sessions: int, limit: int): return alerts_service.alerts(db, user_id, expiring_days, pt_sessions, limit)
def mark_alert_read(db: Session, user_id: int, alert_key: str): return alerts_service.mark_read(db, user_id, alert_key)
def mark_all_alerts_read(db: Session, user_id: int): return alerts_service.mark_all_read(db, user_id)
