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

from model.models.proposal import Proposal, ProposalChange

from ai.services.change_plan import (
    ChangeAction,
    ChangePlan,
    EntityRef,
    EvidenceAssessment,
    EvidenceItem,
    UnresolvedIssue,
)
from ai.services.operations import _unregister_operation, register_operation
from ai.services.orchestrator import run_ai_operation
from ai.services.result_schema import (
    AIStructuredResult,
    ContextRequest,
    ExecutionStatus,
    Finding,
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
    Direct coverage that the reasoning-contract guidance text actually
    ships: the EntityRef-mechanics clauses now live in the generic
    _system_prompt (operation-agnostic -- proven present for Create too,
    not just Reconcile), while the four-sources/dependency-closure
    principles live in RECONCILE_PROMPT_FRAGMENT. The behavioral tests
    elsewhere in this module prove the plumbing those clauses rely on
    works; this proves the guidance text itself ships.
    """

    def setUp(self):
        self.model = self.make_model()

    def _system_prompt_for(self, operation_id):
        provider = ScriptedProvider([_no_change()])
        run_ai_operation(
            operation_id=operation_id, model=self.model, user=self.user,
            intent_text="Reconcile this model with the new documents.", provider=provider,
        )
        return provider.system_prompts[0]

    def test_confirmed_absence_guidance_is_present(self):
        self.assertIn(
            "confirmed absence does not by itself mean stop",
            self._system_prompt_for("reconcile"),
        )

    def test_relationship_type_rule_vs_relationship_type_parent_guidance_is_present_for_reconcile(self):
        self.assertIn(
            "never itself the parent of a Relationship",
            self._system_prompt_for("reconcile"),
        )

    def test_entity_ref_mechanics_guidance_is_present_for_create_too(self):
        # R12/R14/R19 are schema-shape facts, not reasoning-about-evidence
        # rules -- they now live in the generic _system_prompt so every
        # operation (including Create) benefits, not just Reconcile.
        prompt = self._system_prompt_for("create")

        self.assertIn("never itself the parent of a Relationship", prompt)
        self.assertIn("never use a type's key as an existing-kind EntityRef", prompt)
        self.assertIn("treat that as proof the reference itself was wrong", prompt)

    def test_dependency_closure_guidance_is_reconcile_only(self):
        # The four-sources/dependency-closure principles are genuine
        # reasoning-about-evidence content, scoped to Reconcile -- Create
        # never receives them.
        self.assertNotIn("Dependency closure (recursive", self._system_prompt_for("create"))
        self.assertIn("Dependency closure (recursive", self._system_prompt_for("reconcile"))


class RugbyDependencyClosureTests(AIServiceTestCase):
    """
    Pressure-tests the reasoning contract's dependency-closure principle
    (RECONCILE_PROMPT_FRAGMENT's "Dependency closure" paragraph) against a
    full three-hop mandatory chain: Tournament -has_stage-> Stage
    -has_match-> Match -has_team-> Team x2, -played_at-> Venue. Covers the
    brief's cases A-H plus an anti-overreach check (a pre-existing,
    already-valid, unrelated Sponsor this reconciliation never touches).

    The fixture's own Tournament is given a complete, already-valid chain
    in setUp (created directly, not via the AI) rather than left bare:
    model.services.validation.cardinality.validate_cardinality runs
    model-wide on every single compile_and_validate attempt, unconditional
    on what a given cycle's ChangePlan actually touches -- a bare
    pre-existing Tournament with zero Stages would make has_stage's
    object_minimum=1 fail *every* test in this class regardless of intent,
    which is not a real reachable state anyway (the same whole-model check
    would have blocked whatever proposal first added that Tournament
    without a Stage). Cases below that need a *missing* dependency (G, H)
    introduce a second, brand-new branch under this same valid baseline,
    rather than ever leaving the baseline itself invalid.

    Like every other test in this module, these script the *desired*
    post-fix behavior and prove the orchestrator's existing plumbing
    carries it through to the right outcome -- they are capability/
    regression tests, not proof the real model always reasons this way.

    Case H (refinement feedback treated as new knowledge) is additionally,
    and more simply, covered end-to-end by
    ai.tests.test_refinement_feedback_leak.CardinalityViolationLeakTests
    (a single, non-chained cardinality rule) -- this class's own Case H
    test exercises the same principle two hops deep in the chain instead
    of one, which only this fixture can demonstrate.
    """

    def setUp(self):
        self.model = self.make_model()
        self.tournament_type = self.make_object_type(self.model, key="tournament")
        self.stage_type = self.make_object_type(self.model, key="stage")
        self.match_type = self.make_object_type(self.model, key="match")
        self.team_type = self.make_object_type(self.model, key="team")
        self.venue_type = self.make_object_type(self.model, key="venue")
        self.sponsor_type = self.make_object_type(self.model, key="sponsor")

        self.has_stage = self.make_relationship_type(self.model, key="has_stage")
        self.has_match = self.make_relationship_type(self.model, key="has_match")
        self.has_team = self.make_relationship_type(self.model, key="has_team")
        self.played_at = self.make_relationship_type(self.model, key="played_at")
        # Sponsors is a real, optional relationship type (object_minimum=0,
        # the make_rule default) -- a Tournament is never required to have
        # one. Used only by the anti-overreach test below to prove Reconcile
        # doesn't invent a connection to it just because it's visible in
        # context.
        self.sponsors = self.make_relationship_type(self.model, key="sponsors")
        self.make_rule(self.sponsors, self.tournament_type, self.sponsor_type)

        self.make_attribute_definition(object_type=self.venue_type, key="capacity", data_type="number")

        self.has_stage_rule = self.make_rule(self.has_stage, self.tournament_type, self.stage_type, object_minimum=1)
        self.has_match_rule = self.make_rule(self.has_match, self.stage_type, self.match_type, object_minimum=1)
        self.has_team_rule = self.make_rule(self.has_team, self.match_type, self.team_type, object_minimum=2)
        self.played_at_rule = self.make_rule(self.played_at, self.match_type, self.venue_type, object_minimum=1)

        self.tournament = self.make_object(
            self.model, self.tournament_type, name="2027 Championship", key="championship_2027"
        )
        # A complete, already-valid pre-existing chain for self.tournament --
        # see the class docstring for why this can't be left bare.
        self.existing_stage = self.make_object(self.model, self.stage_type, name="Qualifying Stage", key="qualifying_stage")
        self.existing_match = self.make_object(self.model, self.match_type, name="Qualifier Match", key="qualifier_match")
        self.existing_team_a = self.make_object(self.model, self.team_type, name="Qualifier Team A", key="qualifier_team_a")
        self.existing_team_b = self.make_object(self.model, self.team_type, name="Qualifier Team B", key="qualifier_team_b")
        self.existing_venue = self.make_object(self.model, self.venue_type, name="Qualifier Venue", key="qualifier_venue")
        self.make_relationship(self.model, self.has_stage, self.tournament, self.existing_stage)
        self.make_relationship(self.model, self.has_match, self.existing_stage, self.existing_match)
        self.make_relationship(self.model, self.has_team, self.existing_match, self.existing_team_a)
        self.make_relationship(self.model, self.has_team, self.existing_match, self.existing_team_b)
        self.make_relationship(self.model, self.played_at, self.existing_match, self.existing_venue)

        # A pre-existing, unconnected Sponsor -- visible in context, never
        # mentioned by any test's evidence. Used only by the anti-overreach
        # test below.
        self.sponsor = self.make_object(self.model, self.sponsor_type, name="Acme Corp", key="acme_corp")

    def _run(self, provider):
        return run_ai_operation(
            operation_id="reconcile", model=self.model, user=self.user,
            intent_text="Add the venues and stages listed in the flyer, create any relationships "
                        "that should be associated as well.",
            provider=provider,
        )

    def _tournament_ref(self):
        return _existing(f"{self.tournament_type.key}:{self.tournament.key}")

    def _full_chain_actions(self, *, include_team_b, stage_token="tmp:stage", match_token="tmp:match"):
        """
        The full evidenced Tournament->Stage->Match->{Team x2, Venue}
        chain, as one list of ChangeActions. include_team_b=False omits
        the second Team (and its has_team relationship) to deliberately
        under-supply has_team's object_minimum=2 -- used by Case H to
        force a reactive cardinality failure two hops into the chain.
        """

        actions = [
            ChangeAction(
                operation="create", target_type="Object", target_ref=_new(stage_token),
                parent_ref=_existing(self.stage_type.key), fields={"name": "Pool Stage"},
                assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names this stage."),
                evidence=[EvidenceItem(source="flyer.pdf")],
            ),
            ChangeAction(
                operation="create", target_type="Relationship", target_ref=_new(f"{stage_token}:rel"),
                parent_ref=_existing(self.has_stage.key),
                fields={"subject_ref": self._tournament_ref(), "object_ref": _new(stage_token)},
                assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer states this."),
                evidence=[EvidenceItem(source="flyer.pdf")],
            ),
            ChangeAction(
                operation="create", target_type="Object", target_ref=_new(match_token),
                parent_ref=_existing(self.match_type.key), fields={"name": "Pool Stage - Match 1"},
                assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names this match."),
                evidence=[EvidenceItem(source="flyer.pdf")],
            ),
            ChangeAction(
                operation="create", target_type="Relationship", target_ref=_new(f"{match_token}:rel"),
                parent_ref=_existing(self.has_match.key),
                fields={"subject_ref": _new(stage_token), "object_ref": _new(match_token)},
                assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer states this."),
                evidence=[EvidenceItem(source="flyer.pdf")],
            ),
            ChangeAction(
                operation="create", target_type="Object", target_ref=_new(f"{match_token}:team_a"),
                parent_ref=_existing(self.team_type.key), fields={"name": "Team A"},
                assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names this team."),
                evidence=[EvidenceItem(source="flyer.pdf")],
            ),
            ChangeAction(
                operation="create", target_type="Relationship", target_ref=_new(f"{match_token}:has_team_a"),
                parent_ref=_existing(self.has_team.key),
                fields={"subject_ref": _new(match_token), "object_ref": _new(f"{match_token}:team_a")},
                assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer states this."),
                evidence=[EvidenceItem(source="flyer.pdf")],
            ),
            ChangeAction(
                operation="create", target_type="Object", target_ref=_new(f"{match_token}:venue"),
                parent_ref=_existing(self.venue_type.key),
                fields={"name": "Eden Park", "attributes.capacity": 50000},
                assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names this venue."),
                evidence=[EvidenceItem(source="flyer.pdf")],
            ),
            ChangeAction(
                operation="create", target_type="Relationship", target_ref=_new(f"{match_token}:played_at"),
                parent_ref=_existing(self.played_at.key),
                fields={"subject_ref": _new(match_token), "object_ref": _new(f"{match_token}:venue")},
                assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer states this."),
                evidence=[EvidenceItem(source="flyer.pdf")],
            ),
        ]
        if include_team_b:
            actions += [
                ChangeAction(
                    operation="create", target_type="Object", target_ref=_new(f"{match_token}:team_b"),
                    parent_ref=_existing(self.team_type.key), fields={"name": "Team B"},
                    assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names this team."),
                    evidence=[EvidenceItem(source="flyer.pdf")],
                ),
                ChangeAction(
                    operation="create", target_type="Relationship", target_ref=_new(f"{match_token}:has_team_b"),
                    parent_ref=_existing(self.has_team.key),
                    fields={"subject_ref": _new(match_token), "object_ref": _new(f"{match_token}:team_b")},
                    assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer states this."),
                    evidence=[EvidenceItem(source="flyer.pdf")],
                ),
            ]
        return actions

    def _full_chain_plan(self, **kwargs):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Add the stage, match, teams, and venue from the flyer."),
            change_plan=ChangePlan(
                summary="Add the stage, match, teams, and venue from the flyer.",
                actions=self._full_chain_actions(**kwargs),
            ),
        )

    # -- Case A: existing entity is referenced, not recreated --------------

    def test_case_a_existing_entity_is_referenced_not_recreated(self):
        plan = AIStructuredResult(
            interpretation=Interpretation(restated_intent="Update the tournament's description."),
            change_plan=ChangePlan(
                summary="Update the tournament's description.",
                actions=[
                    ChangeAction(
                        operation="update",
                        target_type="Object",
                        target_ref=self._tournament_ref(),
                        fields={"description": "Rugby World Cup qualifier."},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer states this."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    )
                ],
            ),
        )

        result = self._run(ScriptedProvider([plan]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 0)
        self.assertIsNotNone(result.proposal_id)
        # No second Tournament Object was created to satisfy this update.
        self.assertEqual(
            ProposalChange.objects.filter(
                proposal_id=result.proposal_id, target_type="Object", operation="create",
            ).count(),
            0,
        )

    # -- Case B/C/D: context tri-state --------------------------------------
    #
    # Deliberately uses Sponsor, not Tournament: Tournament itself carries a
    # mandatory dependency (has_stage), so creating a *new* bare Tournament
    # would immediately trip Principle 4's dependency closure -- a separate
    # concern from the context tri-state these three cases are about.
    # Sponsor has no mandatory dependency of its own.

    def _uncertain_sponsor_b(self):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Check whether Sponsor B already exists."),
            context_requests=[
                ContextRequest(
                    reference=_existing(f"{self.sponsor_type.key}:sponsor_b"),
                    reason="Need to confirm whether Sponsor B already exists.",
                )
            ],
        )

    def test_case_b_absence_is_uncertain_so_it_asks_before_guessing(self):
        result = self._run(ScriptedProvider([self._uncertain_sponsor_b()] * 5))

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertTrue(
            any(issue.code == "unresolvable_context_reference" for issue in result.unresolved_issues)
        )

    def test_case_c_confirmed_absence_plus_evidence_creates_it(self):
        create_sponsor_b = AIStructuredResult(
            interpretation=Interpretation(restated_intent="Create Sponsor B."),
            change_plan=ChangePlan(
                summary="Create Sponsor B.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:sponsor_b"),
                        parent_ref=_existing(self.sponsor_type.key),
                        fields={"name": "Sponsor B"},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names it."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    )
                ],
            ),
        )

        result = self._run(ScriptedProvider([self._uncertain_sponsor_b(), create_sponsor_b]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 1)
        self.assertIsNotNone(result.proposal_id)

    def test_case_d_confirmed_absence_without_evidence_invents_nothing(self):
        result = self._run(ScriptedProvider([self._uncertain_sponsor_b(), _no_change()]))

        self.assertEqual(result.outcome, OperationOutcome.NO_CHANGE_REQUIRED)
        self.assertIsNone(result.proposal_id)

    # -- Case E: unmodelled attribute ----------------------------------------

    def test_case_e_primary_unmodelled_attribute_is_proactively_omitted_with_a_finding(self):
        plan = AIStructuredResult(
            interpretation=Interpretation(restated_intent="Add the venue from the flyer."),
            findings=[
                Finding(
                    message="The flyer lists a Location for Eden Park, but Venue has no Location "
                            "attribute -- omitted from this plan.",
                    severity="info",
                )
            ],
            change_plan=ChangePlan(
                summary="Add the venue from the flyer.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:venue"),
                        parent_ref=_existing(self.venue_type.key),
                        fields={"name": "Eden Park", "attributes.capacity": 50000},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names this venue."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    )
                ],
            ),
        )

        result = self._run(ScriptedProvider([plan]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 0)
        self.assertTrue(any("Location" in finding.message for finding in result.findings))

    def test_case_e_secondary_reactive_backstop_still_recovers(self):
        # Unchanged existing behavior for when proactive omission doesn't
        # happen: the deep validation/refinement path is still the backstop.
        invalid = AIStructuredResult(
            interpretation=Interpretation(restated_intent="Add the venue from the flyer."),
            change_plan=ChangePlan(
                summary="Add the venue from the flyer.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:venue"),
                        parent_ref=_existing(self.venue_type.key),
                        fields={"name": "Eden Park", "attributes.location": "Auckland, New Zealand"},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names this venue."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    )
                ],
            ),
        )
        corrected = AIStructuredResult(
            interpretation=Interpretation(restated_intent="Add the venue from the flyer."),
            change_plan=ChangePlan(
                summary="Add the venue from the flyer.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:venue2"),
                        parent_ref=_existing(self.venue_type.key),
                        fields={"name": "Eden Park"},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names this venue."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    )
                ],
            ),
        )

        result = self._run(ScriptedProvider([invalid, corrected]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 1)

    # -- Case F: full recursive chain, fully evidenced -----------------------

    def test_case_f_full_evidenced_chain_is_proposed_in_one_pass(self):
        result = self._run(ScriptedProvider([self._full_chain_plan(include_team_b=True)]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 0)
        self.assertEqual(
            ProposalChange.objects.filter(proposal_id=result.proposal_id, target_type="Object").count(),
            5,  # Stage, Match, Team A, Team B, Venue
        )
        self.assertEqual(
            ProposalChange.objects.filter(proposal_id=result.proposal_id, target_type="Relationship").count(),
            5,  # has_stage, has_match, has_team x2, played_at
        )

    # -- Case G: unevidenced hop, invalidity propagates back up -------------

    def test_case_g_unevidenced_hop_propagates_invalidity_up_the_chain(self):
        # The flyer evidences the Stage and its one Match, but never names
        # any Teams for that Match. has_team's object_minimum=2 can't be
        # met, so the Match is unsafe to propose -- and since it's this
        # Stage's only evidenced Match, the Stage is unsafe to propose too.
        no_teams = AIStructuredResult(
            interpretation=Interpretation(restated_intent="Add the stage and match from the flyer."),
            unresolved_issues=[
                UnresolvedIssue(
                    code="missing_mandatory_dependency",
                    message="Match 'Pool Stage - Match 1' requires at least 2 Team relationships "
                            "(has_team), but the flyer does not name any teams for this match -- "
                            "the Stage and Match that depend on it are not included.",
                )
            ],
        )

        result = self._run(ScriptedProvider([no_teams] * 5))

        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertIsNone(result.proposal_id)
        self.assertEqual(len(result.unresolved_issues), 1)
        self.assertIn("has_team", result.unresolved_issues[0].message)

    # -- Anti-overreach: an unrelated, already-valid entity is left alone --

    def test_anti_overreach_unrelated_entity_is_not_touched_just_because_its_in_context(self):
        # self.sponsor exists, is visible in context, and the Sponsors
        # relationship type is a real, satisfiable connection -- but no
        # evidence in this run ever mentions it. A reconciliation scoped to
        # the Tournament's description must not invent a Sponsors
        # relationship just because the connection is structurally possible
        # and the Sponsor happens to be sitting right there in context.
        plan = AIStructuredResult(
            interpretation=Interpretation(restated_intent="Update the tournament's description."),
            change_plan=ChangePlan(
                summary="Update the tournament's description.",
                actions=[
                    ChangeAction(
                        operation="update",
                        target_type="Object",
                        target_ref=self._tournament_ref(),
                        fields={"description": "Rugby World Cup qualifier."},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer states this."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    )
                ],
            ),
        )

        result = self._run(ScriptedProvider([plan]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(
            ProposalChange.objects.filter(
                proposal_id=result.proposal_id, parent_id=self.sponsors.id,
            ).count(),
            0,
        )
        self.assertEqual(
            ProposalChange.objects.filter(
                proposal_id=result.proposal_id, parent_id=self.sponsor_type.id,
            ).count(),
            0,
        )

    # -- Case H: refinement feedback is new knowledge, two hops deep --------

    def test_case_h_cardinality_feedback_two_hops_deep_is_treated_as_new_knowledge(self):
        # Cycle 1 under-supplies has_team (only Team A, minimum is 2) --
        # compile_and_validate rejects the whole plan and rolls back
        # everything (nothing is left committed, by design). Cycle 2 must
        # therefore resubmit the entire chain, this time with both Teams.
        under_supplied = self._full_chain_plan(include_team_b=False)
        complete = self._full_chain_plan(include_team_b=True)

        result = self._run(ScriptedProvider([under_supplied, complete]))

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(result.refinement_cycles, 1)
        self.assertEqual(
            ProposalChange.objects.filter(proposal_id=result.proposal_id, target_type="Object").count(),
            5,
        )
