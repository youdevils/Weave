from django.conf import settings
from django.test import override_settings

from ingestion.models import ImportSource
from ingestion.services.errors import ImportBlocked, MappingError
from ingestion.services.proposals import create_import_proposal
from ingestion.tests.base import ImportTestCase
from model.models.evidence_reference import EvidenceReference
from model.models.object import Object
from model.models.proposal import Proposal, ProposalChange
from model.models.proposal_submission_result import ProposalSubmissionResult
from model.models.relationship import Relationship
from model.services.proposal import submission
from model.services.proposal.proposal import ProposalLimitReached, ProposalService


def drain(model_id):
    while True:
        proposal = submission.claim_next(model_id)
        if proposal is None:
            return
        submission.process(proposal.id)


MATCH = {"column": 0, "field": "attribute.app_id", "match": True}
NAME = {"column": 1, "field": "field.name"}
OWNER = {"column": 2, "field": "attribute.owner"}


class ImportProposalTests(ImportTestCase):

    def run_import(self, rows, *columns, user=None, filename="apps.csv"):
        user = user or self.editor
        source = self.stage(rows, filename, user=user)
        result = create_import_proposal(self.model, user, source, self.object_mapping(*columns))
        return source, result

    def snapshot(self):
        return (
            Object.objects.count(),
            Relationship.objects.count(),
            list(Object.objects.order_by("id").values_list("id", "name", "attributes")),
            self.model.__class__.objects.get(pk=self.model.pk).revision,
        )

    # -- exactly one proposal ------------------------------------------------------

    def test_an_import_with_changes_creates_exactly_one_working_proposal(self):
        self.make_app("Existing", "A0")

        source, result = self.run_import(
            [["App ID", "Name"], ["A1", "One"], ["A2", "Two"], ["A0", "Renamed"]], MATCH, NAME
        )

        proposals = Proposal.objects.filter(model=self.model)
        self.assertEqual(proposals.count(), 1)

        proposal = result.proposal
        self.assertEqual(proposal.status, Proposal.Status.WORKING)
        self.assertEqual(proposal.source, Proposal.Source.USER)
        self.assertEqual(proposal.created_by, self.editor)
        self.assertEqual(proposal.base_revision, self.model.revision)
        self.assertEqual(proposal.title, "Import: apps.csv")
        self.assertEqual(proposal.changes.count(), 3)  # 2 creates + 1 name update
        self.assertEqual(
            (proposal.changes.filter(operation="create").count(), proposal.changes.filter(operation="update").count()),
            (2, 1),
        )
        self.assertIn("2 objects created, 1 updated", proposal.summary)

    def test_it_is_a_new_proposal_even_when_the_user_already_has_one(self):
        existing = ProposalService.create_working(self.model, self.editor, title="Mine")

        _, result = self.run_import([["App ID", "Name"], ["A1", "One"]], MATCH, NAME)

        self.assertNotEqual(result.proposal.id, existing.id)
        self.assertEqual(existing.changes.count(), 0)
        self.assertEqual(Proposal.objects.filter(model=self.model).count(), 2)

    def test_a_no_change_import_creates_nothing_and_removes_its_source(self):
        self.make_app("Same", "A1")

        source, result = self.run_import([["App ID", "Name"], ["A1", "Same"]], MATCH, NAME)

        self.assertTrue(result.no_changes)
        self.assertFalse(Proposal.objects.exists())
        self.assertFalse(ProposalChange.objects.exists())
        self.assertFalse(EvidenceReference.objects.exists())
        self.assertFalse(ImportSource.objects.filter(pk=source.pk).exists())

    def test_canonical_data_is_untouched_until_the_proposal_is_processed(self):
        self.make_app("Old", "A1")
        before = self.snapshot()

        self.run_import([["App ID", "Name"], ["A1", "New"], ["A2", "Fresh"]], MATCH, NAME)

        self.assertEqual(self.snapshot(), before)

    def test_the_proposal_is_built_against_the_canonical_model_at_creation_time(self):
        self.make_app("Old", "A1")
        source = self.stage([["App ID", "Name"], ["A1", "New"]])
        mapping = self.object_mapping(MATCH, NAME)

        # The model moves on between the preview and the creation.
        Object.objects.filter(attributes__app_id="A1").update(name="New")

        result = create_import_proposal(self.model, self.editor, source, mapping)

        self.assertTrue(result.no_changes)

    def test_pending_proposals_are_never_consulted(self):
        # Another user has a pending proposal that would CREATE an object with app_id A1.
        other = ProposalService.create_working(self.model, self.owner)
        ProposalService.record_change(
            proposal=other, operation="create", target_type="Object", target_id=self.new_id(),
            parent_type="ObjectType", parent_id=self.app_type.id, before=None,
            after={"name": "Pending", "description": "", "is_active": True, "attributes": {"app_id": "A1"}},
        )

        _, result = self.run_import([["App ID", "Name"], ["A1", "Mine"]], MATCH, NAME)

        # Matching saw only canonical data: A1 is new, so this is a CREATE.
        self.assertEqual(result.proposal.changes.get().operation, "create")

    # -- the proposal works through the normal lifecycle -----------------------------

    def test_an_imported_proposal_is_submitted_validated_and_committed_normally(self):
        source, result = self.run_import(
            [["App ID", "Name", "Owner"], ["A1", "One", "Finance"], ["A2", "Two", "HR"]],
            MATCH, NAME, OWNER,
        )

        ProposalService.submit(result.proposal)
        drain(self.model.id)

        result.proposal.refresh_from_db()
        self.assertEqual(result.proposal.status, Proposal.Status.COMPLETED)
        self.assertEqual(
            sorted(Object.objects.filter(model=self.model).values_list("name", flat=True)), ["One", "Two"]
        )
        # Created objects carry the imported external id, and an OnyxJar-generated UUID.
        one = Object.objects.get(name="One")
        self.assertEqual(one.attributes, {"app_id": "A1", "owner": "Finance"})

    def test_repeating_an_import_after_it_committed_finds_nothing_to_change(self):
        rows = [["App ID", "Name", "Owner"], ["A1", "One", "Finance"]]
        _, first = self.run_import(rows, MATCH, NAME, OWNER)
        ProposalService.submit(first.proposal)
        drain(self.model.id)

        _, second = self.run_import(rows, MATCH, NAME, OWNER)

        self.assertTrue(second.no_changes)
        self.assertEqual(Object.objects.filter(model=self.model).count(), 1)

    def test_updates_apply_and_keep_the_identity_attribute(self):
        app = self.make_app("Old", "A1", owner="Finance")
        _, result = self.run_import([["App ID", "Name", "Owner"], ["A1", "New", "HR"]], MATCH, NAME, OWNER)

        ProposalService.submit(result.proposal)
        drain(self.model.id)

        app.refresh_from_db()
        self.assertEqual((app.name, app.attributes), ("New", {"app_id": "A1", "owner": "HR"}))

    # -- validation is the Proposal validator's business, not the importer's ----------

    def test_a_blank_required_value_is_built_and_then_rejected_by_the_existing_validator(self):
        self.make_app("Old", "A1")
        # `app_id` is required-by-omission only if flagged; make `owner` required and non-nullable.
        from model.models.attribute_definition import AttributeDefinition

        AttributeDefinition.objects.filter(pk=self.owner_attr.pk).update(required=True, nullable=False)
        self.make_app("Other", "A9", owner="Someone")

        _, result = self.run_import([["App ID", "Owner"], ["A9", ""]], MATCH, {"column": 1, "field": "attribute.owner"})

        # The importer built the change (owner -> empty) without judging it ...
        self.assertEqual(result.proposal.changes.get().after["value"], None)

        # ... and the normal pipeline refuses it.
        ProposalService.submit(result.proposal)
        drain(self.model.id)

        result.proposal.refresh_from_db()
        self.assertEqual(result.proposal.status, Proposal.Status.FAILED)
        codes = set(result.proposal.submission_result.errors.values_list("code", flat=True))
        self.assertIn("null_not_allowed", codes)
        self.assertEqual(Object.objects.get(attributes__app_id="A9").attributes["owner"], "Someone")

    def test_a_blank_name_is_rejected_by_the_strengthened_validator(self):
        _, result = self.run_import([["App ID", "Name"], ["A1", ""]], MATCH, NAME)

        ProposalService.submit(result.proposal)
        drain(self.model.id)

        result.proposal.refresh_from_db()
        self.assertEqual(result.proposal.status, Proposal.Status.FAILED)
        self.assertIn("name_required", set(result.proposal.submission_result.errors.values_list("code", flat=True)))
        self.assertFalse(Object.objects.exists())

    def test_an_overlong_name_is_reported_not_crashed(self):
        _, result = self.run_import([["App ID", "Name"], ["A1", "x" * 300]], MATCH, NAME)

        ProposalService.submit(result.proposal)
        drain(self.model.id)

        result.proposal.refresh_from_db()
        self.assertEqual(result.proposal.submission_result.outcome, ProposalSubmissionResult.Outcome.VALIDATION_FAILED)

    def test_an_unreadable_is_active_is_reported_not_crashed(self):
        self.make_app("Old", "A1")
        _, result = self.run_import(
            [["App ID", "Active"], ["A1", "maybe"]], MATCH, {"column": 1, "field": "field.is_active"}
        )

        ProposalService.submit(result.proposal)
        drain(self.model.id)

        result.proposal.refresh_from_db()
        self.assertEqual(result.proposal.submission_result.outcome, ProposalSubmissionResult.Outcome.VALIDATION_FAILED)
        self.assertIn("invalid_is_active", set(result.proposal.submission_result.errors.values_list("code", flat=True)))

    def test_a_disallowed_relationship_pair_is_blocked_by_the_import_itself(self):
        # Person -> Application is not permitted by the `uses` rule
        # (Application -> Application only); each endpoint resolves
        # individually, but the resulting pair is checked against the
        # relationship type's own rules and blocks before any proposal is
        # created -- it is not left to the Proposal validator.
        a = self.make_app("A", "A")
        person = self.make_app("Ann", object_type=self.person_type)
        source = self.stage([["ID", "To"], [str(person.id), "A"]], "rels.csv")

        with self.assertRaises(ImportBlocked) as raised:
            create_import_proposal(
                self.model, self.editor, source,
                self.relationship_mapping(
                    {"column": 0, "field": "endpoint.subject", "by": "id"},
                    self.by_app_id(1, "endpoint.object"),
                ),
            )

        self.assertEqual(raised.exception.problems[0].code, "endpoint_pair_not_allowed")
        self.assertFalse(Proposal.objects.exists())
        self.assertFalse(Relationship.objects.exists())

    def test_an_endpoint_deleted_after_the_proposal_was_built_is_reported(self):
        a = self.make_app("A", "A")
        b = self.make_app("B", "B")
        source = self.stage([["From", "To"], ["A", "B"]], "rels.csv")
        result = create_import_proposal(
            self.model, self.editor, source,
            self.relationship_mapping(self.by_app_id(0, "endpoint.subject"), self.by_app_id(1, "endpoint.object")),
        )

        b.delete()

        ProposalService.submit(result.proposal)
        drain(self.model.id)

        result.proposal.refresh_from_db()
        self.assertEqual(result.proposal.submission_result.outcome, ProposalSubmissionResult.Outcome.VALIDATION_FAILED)
        self.assertIn("endpoint_not_found", set(result.proposal.submission_result.errors.values_list("code", flat=True)))

    def test_an_object_changed_since_the_import_is_handled_by_normal_validation(self):
        app = self.make_app("Old", "A1")
        _, result = self.run_import([["App ID", "Name"], ["A1", "New"]], MATCH, NAME)

        app.delete()

        ProposalService.submit(result.proposal)
        drain(self.model.id)

        result.proposal.refresh_from_db()
        self.assertIn("target_not_found", set(result.proposal.submission_result.errors.values_list("code", flat=True)))

    # -- blocking --------------------------------------------------------------------

    def test_a_blocking_problem_creates_no_proposal_and_keeps_the_source(self):
        self.make_app("One", "A1")
        self.make_app("Two", "A1")
        source = self.stage([["App ID", "Name"], ["A1", "X"]])

        with self.assertRaises(ImportBlocked) as raised:
            create_import_proposal(self.model, self.editor, source, self.object_mapping(MATCH, NAME))

        self.assertEqual(raised.exception.problems[0].code, "ambiguous_identity")
        self.assertFalse(Proposal.objects.exists())
        self.assertTrue(ImportSource.objects.filter(pk=source.pk, imported_at__isnull=True).exists())

    def test_one_bad_row_blocks_the_whole_import_with_no_partial_proposal(self):
        self.make_app("One", "A1")
        self.make_app("Two", "A1")

        source = self.stage([["App ID", "Name"], ["NEW", "Fine"], ["A1", "Bad"]])

        with self.assertRaises(ImportBlocked):
            create_import_proposal(self.model, self.editor, source, self.object_mapping(MATCH, NAME))

        self.assertFalse(Proposal.objects.exists())
        self.assertFalse(ProposalChange.objects.exists())

    def test_a_malformed_mapping_creates_nothing(self):
        source = self.stage([["A"], ["1"]])

        with self.assertRaises(MappingError):
            create_import_proposal(self.model, self.editor, source, self.object_mapping({"column": 9, "field": "field.name"}))

        self.assertFalse(Proposal.objects.exists())

    @override_settings(IMPORT_MAX_CHANGES=2)
    def test_too_many_changes_blocks_the_import(self):
        source = self.stage([["App ID", "Name"], ["A1", "1"], ["A2", "2"], ["A3", "3"]])

        with self.assertRaises(ImportBlocked) as raised:
            create_import_proposal(self.model, self.editor, source, self.object_mapping(MATCH, NAME))

        self.assertEqual(raised.exception.problems[0].code, "too_many_changes")
        self.assertFalse(Proposal.objects.exists())

    # -- the live-proposal cap ----------------------------------------------------------

    def test_the_live_cap_is_enforced_before_any_work_and_leaves_nothing_behind(self):
        for _ in range(settings.PROPOSAL_MAX_LIVE_PER_MODEL):
            ProposalService.create_working(self.model, self.editor)

        source = self.stage([["App ID", "Name"], ["A1", "One"]])

        with self.assertRaises(ProposalLimitReached):
            create_import_proposal(self.model, self.editor, source, self.object_mapping(MATCH, NAME))

        self.assertEqual(Proposal.objects.filter(model=self.model).count(), settings.PROPOSAL_MAX_LIVE_PER_MODEL)
        self.assertTrue(ImportSource.objects.filter(pk=source.pk).exists())

    def test_the_cap_is_per_user_per_model_as_before(self):
        for _ in range(settings.PROPOSAL_MAX_LIVE_PER_MODEL):
            ProposalService.create_working(self.model, self.owner)

        _, result = self.run_import([["App ID", "Name"], ["A1", "One"]], MATCH, NAME)

        self.assertIsNotNone(result.proposal)
