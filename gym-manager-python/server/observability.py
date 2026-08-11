from collections import Counter
from datetime import datetime, timezone
import json
import logging
import sys
from threading import Lock

from .config import settings


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in (
            "request_id", "method", "path", "status", "duration_ms",
            "client_ip", "event", "user_id",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    logger = logging.getLogger("pulsefit")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(getattr(logging, settings.log_level, logging.INFO))
    logger.propagate = False


configure_logging()
logger = logging.getLogger("pulsefit")


class MetricsRegistry:
    buckets = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0)

    def __init__(self):
        self._lock = Lock()
        self._requests = Counter()
        self._duration_buckets = Counter()
        self._duration_sum = Counter()
        self._in_flight = 0

    def begin(self):
        with self._lock:
            self._in_flight += 1

    def finish(self, method: str, route: str, status: int, duration: float):
        status_class = f"{status // 100}xx"
        key = (method, route, status_class)
        with self._lock:
            self._in_flight = max(self._in_flight - 1, 0)
            self._requests[key] += 1
            self._duration_sum[(method, route)] += duration
            for bucket in self.buckets:
                if duration <= bucket:
                    self._duration_buckets[(method, route, bucket)] += 1
            self._duration_buckets[(method, route, float("inf"))] += 1

    @staticmethod
    def _label(value: str) -> str:
        return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")

    def render(self) -> str:
        lines = [
            "# HELP pulsefit_http_requests_total Total HTTP requests.",
            "# TYPE pulsefit_http_requests_total counter",
        ]
        with self._lock:
            for (method, route, status_class), value in sorted(self._requests.items()):
                labels = f'method="{method}",route="{self._label(route)}",status_class="{status_class}"'
                lines.append(f"pulsefit_http_requests_total{{{labels}}} {value}")
            lines.extend([
                "# HELP pulsefit_http_request_duration_seconds HTTP request duration.",
                "# TYPE pulsefit_http_request_duration_seconds histogram",
            ])
            route_keys = sorted(self._duration_sum)
            for method, route in route_keys:
                labels = f'method="{method}",route="{self._label(route)}"'
                for bucket in (*self.buckets, float("inf")):
                    le = "+Inf" if bucket == float("inf") else str(bucket)
                    count = self._duration_buckets[(method, route, bucket)]
                    lines.append(f'pulsefit_http_request_duration_seconds_bucket{{{labels},le="{le}"}} {count}')
                count = self._duration_buckets[(method, route, float("inf"))]
                lines.append(f"pulsefit_http_request_duration_seconds_sum{{{labels}}} {self._duration_sum[(method, route)]:.6f}")
                lines.append(f"pulsefit_http_request_duration_seconds_count{{{labels}}} {count}")
            lines.extend([
                "# HELP pulsefit_http_requests_in_flight Current in-flight HTTP requests.",
                "# TYPE pulsefit_http_requests_in_flight gauge",
                f"pulsefit_http_requests_in_flight {self._in_flight}",
            ])
        return "\n".join(lines) + "\n"


metrics = MetricsRegistry()


def configure_open_telemetry(app, engine) -> bool:
    """Enable OTLP tracing only when an exporter endpoint is configured."""
    if not settings.otel_exporter_endpoint:
        logger.info("otel_export_disabled", extra={"event": "otel_configuration"})
        return False
    from opentelemetry import trace
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor

    provider = TracerProvider(resource=Resource.create({
        "service.name": settings.otel_service_name,
        "deployment.environment.name": settings.environment,
    }))
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    FastAPIInstrumentor.instrument_app(
        app,
        excluded_urls="/api/health,/api/health/live,/api/health/ready,/api/metrics",
    )
    SQLAlchemyInstrumentor().instrument(engine=engine)
    logger.info("otel_export_enabled", extra={"event": "otel_configuration"})
    return True
