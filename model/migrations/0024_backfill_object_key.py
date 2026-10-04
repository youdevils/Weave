from collections import defaultdict

from django.db import migrations
from django.utils.text import slugify

MAX_KEY_LENGTH = 100
FALLBACK = "object"


def _slugify_key(name):
    """Frozen copy of model.services.keys.slugify_key -- a migration must
    not depend on application code that could change after it has run."""

    return slugify(name or "").replace("-", "_")


def _make_unique_key(name, used_keys):
    """Frozen copy of model.services.keys.make_unique_key, with the
    `fallback` behaviour inlined (always "object" here)."""

    base = _slugify_key(name)[:MAX_KEY_LENGTH]
    if not base:
        base = FALLBACK

    if base not in used_keys:
        return base

    suffix = 2
    while True:
        tail = f"_{suffix}"
        candidate = base[:MAX_KEY_LENGTH - len(tail)] + tail
        if candidate not in used_keys:
            return candidate
        suffix += 1


def backfill_object_keys(apps, schema_editor):
    Object = apps.get_model("model", "Object")

    rows = Object.objects.filter(key__isnull=True).order_by(
        "model_id", "object_type_id", "created_at", "id"
    ).values("id", "model_id", "object_type_id", "name")

    used_by_scope = defaultdict(set)
    to_update = []

    for row in rows:
        scope = (row["model_id"], row["object_type_id"])
        used = used_by_scope[scope]
        key = _make_unique_key(row["name"], used)
        used.add(key)
        to_update.append(Object(id=row["id"], key=key))

    for start in range(0, len(to_update), 1000):
        Object.objects.bulk_update(to_update[start:start + 1000], ["key"])


def clear_object_keys(apps, schema_editor):
    Object = apps.get_model("model", "Object")
    Object.objects.update(key=None)


class Migration(migrations.Migration):

    dependencies = [
        ('model', '0023_object_key'),
    ]

    operations = [
        migrations.RunPython(backfill_object_keys, clear_object_keys),
    ]
