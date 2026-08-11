# PulseFit reliability and observability runbook

## Health endpoints

- `GET /api/health/live`: process liveness; does not query dependencies.
- `GET /api/health/ready`: readiness; returns `503` when the database cannot answer `SELECT 1`.
- `GET /api/health`: backward-compatible readiness alias.

Load balancers should restart only on failed liveness and remove an instance from traffic on failed readiness.

## Logs and request correlation

The API emits one JSON record per API request with UTC timestamp, request ID, normalized route, status class, duration and client IP. Clients may send a safe `X-Request-ID`; otherwise the server creates one and always returns it. UI error notifications show this value as `Mã hỗ trợ` so support can find the exact request without exposing stack traces.

Do not log request bodies, session cookies, CSRF tokens, passwords or receipt contents.

## Prometheus metrics

`GET /api/metrics` exposes:

- `pulsefit_http_requests_total`
- `pulsefit_http_request_duration_seconds`
- `pulsefit_http_requests_in_flight`

When `GYM_METRICS_TOKEN` is set, scrape with `Authorization: Bearer <token>`. Production configuration requires this token.

Recommended alerts:

- readiness failing for 2 consecutive minutes;
- 5xx ratio above 1% for 5 minutes;
- p95 latency above 500 ms for 10 minutes;
- sustained request saturation or abnormal 401/403/429 increases.

## OpenTelemetry

Set `OTEL_EXPORTER_OTLP_ENDPOINT` to enable automatic FastAPI and SQLAlchemy traces through the OTLP HTTP exporter. Standard OpenTelemetry environment variables configure exporter headers and TLS. Health and metrics paths are excluded from tracing.

## Initial service objectives

- Availability: 99.9% monthly.
- p95 API read latency: below 300 ms.
- p95 mutation latency: below 500 ms.
- Error rate: below 0.1%, excluding expected 4xx responses.
- Recovery point objective: 15 minutes.
- Recovery time objective: 60 minutes.

These objectives require external uptime monitoring, automated encrypted backups and quarterly restore drills; application code alone cannot guarantee them.
