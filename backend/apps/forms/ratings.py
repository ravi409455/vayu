"""Rating categories name the sections they cover by title, so a renamed section must be renamed
there too or its rating silently stops counting."""
from django.db.models import F

from .models import FormVersion


def rename_section_title(version_id: int, old: str, new: str) -> None:
    version = FormVersion.objects.get(pk=version_id)
    categories = (version.rating_config or {}).get("categories") or []
    if not any(old in (c.get("sections") or []) for c in categories):
        return
    version.rating_config = {**version.rating_config, "categories": [
        {**c, "sections": [new if t == old else t for t in c.get("sections") or []]}
        for c in categories]}
    version.row_version = F("row_version") + 1
    version.save(update_fields=["rating_config", "row_version"])
