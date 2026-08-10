# PulseFit UX workflow audit

This audit records the operational friction found before the enterprise UX pass and the implemented target flows. The visual identity was intentionally preserved.

## Workflow measurements

| Workflow | Before | After | Result |
|---|---|---|---|
| Open member | Row menu → View profile → new page | Click row/name → URL-addressable drawer | 3 interactions → 1 |
| Inspect membership, debt, attendance and PT | Open profile → switch among 3–4 tabs | One quick-detail/Overview summary | Up to 5 interactions → 1 |
| Check in known member | Open Check-in → search again → select → confirm | Member row/detail → Check-in | 4 interactions → 1–2 |
| Collect member debt | Navigate Payments → search member → edit package/payment | Member detail → Thu tiền → confirm | 4–5 interactions → 2 before confirmation |
| Renew membership | Open profile → package tab → create | Member row/detail → Gia hạn | 4 interactions → 1 before form input |
| Assign PT | Open profile → PT tab → register | Member row/detail → Gán PT | 4 interactions → 1 before selection |
| Change phone/email/status | Full edit form → locate field → save | Click field → edit inline → save | 4 interactions → 2 |
| Inspect member from Payments/PT/Dashboard | Leave module → profile → return and recreate context | Member link → drawer over current module | Context loss removed |
| Find a member globally | Navigate Members → focus search → enter query → open | Ctrl/Cmd+K → type → Enter | Keyboard-first, no manual navigation |
| Edit plan/employee | More menu → Edit | Click row/name or visible Edit action | 2 interactions → 1 |
| Find members for a plan/PT | Navigate Members → recreate filters | Click member/client count → prefiltered workspace | 3–4 interactions → 1 |

## Members reference workspace

- Search, frequent saved views, status/package/PT filters, sort and pagination are server-driven.
- Search/filter/sort/page and selected member are represented in the URL.
- Browser Back closes/restores quick detail predictably.
- Closing a drawer does not clear search, filters, sort, pagination or scroll context.
- Rows support mouse and keyboard activation, visible focus, selected state and bulk selection.
- Primary row actions are visible on hover/focus. Overflow menus are reserved for secondary actions.
- Initial, filtered-empty, loading and error states are differentiated.

## Shared interaction architecture

- `Drawer`: URL-compatible master-detail inspection with Escape support and responsive full-screen behavior.
- `DataTable`: clickable keyboard rows, sticky headings, selection, selected state, loading/error/empty states.
- `InlineEditField`: local field updates without opening a large form.
- `SearchableSelect`: keyboard-friendly entity lookup for plans and coaches.
- `GlobalSearch`: Ctrl/Cmd+K search by member name, phone or code with arrow/Enter navigation.
- `QuickPaymentForm`: focused debt collection without re-entering known member/package data.

## Context and scalability

- List queries use remote debounced search and server-side filters, sorting and pagination.
- No full-page reload is used after CRUD.
- TanStack Query invalidates only related data and preserves the active workspace.
- Quick member links from Dashboard, Memberships, PT and Payments are intercepted as contextual previews while retaining semantic full-profile links for new tabs.
- Routes and sidebar entries are role-filtered, while sensitive API endpoints enforce server-side roles.

## Remaining scale boundary

SQLite remains appropriate for the bundled single-instance deployment. Multi-branch, multi-instance or million-record production should migrate persistence to PostgreSQL and add indexed query plans. The UX and API boundaries are prepared for server-side datasets, but no fake branch-switching or unnecessary virtualization was introduced without corresponding backend data.
