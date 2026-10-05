from django.urls import reverse

from account.models import CustomUser
from workspace.models import Workspace, WorkspaceMember

from assisted.models import AssistedTask
from assisted.tests.support import AssistedTestCase


class LandingViewTests(AssistedTestCase):

    def setUp(self):
        self.model = self.make_model()

    def landing_url(self):
        return reverse("assisted:landing", args=[self.model.id])

    def test_shows_available_assistance_cards(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.landing_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Reconcile")
        self.assertContains(response, "Change")
        self.assertContains(response, "Assess")

    def test_empty_state_still_foregrounds_available_assistance(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.landing_url())

        self.assertContains(response, "No assisted work yet for this model")
        self.assertContains(response, "Available assistance")

    def test_current_work_shown_when_active_task_exists(self):
        self.client.force_login(self.owner)

        AssistedTask.objects.create(
            workspace=self.workspace,
            creator=self.owner,
            operation=AssistedTask.Operation.RECONCILE,
            model=self.model,
            status=AssistedTask.Status.RUNNING,
            submitted_intent="Reconcile the latest status update.",
        )

        response = self.client.get(self.landing_url())

        self.assertContains(response, "Current work")
        self.assertContains(response, "Reconcile the latest status update")

    def test_recent_work_lists_completed_tasks(self):
        self.client.force_login(self.owner)

        AssistedTask.objects.create(
            workspace=self.workspace,
            creator=self.owner,
            operation=AssistedTask.Operation.RECONCILE,
            model=self.model,
            status=AssistedTask.Status.FAILED,
            submitted_intent="An older attempt.",
        )

        response = self.client.get(self.landing_url())

        self.assertContains(response, "Recent assisted work")
        self.assertNotContains(response, "No assisted work yet for this model")

    def test_viewer_can_view_landing(self):
        self.client.force_login(self.viewer)

        response = self.client.get(self.landing_url())

        self.assertEqual(response.status_code, 200)

    def test_non_member_gets_404(self):
        other_workspace = Workspace.objects.create(name="Other Workspace")
        outsider = CustomUser.objects.create_user(email="outsider@example.com", password="pw")
        WorkspaceMember.objects.create(
            workspace=other_workspace,
            user=outsider,
            role=WorkspaceMember.Role.OWNER,
        )
        self.client.force_login(outsider)

        response = self.client.get(self.landing_url())

        self.assertEqual(response.status_code, 404)


class LandingViewEntitlementTests(AssistedTestCase):
    """
    The landing page gates the whole "Available assistance" section on the
    acting user's Assisted entitlement, rather than each of the three
    operation cards individually, so a plan without Assisted Work never
    walks the user into a 403 through the normal landing-page flow. The
    backend gate (assisted.access.get_assisted_workable_model) is unchanged
    and still authoritative -- see ReconcileEntryViewTests in
    test_entry_views.py.
    """

    def setUp(self):
        self.model = self.make_model()

    def landing_url(self):
        return reverse("assisted:landing", args=[self.model.id])

    def test_collaborator_sees_the_actionable_entry_cards(self):
        self.client.force_login(self.owner)

        response = self.client.get(self.landing_url())

        self.assertContains(response, "Available assistance")
        self.assertContains(response, reverse("assisted:reconcile", args=[self.model.id]))
        self.assertContains(response, reverse("assisted:change", args=[self.model.id]))
        self.assertContains(response, reverse("assisted:assess", args=[self.model.id]))
        self.assertNotContains(response, "Assisted Work is available on the Collaborator plan.")

    def test_learner_sees_the_unavailable_state_with_no_entry_links(self):
        self.owner.plan = CustomUser.Plan.LEARNER
        self.owner.save(update_fields=["plan"])
        self.client.force_login(self.owner)

        response = self.client.get(self.landing_url())

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Assisted Work is available on the Collaborator plan.")
        self.assertNotContains(response, "Available assistance")
        self.assertNotContains(response, reverse("assisted:reconcile", args=[self.model.id]))
        self.assertNotContains(response, reverse("assisted:change", args=[self.model.id]))
        self.assertNotContains(response, reverse("assisted:assess", args=[self.model.id]))

    def test_communicator_also_sees_the_unavailable_state(self):
        self.owner.plan = CustomUser.Plan.COMMUNICATOR
        self.owner.save(update_fields=["plan"])
        self.client.force_login(self.owner)

        response = self.client.get(self.landing_url())

        self.assertContains(response, "Assisted Work is available on the Collaborator plan.")

    def test_unavailable_state_does_not_hide_current_work(self):
        self.owner.plan = CustomUser.Plan.LEARNER
        self.owner.save(update_fields=["plan"])
        self.client.force_login(self.owner)

        AssistedTask.objects.create(
            workspace=self.workspace,
            creator=self.owner,
            operation=AssistedTask.Operation.RECONCILE,
            model=self.model,
            status=AssistedTask.Status.RUNNING,
            submitted_intent="Reconcile the latest status update.",
        )

        response = self.client.get(self.landing_url())

        self.assertContains(response, "Current work")
        self.assertContains(response, "Reconcile the latest status update")
        self.assertContains(response, "Assisted Work is available on the Collaborator plan.")
