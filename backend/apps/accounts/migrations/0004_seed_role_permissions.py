from django.db import migrations

# Frozen snapshot of the launch defaults (do not import the live catalog: it evolves, migrations
# must not). Later permissions get their own migration.
DEFAULTS = {
    "expert": {
        "bookings.view": "own",
        "payments.record": "own",
        "submissions.fill": "own",
        "submissions.view": "own"
    },
    "ops": {
        "bookings.assign": "all",
        "bookings.cancel": "all",
        "bookings.create": "all",
        "bookings.edit": "all",
        "bookings.force_release": "all",
        "bookings.reschedule": "all",
        "bookings.view": "all",
        "dashboards.export": "all",
        "dashboards.view": "all",
        "forms.view": "all",
        "library.view": "all",
        "media.download": "all",
        "media.manage": "all",
        "payments.verify": "all",
        "ratings.override": "all",
        "reports.regenerate": "all",
        "reports.view": "all",
        "submissions.edit": "all",
        "submissions.view": "all",
        "users.sign_out_devices": "all",
        "users.view": "all"
    }
}


def seed(apps, schema_editor):
    RolePermission = apps.get_model("accounts", "RolePermission")
    for role, grants in DEFAULTS.items():
        for permission, scope in grants.items():
            RolePermission.objects.get_or_create(
                role=role, permission=permission, defaults={"scope": scope})


class Migration(migrations.Migration):
    dependencies = [("accounts", "0003_role_permissions")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
