from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from ..controllers import operations_controller
from ..database import get_db
from ..dependencies import current_user, require_roles
from ..models import User

router = APIRouter(prefix="/api", tags=["operations"], dependencies=[Depends(current_user)])


@router.get("/trainers", dependencies=[Depends(require_roles("admin", "manager"))])
def trainers(q: str = "", title: str = "all", page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return operations_controller.list_trainers(db, q=q, title=title, page=page, page_size=page_size)


@router.get("/trainers/attendance", dependencies=[Depends(require_roles("admin", "manager"))])
def trainer_attendance(day: str = "", db: Session = Depends(get_db)):
    return operations_controller.employee_attendance(db, day)


@router.get("/trainers/shift-report", dependencies=[Depends(require_roles("admin", "manager"))])
def trainer_shift_report(
    range_type: str = Query("today", alias="rangeType"),
    day: str = "",
    week_start: str = Query("", alias="weekStart"),
    q: str = "",
    title: str = "all",
    status: str = "all",
    shift_kind: str = Query("all", alias="shiftKind"),
    sort: str = "severity",
    page: int = Query(1, ge=1),
    page_size: int = Query(30, ge=10, le=1000, alias="pageSize"),
    db: Session = Depends(get_db),
):
    return operations_controller.employee_shift_report(
        db,
        range_type=range_type,
        day=day,
        week_start=week_start,
        q=q,
        title=title,
        status=status,
        shift_kind=shift_kind,
        sort=sort,
        page=page,
        page_size=page_size,
    )


@router.post("/trainer-shifts/{shift_id}/override", dependencies=[Depends(require_roles("admin", "manager"))])
def approve_trainer_shift_override(shift_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return operations_controller.approve_employee_shift_override(db, shift_id, payload, user)


@router.post("/trainers", dependencies=[Depends(require_roles("admin", "manager"))])
def create_trainer(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return operations_controller.create_trainer(db, payload, user)


@router.patch("/trainers/{trainer_id}", dependencies=[Depends(require_roles("admin", "manager"))])
def update_trainer(trainer_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return operations_controller.update_trainer(db, trainer_id, payload, user)


@router.delete("/trainers/{trainer_id}", dependencies=[Depends(require_roles("admin", "manager"))])
def delete_trainer(trainer_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return operations_controller.delete_trainer(db, trainer_id, user)


@router.get("/trainers/{trainer_id}/shifts", dependencies=[Depends(require_roles("admin", "manager"))])
def list_trainer_shifts(
    trainer_id: int,
    date_from: str = Query("", alias="dateFrom"),
    date_to: str = Query("", alias="dateTo"),
    db: Session = Depends(get_db),
):
    return operations_controller.list_employee_shifts(db, trainer_id, date_from=date_from, date_to=date_to)


@router.get("/trainer-shifts", dependencies=[Depends(require_roles("admin", "manager"))])
def list_trainer_shifts_week(
    date_from: str = Query("", alias="dateFrom"),
    date_to: str = Query("", alias="dateTo"),
    db: Session = Depends(get_db),
):
    return operations_controller.list_employee_shifts_week(db, date_from=date_from, date_to=date_to)


@router.post("/trainers/{trainer_id}/shifts", dependencies=[Depends(require_roles("admin", "manager"))])
def create_trainer_shift(trainer_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return operations_controller.create_employee_shift(db, trainer_id, payload, user)


@router.post("/trainers/{trainer_id}/shifts/bulk", dependencies=[Depends(require_roles("admin", "manager"))])
def create_trainer_shifts_bulk(trainer_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return operations_controller.create_employee_shifts_bulk(db, trainer_id, payload, user)


@router.post("/trainer-shifts/import", dependencies=[Depends(require_roles("admin", "manager"))])
def import_trainer_shifts(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return operations_controller.import_employee_shifts(db, payload, user)


@router.post("/trainer-shifts/import-preview", dependencies=[Depends(require_roles("admin", "manager"))])
async def preview_trainer_shift_import(file: UploadFile = File(...)):
    content = await file.read()
    return operations_controller.preview_employee_shift_excel(content, file.filename or "")


@router.put("/trainer-shifts/week", dependencies=[Depends(require_roles("admin", "manager"))])
def replace_trainer_shifts_week(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return operations_controller.replace_employee_shifts_week(db, payload, user)


@router.patch("/trainer-shifts/{shift_id}", dependencies=[Depends(require_roles("admin", "manager"))])
def update_trainer_shift(shift_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return operations_controller.update_employee_shift(db, shift_id, payload, user)


@router.delete("/trainer-shifts/{shift_id}", dependencies=[Depends(require_roles("admin", "manager"))])
def delete_trainer_shift(shift_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager"))):
    return operations_controller.delete_employee_shift(db, shift_id, user)


@router.get("/training")
def training(type: str = "1:1", q: str = "", assignment: str = "all", page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return operations_controller.list_pt(db, group_type=type, q=q, assignment=assignment, page=page, page_size=page_size)


@router.post("/members/{member_id}/training", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def create_training(member_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    return operations_controller.create_pt(db, member_id, payload, user)


@router.patch("/training/{enrollment_id}", dependencies=[Depends(require_roles("admin", "manager", "receptionist", "coach"))])
def update_training(enrollment_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist", "coach"))):
    return operations_controller.update_pt(db, enrollment_id, payload, user)


@router.get("/checkins/candidates", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def candidates(q: str = "", db: Session = Depends(get_db)):
    return operations_controller.checkin_candidates(db, q)


@router.get("/checkins", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def checkins(day: str = "", type: str = "all", page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return operations_controller.recent_checkins(db, day=day, person_type=type, page=page, page_size=page_size)


@router.post("/checkins", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def checkin(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    return operations_controller.create_checkin(db, payload, user)


@router.patch("/checkins/{session_id}/checkout", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def checkout(session_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin", "manager", "receptionist"))):
    return operations_controller.checkout(db, session_id, user)


@router.get("/payments", dependencies=[Depends(require_roles("admin", "manager", "receptionist"))])
def payments(q: str = "", method: str = "all", date_from: str = Query("", alias="dateFrom"), date_to: str = Query("", alias="dateTo"), page: int = Query(1, ge=1), page_size: int = Query(20, ge=10, le=100, alias="pageSize"), db: Session = Depends(get_db)):
    return operations_controller.list_payments(db, q=q, method=method, date_from=date_from, date_to=date_to, page=page, page_size=page_size)


@router.get("/settings", dependencies=[Depends(require_roles("admin"))])
def settings(db: Session = Depends(get_db)):
    return operations_controller.settings(db)


@router.post("/settings/job-titles", dependencies=[Depends(require_roles("admin"))])
def create_job_title(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return operations_controller.create_job_title(db, payload, user)


@router.patch("/settings/job-titles/{title_id}", dependencies=[Depends(require_roles("admin"))])
def update_job_title(title_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return operations_controller.update_job_title(db, title_id, payload, user)


@router.delete("/settings/job-titles/{title_id}", dependencies=[Depends(require_roles("admin"))])
def delete_job_title(title_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return operations_controller.delete_job_title(db, title_id, user)


@router.post("/settings/bank-accounts", dependencies=[Depends(require_roles("admin"))])
def create_bank_account(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return operations_controller.create_bank_account(db, payload, user)


@router.patch("/settings/bank-accounts/{account_id}", dependencies=[Depends(require_roles("admin"))])
def update_bank_account(account_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return operations_controller.update_bank_account(db, account_id, payload, user)


@router.delete("/settings/bank-accounts/{account_id}", dependencies=[Depends(require_roles("admin"))])
def delete_bank_account(account_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return operations_controller.delete_bank_account(db, account_id, user)
