# Project audit and redesign record

## Executive summary

The previous application was a server-rendered FastAPI/Jinja MVP. It contained useful gym business data and working CRUD flows, but all routing, validation, seeding, reporting and mutations lived in one large module. The redesign preserves the original data, now migrated from SQLite to MySQL, while replacing the delivery architecture with a React SPA and a layered REST server.

| Current feature | Current problem | Proposed improvement | Implementation direction |
|---|---|---|---|
| FastAPI + Jinja pages | Backend logic and rendering were coupled; CRUD required redirects | Separate UI state from business logic | React Query client consuming `/api/*` |
| Single `app/main.py` | Routes, validation, database writes, files and reports shared one large file | Explicit layers and bounded modules | `route → controller → service → SQLAlchemy` under `server/` |
| No authentication | Every mutation was publicly callable | Authenticated sessions and server-side roles | PBKDF2 password hashes, opaque session cookies, role dependencies |
| Customer list | Search only; no pagination/loading/error model | Operational member table | Debounced search, filters, server pagination, skeleton and empty states |
| Customer detail | All histories were shown at once | CRM-style profile | Overview, Membership, Check-in, PT and Notes tabs |
| Membership forms | Full-page redirects and duplicated form logic | Reusable focused workflows | Shared React membership form and query invalidation |
| PT management | Earlier group abstraction did not match daily workflow | Direct enrollment per member | Dedicated 1:1, 1:2 and 1:3 tabs with coach/schedule/session data |
| Employee CRUD | Unsafe deletion could orphan historical records | Safe archive semantics | Hard-delete unused records; archive referenced staff |
| Check-in | Giant member select and weak eligibility feedback | Reception-first workflow | Debounced search → select → verify membership → check in |
| Payments/reports | Separate server-rendered tables with no shared filtering model | Unified data access and filters | Paginated payment API and decision-oriented report screen |
| Device/sync stubs | Useful status data but isolated pages | Place secondary infrastructure appropriately | Consolidated Settings & Devices page |
| Tailwind CDN and remote icons | Runtime network dependency and production warning | Build-time design system | Local Vite/Tailwind build and Lucide React only |
| Custom JavaScript modals | Repeated event binding and full reload behavior | Component-driven interaction | React modal, toast, table, pagination and form primitives |
| Bundled monolithic frontend | No caching or route-level split | Load only what each route needs | React lazy routes; dashboard chart isolated in its own chunk |
| Manual page screenshots | Only desktop/netbook and legacy routes | Broader responsive regression | Playwright coverage at desktop, laptop, netbook, tablet and mobile |

## Preserved business scope

- Members and member profiles
- Standard membership plans and registrations
- Deposits, outstanding balances and receipt images
- PT enrollment by member, coach, schedule and session balance
- Employees and safe removal behavior
- Check-in/check-out
- Payments and cash/bank reporting
- Branches, bank accounts and device status
- Existing records migrated to MySQL, including archived legacy appointment and commission tables

Appointments and commission UI remain intentionally retired based on the approved operating workflow. Historical database tables are not destructively removed.

## Architecture

```text
client/src feature or page
        ↓
client/src/services/api.js
        ↓
server/routes
        ↓
server/controllers
        ↓
server/services
        ↓
server/models.py + MySQL/MariaDB
```

React Query owns loading, error, caching and mutation invalidation. FastAPI remains the source of truth for authentication, role checks, validation and gym business rules.

## Design decisions

- Navy is reserved for navigation, primary actions and selected states.
- Tables use 50px rows, restrained headers and one compact row-action menu.
- Borders, alignment and spacing create hierarchy; normal sections do not rely on shadows.
- Semantic color only communicates status or risk.
- Page titles use 23px type and metrics remain compact.
- Mobile uses a navigation drawer, stacked toolbars and horizontally scrollable tables.
- No CRUD path calls `window.location.reload` or `location.reload`.
