from datetime import timedelta

from django.test import override_settings
from django.utils import timezone

from account.models import CustomUser
from account.services.entitlement import user_can_run_assisted
from assisted.models import AssistedTask
from assisted.services import execution
from assisted.tests.support import (
    AssistedTestCase,
    ScriptedProvider,
    create_object_plan,
    no_change_result,
)


class AssistedUsageTestCase(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")

    def make_task(self, **kwargs):
        kwargs.setdefault("workspace", self.workspace)
        kwargs.setdefault("creator", self.owner)
        kwargs.setdefault("operation", AssistedTask.Operation.CREATE)
        kwargs.setdefault("model", self.model)
        kwargs.setdefault("status", AssistedTask.Status.QUEUED)
        kwargs.setdefault("submitted_intent", "Track widgets.")
        return AssistedTask.objects.create(**kwargs)


class TokensUsedDenormalizationTests(AssistedUsageTestCase):
    """
    AssistedTask.tokens_used is a denormalized copy of
    AIExecution.usage["total_tokens"], captured at finish time so it
    survives a FAILED Create's bootstrap-Model (and therefore AIExecution)
    deletion -- see assisted.services.cleanup.fail_task.
    """

    def test_tokens_used_is_recorded_on_a_successful_run(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([create_object_plan(self.object_type.id)]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.READY_FOR_REVIEW)
        self.assertEqual(task.tokens_used, 1)

    def test_tokens_used_is_recorded_on_a_failed_run_despite_bootstrap_model_deletion(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([no_change_result()]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertIsNone(task.model)  # bootstrap Model was deleted
        self.assertEqual(task.tokens_used, 1)

    def test_tokens_used_stays_zero_when_entitlement_is_denied_before_any_ai_call(self):
        self.owner.plan = CustomUser.Plan.LEARNER
        self.owner.save(update_fields=["plan"])
        task = self.make_task()

        execution.run_and_finish(task.id, provider=None)

        task.refresh_from_db()
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.ENTITLEMENT_DENIED)
        self.assertEqual(task.tokens_used, 0)


class AssistedTokenAllowanceTests(AssistedUsageTestCase):
    """
    account.services.entitlement.user_can_run_assisted incorporates a
    Collaborator-only monthly token allowance (settings.ASSISTED_TOKEN_LIMIT_COLLABORATOR),
    aggregated from AssistedTask.tokens_used for tasks created this calendar month.
    """

    def test_unlimited_by_default(self):
        for _ in range(5):
            task = self.make_task(model=self.make_model(name="M-extra"), status=AssistedTask.Status.COMPLETED)
            task.tokens_used = 1_000_000
            task.save(update_fields=["tokens_used"])

        self.assertTrue(user_can_run_assisted(self.owner))

    @override_settings(ASSISTED_TOKEN_LIMIT_COLLABORATOR=10)
    def test_blocked_once_usage_this_month_reaches_the_limit(self):
        task = self.make_task()
        task.tokens_used = 10
        task.save(update_fields=["tokens_used"])

        self.assertFalse(user_can_run_assisted(self.owner))

    @override_settings(ASSISTED_TOKEN_LIMIT_COLLABORATOR=10)
    def test_allowed_below_the_limit(self):
        task = self.make_task()
        task.tokens_used = 9
        task.save(update_fields=["tokens_used"])

        self.assertTrue(user_can_run_assisted(self.owner))

    @override_settings(ASSISTED_TOKEN_LIMIT_COLLABORATOR=10)
    def test_usage_from_a_previous_month_does_not_count(self):
        task = self.make_task()
        task.tokens_used = 10
        task.created_at = timezone.now() - timedelta(days=45)
        task.save(update_fields=["tokens_used", "created_at"])

        self.assertTrue(user_can_run_assisted(self.owner))

    @override_settings(ASSISTED_TOKEN_LIMIT_COLLABORATOR=10)
    def test_a_non_collaborator_plan_is_unaffected_by_the_token_limit(self):
        self.owner.plan = CustomUser.Plan.LEARNER
        self.owner.save(update_fields=["plan"])

        self.assertFalse(user_can_run_assisted(self.owner))
