"""
Assisted Create on the staged engine: a single Planning stage in which the AI
authors a ChangeSet v3 directly, checked by the same resolver (including
provenance verification) and commit gate Reconcile's compiled ChangeSets use.
"""

from django.test import override_settings

from model.models.object import Object
from model.models.proposal import Proposal, ProposalChange

from ai.services.orchestrator import run_ai_operation
from ai.services.result_schema import ExecutionStatus, OperationOutcome
from ai.tests.support import AIServiceTestCase, ScriptedProvider, plan


def initial_model_plan():
    new = lambda t: {"kind": "new", "token": t}  # noqa: E731
    return plan([
        {"kind": "create_type", "action_id": "t1", "token": "team", "type_kind": "object_type", "name": "Team"},
        {"kind": "create_type", "action_id": "t2", "token": "player", "type_kind": "object_type", "name": "Player"},
        {"kind": "create_type", "action_id": "t3", "token": "plays_for", "type_kind": "relationship_type", "name": "Plays for"},
        {"kind": "create_attribute", "action_id": "t4", "token": "caps", "owner_kind": "object_type", "owner": new("player"),
         "name": "Caps", "data_type": "number"},
        {"kind": "create_rule", "action_id": "t5", "relationship_type": new("plays_for"), "subject_type": new("player"),
         "object_type": new("team"), "objects_per_subject": {"minimum": 1, "maximum": 1}},
        {"kind": "create_object", "action_id": "o1", "token": "nz", "type": new("team"), "name": "New Zealand",
         "provenance": [{"source_id": "intent", "excerpt": "Track teams"}]},
        {"kind": "create_object", "action_id": "o2", "token": "p1", "type": new("player"), "name": "Ardie Savea",
         "attributes": [{"attribute_token": "caps", "number_value": 100}]},
        {"kind": "create_relationship", "action_id": "o3", "relationship_type": new("plays_for"), "subject": new("p1"), "object": new("nz")},
    ])


class CreateWorkflowTests(AIServiceTestCase):

    def setUp(self):
        self.model = self.make_model()

    def run_create(self, provider, assets=()):
        return run_ai_operation(
            operation_id="create", model=self.model, user=self.user, intent_text="Track teams and players.",
            assets=assets, provider=provider,
        )

    def test_one_planning_call_builds_the_initial_model(self):
        provider = ScriptedProvider([initial_model_plan()])

        result = self.run_create(provider, assets=[{"name": "notes.txt", "content": "New Zealand", "mime_type": "text/plain"}])

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        self.assertEqual(provider.stages, ["planning"])
        changes = ProposalChange.objects.filter(proposal_id=result.proposal_id)
        self.assertEqual(changes.count(), 8)
        player = changes.get(target_type="Object", after__name="Ardie Savea")
        self.assertEqual(player.after["attributes"], {"caps": 100})
        self.assertEqual(Object.objects.filter(model=self.model).count(), 0)
        # Create sees the evidence directly (it has no Discovery stage).
        self.assertEqual(provider.user_payloads[0]["evidence"][0]["text"], "New Zealand")

    def test_create_payload_carries_no_canonical_ids(self):
        provider = ScriptedProvider([initial_model_plan()])

        self.run_create(provider)

        payload = provider.user_payloads[0]
        self.assertNotIn("model_id", payload["model"])
        self.assertEqual(payload["context"]["catalogue"], {"object_types": [], "relationship_types": []})

    def test_invalid_change_set_is_corrected_with_feedback(self):
        broken = plan([
            {"kind": "create_object", "action_id": "o1", "token": "x", "type": {"kind": "existing", "key": "widget"}, "name": "W"},
        ])
        provider = ScriptedProvider([broken, initial_model_plan()])

        result = self.run_create(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        feedback = provider.user_payloads[1]["feedback"]
        self.assertEqual(feedback[0]["code"], "unresolvable_reference")
        self.assertEqual(feedback[0]["action_id"], "o1")

    def test_validation_failure_is_fed_back_by_action(self):
        missing_team = plan([
            {"kind": "create_type", "action_id": "t1", "token": "team", "type_kind": "object_type", "name": "Team"},
            {"kind": "create_type", "action_id": "t2", "token": "player", "type_kind": "object_type", "name": "Player"},
            {"kind": "create_type", "action_id": "t3", "token": "plays_for", "type_kind": "relationship_type", "name": "Plays for"},
            {"kind": "create_rule", "action_id": "t5", "relationship_type": {"kind": "new", "token": "plays_for"},
             "subject_type": {"kind": "new", "token": "player"}, "object_type": {"kind": "new", "token": "team"},
             "objects_per_subject": {"minimum": 1, "maximum": 1}},
            {"kind": "create_object", "action_id": "o2", "token": "p1", "type": {"kind": "new", "token": "player"}, "name": "Ardie Savea"},
        ])
        provider = ScriptedProvider([missing_team, initial_model_plan()])

        result = self.run_create(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        feedback = provider.user_payloads[1]["feedback"]
        self.assertTrue(any(i["code"] == "object_cardinality_minimum" and i["action_id"] == "o2" for i in feedback), feedback)

    @override_settings(AI_CREATE_PLANNING_MAX_CALLS=2)
    def test_budget_is_bounded_and_unresolved(self):
        broken = plan([{"kind": "create_object", "action_id": "o1", "token": "x", "type": {"kind": "existing", "key": "nope"}, "name": "W"}])
        provider = ScriptedProvider([broken, broken])

        result = self.run_create(provider)

        self.assertEqual(result.execution_status, ExecutionStatus.COMPLETED)
        self.assertEqual(result.outcome, OperationOutcome.UNRESOLVED)
        self.assertEqual(provider.generate_calls, 2)
        self.assertFalse(Proposal.objects.filter(model=self.model).exists())

    def test_misquoted_provenance_is_fed_back_by_action(self):
        misquoted = plan([
            {"kind": "create_type", "action_id": "t1", "token": "team", "type_kind": "object_type", "name": "Team",
             "provenance": [{"source_id": "intent", "excerpt": "Track every team in the world"}]},
        ])
        provider = ScriptedProvider([misquoted, initial_model_plan()])

        result = self.run_create(provider)

        self.assertEqual(result.outcome, OperationOutcome.READY_FOR_REVIEW)
        feedback = provider.user_payloads[1]["feedback"]
        self.assertEqual((feedback[0]["code"], feedback[0]["action_id"]), ("excerpt_not_found", "t1"))

    def test_empty_change_set_is_no_change(self):
        result = self.run_create(ScriptedProvider([plan([])]))

        self.assertEqual(result.outcome, OperationOutcome.NO_CHANGE_REQUIRED)

    def test_create_cannot_retire_or_delete(self):
        self.make_object_type(self.model, key="team")
        retire = plan([{"kind": "set_active", "action_id": "x", "active": False,
                        "target": {"entity": "object_type", "type_key": "team"}}])
        provider = ScriptedProvider([retire, plan([])])

        self.run_create(provider)

        self.assertEqual(provider.user_payloads[1]["feedback"][0]["code"], "action_not_allowed")
