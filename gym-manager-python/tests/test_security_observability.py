import os
from pathlib import Path
import shutil
import tempfile
from io import BytesIO
import asyncio

TEST_DIR = Path(tempfile.mkdtemp(prefix="pulsefit-security-tests-"))
os.environ.update({
    "GYM_ENV": "test",
    "GYM_DATABASE_PATH": str(TEST_DIR / "test.sqlite3"),
    "GYM_ADMIN_USERNAME": "admin",
    "GYM_ADMIN_PASSWORD": "TestPassword!2026",
    "GYM_ALLOWED_HOSTS": "testserver",
    "GYM_ALLOWED_ORIGINS": "http://testserver",
    "GYM_TRUST_PROXY_HEADERS": "1",
    "GYM_LOGIN_RATE_LIMIT": "5",
    "GYM_LOGIN_RATE_WINDOW_SECONDS": "900",
    "GYM_API_RATE_LIMIT": "500",
    "GYM_MAX_REQUEST_BYTES": "1048576",
    "GYM_MAX_SESSIONS_PER_USER": "3",
    "GYM_METRICS_TOKEN": "m" * 40,
})

import pytest
from fastapi.testclient import TestClient

from server.database import SessionLocal, engine
from server.config import load_settings
from server.main import app
from server.models import AuthSession, Device
from server.timeutils import utc_now


ORIGIN = {"Origin": "http://testserver"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app, base_url="http://testserver") as test_client:
        yield test_client
    engine.dispose()
    shutil.rmtree(TEST_DIR, ignore_errors=True)


def login(client: TestClient, ip: str = "10.0.0.1"):
    return client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "TestPassword!2026"},
        headers={**ORIGIN, "X-Forwarded-For": ip},
    )


def test_health_request_id_metrics_and_security_headers(client):
    with SessionLocal() as db:
        device = db.query(Device).filter(Device.code == "DAH-2470802").first()
        if not device:
            device = Device(code="DAH-2470802", name="DAH1017", model="DAH1017", status="online")
            db.add(device)
        device.last_heartbeat_at = utc_now()
        db.commit()

    request_id = "request-test-0001"
    response = client.get("/api/health/ready", headers={"X-Request-ID": request_id})
    assert response.status_code == 200
    assert response.json()["status"] == "ready"
    assert response.json()["database"] == "ok"
    assert response.json()["dah1017"] == "online"
    assert response.headers["x-request-id"] == request_id
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["cache-control"] == "no-store"

    assert client.get("/api/metrics").status_code == 401
    metrics = client.get(
        "/api/metrics", headers={"Authorization": f"Bearer {'m' * 40}"}
    )
    assert metrics.status_code == 200
    assert "pulsefit_http_requests_total" in metrics.text
    assert "pulsefit_http_request_duration_seconds" in metrics.text


def test_login_issues_session_and_csrf_and_audits_mutations(client):
    response = login(client)
    assert response.status_code == 200
    assert client.cookies.get("gym_session")
    csrf = client.cookies.get("gym_csrf")
    assert csrf

    rejected = client.patch(
        "/api/members/999999",
        json={"name": "No CSRF"},
        headers=ORIGIN,
    )
    assert rejected.status_code == 403

    allowed_through_security = client.patch(
        "/api/members/999999",
        json={"name": "Valid CSRF"},
        headers={**ORIGIN, "X-CSRF-Token": csrf},
    )
    assert allowed_through_security.status_code == 404
    assert allowed_through_security.json()["requestId"]


def test_cross_site_mutation_and_oversized_request_are_rejected(client):
    csrf = client.cookies.get("gym_csrf")
    cross_site = client.post(
        "/api/auth/logout",
        headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf},
    )
    assert cross_site.status_code == 403

    oversized = client.post(
        "/api/auth/login",
        content=b"{}",
        headers={**ORIGIN, "Content-Type": "application/json", "Content-Length": "1048577", "X-Forwarded-For": "10.0.0.9"},
    )
    assert oversized.status_code == 413


def test_login_rate_limit_returns_retry_after(client):
    headers = {**ORIGIN, "X-Forwarded-For": "10.9.9.9"}
    for _ in range(5):
        response = client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "wrong-password"},
            headers=headers,
        )
        assert response.status_code == 401
    limited = client.post(
        "/api/auth/login",
        json={"username": "admin", "password": "wrong-password"},
        headers=headers,
    )
    assert limited.status_code == 429
    assert int(limited.headers["retry-after"]) > 0


def test_session_count_is_capped_per_user(client):
    for index in range(5):
        assert login(client, f"10.20.0.{index + 1}").status_code == 200
    with SessionLocal() as db:
        assert db.query(AuthSession).count() <= 3


def test_admin_can_change_an_account_password(client):
    assert login(client, "10.0.0.77").status_code == 200
    csrf = client.cookies.get("gym_csrf")
    headers = {**ORIGIN, "X-CSRF-Token": csrf}
    created = client.post(
        "/api/users",
        json={
            "username": "password-test",
            "displayName": "Password Test",
            "password": "OldPassword!2026",
            "role": "receptionist",
        },
        headers=headers,
    )
    assert created.status_code == 200
    user_id = created.json()["id"]

    mismatch = client.patch(
        f"/api/users/{user_id}/password",
        json={"password": "NewPassword!2026", "confirmPassword": "not-the-same"},
        headers=headers,
    )
    assert mismatch.status_code == 422

    changed = client.patch(
        f"/api/users/{user_id}/password",
        json={"password": "NewPassword!2026", "confirmPassword": "NewPassword!2026"},
        headers=headers,
    )
    assert changed.status_code == 200
    assert changed.json()["sessionsRevoked"] is True

    logged_in = client.post(
        "/api/auth/login",
        json={"username": "password-test", "password": "NewPassword!2026"},
        headers={**ORIGIN, "X-Forwarded-For": "10.0.0.78"},
    )
    assert logged_in.status_code == 200


def test_untrusted_host_is_rejected(client):
    response = client.get("/api/health/live", headers={"Host": "evil.example"})
    assert response.status_code == 400


def test_receipts_require_authentication_and_validate_real_image_content(client, tmp_path, monkeypatch):
    from starlette.datastructures import UploadFile
    from server.services import members_service

    client.cookies.clear()
    assert client.get("/uploads/receipts/missing.png").status_code == 401
    assert login(client, "10.0.0.88").status_code == 200
    assert client.get("/uploads/receipts/missing.png").status_code == 404

    monkeypatch.setattr(members_service, "RECEIPT_DIR", tmp_path)
    fake = UploadFile(BytesIO(b"<html>not an image</html>"), filename="receipt.png")
    with pytest.raises(Exception) as error:
        asyncio.run(members_service.save_receipt(fake))
    assert error.value.status_code == 400
    assert not list(tmp_path.iterdir())


def test_production_configuration_fails_closed(monkeypatch):
    monkeypatch.setenv("GYM_ENV", "production")
    monkeypatch.setenv("GYM_SECURE_COOKIES", "0")
    monkeypatch.setenv("GYM_ADMIN_PASSWORD", "PulseFit@2026")
    monkeypatch.delenv("GYM_ALLOWED_HOSTS", raising=False)
    monkeypatch.delenv("GYM_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("GYM_METRICS_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="Unsafe production configuration"):
        load_settings()
