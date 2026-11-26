# Plan: photos and work survive sign-out and uninstall (Android + small backend)

Status: **server and Android parts A and B built** (branch `feat/media-backup`, PR #25, draft: not
merged until phone-tested); the phone test is next. Requirements, senior review, grill-me and screens closed (owner, 2026-11-26).
Server notes: the whole sign-in request is now documented in `openapi.yaml` (`LoginRequest`,
with `install_id`; owner's choice 2026-11-26); oasdiff calls username/password/client "new
required" only because sign-in was never documented before, so that commit is marked
`[api-break-ok]`. The logout counts are documented (`LogoutCounts`).
Estimate ≈ 5.5–6.5 days. Follows `docs/engineering-standards.md`.

## Why
An expert on site takes photos that can't be taken again (the car may be sold, the customer gone).
Today:
- **Sign-out** is blocked while anything is unsent, because sign-out deletes the person's drafts
  and files (`AppViewModel.signOut` → `forgetDrafts(all = true)`).
- **Uninstall** (or "Clear storage") deletes everything for good: files live only in the app's own
  storage, `allowBackup="false"`, nothing is outside the app.

## Rule changes (owner-approved; land in the same change as the code)
These written rules say the opposite today and are changed, not worked around (standards §1, §8):
- `docs/engineering-standards.md` §2.7 "Sign-out clears what the device holds" and §5 "Sign-out
  refuses while unsent work exists, then wipes…" → sign-out keeps **unsent** work (drafts, files) for
  that person and clears everything else (sent drafts, copies, caches, notices, tokens); backup copies
  of inspection files are kept in `Documents/Vayu` under the rules below.
- `docs/android-requirements.md` items 7 and 7b → same wording.
- `REQUIREMENTS.md` (one active device per expert; privacy) → a signed-out phone that still holds work
  keeps blocking sign-in on another phone; backup copies outside the app are an approved new place
  customer data lives (photos, videos, signatures, documents).
- New permission (`MANAGE_EXTERNAL_STORAGE`) and new data outside the app: approved by the owner.

## Agreed requirements
1. **Sign out, sign in again (same person, same phone): nothing is lost.**
   - Sign-out is allowed with unsent work. It warns, naming the leads: "TST-1014, TST-1016 are not
     sent yet. They stay on this phone and send when you sign in again."
   - While signed out nothing uploads. When the same person signs in, their drafts are back and the
     uploads start on their own.
   - Another person signing in on that phone sees only their own work, and **nothing** about the
     first person's waiting work (no line on the sign-in screen). Ops sees it on the Users page.
   - A draft file that can't be read still blocks sign-out (as today).
   - A signed-out person's unsent work is **never deleted by the app**, even if they never come back
     (left, deactivated, phone handed over). Ops gets the files from the backup folder.
2. **Uninstall (or Clear storage): drafts and automatic upload are lost (accepted), files are not.**
   - Every photo, video, document and signature is also saved as a **backup copy** in
     `Documents/Vayu/<booking code>/` named `<page> - <field> <n>.<ext>`
     (`TST-1014/Exterior - Front left 1.jpg`).
   - The folder is **hidden from the Gallery** (`.nomedia`), so customer photos never mix with personal
     photos or reach the expert's Google Photos. To send: Files app → Documents → Vayu → booking
     folder → Share. Ops adds the files on the web booking page (existing Ops file edit).
   - The booking folder keeps the code it had at the first photo, even if Ops edits the Booking ID later.
3. **Backup copies are deleted:**
   - when the server has the file **and** the copy is 2+ days old;
   - 2 days after the phone learns the server will never take it (Ops finished without the missing
     files, booking cancelled, deleted or given to another expert);
   - at once when the expert discards the lead or replaces that photo;
   - never otherwise (a copy the server still needs stays).
   - After a reinstall: copies this install didn't make are listed in a notice ("Found copies from
     your earlier install: TST-1014. Send them to Ops. They will be deleted on 28 Nov.") and deleted
     **2 days after they were found**. Accepted risk: moving the phone clock forward deletes them early.
   - If the app is never installed again, nothing can delete them; Ops tells the expert to delete the
     folder after sending it.
4. **Permission: "All files access", experts only.**
   - After sign-in an expert without it sees one screen: "Vayu keeps a backup of your photos. Turn on
     file access." with a button that opens the Android setting for our app (fallback: the general
     "All files access" list when the per-app screen can't open).
   - Turned off later (mid-inspection): the camera **keeps working**; a red line says "Backups are off.
     Turn on file access." with the same button. New files have no copy until it is on again.
   - Ops never sees it (Ops uploads go straight to the server; no drafts).
   - Allowed because the app is an APK, not on Google Play.

## Server (≈ 1 day)
Keep refusing a **different** phone while work sits on this one, even after this phone signed out;
let **the same install** back in.

- `Device.install_id` (new, nullable UUID): the phone generates it once per install and keeps it in
  plain preferences. Sent on mobile sign-in (`install_id`, optional, additive in `openapi.yaml`).
  Validated as a UUID; **never returned by any endpoint and never logged** (it only skips a data-safety
  check, but it is still not to be leaked). An app without it behaves as today.
- `POST auth/logout` takes optional `drafts` / `files` counts. The device is still revoked (that is what
  kills its tokens, unchanged); when the counts are above 0 it is also marked `held_after_sign_out_at`
  (new field) and the counts are stored in `unsynced`.
- `register_device_and_tokens`: a device **blocks** when it holds work and is either active, or revoked
  by its own sign-out and still held (`held_after_sign_out_at` set). A blocking device with the **same
  `install_id` for the same user** does not block: it is released and replaced. This also covers a
  sign-out without signal (the server never heard it; the device still looks active).
- **Releases** (they mean "accept the loss" and clear `held_after_sign_out_at` too): Admin "Sign out
  devices" (`revoke_devices`), deactivating the user, a role change (both via `revoke_devices`), and a
  password change (`ChangePasswordView`, other devices). One helper does it, so the four stay the same.
- Users page "phone" state (`UserViewSet.phone`) also counts held signed-out devices: "Signed out ·
  still holds 2 drafts, 5 files".
- Logging: `auth.signed_out_holding_work` (info, counts only); `auth.device_taken_over` (info).
- Migration additive and reversible. Accounts 100% branch gate holds. Tests: same install back in;
  another phone refused; offline sign-out then same install; each of the four releases; another
  person's sign-in on the same phone unaffected; old app without `install_id` / counts as today;
  bad `install_id` refused with a code.

## Android, part A: sign-out keeps the work (≈ 1.5 days)
- `TokenStore`: `installId()` in plain prefs (survives sign-out; gone on uninstall or Clear storage,
  which is right). Sent on sign-in.
- `AppViewModel.signOut`: no block on unsent drafts; a confirm dialog naming the leads; logout sends
  the unsent counts; `forgetDrafts(userId, all = false)` (keeps unsent, as the server-revoke path does);
  copies, downloads, notices and tokens cleared as today. Offline: counts are not sent, the takeover
  rule covers it.
- `OutboxWorker` already does nothing without a signed-in person; after sign-in the outbox is kicked
  for that person and the heartbeat sends the counts.
- `forgetOthers` already keeps another person's unsent work at sign-in (N-8): unchanged.
- Stale work after a long sign-out reuses the existing paths (`reconcile`, `takeBack`, "already
  submitted"). Robolectric tests: signed out 3 days while Ops reassigned the booking; same expert
  finished it on another phone after an Admin released the block.
- Existing tests for the sign-out block are rewritten; Roborazzi images for the new dialog recorded on
  purpose.

## Android, part B: backup copies (≈ 2–2.5 days)
- One class, `BackupCopies` (in `core/`, no UI), given the folder and the clock (tests use a temp
  folder and a fake clock). It owns:
  - **copy**: called from one place, `InspectionModel.addFile` (files from the server, `Outbox.kt:181`,
    get no copy). Copies the final kept file (stamped photo, recorded video) off the main thread to a
    temporary name, then renames it (a power cut never leaves half a file). Never overwrites, never
    reuses a number. Names cleaned (no `/`, control characters or emoji; length capped). Writes
    `.nomedia` in `Documents/Vayu` when missing. Phone full or no permission → no copy, the inspection
    carries on, the "Backups are off" / "Backup copy skipped (phone full)" line shows.
  - **index**: a small list in the app's own storage of every copy this install made (path, booking id,
    file id, made at, "server never needs it" at). "Found from an earlier install" = a file in the
    folder that is not in the index (so drafts removed by `forgetDrafts`, `forgetOthers` or `prune`
    never cause a false notice).
  - **clean-up**: one pass, run at app start, after each outbox run and after a discard; applies the
    rules in requirement 3 over all people's drafts on the phone; removes empty booking folders.
- `LocalFile` gets no new field (the index holds the copy's path).
- Permission screen and "Backups are off" line in the expert flow; re-checked when the app comes to
  the front.
- Expert home: the "Found copies from your earlier install" notice until they are deleted.
- Logging: backup copy failed → warning with the reason only; **no file paths in Sentry** (they hold
  booking codes and field names).

## Screens (approved 2026-11-26)
The four new screens are approved as drawn on the "Vayu Android prototype" canvas, page "Proposed:
backup and sign-out": file-access screen, sign-out sheet, "Backups are off" / "Phone is full" line,
"Found copies" notice on My leads. Words and layout follow them.

## Tests and done-when
- Every behaviour above has a test that fails without it (pytest, unit, Robolectric); Kover holds.
- Standards §6 checklists for backend and Android all pass; `openapi.yaml` additive only (oasdiff).
- **On the owner's phone** (≈ ½–1 day): airplane mode → photos → sign out → sign in → uploads finish;
  photos → uninstall → reinstall → turn on file access → notice lists the booking → files are in
  `Documents/Vayu/<code>/`, not in the Gallery, shareable from the Files app → gone 2 days later;
  switch turned off mid-inspection → camera works, red line shows; check how the phone maker's
  settings screen and any auto-reset of special access behave.
- Ops note: never tell an expert to reinstall while photos are unsent; after an uninstall ask for the
  `Documents/Vayu/<code>` folder (sent from the Files app); a new install is refused until an Admin
  signs out the old phone.
- Docs updated: the rule changes above, this plan's status line.

## Order
1. Mock approved (done). 2. Server (additive, merged first). 3. Android part A. 4. Android part B.
5. Phone test.

## Known limits (accepted)
- Uninstall while still signed in: the new install is refused until an Admin signs out the old phone
  (the server can't tell an uninstall from a phone in a drawer).
- Unsent work of a person who never signs in again stays in the app for ever; copies outside the app
  stay until sent and handled as above.
- Copies in `Documents/Vayu` can be read by other apps with storage access on the expert's phone.
- A phone that is lost or broken loses everything not yet uploaded.
