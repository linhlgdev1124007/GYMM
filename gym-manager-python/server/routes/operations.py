from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..controllers import operations_controller
from ..database import get_db
from ..dependencies import current_user, require_roles

router = APIRouter(prefix="/api", tags=["operations"], dependencies=[Depends(current_user)])


@router.get("/trainers", dependencies=[Depends(require_roles("admin", "manager"))])
def trainers(q: str = "", page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return operations_controller.list_trainers(db, q=q, page=page, page_size=page_size)


@router.post("/trainers", dependencies=[Depends(require_roles("admin", "manager"))])
def create_trainer(payload: dict, db: Session = Depends(get_db)):
    return operations_controller.create_trainer(db, payload)


@router.patch("/trainers/{trainer_id}", dependencies=[Depends(require_roles("admin", "manager"))])
def update_trainer(trainer_id: int, payload: dict, db: Session = Depends(get_db)):
    return operations_controller.update_trainer(db, trainer_id, payload)


@router.delete("/trainers/{trainer_id}", dependencies=[Depends(require_roles("admin", "manager"))])
def delete_trainer(trainer_id: int, db: Session = Depends(get_db)):
    return operations_controller.delete_trainer(db, trainer_id)


@router.get("/training")
def training(type: str = "1:1", q: str = "", assignment: str = "all", page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return operations_controller.list_pt(db, group_type=type, q=q, assignment=assignment, page=page, page_size=page_size)


@router.post("/members/{member_id}/training", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def create_training(member_id: int, payload: dict, db: Session = Depends(get_db)):
    return operations_controller.create_pt(db, member_id, payload)


@router.patch("/training/{enrollment_id}", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def update_training(enrollment_id: int, payload: dict, db: Session = Depends(get_db)):
    return operations_controller.update_pt(db, enrollment_id, payload)


@router.get("/checkins/candidates")
def candidates(q: str = "", db: Session = Depends(get_db)):
    return operations_controller.checkin_candidates(db, q)


@router.get("/checkins")
def checkins(limit: int = Query(30, ge=1, le=100), db: Session = Depends(get_db)):
    return operations_controller.recent_checkins(db, limit)


@router.post("/checkins", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def checkin(payload: dict, db: Session = Depends(get_db)):
    return operations_controller.create_checkin(db, payload)


@router.patch("/checkins/{session_id}/checkout", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def checkout(session_id: int, db: Session = Depends(get_db)):
    return operations_controller.checkout(db, session_id)


@router.get("/payments")
def payments(q: str = "", method: str = "all", date_from: str = Query("", alias="dateFrom"), date_to: str = Query("", alias="dateTo"), page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return operations_controller.list_payments(db, q=q, method=method, date_from=date_from, date_to=date_to, page=page, page_size=page_size)


@router.get("/settings", dependencies=[Depends(require_roles("admin"))])
def settings(db: Session = Depends(get_db)):
    return operations_controller.settings(db)
