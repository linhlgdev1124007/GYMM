from pathlib import Path
from contextlib import asynccontextmanager
import hmac

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text

from .config import settings
from .database import Base, IS_SQLITE, ROOT_DIR, SessionLocal, engine, migrate_pt_coaches, migrate_pt_schedule, migrate_remove_branches
from .models import (
    AuthSession, Payment, PaymentReceipt, PtEnrollment, PtEnrollmentCoach,
)
from .observability import configure_open_telemetry, metrics
from .routes import audit, auth, insights, members, operations, users
from .security import ensure_admin_user
from .services.operations_service import ensure_employee_job_titles
from .timeutils import utc_now
from .middleware.observability import ObservabilityMiddleware
from .middleware.request_security import RequestSecurityMiddleware, RequestSizeLimitMiddleware
from .middleware.security_headers import SecurityHeadersMiddleware

def initialize_database():
    migrate_pt_coaches()
    migrate_remove_branches()
    migrate_pt_schedule()
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
        db.commit()
        ensure_admin_user(db)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    initialize_database()
    yield


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
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        return {"status": "ready", "database": "ok"}
    except Exception:
        return JSONResponse(status_code=503, content={"status": "not_ready", "database": "unavailable"})


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
app.include_router(insights.router)
app.include_router(members.router)
app.include_router(operations.router)
app.include_router(audit.router)
app.include_router(users.router)

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
