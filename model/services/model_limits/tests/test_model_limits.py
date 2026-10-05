from django.test import TestCase

from account.models import CustomUser
from model.models.model import Model
from model.services.model_limits import ModelLimitReached, ensure_can_create_model
from workspace.models import Workspace, WorkspaceMember


class EnsureCanCreateModelTests(TestCase):
    """
    Model capacity boundary tests per plan -- model_limit is a pure count of
    currently-existing Models in the user's own Workspace, with no
    archive/retire concept, so a limit reached at N is no longer reached
    once a Model is deleted.
    """

    @classmethod
    def setUpTestData(cls):
        cls.workspace = Workspace.objects.create(name="Test Workspace")

        cls.learner = CustomUser.objects.create_user(email="learner@example.com", password="pw")
        cls.communicator = CustomUser.objects.create_user(
            email="communicator@example.com", password="pw", plan=CustomUser.Plan.COMMUNICATOR
        )
        cls.collaborator = CustomUser.objects.create_user(
            email="collaborator@example.com", password="pw", plan=CustomUser.Plan.COLLABORATOR
        )

        for user in (cls.learner, cls.communicator, cls.collaborator):
            WorkspaceMember.objects.create(workspace=cls.workspace, user=user, role=WorkspaceMember.Role.OWNER)

    def _fill_with_models(self, count):
        Model.objects.bulk_create([Model(workspace=self.workspace, name=f"M{i}") for i in range(count)])

    def test_learner_may_create_below_the_cap(self):
        self._fill_with_models(1)

        ensure_can_create_model(self.learner, self.workspace)  # must not raise

    def test_learner_is_blocked_at_the_cap(self):
        self._fill_with_models(2)

        with self.assertRaises(ModelLimitReached):
            ensure_can_create_model(self.learner, self.workspace)

    def test_communicator_is_blocked_at_its_own_higher_cap(self):
        self._fill_with_models(10)

        with self.assertRaises(ModelLimitReached):
            ensure_can_create_model(self.communicator, self.workspace)

    def test_collaborator_may_create_below_its_own_higher_cap(self):
        self._fill_with_models(19)

        ensure_can_create_model(self.collaborator, self.workspace)  # must not raise

    def test_deleting_a_model_frees_a_slot(self):
        self._fill_with_models(2)

        with self.assertRaises(ModelLimitReached):
            ensure_can_create_model(self.learner, self.workspace)

        Model.objects.filter(workspace=self.workspace).first().delete()

        ensure_can_create_model(self.learner, self.workspace)  # must not raise

    def test_error_message_names_the_plan_and_limit(self):
        self._fill_with_models(2)

        with self.assertRaises(ModelLimitReached) as ctx:
            ensure_can_create_model(self.learner, self.workspace)

        self.assertIn("Learner", str(ctx.exception))
        self.assertIn("2", str(ctx.exception))
