from sqlalchemy.orm import Session
from ..services import alerts_service, dashboard_service

def dashboard(db: Session, include_financial: bool = True): return dashboard_service.dashboard(db, include_financial)
def reports(db: Session, date_from: str | None, date_to: str | None): return dashboard_service.reports(db, date_from, date_to)
def alerts(db: Session, user_id: int, expiring_days: int, pt_sessions: int, limit: int, include_financial: bool = True): return alerts_service.alerts(db, user_id, expiring_days, pt_sessions, limit, include_financial)
def mark_alert_read(db: Session, user_id: int, alert_key: str, include_financial: bool = True): return alerts_service.mark_read(db, user_id, alert_key, include_financial)
def mark_all_alerts_read(db: Session, user_id: int, include_financial: bool = True): return alerts_service.mark_all_read(db, user_id, include_financial)
