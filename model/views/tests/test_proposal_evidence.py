from django.db import connection
from django.test.utils import CaptureQueriesContext

from account.models import CustomUser
from model.models.evidence_reference import EvidenceReference
from model.models.proposal import Proposal, ProposalChange
from model.views.tests.test_proposal import ProposalViewTestCase
from workspace.models import WorkspaceMember

HOSTILE = '<img src=x onerror="alert(1)"> & "quotes"'


class EvidenceViewTestCase(ProposalViewTestCase):

    def setUp(self):
        super().setUp()
        self.proposal = self._make_proposal()
        self.change = self.proposal.changes.get()

    def post(self, action, proposal=None, **fields):
        return self.client.post(self.detail_url(proposal or self.proposal), {"action": action, **fields})

    def add_evidence(self, source="Contract.pdf", locator="p. 4", note="Signed", change=None, proposal=None):
        return self.post(
            "add_evidence",
            proposal=proposal,
            change_id=(change or self.change).id,
            source=source,
            locator=locator,
            note=note,
        )


class AddEvidenceViewTests(EvidenceViewTestCase):

    def test_add_persists_and_returns_the_rendered_fragment(self):
        response = self.add_evidence()
        data = response.json()

        self.assertEqual(response.status_code, 200)
        self.assertTrue(data["success"])
        self.assertEqual(data["change_id"], str(self.change.id))
        evidence = EvidenceReference.objects.get()
        self.assertEqual((evidence.change, evidence.source, evidence.locator, evidence.note), (self.change, "Contract.pdf", "p. 4", "Signed"))
        self.assertIn("Contract.pdf", data["html"])
        self.assertIn(f'data-evidence-id="{evidence.id}"', data["html"])
        self.assertIn(f'data-change-id="{self.change.id}"', data["html"])

    def test_evidence_is_optional_locator_and_note_may_be_blank(self):
        response = self.add_evidence(locator="", note="")

        self.assertTrue(response.json()["success"])

    def test_blank_source_is_a_400_with_a_message(self):
        response = self.add_evidence(source="  ")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertIn("source", response.json()["error"].lower())
        self.assertFalse(EvidenceReference.objects.exists())

    def test_unknown_change_is_a_404(self):
        response = self.post("add_evidence", change_id="00000000-0000-0000-0000-000000000000", source="X")

        self.assertEqual(response.status_code, 404)

    def test_malformed_change_id_is_a_404(self):
        response = self.post("add_evidence", change_id="nope", source="X")

        self.assertEqual(response.status_code, 404)

    def test_a_change_of_another_proposal_is_a_404(self):
        other = self._make_proposal()
        foreign_change = other.changes.get()

        response = self.add_evidence(change=foreign_change)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(EvidenceReference.objects.exists())

    def test_another_users_proposal_is_a_404(self):
        stranger = CustomUser.objects.create_user(email="stranger@example.com", password="test-password")
        WorkspaceMember.objects.create(workspace=self.workspace, user=stranger, role=WorkspaceMember.Role.OWNER)
        theirs = Proposal.objects.create(model=self.model, created_by=stranger, status=Proposal.Status.WORKING)
        their_change = ProposalChange.objects.create(
            proposal=theirs,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            before={"field": "description", "value": "a"},
            after={"field": "description", "value": "b"},
        )

        response = self.add_evidence(change=their_change, proposal=theirs)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(EvidenceReference.objects.exists())

    def test_hostile_text_is_escaped_in_the_returned_fragment(self):
        html = self.add_evidence(source=HOSTILE, locator=HOSTILE, note=HOSTILE).json()["html"]

        self.assertNotIn("<img", html)
        self.assertIn("&lt;img", html)

    def test_adding_evidence_does_not_change_review_or_validation_state(self):
        ProposalChange.objects.filter(id=self.change.id).update(review_status=ProposalChange.ReviewStatus.REVIEWED)
        Proposal.objects.filter(id=self.proposal.id).update(validation_status=Proposal.ValidationStatus.VALID)

        self.add_evidence()

        self.change.refresh_from_db()
        self.proposal.refresh_from_db()
        self.assertEqual(self.change.review_status, ProposalChange.ReviewStatus.REVIEWED)
        self.assertEqual(self.proposal.validation_status, Proposal.ValidationStatus.VALID)


class UpdateAndRemoveEvidenceViewTests(EvidenceViewTestCase):

    def setUp(self):
        super().setUp()
        self.add_evidence()
        self.evidence = EvidenceReference.objects.get()

    def test_update_edits_the_evidence_and_returns_the_fragment(self):
        response = self.post(
            "update_evidence", evidence_id=self.evidence.id, source="Spec v2", locator="", note="Rev"
        )

        self.assertTrue(response.json()["success"])
        self.assertIn("Spec v2", response.json()["html"])
        self.evidence.refresh_from_db()
        self.assertEqual((self.evidence.source, self.evidence.locator, self.evidence.note), ("Spec v2", "", "Rev"))

    def test_update_with_blank_source_is_rejected(self):
        response = self.post("update_evidence", evidence_id=self.evidence.id, source="")

        self.assertEqual(response.status_code, 400)
        self.evidence.refresh_from_db()
        self.assertEqual(self.evidence.source, "Contract.pdf")

    def test_remove_deletes_only_the_evidence(self):
        response = self.post("remove_evidence", evidence_id=self.evidence.id)

        self.assertTrue(response.json()["success"])
        self.assertNotIn("Contract.pdf", response.json()["html"])
        self.assertFalse(EvidenceReference.objects.exists())
        self.assertTrue(ProposalChange.objects.filter(id=self.change.id).exists())

    def test_unknown_evidence_is_a_404(self):
        for action in ("update_evidence", "remove_evidence"):
            with self.subTest(action=action):
                response = self.post(action, evidence_id="00000000-0000-0000-0000-000000000000", source="X")

                self.assertEqual(response.status_code, 404)

    def test_evidence_of_another_proposal_is_a_404(self):
        other = self._make_proposal()
        self.add_evidence(change=other.changes.get(), proposal=other)
        foreign = EvidenceReference.objects.get(change__proposal=other)

        for action in ("update_evidence", "remove_evidence"):
            with self.subTest(action=action):
                response = self.post(action, evidence_id=foreign.id, source="X")

                self.assertEqual(response.status_code, 404)

        foreign.refresh_from_db()
        self.assertEqual(foreign.source, "Contract.pdf")

    def test_discarding_the_change_removes_its_evidence(self):
        response = self.post("discard", change_id=self.change.id)

        self.assertTrue(response.json()["success"])
        self.assertFalse(ProposalChange.objects.filter(id=self.change.id).exists())
        self.assertFalse(EvidenceReference.objects.exists())

    def test_deleting_the_proposal_removes_its_evidence(self):
        self.post("abandon")

        self.assertFalse(EvidenceReference.objects.exists())


class LockedProposalEvidenceTests(EvidenceViewTestCase):

    def test_locked_statuses_reject_every_evidence_and_note_action(self):
        self.add_evidence()
        evidence = EvidenceReference.objects.get()

        for status in (Proposal.Status.QUEUED, Proposal.Status.PROCESSING, Proposal.Status.COMPLETED):
            with self.subTest(status=status):
                Proposal.objects.filter(id=self.proposal.id).update(status=status)

                for response in (
                    self.add_evidence(source="Nope"),
                    self.post("update_evidence", evidence_id=evidence.id, source="Nope"),
                    self.post("remove_evidence", evidence_id=evidence.id),
                    self.post("set_change_note", change_note="Nope"),
                ):
                    self.assertEqual(response.status_code, 400)

        evidence.refresh_from_db()
        self.assertEqual(evidence.source, "Contract.pdf")
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.summary, "")

    def test_a_failed_proposal_can_still_be_annotated(self):
        Proposal.objects.filter(id=self.proposal.id).update(status=Proposal.Status.FAILED)

        self.assertTrue(self.add_evidence().json()["success"])
        self.assertTrue(self.post("set_change_note", change_note="Retry").json()["success"])


class ChangeNoteViewTests(EvidenceViewTestCase):

    def test_set_change_note_saves_to_the_proposal(self):
        response = self.post("set_change_note", change_note="  Supplier rename after merger  ")

        self.assertEqual(response.json(), {"success": True, "change_note": "Supplier rename after merger"})
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.summary, "Supplier rename after merger")

    def test_blank_clears_the_note(self):
        self.post("set_change_note", change_note="Something")

        response = self.post("set_change_note", change_note="")

        self.assertEqual(response.json()["change_note"], "")
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.summary, "")

    def test_over_long_note_is_rejected(self):
        response = self.post("set_change_note", change_note="x" * 2001)

        self.assertEqual(response.status_code, 400)
        self.proposal.refresh_from_db()
        self.assertEqual(self.proposal.summary, "")

    def test_the_note_is_not_needed_to_submit(self):
        response = self.post("submit")

        self.assertTrue(response.json()["success"])


class ProposalReviewPageTests(EvidenceViewTestCase):

    def test_page_shows_evidence_and_the_editable_change_note(self):
        self.add_evidence(source="Board minutes", locator="item 7", note="Approved")
        self.post("set_change_note", change_note="Post-merger tidy up")

        response = self.client.get(self.detail_url(self.proposal))

        self.assertContains(response, "Board minutes")
        self.assertContains(response, "item 7")
        self.assertContains(response, "Approved")
        self.assertContains(response, "Post-merger tidy up")
        self.assertContains(response, "model-proposal-change-note-input")
        self.assertContains(response, "Change note")

    def test_change_note_is_offered_but_collapsed_when_empty(self):
        response = self.client.get(self.detail_url(self.proposal))

        self.assertContains(response, 'data-empty="true"')
        self.assertContains(response, "Add change note")

    def test_hostile_text_is_escaped_on_the_page(self):
        self.add_evidence(source=HOSTILE, locator=HOSTILE, note=HOSTILE)
        self.post("set_change_note", change_note=HOSTILE)

        html = self.client.get(self.detail_url(self.proposal)).content.decode()

        self.assertNotIn("<img", html)

    def test_every_change_gets_an_evidence_block(self):
        second = ProposalChange.objects.create(
            proposal=self.proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.UPDATE,
            target_type="Model",
            target_id=self.model.id,
            before={"field": "purpose", "value": "a"},
            after={"field": "purpose", "value": "b"},
        )

        html = self.client.get(self.detail_url(self.proposal)).content.decode()

        for change in (self.change, second):
            self.assertEqual(html.count(f'class="model-proposal-evidence" data-change-id="{change.id}"'), 1)

    def test_query_count_does_not_grow_with_changes_or_evidence(self):
        def count_queries():
            with CaptureQueriesContext(connection) as queries:
                self.assertEqual(self.client.get(self.detail_url(self.proposal)).status_code, 200)
            return len(queries)

        self.add_evidence()
        baseline = count_queries()

        for index in range(6):
            change = ProposalChange.objects.create(
                proposal=self.proposal,
                source=ProposalChange.Source.USER,
                operation=ProposalChange.Operation.UPDATE,
                target_type="Model",
                target_id=self.model.id,
                before={"field": f"field_{index}", "value": "a"},
                after={"field": f"field_{index}", "value": "b"},
            )
            for n in range(3):
                self.add_evidence(source=f"S{index}-{n}", change=change)

        self.assertEqual(count_queries(), baseline)

    def test_completed_proposal_shows_the_change_note_read_only(self):
        self.post("set_change_note", change_note="Why this happened")
        Proposal.objects.filter(id=self.proposal.id).update(status=Proposal.Status.COMPLETED)

        response = self.client.get(self.detail_url(self.proposal))

        self.assertContains(response, "Why this happened")
        self.assertContains(response, "model-proposal-change-note-readonly")
        self.assertNotContains(response, "model-proposal-change-note-input")
        self.assertNotContains(response, "model-proposal-evidence-form")

    def test_no_note_section_when_a_locked_proposal_has_none(self):
        Proposal.objects.filter(id=self.proposal.id).update(status=Proposal.Status.QUEUED)

        response = self.client.get(self.detail_url(self.proposal))

        self.assertNotContains(response, "model-proposal-change-note")
