import uuid

from django.test import override_settings

from account.models import CustomUser
from model.models.model import Model
from model.models.proposal import Proposal
from model.services.proposal.proposal import ProposalService

from ai.services.provider import ProviderError

from assisted.models import AssistedTask, AssistedTaskEvidence
from assisted.services import execution
from assisted.tests.support import (
    AssistedTestCase,
    RaisingProvider,
    ScriptedProvider,
    build_minimal_pdf,
    clarification_result,
    create_object_plan,
    no_change_result,
    unresolved_result,
)


class AssistedExecutionTestCase(AssistedTestCase):

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

    def make_evidence(self, task, *, filename, content, content_type):
        return AssistedTaskEvidence.objects.create(
            task=task,
            original_filename=filename,
            content_type=content_type,
            size_bytes=len(content),
            sha256="0" * 64,
            content=content,
        )


class ClaimTests(AssistedExecutionTestCase):

    def test_claims_a_queued_task(self):
        task = self.make_task()

        claimed = execution.claim(task.id)

        self.assertIsNotNone(claimed)
        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.RUNNING)

    def test_a_non_queued_task_is_a_no_op(self):
        task = self.make_task(status=AssistedTask.Status.RUNNING)

        self.assertIsNone(execution.claim(task.id))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.RUNNING)

    def test_an_unknown_task_is_a_no_op(self):
        self.assertIsNone(execution.claim(uuid.uuid4()))


class RunAndFinishTests(AssistedExecutionTestCase):

    def test_ready_for_review_sets_the_proposal_and_execution(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([create_object_plan(self.object_type.key)]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.READY_FOR_REVIEW)
        self.assertIsNotNone(task.proposal)
        self.assertIsNotNone(task.ai_execution)
        self.assertIsNotNone(task.ready_for_review_at)
        self.assertEqual(task.proposal.status, Proposal.Status.WORKING)
        self.assertEqual(task.proposal.source, Proposal.Source.AI)

    def test_needs_clarification_fails_the_task_without_deleting_a_pending_proposal(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([clarification_result()]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.NEEDS_CLARIFICATION)

    def test_no_change_required_fails_the_task(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([no_change_result()]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.NO_CHANGE_PRODUCED)

    def test_unresolved_fails_the_task(self):
        task = self.make_task()

        with override_settings(AI_MAX_REFINEMENT_CYCLES=1):
            execution.run_and_finish(task.id, provider=ScriptedProvider([unresolved_result()] * 2))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.UNRESOLVED)

    def test_a_provider_error_fails_the_task_and_deletes_the_bootstrap_model(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=RaisingProvider(ProviderError("boom")))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.EXECUTION_FAILED)
        self.assertIsNone(task.model)
        self.assertFalse(Model.objects.filter(id=self.model.id).exists())

    def test_a_non_queued_task_is_a_safe_no_op(self):
        task = self.make_task(status=AssistedTask.Status.READY_FOR_REVIEW)

        # Must not raise, and must not touch an already-finished task.
        execution.run_and_finish(task.id, provider=ScriptedProvider([create_object_plan(self.object_type.key)]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.READY_FOR_REVIEW)

    def test_a_learner_creator_is_rejected_at_the_worker_boundary_without_calling_the_provider(self):
        """
        The worker-side entitlement check is deliberately independent of the
        one in assisted.services.lifecycle.start_assisted_create: it exists
        to catch a queued/forged/stale task whose creator's entitlement is
        no longer (or was never) valid by the time a worker actually picks
        it up -- see assisted.services.execution's module docstring. Uses
        RaisingProvider so the test fails loudly if the provider is ever
        reached despite the entitlement denial.
        """

        self.owner.plan = CustomUser.Plan.LEARNER
        self.owner.save(update_fields=["plan"])

        task = self.make_task()

        execution.run_and_finish(task.id, provider=RaisingProvider(ProviderError("must not be called")))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.ENTITLEMENT_DENIED)
        # CREATE is a bootstrap-model operation: denial cleans up the
        # Model exactly like any other failed Create.
        self.assertIsNone(task.model)
        self.assertFalse(Model.objects.filter(id=self.model.id).exists())

    def test_a_collaborator_creator_is_unaffected_by_the_entitlement_check(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([create_object_plan(self.object_type.key)]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.READY_FOR_REVIEW)

    def test_plain_text_evidence_passes_through_unchanged(self):
        task = self.make_task()
        self.make_evidence(task, filename="notes.txt", content=b"hello evidence", content_type="text/plain")
        provider = ScriptedProvider([create_object_plan(self.object_type.key)])

        execution.run_and_finish(task.id, provider=provider)

        assets = provider.user_payloads[0]["assets"]
        self.assertEqual(assets, [{"name": "notes.txt", "content": "hello evidence", "mime_type": "text/plain"}])

    def test_pdf_evidence_is_extracted_and_bounded_not_raw_decoded(self):
        pdf_bytes = build_minimal_pdf("Quarterly numbers go here")
        task = self.make_task()
        self.make_evidence(task, filename="report.pdf", content=pdf_bytes, content_type="application/pdf")
        provider = ScriptedProvider([create_object_plan(self.object_type.key)])

        with override_settings(ASSISTED_MAX_EVIDENCE_EXTRACTED_CHARS=10):
            execution.run_and_finish(task.id, provider=provider)

        asset = provider.user_payloads[0]["assets"][0]
        # No U+FFFD replacement characters -- real extracted text, not a raw
        # binary-bytes decode -- and bounded to the (deliberately tiny, for
        # this test) per-file character cap, with a truncation indicator.
        self.assertNotIn("�", asset["content"])
        self.assertIn("truncated", asset["content"])
        self.assertLessEqual(len(asset["content"]) - len("\n\n[... evidence truncated at 10 characters]"), 10)


class ReconcileRunAndFinishTests(AssistedExecutionTestCase):
    """
    Unlike Create, Reconcile's Model pre-exists -- these tests use
    operation=RECONCILE throughout and never expect the Model to be deleted
    on failure, and expect NO_CHANGE_REQUIRED/UNRESOLVED/
    NEEDS_USER_CLARIFICATION to reach COMPLETED (via the new
    execution._finish_completed path), never FAILED.
    """

    def make_task(self, **kwargs):
        kwargs.setdefault("operation", AssistedTask.Operation.RECONCILE)
        return super().make_task(**kwargs)

    def test_ready_for_review_still_uses_the_proposal_path(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([create_object_plan(self.object_type.key)]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.READY_FOR_REVIEW)
        self.assertIsNotNone(task.proposal)

    def test_no_change_required_completes_without_a_proposal(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([no_change_result()]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.COMPLETED)
        self.assertIsNone(task.proposal)
        self.assertEqual(task.ai_outcome, "no_change_required")
        self.assertTrue(task.outcome_detail)
        self.assertIsNotNone(task.completed_at)
        # The Model is never a bootstrap artifact for Reconcile -- it must
        # survive regardless of outcome.
        self.assertTrue(Model.objects.filter(id=self.model.id).exists())

    def test_unresolved_completes_without_a_proposal(self):
        task = self.make_task()

        # Reconcile's own OperationDefinition.max_refinement_cycles=5 is
        # fixed and takes priority over the global setting -- unlike
        # Create's equivalent test, overriding AI_MAX_REFINEMENT_CYCLES here
        # would have no effect, so this scripts exactly Reconcile's own budget.
        execution.run_and_finish(task.id, provider=ScriptedProvider([unresolved_result()] * 5))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.COMPLETED)
        self.assertIsNone(task.proposal)
        self.assertEqual(task.ai_outcome, "unresolved")

    def test_needs_clarification_completes_without_a_proposal(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([clarification_result()]))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.COMPLETED)
        self.assertIsNone(task.proposal)
        self.assertEqual(task.ai_outcome, "needs_user_clarification")

    def test_token_usage_is_denormalized_on_the_completed_path(self):
        task = self.make_task()

        execution.run_and_finish(task.id, provider=ScriptedProvider([no_change_result()]))

        task.refresh_from_db()
        self.assertGreater(task.tokens_used, 0)

    def test_proposal_limit_reached_fails_with_a_specific_message(self):
        from django.conf import settings

        for _ in range(settings.PROPOSAL_MAX_LIVE_PER_MODEL):
            ProposalService.create_working(self.model, self.owner)

        task = self.make_task()

        execution.run_and_finish(task.id, provider=RaisingProvider(ProviderError("must not be called")))

        task.refresh_from_db()
        self.assertEqual(task.status, AssistedTask.Status.FAILED)
        self.assertEqual(task.failure_reason_code, AssistedTask.FailureReasonCode.EXECUTION_FAILED)
        self.assertIn("maximum number of open proposals", task.failure_reason)
        # Reconcile's Model is never deleted, unlike Create's bootstrap Model.
        self.assertTrue(Model.objects.filter(id=self.model.id).exists())
