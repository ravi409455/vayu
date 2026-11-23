# Plan: library editor, "update everywhere", and form duplicate / import-as-new

Status: **planned, not started** (re-reviewed after the builder redesign). Depends on `docs/plan-form-types.md` (uses `type = custom`,
`use_start` / `use_end`, bundle schema v2). Profile plan comes after (`docs/plan-profile.md`).

## Agreed requirements
**The library is the global control point.**
- Library items are **fields** and **sections** only (pages, Key Checks and rating setups stay per form).
- The library owns **everything inside an item**: for a field, label, help text, type, config / choices,
  required, `required_if`, `show_if`, visible and the access matrix; for a section, title, visible,
  `show_if`, access, **which fields it holds and their order**. A form decides only **placement** (which page /
  position the item sits in); a push never moves an item.
- Items are **self-contained**: a rule may point only at the item's **own fields** and at **system fields that
  exist in every custom form** (`booking.*` system fields, `inspection.chassis_no`). A rule that needs another
  field is **refused on save** with a message: bundle the dependent field into the same section item, or keep
  that field out of the library.
- Definitions stay **JSON in the database**; the change is a **proper visual editor**, not a new schema.
- Inside a form, a linked item is **read-only** with **Edit in library** and **Unlink**.
- Items are created **from scratch in the library** and via **Save to library** in the builder.
- **Every save is a new revision** with history; old revisions can be restored (as a new revision); saves are
  guarded against two Admins overwriting each other.
- **Two buttons:** *Save* (forms show "update available", nothing changes) and *Save and update everywhere…*
  (opens the **review screen**).
- **Push:** updates every form whose latest version uses the item: open drafts are updated in place; forms
  with only a published version get a **new draft**. **All-or-nothing:** the review screen lists every
  affected form, every setting that will change (for example "EV: required No → Yes") and every problem;
  the push button stays **disabled until the problem list is empty**; then it applies to all forms in one
  transaction (forms locked in a fixed order). Optional **"publish automatically"** switch: **off by default**,
  behind an explicit confirmation (it cannot be undone). Experts mid-job are unaffected (pinned versions).
- The library **wins** over settings that differ in a form today; the review screen shows them first.
- **Renaming a section** (by hand or via a push) **updates the rating categories of that draft** automatically.
- **All library changes and the push are Admin-only and not grantable** (`library.edit` becomes
  non-grantable; Ops keep read-only `library.view`).
- **Form export / import** (new in this plan): Import on the Forms list; on each form's page **Export** and
  **Duplicate as new form** (new key and name; custom forms only). The copy keeps library links, copies
  pages / sections / fields / ratings / Key Checks / PDF template, and **starts as a draft**. Imports **never
  overwrite the library**; differences are listed in the report. The Promote page stays as it is.

## Current state
- `LibraryItem(kind, key, name, definition JSON, revision int, archived)`; usages are `library_item` +
  `library_revision` on `Field` / `Section` rows. No revision history; `update_item` has no stale-edit guard.
- `library.accept_update` copies **content** (label, helper text, config; section title and fields) and
  **keeps** per-form overrides (`required`, `required_if`, `show_if`, `visible`, `access`).
- Web `Library` page: list + usages + archive + raw JSON; the redesigned builder has `LibraryBox` (Save to
  library / Accept update / Unlink) in the inspector. The demo seed already has a library (4 field items,
  3 section items: tyres, documents, lights) linked into the three demo forms; none of those items has a
  rule, so they all pass the new self-contained check.
- `services.reorder` (drag-and-drop) already refuses to move fields into / out of a library-linked section
  (`ensure_not_locked`), which is the behaviour the new ownership model needs.
- `services.discard_draft` exists: a draft created by a push for a form that had **no draft** can be thrown
  away again, so such a push is reversible until published.
- `promote.import_bundle` imports a bundle as a draft of the form with the **same key**, matches library items
  by key, never overwrites them, writes nothing on conflict.

## Design
**Backend**
- `LibraryRevision(item, revision, name, definition, by, at)` written on every save; history endpoint; restore
  = client loads an old definition into the editor and saves it (no restore endpoint).
- `PATCH library/<id>` requires the `revision` the editor loaded (409 `STALE_LIBRARY_ITEM` otherwise).
- Definitions grow to include everything the library owns: field definitions already allow `required`,
  `required_if`, `show_if`, `visible`, `access`; section definitions gain `access`. Validation adds
  **self-contained rules** using the existing `rules.rule_vars` (own keys + allowed system fields).
- `accept_update` is extended to **also copy settings** (required, rules, visible, access, field order in a
  section) and to update rating category titles on a section rename (`services.rename_section`, one
  function, also called by the section serializer for manual renames).
- **Push API** (`apps/forms/library_push.py`):
  - `POST library/<id>/push-preview` → `{forms: [{form, type, state: draft|published_only, changes[],
    problems[]}], blocked: bool}`; no writes.
  - `POST library/<id>/push` `{revision, publish: bool, confirm: bool}` → 409 `PUSH_BLOCKED` with the same
    problem list if anything is wrong; otherwise one transaction: sort affected forms by id, lock, create
    drafts where needed, accept the update in every usage, validate each draft exactly like a publish
    (rules, PDF rows, Key Checks, `start.*`/`end.*` use), optionally publish each; audit `library.push` with
    the form list.
  - Affected = forms whose **latest** version links the item at an older revision; inactive forms are listed
    as skipped.
- Permissions: `library.edit` `grantable=False` plus a data migration deleting existing grants; Admin has it
  implicitly. `library.view` unchanged.
- `promote.import_bundle(actor, bundle, as_new=None)`; `POST forms/<id>/duplicate {key, name}` (server-side
  export + import-as-new, custom forms only, 409 on key clash); the draft is created with `use_start` /
  `use_end` copied.

**Web**
- **Library list:** search, kind filter, archived toggle, "Used in N forms", **New item**.
- **Item editor** (page, not a modal): left = settings (field item reuses `FieldEditor` through a small
  definition ↔ field adapter; section item reuses `ContainerEditor` (`builder/Inspector.tsx`) plus its
  **field list** with add / remove / drag-reorder and a `FieldEditor` per field), right = **live preview**
  (`PreviewDialog`'s renderer / `FormRenderer` on a tree built from the definition). Access uses the existing
  `ui/AccessEditor`. Tabs: **Settings**, **Used in** (form, version, revision, linked /
  behind), **History** (who / when / changed field keys; **Restore** loads it into the editor). Footer:
  **Save** and **Save and update everywhere…**.
- **Review screen:** table of forms with state, per-setting changes and problems; problems block the button;
  the **publish automatically** switch (off) with a confirmation that states how many forms go live and that
  it cannot be undone; result screen with links to each form.
- **Builder:** `LibraryBox` changes: a linked item is read-only with badge, **Edit in library**, **Unlink**; "update available" stays,
  with the existing per-form **Accept update** as a manual alternative.
- **Forms list / form page:** **Import** (file picker; choose *as a draft of "<form>"* when the key exists, or
  *as a new form* with key + name), **Export** (published version download) and **Duplicate as new form**
  (key + name dialog). Import report lists library differences.

## Phases
### P1: backend (≈2.5 days), PR "feat(library): revisions, ownership, push, duplicate"
Tests first.
- **T1.1** revisions: each save writes one; stale `revision` → 409; history lists changed keys; archived items
  cannot be linked.
- **T1.2** self-contained validation: a rule using an outside field is refused (message names the field);
  own fields and allowed system fields pass; section-level rules covered; derived rules too.
- **T1.3** ownership: accepting an update copies required / rules / visible / access / field order; a form's
  placement (page, position) is untouched; section rename updates that draft's rating categories (also for a
  manual rename).
- **T1.4** push preview: forms found (draft, published-only, inactive skipped), changes listed per setting,
  problems found (PDF row or Key Check pointing at a removed field, type clash, `start.*` without the start
  form); preview writes nothing.
- **T1.5** push: blocked while any problem exists (nothing changes); atomic when clean (all forms updated or
  none, including a forced failure half-way); new draft created for published-only forms; fixed lock order
  (two concurrent pushes do not deadlock); `publish: true` publishes all in one go and audits; needs
  `confirm`; live inspections keep their pinned versions.
- **T1.6** permissions: `library.edit` cannot be granted (roles API refuses); migration removes old grants;
  Ops read-only; every new view declares permissions (URL-scan test).
- **T1.7** duplicate / import-as-new: key / name required and unique; library links kept at the same
  revision; PDF template, ratings, Key Checks, `use_start` / `use_end` copied; lands as a draft; system forms
  and non-custom types refused; the import report lists library differences and **never** changes the library.
- **T1.8** existing tests: `forms/tests/test_library.py` (and the promote tests that touch links) currently
  assert that per-form overrides survive an update; they change to assert the library's values win.
- **T1.9** chore: CI 100% gate on `apps.forms.library_push` (+ existing library / promote gates);
  regenerate `openapi.yaml` (additive).

### P2: web (≈3 days; the redesigned builder makes the reuse easier), PR "feat(web): library editor, review screen, form import/export"
- **T2.1 (unit/component):** definition ↔ field adapter round-trips every field type; section field
  add / remove / reorder; save disabled when unchanged; stale 409 dialog; self-contained error shown next to
  the rule; review screen (problems disable the button, changes listed, publish switch off by default,
  confirmation text); history **Restore**; builder read-only linked item and links; import dialog modes.
- **T2.2 (browser):** create a section item in the library with two dependent fields → use it in two forms →
  edit (label, a choice, field order, `required`) → *Save and update everywhere…* → review shows both forms
  → both drafts updated; with a PDF row pointing at a removed field the push is blocked with that message;
  publish-automatically path makes both forms live while a started job keeps the old version; section
  rename keeps ratings working; duplicate a form and see the link retained, then push reaches the copy;
  export → import as new on a clean database; Ops sees the library read-only.
- **T2.3:** docs (`docs/local.md` walk-through, `README`, `plan.md` Amendments); local demo library rebuilt
  with one section item that holds two dependent fields and an internal rule, shared by two demo forms.

## Risks and answers
| Risk | Handling |
|---|---|
| A push edits many forms at once | Preview first; blocked on any problem; one transaction; fixed lock order; audit row lists forms. |
| Auto-publish cannot be undone | Off by default, explicit confirmation, shows exactly how many forms go live. |
| Self-contained rule is too strict for Admins | The error says what to do (bundle into one section item, or keep the field out); `rule_vars` makes it a one-line check. |
| Library wins over a form's own setting | Review screen shows every changed setting per form; Admin can unlink first. |
| Editor effort (section items) | Reuse `FieldEditor` / `ContainerEditor` / `FormRenderer`; no new field widgets. |
| Two Admins edit the same item | Revision check on save (409). |
| A push edits a form's **existing** draft in place (work in progress is changed, not reversible) | The review screen marks such forms ("this draft already has changes"); forms with no draft get a new draft that `discard_draft` can remove; publish-automatically is the only irreversible step. |

## Assumptions to confirm before starting
1. Library items are used in **custom forms only** in v1 (their own fields are `inspection.*`); start / end /
   booking forms keep local fields.
2. "Latest version" is the target of a push; older published versions are never touched.
3. Inactive forms are **skipped and listed**, not updated.
4. Duplicate is **custom forms only**; system forms are not duplicable.

## Done when
Backend suite + gates (incl. the new push gate), Vitest, full Playwright, local-stack check green in CI; the
library editor journey passes in a browser; the push is proven atomic by test; `plan.md` Amendments updated.
