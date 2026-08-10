from pathlib import Path
import os

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.getenv("GYM_DATABASE_PATH", ROOT_DIR / "gym.sqlite3"))
if os.getenv("VERCEL"):
    DATABASE_URL = f"sqlite:///file:{DATABASE_PATH.as_posix()}?mode=ro&uri=true"
else:
    DATABASE_URL = f"sqlite:///{DATABASE_PATH}"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_pt_coaches():
    """Make the legacy coach optional before the assignment table is created."""
    if os.getenv("VERCEL"):
        return
    with engine.connect() as connection:
        columns = connection.exec_driver_sql("PRAGMA table_info(pt_enrollments)").mappings().all()
    coach_column = next((column for column in columns if column["name"] == "coach_id"), None)
    if not coach_column or not coach_column["notnull"]:
        return
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN")
        cursor.execute("""
            CREATE TABLE pt_enrollments_new (
                id INTEGER NOT NULL PRIMARY KEY,
                customer_id INTEGER NOT NULL REFERENCES customers (id),
                coach_id INTEGER REFERENCES employees (id),
                group_type VARCHAR(20) NOT NULL,
                starts_at DATE NOT NULL,
                expires_at DATE,
                total_sessions INTEGER NOT NULL,
                remaining_sessions INTEGER NOT NULL,
                schedule_days VARCHAR(120),
                schedule_time VARCHAR(10),
                status VARCHAR(30) NOT NULL
            )
        """)
        cursor.execute("""
            INSERT INTO pt_enrollments_new
            SELECT id, customer_id, coach_id, group_type, starts_at, expires_at,
                   total_sessions, remaining_sessions, schedule_days, schedule_time, status
            FROM pt_enrollments
        """)
        cursor.execute("DROP TABLE pt_enrollments")
        cursor.execute("ALTER TABLE pt_enrollments_new RENAME TO pt_enrollments")
        cursor.execute("CREATE INDEX ix_pt_enrollments_customer_id ON pt_enrollments (customer_id)")
        cursor.execute("CREATE INDEX ix_pt_enrollments_group_type ON pt_enrollments (group_type)")
        cursor.execute("CREATE INDEX ix_pt_enrollments_status ON pt_enrollments (status)")
        raw.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
    except Exception:
        raw.rollback()
        raise
    finally:
        raw.close()
