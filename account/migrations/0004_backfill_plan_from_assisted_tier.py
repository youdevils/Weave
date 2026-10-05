from django.db import migrations

# Fixed, one-way mapping from the old Assisted Tier to the new Plan, per the
# product decision to preserve exactly who currently has Assisted access
# (ENHANCED -> COLLABORATOR) while everyone else becomes the new bottom tier
# (BASIC -> LEARNER), even though this may put some existing BASIC accounts
# over Learner's new Model/Publication limits -- see the pre-migration audit
# recommendation in the Plan/entitlement implementation plan.
_TIER_TO_PLAN = {
    "basic": "learner",
    "enhanced": "collaborator",
}


def backfill_plan(apps, schema_editor):
    CustomUser = apps.get_model("account", "CustomUser")
    for tier, plan in _TIER_TO_PLAN.items():
        CustomUser.objects.filter(assisted_tier=tier).update(plan=plan)


class Migration(migrations.Migration):

    dependencies = [
        ('account', '0003_customuser_plan'),
    ]

    operations = [
        migrations.RunPython(backfill_plan, migrations.RunPython.noop),
    ]
