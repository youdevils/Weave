from account.models import CustomUser
from model.services.model_graph.tests.base import ModelGraphTestCase
from publication.models import Publication
from publication.services.normalise import normalise_config
from publication.services.publishing import load_publishable_dataset
from workspace.models import Workspace, WorkspaceMember


class PublicationTestCase(ModelGraphTestCase):
    """
    ModelGraphTestCase (Person/Team types, ``member_of``) plus workspace
    membership for each role and a second workspace for isolation tests.
    """

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        cls.owner = cls.user
        cls.editor = CustomUser.objects.create_user(email="editor@example.com", password="test-password")
        cls.viewer = CustomUser.objects.create_user(email="viewer@example.com", password="test-password")
        cls.stranger = CustomUser.objects.create_user(email="stranger@example.com", password="test-password")

        WorkspaceMember.objects.create(workspace=cls.workspace, user=cls.owner, role=WorkspaceMember.Role.OWNER)
        WorkspaceMember.objects.create(workspace=cls.workspace, user=cls.editor, role=WorkspaceMember.Role.EDITOR)
        WorkspaceMember.objects.create(workspace=cls.workspace, user=cls.viewer, role=WorkspaceMember.Role.VIEWER)

        cls.other_workspace = Workspace.objects.create(name="Other Workspace")
        WorkspaceMember.objects.create(
            workspace=cls.other_workspace, user=cls.stranger, role=WorkspaceMember.Role.OWNER
        )

    # -- helpers ----------------------------------------------------------------

    def canonical(self):
        """The canonical dataset, exactly as Publishing loads it (no proposal)."""
        return load_publishable_dataset(self.model)

    def normalised(self, raw=None):
        return normalise_config(self.model, raw or {}, self.canonical())

    def make_publication(self, **overrides):
        """A stored publication row (bypassing the publish service)."""
        fields = {
            "model": self.model,
            "sequence": (Publication.objects.filter(model=self.model).count() or 0) + 1,
            "source_revision": self.model.revision,
            "title": "Published",
            "filename": "published.html",
            "content_digest": "0" * 64,
            "published_by": self.owner,
        }
        fields.update(overrides)
        return Publication.objects.create(**fields)
