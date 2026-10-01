from unittest.mock import patch

from django.test import override_settings

from model.models.proposal import Proposal
from model.models.object import Object
from model.services.proposal.proposal import ProposalLimitReached, ProposalService

from ai.services.change_plan import ChangeAction, ChangePlan, EntityRef
from ai.services.operations import register_operation, _unregister_operation
from ai.services.orchestrator import run_ai_operation
from ai.services.provider import ProviderError
from ai.services.result_schema import (
    AIStructuredResult,
    ExecutionStatus,
    Finding,
    Interpretation,
    OperationOutcome,
    UnresolvedIssue,
)
from ai.tests.support import AIServiceTestCase, RaisingProvider, ScriptedProvider, fake_operation


def _new(token):
    return EntityRef(kind="new", id=token)


def _existing(id_):
    return EntityRef(kind="existing", id=str(id_))


def _clarification():
    return AIStructuredResult(needs_clarification=True, clarification_question="Which widget?")


def _no_change():
    return AIStructuredResult(interpretation=Interpretation(restated_intent="Nothing to do."))


def _no_change_with_issues():
    return AIStructuredResult(
        unresolved_issues=[UnresolvedIssue(code="ambiguous", message="Too ambiguous to act on.")],
    )


def _create_object_plan(object_type_id, name="New widget", token="tmp:1", findings=None):
    return AIStructuredResult(
        interpretation=Interpretation(restated_intent="Create a widget."),
        findings=findings or [],
        change_plan=ChangePlan(
            summary="Create a widget.",
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new(token),
                    parent_ref=_existing(object_type_id),
                    fields={"name": name},
                )
            ],
        ),
    )


def _invalid_create_plan(object_type_id, token="tmp:bad"):
    """Valid structurally (passes validate_change_plan) but fails
    compile_and_validate's apply step (empty name)."""
    return AIStructuredResult(
        interpretation=Interpretation(restated_intent="Try to create a widget."),
        change_plan=ChangePlan(
            summary="",
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new(token),
                    parent_ref=_existing(object_type_id),
                    fields={"name": ""},
                )
            ],
        ),
    )


@override_settings(AI_MAX_REFINEMENT_CYCLES=3, AI_MAX_CONTEXT_EXPANSIONS=2)
class RunAIOperationTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")
        self.operation = fake_operation("test_op")
        register_operation(self.operation)
        self.addCleanup(_unregister_operation, "test_op")

    def _run(self, provider, operation_id="test_op"):
        return run_ai_operation(
            operation_id=operation_id,
            model=self.model,
            user=self.user,
            intent_text="Do something with widgets.",
            provider=provider,
        )

    def test_no_proposal_created_for_needs_clarification(self):
        result = self._run(ScriptedProvider([_clarification()]))

        self.assertEqual(result.outcome, OperationOutcome.NEEDS_USER_CLARIFICATION)
        self.assertIsNone(result.proposal_id)
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 0)

    def test_no_proposal_created_for_no_change_required(self):
        result = self._run(ScriptedProvider([_no_change()]))

        self.assertEqual(result.outcome, OperationOutcome.NO_CHANGE_REQUIRED)
        self.assertIsNone(result.proposal_id)
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 0)

    def test_empty_change_plan_with_unresolved_issues_is_not_no_change_required(self):
        # Every scripted cycle keeps returning the same "empty plan +
        # issues" result until AI_MAX_REFINEMENT_CYCLES is exhausted.
        result = self._run(ScriptedProvider([_no_change_with_issues()] * 4))

        self.assertNotEqual(result.outcome, OperationOutcome.NO_CHANGE_REQUIRED)
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)

    def test_proposal_only_created_on_ready_for_review(self):
        result = self._run(ScriptedProvider([_create_object_plan(self.object_type.id)]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertIsNotNone(result.proposal_id)
        proposal = Proposal.objects.get(id=result.proposal_id)
        self.assertEqual(proposal.status, Proposal.Status.WORKING)
        self.assertEqual(proposal.source, Proposal.Source.AI)

    def test_no_proposal_created_for_unresolved(self):
        bad = _invalid_create_plan(self.object_type.id)
        result = self._run(ScriptedProvider([bad, bad, bad, bad]))

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 0)

    def test_intermediate_refinement_cycles_leave_no_persisted_rows(self):
        bad = _invalid_create_plan(self.object_type.id)
        good = _create_object_plan(self.object_type.id)

        result = self._run(ScriptedProvider([bad, bad, good]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 1)
        self.assertEqual(Object.objects.filter(model=self.model).count(), 0)

    def test_execution_status_completed_with_outcome_unresolved_on_cycle_exhaustion(self):
        bad = _invalid_create_plan(self.object_type.id)
        result = self._run(ScriptedProvider([bad, bad, bad, bad]))

        self.assertEqual(result.execution_status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)

    def test_execution_status_failed_with_outcome_failed_on_provider_error(self):
        result = self._run(RaisingProvider(ProviderError("boom")))

        self.assertEqual(result.execution_status, ExecutionStatus.FAILED)
        self.assertEqual(result.outcome, OperationOutcome.FAILED)
        self.assertIsNone(result.proposal_id)

    def test_no_proposal_created_for_failed(self):
        self._run(RaisingProvider(ProviderError("boom")))

        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 0)

    def test_unexpected_exception_finalises_execution_as_failed_without_leaking_details(self):
        with patch("ai.services.orchestrator.build_context_packet", side_effect=RuntimeError("super-secret-detail")):
            result = self._run(ScriptedProvider([_no_change()]))

        self.assertEqual(result.execution_status, ExecutionStatus.FAILED)
        self.assertEqual(result.outcome, OperationOutcome.FAILED)
        self.assertNotIn("super-secret-detail", result.explanation)

    def test_explain_only_called_for_unresolved_when_setting_enabled(self):
        bad = _invalid_create_plan(self.object_type.id)
        provider = ScriptedProvider([bad, bad, bad, bad])

        with override_settings(AI_FINAL_EXPLANATION_ENABLED=True):
            result = self._run(provider)

        self.assertTrue(provider.explain_called)
        self.assertEqual(result.explanation, provider.explanation)

    def test_explain_only_skipped_when_setting_disabled(self):
        bad = _invalid_create_plan(self.object_type.id)
        provider = ScriptedProvider([bad, bad, bad, bad])

        with override_settings(AI_FINAL_EXPLANATION_ENABLED=False):
            self._run(provider)

        self.assertFalse(provider.explain_called)

    def test_explain_only_not_called_for_needs_clarification(self):
        provider = ScriptedProvider([_clarification()])

        self._run(provider)

        self.assertFalse(provider.explain_called)

    def test_capacity_checked_before_first_provider_call_when_can_produce_proposal(self):
        from django.conf import settings

        for _ in range(settings.PROPOSAL_MAX_LIVE_PER_MODEL):
            ProposalService.create_working(self.model, self.user)

        provider = ScriptedProvider([_no_change()])

        with self.assertRaises(ProposalLimitReached):
            self._run(provider)

        self.assertEqual(provider.generate_calls, 0)

    def test_capacity_not_checked_when_operation_cannot_produce_proposal(self):
        from django.conf import settings

        for _ in range(settings.PROPOSAL_MAX_LIVE_PER_MODEL):
            ProposalService.create_working(self.model, self.user)

        readonly_operation = fake_operation("readonly_op", can_produce_proposal=False)
        register_operation(readonly_operation)
        self.addCleanup(_unregister_operation, "readonly_op")

        result = self._run(ScriptedProvider([_no_change()]), operation_id="readonly_op")

        self.assertEqual(result.outcome, OperationOutcome.NO_CHANGE_REQUIRED)

    def test_findings_on_successful_plan_surfaced_not_discarded(self):
        finding = Finding(message="Note: this is a best guess.", severity="info")
        result = self._run(ScriptedProvider([_create_object_plan(self.object_type.id, findings=[finding])]))

        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0].message, finding.message)

    def test_findings_reflect_only_the_determining_cycle_not_accumulated(self):
        cycle_1 = _invalid_create_plan(self.object_type.id)
        cycle_1.findings = [Finding(message="From cycle 1.")]
        cycle_2 = _create_object_plan(self.object_type.id, findings=[Finding(message="From cycle 2.")])

        result = self._run(ScriptedProvider([cycle_1, cycle_2]))

        self.assertEqual(len(result.findings), 1)
        self.assertEqual(result.findings[0].message, "From cycle 2.")

    def test_proposal_capacity_limit_raises_proposal_limit_reached(self):
        from django.conf import settings

        for _ in range(settings.PROPOSAL_MAX_LIVE_PER_MODEL):
            ProposalService.create_working(self.model, self.user)

        with self.assertRaises(ProposalLimitReached):
            self._run(ScriptedProvider([_no_change()]))
