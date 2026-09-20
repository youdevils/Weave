import uuid
from datetime import datetime, timedelta, timezone

from django.db import connection
from django.test.utils import CaptureQueriesContext

from account.models import CustomUser
from model.models.evidence_reference import EvidenceReference
from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.models.proposal_submission_result import ProposalSubmissionResult
from model.services.model_graph.provenance import build_provenance, build_provenance_bulk
from model.services.model_graph.tests.base import ModelGraphTestCase

Op = ProposalChange.Operation

BASE_TIME = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)

SPECS = {
    "status": {"label": "Status", "dataType": "choice"},
    "certified": {"label": "Certified", "dataType": "boolean"},
}


class ProvenanceTestCase(ModelGraphTestCase):

    def setUp(self):
        super().setUp()
        self.alice = self.make_object(self.person_type, "Alice")
        self.ops = self.make_object(self.team_type, "Ops")

    # -- builders ------------------------------------------------------------

    def proposal(
        self,
        revision,
        *,
        status=Proposal.Status.COMPLETED,
        title="",
        note="",
        user=None,
        source=Proposal.Source.USER,
        model=None,
    ):
        """A proposal that produced ``revision`` (or, if not COMPLETED, none)."""
        proposal = Proposal.objects.create(
            model=model or self.model,
            created_by=user or self.user,
            source=source,
            status=status,
            title=title,
            summary=note,
            submitted_at=BASE_TIME + timedelta(days=revision),
            completed_at=BASE_TIME + timedelta(days=revision, hours=1) if status == Proposal.Status.COMPLETED else None,
        )
        if status == Proposal.Status.COMPLETED:
            ProposalSubmissionResult.objects.create(
                proposal=proposal,
                outcome=ProposalSubmissionResult.Outcome.SUCCESS,
                before_revision=revision - 1,
                after_revision=revision,
            )
        return proposal

    def change(self, proposal, operation, target_type, target_id, before=None, after=None, **kwargs):
        return self.add_change(
            proposal,
            operation=operation,
            target_type=target_type,
            target_id=target_id,
            before=before,
            after=after,
            **kwargs,
        )

    def field_change(self, proposal, target, field, before, after, target_type="Object", **kwargs):
        return self.change(
            proposal,
            Op.UPDATE,
            target_type,
            target,
            before={"field": field, "value": before},
            after={"field": field, "value": after},
            **kwargs,
        )

    def provenance(self, target_type="Object", target=None, **kwargs):
        return build_provenance(self.model, target_type, (target or self.alice).id, kwargs.pop("specs", SPECS), **kwargs)

    def entries(self, **kwargs):
        return self.provenance(**kwargs)["entries"]

    def only_change(self, **kwargs):
        (entry,) = self.entries(**kwargs)
        (change,) = entry["changes"]
        return change


class ChainSelectionTests(ProvenanceTestCase):

    def test_no_history_is_an_empty_chain(self):
        self.assertEqual(self.provenance(), {"entries": [], "truncated": False})

    def test_only_completed_proposals_count(self):
        for revision, status in enumerate(
            (
                Proposal.Status.WORKING,
                Proposal.Status.FAILED,
                Proposal.Status.QUEUED,
                Proposal.Status.PROCESSING,
            ),
            start=2,
        ):
            self.field_change(self.proposal(revision, status=status), self.alice.id, "name", "A", "B")

        self.assertEqual(self.entries(), [])

    def test_only_changes_to_the_selected_record_are_included(self):
        proposal = self.proposal(2)
        self.field_change(proposal, self.alice.id, "name", "Alice", "Alicia")
        self.field_change(proposal, self.ops.id, "name", "Ops", "Operations")
        self.change(proposal, Op.CREATE, "ObjectType", uuid.uuid4(), after={"name": "Thing"})

        (entry,) = self.entries()

        self.assertEqual([c["kind"] for c in entry["changes"]], ["renamed"])
        self.assertEqual(entry["changes"][0]["after"], "Alicia")

    def test_an_object_and_relationship_sharing_an_id_are_not_confused(self):
        shared = uuid.uuid4()
        proposal = self.proposal(2)
        self.field_change(proposal, shared, "name", "A", "B", target_type="Object")
        self.field_change(proposal, shared, "attributes.status", "x", "y", target_type="Relationship")

        entries = build_provenance(self.model, "Object", shared, SPECS)["entries"]

        self.assertEqual([c["kind"] for e in entries for c in e["changes"]], ["renamed"])

    def test_another_models_changes_are_excluded(self):
        other = Model.objects.create(workspace=self.workspace, name="Other", revision=1)
        self.field_change(self.proposal(2, model=other), self.alice.id, "name", "A", "B")

        self.assertEqual(self.entries(), [])


class OrderingAndGroupingTests(ProvenanceTestCase):

    def test_entries_run_oldest_to_newest_by_revision_not_by_creation(self):
        # Created out of order on purpose.
        for revision in (7, 3, 5):
            self.field_change(self.proposal(revision), self.alice.id, "name", "a", f"name r{revision}")

        entries = self.entries()

        self.assertEqual([e["revision"]["after"] for e in entries], [3, 5, 7])
        self.assertEqual([e["changes"][0]["after"] for e in entries], ["name r3", "name r5", "name r7"])

    def test_a_story_reads_created_changed_changed_deactivated(self):
        self.change(
            self.proposal(2),
            Op.CREATE,
            "Object",
            self.alice.id,
            after={"name": "Alice", "description": "", "is_active": True, "attributes": {}},
        )
        self.field_change(self.proposal(3), self.alice.id, "name", "Alice", "Alicia")
        self.field_change(self.proposal(4), self.alice.id, "attributes.status", "Active", "Left")
        self.field_change(self.proposal(5), self.alice.id, "is_active", True, False)

        kinds = [e["changes"][0]["kind"] for e in self.entries()]

        self.assertEqual(kinds, ["created", "renamed", "attribute_changed", "deactivated"])

    def test_changes_in_one_proposal_share_one_entry(self):
        proposal = self.proposal(2, title="Onboarding", note="Joined in March")
        self.field_change(proposal, self.alice.id, "name", "a", "b")
        self.field_change(proposal, self.alice.id, "description", "", "New starter")

        (entry,) = self.entries()

        self.assertEqual(len(entry["changes"]), 2)
        self.assertEqual(entry["title"], "Onboarding")
        self.assertEqual(entry["changeNote"], "Joined in March")

    def test_within_an_entry_create_comes_first_and_delete_last(self):
        proposal = self.proposal(2)
        stamps = iter(BASE_TIME + timedelta(minutes=n) for n in range(10))
        delete = self.change(proposal, Op.DELETE, "Object", self.alice.id)
        update = self.field_change(proposal, self.alice.id, "name", "a", "b")
        create = self.change(
            proposal, Op.CREATE, "Object", self.alice.id, after={"name": "Alice", "attributes": {}}
        )
        # Make the stored order deliberately different from the presentation order.
        for change in (update, delete, create):
            ProposalChange.objects.filter(id=change.id).update(created_at=next(stamps))

        (entry,) = self.entries()

        self.assertEqual([c["kind"] for c in entry["changes"]], ["created", "renamed", "deleted"])

    def test_entry_carries_proposer_revision_and_dates(self):
        author = CustomUser.objects.create_user(email="author@example.com", password="test-password")
        self.field_change(self.proposal(4, user=author), self.alice.id, "name", "a", "b")

        (entry,) = self.entries()

        self.assertEqual(entry["proposer"], "author@example.com")
        self.assertEqual(entry["revision"], {"before": 3, "after": 4})
        self.assertEqual(entry["source"], "user")
        self.assertEqual(entry["submittedAt"], (BASE_TIME + timedelta(days=4)).isoformat())
        self.assertEqual(entry["committedAt"], (BASE_TIME + timedelta(days=4, hours=1)).isoformat())

    def test_an_ai_proposal_is_flagged(self):
        self.field_change(self.proposal(2, source=Proposal.Source.AI), self.alice.id, "name", "a", "b")

        self.assertEqual(self.entries()[0]["source"], "ai")

    def test_committed_at_falls_back_to_the_submission_result_time(self):
        proposal = self.proposal(2)
        Proposal.objects.filter(id=proposal.id).update(completed_at=None)
        self.field_change(proposal, self.alice.id, "name", "a", "b")

        self.assertIsNotNone(self.entries()[0]["committedAt"])

    def test_no_proposal_identifier_or_link_is_exposed(self):
        proposal = self.proposal(2)
        self.field_change(proposal, self.alice.id, "name", "a", "b")

        rendered = repr(self.provenance())

        self.assertNotIn(str(proposal.id), rendered)
        self.assertNotIn("/proposals/", rendered)
        entry = self.entries()[0]
        self.assertEqual(
            set(entry),
            {"revision", "title", "source", "proposer", "changeNote", "submittedAt", "committedAt", "changes"},
        )

    def test_a_long_chain_is_capped_to_the_most_recent_and_flagged(self):
        for revision in range(2, 8):
            self.field_change(self.proposal(revision), self.alice.id, "name", "a", f"r{revision}")

        result = self.provenance(limit=3)

        self.assertTrue(result["truncated"])
        self.assertEqual([e["revision"]["after"] for e in result["entries"]], [5, 6, 7])

    def test_a_chain_within_the_cap_is_not_truncated(self):
        for revision in range(2, 5):
            self.field_change(self.proposal(revision), self.alice.id, "name", "a", "b")

        self.assertFalse(self.provenance(limit=3)["truncated"])


class EvidenceInProvenanceTests(ProvenanceTestCase):

    def evidence(self, change, source, locator="", note=""):
        return EvidenceReference.objects.create(change=change, source=source, locator=locator, note=note)

    def test_evidence_attached_to_a_change_is_shown_with_that_change(self):
        proposal = self.proposal(2)
        renamed = self.field_change(proposal, self.alice.id, "name", "a", "b")
        described = self.field_change(proposal, self.alice.id, "description", "", "x")
        self.evidence(renamed, "HR system", "record 12", "Confirmed by HR")

        (entry,) = self.entries()
        by_kind = {c["kind"]: c for c in entry["changes"]}

        self.assertEqual(
            by_kind["renamed"]["evidence"],
            [{"source": "HR system", "locator": "record 12", "note": "Confirmed by HR"}],
        )
        self.assertEqual(by_kind["described"]["evidence"], [])
        self.assertTrue(described)

    def test_a_change_may_carry_several_pieces_of_evidence(self):
        change = self.field_change(self.proposal(2), self.alice.id, "name", "a", "b")
        self.evidence(change, "A")
        self.evidence(change, "B")

        self.assertEqual(sorted(e["source"] for e in self.only_change()["evidence"]), ["A", "B"])

    def test_evidence_of_other_records_or_uncommitted_proposals_does_not_leak(self):
        committed = self.proposal(2)
        self.evidence(self.field_change(committed, self.ops.id, "name", "a", "b"), "Ops only")
        pending = self.proposal(3, status=Proposal.Status.WORKING)
        self.evidence(self.field_change(pending, self.alice.id, "name", "a", "b"), "Not yet committed")
        self.field_change(committed, self.alice.id, "description", "", "x")

        (change,) = [c for e in self.entries() for c in e["changes"]]

        self.assertEqual(change["evidence"], [])

    def test_evidence_is_not_a_property_of_the_record(self):
        change = self.field_change(self.proposal(2), self.alice.id, "name", "a", "b")
        self.evidence(change, "Doc")

        self.assertFalse(hasattr(self.alice, "evidence"))
        self.assertEqual(EvidenceReference.objects.get().change_id, change.id)

    def test_query_count_does_not_grow_with_the_chain(self):
        def count():
            with CaptureQueriesContext(connection) as queries:
                self.provenance()
            return len(queries)

        self.evidence(self.field_change(self.proposal(2), self.alice.id, "name", "a", "b"), "First")
        baseline = count()

        for revision in range(3, 9):
            proposal = self.proposal(revision, user=CustomUser.objects.create_user(
                email=f"u{revision}@example.com", password="test-password"))
            for field in ("name", "description"):
                change = self.field_change(proposal, self.alice.id, field, "a", "b")
                self.evidence(change, f"S{revision}{field}")
                self.evidence(change, f"T{revision}{field}")

        self.assertEqual(count(), baseline)

    def test_relationship_query_count_is_also_constant(self):
        relationship = self.make_relationship(self.alice, self.ops)

        def count():
            with CaptureQueriesContext(connection) as queries:
                self.provenance("Relationship", relationship)
            return len(queries)

        self.change(
            self.proposal(2),
            Op.CREATE,
            "Relationship",
            relationship.id,
            after={"subject_id": str(self.alice.id), "object_id": str(self.ops.id), "is_active": True, "attributes": {}},
        )
        baseline = count()

        for revision in range(3, 7):
            self.field_change(self.proposal(revision), relationship.id, "attributes.status", "a", "b", target_type="Relationship")

        self.assertEqual(count(), baseline)


class ObjectInterpretationTests(ProvenanceTestCase):

    def create(self, **after):
        payload = {"name": "Alice", "description": "", "is_active": True, "attributes": {}, **after}
        self.change(self.proposal(2), Op.CREATE, "Object", self.alice.id, after=payload)
        return self.only_change()

    def test_create(self):
        change = self.create()

        self.assertEqual(
            (change["kind"], change["summary"], change["after"], change["initial"]),
            ("created", "Created", "Alice", []),
        )

    def test_create_lists_initial_populated_attributes_formatted(self):
        change = self.create(attributes={"status": "Active", "certified": True, "blank": "  ", "empty": None})

        self.assertEqual(
            change["initial"],
            [
                {"label": "Status", "value": "Active"},
                {"label": "Certified", "value": "Yes"},
                # Not defined any more: falls back to the key.
            ],
        )

    def test_create_of_an_inactive_object_says_so(self):
        change = self.create(is_active=False)

        self.assertEqual((change["kind"], change["summary"]), ("created", "Created (inactive)"))

    def test_rename(self):
        self.field_change(self.proposal(2), self.alice.id, "name", "Alice", "Alicia")

        change = self.only_change()

        self.assertEqual(
            (change["kind"], change["summary"], change["field"], change["before"], change["after"]),
            ("renamed", "Renamed", "Name", "Alice", "Alicia"),
        )

    def test_description(self):
        self.field_change(self.proposal(2), self.alice.id, "description", "", "Engineer")

        change = self.only_change()

        self.assertEqual((change["kind"], change["summary"], change["before"], change["after"]), ("described", "Changed description", None, "Engineer"))

    def test_attribute_changed_uses_the_definition_label(self):
        self.field_change(self.proposal(2), self.alice.id, "attributes.status", "Active", "Left")

        change = self.only_change()

        self.assertEqual(
            (change["kind"], change["summary"], change["field"], change["before"], change["after"]),
            ("attribute_changed", "Changed Status", "Status", "Active", "Left"),
        )

    def test_attribute_set_when_it_was_empty(self):
        for before in (None, ""):
            with self.subTest(before=before):
                ProposalChange.objects.all().delete()
                self.field_change(self.proposal(2), self.alice.id, "attributes.status", before, "Active")

                change = self.only_change()

                self.assertEqual((change["kind"], change["summary"], change["before"]), ("attribute_set", "Set Status", None))

    def test_attribute_cleared(self):
        self.field_change(self.proposal(2), self.alice.id, "attributes.status", "Active", None)

        change = self.only_change()

        self.assertEqual(
            (change["kind"], change["summary"], change["before"], change["after"]),
            ("attribute_cleared", "Cleared Status", "Active", None),
        )

    def test_boolean_attribute_values_read_yes_no(self):
        self.field_change(self.proposal(2), self.alice.id, "attributes.certified", False, True)

        change = self.only_change()

        self.assertEqual((change["before"], change["after"]), ("No", "Yes"))

    def test_a_false_boolean_is_a_value_not_a_clear(self):
        self.field_change(self.proposal(2), self.alice.id, "attributes.certified", True, False)

        self.assertEqual(self.only_change()["kind"], "attribute_changed")

    def test_attribute_without_a_definition_falls_back_to_its_key(self):
        self.field_change(self.proposal(2), self.alice.id, "attributes.retired_field", "a", "b")

        change = self.only_change()

        self.assertEqual((change["summary"], change["field"]), ("Changed retired_field", "retired_field"))

    def test_missing_before_shows_only_the_new_value(self):
        self.change(
            self.proposal(2),
            Op.UPDATE,
            "Object",
            self.alice.id,
            before=None,
            after={"field": "attributes.status", "value": "Active"},
        )

        change = self.only_change()

        self.assertEqual((change["kind"], change["before"], change["after"]), ("attribute_changed", None, "Active"))

    def test_deactivate_and_reactivate(self):
        self.field_change(self.proposal(2), self.alice.id, "is_active", True, False)
        self.field_change(self.proposal(3), self.alice.id, "is_active", False, True)

        first, second = (e["changes"][0] for e in self.entries())

        self.assertEqual((first["kind"], first["summary"]), ("deactivated", "Deactivated"))
        self.assertEqual((second["kind"], second["summary"]), ("reactivated", "Reactivated"))

    def test_delete(self):
        self.change(self.proposal(2), Op.DELETE, "Object", self.alice.id)

        change = self.only_change()

        self.assertEqual((change["kind"], change["summary"]), ("deleted", "Deleted"))

    def test_an_unrecognised_field_stays_legible(self):
        self.field_change(self.proposal(2), self.alice.id, "sort_order", 1, 2)

        change = self.only_change()

        self.assertEqual(
            (change["kind"], change["summary"], change["before"], change["after"]),
            ("field_changed", "Changed Sort Order", "1", "2"),
        )

    def test_raw_operation_and_json_are_never_exposed(self):
        self.field_change(self.proposal(2), self.alice.id, "name", "a", "b")

        change = self.only_change()

        self.assertEqual(
            set(change),
            {"kind", "summary", "field", "before", "after", "evidence"},
        )


class RelationshipInterpretationTests(ProvenanceTestCase):

    def setUp(self):
        super().setUp()
        self.link = self.make_relationship(self.alice, self.ops)

    def create(self, **after):
        payload = {
            "subject_id": str(self.alice.id),
            "object_id": str(self.ops.id),
            "is_active": True,
            "attributes": {},
            **after,
        }
        self.change(self.proposal(2), Op.CREATE, "Relationship", self.link.id, after=payload)
        return self.only_change(target_type="Relationship", target=self.link)

    def test_create_names_the_endpoints_as_they_are_now(self):
        change = self.create()

        self.assertEqual(
            (change["kind"], change["summary"], change["after"]),
            ("created", "Created relationship", "Alice → Ops"),
        )
        # Flagged so the UI never presents these as names-at-the-time.
        self.assertTrue(change["currentNames"])

    def test_create_uses_current_names_not_historical_ones(self):
        self.create()
        self.alice.name = "Alicia"
        self.alice.save()

        (entry,) = self.entries(target_type="Relationship", target=self.link)

        self.assertEqual(entry["changes"][0]["after"], "Alicia → Ops")

    def test_create_with_a_deleted_endpoint_says_so(self):
        self.create()
        link_id = self.link.id
        self.link.delete()
        self.ops.delete()

        (entry,) = build_provenance(self.model, "Relationship", link_id, SPECS)["entries"]

        self.assertEqual(entry["changes"][0]["after"], "Alice → an object that no longer exists")

    def test_create_of_an_inactive_relationship_says_so(self):
        self.assertEqual(self.create(is_active=False)["summary"], "Created relationship (inactive)")

    def test_attribute_is_active_and_delete_follow_the_object_rules(self):
        self.field_change(self.proposal(3), self.link.id, "attributes.status", "a", "b", target_type="Relationship")
        self.field_change(self.proposal(4), self.link.id, "is_active", True, False, target_type="Relationship")
        self.change(self.proposal(5), Op.DELETE, "Relationship", self.link.id)

        kinds = [e["changes"][0]["kind"] for e in self.entries(target_type="Relationship", target=self.link)]

        self.assertEqual(kinds, ["attribute_changed", "deactivated", "deleted"])

    def test_an_objects_chain_does_not_include_its_relationships(self):
        self.create()
        self.field_change(self.proposal(3), self.alice.id, "name", "a", "b")

        kinds = [c["kind"] for e in self.entries() for c in e["changes"]]

        self.assertEqual(kinds, ["renamed"])


class BulkProvenanceTests(ProvenanceTestCase):

    def test_bulk_matches_single_record_calls(self):
        proposal = self.proposal(2, title="First", note="why")
        self.field_change(proposal, self.alice.id, "name", "Alice", "Alicia")
        EvidenceReference.objects.create(
            change=self.field_change(proposal, self.alice.id, "attributes.status", "x", "Active"), source="Source A"
        )
        self.field_change(self.proposal(3), self.ops.id, "name", "Ops", "Operations")

        bulk = build_provenance_bulk(
            self.model,
            "Object",
            [self.alice.id, self.ops.id],
            lambda _id: SPECS,
            endpoint_names={},
        )

        for record in (self.alice, self.ops):
            self.assertEqual(bulk[str(record.id)], build_provenance(self.model, "Object", record.id, SPECS))

    def test_every_requested_id_has_an_entry_even_without_history(self):
        untouched = uuid.uuid4()

        bulk = build_provenance_bulk(self.model, "Object", [untouched], lambda _id: {}, endpoint_names={})

        self.assertEqual(bulk, {str(untouched): {"entries": [], "truncated": False}})

    def test_query_count_does_not_grow_with_the_number_of_records(self):
        people = [self.make_object(self.person_type, f"P{i}") for i in range(6)]
        for i, person in enumerate(people, start=2):
            self.field_change(self.proposal(i, user=self.user), person.id, "name", "a", "b")

        def count(ids):
            with CaptureQueriesContext(connection) as queries:
                build_provenance_bulk(self.model, "Object", ids, lambda _id: SPECS, endpoint_names={})
            return len(queries)

        self.assertEqual(count([p.id for p in people[:1]]), count([p.id for p in people]))

    def test_unlisted_relationship_endpoints_use_the_supplied_label(self):
        relationship = self.make_relationship(self.alice, self.ops)
        self.change(
            self.proposal(2),
            Op.CREATE,
            "Relationship",
            relationship.id,
            after={"subject_id": str(self.alice.id), "object_id": str(self.ops.id), "is_active": True},
        )

        bulk = build_provenance_bulk(
            self.model,
            "Relationship",
            [relationship.id],
            lambda _id: {},
            endpoint_names={str(self.alice.id): "Alice"},
            missing_endpoint="an object outside this publication",
        )

        (entry,) = bulk[str(relationship.id)]["entries"]
        self.assertEqual(entry["changes"][0]["after"], "Alice → an object outside this publication")
