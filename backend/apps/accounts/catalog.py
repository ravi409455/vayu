"""The permission catalog and the default grants of the Ops and Expert roles.

One permission per action. `scoped` permissions can be granted as "own" (assigned to me) or
"all". The Admin role always has everything and is not stored. `grantable=False` permissions
can only ever be held by Admin. Add new permissions here and in a data migration (defaults for
existing roles); never rename a key, it is stored and used by the API.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Perm:
    key: str
    group: str
    label: str
    scoped: bool = False
    grantable: bool = True


CATALOG: list[Perm] = [
    Perm("users.view", "Users", "See the user list"),
    Perm("users.manage", "Users", "Create, edit, deactivate users and reset passwords",
         grantable=False),
    Perm("users.sign_out_devices", "Users", "Sign a user out of all devices"),
    Perm("roles.manage", "Users", "Edit role permissions", grantable=False),
    Perm("audit.view", "Settings", "View the configuration audit log"),
    Perm("master_lists.manage", "Settings", "Edit master lists (cities, reasons, statuses)"),
    Perm("integrations.manage", "Settings", "Manage webhooks and integrations"),
    Perm("api_keys.manage", "Settings", "Manage API keys"),
    Perm("forms.view", "Templates", "View forms and checklists"),
    Perm("forms.edit", "Templates", "Edit form drafts"),
    Perm("forms.publish", "Templates", "Publish form versions"),
    Perm("forms.promote", "Templates", "Promote forms from staging to production"),
    Perm("library.view", "Templates", "View the shared library"),
    Perm("library.edit", "Templates", "Edit the shared library", grantable=False),
    Perm("pdf_templates.view", "Templates", "View PDF report templates"),
    Perm("pdf_templates.edit", "Templates", "Edit and publish PDF report templates"),
    Perm("bookings.view", "Bookings", "View bookings", scoped=True),
    Perm("bookings.create", "Bookings", "Create bookings"),
    Perm("bookings.edit", "Bookings", "Edit booking details", scoped=True),
    Perm("bookings.assign", "Bookings", "Assign or reassign experts"),
    Perm("bookings.reschedule", "Bookings", "Reschedule bookings"),
    Perm("bookings.cancel", "Bookings", "Cancel bookings"),
    Perm("bookings.force_release", "Bookings", "Force-release a started job"),
    Perm("bookings.delete", "Bookings", "Delete bookings (non-Admins: only unassigned drafts)"),
    Perm("submissions.view", "Inspections", "View inspection submissions", scoped=True),
    Perm("submissions.fill", "Inspections", "Fill in and submit inspections", scoped=True),
    Perm("submissions.edit", "Inspections", "Edit submitted inspection data", scoped=True),
    Perm("submissions.delete", "Inspections", "Delete inspection submissions"),
    Perm("media.manage", "Inspections", "Add, replace and delete photos and videos"),
    Perm("media.download", "Inspections", "Download media as ZIP"),
    Perm("payments.record", "Inspections", "Record payments on site", scoped=True),
    Perm("payments.verify", "Inspections", "Verify recorded payments"),
    Perm("ratings.override", "Inspections", "Override suggested ratings and Key Checks"),
    Perm("reports.view", "Reports", "View and download PDF reports", scoped=True),
    Perm("reports.regenerate", "Reports", "Regenerate PDF reports"),
    Perm("dashboards.view", "Reports", "View dashboards"),
    Perm("dashboards.export", "Reports", "Export dashboard data to CSV"),
]
KEYS: dict[str, Perm] = {p.key: p for p in CATALOG}

# Defaults for the roles an Admin can edit. Ops: daily operations only, no templates, no deletes.
DEFAULTS: dict[str, dict[str, str]] = {
    "ops": {k: "all" for k in (
        "users.view", "users.sign_out_devices", "forms.view", "library.view",
        "bookings.view", "bookings.create", "bookings.edit", "bookings.assign",
        "bookings.reschedule", "bookings.cancel", "bookings.force_release", "bookings.delete",
        "submissions.view", "submissions.edit", "media.manage", "media.download",
        "payments.verify", "ratings.override", "reports.view", "reports.regenerate",
        "dashboards.view", "dashboards.export")},
    "expert": {"bookings.view": "own", "submissions.view": "own", "submissions.fill": "own",
               "payments.record": "own"},
}
