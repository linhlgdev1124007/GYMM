from pathlib import Path
import os

from sqlalchemy import create_engine, event, inspect
from sqlalchemy.schema import CreateTable
from sqlalchemy.engine import URL
from sqlalchemy.orm import DeclarativeBase, sessionmaker

ROOT_DIR = Path(__file__).resolve().parent.parent
DATABASE_PATH = Path(os.getenv("GYM_DATABASE_PATH", ROOT_DIR / "gym.sqlite3"))


def database_url():
    explicit_url = os.getenv("GYM_DATABASE_URL", "").strip()
    if explicit_url:
        return explicit_url
    # The path setting remains available only so the isolated backend test suite
    # can use a temporary SQLite database without requiring MySQL.
    if os.getenv("GYM_DATABASE_PATH"):
        return f"sqlite:///{DATABASE_PATH}"
    return URL.create(
        drivername="mysql+pymysql",
        username=os.getenv("GYM_DB_USER", "root"),
        password=os.getenv("GYM_DB_PASSWORD", ""),
        host=os.getenv("GYM_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("GYM_DB_PORT", "3306")),
        database=os.getenv("GYM_DB_NAME", "pulsefit_gym"),
        query={"charset": "utf8mb4"},
    )


DATABASE_URL = database_url()
IS_SQLITE = str(DATABASE_URL).startswith("sqlite")
engine_options = {"pool_pre_ping": True}
if IS_SQLITE:
    engine_options["connect_args"] = {"check_same_thread": False}
else:
    engine_options.update({"pool_recycle": 1800})
engine = create_engine(DATABASE_URL, **engine_options)


@event.listens_for(engine, "connect")
def enable_sqlite_foreign_keys(dbapi_connection, _connection_record):
    if not IS_SQLITE:
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


LEGACY_BRANCH_TABLES = ("customers", "employees", "devices", "cash_shifts")


def migrate_remove_branches():
    """Remove the retired multi-location schema without deleting business rows."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    affected = [
        table for table in LEGACY_BRANCH_TABLES
        if table in tables and "branch_id" in {
            column["name"] for column in inspector.get_columns(table)
        }
    ]
    if not affected and "branches" not in tables:
        return

    if IS_SQLITE:
        raw = engine.raw_connection()
        try:
            cursor = raw.cursor()
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute("BEGIN")
            for table in affected:
                replacement = f"{table}__without_branches"
                model_table = Base.metadata.tables[table]
                ddl = str(CreateTable(model_table).compile(dialect=engine.dialect))
                ddl = ddl.replace(
                    f"CREATE TABLE {table}",
                    f'CREATE TABLE "{replacement}"',
                    1,
                )
                cursor.execute(f'DROP TABLE IF EXISTS "{replacement}"')
                cursor.execute(ddl)
                columns = [column.name for column in model_table.columns]
                column_list = ", ".join(f'"{column}"' for column in columns)
                cursor.execute(
                    f'INSERT INTO "{replacement}" ({column_list}) '
                    f'SELECT {column_list} FROM "{table}"'
                )
                cursor.execute(f'DROP TABLE "{table}"')
                cursor.execute(
                    f'ALTER TABLE "{replacement}" RENAME TO "{table}"'
                )
            if "branches" in tables:
                cursor.execute('DROP TABLE "branches"')
            raw.commit()
            cursor.execute("PRAGMA foreign_keys=ON")
        except Exception:
            raw.rollback()
            raise
        finally:
            raw.close()
        return

    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        connection_inspector = inspect(connection)
        for table in affected:
            for foreign_key in connection_inspector.get_foreign_keys(table):
                if "branch_id" in foreign_key.get("constrained_columns", []):
                    connection.exec_driver_sql(
                        f"ALTER TABLE {quote(table)} DROP FOREIGN KEY {quote(foreign_key['name'])}"
                    )
            connection.exec_driver_sql(
                f"ALTER TABLE {quote(table)} DROP COLUMN {quote('branch_id')}"
            )
        if "branches" in tables:
            connection.exec_driver_sql(f"DROP TABLE {quote('branches')}")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def migrate_pt_coaches():
    """Make the legacy coach optional before the assignment table is created."""
    if not IS_SQLITE:
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


def migrate_pt_schedule():
    """Add per-weekday PT times while retaining old schedule columns for compatibility."""
    inspector = inspect(engine)
    if "pt_enrollments" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("pt_enrollments")}
    if "schedule_json" in columns:
        return
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"ALTER TABLE {quote('pt_enrollments')} ADD COLUMN {quote('schedule_json')} TEXT"
        )
