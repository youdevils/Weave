import json
import uuid
from datetime import datetime, timedelta, timezone

from model.models.evidence_reference import EvidenceReference
from model.models.proposal import Proposal, ProposalChange
from model.models.proposal_submission_result import ProposalSubmissionResult
from model.services.appearance import AppearanceService
from publication.services.bundle import (
    FORMAT,
    OUTSIDE_PUBLICATION,
    build_bundle,
    compute_digest,
    with_publication,
)

from .base import PublicationTestCase

Op = ProposalChange.Operation
BASE_TIME = datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc)


class BundleFixture(PublicationTestCase):

    def setUp(self):
        super().setUp()
        self.alice = self.make_object(self.person_type, "Alice", attributes={"status": "Active"})
        self.ops = self.make_object(self.team_type, "Ops")
        self.rel = self.make_relationship(self.alice, self.ops)

    def bundle(self, raw=None):
        result = self.normalised(raw)
        return build_bundle(self.model, result.published, result.config)

    def commit(self, revision, target_type, target_id, field, before, after, *, user=None, note="", title=""):
        """A COMPLETED proposal that changed one field of one record."""
        proposal = Proposal.objects.create(
            model=self.model,
            created_by=user or self.user,
            status=Proposal.Status.COMPLETED,
            title=title,
            summary=note,
            submitted_at=BASE_TIME + timedelta(days=revision),
            completed_at=BASE_TIME + timedelta(days=revision, hours=1),
        )
        ProposalSubmissionResult.objects.create(
            proposal=proposal,
            outcome=ProposalSubmissionResult.Outcome.SUCCESS,
            before_revision=revision - 1,
            after_revision=revision,
        )
        return self.add_change(
            proposal,
            operation=Op.UPDATE,
            target_type=target_type,
            target_id=target_id,
            before={"field": field, "value": before},
            after={"field": field, "value": after},
        )


class ShapeTests(BundleFixture):

    def test_top_level_shape(self):
        bundle = self.bundle()

        self.assertEqual(bundle["format"], FORMAT)
        self.assertEqual(bundle["formatVersion"], 1)
        self.assertEqual(bundle["sourceRevision"], self.model.revision)
        self.assertEqual(
            set(bundle),
            {
                "format",
                "formatVersion",
                "sourceRevision",
                "publication",
                "presentation",
                "defaultView",
                "graphTemplate",
                "dataset",
                "facets",
                "provenance",
                "digest",
            },
        )

    def test_it_is_plain_json(self):
        bundle = self.bundle()

        self.assertEqual(json.loads(json.dumps(bundle)), bundle)

    def test_records_are_embedded_in_the_datasets_stable_order(self):
        self.make_object(self.person_type, "aaron")

        objects = self.bundle()["dataset"]["objects"]

        self.assertEqual([o["name"] for o in objects], ["aaron", "Alice", "Ops"])
        self.assertEqual(objects[0]["sortKey"], "aaron")
        self.assertEqual(objects[0]["foldKey"], "aaron")

    def test_types_carry_their_resolved_style(self):
        AppearanceService.set_type_style(self.model, "object_type", self.person_type.id, "background", "#ff0000")

        types = {t["name"]: t for t in self.bundle()["dataset"]["objectTypes"]}

        self.assertEqual(types["Person"]["style"]["background"], "#FF0000")
        self.assertEqual(types["Team"]["style"]["background"], "#EDF2FF")

    def test_the_graph_template_is_a_payload_without_nodes(self):
        template = self.bundle()["graphTemplate"]

        self.assertEqual(template["schema_version"], "1.0")
        self.assertEqual(template["nodes"], [])
        self.assertEqual(template["edges"], [])
        self.assertEqual({t["key"] for t in template["node_types"]}, {"person", "team"})

    def test_publication_identity_is_added_without_changing_the_digest(self):
        bundle = self.bundle()

        stamped = with_publication(bundle, {"id": "abc", "sequence": 3, "publishedAt": "2026-01-01T00:00:00+00:00"})

        self.assertEqual(stamped["publication"]["sequence"], 3)
        self.assertEqual(stamped["publication"]["title"], bundle["publication"]["title"])
        self.assertEqual(compute_digest(stamped), bundle["digest"])
        self.assertNotIn("sequence", bundle["publication"])

    def test_no_link_back_to_weave_is_embedded(self):
        text = json.dumps(self.bundle())

        for needle in (str(self.model.id), str(self.workspace.id), "/model/", "csrf", "explore/graph"):
            self.assertNotIn(needle, text)


class AttributeDrivenStyleTests(BundleFixture):
    """
    ``build_dataset_block`` must resolve colour per instance only for types
    that are actually attribute-driven, so an unmodified model's bundle is
    byte-identical to before this feature existed.
    """

    def test_type_sourced_types_carry_no_per_instance_style(self):
        bundle = self.bundle()

        self.assertNotIn("style", bundle["dataset"]["objects"][0])
        self.assertNotIn("style", bundle["dataset"]["relationships"][0])

    def test_attribute_sourced_object_type_gets_a_resolved_per_instance_style(self):
        AppearanceService.set_type_style(self.model, "object_type", self.person_type.id, "background_source", "attribute")
        AppearanceService.set_type_style(self.model, "object_type", self.person_type.id, "background_attribute", "status")
        AppearanceService.set_attribute_colour(self.model, "object_type", self.person_type.id, "status", "Active", "#00FF00")

        objects = {o["name"]: o for o in self.bundle()["dataset"]["objects"]}

        self.assertEqual(objects["Alice"]["style"]["background"], "#00FF00")
        self.assertNotIn("style", objects["Ops"])  # a Team: an unaffected type

    def test_missing_value_falls_back_to_the_type_colour_in_the_bundle(self):
        AppearanceService.set_type_style(self.model, "object_type", self.person_type.id, "background_source", "attribute")
        AppearanceService.set_type_style(self.model, "object_type", self.person_type.id, "background_attribute", "status")
        AppearanceService.set_type_style(self.model, "object_type", self.person_type.id, "background", "#123456")
        self.make_object(self.person_type, "NoValue")

        objects = {o["name"]: o for o in self.bundle()["dataset"]["objects"]}

        self.assertEqual(objects["NoValue"]["style"]["background"], "#123456")

    def test_attribute_sourced_relationship_type_gets_a_resolved_per_instance_style(self):
        AttributeDefinitionCls = self.status_attribute.__class__
        AttributeDefinitionCls.objects.create(
            relationship_type=self.member_of,
            name="Importance",
            key="importance",
            data_type=AttributeDefinitionCls.DataType.CHOICE,
            config={"choices": ["High", "Low"]},
        )
        self.rel.attributes = {"importance": "High"}
        self.rel.save()
        AppearanceService.set_type_style(self.model, "relationship_type", self.member_of.id, "colour_source", "attribute")
        AppearanceService.set_type_style(self.model, "relationship_type", self.member_of.id, "colour_attribute", "importance")
        AppearanceService.set_attribute_colour(
            self.model, "relationship_type", self.member_of.id, "importance", "High", "#FF0000"
        )

        relationships = self.bundle()["dataset"]["relationships"]

        self.assertEqual(relationships[0]["style"]["colour"], "#FF0000")


class CanonicalOnlyTests(BundleFixture):

    def test_pending_proposal_changes_never_appear(self):
        proposal = self.working_proposal()
        proposed_object = self.propose_object(proposal, self.person_type.id, "Proposed Pat")
        self.propose_relationship(proposal, proposed_object, self.ops.id)
        self.update(proposal, "Object", self.alice.id, "name", "Alice Renamed")
        self.add_change(proposal, operation=Op.DELETE, target_type="Object", target_id=self.ops.id)
        new_type = str(uuid.uuid4())
        self.add_change(
            proposal,
            operation=Op.CREATE,
            target_type="ObjectType",
            target_id=new_type,
            after={"name": "Proposed Type", "key": "proposed_type", "is_active": True},
        )

        bundle = self.bundle()
        text = json.dumps(bundle)

        self.assertEqual([o["name"] for o in bundle["dataset"]["objects"]], ["Alice", "Ops"])
        self.assertNotIn("Proposed Pat", text)
        self.assertNotIn("Alice Renamed", text)
        self.assertNotIn("Proposed Type", text)
        self.assertEqual(len(bundle["dataset"]["relationships"]), 1)

    def test_no_record_or_type_is_marked_proposed(self):
        text = json.dumps(self.bundle())

        # The Explorer's facet shape carries the flag, but it must never be true.
        self.assertNotIn('"isProposed": true', text)
        self.assertNotIn('"is_proposed": true', text)
        self.assertNotIn("is_created", text)

    def test_queued_and_failed_proposals_are_not_canonical_either(self):
        for status in (Proposal.Status.QUEUED, Proposal.Status.FAILED, Proposal.Status.PROCESSING):
            proposal = Proposal.objects.create(model=self.model, created_by=self.user, status=status)
            self.propose_object(proposal, self.person_type.id, f"Ghost {status}")

        names = [o["name"] for o in self.bundle()["dataset"]["objects"]]

        self.assertEqual(names, ["Alice", "Ops"])


class DigestTests(BundleFixture):

    def test_the_same_content_has_the_same_digest(self):
        self.assertEqual(self.bundle()["digest"], self.bundle()["digest"])

    def test_the_digest_is_recomputable_from_the_bundle(self):
        bundle = self.bundle()

        self.assertEqual(compute_digest(json.loads(json.dumps(bundle))), bundle["digest"])

    def test_metadata_and_presentation_do_not_change_the_digest(self):
        base = self.bundle()["digest"]

        changed = self.bundle({"title": "Other title", "description": "d", "presentation": {"theme_colour": "#00ff00"}})

        self.assertEqual(changed["digest"], base)

    def test_scope_changes_the_digest(self):
        base = self.bundle()["digest"]

        narrowed = self.bundle({"scope": {"object_types": {"excluded": [str(self.team_type.id)]}}})

        self.assertNotEqual(narrowed["digest"], base)

    def test_data_changes_the_digest(self):
        base = self.bundle()["digest"]

        self.make_object(self.team_type, "New Team")

        self.assertNotEqual(self.bundle()["digest"], base)

    def test_appearance_changes_the_digest_but_not_the_revision(self):
        before = self.bundle()

        AppearanceService.update_customisation(self.model, "object", "background", "#ff0000")
        self.model.refresh_from_db()
        after = self.bundle()

        self.assertEqual(after["sourceRevision"], before["sourceRevision"])
        self.assertNotEqual(after["digest"], before["digest"])

    def test_the_revision_changes_the_digest(self):
        before = self.bundle()["digest"]

        self.model.revision += 1
        self.model.save(update_fields=["revision"])

        self.assertNotEqual(self.bundle()["digest"], before)


class ProvenanceTests(BundleFixture):

    def test_history_of_published_records_is_included_with_evidence(self):
        change = self.commit(2, "Object", self.alice.id, "name", "Alicia", "Alice", note="Fixed spelling", title="Tidy")
        EvidenceReference.objects.create(change=change, source="https://example.com/hr", locator="p1", note="HR file")

        chain = self.bundle()["provenance"]["objects"][str(self.alice.id)]

        (entry,) = chain["entries"]
        self.assertEqual(entry["revision"], {"before": 1, "after": 2})
        self.assertEqual(entry["changeNote"], "Fixed spelling")
        self.assertEqual(entry["proposer"], self.user.email)
        self.assertEqual(
            entry["changes"][0]["evidence"], [{"source": "https://example.com/hr", "locator": "p1", "note": "HR file"}]
        )

    def test_records_without_history_are_absent(self):
        self.assertEqual(self.bundle()["provenance"], {"objects": {}, "relationships": {}})

    def test_history_of_unpublished_records_is_not_included(self):
        self.commit(2, "Object", self.ops.id, "name", "Operations", "Ops")

        bundle = self.bundle({"scope": {"object_types": {"excluded": [str(self.team_type.id)]}}})

        self.assertEqual(bundle["provenance"]["objects"], {})
        self.assertNotIn("Operations", json.dumps(bundle))

    def test_a_relationship_created_by_a_proposal_names_only_published_endpoints(self):
        proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.COMPLETED,
            submitted_at=BASE_TIME,
            completed_at=BASE_TIME,
        )
        ProposalSubmissionResult.objects.create(
            proposal=proposal, outcome="success", before_revision=1, after_revision=2
        )
        self.add_change(
            proposal,
            operation=Op.CREATE,
            target_type="Relationship",
            target_id=self.rel.id,
            after={"subject_id": str(self.alice.id), "object_id": str(self.ops.id), "is_active": True},
        )

        everything = self.bundle()["provenance"]["relationships"][str(self.rel.id)]
        self.assertEqual(everything["entries"][0]["changes"][0]["after"], "Alice → Ops")

        # A relationship is only published when both of its ends are, so narrowing the scope
        # removes the relationship, its history and every mention of the other end.
        narrowed = self.bundle({"scope": {"traversal": {"roots": [str(self.alice.id)], "depth": 0}}})
        self.assertNotIn("Ops", json.dumps(narrowed))
        self.assertEqual(narrowed["provenance"]["relationships"], {})

    def test_outside_label_is_what_an_unlisted_endpoint_is_called(self):
        # The wording is part of the privacy contract (see the module docstring in bundle.py).
        self.assertEqual(OUTSIDE_PUBLICATION, "an object outside this publication")


class LeakTests(BundleFixture):

    def test_nothing_about_excluded_content_appears_anywhere(self):
        secret_type = self.team_type
        secret = self.make_object(secret_type, "Project Zeta Secret")
        self.commit(2, "Object", secret.id, "name", "Project Zeta Old", "Project Zeta Secret", note="Zeta rename")
        self.make_relationship(self.alice, secret)

        text = json.dumps(self.bundle({"scope": {"object_types": {"excluded": [str(secret_type.id)]}}}))

        for needle in ("Zeta", str(secret.id), str(secret_type.id), "Team", "Ops"):
            with self.subTest(needle=needle):
                self.assertNotIn(needle, text)
