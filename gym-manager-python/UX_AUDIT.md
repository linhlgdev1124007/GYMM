# PulseFit operational UX audit

Audit date: 11/08/2026
Scope: every authenticated route, shared navigation, tables, forms, drawers, dialogs, asynchronous states, permissions and the main cross-module journeys.

## Product and route map

| Workspace | Primary user task | Main completion path |
|---|---|---|
| Dashboard | Understand today's operational risk | Metric/attention item → member drawer or check-in workspace |
| Members | Find and operate on a member | Search/filter → row/drawer → check-in, collect debt, renew, assign PT or edit |
| Memberships | Register and monitor packages | Find member → create package registration → record initial payment |
| Plans | Maintain the package catalogue | Search → row/edit → save or archive |
| Staff | Maintain staff and inspect PT load | Search → row/edit; client count → filtered members |
| PT clients | Review schedules and assignments | Type/filter → row → update coaches and session balance |
| Check-in | Admit eligible members and close visits | Search → eligibility result → check-in; open visit → check-out |
| Payments | Reconcile receipts and evidence | Filter → member preview or attach receipt |
| Reports | Review revenue, attendance and debt | Date range → summary/detail → member preview |
| Accounts | Maintain access and roles | Create/edit user → validate role and active state |
| Audit log | Trace operational changes | Filter → inspect event detail/member |
| Settings | Inspect branches, bank accounts and devices | Read-only operational status |

## Existing strengths retained

- React Query provides partial refresh, mutation pending states and targeted cache invalidation; CRUD does not reload the page.
- Member filters, page, sort, saved views and the selected drawer record are URL-addressable.
- Cross-module member links open a contextual drawer, preserving the current workspace.
- Server-side role checks are mirrored by route/action visibility in the UI.
- Tables have sticky headers, dense rows, skeleton/error/empty states and keyboard-openable rows.
- Member workflows already expose direct check-in, payment, renewal, PT and inline profile editing.
- Dates, money and phone numbers are formatted for the Vietnamese locale.
- The responsive smoke suite passes at 1440, 1280, 1024, 768 and 390 px.

## Prioritized UX debt

### P0 — Critical

No task-blocking flow was found in the tested seeded-data journeys.

### P1 — High

#### Global search is not actually global

- **Current issue:** `Ctrl/Cmd + K` searches members only. It cannot navigate to a workspace or start a frequent action.
- **Why it is a problem:** staff must remember the sidebar taxonomy and leave the keyboard for common navigation.
- **Current flow:** shortcut → search member; for modules, close palette → scan sidebar → navigate.
- **Proposed flow:** one palette returns navigation commands, permitted quick actions, recent members and live member matches.
- **Expected improvement:** module navigation drops from 2–4 pointer interactions to shortcut → type → Enter.

#### Member row actions are discoverable only as faint icons

- **Current issue:** four icon-only actions have equal weight and low contrast until hover.
- **Why it is a problem:** frequent reception actions require recognition from icons and are difficult to scan.
- **Current flow:** locate row → infer icon → hover/read tooltip → click.
- **Proposed flow:** expose the two highest-frequency actions as labelled `Check-in` and `Thu tiền`; keep renewal/edit in contextual detail where their data is visible.
- **Expected improvement:** critical actions become self-describing with no tooltip-discovery step.

### P2 — Medium

#### Empty states explain but do not complete the next step

- **Current issue:** shared tables can describe an empty result but cannot render a CTA.
- **Why it is a problem:** users understand why the table is empty but still need to find the control that resolves it.
- **Proposed flow:** shared empty state accepts a relevant action such as clear filters, add member or open member search.
- **Expected improvement:** empty result → next action in one interaction.

#### Unsaved-change warning uses a browser confirm

- **Current issue:** the message is generic and visually inconsistent with the application.
- **Why it is a problem:** it does not clearly separate continuing work from intentionally discarding changes.
- **Proposed flow:** application dialog with `Tiếp tục chỉnh sửa` as the safe action and `Bỏ thay đổi` as the destructive action.
- **Expected improvement:** clearer consequence and consistent keyboard/focus behavior.

#### Profile summary has a dense inline expiry string

- **Current issue:** package and expiry can visually run together at common desktop widths.
- **Why it is a problem:** a high-value operational date becomes harder to scan.
- **Proposed flow:** package and expiry use separate aligned text elements.
- **Expected improvement:** expiry remains readable for long package names.

### P3 — Low

- Add richer command-result highlighting and recent-query history after usage data confirms value.
- Consider server-backed saved views if staff work across multiple devices.
- Consider per-user table column preferences instead of browser-only storage.

## Key journeys and interaction counts

| Journey | Baseline | Target after this pass |
|---|---|---|
| Open a member without losing filters | Click row → drawer | Retain (1 interaction) |
| Check in from member list | Interpret icon → click | Click labelled `Check-in` |
| Collect debt from member list | Click debt or interpret icon | Click debt or labelled `Thu tiền` |
| Navigate to Payments with keyboard | Close palette → sidebar → Payments | `Ctrl/Cmd+K` → type → Enter |
| Recover from an empty filtered list | Inspect filters → identify reset controls | Click `Xóa bộ lọc` in empty state |
| Close a dirty form | Native confirm with generic choices | Explicit discard-changes dialog |

## Business-logic observations

- Membership creation atomically creates the registration, initial payment, receipts and audit entries.
- Additional collection is represented as a payment delta; collected money cannot be silently reduced.
- Check-in validates active member status, a valid non-PT package and duplicate open attendance.
- PT enrolment prevents multiple simultaneous active enrolments and validates coach availability.
- Staff deletion safely archives referenced employees and hard-deletes only unreferenced records.
- Membership transfer, package change, upgrade, freeze and cancellation create history/audit records.

Remaining platform risks are outside this UI pass: ad-hoc SQLite migrations, dictionary request bodies instead of typed schemas, no backend test suite and read-only SQLite behavior on Vercel.

## Verification baseline

- `npm run build`: passed.
- Python compilation: passed.
- `npm test`: passed all 11 primary routes at five responsive widths.
- Extended browser journeys pass command-based module navigation, command-based member creation and both branches of the unsaved-change dialog.
- No full-page reload pattern or uncaught browser error was found in the tested journeys.
