"""Storage objects of files and ZIPs, removed once the change is saved; reports marked out of
date."""


from typing import Any

from apps.core import tasks as core_tasks

from ..models import MediaAsset


def asset_keys(asset: MediaAsset) -> list[str]:
    """Every object one file has in storage: the original, its preview, JPEG and print copies."""
    from apps.reports.render import print_keys

    return [k for k in (asset.key, asset.preview_key, asset.jpeg_key, *print_keys(asset.id)) if k]


def drop_zips(zips_qs: Any) -> None:
    """Cached ZIPs that no longer match go, objects included (F-069), once the change is saved."""
    keys = [k for k in zips_qs.values_list("key", flat=True) if k]
    zips_qs.delete()
    from ..tasks import delete_files

    core_tasks.after_commit(lambda: delete_files.delay(keys))


def report_out_of_date(booking_id: Any) -> None:
    """Something the report shows changed: its PDF is marked out of date (Ops press Regenerate;
    nothing is made again by itself)."""
    from apps.reports.models import Report, mark_out_of_date

    mark_out_of_date(Report.objects.filter(booking_id=booking_id))
