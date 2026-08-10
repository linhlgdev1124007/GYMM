# PulseFit Gym Management

Production-oriented gym operations dashboard built as one repository and one deployable application:

- `client/`: React, Vite, Tailwind CSS, React Router, TanStack Query
- `server/`: FastAPI, SQLAlchemy, SQLite, cookie-session authentication
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

## Authentication

On the first writable startup, an administrator is created from:

```text
GYM_ADMIN_USERNAME
GYM_ADMIN_PASSWORD
```

Local fallback credentials are `admin` / `PulseFit@2026`. Set explicit secure values in production. Sessions are stored as SHA-256 token digests in SQLite and delivered using `HttpOnly`, `SameSite=Strict` cookies.

## Verification

```powershell
npm run build
npm test
```

The UI test checks the main routes at 1440, 1280, 1024, 768 and 390 pixel widths.

Operational shortcuts:

- `Ctrl/Cmd + K`: global member search
- `/`: focus member-list search
- `Esc`: close the active drawer, dialog or search surface
- `↑`, `↓`, `Enter`: navigate and open global-search results

See [AUDIT.md](AUDIT.md) for the architecture audit and [UX_AUDIT.md](UX_AUDIT.md) for measured workflow improvements.
