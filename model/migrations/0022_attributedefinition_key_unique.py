from collections import Counter

from django.db import migrations, models


def check_no_duplicate_attribute_keys(apps, schema_editor):
    """
    AttributeDefinition.key has never had a DB-level uniqueness constraint
    (app-level validation only -- see model.services.keys). Before adding
    one, confirm no existing data would violate it: silently renaming a
    duplicate here (rather than failing loudly) could orphan references
    to that key inside sibling Object/Relationship `attributes` JSON
    payloads, so this never auto-fixes -- it only reports.
    """

    AttributeDefinition = apps.get_model("model", "AttributeDefinition")

    for parent_field in ("object_type_id", "relationship_type_id"):
        rows = AttributeDefinition.objects.filter(
            **{f"{parent_field}__isnull": False}
        ).values_list(parent_field, "key")

        counts = Counter(rows)
        duplicates = [key for key, count in counts.items() if count > 1]

        if duplicates:
            raise RuntimeError(
                f"Duplicate AttributeDefinition keys found, scoped by {parent_field}: "
                f"{duplicates}. Resolve these manually (they cannot be auto-renamed "
                "without risking orphaned references in Object/Relationship "
                "attribute data) before this migration can add a uniqueness "
                "constraint."
            )


class Migration(migrations.Migration):

    dependencies = [
        ('model', '0021_alter_model_revision'),
    ]

    operations = [
        migrations.RunPython(
            check_no_duplicate_attribute_keys,
            migrations.RunPython.noop,
        ),
        migrations.AddConstraint(
            model_name='attributedefinition',
            constraint=models.UniqueConstraint(condition=models.Q(('object_type__isnull', False)), fields=('object_type', 'key'), name='uniq_attrdef_objecttype_key'),
        ),
        migrations.AddConstraint(
            model_name='attributedefinition',
            constraint=models.UniqueConstraint(condition=models.Q(('relationship_type__isnull', False)), fields=('relationship_type', 'key'), name='uniq_attrdef_relationshiptype_key'),
        ),
    ]
