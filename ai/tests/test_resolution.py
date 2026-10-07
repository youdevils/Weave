"""
Deterministic ChangeSet v3 resolution (ai.services.resolution) against the
rugby fixture: references, keys, duplicates, representability, policy and
provenance -- every mutation-level check OnyxJar makes without the AI. (Which
evidence an action is traced to is not the resolver's concern: see
ai.tests.test_reconcile_pipeline's TracePolicy tests.)
"""

from ai.services.change_set import ChangeSet
from ai.services.evidence_bundle import EvidenceBundle
from ai.services.operation_definitions import CREATE_POLICY, RECONCILE_POLICY
from ai.services.resolution import resolve_change_set
from ai.services.semantic.index import SemanticModelIndex
from ai.tests.rugby import FLYER_ASSETS, RugbyFixture


def codes(resolution):
    return [issue.code for issue in resolution.issues]


class ResolutionTestCase(RugbyFixture):

    def setUp(self):
        super().setUp()
        self.bundle = EvidenceBundle.from_assets(FLYER_ASSETS)

    def resolve(self, actions, *, policy=RECONCILE_POLICY):
        return resolve_change_set(
            ChangeSet.model_validate({"actions": actions}),
            model=self.model,
            index=SemanticModelIndex.load(self.model),
            policy=policy,
            bundle=self.bundle,
        )


class HappyPathResolutionTests(ResolutionTestCase):

    def test_full_chain_resolves_cleanly(self):
        resolution = self.resolve(self.chain_actions())

        self.assertEqual(resolution.issues, [])
        self.assertTrue(resolution.specs)

    def test_new_tokens_are_minted_once_and_reused_by_every_reference(self):
        resolution = self.resolve(self.chain_actions())

        stage_id = resolution.ref_map.tokens["stage"].uuid
        self.assertTrue(any(s["target_type"] == "Relationship" and s["after"]["object_id"] == stage_id for s in resolution.specs))
        self.assertTrue(any(s["target_type"] == "Relationship" and s["after"]["subject_id"] == stage_id for s in resolution.specs))
        self.assertEqual(str(next(s for s in resolution.specs if s["target_type"] == "Object" and s["after"]["name"] == "Pool Stage")["target_id"]), stage_id)

    def test_keys_of_new_entities_are_onyxjar_assigned(self):
        resolution = self.resolve(self.chain_actions())

        venue = next(s for s in resolution.specs if s["target_type"] == "Object" and s["after"]["name"] == "Eden Park")
        self.assertEqual(venue["after"]["key"], "eden_park")

    def test_existing_reference_resolves_by_type_key_and_key(self):
        resolution = self.resolve(self.chain_actions())

        has_stage = next(s for s in resolution.specs if s["target_type"] == "Relationship" and s["after"].get("subject_id") == str(self.tournament.id))
        self.assertEqual(str(has_stage["parent_id"]), str(self.has_stage.id))

    def test_action_provenance_becomes_the_proposal_evidence(self):
        resolution = self.resolve(self.chain_actions())

        eden = resolution.evidence["a9"]
        self.assertIn(("flyer.txt", "", "Eden Park capacity: 50000"), eden)
        self.assertIn(("flyer.txt", "", "Eden Park | Auckland"), eden)

    def test_change_set_v3_carries_no_evidence_pipeline_fields(self):
        fields = set(ChangeSet.model_fields) | {f for action in ChangeSet.model_validate({"actions": self.chain_actions()}).actions for f in type(action).model_fields}

        self.assertFalse(fields & {"candidate_ids", "fact_ids", "basis", "schema_candidate_id", "dispositions"})


class ReferenceTests(ResolutionTestCase):

    def test_unknown_existing_object_is_reported_with_the_action_id(self):
        actions = self.chain_actions()
        actions[1]["subject"] = {"kind": "existing", "type_key": "tournament", "key": "championship_2028"}

        issue = next(i for i in self.resolve(actions).issues if i.code == "unresolvable_reference")
        self.assertEqual(issue.action_id, "a2")

    def test_type_key_used_as_an_object_is_unresolvable(self):
        actions = self.chain_actions()
        actions[1]["subject"] = {"kind": "existing", "type_key": "tournament", "key": "tournament"}

        self.assertIn("unresolvable_reference", codes(self.resolve(actions)))

    def test_unknown_relationship_type_lists_the_valid_keys(self):
        actions = self.chain_actions()
        actions[1]["relationship_type"] = {"kind": "existing", "key": "has_stage:tournament:stage"}

        issue = next(i for i in self.resolve(actions).issues if i.code == "unresolvable_reference")
        self.assertIn("has_stage", issue.message)

    def test_dangling_and_mismatched_tokens(self):
        actions = self.chain_actions()
        actions[1]["object"] = {"kind": "new", "token": "nowhere"}
        actions[3]["relationship_type"] = {"kind": "new", "token": "stage"}

        found = codes(self.resolve(actions))
        self.assertIn("dangling_token", found)
        self.assertIn("token_kind_mismatch", found)

    def test_duplicate_tokens_and_action_ids(self):
        actions = self.chain_actions()
        actions[2]["token"] = "stage"
        actions[3]["action_id"] = "a1"

        found = codes(self.resolve(actions))
        self.assertIn("duplicate_token", found)
        self.assertIn("duplicate_action_id", found)

    def test_relationship_direction_must_match_a_rule(self):
        actions = self.chain_actions()
        actions[3]["subject"], actions[3]["object"] = actions[3]["object"], actions[3]["subject"]

        issue = next(i for i in self.resolve(actions).issues if i.code == "no_matching_rule")
        self.assertEqual(issue.action_id, "a4")
        self.assertIn("stage -> match", issue.message)


class ExistingVersusNewTests(ResolutionTestCase):

    def test_creating_an_existing_entity_is_a_probable_duplicate(self):
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park")

        issue = next(i for i in self.resolve(self.chain_actions()).issues if i.code == "probable_duplicate_of_existing")
        self.assertEqual(issue.action_id, "a9")
        self.assertEqual(issue.ref["key"], "eden_park")

    def test_existing_entity_is_referenced_and_updated_instead(self):
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park", attributes={"capacity": 48000})
        eden = {"kind": "existing", "type_key": "venue", "key": "eden_park"}
        update = {"kind": "update_object", "action_id": "a9", "target": eden, "attributes": [{"key": "capacity", "number_value": 50000}]}

        resolution = self.resolve(self.chain_actions(eden_park=([update], eden)))

        self.assertEqual(resolution.issues, [])
        spec = next(s for s in resolution.specs if s["operation"] == "update")
        self.assertEqual(spec["after"], {"field": "attributes.capacity", "value": 50000})
        self.assertEqual(spec["before"], {"field": "attributes.capacity", "value": 48000})

    def test_an_update_that_changes_nothing_is_rejected(self):
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park", attributes={"capacity": 50000})
        eden = {"kind": "existing", "type_key": "venue", "key": "eden_park"}
        update = {"kind": "update_object", "action_id": "a9", "target": eden, "attributes": [{"key": "capacity", "number_value": 50000}]}

        self.assertIn("empty_update", codes(self.resolve(self.chain_actions(eden_park=([update], eden)))))

    def test_a_retired_match_is_reported_as_inactive_not_silently_duplicated(self):
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park", is_active=False)

        issue = next(i for i in self.resolve(self.chain_actions()).issues if i.action_id == "a9")
        self.assertEqual(issue.code, "inactive_entity")
        self.assertIn("retired", issue.message)

    def test_a_retired_entity_can_be_reactivated_and_connected(self):
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park", is_active=False)
        eden = {"kind": "existing", "type_key": "venue", "key": "eden_park"}
        reactivate = {"kind": "set_active", "action_id": "a9", "active": True, "target": {"entity": "object", "object": eden}}

        resolution = self.resolve(self.chain_actions(eden_park=([reactivate], eden)))

        self.assertEqual(resolution.issues, [])
        spec = next(s for s in resolution.specs if s["operation"] == "update")
        self.assertEqual(spec["after"], {"field": "is_active", "value": True})

    def test_connecting_to_a_retired_entity_without_reactivating_it_is_rejected(self):
        self.make_object(self.model, self.venue_type, name="Eden Park", key="eden_park", is_active=False)
        eden = {"kind": "existing", "type_key": "venue", "key": "eden_park"}

        self.assertIn("inactive_entity", codes(self.resolve(self.chain_actions(eden_park=([], eden)))))

    def test_ambiguous_existing_relationship(self):
        from model.models.object import Object

        qualifying = Object.objects.get(model=self.model, key="qualifying_stage")
        self.make_relationship(self.model, self.has_stage, self.tournament, qualifying)
        update = {
            "kind": "update_relationship", "action_id": "u1", "valid_from": "2027-01-01T00:00:00Z",
            "target": {"relationship_type_key": "has_stage", "subject": self.tournament_ref(),
                       "object": {"kind": "existing", "type_key": "stage", "key": "qualifying_stage"}},
        }

        self.assertIn("ambiguous_relationship_reference", codes(self.resolve([update])))

    def test_an_existing_relationship_is_not_created_again(self):
        qualifying = {"kind": "existing", "type_key": "stage", "key": "qualifying_stage"}
        create = {"kind": "create_relationship", "action_id": "r1", "relationship_type": {"kind": "existing", "key": "has_stage"},
                  "subject": self.tournament_ref(), "object": qualifying}

        self.assertIn("relationship_already_exists", codes(self.resolve([create])))

    def test_two_creates_of_the_same_thing_in_one_change_set(self):
        actions = self.chain_actions()
        duplicate = dict(actions[0], action_id="a1b", token="stage2")

        self.assertIn("duplicate_in_change_set", codes(self.resolve(actions + [duplicate])))


class RepresentabilityTests(ResolutionTestCase):

    def test_unsupported_field_lists_the_types_real_attributes(self):
        actions = self.chain_actions()
        next(a for a in actions if a["action_id"] == "a9")["attributes"].append({"key": "location", "string_value": "Auckland"})

        issue = next(i for i in self.resolve(actions).issues if i.code == "attribute_not_defined")
        self.assertEqual(issue.action_id, "a9")
        self.assertIn("capacity", issue.message)

    def test_value_type_must_match_the_attribute(self):
        actions = self.chain_actions()
        next(a for a in actions if a["action_id"] == "a9")["attributes"] = [{"key": "capacity", "string_value": "50,000"}]

        self.assertIn("attribute_value_type_mismatch", codes(self.resolve(actions)))

    def test_reconcile_may_not_change_the_schema(self):
        create = {"kind": "create_attribute", "action_id": "s1", "token": "loc", "owner_kind": "object_type",
                  "owner": {"kind": "existing", "key": "venue"}, "name": "Location"}

        found = codes(self.resolve(self.chain_actions() + [create]))
        self.assertTrue({"action_not_allowed", "schema_change_not_allowed"} & set(found), found)

    def test_new_object_type_duplicating_an_existing_type_is_rejected(self):
        create = {"kind": "create_type", "action_id": "s1", "token": "v2", "type_kind": "object_type", "name": "Venue"}

        self.assertIn("probable_duplicate_of_existing", codes(self.resolve([create], policy=CREATE_POLICY)))

    def test_create_policy_allows_unrestricted_schema(self):
        actions = [
            {"kind": "create_type", "action_id": "t1", "token": "ref", "type_kind": "object_type", "name": "Referee"},
            {"kind": "create_attribute", "action_id": "t2", "token": "grade", "owner_kind": "object_type",
             "owner": {"kind": "new", "token": "ref"}, "name": "Grade", "data_type": "number"},
            {"kind": "create_object", "action_id": "t3", "token": "r1", "type": {"kind": "new", "token": "ref"},
             "name": "Wayne Barnes", "attributes": [{"attribute_token": "grade", "number_value": 1}]},
        ]

        self.assertEqual(self.resolve(actions, policy=CREATE_POLICY).issues, [])


class ProvenanceAndPolicyTests(ResolutionTestCase):

    def test_a_misquoted_excerpt_is_rejected_on_its_action(self):
        actions = self.chain_actions()
        actions[0]["provenance"] = [{"source_id": "S1", "excerpt": "Pool Stage 2"}]

        issue = next(i for i in self.resolve(actions).issues if i.code == "excerpt_not_found")
        self.assertEqual(issue.action_id, "a1")

    def test_an_over_long_excerpt_is_rejected_not_an_exception(self):
        actions = self.chain_actions()
        actions[0]["provenance"] = [{"source_id": "S1", "excerpt": "x" * 5000}]

        self.assertIn("excerpt_too_long", codes(self.resolve(actions)))

    def test_an_unknown_source_is_rejected(self):
        actions = self.chain_actions()
        actions[0]["provenance"] = [{"source_id": "S9", "excerpt": "Pool Stage"}]

        self.assertIn("unknown_source", codes(self.resolve(actions)))

    def test_hard_delete_is_not_available_to_reconcile(self):
        delete = {"kind": "delete", "action_id": "x1",
                  "target": {"entity": "object", "object": {"kind": "existing", "type_key": "sponsor", "key": "acme_corp"}}}

        issue = next(i for i in self.resolve([delete]).issues if i.code == "action_not_allowed")
        self.assertIn("set_active", issue.message)

    def test_policies_describe_partial_outcome(self):
        self.assertEqual(RECONCILE_POLICY.describe()["partial_outcome"], "allowed")
        self.assertEqual(CREATE_POLICY.describe()["partial_outcome"], "forbidden")
