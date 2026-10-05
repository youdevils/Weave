"""
Regression coverage for the canonical-UUID leak into AI-facing refinement
feedback (ContextPacket.previous_attempt_issues) -- see
ai.services.context_builder._issue_to_dict. Exercises the real, full path
end-to-end:

    AI ChangePlan -> internal UUID resolution -> validation failure
    -> refinement feedback -> next AI context

for both leak sources identified while tracing the bug: the compiler-level
ai.services.proposal_compiler.InvalidFieldError (a ValidationIssue carrying
an already-resolved real UUID), and the deep, AI-unaware validation
machinery apply_and_validate shares with human-authored Proposal review
(model.services.validation.cardinality, operating purely on real canonical
ids by the time it ever runs).
"""

from __future__ import annotations

import re

from ai.services.change_plan import ChangeAction, ChangePlan, EntityRef, EvidenceAssessment, EvidenceItem
from ai.services.orchestrator import run_ai_operation
from ai.services.result_schema import AIStructuredResult, Interpretation, OperationOutcome
from ai.tests.support import AIServiceTestCase, ScriptedProvider

_UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.IGNORECASE)


def _new(token):
    return EntityRef(kind="new", id=token)


def _existing(id_):
    return EntityRef(kind="existing", id=str(id_))


def _no_uuid_anywhere(value) -> bool:
    """
    Recursively confirms no string anywhere under `value` contains a
    UUID-shaped substring. Callers deliberately scope this to
    previous_attempt_issues alone, never the whole context packet: objects'
    /relationships' own raw id/model_id fields are pre-existing, intentional,
    unrelated-to-this-bug content (their AI-usable reference is the separate
    ref/typeKey field the semantic-key architecture added) -- a blanket scan
    over the whole payload would wrongly flag those too.
    """

    if isinstance(value, str):
        return not _UUID_RE.search(value)
    if isinstance(value, dict):
        return all(_no_uuid_anywhere(v) for v in value.values())
    if isinstance(value, list):
        return all(_no_uuid_anywhere(v) for v in value)
    return True


class InvalidFieldLeakTests(AIServiceTestCase):
    """
    ai.services.proposal_compiler.InvalidFieldError's ValidationIssue always
    carries a real, already-resolved canonical UUID in target_id (set from
    TempRefResolver.resolve(...)'s return value at the point the error is
    raised -- confirmed by direct read of compile_change_plan). Proves it
    never reaches the next cycle's AI-facing context.
    """

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")

    def _run(self, provider):
        return run_ai_operation(
            operation_id="reconcile", model=self.model, user=self.user,
            intent_text="Reconcile this model with the new documents.", provider=provider,
        )

    def _illegal_field_plan(self):
        # "location" is not a legal Object field (model.services.entity_fields
        # .OBJECT_PROPERTY_FIELDS is {"name", "description"}) -- triggers
        # InvalidFieldError inside compile_change_plan.
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Create a widget with a location."),
            change_plan=ChangePlan(
                summary="Create a widget.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:widget"),
                        parent_ref=_existing(self.object_type.key),
                        fields={"name": "New widget", "location": "North Wing"},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The notes say so."),
                        evidence=[EvidenceItem(source="notes.txt")],
                    )
                ],
            ),
        )

    def _corrected_plan(self):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Create a widget."),
            change_plan=ChangePlan(
                summary="Create a widget.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:widget2"),
                        parent_ref=_existing(self.object_type.key),
                        fields={"name": "New widget"},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The notes say so."),
                        evidence=[EvidenceItem(source="notes.txt")],
                    )
                ],
            ),
        )

    def test_invalid_field_errors_resolved_uuid_never_leaks_into_the_retry_context(self):
        provider = ScriptedProvider([self._illegal_field_plan(), self._corrected_plan()])

        result = self._run(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(provider.generate_calls, 2)

        retry_payload = provider.user_payloads[1]
        issues = retry_payload["previous_attempt_issues"]
        self.assertTrue(issues)
        self.assertTrue(any("location" in issue.get("message", "") for issue in issues))
        self.assertTrue(_no_uuid_anywhere(issues))
        self.assertTrue(all("target_id" not in issue for issue in issues))


class CardinalityViolationLeakTests(AIServiceTestCase):
    """
    The deep validation layer apply_and_validate shares with human-authored
    Proposal review (model.services.validation.cardinality) raises
    ValidationIssues carrying a real canonical Object.id in target_id, by
    design -- it is entirely unaware an AI consumer exists. Proves this
    second, independent leak source is caught by the same fix (the
    translation boundary, not the validator itself).
    """

    def setUp(self):
        self.model = self.make_model()
        self.tournament_type = self.make_object_type(self.model, key="tournament")
        self.stage_type = self.make_object_type(self.model, key="stage")
        self.relationship_type = self.make_relationship_type(self.model, key="has_stage")
        self.make_rule(
            self.relationship_type, self.tournament_type, self.stage_type,
            object_minimum=1,  # every Tournament must have at least one Stage
        )

    def _run(self, provider):
        return run_ai_operation(
            operation_id="reconcile", model=self.model, user=self.user,
            intent_text="Reconcile this model with the new documents.", provider=provider,
        )

    def _tournament_without_a_stage(self):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Create the tournament."),
            change_plan=ChangePlan(
                summary="Create the tournament.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:tournament"),
                        parent_ref=_existing(self.tournament_type.key),
                        fields={"name": "2027 Championship"},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names it."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    )
                ],
            ),
        )

    def _tournament_with_a_stage(self):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Create the tournament and its stage."),
            change_plan=ChangePlan(
                summary="Create the tournament and its stage.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:tournament2"),
                        parent_ref=_existing(self.tournament_type.key),
                        fields={"name": "2027 Championship"},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names it."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    ),
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=_new("tmp:stage"),
                        parent_ref=_existing(self.stage_type.key),
                        fields={"name": "Pool Stage"},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer names it."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    ),
                    ChangeAction(
                        operation="create",
                        target_type="Relationship",
                        target_ref=_new("tmp:rel"),
                        parent_ref=_existing(self.relationship_type.key),
                        fields={"subject_ref": _new("tmp:tournament2"), "object_ref": _new("tmp:stage")},
                        assessment=EvidenceAssessment(verdict="supported", reasoning="The flyer states this."),
                        evidence=[EvidenceItem(source="flyer.pdf")],
                    ),
                ],
            ),
        )

    def test_cardinality_violations_canonical_object_id_never_leaks_into_the_retry_context(self):
        provider = ScriptedProvider([self._tournament_without_a_stage(), self._tournament_with_a_stage()])

        result = self._run(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(provider.generate_calls, 2)

        retry_payload = provider.user_payloads[1]
        issues = retry_payload["previous_attempt_issues"]
        self.assertTrue(issues)
        self.assertTrue(any("minimum" in issue.get("message", "") for issue in issues))
        self.assertTrue(_no_uuid_anywhere(issues))
        self.assertTrue(all("target_id" not in issue for issue in issues))
