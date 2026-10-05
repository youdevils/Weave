"""
Orchestrator-level coverage for the generic extension points Reconcile is
the first real caller of: OperationDefinition.max_refinement_cycles (an
operation-specific bounded-refinement budget, falling back to the global
settings.AI_MAX_REFINEMENT_CYCLES default), prompt_fragment, and
plan_sufficiency_check (ai.services.evidence_assessment.assess_change_plan).

None of this is reconcile-specific machinery -- run_ai_operation never
branches on operation_id -- but exercising it through the real registered
"reconcile" operation (ai.services.operation_definitions.RECONCILE,
registered at AiConfig.ready()) is also an end-to-end proof that the
registration actually works, not just the orchestrator's generic hooks in
isolation.
"""

from django.test import override_settings

from model.models.proposal import Proposal

from ai.services.change_plan import ChangeAction, ChangePlan, EntityRef, EvidenceAssessment, EvidenceItem
from ai.services.operations import _unregister_operation, register_operation
from ai.services.orchestrator import run_ai_operation
from ai.services.result_schema import (
    AIStructuredResult,
    ContextRequest,
    ExecutionStatus,
    Interpretation,
    OperationOutcome,
)
from ai.tests.support import AIServiceTestCase, ScriptedProvider, fake_operation


def _new(token):
    return EntityRef(kind="new", id=token)


def _existing(id_):
    return EntityRef(kind="existing", id=str(id_))


def _no_change():
    return AIStructuredResult(interpretation=Interpretation(restated_intent="Nothing to do."))


def _create_plan_with_verdict(object_type_id, verdict, token="tmp:1", name="New widget"):
    return AIStructuredResult(
        interpretation=Interpretation(restated_intent="Create a widget."),
        change_plan=ChangePlan(
            summary="Create a widget.",
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new(token),
                    parent_ref=_existing(object_type_id),
                    fields={"name": name},
                    assessment=EvidenceAssessment(verdict=verdict, reasoning="Because the test says so."),
                    evidence=[EvidenceItem(source="notes.txt", note="Supports this.")],
                )
            ],
        ),
    )


def _delete_plan(object_ref, verdict="supported", evidence=(), token_evidence=True):
    return AIStructuredResult(
        interpretation=Interpretation(restated_intent="Retire this object."),
        change_plan=ChangePlan(
            summary="Retire this object.",
            actions=[
                ChangeAction(
                    operation="delete",
                    target_type="Object",
                    target_ref=_existing(object_ref),
                    assessment=EvidenceAssessment(verdict=verdict, reasoning="Because the test says so."),
                    evidence=list(evidence),
                )
            ],
        ),
    )


@override_settings(AI_MAX_REFINEMENT_CYCLES=3)
class RefinementBudgetTests(AIServiceTestCase):
    """
    OperationDefinition.max_refinement_cycles: None falls back to the global
    default (here overridden to 3 to make the contrast unambiguous); an
    explicit value is an operation's own budget, used consistently by every
    refinement-causing branch in run_ai_operation, with no second counter.
    """

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")

    def _bad(self):
        # Schema-valid but fails compile_and_validate's apply step (empty name).
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Try to create a widget."),
            change_plan=ChangePlan(
                summary="",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:bad"),
                        parent_ref=_existing(self.object_type.key),
                        fields={"name": ""},
                    )
                ],
            ),
        )

    def _good(self):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Create a widget."),
            change_plan=ChangePlan(
                summary="Create a widget.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:good"),
                        parent_ref=_existing(self.object_type.key),
                        fields={"name": "New widget"},
                    )
                ],
            ),
        )

    def test_unconfigured_operation_uses_the_global_default(self):
        """Regression guard: resolving the budget must not change Create's
        (or any unconfigured operation's) existing behavior."""
        operation = fake_operation("plain_op")
        register_operation(operation)
        self.addCleanup(_unregister_operation, "plain_op")

        provider = ScriptedProvider([self._bad(), self._bad(), self._bad()])
        result = run_ai_operation(
            operation_id="plain_op", model=self.model, user=self.user,
            intent_text="Do something.", provider=provider,
        )

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertEqual(result.refinement_cycles, 3)
        self.assertEqual(provider.generate_calls, 3)

    def test_operation_specific_budget_allows_more_cycles_than_the_global_default(self):
        """The same 4-bad-then-good script that would exhaust the global
        default of 3 (never reaching the good attempt) succeeds when the
        operation's own budget is 5."""
        operation = fake_operation("generous_op", max_refinement_cycles=5)
        register_operation(operation)
        self.addCleanup(_unregister_operation, "generous_op")

        provider = ScriptedProvider([self._bad(), self._bad(), self._bad(), self._bad(), self._good()])
        result = run_ai_operation(
            operation_id="generous_op", model=self.model, user=self.user,
            intent_text="Do something.", provider=provider,
        )

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 4)
        self.assertEqual(provider.generate_calls, 5)

    def test_the_same_script_exhausts_the_unconfigured_global_default_first(self):
        """Same script as above, against an operation with no budget
        override: proves the earlier success came from the operation's own
        higher budget, not some other difference."""
        operation = fake_operation("plain_op")
        register_operation(operation)
        self.addCleanup(_unregister_operation, "plain_op")

        provider = ScriptedProvider([self._bad(), self._bad(), self._bad(), self._bad(), self._good()])
        result = run_ai_operation(
            operation_id="plain_op", model=self.model, user=self.user,
            intent_text="Do something.", provider=provider,
        )

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertEqual(result.refinement_cycles, 3)
        self.assertEqual(provider.generate_calls, 3)

    def test_operation_specific_budget_still_terminates_deterministically(self):
        """Exactly `max_refinement_cycles` scripted failures and no more --
        proves the operation's own higher budget is still a fixed,
        deterministic cap, not unlimited or self-extending."""
        operation = fake_operation("generous_op", max_refinement_cycles=5)
        register_operation(operation)
        self.addCleanup(_unregister_operation, "generous_op")

        provider = ScriptedProvider([self._bad()] * 5)
        result = run_ai_operation(
            operation_id="generous_op", model=self.model, user=self.user,
            intent_text="Do something.", provider=provider,
        )

        self.assertEqual(result.execution_status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertEqual(result.refinement_cycles, 5)
        self.assertEqual(provider.generate_calls, 5)
        # ScriptedProvider itself would raise AssertionError on a 6th call --
        # the test reaching this line at all is part of the proof there is
        # no path that keeps looping past the cap.

    def test_prompt_fragment_is_appended_to_the_system_prompt(self):
        operation = fake_operation("fragment_op", prompt_fragment="UNIQUE-FRAGMENT-MARKER")
        register_operation(operation)
        self.addCleanup(_unregister_operation, "fragment_op")

        provider = ScriptedProvider([self._good()])
        run_ai_operation(
            operation_id="fragment_op", model=self.model, user=self.user,
            intent_text="Do something.", provider=provider,
        )

        self.assertIn("UNIQUE-FRAGMENT-MARKER", provider.system_prompts[0])


class ReconcilePlanSufficiencyTests(AIServiceTestCase):
    """
    Integration coverage for the real registered "reconcile" operation
    (ai.services.operation_definitions.RECONCILE) and its
    plan_sufficiency_check (ai.services.evidence_assessment.assess_change_plan).
    """

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")

    def _run(self, provider):
        return run_ai_operation(
            operation_id="reconcile", model=self.model, user=self.user,
            intent_text="Reconcile this model with the new documents.", provider=provider,
        )

    def test_reconcile_operation_is_registered(self):
        # If this were unregistered, every test below would fail with
        # UnknownOperation instead of exercising anything meaningful.
        result = self._run(ScriptedProvider([_no_change()]))
        self.assertEqual(result.outcome, OperationOutcome.NO_CHANGE_REQUIRED)

    def test_mixed_supported_and_unsupported_candidates_block_the_whole_plan(self):
        plan = AIStructuredResult(
            interpretation=Interpretation(restated_intent="Two candidates."),
            change_plan=ChangePlan(
                summary="",
                actions=[
                    ChangeAction(
                        operation="create", target_type="Object", target_ref=_new("tmp:a"),
                        parent_ref=_existing(self.object_type.key), fields={"name": "A"},
                        assessment=EvidenceAssessment(verdict="supported"),
                        evidence=[EvidenceItem(source="notes.txt")],
                    ),
                    ChangeAction(
                        operation="create", target_type="Object", target_ref=_new("tmp:b"),
                        parent_ref=_existing(self.object_type.key), fields={"name": "B"},
                        assessment=EvidenceAssessment(verdict="unsupported"),
                    ),
                ],
            ),
        )

        result = self._run(ScriptedProvider([plan] * 5))

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 0)

    def test_conflicting_verdict_never_silently_resolved_and_exhausts_to_unresolved(self):
        conflicting = _create_plan_with_verdict(self.object_type.key, "conflicting")

        result = self._run(ScriptedProvider([conflicting] * 5))

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)
        self.assertEqual(result.refinement_cycles, 5)  # Reconcile's own max_refinement_cycles=5

    def test_absence_is_not_deletion_delete_without_evidence_is_blocked_then_recovers(self):
        existing_object = self.make_object(self.model, self.object_type, name="Old widget", key="old_widget")
        object_ref = f"{self.object_type.key}:{existing_object.key}"

        bad_delete = _delete_plan(object_ref, verdict="supported", evidence=())
        good_delete = _delete_plan(
            object_ref, verdict="supported", evidence=[EvidenceItem(source="notes.txt", note="Retired.")]
        )

        result = self._run(ScriptedProvider([bad_delete, good_delete]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 1)
        self.assertIsNotNone(result.proposal_id)

    def test_supported_candidate_with_evidence_compiles_cleanly(self):
        result = self._run(ScriptedProvider([_create_plan_with_verdict(self.object_type.key, "supported")]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 0)
        self.assertIsNotNone(result.proposal_id)

    def test_reconcile_prompt_fragment_is_present(self):
        provider = ScriptedProvider([_no_change()])
        self._run(provider)

        self.assertIn("authoritative, pre-existing truth", provider.system_prompts[0])


class ContextRequestObjectTypeConfusionTests(AIServiceTestCase):
    """
    Generic reproduction of a real failure mode (not rugby/tournament
    -specific): a response proposes a well-formed create-with-parent_ref
    action for a new instance of an existing ObjectType, but *also* submits
    a context_request wrongly naming that same ObjectType's id as if it
    were an existing Object instance it needs more context about. Proves
    the orchestrator/context_expansion machinery already handles this
    correctly and deterministically -- see ai.services.context_expansion
    .resolve_context_requests and the orchestrator's context_requests
    branch (checked, and consumed, before change_plan is ever read).
    """

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")

    def _run(self, provider):
        return run_ai_operation(
            operation_id="reconcile", model=self.model, user=self.user,
            intent_text="Reconcile this model with the new documents.", provider=provider,
        )

    def _confused_result(self):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Create a widget."),
            context_requests=[
                ContextRequest(
                    reference=_existing(self.object_type.key),
                    reason="Need more context about this widget.",
                )
            ],
            change_plan=ChangePlan(
                summary="Create a widget.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:widget"),
                        parent_ref=_existing(self.object_type.key),
                        fields={"name": "New widget"},
                        assessment=EvidenceAssessment(verdict="supported"),
                        evidence=[EvidenceItem(source="notes.txt")],
                    )
                ],
            ),
        )

    def test_repeated_objecttype_id_confusion_exhausts_deterministically_without_a_proposal(self):
        result = self._run(ScriptedProvider([self._confused_result()] * 5))

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)
        self.assertEqual(result.refinement_cycles, 5)  # Reconcile's own max_refinement_cycles=5
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 0)

    def test_recovers_once_the_context_request_mistake_is_dropped(self):
        corrected = _create_plan_with_verdict(self.object_type.key, "supported")

        result = self._run(ScriptedProvider([self._confused_result(), corrected]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 1)
        self.assertIsNotNone(result.proposal_id)


class ConfirmedAbsenceThenCreateTests(AIServiceTestCase):
    """
    Fix #5's first guidance clause: once a context_request comes back
    unresolved (ai.services.context_expansion.resolve_context_requests
    reporting "unresolvable_context_reference"), that is confirmed-absence
    feedback fed into the next cycle's context as previous_attempt_issues
    (ai.services.context_builder) -- the AI should create the entity on the
    next attempt (given evidence + a covering ObjectType), not keep asking
    about it. Proves the orchestrator/context_expansion plumbing already
    supports exactly this retry pattern end-to-end; the fix itself is prompt
    guidance only, so this is a capability/regression test, not a test of
    the AI's own reasoning.
    """

    def setUp(self):
        self.model = self.make_model()
        self.customer_type = self.make_object_type(self.model, key="customer")

    def _run(self, provider):
        return run_ai_operation(
            operation_id="reconcile", model=self.model, user=self.user,
            intent_text="Reconcile this model with the new documents.", provider=provider,
        )

    def _uncertain_result(self):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Check whether Customer A already exists."),
            context_requests=[
                ContextRequest(
                    reference=_existing("customer:customer_a"),
                    reason="Need to confirm whether Customer A already exists before acting.",
                )
            ],
        )

    def _create_customer_a(self):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Create Customer A."),
            change_plan=ChangePlan(
                summary="Create Customer A.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:customer_a"),
                        parent_ref=_existing(self.customer_type.key),
                        fields={"name": "Customer A"},
                        assessment=EvidenceAssessment(
                            verdict="supported", reasoning="The document explicitly names Customer A."
                        ),
                        evidence=[EvidenceItem(source="document.pdf", note="Names Customer A explicitly.")],
                    )
                ],
            ),
        )

    def test_confirmed_absence_is_fed_back_as_an_unresolved_issue_not_silently_dropped(self):
        result = self._run(ScriptedProvider([self._uncertain_result()] * 5))

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertTrue(
            any(issue.code == "unresolvable_context_reference" for issue in result.unresolved_issues)
        )

    def test_creates_the_entity_once_its_absence_is_confirmed_and_evidence_supports_it(self):
        result = self._run(ScriptedProvider([self._uncertain_result(), self._create_customer_a()]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 1)
        self.assertIsNotNone(result.proposal_id)


class RelationshipTypeRuleAsParentRefConfusionTests(AIServiceTestCase):
    """
    Fix #5's second guidance clause: a Relationship action's parent_ref must
    be its RelationshipType's own key, never the RelationshipTypeRule
    composite ref that governs its endpoints -- even though both strings
    appear together in ontology context (ai.services.ontology_context) and
    the rule's ref is built from that same RelationshipType key.
    validate_change_plan already rejects the Rule composite deterministically
    (parent_domain/_resolves_in_domain resolve a Relationship's parent_ref
    against the relationship_type domain, which a 3-part Rule composite can
    never match) -- confirmed, unchanged by this fix. This is a regression
    guard for that existing behavior plus a proof that a corrected retry
    using the bare RelationshipType key succeeds.
    """

    def setUp(self):
        self.model = self.make_model()
        self.tournament_type = self.make_object_type(self.model, key="tournament")
        self.stage_type = self.make_object_type(self.model, key="stage")
        self.relationship_type = self.make_relationship_type(self.model, key="has_stage")
        self.make_rule(self.relationship_type, self.tournament_type, self.stage_type)
        self.tournament = self.make_object(
            self.model, self.tournament_type, name="2027 Championship", key="championship_2027"
        )
        self.stage = self.make_object(self.model, self.stage_type, name="Pool Stage", key="pool_stage")

    def _run(self, provider):
        return run_ai_operation(
            operation_id="reconcile", model=self.model, user=self.user,
            intent_text="Reconcile this model with the new documents.", provider=provider,
        )

    def _relationship_plan(self, parent_ref_id):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Link the tournament to its stage."),
            change_plan=ChangePlan(
                summary="Link the tournament to its stage.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Relationship",
                        target_ref=_new("tmp:rel"),
                        parent_ref=_existing(parent_ref_id),
                        fields={
                            "subject_ref": _existing(f"{self.tournament_type.key}:{self.tournament.key}"),
                            "object_ref": _existing(f"{self.stage_type.key}:{self.stage.key}"),
                        },
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer states this."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    )
                ],
            ),
        )

    def test_rule_composite_ref_as_parent_ref_is_rejected_then_recovers_with_the_type_key(self):
        rule_ref = f"{self.relationship_type.key}:{self.tournament_type.key}:{self.stage_type.key}"
        confused = self._relationship_plan(rule_ref)
        corrected = self._relationship_plan(self.relationship_type.key)

        result = self._run(ScriptedProvider([confused, corrected]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 1)
        self.assertIsNotNone(result.proposal_id)

    def test_repeated_rule_composite_confusion_exhausts_deterministically_without_a_proposal(self):
        rule_ref = f"{self.relationship_type.key}:{self.tournament_type.key}:{self.stage_type.key}"
        confused = self._relationship_plan(rule_ref)

        result = self._run(ScriptedProvider([confused] * 5))

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)
        self.assertEqual(result.refinement_cycles, 5)  # Reconcile's own max_refinement_cycles=5


class ReconcilePromptGuidanceTests(AIServiceTestCase):
    """
    Direct coverage that Fix #5's two new prompt clauses are actually
    present in RECONCILE_PROMPT_FRAGMENT -- the behavioral tests above prove
    the plumbing those clauses rely on works; this proves the guidance text
    itself ships.
    """

    def setUp(self):
        self.model = self.make_model()

    def test_confirmed_absence_guidance_is_present(self):
        provider = ScriptedProvider([_no_change()])
        run_ai_operation(
            operation_id="reconcile", model=self.model, user=self.user,
            intent_text="Reconcile this model with the new documents.", provider=provider,
        )

        self.assertIn("confirmed absence does not by itself mean stop", provider.system_prompts[0])

    def test_relationship_type_rule_vs_relationship_type_parent_guidance_is_present(self):
        provider = ScriptedProvider([_no_change()])
        run_ai_operation(
            operation_id="reconcile", model=self.model, user=self.user,
            intent_text="Reconcile this model with the new documents.", provider=provider,
        )

        self.assertIn(
            "never itself the parent of a Relationship",
            provider.system_prompts[0],
        )
