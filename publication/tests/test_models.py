from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, models, transaction
from django.test import override_settings

from model.models.model import Model
from publication.models import ImmutablePublicationError, Publication

from .base import PublicationTestCase


class ImmutabilityTests(PublicationTestCase):

    def test_saving_an_existing_publication_is_refused(self):
        publication = self.make_publication()
        publication.title = "Changed"

        with self.assertRaises(ImmutablePublicationError):
            publication.save()

        self.assertEqual(Publication.objects.get(pk=publication.pk).title, "Published")

    def test_bulk_updates_are_refused(self):
        publication = self.make_publication()

        with self.assertRaises(ImmutablePublicationError):
            Publication.objects.filter(pk=publication.pk).update(title="Changed")
        with self.assertRaises(ImmutablePublicationError):
            Publication.objects.bulk_update([publication], ["title"])

        self.assertEqual(Publication.objects.get(pk=publication.pk).title, "Published")

    def test_related_manager_updates_are_refused_too(self):
        self.make_publication()

        with self.assertRaises(ImmutablePublicationError):
            self.model.publications.update(title="Changed")

    def test_the_admin_offers_no_way_to_add_or_edit(self):
        from django.contrib import admin
        from django.test import RequestFactory

        model_admin = admin.site._registry[Publication]
        request = RequestFactory().get("/")
        request.user = self.owner

        self.assertFalse(model_admin.has_add_permission(request))
        self.assertFalse(model_admin.has_change_permission(request))


class SchemaTests(PublicationTestCase):

    def test_the_rendered_html_is_never_stored_only_the_resolved_data(self):
        # The resolved bundle (data) is stored so View/Download can read it back later; the
        # rendered HTML itself is not: no file, blob or html-named field, ever.
        stored = {field.name: field for field in Publication._meta.get_fields() if hasattr(field, "column")}

        self.assertFalse([f for f in stored.values() if isinstance(f, (models.FileField, models.BinaryField))])
        self.assertFalse([name for name in stored if "html" in name.lower() or "content" == name.lower()])
        self.assertIsInstance(stored["bundle"], models.JSONField)
        # Long free text is limited to the publisher-facing description.
        self.assertEqual(
            [name for name, f in stored.items() if isinstance(f, models.TextField)],
            ["description"],
        )

    def test_sequence_is_unique_per_model(self):
        self.make_publication(sequence=1)

        with self.assertRaises(IntegrityError), transaction.atomic():
            self.make_publication(sequence=1)

        other = Model.objects.create(workspace=self.workspace, name="Other", revision=1)
        self.make_publication(model=other, sequence=1)

    def test_publications_list_newest_sequence_first(self):
        for sequence in (1, 3, 2):
            self.make_publication(sequence=sequence)

        self.assertEqual([p.sequence for p in Publication.objects.filter(model=self.model)], [3, 2, 1])

    def test_deleting_the_model_removes_its_publications(self):
        from model.services.model_deletion import deletion

        self.make_publication()

        deletion.delete_model(self.model)

        self.assertFalse(Publication.objects.exists())
        with self.assertRaises(ObjectDoesNotExist):
            Model.objects.get(pk=self.model.pk)
