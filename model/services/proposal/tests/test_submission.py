import uuid
from unittest.mock import patch

from django.test import TestCase

from account.models import CustomUser
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.services.proposal import submission
from model.services.proposal.proposal import ProposalService
from workspace.models import Workspace


def _drain(model_id):
    """
    Simulate what the Celery task chain does, without touching Celery:
    repeatedly claim and process the next queued proposal for a Model
    until nothing is left to claim.
    """

    while True:
        proposal = submission.claim_next(model_id)

        if proposal is None:
            return

        submission.process(proposal.id)


class SubmissionTestCase(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.user = CustomUser.objects.create_user(
            email="submitter@example.com",
            password="test-password",
        )

    def _new_model(self, name="Test Model", revision=1):
        return Model.objects.create(
            workspace=self.workspace,
            name=name,
            revision=revision,
        )

    def _submit_object_type_create(self, model, key, user=None):
        """
        Build a working proposal containing a single ObjectType CREATE
        change and submit it. Returns (proposal, object_type_id).
        """

        proposal = ProposalService.get_or_create_working(model, user or self.user)

        object_type_id = uuid.uuid4()

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType",
            target_id=object_type_id,
            parent_type="Model",
            parent_id=model.id,
            before=None,
            after={
                "name": key.title(),
                "key": key,
                "description": "",
                "sort_order": 0,
                "is_active": True,
            },
        )

        ProposalService.submit(proposal)

        return proposal, object_type_id


class QueueOrderingTests(SubmissionTestCase):

    def test_serial_processing_for_one_model(self):
        model = self._new_model(revision=1)

        proposal_1, object_type_1 = self._submit_object_type_create(model, "alpha")
        proposal_2, object_type_2 = self._submit_object_type_create(
            model,
            "beta",
            user=CustomUser.objects.create_user(
                email="second@example.com", password="test-password"
            ),
        )
        proposal_3, object_type_3 = self._submit_object_type_create(
            model,
            "gamma",
            user=CustomUser.objects.create_user(
                email="third@example.com", password="test-password"
            ),
        )

        _drain(model.id)

        for proposal in (proposal_1, proposal_2, proposal_3):
            proposal.refresh_from_db()
            self.assertEqual(proposal.status, Proposal.Status.COMPLETED)

        model.refresh_from_db()
        self.assertEqual(model.revision, 4)

        self.assertTrue(ObjectType.objects.filter(id=object_type_1, key="alpha").exists())
        self.assertTrue(ObjectType.objects.filter(id=object_type_2, key="beta").exists())
        self.assertTrue(ObjectType.objects.filter(id=object_type_3, key="gamma").exists())

    def test_independent_models_process_independently(self):
        model_a = self._new_model(name="Model A", revision=1)
        model_b = self._new_model(name="Model B", revision=1)

        proposal_a, object_type_a = self._submit_object_type_create(model_a, "alpha")
        proposal_b, object_type_b = self._submit_object_type_create(model_b, "beta")

        claimed_a = submission.claim_next(model_a.id)
        self.assertEqual(claimed_a.id, proposal_a.id)

        # Model B's queue is unaffected by Model A's in-flight PROCESSING proposal.
        claimed_b = submission.claim_next(model_b.id)
        self.assertEqual(claimed_b.id, proposal_b.id)

        submission.process(claimed_a.id)
        submission.process(claimed_b.id)

        proposal_a.refresh_from_db()
        proposal_b.refresh_from_db()
        model_a.refresh_from_db()
        model_b.refresh_from_db()

        self.assertEqual(proposal_a.status, Proposal.Status.COMPLETED)
        self.assertEqual(proposal_b.status, Proposal.Status.COMPLETED)
        self.assertEqual(model_a.revision, 2)
        self.assertEqual(model_b.revision, 2)


class ProcessingAgainstCurrentStateTests(SubmissionTestCase):

    def test_revision_advancing_alone_does_not_reject(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")

        # Simulate an unrelated intervening commit: nothing conflicts,
        # only the revision moves.
        model.revision = 5
        model.save(update_fields=["revision"])

        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()
        model.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(model.revision, 6)
        self.assertTrue(ObjectType.objects.filter(id=object_type_id).exists())

    def test_proposal_still_valid_after_intervening_commit_succeeds(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")

        # An unrelated ObjectType lands canonically before this
        # proposal is processed -- no conflict with "alpha".
        ObjectType.objects.create(model=model, name="Beta", key="beta")
        model.revision = 2
        model.save(update_fields=["revision"])

        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertTrue(ObjectType.objects.filter(id=object_type_id, key="alpha").exists())

    def test_a_key_collision_from_an_intervening_commit_is_silently_regenerated(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")

        # A conflicting ObjectType with the same key lands canonically
        # (as if a different proposal committed first) before this one is
        # processed -- validated against CURRENT state, not the state at
        # submit time. ObjectType's key is regenerable (a proposal links
        # by target_id, never by key -- see _REGENERABLE_KEY_TYPES), so
        # this succeeds with a fresh key rather than failing.
        ObjectType.objects.create(model=model, name="Alpha (existing)", key="alpha")
        model.revision = 2
        model.save(update_fields=["revision"])

        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)

        created = ObjectType.objects.get(id=object_type_id)
        self.assertNotEqual(created.key, "alpha")
        self.assertTrue(created.key.startswith("alpha"))

        # The pre-existing canonical row is untouched.
        self.assertTrue(
            ObjectType.objects.filter(name="Alpha (existing)", key="alpha").exists()
        )


class ErrorAttributionTests(SubmissionTestCase):

    def test_errors_attributed_to_correct_proposal_change(self):
        model = self._new_model(revision=1)

        existing = ObjectType.objects.create(model=model, name="Existing", key="existing")

        proposal = ProposalService.get_or_create_working(model, self.user)

        # Keys are immutable once assigned -- an UPDATE of "key" always
        # blocks, regardless of collision, so this is a reliable second
        # defect alongside the Model field error below.
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="ObjectType",
            target_id=existing.id,
            field="key",
            before={"field": "key", "value": "existing"},
            after={"field": "key", "value": "renamed"},
        )

        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=model.id,
            field="not_a_real_field",
            before={"field": "not_a_real_field", "value": "x"},
            after={"field": "not_a_real_field", "value": "y"},
        )

        ProposalService.submit(proposal)
        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.FAILED)

        errors = list(proposal.submission_result.errors.all())
        self.assertEqual(len(errors), 2)

        errors_by_code = {error.code: error for error in errors}

        self.assertEqual(
            errors_by_code["key_immutable"].change.target_id,
            existing.id,
        )
        self.assertEqual(
            errors_by_code["invalid_change"].change.target_type,
            "Model",
        )
        self.assertNotEqual(
            errors_by_code["key_immutable"].change_id,
            errors_by_code["invalid_change"].change_id,
        )


class CommitAtomicityTests(SubmissionTestCase):

    def test_failed_validation_leaves_no_canonical_changes(self):
        model = self._new_model(revision=1)

        object_type = ObjectType.objects.create(model=model, name="Existing", key="existing")
        AttributeDefinition.objects.create(
            object_type=object_type,
            name="Existing attr",
            key="existing_attr",
            data_type="text",
        )

        proposal = ProposalService.get_or_create_working(model, self.user)

        # Unlike ObjectType/RelationshipType, AttributeDefinition's key
        # collision is never silently regenerated (see
        # _REGENERABLE_KEY_TYPES) -- its key is embedded inside sibling
        # Object/Relationship `attributes` JSON, so a collision reliably
        # blocks, which is what this test needs to verify atomicity.
        conflicting_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="AttributeDefinition",
            target_id=conflicting_id,
            parent_type="ObjectType",
            parent_id=object_type.id,
            before=None,
            after={
                "name": "Existing attr (duplicate)",
                "key": "existing_attr",
                "data_type": "text",
                "description": "",
                "required": False,
                "nullable": False,
                "default_value": None,
                "sort_order": 0,
                "config": {},
                "is_active": True,
            },
        )

        ProposalService.submit(proposal)

        attribute_count_before = AttributeDefinition.objects.count()
        revision_before = model.revision

        submission.process(submission.claim_next(model.id).id)

        model.refresh_from_db()

        self.assertEqual(AttributeDefinition.objects.count(), attribute_count_before)
        self.assertEqual(model.revision, revision_before)
        self.assertFalse(AttributeDefinition.objects.filter(id=conflicting_id).exists())

    def test_successful_commit_is_atomic_and_revision_increments_once(self):
        model = self._new_model(revision=1)

        proposal = ProposalService.get_or_create_working(model, self.user)

        object_type_ids = [uuid.uuid4() for _ in range(3)]

        for index, object_type_id in enumerate(object_type_ids):
            ProposalService.record_change(
                proposal=proposal,
                operation=ProposalChange.Operation.CREATE,
                target_type="ObjectType",
                target_id=object_type_id,
                parent_type="Model",
                parent_id=model.id,
                before=None,
                after={
                    "name": f"Type {index}",
                    "key": f"type_{index}",
                    "description": "",
                    "sort_order": 0,
                    "is_active": True,
                },
            )

        ProposalService.submit(proposal)
        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()
        model.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(model.revision, 2)

        for object_type_id in object_type_ids:
            self.assertTrue(ObjectType.objects.filter(id=object_type_id).exists())

    def test_successful_proposal_remains_complete_historical_record(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")
        change_id = proposal.changes.get().id

        submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertTrue(Proposal.objects.filter(id=proposal.id).exists())
        self.assertTrue(ProposalChange.objects.filter(id=change_id).exists())
        self.assertEqual(proposal.changes.count(), 1)

    def test_unexpected_exception_during_commit_rolls_back_and_records_system_error(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")

        revision_before = model.revision
        object_type_count_before = ObjectType.objects.count()

        with patch(
            "model.services.proposal.validation_runner.validate_model",
            side_effect=RuntimeError("super-secret-internal-detail"),
        ):
            submission.process(submission.claim_next(model.id).id)

        proposal.refresh_from_db()
        model.refresh_from_db()

        self.assertEqual(proposal.status, Proposal.Status.FAILED)
        self.assertEqual(model.revision, revision_before)
        self.assertEqual(ObjectType.objects.count(), object_type_count_before)
        self.assertFalse(ObjectType.objects.filter(id=object_type_id).exists())

        result = proposal.submission_result
        self.assertEqual(result.outcome, result.Outcome.SYSTEM_ERROR)
        self.assertNotIn("super-secret-internal-detail", result.message)


class QueueDrainDispatchTests(SubmissionTestCase):

    def test_queue_drain_dispatch_only_follows_durable_commit(self):
        model = self._new_model(revision=1)

        proposal, object_type_id = self._submit_object_type_create(model, "alpha")
        claimed = submission.claim_next(model.id)

        with patch(
            "model.tasks.proposal_tasks.process_next_for_model.delay"
        ) as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                submission.process(claimed.id)

        proposal.refresh_from_db()
        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)

        # Dispatched exactly once, and only after the proposal's
        # final COMPLETED state is what a fresh query would see --
        # i.e. execute=True only ran callbacks from transactions that
        # actually committed within the captured block.
        mock_delay.assert_called_once_with(str(model.id))


class AttributeUpdateApplyTests(SubmissionTestCase):
    """
    "attributes.<key>" UPDATE changes replace one key inside an Object's /
    Relationship's `attributes` JSON. Value rules stay with validate_model.
    """

    def setUp(self):
        self.model = self._new_model(revision=1)

        self.person_type = ObjectType.objects.create(
            model=self.model, name="Person", key="person"
        )
        self.team_type = ObjectType.objects.create(
            model=self.model, name="Team", key="team"
        )
        self.member_of = RelationshipType.objects.create(
            model=self.model, name="Member of", key="member_of"
        )
        RelationshipTypeRule.objects.create(
            relationship_type=self.member_of,
            subject_type=self.person_type,
            object_type=self.team_type,
        )

        DataType = AttributeDefinition.DataType
        self.definitions = {}
        for key, data_type, extra in (
            ("owner", DataType.TEXT, {}),
            ("website", DataType.URL, {}),
            ("grade", DataType.NUMBER, {}),
            ("nickname", DataType.TEXT, {"nullable": True}),
        ):
            self.definitions[key] = AttributeDefinition.objects.create(
                object_type=self.person_type,
                name=key.title(),
                key=key,
                data_type=data_type,
                **extra,
            )

        self.since = AttributeDefinition.objects.create(
            relationship_type=self.member_of,
            name="Since",
            key="since",
            data_type=DataType.DATE,
        )
        self.charter = AttributeDefinition.objects.create(
            relationship_type=self.member_of,
            name="Charter",
            key="charter",
            data_type=DataType.URL,
        )

        self.alice = Object.objects.create(
            model=self.model,
            object_type=self.person_type,
            name="Alice",
            attributes={"owner": "Ops", "website": "https://example.com", "grade": 3},
        )
        self.ops = Object.objects.create(
            model=self.model, object_type=self.team_type, name="Ops"
        )
        self.membership = Relationship.objects.create(
            model=self.model,
            relationship_type=self.member_of,
            subject=self.alice,
            object=self.ops,
            attributes={"since": "2020-01-01", "charter": "https://example.com/c"},
        )

        self.proposal = ProposalService.get_or_create_working(self.model, self.user)

    # -- helpers -------------------------------------------------------------

    def _update(self, target_type, target_id, field, value, canonical=None):
        return ProposalService.record_change(
            proposal=self.proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type=target_type,
            target_id=target_id,
            parent_type="ObjectType" if target_type == "Object" else "RelationshipType",
            parent_id=(
                self.person_type.id if target_type == "Object" else self.member_of.id
            ),
            field=field,
            before={"field": field, "value": canonical},
            after={"field": field, "value": value},
        )

    def _attr(self, key, value, target_id=None):
        return self._update("Object", target_id or self.alice.id, f"attributes.{key}", value)

    def _run(self):
        ProposalService.submit(self.proposal)
        submission.process(submission.claim_next(self.model.id).id)
        self.proposal.refresh_from_db()
        self.model.refresh_from_db()
        self.alice.refresh_from_db()
        self.membership.refresh_from_db()

    def _codes(self):
        return sorted(e.code for e in self.proposal.submission_result.errors.all())

    # -- applying ------------------------------------------------------------

    def test_object_attribute_update_is_applied(self):
        self._attr("owner", "Platform")
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(self.model.revision, 2)
        self.assertEqual(self.alice.attributes["owner"], "Platform")

    def test_relationship_attribute_update_is_applied(self):
        self._update("Relationship", self.membership.id, "attributes.since", "2021-05-06")
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(self.membership.attributes["since"], "2021-05-06")

    def test_unrelated_attributes_are_preserved(self):
        self._attr("owner", "Platform")
        self._run()

        self.assertEqual(
            self.alice.attributes,
            {"owner": "Platform", "website": "https://example.com", "grade": 3},
        )
        self.assertIs(type(self.alice.attributes), dict)

    def test_relationship_update_preserves_other_relationship_attributes(self):
        self._update("Relationship", self.membership.id, "attributes.since", "2022-02-02")
        self._run()

        self.assertEqual(
            self.membership.attributes,
            {"since": "2022-02-02", "charter": "https://example.com/c"},
        )

    def test_multiple_updates_on_one_target_including_a_new_optional_key(self):
        self._attr("owner", "Platform")
        self._attr("grade", 5)
        self._attr("nickname", "Al")
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(
            self.alice.attributes,
            {
                "owner": "Platform",
                "website": "https://example.com",
                "grade": 5,
                "nickname": "Al",
            },
        )

    def test_null_is_stored_when_the_attribute_is_nullable(self):
        self.alice.attributes = {**self.alice.attributes, "nickname": "Al"}
        self.alice.save()

        self._attr("nickname", None)
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.assertIn("nickname", self.alice.attributes)
        self.assertIsNone(self.alice.attributes["nickname"])

    def test_null_is_rejected_by_validation_when_not_nullable(self):
        self._attr("owner", None)
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.FAILED)
        self.assertEqual(self._codes(), ["null_not_allowed"])
        self.assertEqual(self.alice.attributes["owner"], "Ops")

    def test_url_attribute_updates_without_url_format_validation(self):
        for value in ("https://example.org/new", "not a url", "javascript:alert(1)"):
            with self.subTest(value=value):
                proposal = ProposalService.get_or_create_working(self.model, self.user)
                self.proposal = proposal
                self._attr("website", value)
                self._update("Relationship", self.membership.id, "attributes.charter", value)
                self._run()

                self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
                self.assertEqual(self.alice.attributes["website"], value)
                self.assertEqual(self.membership.attributes["charter"], value)

    # -- failures ------------------------------------------------------------

    def test_unknown_attribute_key_is_a_validation_issue_not_a_system_error(self):
        change = self._attr("no_such_key", "x")
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.FAILED)
        result = self.proposal.submission_result
        self.assertEqual(result.outcome, result.Outcome.VALIDATION_FAILED)
        self.assertEqual(self._codes(), ["unknown_attribute"])

        (error,) = result.errors.all()
        self.assertEqual(error.change_id, change.id)
        self.assertEqual(error.field, "no_such_key")
        self.assertNotIn("Unrecognised", error.message)
        self.assertNotIn("no_such_key", self.alice.attributes)

    def test_attribute_of_another_type_is_unknown_for_this_target(self):
        # "since" is defined on the relationship type, not on Person.
        self._attr("since", "2020-01-01")
        self._run()

        self.assertEqual(self._codes(), ["unknown_attribute"])
        self.assertNotIn("since", self.alice.attributes)

    def test_relationship_unknown_attribute_key(self):
        self._update("Relationship", self.membership.id, "attributes.owner", "x")
        self._run()

        self.assertEqual(self._codes(), ["unknown_attribute"])
        self.assertNotIn("owner", self.membership.attributes)

    def test_missing_target_is_reported(self):
        self._attr("owner", "x", target_id=uuid.uuid4())
        self._run()

        self.assertEqual(self._codes(), ["target_not_found"])

    def test_invalid_value_errors_are_attributed_to_their_own_change(self):
        good = self._attr("owner", "Platform")
        bad = self._attr("grade", "not-a-number")
        self._run()

        self.assertEqual(self._codes(), ["invalid_attribute_type"])
        (error,) = self.proposal.submission_result.errors.all()
        self.assertEqual(error.change_id, bad.id)
        self.assertNotEqual(error.change_id, good.id)

    def test_failed_proposal_rolls_back_every_canonical_change(self):
        self._attr("owner", "Platform")
        self._update("Relationship", self.membership.id, "attributes.since", "2030-01-01")
        self._update("Object", self.alice.id, "name", "Renamed")
        self._attr("no_such_key", "x")
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.FAILED)
        self.assertEqual(self.model.revision, 1)
        self.assertEqual(self.alice.name, "Alice")
        self.assertEqual(self.alice.attributes["owner"], "Ops")
        self.assertEqual(self.membership.attributes["since"], "2020-01-01")

    # -- unchanged behaviour ---------------------------------------------------

    def test_direct_field_updates_are_unchanged(self):
        self._update("Object", self.alice.id, "name", "Alicia")
        self._update("Object", self.alice.id, "description", "Lead")
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(self.alice.name, "Alicia")
        self.assertEqual(self.alice.description, "Lead")
        self.assertEqual(self.alice.attributes["owner"], "Ops")

    def test_unknown_direct_field_still_reports_unrecognised_field(self):
        self._update("Object", self.alice.id, "not_a_field", "x")
        self._run()

        self.assertEqual(self._codes(), ["invalid_change"])
        (error,) = self.proposal.submission_result.errors.all()
        self.assertIn("Unrecognised Object field 'not_a_field'", error.message)

    # -- proposal-only data ----------------------------------------------------

    def test_proposed_attribute_definition_and_proposal_created_object(self):
        website_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=self.proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="AttributeDefinition",
            target_id=website_id,
            parent_type="ObjectType",
            parent_id=self.team_type.id,
            before=None,
            after={
                "name": "Homepage",
                "key": "homepage",
                "data_type": "url",
                "description": "",
                "required": False,
                "nullable": False,
                "default_value": None,
                "sort_order": 0,
                "config": {},
                "is_active": True,
            },
        )
        # An existing Team gets a value for the proposed definition.
        self._update("Object", self.ops.id, "attributes.homepage", "https://example.com/ops")
        # A proposal-created Object carries its attributes on its CREATE change.
        new_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=self.proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Object",
            target_id=new_id,
            parent_type="ObjectType",
            parent_id=self.person_type.id,
            before=None,
            after={
                "name": "Bob",
                "description": "",
                "is_active": True,
                "attributes": {"owner": "Ops", "website": "still not validated"},
            },
        )
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.ops.refresh_from_db()
        self.assertEqual(self.ops.attributes, {"homepage": "https://example.com/ops"})
        self.assertEqual(
            Object.objects.get(id=new_id).attributes,
            {"owner": "Ops", "website": "still not validated"},
        )


class RelationshipEndpointUpdateApplyTests(SubmissionTestCase):
    """
    A field-level "subject_id" / "object_id" UPDATE re-points an existing
    Relationship in place. Rules and cardinality are enforced by the same
    validate_model pass as every other change.
    """

    def setUp(self):
        self.model = self._new_model(revision=1)

        self.person_type = ObjectType.objects.create(
            model=self.model, name="Person", key="person"
        )
        self.team_type = ObjectType.objects.create(
            model=self.model, name="Team", key="team"
        )
        self.member_of = RelationshipType.objects.create(
            model=self.model, name="Member of", key="member_of"
        )
        self.rule = RelationshipTypeRule.objects.create(
            relationship_type=self.member_of,
            subject_type=self.person_type,
            object_type=self.team_type,
        )

        self.alice = Object.objects.create(
            model=self.model, object_type=self.person_type, name="Alice"
        )
        self.bob = Object.objects.create(
            model=self.model, object_type=self.person_type, name="Bob"
        )
        self.ops = Object.objects.create(
            model=self.model, object_type=self.team_type, name="Ops"
        )
        self.dev = Object.objects.create(
            model=self.model, object_type=self.team_type, name="Dev"
        )
        self.membership = Relationship.objects.create(
            model=self.model,
            relationship_type=self.member_of,
            subject=self.alice,
            object=self.ops,
            attributes={},
        )

        self.proposal = ProposalService.get_or_create_working(self.model, self.user)

    def _repoint(self, field, value):
        return ProposalService.record_change(
            proposal=self.proposal,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Relationship",
            target_id=self.membership.id,
            parent_type="RelationshipType",
            parent_id=self.member_of.id,
            field=field,
            before={"field": field, "value": str(getattr(self.membership, field))},
            after={"field": field, "value": str(value)},
        )

    def _run(self):
        ProposalService.submit(self.proposal)
        submission.process(submission.claim_next(self.model.id).id)
        self.proposal.refresh_from_db()
        self.model.refresh_from_db()
        self.membership.refresh_from_db()

    def _codes(self):
        return sorted(e.code for e in self.proposal.submission_result.errors.all())

    def test_object_endpoint_update_is_applied(self):
        self._repoint("object_id", self.dev.id)
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(self.model.revision, 2)
        self.assertEqual(self.membership.object_id, self.dev.id)
        self.assertEqual(self.membership.subject_id, self.alice.id)

    def test_subject_endpoint_update_is_applied(self):
        self._repoint("subject_id", self.bob.id)
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(self.membership.subject_id, self.bob.id)

    def test_endpoint_may_be_an_object_created_by_the_same_proposal(self):
        new_team_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=self.proposal,
            operation=ProposalChange.Operation.CREATE,
            target_type="Object",
            target_id=new_team_id,
            parent_type="ObjectType",
            parent_id=self.team_type.id,
            before=None,
            after={"name": "Platform", "description": "", "is_active": True, "attributes": {}},
        )
        self._repoint("object_id", new_team_id)
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(self.membership.object_id, new_team_id)

    def test_type_pair_not_permitted_by_the_rules_fails_validation(self):
        change = self._repoint("object_id", self.bob.id)
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.FAILED)
        self.assertEqual(self._codes(), ["invalid_relationship_types"])
        self.assertEqual(self.membership.object_id, self.ops.id)

        (error,) = self.proposal.submission_result.errors.all()
        self.assertEqual(error.change_id, change.id)

    def test_missing_endpoint_is_a_validation_issue_not_a_system_error(self):
        change = self._repoint("subject_id", uuid.uuid4())
        self._run()

        result = self.proposal.submission_result
        self.assertEqual(self.proposal.status, Proposal.Status.FAILED)
        self.assertEqual(result.outcome, result.Outcome.VALIDATION_FAILED)
        self.assertEqual(self._codes(), ["endpoint_not_found"])
        self.assertEqual(result.errors.get().change_id, change.id)
        self.assertEqual(self.membership.subject_id, self.alice.id)

    def test_endpoint_in_another_model_is_rejected(self):
        other_model = self._new_model(name="Other")
        other_type = ObjectType.objects.create(model=other_model, name="Team", key="team")
        stranger = Object.objects.create(model=other_model, object_type=other_type, name="Elsewhere")

        self._repoint("object_id", stranger.id)
        self._run()

        self.assertEqual(self._codes(), ["endpoint_not_found"])
        self.assertEqual(self.membership.object_id, self.ops.id)

    def test_cardinality_is_enforced_after_re_pointing(self):
        self.rule.object_minimum = 1
        self.rule.save()
        Relationship.objects.create(
            model=self.model,
            relationship_type=self.member_of,
            subject=self.bob,
            object=self.dev,
        )

        # Handing Alice's membership to Bob leaves Alice with no team,
        # below the rule's minimum of one.
        self._repoint("subject_id", self.bob.id)
        self._run()

        self.assertEqual(self.proposal.status, Proposal.Status.FAILED)
        self.assertEqual(self._codes(), ["object_cardinality_minimum"])
        self.assertEqual(self.membership.subject_id, self.alice.id)


class DeletedModelTaskTests(SubmissionTestCase):
    """A task dispatched before its model was deleted must be a quiet no-op."""

    def test_claim_next_for_a_deleted_model_does_nothing(self):
        model = self._new_model()
        model_id = model.id
        model.delete()

        self.assertIsNone(submission.claim_next(model_id))

    def test_process_for_a_deleted_proposal_does_nothing(self):
        model = self._new_model()
        proposal, _ = self._submit_object_type_create(model, "alpha")
        proposal_id = proposal.id
        model.delete()

        with patch("model.tasks.proposal_tasks.process_next_for_model.delay") as mock_delay:
            with self.captureOnCommitCallbacks(execute=True):
                submission.process(proposal_id)

        mock_delay.assert_not_called()


class KeyAssignmentTests(SubmissionTestCase):
    """
    model.services.keys-backed CREATE/UPDATE handling in
    _apply_create_or_update, across every key-bearing type
    (ObjectType/RelationshipType/AttributeDefinition/Object).
    """

    def _submit(self, model, proposal=None):
        proposal = proposal or ProposalService.get_or_create_working(model, self.user)
        ProposalService.submit(proposal)
        submission.process(submission.claim_next(model.id).id)
        proposal.refresh_from_db()
        return proposal

    def test_object_type_create_without_key_is_assigned_one(self):
        model = self._new_model()
        proposal = ProposalService.get_or_create_working(model, self.user)
        type_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal, operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType", target_id=type_id, parent_type="Model", parent_id=model.id,
            before=None,
            after={"name": "Widget", "description": "", "sort_order": 0, "is_active": True},
        )

        self._submit(model, proposal)

        self.assertEqual(ObjectType.objects.get(id=type_id).key, "widget")

    def test_object_create_without_key_is_assigned_one(self):
        model = self._new_model()
        object_type = ObjectType.objects.create(model=model, name="Widget", key="widget")
        proposal = ProposalService.get_or_create_working(model, self.user)
        object_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal, operation=ProposalChange.Operation.CREATE,
            target_type="Object", target_id=object_id,
            parent_type="ObjectType", parent_id=object_type.id,
            before=None,
            after={"name": "Acme Ltd", "description": "", "is_active": True, "attributes": {}},
        )

        self._submit(model, proposal)

        self.assertEqual(Object.objects.get(id=object_id).key, "acme_ltd")

    def test_object_key_collision_with_canonical_data_is_regenerated(self):
        model = self._new_model()
        object_type = ObjectType.objects.create(model=model, name="Widget", key="widget")
        Object.objects.create(model=model, object_type=object_type, name="Acme Ltd", key="acme_ltd")

        proposal = ProposalService.get_or_create_working(model, self.user)
        object_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal, operation=ProposalChange.Operation.CREATE,
            target_type="Object", target_id=object_id,
            parent_type="ObjectType", parent_id=object_type.id,
            before=None,
            after={
                "name": "Acme Ltd 2", "key": "acme_ltd",
                "description": "", "is_active": True, "attributes": {},
            },
        )

        proposal = self._submit(model, proposal)

        self.assertEqual(proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(Object.objects.get(id=object_id).key, "acme_ltd_2")

    def test_object_key_does_not_collide_across_object_types(self):
        model = self._new_model()
        type_a = ObjectType.objects.create(model=model, name="A", key="a")
        type_b = ObjectType.objects.create(model=model, name="B", key="b")
        Object.objects.create(model=model, object_type=type_a, name="Acme Ltd", key="acme_ltd")

        proposal = ProposalService.get_or_create_working(model, self.user)
        object_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal, operation=ProposalChange.Operation.CREATE,
            target_type="Object", target_id=object_id,
            parent_type="ObjectType", parent_id=type_b.id,
            before=None,
            after={
                "name": "Acme Ltd", "key": "acme_ltd",
                "description": "", "is_active": True, "attributes": {},
            },
        )

        self._submit(model, proposal)

        self.assertEqual(Object.objects.get(id=object_id).key, "acme_ltd")

    def test_attribute_definition_key_collision_blocks_rather_than_regenerates(self):
        model = self._new_model()
        object_type = ObjectType.objects.create(model=model, name="Widget", key="widget")
        AttributeDefinition.objects.create(
            object_type=object_type, name="Status", key="status", data_type="text",
        )

        proposal = ProposalService.get_or_create_working(model, self.user)
        attr_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal, operation=ProposalChange.Operation.CREATE,
            target_type="AttributeDefinition", target_id=attr_id,
            parent_type="ObjectType", parent_id=object_type.id,
            before=None,
            after={
                "name": "Status 2", "key": "status", "data_type": "text", "description": "",
                "required": False, "nullable": False, "default_value": None,
                "sort_order": 0, "config": {}, "is_active": True,
            },
        )

        proposal = self._submit(model, proposal)

        self.assertEqual(proposal.status, Proposal.Status.FAILED)
        self.assertEqual(proposal.submission_result.errors.get().code, "duplicate_key")
        self.assertFalse(AttributeDefinition.objects.filter(id=attr_id).exists())

    def test_key_update_is_rejected_for_every_key_bearing_type(self):
        model = self._new_model()
        object_type = ObjectType.objects.create(model=model, name="Widget", key="widget")
        relationship_type = RelationshipType.objects.create(model=model, name="Uses", key="uses")
        attribute = AttributeDefinition.objects.create(
            object_type=object_type, name="Status", key="status", data_type="text",
        )
        obj = Object.objects.create(model=model, object_type=object_type, name="Acme Ltd", key="acme_ltd")

        cases = [
            ("ObjectType", object_type.id),
            ("RelationshipType", relationship_type.id),
            ("AttributeDefinition", attribute.id),
            ("Object", obj.id),
        ]

        for target_type, target_id in cases:
            with self.subTest(target_type=target_type):
                proposal = ProposalService.get_or_create_working(model, self.user)
                ProposalService.record_change(
                    proposal=proposal, operation=ProposalChange.Operation.UPDATE,
                    target_type=target_type, target_id=target_id,
                    field="key",
                    before={"field": "key", "value": "whatever"},
                    after={"field": "key", "value": "renamed"},
                )

                proposal = self._submit(model, proposal)

                self.assertEqual(proposal.status, Proposal.Status.FAILED)
                error = proposal.submission_result.errors.get(
                    target_type=target_type, target_id=target_id,
                )
                self.assertEqual(error.code, "key_immutable")

    def test_invalid_template_supplied_key_is_reported(self):
        model = self._new_model()
        proposal = ProposalService.get_or_create_working(model, self.user)
        type_id = uuid.uuid4()
        ProposalService.record_change(
            proposal=proposal, operation=ProposalChange.Operation.CREATE,
            target_type="ObjectType", target_id=type_id, parent_type="Model", parent_id=model.id,
            before=None,
            after={
                "name": "Widget", "key": "not-a-valid-key",
                "description": "", "sort_order": 0, "is_active": True,
            },
        )

        proposal = self._submit(model, proposal)

        self.assertEqual(proposal.status, Proposal.Status.FAILED)
        self.assertEqual(proposal.submission_result.errors.get().code, "invalid_key")
