from pathlib import Path
import os

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware

from .database import Base, ROOT_DIR, SessionLocal, engine
from .routes import auth, insights, members, operations
from .security import ensure_admin_user
from .middleware.security_headers import SecurityHeadersMiddleware

app = FastAPI(title="PulseFit Gym Management API", version="2.0.0", docs_url="/api/docs", openapi_url="/api/openapi.json")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(SecurityHeadersMiddleware)


@app.on_event("startup")
def startup():
    if os.getenv("VERCEL"):
        return
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        ensure_admin_user(db)
    finally:
        db.close()


@app.exception_handler(RequestValidationError)
async def validation_error(_request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": "Dữ liệu gửi lên chưa hợp lệ.", "fields": exc.errors()})


@app.get("/api/health", tags=["system"])
def health():
    return {"status": "ok"}


app.include_router(auth.router)
app.include_router(insights.router)
app.include_router(members.router)
app.include_router(operations.router)

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
