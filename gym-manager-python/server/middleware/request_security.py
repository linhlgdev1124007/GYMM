from collections import defaultdict, deque
import hmac
import re
import secrets
from threading import Lock
import time
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..config import settings


SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_COOKIE = "gym_csrf"
CSRF_HEADER = "x-csrf-token"
REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9._:-]{8,128}$")
TOKEN_AUTH_PATH_PREFIXES = ("/api/dah/local-agent/",)


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)


def set_csrf_cookie(response, token: str) -> None:
    response.set_cookie(
        CSRF_COOKIE,
        token,
        httponly=False,
        secure=settings.secure_cookies,
        samesite="strict",
        max_age=settings.session_days * 86400,
        path="/",
    )


def request_client_ip(request: Request) -> str:
    if settings.trust_proxy_headers:
        forwarded = request.headers.get("x-forwarded-for", "").split(",", 1)[0].strip()
        if forwarded:
            return forwarded[:64]
    return (request.client.host if request.client else "unknown")[:64]


class RequestSizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int):
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        try:
            content_length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            content_length = 0
        if content_length > self.max_bytes:
            response = JSONResponse(
                status_code=413,
                content={"detail": "Yêu cầu vượt quá kích thước cho phép."},
            )
            await response(scope, receive, send)
            return
        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    return {"type": "http.disconnect"}
            return message

        await self.app(scope, limited_receive, send)


class SlidingWindowLimiter:
    def __init__(self):
        self._events = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, limit: int, window: int) -> tuple[bool, int]:
        now = time.monotonic()
        cutoff = now - window
        with self._lock:
            events = self._events[key]
            while events and events[0] <= cutoff:
                events.popleft()
            if len(events) >= limit:
                retry_after = max(int(window - (now - events[0])) + 1, 1)
                return False, retry_after
            events.append(now)
            if len(self._events) > 10_000:
                stale = [item for item, values in self._events.items() if not values or values[-1] <= cutoff]
                for item in stale[:1000]:
                    self._events.pop(item, None)
            return True, 0


rate_limiter = SlidingWindowLimiter()


def _source_origin(request: Request) -> str | None:
    value = request.headers.get("origin")
    if not value:
        referer = request.headers.get("referer")
        if referer:
            parsed = urlsplit(referer)
            value = f"{parsed.scheme}://{parsed.netloc}"
    return value.rstrip("/") if value else None


class RequestSecurityMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope, receive=receive)
        path = request.url.path
        if not path.startswith("/api/"):
            await self.app(scope, receive, send)
            return
        client_ip = request_client_ip(request)
        scope.setdefault("state", {})["client_ip"] = client_ip

        if path == "/api/auth/login":
            allowed, retry_after = rate_limiter.check(
                f"login:{client_ip}", settings.login_rate_limit, settings.login_rate_window_seconds,
            )
        else:
            allowed, retry_after = rate_limiter.check(
                f"api:{client_ip}", settings.api_rate_limit, settings.api_rate_window_seconds,
            )
        if not allowed:
            response = JSONResponse(
                status_code=429,
                content={"detail": "Quá nhiều yêu cầu. Vui lòng thử lại sau."},
                headers={"Retry-After": str(retry_after)},
            )
            await response(scope, receive, send)
            return

        token_authenticated_path = any(path.startswith(prefix) for prefix in TOKEN_AUTH_PATH_PREFIXES)
        if request.method not in SAFE_METHODS and not token_authenticated_path:
            origin = _source_origin(request)
            if not origin or origin not in settings.allowed_origins:
                response = JSONResponse(
                    status_code=403,
                    content={"detail": "Nguồn gửi yêu cầu không được phép."},
                )
                await response(scope, receive, send)
                return
            if path != "/api/auth/login" and request.cookies.get("gym_session"):
                cookie_token = request.cookies.get(CSRF_COOKIE, "")
                header_token = request.headers.get(CSRF_HEADER, "")
                if not cookie_token or not header_token or not hmac.compare_digest(cookie_token, header_token):
                    response = JSONResponse(
                        status_code=403,
                        content={"detail": "Phiên bảo vệ đã hết hạn. Vui lòng tải lại trang và thử lại."},
                    )
                    await response(scope, receive, send)
                    return
        await self.app(scope, receive, send)
