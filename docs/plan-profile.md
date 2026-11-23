# Plan: user profile (picture, password, theme) + Admin-only identity edits

Status: **planned, not started.** Third in the order (re-reviewed after the builder redesign; estimate now ≈ 4.5 days): **form types (`docs/plan-form-types.md`) → library +
form import (`docs/plan-library.md`) → this profile plan.** Decisions below are agreed; the ladder review
(2026-11) made two simplifications, marked **(simplified)**.

## Agreed requirements
**Every person, on their own profile** (opened from the sidebar footer: avatar + name):
| Setting | Rule |
|---|---|
| Picture | Pick a file, upload to the API. **(simplified)** The server **centre-crops to a square** itself; there is **no crop dialog in v1** (add a drag-and-zoom dialog only if people complain about framing). Server verifies it is a real JPEG/PNG/WebP image (by decoding, not by the file name), strips metadata (GPS), keeps one 256 px JPEG. Limit 5 MB. Person can remove it (initials fall back). |
| Password | Unchanged rules: old password, min 8, not common, not the username; signs out other devices. |
| Theme | Light / Dark / Match my device, saved on the server per person. **Default Light for everyone**, sign-in page Light. |
| Details | Name, username, email, role, phone shown **read-only** with an "ask an Admin" note. |

**Admin only (cannot be delegated):** change name, email, role, status and the new **phone** of any user;
remove any user's picture (from that user's edit dialog). `users.manage` becomes non-grantable.

**Phone:** new optional field, Indian mobile format (same normalisation as customer phones), set only by
Admins; visible to Ops, Admins and the person; not to other experts.

**Who sees pictures:** the person; Ops and Admins (job board next to the expert, Admin user edit dialog).
Not other experts, customers or PDFs. Served through the API with an access check.

**Audit log (all recorded, never the password or image):** password change, own picture set/removed,
Admin removed a picture, theme change.

**Out of scope:** notification preferences (with Android push), "sign out my other devices" button,
Admin upload-on-behalf, picture approval, pictures in PDFs/booking header/users table/audit list.
**Android** later gets the same screen; the API stays device-neutral.

## Before you start
- The form-types and library plans land first. Expect overlap in: `web/src/Layout.tsx` (the sidebar is now
  **collapsible to icons**: the profile button must work as avatar-only when collapsed),
  `web/src/styles.css`, `web/src/App.tsx`, `web/src/pages/admin/Users.tsx`, the Ops Bookings / job board
  pages, `backend/apps/accounts/*` (views, serializers, catalog, urls), `backend/openapi.yaml`, `plan.md`.
  Rebase, re-run the full suites, then begin.
- The API is **frozen** (`backend/openapi.yaml`, oasdiff in CI). Everything here is additive (new
  endpoints, new response fields); nothing is renamed or removed, so CI stays green. Add a line to
  `plan.md` Amendments when starting.

## Design (decided)
**Data** (`accounts` migration `0006`, next free number if the parent added one):
`User.phone` (CharField 20, blank), `User.theme` (`light|dark|system`, default `light`),
`User.avatar` (`BinaryField`, null; **(simplified)** the 256 px JPEG, about 15 KB), `User.avatar_version`
(PositiveInteger, default 0; bumped on every change, used for the cache-busting URL and the `ETag`).
Second migration: delete `RolePermission` rows for `users.manage`.

**Storage:** **(simplified)** the picture bytes live **in the database** (about 3 MB for 200 users): no
object-store keys, no deleting old files, no orphans, no dependency on the bucket. Never listed in user
queries (`defer("avatar")`); only the picture endpoint reads it.

**Endpoints (all under `/api/v1/`):**
| Call | Who | Notes |
|---|---|---|
| `GET auth/me` | signed in | adds `phone`, `theme`, `avatar_url` (`/users/<id>/picture?v=<version>` or null) |
| `PATCH auth/me/profile` `{theme}` | self | any other key → 400 `FIELD_NOT_EDITABLE` listing the keys |
| `PUT auth/me/picture` (multipart `file`) | self | throttled (scope `avatar`, e.g. 20/hour); audit; stores into `User.avatar` |
| `DELETE auth/me/picture` | self | audit |
| `GET users/<id>/picture` | self, or anyone with `users.view` (Ops, Admin) | `Cache-Control: private, max-age=86400`, `ETag`, 304; 404 when none/not allowed |
| `DELETE users/<id>/picture` | `users.manage` (Admin only) | audit `user.picture_removed_by_admin` |
| `PATCH users/<id>` | `users.manage` | now also accepts `phone` (validated/normalised) |
| `POST auth/change-password` | self | unchanged rules; now audited (`user.change_password`) |

User list/detail serializers add `phone` and `avatar_url` for viewers with `users.view`.
Experts have no `users.view`, so they cannot read other people's pictures or phones.

**Picture processing** (`apps/accounts/avatars.py`, new, 100% branch-coverage gate): size check before
decoding, `Image.open` + `verify`, allow only JPEG/PNG/WebP, pixel-count guard (decompression bomb),
`exif_transpose`, centre-crop to square, `resize(256)`, re-encode JPEG q85 with no metadata.

**Web:**
- `theme.ts`: resolve `light|dark|system`, set `data-theme` on `<html>`, cache the last signed-in
  choice in `localStorage` and apply it from an inline script in `index.html` (no flash); sign-in page
  and signed-out state are always Light.
- Dark palette: move every hard-coded colour in `styles.css` and the few inline styles into CSS
  variables with a dark set (`:root[data-theme="dark"]`, plus `prefers-color-scheme` for `system`).
  Native controls get `color-scheme`. PDF preview iframe stays as the PDF is.
- `Avatar` component (picture with initials fallback, stable colour per user).
- `/profile` page: avatar + Upload/Remove (plain file picker; **no crop dialog**), theme radio group,
  change-password form, read-only details block.
- Sidebar footer: the existing `.who` block in `Layout.tsx` (icon + "name · role", already hidden to icons
  when collapsed) becomes the button to `/profile`, showing the avatar; "Sign out" stays; the old "Change
  password" link goes (the forced-change screen stays as is).
- Users screen: edit dialog gains **Phone** and the person's picture with **Remove picture**.
- **Job board and Ops Bookings page** (decided): `Avatar` next to the expert's name in both lists (same
  component, initials fallback).
- Roles screen: needs no change (it already reads `grantable`); `users.manage` now shows "Admin only".

## Phases
### P1: backend (≈1.5 days) — PR "feat(accounts): profile picture, theme, phone"
Tests first, then code.

- **T1.1 test(accounts): model + me.** New fields and defaults; `GET auth/me` returns them; `avatar_url`
  null until set and carries the version after.
- **T1.2 test(accounts): self-service limits.** `PATCH auth/me/profile` accepts valid theme only; name,
  email, username, role, phone, is_active, must_change_password → 400 `FIELD_NOT_EDITABLE`; unknown theme
  → 400; unauthenticated → 401; a user with a forced password change is blocked (same rule as other views).
- **T1.3 test(accounts): picture upload.** JPEG/PNG/WebP accepted → stored as a centre-cropped 256×256
  JPEG in `User.avatar`; metadata stripped (assert no EXIF/GPS in the stored bytes); a non-square photo is
  cropped from the centre; a PNG named `.jpg` still works; a GIF, an SVG, text,
  an empty body, a truncated file, an image over 5 MB, and a decompression-bomb image are all refused with
  clear codes; replacing overwrites the bytes and bumps `avatar_version`; throttle returns 429.
- **T1.4 test(accounts): picture access.** Owner 200; Ops 200; Admin 200; another expert 404; anonymous
  401; deactivated user's picture still readable by staff; `Cache-Control` and `ETag`; `If-None-Match` →
  304; no picture → 404.
- **T1.5 test(accounts): Admin powers.** Admin sets/clears `phone` (normalised to `+91…`, invalid
  rejected); Admin removes a picture (audited, expert falls back to initials); Ops and Expert get 403 on
  `PATCH users/<id>`, `DELETE users/<id>/picture`, reset-password and create.
- **T1.6 test(accounts): `users.manage` non-grantable.** Roles API refuses to grant it (`NOT_GRANTABLE`);
  Roles screen payload shows `grantable: false`; the data migration removes an existing Ops grant (test
  with a pre-existing row); update tests that granted it to Ops; update the permission-catalog tests.
- **T1.7 test(accounts): audit.** Each of: password change, picture set, picture removed (self), picture
  removed (Admin), theme change writes one row with a clear summary and no secret or image data.
- **T1.8 feat: implement** models/migrations, `avatars.py`, views/urls, serializers, throttle scope,
  catalog flag, audit calls (no object-store code: the bytes are a column). Declare permissions on every new view so
  the URL-scan test passes.
- **T1.9 chore:** regenerate `backend/openapi.yaml` (oasdiff must report no breaking change); CI gate
  line `pytest apps/accounts --cov=apps.accounts.avatars --cov=apps.accounts.permissions --cov=apps.accounts.roles --cov-fail-under=100`;
  `docs/integrations.md` unchanged (API-key surface is not touched).

### P2: web foundations (≈1 day) — PR "feat(web): profile page, avatar, theme switch"
- **T2.1 test:** `theme.ts` (resolve `system` from the device setting; cache read/write; signed-out is
  Light; logout resets to Light); `Avatar` (initials for one/two/odd names, stable colour, image wins,
  broken image falls back).
- **T2.2 test (component):** Profile page — read-only details with the Admin note; theme choice sends
  `PATCH auth/me/profile` and applies at once; password form shows server errors in plain words and a
  mismatch locally; Remove button only when a picture exists; upload error messages (too big, not an
  image).
- **T2.3 feat:** `theme.ts` + inline no-flash script, `Avatar`, `/profile` route and page,
  sidebar footer button (avatar-only when the sidebar is collapsed); remove the sidebar "Change password" link; `useAuth` carries the new fields and
  refreshes after each change.

### P3: dark palette sweep (≈2 days) — in the same PR as P2 or its own ("feat(web): dark theme")
- **T3.1 audit:** list every hard-coded colour (`styles.css` now has **94 hex + 6 rgba** after the builder
  canvas, camera capture, info tips and collapsible sidebar were added; 3 in `.tsx`; inline styles such as thumbnail
  placeholders, pills, progress bars, the dashboard bars); replace with variables; add the dark set;
  `color-scheme` for native inputs, date pickers and scrollbars.
- **T3.2 test (browser):** with `data-theme=dark`, background/text/border colours of the shell, a card, an
  input, a table, a modal, each pill tone and the toast are all dark-appropriate (assert computed colours
  and contrast ≥ 4.5:1 for body text); `system` follows `prefers-color-scheme` (Playwright `colorScheme`).
- **T3.3 manual:** screenshot every screen in both themes (admin builder, PDF designer, job board,
  booking tabs, expert wizard on a phone-sized viewport) and fix what looks off.

### P4: Admin and Ops touches (≈0.5 day) — PR "feat(web): admin phone + picture removal, avatars on the job board"
- **T4.1 test (component):** Users edit dialog shows Phone and the picture; **Remove picture** is only
  there when one exists and calls `DELETE users/<id>/picture`; phone errors are shown; job board shows the
  avatar or initials next to the expert.
- **T4.2 feat:** implement the above.

### P5: browser journeys, docs, release (≈0.5 day)
- **E2E (new `e2e/profile.spec.ts`):**
  1. Expert signs in → Profile → uploads a non-square picture (it shows as a square) → the sidebar shows it → Ops sees it on the
     job board and the Bookings page next to that expert → another expert cannot fetch it (404).
  2. Theme: choose Dark → page is dark immediately → reload (still dark, no light flash) → sign out
     (sign-in page is Light) → sign in on a fresh browser context (Dark again, from the server).
  3. Password: change it → the old password fails, the new one works, an older session is signed out.
  4. Locked fields: name/email/role/phone are not editable on the profile; the API refuses them.
  5. Admin edits an expert's phone, then removes their picture → expert sees initials; audit rows exist.
  6. `users.manage` cannot be granted to Ops (Roles screen shows "Admin only").
- Update `docs/local.md` walk-through, `README`, plan Amendments, local demo seed (give one demo user a
  phone number). Run: backend suite + gates, Vitest, full Playwright, local-stack check, CI green.

## Risks and how we handle them
| Risk | Handling |
|---|---|
| Dark palette touches almost every screen | Variables first, then a screenshot pass; contrast assertions in the browser tests. |
| Hidden metadata (GPS) in uploaded photos | Re-encode without metadata; test asserts none in the stored bytes. |
| Hostile uploads (huge, disguised, decompression bombs) | Size cap before decoding, decode-based type check, pixel limit, throttle. |
| Picture bytes inflate user queries | `defer("avatar")` everywhere; only the picture endpoint loads it. |
| Pictures leak to people who should not see them | Access-checked endpoint, 404 for others, tests for every role; no public or signed links. |
| Removing `users.manage` from Ops breaks something | Data migration + tests; Ops never had it by default; Roles screen shows "Admin only". |
| Theme flash on load | Inline script applies the cached choice before React starts. |
| Audit log noise from theme changes | Accepted; the Audit screen's action filter can hide `user.theme_change`. |
| Merge conflicts with the parent session | Start only after it merges; rebase first; the overlap files are listed above. |

## Done when
All tasks pass in CI (backend gates incl. the new one, Vitest, Playwright, oasdiff); the local stack check
passes; the picture/theme/password journey works on a phone-sized viewport; a manual pass in both themes
finds nothing unreadable; `plan.md` Amendments updated.

## Estimate
About **4 days** in total (backend 1.5, web foundations 1, dark palette 1.5, admin/Ops touches and browser
journeys 1) after the ladder simplifications (picture in the database, no crop dialog).
