import re
import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship_type import RelationshipType
from model.views.tests.proposal_test_utils import activate_proposal
from workspace.models import Workspace, WorkspaceMember

CARD = re.compile(r"<article\b[^>]*data-index-item.*?</article>", re.DOTALL)
CARD_NAME = re.compile(r'model-index-card-link"\s*>\s*(.*?)\s*</a>', re.DOTALL)


def cards(response):
    """Rendered index cards keyed by displayed name."""
    html = response.content.decode()
    return {
        CARD_NAME.search(block).group(1): block for block in CARD.findall(html)
    }


def is_hidden(card):
    return bool(re.match(r"<article[^>]*\bhidden\b[^>]*>", card))


class IndexPageTestBase(TestCase):
    """Two object types and two relationship types, one of each retired."""

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")
        cls.user = CustomUser.objects.create_user(
            email="user@example.com",
            password="test-password",
        )
        WorkspaceMember.objects.create(
            workspace=cls.workspace,
            user=cls.user,
            role=WorkspaceMember.Role.OWNER,
        )
        cls.model = Model.objects.create(
            workspace=cls.workspace,
            name="Test Model",
            revision=1,
        )

        cls.customer = ObjectType.objects.create(
            model=cls.model, name="Customer", key="cust_id", is_active=True
        )
        cls.legacy = ObjectType.objects.create(
            model=cls.model, name="Legacy Account", key="legacy_acct",
            is_active=False,
        )
        cls.owns = RelationshipType.objects.create(
            model=cls.model, name="Owns", key="owns_link", is_active=True
        )
        cls.former = RelationshipType.objects.create(
            model=cls.model, name="Formerly Owned", key="former_link",
            is_active=False,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def get(self, url_name):
        return self.client.get(reverse(url_name, args=[self.model.id]))

    def working_proposal(self):
        proposal = Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.WORKING,
        )
        activate_proposal(self.client, self.model.id, proposal)
        return proposal

    def propose_update(self, proposal, target_type, target_id, field, value):
        ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.UPDATE,
            target_type=target_type,
            target_id=target_id,
            after={"field": field, "value": value},
        )

    def propose_create(self, proposal, target_type, **after):
        target_id = uuid.uuid4()
        ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.CREATE,
            target_type=target_type,
            target_id=target_id,
            parent_type="Model",
            parent_id=self.model.id,
            after={
                "description": "",
                "sort_order": 0,
                "is_active": True,
                **after,
            },
        )
        return target_id


class SharedIndexPatternTests(IndexPageTestBase):
    """Every index page has the same header identity and control bar."""

    PAGES = [
        ("model:object_types", "Define model"),
        ("model:relationship_types", "Define model"),
        ("model:data_object_types", "Model data"),
        ("model:data_relationship_types", "Model data"),
    ]

    def test_each_page_has_its_eyebrow_and_shared_wrapper(self):
        for url_name, eyebrow in self.PAGES:
            with self.subTest(page=url_name):
                response = self.get(url_name)
                self.assertContains(
                    response,
                    f'<div class="model-page-eyebrow">{eyebrow}</div>',
                    html=True,
                )
                self.assertContains(response, 'class="model-index"')
                self.assertNotContains(response, "model-object-types")

    def test_each_page_has_search_and_active_all_with_active_default(self):
        for url_name, _ in self.PAGES:
            with self.subTest(page=url_name):
                content = self.get(url_name).content.decode()
                self.assertIn("data-index-search", content)
                self.assertRegex(
                    content,
                    r'data-index-filter-value="active"\s+aria-pressed="true"',
                )
                self.assertRegex(
                    content,
                    r'data-index-filter-value="all"\s+aria-pressed="false"',
                )
                self.assertIn("data-index-noresults", content)

    def test_retired_types_are_hidden_by_default_active_types_are_not(self):
        cases = [
            ("model:object_types", "Customer", "Legacy Account"),
            ("model:relationship_types", "Owns", "Formerly Owned"),
            ("model:data_object_types", "Customer", "Legacy Account"),
            ("model:data_relationship_types", "Owns", "Formerly Owned"),
        ]
        for url_name, active_name, retired_name in cases:
            with self.subTest(page=url_name):
                found = cards(self.get(url_name))
                self.assertFalse(is_hidden(found[active_name]))
                self.assertIn('data-active="true"', found[active_name])
                self.assertTrue(is_hidden(found[retired_name]))
                self.assertIn('data-active="false"', found[retired_name])
                self.assertIn("Retired", found[retired_name])

    def test_search_text_holds_name_and_key(self):
        cases = [
            ("model:object_types", "Customer", "customer cust_id"),
            ("model:relationship_types", "Owns", "owns owns_link"),
            ("model:data_object_types", "Customer", "customer cust_id"),
            ("model:data_relationship_types", "Owns", "owns owns_link"),
        ]
        for url_name, name, search in cases:
            with self.subTest(page=url_name):
                found = cards(self.get(url_name))
                self.assertIn(f'data-search="{search}"', found[name])

    def test_empty_model_shows_empty_state_without_controls(self):
        empty = Model.objects.create(
            workspace=self.workspace, name="Empty", revision=1
        )
        for url_name, message in [
            ("model:object_types", "No object types yet"),
            ("model:relationship_types", "No relationship types yet"),
            ("model:data_object_types", "No object types yet"),
            ("model:data_relationship_types", "No relationship types yet"),
        ]:
            with self.subTest(page=url_name):
                response = self.client.get(reverse(url_name, args=[empty.id]))
                self.assertContains(response, message)
                self.assertNotContains(response, "data-index-search")


class ObjectTypesIndexTests(IndexPageTestBase):

    def test_links_and_create_action_are_preserved(self):
        response = self.get("model:object_types")
        self.assertContains(
            response,
            reverse("model:object_type_create", args=[self.model.id]),
        )
        self.assertContains(
            response,
            reverse(
                "model:object_type_edit", args=[self.model.id, self.customer.id]
            ),
        )
        self.assertContains(response, "0 attributes")

    def test_no_discard_without_a_proposal(self):
        self.assertNotContains(
            self.get("model:object_types"), "data-discard-object-type"
        )

    def test_proposed_create_is_visible_with_badge_and_discard(self):
        proposal = self.working_proposal()
        new_id = self.propose_create(
            proposal, "ObjectType", name="Vendor", key="vendor"
        )

        card = cards(self.get("model:object_types"))["Vendor"]

        self.assertFalse(is_hidden(card))
        self.assertIn("Proposed", card)
        self.assertNotIn("Proposed change", card)
        self.assertIn("data-discard-object-type", card)
        self.assertIn(f'data-object-type-id="{new_id}"', card)

    def test_proposed_edit_on_active_type_stays_in_active_view(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "ObjectType", self.customer.id, "description", "Updated"
        )

        card = cards(self.get("model:object_types"))["Customer"]

        self.assertFalse(is_hidden(card))
        self.assertIn("Proposed change", card)
        self.assertIn("data-discard-object-type", card)

    def test_proposed_retirement_of_active_type_stays_in_active_view(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "ObjectType", self.customer.id, "is_active", False
        )

        card = cards(self.get("model:object_types"))["Customer"]

        self.assertFalse(is_hidden(card))
        self.assertIn('data-active="true"', card)
        self.assertIn("Retired", card)
        self.assertIn("Proposed change", card)

    def test_proposed_reactivation_of_retired_type_only_shows_under_all(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "ObjectType", self.legacy.id, "is_active", True
        )

        card = cards(self.get("model:object_types"))["Legacy Account"]

        self.assertTrue(is_hidden(card))
        self.assertIn('data-active="false"', card)
        self.assertNotIn("Retired", card)
        self.assertIn("Proposed change", card)

    def test_discard_endpoint_is_unchanged(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "ObjectType", self.customer.id, "description", "Updated"
        )

        response = self.client.post(
            reverse("model:object_types", args=[self.model.id]),
            {
                "action": "discard_object_type_proposal",
                "object_type_id": str(self.customer.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])
        self.assertFalse(proposal.changes.exists())


class RelationshipTypesIndexTests(IndexPageTestBase):

    def test_links_create_action_and_rule_count_are_preserved(self):
        response = self.get("model:relationship_types")
        self.assertContains(
            response,
            reverse("model:relationship_type_create", args=[self.model.id]),
        )
        self.assertContains(
            response,
            reverse(
                "model:relationship_type_edit",
                args=[self.model.id, self.owns.id],
            ),
        )
        self.assertContains(response, "0 rules")
        self.assertContains(response, "0 attributes")

    def test_proposed_create_is_visible_with_badge_and_discard(self):
        proposal = self.working_proposal()
        new_id = self.propose_create(
            proposal, "RelationshipType", name="Manages", key="manages"
        )

        card = cards(self.get("model:relationship_types"))["Manages"]

        self.assertFalse(is_hidden(card))
        self.assertIn("Proposed", card)
        self.assertNotIn("Proposed change", card)
        self.assertIn("data-discard-relationship-type", card)
        self.assertIn(f'data-relationship-type-id="{new_id}"', card)

    def test_proposed_retirement_of_active_type_stays_in_active_view(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "RelationshipType", self.owns.id, "is_active", False
        )

        card = cards(self.get("model:relationship_types"))["Owns"]

        self.assertFalse(is_hidden(card))
        self.assertIn("Retired", card)
        self.assertIn("Proposed change", card)

    def test_proposed_reactivation_of_retired_type_only_shows_under_all(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "RelationshipType", self.former.id, "is_active", True
        )

        card = cards(self.get("model:relationship_types"))["Formerly Owned"]

        self.assertTrue(is_hidden(card))

    def test_discard_endpoint_is_unchanged(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "RelationshipType", self.owns.id, "description", "Updated"
        )

        response = self.client.post(
            reverse("model:relationship_types", args=[self.model.id]),
            {
                "action": "discard_relationship_type_proposal",
                "relationship_type_id": str(self.owns.id),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])


class DataTypeChoosersTests(IndexPageTestBase):

    def test_object_chooser_links_to_records_and_shows_record_count(self):
        response = self.get("model:data_object_types")
        self.assertContains(
            response,
            reverse("model:data_objects", args=[self.model.id, self.customer.id]),
        )
        self.assertContains(response, "0 records")

    def test_relationship_chooser_links_to_records(self):
        response = self.get("model:data_relationship_types")
        self.assertContains(
            response,
            reverse(
                "model:data_relationships", args=[self.model.id, self.owns.id]
            ),
        )

    def test_proposal_only_type_is_listed_and_active(self):
        proposal = self.working_proposal()
        self.propose_create(proposal, "ObjectType", name="Vendor", key="vendor")

        card = cards(self.get("model:data_object_types"))["Vendor"]

        self.assertFalse(is_hidden(card))
        self.assertNotIn("data-discard", card)
