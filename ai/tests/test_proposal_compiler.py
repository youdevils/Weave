from model.models.evidence_reference import EvidenceReference
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.proposal import ProposalService

from ai.services.change_plan import ChangeAction, ChangePlan, EntityRef, EvidenceItem
from ai.services.proposal_compiler import compile_and_validate, compile_change_plan
from ai.tests.support import AIServiceTestCase, fake_operation


def _existing(id_):
    return EntityRef(kind="existing", id=str(id_))


def _new(token):
    return EntityRef(kind="new", id=token)


class CompileChangePlanTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")
        self.object = self.make_object(self.model, self.object_type, name="Widget 1")
        self.proposal = ProposalService.create_working(
            self.model, self.user, source=Proposal.Source.AI
        )

    def test_compile_create_action_maps_fields_to_single_after_payload(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(self.object_type.id),
                    fields={"name": "New widget", "description": "", "is_active": True},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(len(created), 1)
        change = created[0]
        self.assertEqual(change.operation, ProposalChange.Operation.CREATE)
        self.assertEqual(change.after["name"], "New widget")
        self.assertEqual(str(change.parent_id), str(self.object_type.id))

    def test_compile_update_action_fans_out_to_one_spec_per_field(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(self.object.id),
                    fields={"name": "Renamed", "description": "New description"},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(len(created), 2)
        fields = {c.after["field"] for c in created}
        self.assertEqual(fields, {"name", "description"})

    def test_compile_update_action_populates_before_from_current_canonical_value(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(self.object.id),
                    fields={"name": "Renamed"},
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(created[0].before, {"field": "name", "value": "Widget 1"})

    def test_compile_new_entity_referenced_by_later_action_in_same_plan(self):
        relationship_type = self.make_relationship_type(self.model, key="connects_to")
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:new_obj"),
                    parent_ref=_existing(self.object_type.id),
                    fields={"name": "New widget"},
                ),
                ChangeAction(
                    operation="create",
                    target_type="Relationship",
                    target_ref=_new("tmp:rel"),
                    parent_ref=_existing(relationship_type.id),
                    fields={
                        "subject_id": _existing(self.object.id).model_dump(),
                        "object_id": _new("tmp:new_obj").model_dump(),
                    },
                ),
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        object_change = next(c for c in created if c.target_type == "Object")
        relationship_change = next(c for c in created if c.target_type == "Relationship")

        self.assertEqual(str(relationship_change.after["object_id"]), str(object_change.target_id))

    def test_rationale_is_attached_as_evidence_reference_note(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(self.object.id),
                    fields={"name": "Renamed"},
                    rationale="The intent asked for a rename.",
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        evidence = EvidenceReference.objects.filter(change=created[0])
        self.assertEqual(evidence.count(), 1)
        self.assertEqual(evidence.first().note, "The intent asked for a rename.")
        self.assertEqual(evidence.first().source, "AI")

    def test_rationale_and_explicit_evidence_items_both_attached(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(self.object.id),
                    fields={"name": "Renamed"},
                    rationale="Why I did this.",
                    evidence=[EvidenceItem(source="doc.pdf", locator="p.3", note="Source context.")],
                )
            ]
        )

        created = compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.assertEqual(EvidenceReference.objects.filter(change=created[0]).count(), 2)

    def test_compile_never_calls_submit_proposal_stays_working(self):
        plan = ChangePlan(
            actions=[
                ChangeAction(
                    operation="update",
                    target_type="Object",
                    target_ref=_existing(self.object.id),
                    fields={"name": "Renamed"},
                )
            ]
        )

        compile_change_plan(model=self.model, user=self.user, change_plan=plan, proposal=self.proposal)

        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.status, Proposal.Status.WORKING)


class CompileAndValidateTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model()
        self.object_type = self.make_object_type(self.model, key="widget")
        self.operation = fake_operation()

    def _valid_plan(self, summary="Create a widget."):
        return ChangePlan(
            summary=summary,
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(self.object_type.id),
                    fields={"name": "New widget"},
                )
            ],
        )

    def _invalid_plan(self):
        # An empty name fails validate_object_builtin_fields's pre-check
        # inside _apply_changes -- reported as a ValidationIssue, not a
        # raised exception, so apply_and_validate returns cleanly with
        # issues for compile_and_validate to roll back on.
        return ChangePlan(
            summary="",
            actions=[
                ChangeAction(
                    operation="create",
                    target_type="Object",
                    target_ref=_new("tmp:1"),
                    parent_ref=_existing(self.object_type.id),
                    fields={"name": ""},
                )
            ],
        )

    def test_compile_and_validate_commits_exactly_one_proposal_on_success(self):
        result = compile_and_validate(
            model=self.model, user=self.user, operation=self.operation, change_plan=self._valid_plan()
        )

        self.assertIsNotNone(result.proposal)
        self.assertEqual(result.issues, [])
        self.assertEqual(Proposal.objects.filter(id=result.proposal.id).count(), 1)
        self.assertTrue(result.proposal.changes.exists())

    def test_change_plan_summary_maps_to_proposal_summary_field(self):
        result = compile_and_validate(
            model=self.model,
            user=self.user,
            operation=self.operation,
            change_plan=self._valid_plan(summary="Because the intent asked for it."),
        )

        self.assertEqual(result.proposal.summary, "Because the intent asked for it.")

    def test_successful_attempt_commits_proposal_but_rolls_back_speculative_canonical_writes(self):
        revision_before = self.model.revision

        result = compile_and_validate(
            model=self.model, user=self.user, operation=self.operation, change_plan=self._valid_plan()
        )

        self.assertIsNotNone(result.proposal)
        self.model.refresh_from_db()
        self.assertEqual(self.model.revision, revision_before)
        self.assertEqual(Object.objects.filter(model=self.model).count(), 0)

    def test_failed_attempt_leaves_no_durable_trace(self):
        proposal_count_before = Proposal.objects.count()
        change_count_before = ProposalChange.objects.count()
        evidence_count_before = EvidenceReference.objects.count()
        object_count_before = Object.objects.count()
        revision_before = self.model.revision

        result = compile_and_validate(
            model=self.model, user=self.user, operation=self.operation, change_plan=self._invalid_plan()
        )

        self.assertIsNone(result.proposal)
        self.assertTrue(result.issues)
        self.assertEqual(Proposal.objects.count(), proposal_count_before)
        self.assertEqual(ProposalChange.objects.count(), change_count_before)
        self.assertEqual(EvidenceReference.objects.count(), evidence_count_before)
        self.assertEqual(Object.objects.filter(model=self.model).count(), object_count_before)
        self.model.refresh_from_db()
        self.assertEqual(self.model.revision, revision_before)
