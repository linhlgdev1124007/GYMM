import os
from pathlib import Path
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GYM_ENV", "test")
os.environ.setdefault(
    "GYM_DATABASE_PATH",
    str(Path(tempfile.mkdtemp(prefix="pulsefit-operations-tests-")) / "bootstrap.sqlite3"),
)


def make_session(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'settings.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def active_titles(db):
    from server.models import EmployeeJobTitle

    return {
        row.name
        for row in db.query(EmployeeJobTitle)
        .filter(EmployeeJobTitle.is_active == True)
        .all()
    }


def test_renaming_default_job_title_does_not_recreate_old_name(tmp_path):
    from server.models import EmployeeJobTitle
    from server.services.operations_service import (
        ensure_employee_job_titles,
        update_job_title,
    )

    db = make_session(tmp_path)
    try:
        ensure_employee_job_titles(db)
        db.commit()
        sale = db.query(EmployeeJobTitle).filter(EmployeeJobTitle.name == "Sale").one()

        update_job_title(db, sale.id, {"name": "sale f", "renameEmployees": True})
        ensure_employee_job_titles(db)
        db.commit()

        names = active_titles(db)
        assert "sale f" in names
        assert "Sale" not in names
    finally:
        db.close()


def test_deleting_default_job_title_does_not_recreate_it(tmp_path):
    from server.models import EmployeeJobTitle
    from server.services.operations_service import (
        delete_job_title,
        ensure_employee_job_titles,
    )

    db = make_session(tmp_path)
    try:
        ensure_employee_job_titles(db)
        db.commit()
        marketing = db.query(EmployeeJobTitle).filter(EmployeeJobTitle.name == "Marketing").one()

        delete_job_title(db, marketing.id)
        ensure_employee_job_titles(db)
        db.commit()

        assert "Marketing" not in active_titles(db)
    finally:
        db.close()
