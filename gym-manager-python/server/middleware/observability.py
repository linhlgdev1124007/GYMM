import time
import uuid

from fastapi import Request

from ..observability import logger, metrics
from .request_security import REQUEST_ID_PATTERN, request_client_ip


class ObservabilityMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request = Request(scope)
        incoming = request.headers.get("x-request-id", "")
        request_id = incoming if REQUEST_ID_PATTERN.fullmatch(incoming) else uuid.uuid4().hex
        scope.setdefault("state", {})["request_id"] = request_id
        scope["state"].setdefault("client_ip", request_client_ip(request))
        started = time.perf_counter()
        status_code = 500
        metrics.begin()

        async def send_with_headers(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, receive, send_with_headers)
        except Exception:
            logger.exception(
                "unhandled_request_error",
                extra={
                    "request_id": request_id,
                    "method": request.method,
                    "path": request.url.path,
                    "client_ip": scope["state"]["client_ip"],
                    "event": "http_request_error",
                },
            )
            raise
        finally:
            duration = time.perf_counter() - started
            route_object = scope.get("route")
            route = getattr(route_object, "path", "unmatched")
            if request.url.path.startswith("/api/"):
                metrics.finish(request.method, route, status_code, duration)
                logger.info(
                    "http_request",
                    extra={
                        "request_id": request_id,
                        "method": request.method,
                        "path": route,
                        "status": status_code,
                        "duration_ms": round(duration * 1000, 2),
                        "client_ip": scope["state"]["client_ip"],
                        "event": "http_request",
                    },
                )
