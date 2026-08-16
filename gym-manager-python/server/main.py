from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
import asyncio
import contextlib
import hmac
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import or_, text

from .config import settings
from .database import Base, IS_SQLITE, ROOT_DIR, SessionLocal, engine, migrate_dah_integration, migrate_employee_shift_attendance, migrate_employee_shift_overrides, migrate_mbs_card_code_not_unique, migrate_membership_activation, migrate_membership_freeze_completion, migrate_pt_coaches, migrate_pt_schedule, migrate_remove_branches
from .models import (
    AuthSession, Device, Payment, PaymentReceipt, PtEnrollment, PtEnrollmentCoach,
)
from .observability import configure_open_telemetry, metrics
from .routes import audit, auth, dah, insights, inventory, members, operations, users
from .security import ensure_admin_user
from .services.attendance_auto_checkout import auto_checkout_open_sessions, AUTO_CHECKOUT_TIME, next_auto_checkout_run
from .services.operations_service import ensure_employee_job_titles
from .services.dah_service import DAH_MODEL, HEARTBEAT_TIMEOUT_SECONDS, cleanup_webhook_images
from .services.members_service import normalize_cancelled_members
from .services.membership_lifecycle import refresh_membership_lifecycle
from .timeutils import VIETNAM_TZ, utc_iso, utc_now
from .middleware.observability import ObservabilityMiddleware
from .middleware.request_security import RequestSecurityMiddleware, RequestSizeLimitMiddleware
from .middleware.security_headers import SecurityHeadersMiddleware

def initialize_database():
    migrate_pt_coaches()
    migrate_remove_branches()
    migrate_mbs_card_code_not_unique()
    migrate_pt_schedule()
    migrate_dah_integration()
    migrate_membership_activation()
    migrate_membership_freeze_completion()
    migrate_employee_shift_attendance()
    migrate_employee_shift_overrides()
    if IS_SQLITE:
        with engine.connect() as connection:
            user_columns = {
                column["name"]
                for column in connection.exec_driver_sql("PRAGMA table_info(users)").mappings()
            }
        # Keep compatibility with the legacy local SQLite database. MySQL starts
        # from the current schema and future schema changes should use migrations.
        if user_columns and "employee_id" not in user_columns:
            with engine.begin() as connection:
                connection.exec_driver_sql(
                    "ALTER TABLE users ADD COLUMN employee_id INTEGER REFERENCES employees(id)"
                )
                connection.exec_driver_sql(
                    "CREATE UNIQUE INDEX IF NOT EXISTS ix_users_employee_id ON users(employee_id)"
                )
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        assigned_enrollments = {
            enrollment_id for (enrollment_id,) in db.query(PtEnrollmentCoach.enrollment_id).distinct()
        }
        for enrollment in db.query(PtEnrollment).filter(PtEnrollment.coach_id.is_not(None)):
            if enrollment.id not in assigned_enrollments:
                db.add(PtEnrollmentCoach(enrollment_id=enrollment.id, coach_id=enrollment.coach_id))
        receipt_payment_ids = {
            payment_id for (payment_id,) in db.query(PaymentReceipt.payment_id).distinct()
        }
        for payment in db.query(Payment).filter(Payment.receipt_image_path.is_not(None)):
            if payment.id not in receipt_payment_ids:
                db.add(PaymentReceipt(
                    payment_id=payment.id,
                    file_path=payment.receipt_image_path,
                    original_name="Chứng từ cũ",
                    uploaded_at=payment.paid_at,
                ))
        now = utc_now()
        db.query(AuthSession).filter(AuthSession.expires_at <= now).delete(synchronize_session=False)
        ensure_employee_job_titles(db)
        refresh_membership_lifecycle(db)
        normalize_cancelled_members(db)
        auto_checkout_open_sessions(db)
        db.commit()
        ensure_admin_user(db)
    finally:
        db.close()


async def webhook_image_cleanup_job():
    while True:
        db = SessionLocal()
        try:
            cleanup_webhook_images(db)
            refresh_membership_lifecycle(db)
        finally:
            db.close()
        interval = 24 * 60 * 60
        if settings.environment == "test":
            try:
                interval = max(float(os.getenv("GYM_TEST_JOB_INTERVAL_SECONDS", "1")), 0.1)
            except (TypeError, ValueError):
                interval = 1
        await asyncio.sleep(interval)


def _seconds_until_auto_checkout() -> float:
    now = datetime.now(VIETNAM_TZ)
    target = datetime.combine(now.date(), AUTO_CHECKOUT_TIME, tzinfo=VIETNAM_TZ)
    if now >= target:
        target += timedelta(days=1)
    return max((target - now).total_seconds(), 1)


async def attendance_auto_checkout_job():
    while True:
        interval = _seconds_until_auto_checkout()
        if settings.environment == "test":
            try:
                interval = max(float(os.getenv("GYM_TEST_JOB_INTERVAL_SECONDS", "1")), 0.1)
            except (TypeError, ValueError):
                interval = 1
        await asyncio.sleep(interval)
        db = SessionLocal()
        try:
            auto_checkout_open_sessions(db)
        finally:
            db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    cleanup_task = asyncio.create_task(webhook_image_cleanup_job())
    auto_checkout_task = asyncio.create_task(attendance_auto_checkout_job())
    try:
        yield
    finally:
        cleanup_task.cancel()
        auto_checkout_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await cleanup_task
        with contextlib.suppress(asyncio.CancelledError):
            await auto_checkout_task


app = FastAPI(
    title="PulseFit Gym Management API",
    version="2.0.0",
    docs_url=None if settings.production else "/api/docs",
    openapi_url=None if settings.production else "/api/openapi.json",
    lifespan=lifespan,
)
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(RequestSizeLimitMiddleware, max_bytes=settings.max_request_bytes)
app.add_middleware(RequestSecurityMiddleware)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=list(settings.allowed_hosts))
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(ObservabilityMiddleware)
configure_open_telemetry(app, engine)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={
        "detail": "Dữ liệu gửi lên chưa hợp lệ.",
        "fields": exc.errors(),
        "requestId": getattr(request.state, "request_id", None),
    })


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException):
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.detail, "requestId": getattr(request.state, "request_id", None)},
        headers=exc.headers,
    )


@app.get("/api/health", tags=["system"])
def health():
    server_time = datetime.now(VIETNAM_TZ)
    result = {
        "status": "ready",
        "database": "ok",
        "dah1017": "unknown",
        "serverTime": server_time.isoformat(),
        "timezone": "Asia/Ho_Chi_Minh",
        "autoCheckout": {
            "time": AUTO_CHECKOUT_TIME.strftime("%H:%M"),
            "nextRunAt": next_auto_checkout_run(server_time).isoformat(),
        },
    }
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        result["status"] = "not_ready"
        result["database"] = "unavailable"
        result["dah1017"] = "unknown"
        return JSONResponse(status_code=503, content=result)

    db = SessionLocal()
    try:
        device = (
            db.query(Device)
            .filter(or_(Device.model == DAH_MODEL, Device.code.like("DAH-%"), Device.code == DAH_MODEL))
            .order_by(Device.last_heartbeat_at.desc(), Device.id.desc())
            .first()
        )
        online = bool(
            device and device.last_heartbeat_at and
            device.last_heartbeat_at >= utc_now() - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)
        )
        result["dah1017"] = "online" if online else "offline"
        result["lastHeartbeat"] = utc_iso(device.last_heartbeat_at) if device else None
        result["heartbeatTimeoutSeconds"] = HEARTBEAT_TIMEOUT_SECONDS
        if not online:
            result["status"] = "not_ready"
            return JSONResponse(status_code=503, content=result)
        return result
    finally:
        db.close()


@app.get("/api/health/live", tags=["system"])
def liveness():
    return {"status": "alive"}


@app.get("/api/health/ready", tags=["system"])
def readiness():
    return health()


@app.get("/api/metrics", include_in_schema=False)
def prometheus_metrics(request: Request):
    if settings.metrics_token:
        authorization = request.headers.get("authorization", "")
        expected = f"Bearer {settings.metrics_token}"
        if not hmac.compare_digest(authorization, expected):
            raise HTTPException(status_code=401, detail="Metrics authentication required")
    return PlainTextResponse(metrics.render(), media_type="text/plain; version=0.0.4")


app.include_router(auth.router)
app.include_router(dah.router)
app.include_router(insights.router)
app.include_router(inventory.router)
app.include_router(members.router)
app.include_router(operations.router)
app.include_router(audit.router)
app.include_router(users.router)
if settings.environment == "test":
    from .routes import testhooks
    app.include_router(testhooks.router)

UPLOAD_DIR = ROOT_DIR / "server" / "uploads"
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

DIST_DIR = ROOT_DIR / "client" / "dist"
ASSETS_DIR = DIST_DIR / "assets"
if ASSETS_DIR.exists():
    app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")


@app.api_route("/api/{api_path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"], include_in_schema=False)
def api_not_found(api_path: str):
    return JSONResponse(status_code=404, content={"detail": "API endpoint không tồn tại."})


@app.get("/{client_path:path}", include_in_schema=False)
def spa_fallback(client_path: str):
    index = DIST_DIR / "index.html"
    if index.exists():
        return FileResponse(index)
    return JSONResponse(status_code=503, content={"detail": "Frontend chưa được build. Chạy npm run dev hoặc npm run build."})
