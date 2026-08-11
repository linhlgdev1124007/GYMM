# PulseFit security baseline

## Implemented controls

- PBKDF2-SHA256 password hashing and opaque server-side sessions.
- `HttpOnly`, `SameSite=Strict` session cookies; production requires `Secure` cookies.
- Double-submit CSRF token plus strict Origin/Referer validation for unsafe API methods.
- Login and general API sliding-window rate limits with `Retry-After` responses.
- Trusted Host validation and explicit browser-origin allowlist.
- Request body limit plus per-receipt type, count and size validation.
- CSP, HSTS in secure environments, clickjacking, MIME-sniffing, referrer and browser-capability headers.
- Maximum active sessions per user and automatic expired-session cleanup.
- Successful login, failed login and logout events in the audit log with source IP.
- Production startup fails closed for insecure cookies, wildcard/missing hosts, non-HTTPS origins, weak metrics token or default administrator password.
- Production API docs are disabled.

## Production configuration

Set at minimum:

```text
GYM_ENV=production
GYM_ADMIN_PASSWORD=<unique secret of at least 12 characters>
GYM_SECURE_COOKIES=1
GYM_ALLOWED_HOSTS=gym.example.com
GYM_ALLOWED_ORIGINS=https://gym.example.com
GYM_METRICS_TOKEN=<at least 32 random characters>
GYM_TRUST_PROXY_HEADERS=1
```

Only enable `GYM_TRUST_PROXY_HEADERS` when the application is behind a trusted proxy that overwrites incoming forwarding headers.

## Deployment controls still required

The in-process rate limiter is a last-line defense for the current single-instance application. Multi-worker or multi-instance deployments must enforce shared limits at a trusted reverse proxy, API gateway or WAF. TLS termination, DDoS protection, secret storage/rotation, vulnerability scanning and encrypted backups also belong to the deployment platform.

Before handling real enterprise data, use a managed MySQL service with encrypted automated backups, move receipts to private object storage with signed access, add MFA/SSO and complete an OWASP ASVS Level 2 verification.

## Security verification

```powershell
python -m pip install -r requirements-dev.txt
python -m pip_audit -r requirements.txt
npm audit --omit=dev --audit-level=high
npm --prefix client audit --omit=dev --audit-level=high
npm run test:backend
```

The audit commands check production dependencies against known vulnerability advisories. The suite verifies security headers, request IDs, readiness, authenticated metrics, CSRF, cross-site rejection, request limits, login throttling, session caps and untrusted hosts. CI runs these gates for every push and pull request.
