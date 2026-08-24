from pathlib import Path
import contextlib
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


def migrate_mbs_card_code_not_unique():
    """Allow reused MBS/card labels such as shared placeholder card names."""
    inspector = inspect(engine)
    if "customers" not in inspector.get_table_names():
        return

    indexes = inspector.get_indexes("customers")
    unique_indexes = [
        index for index in indexes
        if index.get("unique") and index.get("column_names") == ["mbs_card_code"]
    ]
    if not unique_indexes:
        return

    if IS_SQLITE:
        droppable_indexes = [
            index for index in unique_indexes
            if not str(index.get("name", "")).startswith("sqlite_autoindex_")
        ]
        with engine.begin() as connection:
            quote = engine.dialect.identifier_preparer.quote
            for index in droppable_indexes:
                connection.exec_driver_sql(f"DROP INDEX {quote(index['name'])}")
        return

    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        for index in unique_indexes:
            connection.exec_driver_sql(
                f"ALTER TABLE {quote('customers')} DROP INDEX {quote(index['name'])}"
            )


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


def migrate_pt_finance():
    """Add isolated PT finance fields and installment debt tracking."""
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    quote = engine.dialect.identifier_preparer.quote
    if "pt_enrollments" in tables:
        columns = {column["name"] for column in inspector.get_columns("pt_enrollments")}
        definitions = {
            "package_name": "VARCHAR(160)",
            "final_price": "FLOAT NOT NULL DEFAULT 0",
            "paid_amount": "FLOAT NOT NULL DEFAULT 0",
            "debt_amount": "FLOAT NOT NULL DEFAULT 0",
        }
        with engine.begin() as connection:
            for column, definition in definitions.items():
                if column not in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {quote('pt_enrollments')} ADD COLUMN {quote(column)} {definition}"
                    )
    if "payments" in tables:
        columns = {column["name"] for column in inspector.get_columns("payments")}
        with engine.begin() as connection:
            if "pt_enrollment_id" not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote('payments')} ADD COLUMN {quote('pt_enrollment_id')} INTEGER"
                )
                connection.exec_driver_sql(
                    f"CREATE INDEX {quote('ix_payments_pt_enrollment_id')} ON {quote('payments')} ({quote('pt_enrollment_id')})"
                )
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "pt_debt_installments" not in tables:
        id_definition = "INTEGER NOT NULL PRIMARY KEY" if IS_SQLITE else "INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY"
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"""
                CREATE TABLE {quote('pt_debt_installments')} (
                    {quote('id')} {id_definition},
                    {quote('enrollment_id')} INTEGER NOT NULL,
                    {quote('amount')} FLOAT NOT NULL DEFAULT 0,
                    {quote('due_date')} DATE NOT NULL,
                    {quote('paid_amount')} FLOAT NOT NULL DEFAULT 0,
                    {quote('status')} VARCHAR(30) NOT NULL DEFAULT 'pending',
                    {quote('note')} VARCHAR(255) NULL,
                    {quote('created_at')} DATETIME NOT NULL
                )
                """
            )
            for column in ("enrollment_id", "due_date", "status"):
                connection.exec_driver_sql(
                    f"CREATE INDEX {quote(f'ix_pt_debt_installments_{column}')} "
                    f"ON {quote('pt_debt_installments')} ({quote(column)})"
                )


def migrate_dah_integration():
    """Add DAH customer identity fields to existing databases."""
    inspector = inspect(engine)
    if "customers" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("customers")}
    quote = engine.dialect.identifier_preparer.quote
    text_type = "TEXT" if IS_SQLITE else "LONGTEXT"
    with engine.begin() as connection:
        if "person_uuid" not in columns:
            connection.exec_driver_sql(
                f"ALTER TABLE {quote('customers')} ADD COLUMN {quote('person_uuid')} VARCHAR(80)"
            )
        if "avatar_image_data" not in columns:
            connection.exec_driver_sql(
                f"ALTER TABLE {quote('customers')} ADD COLUMN {quote('avatar_image_data')} {text_type}"
            )
        indexes = {index["name"] for index in inspector.get_indexes("customers")}
        if "ix_customers_person_uuid" not in indexes:
            connection.exec_driver_sql(
                f"CREATE UNIQUE INDEX {quote('ix_customers_person_uuid')} ON {quote('customers')} ({quote('person_uuid')})"
            )
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "dah_customer_identities" in tables:
        columns = {column["name"] for column in inspector.get_columns("dah_customer_identities")}
        indexes = {index["name"] for index in inspector.get_indexes("dah_customer_identities")}
        with engine.begin() as connection:
            if "person_id" not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote('dah_customer_identities')} ADD COLUMN {quote('person_id')} VARCHAR(80)"
                )
            if "ix_dah_customer_identities_person_id" not in indexes:
                connection.exec_driver_sql(
                    f"CREATE INDEX {quote('ix_dah_customer_identities_person_id')} ON {quote('dah_customer_identities')} ({quote('person_id')})"
                )
            if "employee_id" not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote('dah_customer_identities')} ADD COLUMN {quote('employee_id')} INTEGER"
                )
                connection.exec_driver_sql(
                    f"CREATE INDEX {quote('ix_dah_customer_identities_employee_id')} ON {quote('dah_customer_identities')} ({quote('employee_id')})"
                )
            if not IS_SQLITE:
                customer_column = next(
                    column for column in inspector.get_columns("dah_customer_identities")
                    if column["name"] == "customer_id"
                )
                if not customer_column["nullable"]:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {quote('dah_customer_identities')} MODIFY COLUMN {quote('customer_id')} INTEGER NULL"
                    )
    if "dah_webhook_events" in tables:
        columns = {column["name"] for column in inspector.get_columns("dah_webhook_events")}
        indexes = {index["name"] for index in inspector.get_indexes("dah_webhook_events")}
        with engine.begin() as connection:
            if "person_id" not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote('dah_webhook_events')} ADD COLUMN {quote('person_id')} VARCHAR(80)"
                )
            if "ix_dah_webhook_events_person_id" not in indexes:
                connection.exec_driver_sql(
                    f"CREATE INDEX {quote('ix_dah_webhook_events_person_id')} ON {quote('dah_webhook_events')} ({quote('person_id')})"
                )
            if "person_uuid" not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote('dah_webhook_events')} ADD COLUMN {quote('person_uuid')} VARCHAR(80)"
                )
            if "ix_dah_webhook_events_person_uuid" not in indexes:
                connection.exec_driver_sql(
                    f"CREATE INDEX {quote('ix_dah_webhook_events_person_uuid')} ON {quote('dah_webhook_events')} ({quote('person_uuid')})"
                )
            if "employee_id" not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote('dah_webhook_events')} ADD COLUMN {quote('employee_id')} INTEGER"
                )
                connection.exec_driver_sql(
                    f"CREATE INDEX {quote('ix_dah_webhook_events_employee_id')} ON {quote('dah_webhook_events')} ({quote('employee_id')})"
                )


def migrate_membership_activation():
    inspector = inspect(engine)
    if "memberships" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("memberships")}
    if "activated_at" in columns:
        return
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"ALTER TABLE {quote('memberships')} ADD COLUMN {quote('activated_at')} DATE"
        )


def migrate_membership_pricing_adjustments():
    inspector = inspect(engine)
    if "memberships" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("memberships")}
    quote = engine.dialect.identifier_preparer.quote
    definitions = {
        "base_price": "FLOAT NOT NULL DEFAULT 0",
        "discount_type": "VARCHAR(20) NOT NULL DEFAULT 'none'",
        "discount_value": "FLOAT NOT NULL DEFAULT 0",
        "discount_amount": "FLOAT NOT NULL DEFAULT 0",
        "surcharge_amount": "FLOAT NOT NULL DEFAULT 0",
        "pricing_note": "VARCHAR(255) NULL",
    }
    added_base_price = False
    with engine.begin() as connection:
        for column, definition in definitions.items():
            if column not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote('memberships')} ADD COLUMN {quote(column)} {definition}"
                )
                if column == "base_price":
                    added_base_price = True
        if added_base_price:
            connection.exec_driver_sql(
                f"UPDATE {quote('memberships')} "
                f"SET {quote('base_price')} = COALESCE({quote('final_price')}, 0)"
            )


def migrate_membership_freeze_completion():
    inspector = inspect(engine)
    if "membership_freezes" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("membership_freezes")}
    if "completed_at" in columns:
        return
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"ALTER TABLE {quote('membership_freezes')} ADD COLUMN {quote('completed_at')} DATE"
        )
        connection.exec_driver_sql(
            f"UPDATE {quote('membership_freezes')} "
            f"SET {quote('completed_at')} = {quote('ends_at')} "
            f"WHERE {quote('compensated_days')} > 0"
        )


def migrate_employee_shift_attendance():
    inspector = inspect(engine)
    if "attendance_sessions" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("attendance_sessions")}
    quote = engine.dialect.identifier_preparer.quote
    with engine.begin() as connection:
        if "employee_shift_schedule_id" not in columns:
            connection.exec_driver_sql(
                f"ALTER TABLE {quote('attendance_sessions')} ADD COLUMN {quote('employee_shift_schedule_id')} INTEGER"
            )
            connection.exec_driver_sql(
                f"CREATE INDEX {quote('ix_attendance_sessions_employee_shift_schedule_id')} "
                f"ON {quote('attendance_sessions')} ({quote('employee_shift_schedule_id')})"
            )
        if "scheduled_start_at" not in columns:
            connection.exec_driver_sql(
                f"ALTER TABLE {quote('attendance_sessions')} ADD COLUMN {quote('scheduled_start_at')} DATETIME"
            )
        if "scheduled_end_at" not in columns:
            connection.exec_driver_sql(
                f"ALTER TABLE {quote('attendance_sessions')} ADD COLUMN {quote('scheduled_end_at')} DATETIME"
            )


def migrate_employee_shift_overrides():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    if "employee_shift_overrides" in tables:
        return
    quote = engine.dialect.identifier_preparer.quote
    id_definition = "INTEGER NOT NULL PRIMARY KEY" if IS_SQLITE else "INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY"
    with engine.begin() as connection:
        connection.exec_driver_sql(
            f"""
            CREATE TABLE {quote('employee_shift_overrides')} (
                {quote('id')} {id_definition},
                {quote('employee_id')} INTEGER NOT NULL,
                {quote('original_shift_schedule_id')} INTEGER NULL,
                {quote('work_date')} DATE NOT NULL,
                {quote('original_start_at')} DATETIME NULL,
                {quote('original_end_at')} DATETIME NULL,
                {quote('approved_start_at')} DATETIME NOT NULL,
                {quote('approved_end_at')} DATETIME NOT NULL,
                {quote('status')} VARCHAR(30) NOT NULL DEFAULT 'approved',
                {quote('reason')} VARCHAR(255) NULL,
                {quote('requested_by_user_id')} INTEGER NULL,
                {quote('approved_by_user_id')} INTEGER NULL,
                {quote('approved_at')} DATETIME NULL,
                {quote('created_at')} DATETIME NOT NULL,
                {quote('updated_at')} DATETIME NOT NULL
            )
            """
        )
        for column in ("employee_id", "original_shift_schedule_id", "work_date", "approved_start_at", "approved_end_at", "status"):
            connection.exec_driver_sql(
                f"CREATE INDEX {quote(f'ix_employee_shift_overrides_{column}')} "
                f"ON {quote('employee_shift_overrides')} ({quote(column)})"
            )


def migrate_checkin_speech_config():
    inspector = inspect(engine)
    if "checkin_speech_configs" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("checkin_speech_configs")}
    quote = engine.dialect.identifier_preparer.quote
    definitions = {
        "voice_uri": "VARCHAR(300) NULL",
        "voice_name": "VARCHAR(200) NULL",
        "volume": "FLOAT NOT NULL DEFAULT 1",
        "rate": "FLOAT NOT NULL DEFAULT 1",
        "pitch": "FLOAT NOT NULL DEFAULT 1",
    }
    with engine.begin() as connection:
        for column, definition in definitions.items():
            if column not in columns:
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote('checkin_speech_configs')} ADD COLUMN {quote(column)} {definition}"
                )


def migrate_checkin_speech_event_reference():
    inspector = inspect(engine)
    table = "checkin_speech_events"
    if table not in inspector.get_table_names():
        return
    columns = {column["name"]: column for column in inspector.get_columns(table)}
    foreign_keys = inspector.get_foreign_keys(table)
    attendance_fk = next(
        (foreign_key for foreign_key in foreign_keys if foreign_key.get("constrained_columns") == ["attendance_session_id"]),
        None,
    )
    on_delete = str((attendance_fk or {}).get("options", {}).get("ondelete") or "").upper()
    if columns.get("attendance_session_id", {}).get("nullable") and on_delete == "SET NULL":
        return

    quote = engine.dialect.identifier_preparer.quote
    if not IS_SQLITE:
        with engine.begin() as connection:
            if attendance_fk and attendance_fk.get("name"):
                connection.exec_driver_sql(
                    f"ALTER TABLE {quote(table)} DROP FOREIGN KEY {quote(attendance_fk['name'])}"
                )
            connection.exec_driver_sql(
                f"ALTER TABLE {quote(table)} MODIFY COLUMN {quote('attendance_session_id')} INTEGER NULL"
            )
            connection.exec_driver_sql(
                f"ALTER TABLE {quote(table)} ADD CONSTRAINT {quote('fk_checkin_speech_events_attendance_session_id')} "
                f"FOREIGN KEY ({quote('attendance_session_id')}) REFERENCES {quote('attendance_sessions')} ({quote('id')}) ON DELETE SET NULL"
            )
        return

    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("BEGIN")
        cursor.execute("DROP TABLE IF EXISTS checkin_speech_events__new")
        cursor.execute(
            """
            CREATE TABLE checkin_speech_events__new (
                id INTEGER NOT NULL PRIMARY KEY,
                attendance_session_id INTEGER NULL UNIQUE,
                person_type VARCHAR(20) NOT NULL,
                person_name VARCHAR(180) NOT NULL,
                message VARCHAR(700) NOT NULL,
                created_at DATETIME NOT NULL,
                FOREIGN KEY(attendance_session_id) REFERENCES attendance_sessions(id) ON DELETE SET NULL
            )
            """
        )
        cursor.execute(
            "INSERT INTO checkin_speech_events__new "
            "(id, attendance_session_id, person_type, person_name, message, created_at) "
            "SELECT id, attendance_session_id, person_type, person_name, message, created_at FROM checkin_speech_events"
        )
        cursor.execute("DROP TABLE checkin_speech_events")
        cursor.execute("ALTER TABLE checkin_speech_events__new RENAME TO checkin_speech_events")
        cursor.execute("CREATE INDEX ix_checkin_speech_events_attendance_session_id ON checkin_speech_events (attendance_session_id)")
        cursor.execute("CREATE INDEX ix_checkin_speech_events_person_type ON checkin_speech_events (person_type)")
        cursor.execute("CREATE INDEX ix_checkin_speech_events_created_at ON checkin_speech_events (created_at)")
        raw.commit()
        cursor.execute("PRAGMA foreign_keys=ON")
    except Exception:
        raw.rollback()
        with contextlib.suppress(Exception):
            raw.cursor().execute("PRAGMA foreign_keys=ON")
        raise
    finally:
        raw.close()


def migrate_member_processing():
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    quote = engine.dialect.identifier_preparer.quote
    if "attendance_sessions" in tables:
        columns = {column["name"] for column in inspector.get_columns("attendance_sessions")}
        definitions = {
            "workout_type": "VARCHAR(30)",
            "pt_enrollment_id": "INTEGER",
            "processed_at": "DATETIME",
            "processed_by_user_id": "INTEGER",
        }
        with engine.begin() as connection:
            for column, definition in definitions.items():
                if column not in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {quote('attendance_sessions')} ADD COLUMN {quote(column)} {definition}"
                    )
                    if column in {"workout_type", "pt_enrollment_id", "processed_at"}:
                        connection.exec_driver_sql(
                            f"CREATE INDEX {quote(f'ix_attendance_sessions_{column}')} "
                            f"ON {quote('attendance_sessions')} ({quote(column)})"
                        )
    if "pt_session_logs" not in tables:
        id_definition = "INTEGER NOT NULL PRIMARY KEY" if IS_SQLITE else "INTEGER NOT NULL AUTO_INCREMENT PRIMARY KEY"
        with engine.begin() as connection:
            connection.exec_driver_sql(
                f"""
                CREATE TABLE {quote('pt_session_logs')} (
                    {quote('id')} {id_definition},
                    {quote('enrollment_id')} INTEGER NOT NULL,
                    {quote('attendance_session_id')} INTEGER NULL,
                    {quote('action')} VARCHAR(40) NOT NULL,
                    {quote('delta_sessions')} INTEGER NOT NULL DEFAULT 0,
                    {quote('remaining_before')} INTEGER NOT NULL,
                    {quote('remaining_after')} INTEGER NOT NULL,
                    {quote('training_date')} DATE NULL,
                    {quote('started_at')} DATETIME NULL,
                    {quote('ended_at')} DATETIME NULL,
                    {quote('note')} VARCHAR(255) NULL,
                    {quote('created_by_user_id')} INTEGER NULL,
                    {quote('created_at')} DATETIME NOT NULL
                )
                """
            )
            for column in ("enrollment_id", "attendance_session_id", "action", "training_date", "created_at"):
                connection.exec_driver_sql(
                    f"CREATE INDEX {quote(f'ix_pt_session_logs_{column}')} "
                    f"ON {quote('pt_session_logs')} ({quote(column)})"
                )
    else:
        columns = {column["name"] for column in inspector.get_columns("pt_session_logs")}
        definitions = {
            "training_date": "DATE",
            "started_at": "DATETIME",
            "ended_at": "DATETIME",
        }
        with engine.begin() as connection:
            for column, definition in definitions.items():
                if column not in columns:
                    connection.exec_driver_sql(
                        f"ALTER TABLE {quote('pt_session_logs')} ADD COLUMN {quote(column)} {definition}"
                    )
                    if column == "training_date":
                        connection.exec_driver_sql(
                            f"CREATE INDEX {quote('ix_pt_session_logs_training_date')} "
                            f"ON {quote('pt_session_logs')} ({quote(column)})"
                        )
