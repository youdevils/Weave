from html.parser import HTMLParser

from django.test import TestCase
from django.urls import reverse

from account.models import CustomUser
from model.models.model import Model
from model.models.object_type import ObjectType
from model.models.proposal import Proposal
from workspace.models import Workspace, WorkspaceMember


class SidebarParser(HTMLParser):
    """Collects the parts of the sidebar these tests care about."""

    VOID = {"br", "hr", "img", "input", "meta", "link"}

    def __init__(self):
        super().__init__()
        self.stack = []
        self.section_labels = []
        self.section_toggles = 0
        self.group_toggle_labels = []
        self.group_toggle_expanded = []
        self.collapsed_blocks = 0
        self.collapsed_group_blocks = 0
        self.proposal_links = 0
        self._label_text = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        classes = (attrs.get("class") or "").split()

        if "model-nav-children" in classes and "collapsed" in classes:
            if "model-nav-group" in self._ancestor_classes():
                self.collapsed_group_blocks += 1
            else:
                self.collapsed_blocks += 1

        if "model-nav-proposal" in classes:
            self.proposal_links += 1

        if "model-nav-toggle" in classes:
            if "model-nav-section-row" in self._ancestor_classes():
                self.section_toggles += 1
            else:
                self.group_toggle_labels.append(attrs.get("aria-label"))
                self.group_toggle_expanded.append(attrs.get("aria-expanded"))

        if "model-nav-section-label" in classes:
            self._label_text = []

        if tag not in self.VOID:
            self.stack.append((tag, classes))

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return

        while self.stack:
            popped, classes = self.stack.pop()

            if "model-nav-section-label" in classes and self._label_text is not None:
                self.section_labels.append(" ".join("".join(self._label_text).split()))
                self._label_text = None

            if popped == tag:
                break

    def handle_data(self, data):
        if self._label_text is not None:
            self._label_text.append(data)

    def _ancestor_classes(self):
        return {name for _, classes in self.stack for name in classes}


class SidebarTests(TestCase):

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

        ObjectType.objects.create(model=cls.model, name="Person", key="person")

    def setUp(self):
        self.client.force_login(self.user)

    def sidebar(self, url_name, follow=False):
        response = self.client.get(
            reverse(url_name, args=[self.model.id]),
            follow=follow,
        )

        self.assertEqual(response.status_code, 200)

        html = response.content.decode()
        start = html.index('<aside class="model-sidebar">')
        end = html.index("</aside>", start)

        parser = SidebarParser()
        parser.feed(html[start:end])

        return parser, html[start:end]

    def test_top_level_headings_are_renamed(self):
        parser, _ = self.sidebar("model:overview")

        self.assertEqual(
            parser.section_labels,
            ["Understand", "Define model", "Model data", "Proposals", "Publishing"],
        )

    def test_top_level_headings_are_never_collapsible(self):
        # Whichever page is showing -- including ones under no heading at all.
        for url_name in (
            "model:overview",
            "model:explore",
            "model:customise",
            "model:object_types",
            "model:data_object_types",
            "model:proposal_list",
        ):
            with self.subTest(page=url_name):
                parser, _ = self.sidebar(url_name, follow=True)

                self.assertEqual(parser.section_toggles, 0)
                self.assertEqual(parser.collapsed_blocks, 0)

    def test_only_child_sections_can_collapse(self):
        parser, _ = self.sidebar("model:overview")

        self.assertEqual(
            parser.group_toggle_labels,
            [
                "Expand object types",
                "Expand relationships",
                "Expand data objects",
                "Expand data relationships",
            ],
        )

    def test_child_sections_start_collapsed_on_every_page(self):
        for url_name in (
            "model:overview",
            "model:object_types",
            "model:data_object_types",
        ):
            with self.subTest(page=url_name):
                parser, _ = self.sidebar(url_name)

                self.assertEqual(parser.group_toggle_expanded, ["false"] * 4)
                self.assertEqual(parser.collapsed_group_blocks, 4)

    def test_proposals_are_listed_with_no_toggle_to_reveal_them(self):
        Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            title="Add a thing",
        )

        parser, html = self.sidebar("model:overview")

        self.assertEqual(parser.proposal_links, 1)
        self.assertIn("Add a thing", html)
        self.assertNotIn("Collapse proposals", html)
        self.assertNotIn("Expand proposals", html)
        self.assertEqual(parser.collapsed_blocks, 0)
        # Only the four toggled groups are collapsed, never the proposals.
        self.assertEqual(parser.collapsed_group_blocks, 4)

    def test_proposals_heading_has_no_link_or_count_but_keeps_new_proposal_button(self):
        Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            title="Add a thing",
        )

        parser, html = self.sidebar("model:overview")

        self.assertIn("Proposals", parser.section_labels)
        list_url = reverse("model:proposal_list", args=[self.model.id])
        self.assertNotIn(f'href="{list_url}"', html)
        proposals_section = html.split("GOVERN", 1)[1].split("PUBLISHING", 1)[0]
        self.assertNotIn("model-nav-parent", proposals_section)
        self.assertNotIn("model-nav-group", proposals_section)
        self.assertIn('id="model-new-proposal-btn"', html)

    def test_proposal_items_link_to_their_proposal(self):
        proposal = Proposal.objects.create(model=self.model, created_by=self.user)

        _, html = self.sidebar("model:overview")

        self.assertIn(reverse("model:proposal", args=[self.model.id, proposal.id]), html)

    def test_sidebar_represents_the_empty_state(self):
        parser, html = self.sidebar("model:overview")

        self.assertEqual(parser.proposal_links, 0)
        self.assertIn("No open proposals", html)
        self.assertIn('id="model-new-proposal-btn"', html)

    def test_completed_proposal_is_listed_with_its_status(self):
        Proposal.objects.create(
            model=self.model,
            created_by=self.user,
            status=Proposal.Status.COMPLETED,
        )

        parser, html = self.sidebar("model:overview")

        self.assertEqual(parser.proposal_links, 1)
        self.assertIn("model-nav-proposal-status-completed", html)
        self.assertNotIn("No open proposals", html)
