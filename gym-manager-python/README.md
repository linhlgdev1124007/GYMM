# PulseFit Gym Management

Production-oriented gym operations dashboard built as one repository and one deployable application:

- `client/`: React, Vite, Tailwind CSS, React Router, TanStack Query
- `server/`: FastAPI, SQLAlchemy, MySQL/MariaDB, cookie-session authentication
- `client/dist/`: production frontend served by FastAPI

## Local setup

```powershell
cd D:\TOOL_VID\gym-manager-python
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
npm install
npm --prefix client install
```

Copy `.env.example` values into your environment and change the default administrator password outside local development.

Create the local database once before the first run (the application creates its tables):

```powershell
& 'C:\xampp\mysql\bin\mysql.exe' -h 127.0.0.1 -P 3306 -u root -e "CREATE DATABASE IF NOT EXISTS pulsefit_gym CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
```

Production starts fail-closed when secure cookies, explicit HTTPS origins, trusted hosts, a strong administrator secret or a metrics token are missing. See [SECURITY.md](SECURITY.md) before deployment.

## Development

```powershell
npm run dev
```

- React: `http://127.0.0.1:5173`
- API: `http://127.0.0.1:8100/api`
- API docs: `http://127.0.0.1:8100/api/docs`

## Production

```powershell
npm run build
npm start
```

FastAPI serves both the REST API and React build:

```text
/api/*  → FastAPI
/*      → client/dist/index.html
```

Direct navigation and refresh at routes such as `/members/1` work through the SPA fallback.

## Docker deployment

Docker Compose runs the application and MariaDB as separate containers. The web UI is published on port `3333`; MariaDB is published only on localhost port `33306` for shell maintenance tools.

```powershell
Copy-Item .env.docker.example .env
# Change every password/token in .env before a public deployment.
docker compose up -d --build
docker compose ps
```

Open `http://localhost:3333`. Application uploads and MariaDB data persist in the named volumes `pulsefit_uploads_data` and `pulsefit_database_data`. `docker compose down` stops the stack without deleting either volume.

On the first start of an empty database volume, Compose imports `tools/database-backup.sql`. MariaDB ignores the initialization file after its data volume has been initialized.

For HTTPS deployment, set `GYM_ENV=production`, `GYM_SECURE_COOKIES=1`, the public HTTPS `GYM_ALLOWED_ORIGINS`, the public hostname in `GYM_ALLOWED_HOSTS`, and strong unique secrets in `.env`.

## Authentication

On the first writable startup, an administrator is created from:

```text
GYM_ADMIN_USERNAME
GYM_ADMIN_PASSWORD
```

Local fallback credentials are `admin` / `PulseFit@2026`. Set explicit secure values in production. Sessions are stored as SHA-256 token digests in MySQL and delivered using `HttpOnly`, `SameSite=Strict` cookies.

## Verification

```powershell
npm run build
npm run test:backend
npm test
```

The UI test checks the main routes at 1440, 1280, 1024, 768 and 390 pixel widths.
The backend suite verifies CSRF, origin/host checks, rate limiting, request limits, session caps, security headers, health probes, request IDs and protected metrics.

Operational endpoints and alert recommendations are documented in [OPERATIONS.md](OPERATIONS.md).

Operational shortcuts:

- `Ctrl/Cmd + K`: global member search
- `/`: focus member-list search
- `Esc`: close the active drawer, dialog or search surface
- `↑`, `↓`, `Enter`: navigate and open global-search results

See [AUDIT.md](AUDIT.md) for the architecture audit and [UX_AUDIT.md](UX_AUDIT.md) for measured workflow improvements.

## Database backup and restore

These are local PowerShell tools only. The `tools/` directory is never mounted by FastAPI and no API endpoint invokes them.

```powershell
.\tools\backup-database.ps1
.\tools\restore-database.ps1
```

Backup always writes `tools/database-backup.sql`. Restore reads `tools/database.sql`; when that file does not exist, it exits without changing the database. Both tools use the `GYM_DB_*` environment variables and find XAMPP MySQL automatically.

To target the Docker database from the host shell, set the container credentials and local maintenance port first:

```powershell
$env:GYM_DB_HOST="127.0.0.1"
$env:GYM_DB_PORT="33306"
$env:GYM_DB_USER="pulsefit"
$env:GYM_DB_PASSWORD="PulseFitDb@2026" # or the value from .env
.\tools\backup-database.ps1
```
