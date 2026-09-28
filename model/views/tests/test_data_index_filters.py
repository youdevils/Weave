import re
import uuid

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from model.models.object import Object
from model.models.object_type import ObjectType
from model.models.proposal import Proposal, ProposalChange
from model.models.relationship import Relationship
from model.models.relationship_type import RelationshipType
from model.models.relationship_type_rule import RelationshipTypeRule
from model.views.data_objects import PAGE_SIZE
from model.views.tests.proposal_test_utils import activate_proposal
from workspace.models import Workspace, WorkspaceMember

ACTIVE_PRESSED = re.compile(
    r'name="show"\s+value="active"\s+aria-pressed="true"'
)
ALL_PRESSED = re.compile(r'name="show"\s+value="all"\s+aria-pressed="true"')


class DataIndexFilterBase(TestCase):
    """One object type and one relationship type, each with active and
    retired records."""

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
            workspace=cls.workspace, name="Test Model", revision=1
        )

        cls.app_type = ObjectType.objects.create(
            model=cls.model, name="Application", key="application"
        )
        cls.process_type = ObjectType.objects.create(
            model=cls.model, name="Process", key="process"
        )
        cls.uses_type = RelationshipType.objects.create(
            model=cls.model, name="Uses", key="uses"
        )
        RelationshipTypeRule.objects.create(
            relationship_type=cls.uses_type,
            subject_type=cls.process_type,
            object_type=cls.app_type,
            subject_minimum=0,
            object_minimum=0,
        )

        cls.finance_app = cls.make_app("Finance Ledger")
        cls.retired_finance_app = cls.make_app("Finance Legacy", active=False)
        cls.hr_app = cls.make_app("HR Portal")

        cls.close_process = cls.make_process("Month End Close")
        cls.active_link = cls.make_link(cls.close_process, cls.finance_app)
        cls.retired_link = cls.make_link(
            cls.close_process, cls.retired_finance_app, active=False
        )

    @classmethod
    def make_app(cls, name, active=True):
        return Object.objects.create(
            model=cls.model,
            object_type=cls.app_type,
            name=name,
            is_active=active,
        )

    @classmethod
    def make_process(cls, name):
        return Object.objects.create(
            model=cls.model, object_type=cls.process_type, name=name
        )

    @classmethod
    def make_link(cls, subject, obj, active=True):
        return Relationship.objects.create(
            model=cls.model,
            relationship_type=cls.uses_type,
            subject=subject,
            object=obj,
            is_active=active,
        )

    def setUp(self):
        self.client.force_login(self.user)

    def objects_url(self, **params):
        return self._url("model:data_objects", self.app_type, params)

    def relationships_url(self, **params):
        return self._url("model:data_relationships", self.uses_type, params)

    def _url(self, name, record_type, params):
        url = reverse(name, args=[self.model.id, record_type.id])
        if params:
            url += "?" + "&".join(f"{k}={v}" for k, v in params.items())
        return url

    def names(self, response, key="rows"):
        return [
            getattr(row, "name", None) or row.subject_name + row.object_name
            for row in response.context[key]
        ]

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

    def propose_create(self, proposal, target_type, parent_type, parent_id, **after):
        target_id = uuid.uuid4()
        ProposalChange.objects.create(
            proposal=proposal,
            source=ProposalChange.Source.USER,
            operation=ProposalChange.Operation.CREATE,
            target_type=target_type,
            target_id=target_id,
            parent_type=parent_type,
            parent_id=parent_id,
            after={"description": "", "is_active": True, **after},
        )
        return target_id


class RecordPageHeaderTests(DataIndexFilterBase):

    def test_object_page_header_and_back_link(self):
        response = self.client.get(self.objects_url())

        self.assertContains(response, 'class="model-index model-data-index"')
        self.assertContains(
            response,
            '<div class="model-page-eyebrow">Model data</div>',
            html=True,
        )
        self.assertContains(
            response,
            '<h1 class="model-page-title">Application</h1>',
            html=True,
        )
        self.assertContains(
            response,
            "Browse and edit the data recorded for this object type.",
        )
        self.assertRegex(
            response.content.decode(),
            r'href="%s"\s+class="model-back-link"\s*>\s*<i[^>]*></i>\s*Objects'
            % re.escape(reverse("model:data_object_types", args=[self.model.id])),
        )

    def test_relationship_page_header_and_back_link(self):
        response = self.client.get(self.relationships_url())

        self.assertContains(response, 'class="model-index model-data-index"')
        self.assertContains(
            response,
            '<div class="model-page-eyebrow">Model data</div>',
            html=True,
        )
        self.assertContains(
            response,
            '<h1 class="model-page-title">Uses</h1>',
            html=True,
        )
        self.assertContains(
            response,
            "Browse and edit the data recorded for this relationship type.",
        )
        self.assertRegex(
            response.content.decode(),
            r'href="%s"\s+class="model-back-link"\s*>\s*<i[^>]*></i>\s*Relationships'
            % re.escape(
                reverse("model:data_relationship_types", args=[self.model.id])
            ),
        )

    def test_create_action_is_kept_in_header(self):
        self.assertContains(
            self.client.get(self.objects_url()),
            reverse("model:data_object_create", args=[self.model.id, self.app_type.id]),
        )
        self.assertContains(
            self.client.get(self.relationships_url()),
            reverse(
                "model:data_relationship_create",
                args=[self.model.id, self.uses_type.id],
            ),
        )


class ObjectActiveAllFilterTests(DataIndexFilterBase):

    def test_defaults_to_active(self):
        response = self.client.get(self.objects_url())

        self.assertEqual(response.context["show"], "active")
        self.assertEqual(
            sorted(self.names(response)), ["Finance Ledger", "HR Portal"]
        )
        self.assertRegex(response.content.decode(), ACTIVE_PRESSED)
        self.assertNotRegex(response.content.decode(), ALL_PRESSED)

    def test_all_includes_retired(self):
        response = self.client.get(self.objects_url(show="all"))

        self.assertEqual(
            sorted(self.names(response)),
            ["Finance Ledger", "Finance Legacy", "HR Portal"],
        )
        self.assertRegex(response.content.decode(), ALL_PRESSED)
        self.assertNotRegex(response.content.decode(), ACTIVE_PRESSED)

    def test_unknown_value_falls_back_to_active(self):
        response = self.client.get(self.objects_url(show="retired"))

        self.assertEqual(response.context["show"], "active")
        self.assertNotIn("Finance Legacy", self.names(response))

    def test_search_combines_with_filter(self):
        active = self.client.get(self.objects_url(q="Finance"))
        both = self.client.get(self.objects_url(q="Finance", show="all"))

        self.assertEqual(self.names(active), ["Finance Ledger"])
        self.assertEqual(active.context["total_count"], 1)
        self.assertEqual(
            sorted(self.names(both)), ["Finance Ledger", "Finance Legacy"]
        )
        self.assertEqual(both.context["total_count"], 2)

    def test_apply_and_filter_buttons_keep_search_and_sort_in_one_form(self):
        content = self.client.get(
            self.objects_url(q="Finance", sort="name_desc", show="all")
        ).content.decode()

        self.assertIn('name="q"\n                        value="Finance"', content)
        self.assertRegex(content, r'<option value="name_desc"\s+selected')
        # Apply carries the current filter so Enter in the search box keeps it.
        self.assertRegex(content, r'name="show"\s+value="all"\s+class="btn btn-sm')
        # No page field in the form: changing the filter starts on page 1.
        self.assertNotIn('name="page"', content)

    def test_sort_still_works_with_filter(self):
        response = self.client.get(self.objects_url(sort="name_desc", show="all"))

        self.assertEqual(
            self.names(response),
            ["HR Portal", "Finance Legacy", "Finance Ledger"],
        )

    def test_pagination_preserves_filter_and_encodes_search(self):
        for i in range(PAGE_SIZE + 5):
            Object.objects.create(
                model=self.model,
                object_type=self.app_type,
                name=f"R&D System {i:02d}",
                is_active=i % 2 == 0,
            )

        first = self.client.get(self.objects_url(q="R%26D", show="all"))
        content = first.content.decode()

        self.assertEqual(first.context["total_count"], PAGE_SIZE + 5)
        self.assertIn(
            "?q=R%26D&sort=name&show=all&page=2", content.replace("&amp;", "&")
        )

        second = self.client.get(self.objects_url(q="R%26D", show="all", page=2))
        self.assertEqual(len(second.context["rows"]), 5)

        active = self.client.get(self.objects_url(q="R%26D"))
        self.assertEqual(active.context["total_count"], (PAGE_SIZE + 5 + 1) // 2)

    def test_proposed_retirement_stays_in_active(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "Object", self.finance_app.id, "is_active", False
        )

        response = self.client.get(self.objects_url())
        row = next(r for r in response.context["rows"] if r.name == "Finance Ledger")

        self.assertFalse(row.is_active)
        self.assertTrue(row.is_proposed)
        self.assertContains(response, "Proposed change")

    def test_proposed_reactivation_only_appears_under_all(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "Object", self.retired_finance_app.id, "is_active", True
        )

        self.assertNotIn(
            "Finance Legacy", self.names(self.client.get(self.objects_url()))
        )
        self.assertIn(
            "Finance Legacy",
            self.names(self.client.get(self.objects_url(show="all"))),
        )

    def test_proposed_only_records_follow_their_own_active_state(self):
        proposal = self.working_proposal()
        self.propose_create(
            proposal, "Object", "ObjectType", self.app_type.id,
            name="Draft Active", is_active=True,
        )
        self.propose_create(
            proposal, "Object", "ObjectType", self.app_type.id,
            name="Draft Retired", is_active=False,
        )

        active = self.client.get(self.objects_url())
        both = self.client.get(self.objects_url(show="all"))

        self.assertEqual(
            [r.name for r in active.context["pending_rows"]], ["Draft Active"]
        )
        self.assertEqual(
            sorted(r.name for r in both.context["pending_rows"]),
            ["Draft Active", "Draft Retired"],
        )

    def test_discard_endpoint_is_unchanged(self):
        proposal = self.working_proposal()
        new_id = self.propose_create(
            proposal, "Object", "ObjectType", self.app_type.id, name="Draft"
        )

        response = self.client.post(
            self.objects_url(),
            {"action": "discard_object_proposal", "object_id": str(new_id)},
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_empty_states(self):
        Object.objects.filter(object_type=self.app_type).update(is_active=False)

        only_retired = self.client.get(self.objects_url())
        content = only_retired.content.decode()
        self.assertContains(only_retired, "No active records.")
        self.assertIn(
            "?q=&sort=name&show=all", content.replace("&amp;", "&")
        )
        self.assertContains(only_retired, "Show all")
        self.assertNotContains(only_retired, "Create the first")

        miss = self.client.get(self.objects_url(q="Finance"))
        self.assertContains(miss, "No active records match &ldquo;Finance&rdquo;.")
        self.assertContains(miss, "Clear search")
        self.assertContains(miss, "Show all")

        miss_all = self.client.get(self.objects_url(q="Nothing", show="all"))
        self.assertContains(miss_all, "No records match &ldquo;Nothing&rdquo;.")
        self.assertNotContains(miss_all, "Show all")

    def test_type_without_records_keeps_create_prompt(self):
        Object.objects.filter(object_type=self.app_type).delete()

        response = self.client.get(self.objects_url())

        self.assertContains(response, "No application records yet")
        self.assertContains(response, "Create the first Application record.")


class RelationshipActiveAllFilterTests(DataIndexFilterBase):

    def test_defaults_to_active(self):
        response = self.client.get(self.relationships_url())

        self.assertEqual(response.context["show"], "active")
        self.assertEqual(
            [r.id for r in response.context["rows"]], [self.active_link.id]
        )
        self.assertRegex(response.content.decode(), ACTIVE_PRESSED)

    def test_all_includes_retired(self):
        response = self.client.get(self.relationships_url(show="all"))

        self.assertEqual(
            {r.id for r in response.context["rows"]},
            {self.active_link.id, self.retired_link.id},
        )
        self.assertRegex(response.content.decode(), ALL_PRESSED)

    def test_search_combines_with_filter(self):
        active = self.client.get(self.relationships_url(q="Legacy"))
        both = self.client.get(self.relationships_url(q="Legacy", show="all"))

        self.assertEqual(active.context["total_count"], 0)
        self.assertEqual(
            [r.id for r in both.context["rows"]], [self.retired_link.id]
        )

    def test_pagination_preserves_filter(self):
        for i in range(PAGE_SIZE + 2):
            self.make_link(
                self.close_process, self.make_app(f"App {i:02d}"), active=True
            )

        first = self.client.get(self.relationships_url(show="all"))
        self.assertIn(
            "?q=&sort=subject&show=all&page=2",
            first.content.decode().replace("&amp;", "&"),
        )
        self.assertEqual(first.context["total_count"], PAGE_SIZE + 4)

        second = self.client.get(self.relationships_url(show="all", page=2))
        self.assertEqual(len(second.context["rows"]), 4)

    def test_proposed_retirement_stays_in_active(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "Relationship", self.active_link.id, "is_active", False
        )

        response = self.client.get(self.relationships_url())
        row = response.context["rows"][0]

        self.assertEqual(row.id, self.active_link.id)
        self.assertFalse(row.is_active)
        self.assertTrue(row.is_proposed)

    def test_proposed_reactivation_only_appears_under_all(self):
        proposal = self.working_proposal()
        self.propose_update(
            proposal, "Relationship", self.retired_link.id, "is_active", True
        )

        active = self.client.get(self.relationships_url())
        both = self.client.get(self.relationships_url(show="all"))

        self.assertNotIn(self.retired_link.id, [r.id for r in active.context["rows"]])
        self.assertIn(self.retired_link.id, [r.id for r in both.context["rows"]])

    def test_proposed_only_records_follow_their_own_active_state(self):
        proposal = self.working_proposal()
        other_app = self.make_app("Other App")
        for is_active in (True, False):
            self.propose_create(
                proposal, "Relationship", "RelationshipType", self.uses_type.id,
                subject_id=str(self.close_process.id),
                object_id=str(other_app.id),
                is_active=is_active,
            )

        active = self.client.get(self.relationships_url())
        both = self.client.get(self.relationships_url(show="all"))

        self.assertEqual(len(active.context["pending_rows"]), 1)
        self.assertEqual(len(both.context["pending_rows"]), 2)

    def test_empty_states(self):
        Relationship.objects.filter(relationship_type=self.uses_type).update(
            is_active=False
        )

        only_retired = self.client.get(self.relationships_url())
        self.assertContains(only_retired, "No active relationships.")
        self.assertContains(only_retired, "Show all")

        miss = self.client.get(self.relationships_url(q="Month"))
        self.assertContains(miss, "No active relationships match &ldquo;Month&rdquo;.")

        miss_all = self.client.get(self.relationships_url(q="Nothing", show="all"))
        self.assertContains(miss_all, "No relationships match &ldquo;Nothing&rdquo;.")

    def test_type_without_records_keeps_create_prompt(self):
        Relationship.objects.filter(relationship_type=self.uses_type).delete()

        response = self.client.get(self.relationships_url())

        self.assertContains(response, "No uses relationships yet")
        self.assertContains(response, "Create the first Uses relationship.")
