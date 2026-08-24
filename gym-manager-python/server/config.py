from dataclasses import dataclass
import os


def _bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, "1" if default else "0").strip().lower() in {
        "1", "true", "yes", "on",
    }


def _int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(int(os.getenv(name, default)), minimum)
    except (TypeError, ValueError):
        return default


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in os.getenv(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class Settings:
    environment: str
    secure_cookies: bool
    allowed_hosts: tuple[str, ...]
    allowed_origins: tuple[str, ...]
    trust_proxy_headers: bool
    login_rate_limit: int
    login_rate_window_seconds: int
    api_rate_limit: int
    api_rate_window_seconds: int
    max_request_bytes: int
    session_days: int
    max_sessions_per_user: int
    metrics_token: str
    dah_agent_token: str
    dah_agent_latest_version: str
    dah_agent_download_url: str
    dah_agent_sha256: str
    dah_agent_mandatory_update: bool
    enable_api_docs: bool
    log_level: str
    otel_exporter_endpoint: str
    otel_service_name: str

    @property
    def production(self) -> bool:
        return self.environment == "production"


def load_settings() -> Settings:
    environment = os.getenv("GYM_ENV", "development").strip().lower()
    secure_cookies = _bool("GYM_SECURE_COOKIES", environment == "production")
    settings = Settings(
        environment=environment,
        secure_cookies=secure_cookies,
        allowed_hosts=_csv("GYM_ALLOWED_HOSTS", "127.0.0.1,localhost,testserver"),
        allowed_origins=_csv(
            "GYM_ALLOWED_ORIGINS",
            "http://127.0.0.1:5173,http://127.0.0.1:8100,http://localhost:5173,http://localhost:8100,http://testserver",
        ),
        trust_proxy_headers=_bool("GYM_TRUST_PROXY_HEADERS"),
        login_rate_limit=_int("GYM_LOGIN_RATE_LIMIT", 10),
        login_rate_window_seconds=_int("GYM_LOGIN_RATE_WINDOW_SECONDS", 900),
        api_rate_limit=_int("GYM_API_RATE_LIMIT", 600),
        api_rate_window_seconds=_int("GYM_API_RATE_WINDOW_SECONDS", 60),
        max_request_bytes=_int("GYM_MAX_REQUEST_BYTES", 55 * 1024 * 1024),
        session_days=_int("GYM_SESSION_DAYS", 7),
        max_sessions_per_user=_int("GYM_MAX_SESSIONS_PER_USER", 5),
        metrics_token=os.getenv("GYM_METRICS_TOKEN", "").strip(),
        dah_agent_token=os.getenv("GYM_DAH_AGENT_TOKEN", "").strip(),
        dah_agent_latest_version=os.getenv("GYM_DAH_AGENT_LATEST_VERSION", "").strip(),
        dah_agent_download_url=os.getenv("GYM_DAH_AGENT_DOWNLOAD_URL", "").strip(),
        dah_agent_sha256=os.getenv("GYM_DAH_AGENT_SHA256", "").strip().lower(),
        dah_agent_mandatory_update=_bool("GYM_DAH_AGENT_MANDATORY_UPDATE"),
        enable_api_docs=_bool("GYM_ENABLE_API_DOCS"),
        log_level=os.getenv("GYM_LOG_LEVEL", "INFO").strip().upper(),
        otel_exporter_endpoint=os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip(),
        otel_service_name=os.getenv("OTEL_SERVICE_NAME", "pulsefit-api").strip() or "pulsefit-api",
    )
    if settings.production:
        problems = []
        if not settings.secure_cookies:
            problems.append("GYM_SECURE_COOKIES must be enabled")
        if "*" in settings.allowed_hosts:
            problems.append("GYM_ALLOWED_HOSTS must not contain '*' in production")
        if not settings.metrics_token:
            problems.append("GYM_METRICS_TOKEN is required")
        if len(settings.metrics_token) < 32 or settings.metrics_token.startswith("replace-with-"):
            problems.append("GYM_METRICS_TOKEN must contain at least 32 characters")
        if not settings.dah_agent_token:
            problems.append("GYM_DAH_AGENT_TOKEN is required")
        if len(settings.dah_agent_token) < 24 or settings.dah_agent_token.startswith("replace-with-"):
            problems.append("GYM_DAH_AGENT_TOKEN must contain at least 24 characters")
        if not os.getenv("GYM_ALLOWED_HOSTS", "").strip():
            problems.append("GYM_ALLOWED_HOSTS must be configured explicitly")
        if not os.getenv("GYM_ALLOWED_ORIGINS", "").strip():
            problems.append("GYM_ALLOWED_ORIGINS must be configured explicitly")
        if any(not origin.startswith("https://") for origin in settings.allowed_origins):
            problems.append("all GYM_ALLOWED_ORIGINS must use HTTPS")
        admin_password = os.getenv("GYM_ADMIN_PASSWORD", "")
        if len(admin_password) < 12 or admin_password in {"PulseFit@2026", "change-this-password"}:
            problems.append("GYM_ADMIN_PASSWORD must be a non-default value of at least 12 characters")
        if problems:
            raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
    return settings


settings = load_settings()
