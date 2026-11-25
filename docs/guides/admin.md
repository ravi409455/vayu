# Admin guide

For the person who sets Vayu up: users, forms, reports and connections to other systems. Admins use
the **web** only (the Android app is for Ops and experts). Everything below is in the left menu.
Every change here is written to the **Audit log**.

## People

**Add someone** — Users → New user: name, username, role (Expert, Ops or Admin), a first password.
They must choose their own password at first sign-in.

**Someone left** — Users → their row → Deactivate…. Nobody is ever deleted; their past work keeps
their name.

**Forgot password** — Users → their row → Reset password. They choose a new one at next sign-in, and
their phone is signed out.

**Lost phone** — Users → their row → Sign out of every device. Anything on that phone that had not reached
the office is lost (you are warned first).

Five wrong passwords lock that username from that address for 15 minutes; a reset ends the lock.

## Who may do what

Roles & permissions: one row per action (create bookings, edit submissions, override ratings…), one
column per role. For bookings, submissions and reports a permission is **own** (only what is
assigned to that person) or **all**. The Admin column is always full. Integrations, API keys and
editing forms, PDF templates and master lists are Admin-only and cannot be given to another role.

Which **fields** a role sees is separate: it is set on the field, section or page in the form
builder (hidden / view / edit, per stage).

## Master lists

Master lists hold the choices of dropdowns: cities, car make/model, cancel and reschedule reasons,
Ops status, and any list you add. Add an item with a label (the key is made from it and never
changes). Archive an item instead of deleting it: old bookings keep showing it.

## Forms

Forms → open one. There are three kinds: the **booking form** (what Ops fill to make a booking), the
**start and end forms** (what every expert fills at the start and at the end), and one **inspection
form** per inspection type (PDI, Used car, EV…).

1. **Start a new draft.** The live version keeps working while you edit.
2. Add pages (one step of the expert's wizard), sections and fields. Each field has a label, a type,
   helper text, required / required-if, limits, and who sees it at each stage. The **key** is fixed
   once made: reports and integrations use it.
3. **Preview** shows the form as an expert fills it.
4. **Check & publish.** Vayu lists problems first (a rule pointing at a missing field…) and warns
   about fields the PDF template or an integration no longer finds. Publishing cannot be undone.
   Leads already started keep the version they began with.

**Ratings and Key Checks** (inspection forms): rating categories map to sections, with points taken
off per defect severity; Key Checks are yes/no results computed from answers. Experts never see
either; Ops can override them.

**Duplicate** makes a new form from an existing one (library links, ratings, Key Checks and the PDF
template come along).

## Library

Library: fields and sections used by many forms. Add one to a form "linked", and later edits come to
that form as an update. To change it everywhere at once: edit the item, then **Save and update
everywhere**. Vayu shows every form it would change first, and stops if any would get a problem;
tick "Publish automatically after updating" to make the changed forms live in the same step. An item in use can only be archived.

## PDF templates

PDF templates → one template per inspection form, with its own draft → preview → publish. Build the
report from blocks (cover and info grid, tables, ratings, photo grid, text, page break), give each
field its report label, and set the header, footer, watermark and file name. **Preview** with a real
booking before you publish. Shared parts (a header used by several templates) are edited once.

## Integrations and API keys

- **Integrations** send a request to another system when something happens (a booking is created,
  a PDF is ready…). See [the webhook guide](../integrations/webhooks.md).
- **API keys** let another system create and change bookings. Give each key only the forms, fields
  and actions it needs; it is shown once. See [the REST API guide](../integrations/rest-api.md).

## Moving forms from staging to production (Promote)

Forms are built and tried on the staging server. There, Promote → Export downloads a bundle (the
form version, its library items, the master lists it uses by key, and its PDF template); on
production, Promote → Import brings it in **as a draft**, which you then check and publish.

## Settings

Settings: the late-start grace (minutes after the booked time) and the minimum inspection time per
type. Ops can see this page but not change it.
