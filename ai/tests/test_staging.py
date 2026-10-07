"""
Speculative staging and final commit (ai.services.staging): staging never
keeps anything, the projected delta is semantic, and commit is the atomic
commit-or-discard gate.
"""

from model.models.evidence_reference import EvidenceReference
from model.models.object import Object
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship import Relationship

from ai.services.change_set import ChangeSet
from ai.services.evidence_bundle import EvidenceBundle
from ai.services.operation_definitions import RECONCILE, RECONCILE_POLICY
from ai.services.resolution import resolve_change_set
from ai.services.semantic.index import SemanticModelIndex
from ai.services.staging import commit_proposal, stage_and_validate
from ai.tests.rugby import FLYER_ASSETS, RugbyFixture


class StagingTests(RugbyFixture):

    def resolution(self, **kwargs):
        index = SemanticModelIndex.load(self.model)
        change_set = ChangeSet.model_validate({"actions": self.chain_actions(**kwargs)})
        resolution = resolve_change_set(
            change_set, model=self.model, index=index, policy=RECONCILE_POLICY, bundle=EvidenceBundle.from_assets(FLYER_ASSETS),
        )
        self.assertEqual(resolution.issues, [])
        return resolution, index

    def counts(self):
        return (
            Object.objects.filter(model=self.model).count(),
            Relationship.objects.filter(model=self.model).count(),
            Proposal.objects.filter(model=self.model).count(),
            ProposalChange.objects.count(),
            EvidenceReference.objects.count(),
        )

    def test_a_clean_stage_keeps_nothing_and_projects_a_semantic_delta(self):
        resolution, index = self.resolution()
        before = self.counts()

        staged = stage_and_validate(model=self.model, user=self.user, operation=RECONCILE, resolution=resolution, index=index)

        self.assertEqual(staged.issues, [])
        self.assertEqual(self.counts(), before)
        eden = next(e for e in staged.delta.entries if e.after and e.after.get("name") == "Eden Park")
        self.assertEqual(eden.change, "created")
        self.assertEqual(eden.action_ids, ["a9"])
        self.assertEqual(eden.after["key"], "eden_park")
        self.assertEqual(eden.after["attributes"], {"capacity": 50000})
        self.assertIsNone(eden.before)

    def test_a_failing_stage_keeps_nothing_and_reports_validation_issues(self):
        resolution, index = self.resolution(include_fiji=False)
        before = self.counts()

        staged = stage_and_validate(model=self.model, user=self.user, operation=RECONCILE, resolution=resolution, index=index)

        self.assertIn("object_cardinality_minimum", [i.code for i in staged.issues])
        self.assertIsNone(staged.delta)
        self.assertEqual(self.counts(), before)

    def test_commit_keeps_a_working_proposal_with_evidence_and_no_canonical_change(self):
        resolution, _ = self.resolution()
        objects_before = Object.objects.filter(model=self.model).count()

        result = commit_proposal(model=self.model, user=self.user, operation=RECONCILE, resolution=resolution, summary="Notes")

        self.assertEqual(result.issues, [])
        self.assertEqual(result.proposal.status, Proposal.Status.WORKING)
        self.assertEqual(result.proposal.source, Proposal.Source.AI)
        self.assertEqual(result.proposal.summary, "Notes")
        self.assertTrue(EvidenceReference.objects.filter(change__proposal=result.proposal, note="Eden Park capacity: 50000").exists())
        self.assertEqual(Object.objects.filter(model=self.model).count(), objects_before)

    def test_commit_is_abandoned_when_the_caller_no_longer_wants_it(self):
        resolution, _ = self.resolution()
        before = self.counts()

        result = commit_proposal(
            model=self.model, user=self.user, operation=RECONCILE, resolution=resolution, summary="", should_commit=lambda: False
        )

        self.assertIsNone(result.proposal)
        self.assertEqual(result.issues, [])
        self.assertEqual(self.counts(), before)
