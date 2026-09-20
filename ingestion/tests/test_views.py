import json

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.files.uploadhandler import SkipFile
from django.test import Client, SimpleTestCase, override_settings
from django.urls import reverse

from ingestion.models import ImportSource
from ingestion.tests.base import ImportTestCase, csv_bytes
from ingestion.uploads import LimitedUploadHandler
from model.models.evidence_reference import EvidenceReference
from model.models.object import Object
from model.models.proposal import Proposal
from model.services.proposal.proposal import ProposalService

MATCH = {"column": 0, "field": "attribute.app_id", "match": True}
NAME = {"column": 1, "field": "field.name"}

ROWS = [["App ID", "Name"], ["A1", "One"], ["A2", "Two"]]


class ViewTestCase(ImportTestCase):

    def url(self, name, model=None):
        return reverse(f"ingestion:{name}", args=[(model or self.model).id])

    def login(self, user):
        client = Client()
        client.force_login(user)
        return client

    def upload(self, client, rows=ROWS, filename="apps.csv", model=None, data=None):
        return client.post(
            self.url("import_upload", model),
            {"file": SimpleUploadedFile(filename, data if data is not None else csv_bytes(rows), "text/csv")},
        )

    def post_json(self, client, name, body, model=None):
        return client.post(self.url(name, model), json.dumps(body), content_type="application/json")

    def upload_id(self, client, rows=ROWS):
        return self.upload(client, rows).json()["source"]["id"]


class PageAccessTests(ViewTestCase):

    def test_owner_and_editor_can_open_the_page(self):
        for user in (self.owner, self.editor):
            response = self.login(user).get(self.url("assets"))

            self.assertEqual(response.status_code, 200, user.email)
            self.assertContains(response, "Import data")

    def test_a_viewer_cannot(self):
        self.assertEqual(self.login(self.viewer).get(self.url("assets")).status_code, 403)

    def test_a_member_of_another_workspace_gets_a_404(self):
        self.assertEqual(self.login(self.stranger).get(self.url("assets")).status_code, 404)

    def test_anonymous_users_are_sent_to_log_in(self):
        response = Client().get(self.url("assets"))

        self.assertEqual(response.status_code, 302)

    def test_assets_in_the_sidebar_leads_to_the_page_and_is_highlighted(self):
        response = self.login(self.editor).get(self.url("assets"))

        self.assertContains(response, f'href="{self.url("assets")}"')
        self.assertContains(response, "model-nav-item")
        self.assertRegex(response.content.decode(), r'model-nav-item\s+active\s+"\s*>\s*<span>Assets')

    def test_the_sidebar_link_exists_on_other_model_pages(self):
        response = self.login(self.editor).get(reverse("model:overview", args=[self.model.id]))

        self.assertContains(response, f'href="{self.url("assets")}"')

    def test_the_page_offers_only_this_models_canonical_types(self):
        response = self.login(self.editor).get(self.url("assets"))

        bootstrap = response.context["import_bootstrap"]
        names = {t["name"] for t in bootstrap["targets"]["object_types"]}
        ids = {t["type_id"] for t in bootstrap["targets"]["object_types"]}

        self.assertEqual(names, {"Application", "Person"})
        self.assertNotIn(str(self.other_app_type.id), ids)

    def test_type_names_cannot_break_out_of_the_embedded_json(self):
        self.person_type.name = "</script><script>alert(1)</script>"
        self.person_type.save()

        content = self.login(self.editor).get(self.url("assets")).content.decode()

        self.assertNotIn("<script>alert(1)</script>", content)
        self.assertIn("\\u003C/script\\u003E", content)


class UploadTests(ViewTestCase):

    def test_an_upload_returns_the_parsed_file_and_persists_a_staged_source(self):
        response = self.upload(self.login(self.editor))

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["source"]["filename"], "apps.csv")
        self.assertEqual((data["source"]["format"], data["source"]["row_count"], data["source"]["column_count"]), ("csv", 2, 2))
        self.assertEqual([c["header"] for c in data["columns"]], ["App ID", "Name"])
        self.assertEqual(data["sample_rows"], [["A1", "One"], ["A2", "Two"]])
        self.assertEqual(ImportSource.objects.filter(model=self.model, uploaded_by=self.editor).count(), 1)

    def test_a_viewer_cannot_upload_and_nothing_is_stored(self):
        response = self.upload(self.login(self.viewer))

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ImportSource.objects.exists())

    def test_a_stranger_cannot_upload_into_a_model_they_do_not_belong_to(self):
        response = self.upload(self.login(self.stranger))

        self.assertEqual(response.status_code, 404)
        self.assertFalse(ImportSource.objects.exists())

    def test_only_post_is_accepted(self):
        self.assertEqual(self.login(self.editor).get(self.url("import_upload")).status_code, 405)

    def test_a_bad_file_gets_a_clear_error(self):
        response = self.upload(self.login(self.editor), data=b"PK\x03\x04junk", filename="x.xlsx")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "malformed_workbook")
        self.assertFalse(ImportSource.objects.exists())

    def test_an_unsupported_type_is_rejected(self):
        response = self.upload(self.login(self.editor), filename="notes.txt")

        self.assertEqual(response.json()["code"], "unsupported_format")

    def test_no_file_is_a_clear_error(self):
        response = self.login(self.editor).post(self.url("import_upload"), {})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "no_file")

    def test_a_multi_sheet_workbook_is_rejected(self):
        import io
        import openpyxl

        workbook = openpyxl.Workbook()
        workbook.active.append(["A"])
        workbook.create_sheet("Two")
        buffer = io.BytesIO()
        workbook.save(buffer)

        response = self.upload(self.login(self.editor), data=buffer.getvalue(), filename="two.xlsx")

        self.assertEqual(response.json()["code"], "multiple_sheets")

    @override_settings(IMPORT_MAX_FILE_BYTES=100)
    def test_the_size_limit_is_enforced_on_the_bytes_received(self):
        big = csv_bytes([["A"], ["x" * 500]])

        response = self.upload(self.login(self.editor), data=big)

        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["code"], "file_too_large")
        self.assertFalse(ImportSource.objects.exists())

    @override_settings(IMPORT_MAX_FILE_BYTES=200)
    def test_a_file_exactly_at_the_limit_is_accepted(self):
        data = csv_bytes([["A"], ["x" * 190]])
        self.assertLessEqual(len(data), 200)

        response = self.upload(self.login(self.editor), data=data)

        self.assertEqual(response.status_code, 200)

    @override_settings(IMPORT_MAX_FILE_BYTES=100)
    def test_a_declared_length_far_over_the_limit_is_refused_without_reading(self):
        response = self.login(self.editor).post(
            self.url("import_upload"),
            data=b"x",
            content_type="multipart/form-data; boundary=b",
            CONTENT_LENGTH="10000000",
        )

        self.assertEqual(response.status_code, 413)

    def test_csrf_is_enforced_on_upload(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)

        response = self.upload(client)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(ImportSource.objects.exists())

    def test_a_hostile_filename_is_stored_sanitised_and_returned_only_as_json(self):
        response = self.upload(self.login(self.editor), filename='<img src=x onerror=alert(1)>/..\\evil.csv')

        data = response.json()
        self.assertEqual(data["source"]["filename"], "evil.csv")
        self.assertEqual(response["Content-Type"], "application/json")


class LimitedUploadHandlerTests(SimpleTestCase):

    def handler(self, limit):
        handler = LimitedUploadHandler(max_bytes=limit)
        handler.new_file("file", "a.csv", "text/csv", None)
        return handler

    def test_chunks_within_the_limit_are_kept(self):
        handler = self.handler(10)

        handler.receive_data_chunk(b"12345", 0)
        handler.receive_data_chunk(b"12345", 5)
        uploaded = handler.file_complete(10)

        self.assertEqual(uploaded.read(), b"1234512345")
        self.assertFalse(handler.too_large)

    def test_the_limit_applies_to_the_running_total_not_to_a_declared_length(self):
        handler = self.handler(10)

        handler.receive_data_chunk(b"12345", 0)

        with self.assertRaises(SkipFile):
            handler.receive_data_chunk(b"123456", 5)

        self.assertTrue(handler.too_large)
        self.assertIsNone(handler.file_complete(11))

    def test_the_buffer_is_dropped_once_the_limit_is_passed(self):
        handler = self.handler(3)

        with self.assertRaises(SkipFile):
            handler.receive_data_chunk(b"12345678", 0)

        self.assertIsNone(handler._buffer)


class PreviewTests(ViewTestCase):

    def test_a_preview_reports_the_changes_and_writes_nothing(self):
        self.make_app("Old", "A1")
        client = self.login(self.editor)
        source_id = self.upload_id(client)

        response = self.post_json(
            client, "import_preview",
            {"source_id": source_id, "mapping": self.object_mapping(MATCH, NAME)},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["blocked"])
        self.assertEqual((data["summary"]["creates"], data["summary"]["updates"]), (1, 1))
        self.assertEqual(data["change_count"], 2)
        self.assertFalse(Proposal.objects.exists())
        self.assertEqual(Object.objects.count(), 1)

    def test_a_blocked_preview_lists_the_problems(self):
        self.make_app("One", "A1")
        self.make_app("Two", "A1")
        client = self.login(self.editor)
        source_id = self.upload_id(client)

        data = self.post_json(
            client, "import_preview",
            {"source_id": source_id, "mapping": self.object_mapping(MATCH, NAME)},
        ).json()

        self.assertTrue(data["blocked"])
        self.assertEqual(data["problems"][0]["code"], "ambiguous_identity")
        self.assertEqual(data["problem_count"], 1)

    @override_settings(IMPORT_PROBLEMS_SHOWN=2)
    def test_only_the_first_problems_are_listed_but_all_are_counted(self):
        client = self.login(self.editor)
        rows = [["From", "To"]] + [["NOPE", "NOPE"]] * 4
        source_id = self.upload_id(client, rows)

        data = self.post_json(
            client, "import_preview",
            {"source_id": source_id, "mapping": self.relationship_mapping(
                self.by_app_id(0, "endpoint.subject"), self.by_app_id(1, "endpoint.object"))},
        ).json()

        self.assertEqual(len(data["problems"]), 2)
        self.assertEqual(data["problem_count"], 8)

    def test_an_invalid_mapping_is_a_400_with_every_message(self):
        client = self.login(self.editor)
        source_id = self.upload_id(client)

        response = self.post_json(
            client, "import_preview",
            {"source_id": source_id, "mapping": self.object_mapping(
                {"column": 0, "field": "attribute.nope"}, {"column": 7, "field": "field.name"})},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_mapping")
        self.assertEqual(len(response.json()["messages"]), 2)

    def test_a_type_from_another_model_is_rejected(self):
        client = self.login(self.editor)
        source_id = self.upload_id(client)

        response = self.post_json(
            client, "import_preview",
            {"source_id": source_id, "mapping": self.object_mapping(NAME, type_id=self.other_app_type.id)},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["code"], "invalid_target")

    def test_another_editors_staged_upload_is_not_found(self):
        mine = self.upload_id(self.login(self.editor))

        response = self.post_json(
            self.login(self.other_editor), "import_preview",
            {"source_id": mine, "mapping": self.object_mapping(MATCH, NAME)},
        )

        self.assertEqual(response.status_code, 404)

    def test_a_staged_upload_cannot_be_used_through_another_model(self):
        source_id = self.upload_id(self.login(self.editor))
        from workspace.models import WorkspaceMember

        WorkspaceMember.objects.create(
            workspace=self.other_workspace, user=self.editor, role=WorkspaceMember.Role.EDITOR
        )

        response = self.post_json(
            self.login(self.editor), "import_preview",
            {"source_id": source_id, "mapping": self.object_mapping(NAME, type_id=self.other_app_type.id)},
            model=self.other_model,
        )

        self.assertEqual(response.status_code, 404)

    def test_a_viewer_cannot_preview(self):
        source_id = self.upload_id(self.login(self.editor))

        response = self.post_json(
            self.login(self.viewer), "import_preview",
            {"source_id": source_id, "mapping": self.object_mapping(MATCH, NAME)},
        )

        self.assertEqual(response.status_code, 403)

    def test_malformed_bodies_are_400s(self):
        client = self.login(self.editor)

        for body in ("not json", "[1, 2]"):
            response = client.post(self.url("import_preview"), body, content_type="application/json")
            self.assertEqual(response.status_code, 400, body)

    def test_malicious_cell_content_comes_back_as_data_never_as_markup(self):
        client = self.login(self.editor)
        rows = [["App ID", "Name"], ["A1", "<script>alert(1)</script>"]]
        source_id = self.upload_id(client, rows)

        response = self.post_json(
            client, "import_preview",
            {"source_id": source_id, "mapping": self.object_mapping(MATCH, NAME)},
        )

        self.assertEqual(response["Content-Type"], "application/json")
        self.assertEqual(
            response.json()["items"][0]["fields"][0]["after"], "<script>alert(1)</script>"
        )


class CreateTests(ViewTestCase):

    def create(self, client, source_id, mapping=None, model=None):
        return self.post_json(
            client, "import_create",
            {"source_id": source_id, "mapping": mapping or self.object_mapping(MATCH, NAME)},
            model=model,
        )

    def test_create_makes_one_proposal_and_points_at_the_review_page(self):
        client = self.login(self.editor)
        source_id = self.upload_id(client)

        response = self.create(client, source_id)

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertFalse(data["no_changes"])
        proposal = Proposal.objects.get()
        self.assertEqual(data["proposal_url"], reverse("model:proposal", args=[self.model.id, proposal.id]))
        self.assertEqual(proposal.changes.count(), 2)
        self.assertEqual(EvidenceReference.objects.count(), 2)
        self.assertEqual(Object.objects.count(), 0)

    def test_the_imported_proposal_opens_in_the_normal_review_page(self):
        client = self.login(self.editor)
        response = self.create(client, self.upload_id(client))

        page = client.get(response.json()["proposal_url"])

        self.assertEqual(page.status_code, 200)
        self.assertContains(page, "Import: apps.csv")
        self.assertContains(page, "Data import: apps.csv")
        self.assertContains(page, "Imported apps.csv: 2 objects created")

    def test_the_active_proposal_becomes_the_imported_one(self):
        client = self.login(self.editor)

        self.create(client, self.upload_id(client))

        self.assertEqual(client.session["active_proposals"][str(self.model.id)], str(Proposal.objects.get().id))

    def test_a_hostile_filename_is_escaped_on_the_review_page(self):
        client = self.login(self.editor)
        name = "<img src=x onerror=alert(1)>.csv"
        source_id = self.upload(client, filename=name).json()["source"]["id"]

        page = client.get(self.create(client, source_id).json()["proposal_url"])

        self.assertNotContains(page, name)
        self.assertContains(page, "&lt;img src=x onerror=alert(1)&gt;.csv")

    def test_nothing_to_change_creates_nothing_and_says_so(self):
        self.make_app("One", "A1")
        self.make_app("Two", "A2")
        client = self.login(self.editor)
        source_id = self.upload_id(client, [["App ID", "Name"], ["A1", "One"], ["A2", "Two"]])

        response = self.create(client, source_id)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["no_changes"])
        self.assertNotIn("proposal_url", response.json())
        self.assertFalse(Proposal.objects.exists())
        self.assertFalse(ImportSource.objects.exists())

    def test_blocking_problems_refuse_creation_with_a_422(self):
        self.make_app("One", "A1")
        self.make_app("Two", "A1")
        client = self.login(self.editor)
        source_id = self.upload_id(client)

        response = self.create(client, source_id)

        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["code"], "import_blocked")
        self.assertEqual(response.json()["problems"][0]["code"], "ambiguous_identity")
        self.assertFalse(Proposal.objects.exists())

    def test_the_live_proposal_cap_is_a_409(self):
        for _ in range(settings.PROPOSAL_MAX_LIVE_PER_MODEL):
            ProposalService.create_working(self.model, self.editor)
        client = self.login(self.editor)
        source_id = self.upload_id(client)

        response = self.create(client, source_id)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["code"], "proposal_limit")
        self.assertEqual(Proposal.objects.count(), settings.PROPOSAL_MAX_LIVE_PER_MODEL)

    def test_a_viewer_cannot_create(self):
        source_id = self.upload_id(self.login(self.editor))

        response = self.create(self.login(self.viewer), source_id)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Proposal.objects.exists())

    def test_another_editor_cannot_submit_someone_elses_staged_upload(self):
        source_id = self.upload_id(self.login(self.editor))

        response = self.create(self.login(self.other_editor), source_id)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Proposal.objects.exists())

    def test_a_stranger_gets_a_404_and_creates_nothing(self):
        source_id = self.upload_id(self.login(self.editor))

        response = self.create(self.login(self.stranger), source_id)

        self.assertEqual(response.status_code, 404)
        self.assertFalse(Proposal.objects.exists())

    def test_an_imported_source_cannot_be_imported_again_through_the_staged_endpoints(self):
        client = self.login(self.editor)
        source_id = self.upload_id(client)
        self.create(client, source_id)

        response = self.create(client, source_id)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(Proposal.objects.count(), 1)

    def test_csrf_is_enforced_on_create(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.editor)
        source_id = self.upload_id(self.login(self.editor))

        response = self.create(client, source_id)

        self.assertEqual(response.status_code, 403)
        self.assertFalse(Proposal.objects.exists())

    def test_create_never_changes_the_other_models(self):
        client = self.login(self.editor)
        self.create(client, self.upload_id(client))

        self.assertFalse(Proposal.objects.filter(model=self.other_model).exists())
        self.assertFalse(ImportSource.objects.filter(model=self.other_model).exists())


class DiscardTests(ViewTestCase):

    def test_discard_removes_the_callers_staged_source(self):
        client = self.login(self.editor)
        source_id = self.upload_id(client)

        response = self.post_json(client, "import_discard", {"source_id": source_id})

        self.assertEqual(response.status_code, 200)
        self.assertFalse(ImportSource.objects.exists())

    def test_discard_cannot_remove_another_editors_source(self):
        source_id = self.upload_id(self.login(self.editor))

        self.post_json(self.login(self.other_editor), "import_discard", {"source_id": source_id})

        self.assertEqual(ImportSource.objects.count(), 1)

    def test_a_viewer_cannot_discard(self):
        source_id = self.upload_id(self.login(self.editor))

        response = self.post_json(self.login(self.viewer), "import_discard", {"source_id": source_id})

        self.assertEqual(response.status_code, 403)
        self.assertEqual(ImportSource.objects.count(), 1)
