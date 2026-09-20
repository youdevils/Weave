"""
The Proposal/Evidence service additions Data Import relies on: an always-new
working proposal under a concurrency-safe live cap, bulk change recording that
matches record_change, and bulk evidence.
"""

import threading
import time
import uuid
from unittest.mock import patch

from django.conf import settings
from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings

from account.models import CustomUser
from model.models.evidence_reference import EvidenceReference
from model.models.model import Model
from model.models.proposal import Proposal, ProposalChange
from model.services.proposal.evidence import MAX_EVIDENCE_PER_CHANGE, EvidenceService
from model.services.proposal.proposal import ProposalLimitReached, ProposalService
from model.views.active_proposal import live_proposals_queryset
from workspace.models import Workspace


class Base(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="W")
        cls.user = CustomUser.objects.create_user(email="u@example.com", password="pw")
        cls.other_user = CustomUser.objects.create_user(email="o@example.com", password="pw")
        cls.model = Model.objects.create(workspace=cls.workspace, name="M", revision=4)
        cls.other_model = Model.objects.create(workspace=cls.workspace, name="M2")


class LiveQuerysetTests(Base):

    def make(self, user=None, model=None, **fields):
        return Proposal.objects.create(model=model or self.model, created_by=user or self.user, **fields)

    def test_live_means_working_failed_queued_processing_or_unacknowledged_completed(self):
        from django.utils import timezone

        live = [
            self.make(status=Proposal.Status.WORKING),
            self.make(status=Proposal.Status.FAILED),
            self.make(status=Proposal.Status.QUEUED),
            self.make(status=Proposal.Status.PROCESSING),
            self.make(status=Proposal.Status.COMPLETED),
        ]
        self.make(status=Proposal.Status.COMPLETED, acknowledged_at=timezone.now())

        self.assertEqual(set(ProposalService.live_queryset(self.model, self.user)), set(live))

    def test_it_is_scoped_to_one_user_on_one_model_as_before(self):
        mine = self.make()
        self.make(user=self.other_user)
        self.make(model=self.other_model)

        self.assertEqual(list(ProposalService.live_queryset(self.model, self.user)), [mine])

    def test_the_view_layer_helper_returns_exactly_the_same_thing(self):
        self.make()
        self.make(status=Proposal.Status.QUEUED)
        self.make(user=self.other_user)

        self.assertEqual(
            list(live_proposals_queryset(self.model, self.user).order_by("id")),
            list(ProposalService.live_queryset(self.model, self.user).order_by("id")),
        )


class CreateWorkingTests(Base):

    def test_it_always_creates_a_new_working_user_proposal_at_the_current_revision(self):
        first = ProposalService.create_working(self.model, self.user, title="A" * 300, summary="note")
        second = ProposalService.create_working(self.model, self.user)

        self.assertNotEqual(first.id, second.id)
        self.assertEqual(first.status, Proposal.Status.WORKING)
        self.assertEqual(first.source, Proposal.Source.USER)
        self.assertEqual(first.base_revision, 4)
        self.assertEqual(len(first.title), 200)
        self.assertEqual(first.summary, "note")

    def test_the_cap_is_the_existing_setting_and_per_user(self):
        for _ in range(settings.PROPOSAL_MAX_LIVE_PER_MODEL):
            ProposalService.create_working(self.model, self.user)

        with self.assertRaises(ProposalLimitReached) as raised:
            ProposalService.create_working(self.model, self.user)

        self.assertIn(str(settings.PROPOSAL_MAX_LIVE_PER_MODEL), str(raised.exception))
        # Another user, and another model, are unaffected.
        ProposalService.create_working(self.model, self.other_user)
        ProposalService.create_working(self.other_model, self.user)

    @override_settings(PROPOSAL_MAX_LIVE_PER_MODEL=1)
    def test_the_cap_follows_the_setting(self):
        ProposalService.create_working(self.model, self.user)

        with self.assertRaises(ProposalLimitReached):
            ProposalService.create_working(self.model, self.user)

    def test_a_refused_creation_leaves_nothing_behind(self):
        for _ in range(settings.PROPOSAL_MAX_LIVE_PER_MODEL):
            ProposalService.create_working(self.model, self.user)

        with self.assertRaises(ProposalLimitReached):
            ProposalService.create_working(self.model, self.user)

        self.assertEqual(Proposal.objects.filter(model=self.model).count(), settings.PROPOSAL_MAX_LIVE_PER_MODEL)


class ConcurrentCapTests(TransactionTestCase):
    """Two simultaneous creations at one below the cap: exactly one may win."""

    def test_two_concurrent_creations_cannot_both_take_the_last_slot(self):
        workspace = Workspace.objects.create(name="W")
        user = CustomUser.objects.create_user(email="race@example.com", password="pw")
        model = Model.objects.create(workspace=workspace, name="M")

        for _ in range(settings.PROPOSAL_MAX_LIVE_PER_MODEL - 1):
            ProposalService.create_working(model, user)

        real_assert_capacity = ProposalService.assert_capacity

        def slow_assert_capacity(*args, **kwargs):
            # Widen the window between "count" and "insert" so that, without the
            # Model row lock, both callers would observe the free slot.
            real_assert_capacity(*args, **kwargs)
            time.sleep(0.5)

        barrier = threading.Barrier(2)
        outcomes = []

        def attempt():
            try:
                barrier.wait(timeout=10)
                ProposalService.create_working(model, user)
                outcomes.append("created")
            except ProposalLimitReached:
                outcomes.append("refused")
            except Exception as error:  # pragma: no cover - reported by the assertion below
                outcomes.append(f"error: {error!r}")
            finally:
                connection.close()

        with patch.object(ProposalService, "assert_capacity", staticmethod(slow_assert_capacity)):
            threads = [threading.Thread(target=attempt) for _ in range(2)]

            for thread in threads:
                thread.start()

            for thread in threads:
                thread.join(timeout=30)

        self.assertEqual(sorted(outcomes), ["created", "refused"], outcomes)
        self.assertEqual(
            Proposal.objects.filter(model=model, created_by=user).count(),
            settings.PROPOSAL_MAX_LIVE_PER_MODEL,
        )


class BulkRecordingTests(Base):

    def spec(self, index, **overrides):
        base = dict(
            operation="update", target_type="Object", target_id=uuid.uuid4(),
            parent_type="ObjectType", parent_id=uuid.uuid4(),
            before={"field": "name", "value": f"old {index}"},
            after={"field": "name", "value": f"new {index}"},
        )
        base.update(overrides)
        return base

    def test_bulk_recording_matches_record_change_row_for_row(self):
        specs = [self.spec(0), self.spec(1, operation="create", before=None, after={"name": "x", "attributes": {}})]
        one_by_one = ProposalService.create_working(self.model, self.user)
        in_bulk = ProposalService.create_working(self.model, self.user)

        for spec in specs:
            ProposalService.record_change(
                proposal=one_by_one, field=(spec["after"] or {}).get("field"), **spec
            )

        ProposalService.record_changes_bulk(proposal=in_bulk, specs=specs)

        def shape(proposal):
            return sorted(
                (
                    c.source, c.operation, c.target_type, str(c.target_id), c.parent_type,
                    str(c.parent_id), repr(c.before), repr(c.after), c.review_status,
                )
                for c in proposal.changes.all()
            )

        self.assertEqual(shape(one_by_one), shape(in_bulk))

    def test_it_returns_the_created_changes_with_ids(self):
        proposal = ProposalService.create_working(self.model, self.user)

        created = ProposalService.record_changes_bulk(proposal=proposal, specs=[self.spec(i) for i in range(3)])

        self.assertEqual(len(created), 3)
        self.assertEqual({c.id for c in created}, set(proposal.changes.values_list("id", flat=True)))

    def test_it_resets_validation_once(self):
        proposal = ProposalService.create_working(self.model, self.user)
        Proposal.objects.filter(pk=proposal.pk).update(validation_status=Proposal.ValidationStatus.VALID)
        proposal.refresh_from_db()

        ProposalService.record_changes_bulk(proposal=proposal, specs=[self.spec(0)])

        proposal.refresh_from_db()
        self.assertEqual(proposal.validation_status, Proposal.ValidationStatus.NOT_VALIDATED)

    def test_an_ai_proposal_records_ai_changes(self):
        proposal = ProposalService.get_or_create_ai_proposal(self.model, self.user)

        (change,) = ProposalService.record_changes_bulk(proposal=proposal, specs=[self.spec(0)])

        self.assertEqual(change.source, ProposalChange.Source.AI)

    def test_a_locked_proposal_refuses_changes(self):
        proposal = ProposalService.create_working(self.model, self.user)
        Proposal.objects.filter(pk=proposal.pk).update(status=Proposal.Status.QUEUED)
        proposal.refresh_from_db()

        with self.assertRaises(ValueError):
            ProposalService.record_changes_bulk(proposal=proposal, specs=[self.spec(0)])

        self.assertFalse(ProposalChange.objects.exists())


class BulkEvidenceTests(Base):

    def setUp(self):
        self.proposal = ProposalService.create_working(self.model, self.user)
        self.changes = ProposalService.record_changes_bulk(
            proposal=self.proposal,
            specs=[
                dict(operation="update", target_type="Object", target_id=uuid.uuid4(), parent_type="ObjectType",
                     parent_id=uuid.uuid4(), before={"field": "name", "value": "a"}, after={"field": "name", "value": str(i)})
                for i in range(3)
            ],
        )

    def ids(self):
        return [change.id for change in self.changes]

    def test_each_change_gets_its_own_independent_reference(self):
        created = EvidenceService.add_for_changes(self.proposal, self.ids(), " abc.csv ", "", "Data import: a")

        self.assertEqual(len(created), 3)
        self.assertEqual({e.change_id for e in created}, set(self.ids()))
        self.assertEqual({e.source for e in EvidenceReference.objects.all()}, {"abc.csv"})
        self.assertEqual(EvidenceReference.objects.count(), 3)

    def test_input_is_cleaned_like_add(self):
        with self.assertRaises(ValueError):
            EvidenceService.add_for_changes(self.proposal, self.ids(), "   ")

        with self.assertRaises(ValueError):
            EvidenceService.add_for_changes(self.proposal, self.ids(), "x" * 501)

        self.assertFalse(EvidenceReference.objects.exists())

    def test_a_change_of_another_proposal_is_not_found_and_nothing_is_written(self):
        other = ProposalService.create_working(self.model, self.other_user)
        (foreign,) = ProposalService.record_changes_bulk(
            proposal=other,
            specs=[dict(operation="update", target_type="Object", target_id=uuid.uuid4(), parent_type="ObjectType",
                        parent_id=uuid.uuid4(), before=None, after={"field": "name", "value": "z"})],
        )

        with self.assertRaises(ProposalChange.DoesNotExist):
            EvidenceService.add_for_changes(self.proposal, self.ids() + [foreign.id], "abc.csv")

        self.assertFalse(EvidenceReference.objects.exists())

    def test_the_per_change_cap_applies(self):
        for index in range(MAX_EVIDENCE_PER_CHANGE):
            EvidenceService.add(self.proposal, self.changes[0].id, f"s{index}")

        with self.assertRaises(ValueError):
            EvidenceService.add_for_changes(self.proposal, self.ids(), "abc.csv")

    def test_a_locked_proposal_refuses_evidence(self):
        Proposal.objects.filter(pk=self.proposal.pk).update(status=Proposal.Status.QUEUED)
        self.proposal.refresh_from_db()

        with self.assertRaises(ValueError):
            EvidenceService.add_for_changes(self.proposal, self.ids(), "abc.csv")
