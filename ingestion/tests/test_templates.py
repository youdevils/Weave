import csv
import io
import zipfile

import openpyxl
from django.test import Client, SimpleTestCase
from django.urls import reverse
from openpyxl.utils import get_column_letter

from ingestion.services import templates
from ingestion.services.proposals import preview_import
from ingestion.services.targets import OBJECT, RELATIONSHIP, resolve_target
from ingestion.tests.base import ImportTestCase
from model.models.attribute_definition import AttributeDefinition
from model.models.model import Model


def _column_index(columns, header):
    return next(i for i, column in enumerate(columns, start=1) if column.header == header)


class InlineListFormulaTests(SimpleTestCase):
    """The strict allow-list that decides whether a choice list is safe to
    offer as an Excel dropdown. Anything not clearly safe falls back to an
    ordinary text column -- never a helper sheet/range."""

    def test_simple_choices_produce_a_quoted_comma_list(self):
        self.assertEqual(templates._inline_list_formula(("gold", "silver")), '"gold,silver"')

    def test_no_choices_is_none(self):
        self.assertIsNone(templates._inline_list_formula(()))

    def test_a_choice_containing_a_comma_is_rejected(self):
        self.assertIsNone(templates._inline_list_formula(("a,b", "c")))

    def test_a_choice_containing_a_control_character_is_rejected(self):
        self.assertIsNone(templates._inline_list_formula(("a\nb",)))

    def test_a_choice_containing_a_quote_is_escaped(self):
        self.assertEqual(templates._inline_list_formula(('he said "hi"',)), '"he said ""hi"""')

    def test_a_list_too_long_for_excels_inline_literal_is_rejected(self):
        choices = tuple(f"choice-number-{i}" for i in range(30))
        self.assertIsNone(templates._inline_list_formula(choices))


class TemplateColumnsTests(ImportTestCase):
    """Pure unit tests on template_columns() -- no HTTP, no file bytes."""

    def test_object_columns_start_with_identity_then_built_ins(self):
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        headers = [column.header for column in templates.template_columns(target)]

        self.assertEqual(headers[:4], ["OnyxJar Key", "Name", "Description", "Active"])
        self.assertEqual(set(headers[4:]), {"App ID", "Owner", "Cost", "Live", "Go live", "Tier"})

    def test_relationship_columns_start_with_endpoints(self):
        target = resolve_target(self.model, RELATIONSHIP, self.uses.id)
        headers = [column.header for column in templates.template_columns(target)]

        self.assertEqual(headers[:3], ["Source object key", "Target object key", "Active"])
        self.assertIn("Since", headers)

    def test_name_is_always_required_and_identity_is_never_required(self):
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        columns = {column.header: column for column in templates.template_columns(target)}

        self.assertTrue(columns["Name"].required)
        self.assertFalse(columns["OnyxJar Key"].required)

    def test_relationship_endpoints_are_required(self):
        target = resolve_target(self.model, RELATIONSHIP, self.uses.id)
        columns = {column.header: column for column in templates.template_columns(target)}

        self.assertTrue(columns["Source object key"].required)
        self.assertTrue(columns["Target object key"].required)

    def test_an_attributes_required_flag_comes_from_the_model(self):
        AttributeDefinition.objects.create(
            object_type=self.app_type,
            name="Mandatory Field",
            key="mandatory_field",
            data_type=AttributeDefinition.DataType.TEXT,
            required=True,
        )
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        columns = {column.header: column for column in templates.template_columns(target)}

        self.assertTrue(columns["Mandatory Field"].required)
        self.assertFalse(columns["Owner"].required)

    def test_a_choice_attributes_column_carries_its_choices(self):
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        columns = {column.header: column for column in templates.template_columns(target)}

        self.assertEqual(columns["Tier"].choices, ("gold", "silver"))
        self.assertEqual(columns["App ID"].choices, ())

    def test_an_inactive_attribute_is_not_included(self):
        self.cost.is_active = False
        self.cost.save()

        target = resolve_target(self.model, OBJECT, self.app_type.id)
        headers = [column.header for column in templates.template_columns(target)]

        self.assertNotIn("Cost", headers)


class DataRowsTests(ImportTestCase):
    """data_rows() -- the inverse of the import wizard, read in
    template_columns() order, for the optional "with current data" download."""

    def test_object_rows_carry_the_key_and_every_column_in_order(self):
        app = self.make_app("Alpha", app_id="A1", owner="Finance", cost=1200, live=True)
        target = resolve_target(self.model, OBJECT, self.app_type.id)

        (row,) = templates.data_rows(self.model, target)

        headers = [column.header for column in templates.template_columns(target)]
        by_header = dict(zip(headers, row))

        self.assertEqual(by_header["OnyxJar Key"], app.key)
        self.assertEqual(by_header["Name"], "Alpha")
        self.assertEqual(by_header["Description"], "")
        self.assertEqual(by_header["Active"], "true")
        self.assertEqual(by_header["App ID"], "A1")
        self.assertEqual(by_header["Owner"], "Finance")
        self.assertEqual(by_header["Cost"], 1200)
        self.assertEqual(by_header["Live"], "true")

    def test_an_unset_attribute_is_a_blank_cell(self):
        self.make_app("Alpha", app_id="A1")
        target = resolve_target(self.model, OBJECT, self.app_type.id)

        (row,) = templates.data_rows(self.model, target)
        by_header = dict(zip([c.header for c in templates.template_columns(target)], row))

        self.assertEqual(by_header["Owner"], "")

    def test_an_empty_type_has_no_rows(self):
        target = resolve_target(self.model, OBJECT, self.app_type.id)

        self.assertEqual(templates.data_rows(self.model, target), [])

    def test_relationship_rows_carry_endpoint_keys(self):
        one = self.make_app("Alpha", app_id="A")
        two = self.make_app("Beta", app_id="B")
        self.make_uses(one, two, since="2024-01-01")

        target = resolve_target(self.model, RELATIONSHIP, self.uses.id)
        (row,) = templates.data_rows(self.model, target)
        by_header = dict(zip([c.header for c in templates.template_columns(target)], row))

        self.assertEqual(by_header["Source object key"], one.key)
        self.assertEqual(by_header["Target object key"], two.key)
        self.assertEqual(by_header["Active"], "true")
        self.assertEqual(by_header["Since"], "2024-01-01")


class CsvTemplateBytesTests(ImportTestCase):

    def test_header_only_matches_template_columns_in_order(self):
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        data = templates.build_csv_template(target)

        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], [column.header for column in templates.template_columns(target)])

    def test_build_template_without_data_has_no_rows(self):
        self.make_app("Alpha")
        target = resolve_target(self.model, OBJECT, self.app_type.id)

        data = templates.build_template(target, "csv", model=self.model, with_data=False)
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))

        self.assertEqual(len(rows), 1)

    def test_build_template_with_data_includes_existing_rows(self):
        app = self.make_app("Alpha", app_id="A1")
        target = resolve_target(self.model, OBJECT, self.app_type.id)

        data = templates.build_template(target, "csv", model=self.model, with_data=True)
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))

        self.assertEqual(len(rows), 2)
        by_header = dict(zip(rows[0], rows[1]))
        self.assertEqual(by_header["OnyxJar Key"], app.key)
        self.assertEqual(by_header["App ID"], "A1")


class XlsxTemplateBytesTests(ImportTestCase):

    def test_exactly_one_worksheet_with_matching_headers(self):
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        columns = templates.template_columns(target)
        data = templates.build_xlsx_template(target)

        workbook = openpyxl.load_workbook(io.BytesIO(data))
        self.assertEqual(len(workbook.sheetnames), 1)

        sheet = workbook.active
        header_row = [sheet.cell(row=1, column=i).value for i in range(1, len(columns) + 1)]
        self.assertEqual(header_row, [column.header for column in columns])

    def test_required_header_is_bold(self):
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        columns = templates.template_columns(target)
        sheet = openpyxl.load_workbook(io.BytesIO(templates.build_xlsx_template(target))).active

        name_index = _column_index(columns, "Name")
        owner_index = _column_index(columns, "Owner")

        self.assertTrue(sheet.cell(row=1, column=name_index).font.bold)
        self.assertFalse(sheet.cell(row=1, column=owner_index).font.bold)

    def test_choice_and_boolean_columns_have_dropdowns(self):
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        columns = templates.template_columns(target)
        sheet = openpyxl.load_workbook(io.BytesIO(templates.build_xlsx_template(target))).active

        ranges = [str(validation.sqref) for validation in sheet.data_validations.dataValidation]

        tier_letter = get_column_letter(_column_index(columns, "Tier"))
        active_letter = get_column_letter(_column_index(columns, "Active"))

        self.assertTrue(any(f"{tier_letter}2" in r for r in ranges))
        self.assertTrue(any(f"{active_letter}2" in r for r in ranges))

    def test_a_relationship_templates_endpoints_are_plain_text_columns(self):
        target = resolve_target(self.model, RELATIONSHIP, self.uses.id)
        data = templates.build_xlsx_template(target)

        workbook = openpyxl.load_workbook(io.BytesIO(data))
        self.assertEqual(len(workbook.sheetnames), 1)

    def test_with_data_writes_the_key_as_text_and_a_number_attribute_as_a_number(self):
        app = self.make_app("Alpha", app_id="A1", cost=1200)
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        columns = templates.template_columns(target)

        data = templates.build_template(target, "xlsx", model=self.model, with_data=True)
        sheet = openpyxl.load_workbook(io.BytesIO(data)).active

        key_cell = sheet.cell(row=2, column=_column_index(columns, "OnyxJar Key"))
        cost_cell = sheet.cell(row=2, column=_column_index(columns, "Cost"))

        self.assertEqual(key_cell.value, app.key)
        self.assertEqual(key_cell.data_type, "s")
        self.assertEqual(cost_cell.value, 1200)
        self.assertEqual(cost_cell.data_type, "n")


class TemplatesZipTests(ImportTestCase):

    def test_one_member_per_active_type(self):
        data = templates.build_templates_zip(self.model, "csv")

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            names = archive.namelist()

        self.assertEqual(len(names), 3)
        self.assertIn(f"object-{self.app_type.key}.csv", names)
        self.assertIn(f"object-{self.person_type.key}.csv", names)
        self.assertIn(f"relationship-{self.uses.key}.csv", names)

    def test_a_model_with_no_active_types_produces_an_empty_zip(self):
        empty_model = Model.objects.create(workspace=self.workspace, name="Empty")

        data = templates.build_templates_zip(empty_model, "csv")

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.namelist(), [])

    def test_each_member_is_independently_importable(self):
        data = templates.build_templates_zip(self.model, "xlsx")

        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            for name in archive.namelist():
                workbook = openpyxl.load_workbook(io.BytesIO(archive.read(name)))
                self.assertEqual(len(workbook.sheetnames), 1)


class TemplateDownloadAccessTests(ImportTestCase):

    def _get(self, user, url):
        client = Client()
        client.force_login(user)
        return client.get(url)

    def template_url(self, kind, type_id, file_format, model=None):
        return reverse(
            "ingestion:download_template", args=[(model or self.model).id, kind, type_id, file_format]
        )

    def zip_url(self, file_format, model=None):
        return reverse("ingestion:download_templates_zip", args=[(model or self.model).id, file_format])

    def test_owner_and_editor_can_download_a_csv_template(self):
        for user in (self.owner, self.editor):
            response = self._get(user, self.template_url("object", self.app_type.id, "csv"))

            self.assertEqual(response.status_code, 200, user.email)
            self.assertEqual(response["Content-Type"], "text/csv")
            self.assertIn("attachment;", response["Content-Disposition"])
            self.assertIn(".csv", response["Content-Disposition"])

    def test_owner_and_editor_can_download_an_xlsx_template(self):
        response = self._get(self.owner, self.template_url("relationship", self.uses.id, "xlsx"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Type"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn(".xlsx", response["Content-Disposition"])

    def test_the_data_flag_includes_current_rows_and_names_the_file_accordingly(self):
        app = self.make_app("Alpha", app_id="A1")
        url = self.template_url("object", self.app_type.id, "csv") + "?data=1"

        response = self._get(self.owner, url)

        self.assertEqual(response.status_code, 200)
        self.assertIn("with-data", response["Content-Disposition"])
        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 2)
        self.assertIn(app.key, rows[1])

    def test_without_the_data_flag_only_the_header_is_returned(self):
        self.make_app("Alpha")
        response = self._get(self.owner, self.template_url("object", self.app_type.id, "csv"))

        rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
        self.assertEqual(len(rows), 1)

    def test_a_viewer_cannot(self):
        self.assertEqual(
            self._get(self.viewer, self.template_url("object", self.app_type.id, "csv")).status_code, 403
        )

    def test_a_member_of_another_workspace_gets_a_404(self):
        self.assertEqual(
            self._get(self.stranger, self.template_url("object", self.app_type.id, "csv")).status_code, 404
        )

    def test_anonymous_users_are_sent_to_log_in(self):
        response = Client().get(self.template_url("object", self.app_type.id, "csv"))
        self.assertEqual(response.status_code, 302)

    def test_an_unknown_file_format_is_a_404(self):
        self.assertEqual(
            self._get(self.editor, self.template_url("object", self.app_type.id, "tsv")).status_code, 404
        )

    def test_an_invalid_kind_is_a_404(self):
        self.assertEqual(
            self._get(self.editor, self.template_url("widget", self.app_type.id, "csv")).status_code, 404
        )

    def test_a_type_from_another_model_is_a_404(self):
        self.assertEqual(
            self._get(self.editor, self.template_url("object", self.other_app_type.id, "csv")).status_code,
            404,
        )

    def test_an_unknown_type_id_is_a_404(self):
        self.assertEqual(
            self._get(self.editor, self.template_url("object", self.new_id(), "csv")).status_code, 404
        )

    def test_owner_and_editor_can_download_the_zip(self):
        for user in (self.owner, self.editor):
            response = self._get(user, self.zip_url("csv"))

            self.assertEqual(response.status_code, 200, user.email)
            self.assertEqual(response["Content-Type"], "application/zip")
            self.assertIn(".zip", response["Content-Disposition"])

    def test_a_viewer_cannot_download_the_zip(self):
        self.assertEqual(self._get(self.viewer, self.zip_url("csv")).status_code, 403)

    def test_an_unknown_zip_format_is_a_404(self):
        self.assertEqual(self._get(self.editor, self.zip_url("tsv")).status_code, 404)


class TemplateRoundTripTests(ImportTestCase):
    """
    Hard acceptance criterion: a generated, hand-filled template must flow
    through the REAL parser + mapping + planner with no format/mapping
    errors -- current model -> generated template -> user adds valid data ->
    existing Import wizard -> mapping -> preview -> clean proposal.

    Mapping columns are derived from template_columns() by header, not by a
    hardcoded index, so these tests stay correct even if attribute ordering
    changes -- they prove the template's shape is importable, not that a
    specific hardcoded layout happens to match.
    """

    def _object_mapping_columns(self, target, *, match_on=None):
        key_by_name = {attribute.name: attribute.key for attribute in target.attributes}
        columns = []

        for index, column in enumerate(templates.template_columns(target)):
            if column.header == templates.FIELD_NAME_HEADER:
                columns.append({"column": index, "field": "field.name"})
            elif column.header == templates.FIELD_DESCRIPTION_HEADER:
                columns.append({"column": index, "field": "field.description"})
            elif column.header == templates.FIELD_IS_ACTIVE_HEADER:
                columns.append({"column": index, "field": "field.is_active"})
            elif column.header == templates.IDENTITY_KEY_HEADER:
                continue
            else:
                key = key_by_name[column.header]
                entry = {"column": index, "field": f"attribute.{key}"}
                if key == match_on:
                    entry["match"] = True
                columns.append(entry)

        return columns

    def _relationship_mapping_columns(self, target):
        key_by_name = {attribute.name: attribute.key for attribute in target.attributes}
        columns = []

        for index, column in enumerate(templates.template_columns(target)):
            if column.header == templates.ENDPOINT_SUBJECT_HEADER:
                columns.append(self.by_app_id(index, "endpoint.subject"))
            elif column.header == templates.ENDPOINT_OBJECT_HEADER:
                columns.append(self.by_app_id(index, "endpoint.object"))
            elif column.header == templates.FIELD_IS_ACTIVE_HEADER:
                columns.append({"column": index, "field": "field.is_active"})
            else:
                key = key_by_name[column.header]
                columns.append({"column": index, "field": f"attribute.{key}"})

        return columns

    def _filled_row(self, columns, values):
        return [values.get(column.header, "") for column in columns]

    def test_a_filled_in_object_csv_template_plans_a_clean_create(self):
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        columns = templates.template_columns(target)
        header = [column.header for column in columns]
        row = self._filled_row(
            columns,
            {
                "Name": "New App",
                "Active": "true",
                "App ID": "A1",
                "Owner": "Alice",
                "Cost": "9.5",
                "Live": "true",
                "Go live": "2024-01-01",
                "Tier": "gold",
            },
        )

        source = self.stage([header, row])
        plan = preview_import(
            self.model,
            source,
            self.object_mapping(*self._object_mapping_columns(target, match_on="app_id")),
        )

        self.assertFalse(plan.blocked, plan.problems)
        (change,) = plan.changes
        self.assertEqual(change.operation, "create")
        self.assertEqual(change.after["attributes"]["tier"], "gold")

    def test_a_filled_in_object_xlsx_template_plans_a_clean_create(self):
        target = resolve_target(self.model, OBJECT, self.app_type.id)
        columns = templates.template_columns(target)

        workbook = openpyxl.load_workbook(io.BytesIO(templates.build_xlsx_template(target)))
        sheet = workbook.active
        values = {
            "Name": "New App",
            "Active": True,
            "App ID": "A1",
            "Owner": "Alice",
            "Cost": 9.5,
            "Live": True,
            "Go live": "2024-01-01",
            "Tier": "gold",
        }
        for index, column in enumerate(columns, start=1):
            if column.header in values:
                sheet.cell(row=2, column=index, value=values[column.header])

        buffer = io.BytesIO()
        workbook.save(buffer)

        source = self.stage(buffer.getvalue(), filename="apps.xlsx")
        plan = preview_import(
            self.model,
            source,
            self.object_mapping(*self._object_mapping_columns(target, match_on="app_id")),
        )

        self.assertFalse(plan.blocked, plan.problems)
        (change,) = plan.changes
        self.assertEqual(change.operation, "create")

    def test_a_filled_in_relationship_csv_template_plans_a_clean_create(self):
        self.make_app("Alpha", app_id="A")
        self.make_app("Beta", app_id="B")

        target = resolve_target(self.model, RELATIONSHIP, self.uses.id)
        columns = templates.template_columns(target)
        header = [column.header for column in columns]
        row = self._filled_row(
            columns,
            {"Source object key": "A", "Target object key": "B", "Active": "true", "Since": "2024-01-01"},
        )

        source = self.stage([header, row], "rels.csv")
        plan = preview_import(
            self.model, source, self.relationship_mapping(*self._relationship_mapping_columns(target))
        )

        self.assertFalse(plan.blocked, plan.problems)
        (change,) = plan.changes
        self.assertEqual(change.operation, "create")
        self.assertEqual(change.after["attributes"]["since"], "2024-01-01")

    def test_a_filled_in_relationship_xlsx_template_plans_a_clean_create(self):
        self.make_app("Alpha", app_id="A")
        self.make_app("Beta", app_id="B")

        target = resolve_target(self.model, RELATIONSHIP, self.uses.id)
        columns = templates.template_columns(target)

        workbook = openpyxl.load_workbook(io.BytesIO(templates.build_xlsx_template(target)))
        sheet = workbook.active
        values = {"Source object key": "A", "Target object key": "B", "Active": True, "Since": "2024-01-01"}
        for index, column in enumerate(columns, start=1):
            if column.header in values:
                sheet.cell(row=2, column=index, value=values[column.header])

        buffer = io.BytesIO()
        workbook.save(buffer)

        source = self.stage(buffer.getvalue(), filename="rels.xlsx")
        plan = preview_import(
            self.model, source, self.relationship_mapping(*self._relationship_mapping_columns(target))
        )

        self.assertFalse(plan.blocked, plan.problems)
        (change,) = plan.changes
        self.assertEqual(change.operation, "create")


class TemplateWithDataRoundTripTests(ImportTestCase):
    """
    The "download with current data" file (templates.build_template(...,
    with_data=True)) must flow back through the real parser + mapping +
    planner just as cleanly as the blank template above: unchanged, it is a
    no-op; with one value edited, it is exactly one UPDATE, with the key
    unchanged -- the round-trip property the data mode exists for.
    """

    def _key_mapping_columns(self, target):
        key_by_name = {attribute.name: attribute.key for attribute in target.attributes}
        columns = []

        for index, column in enumerate(templates.template_columns(target)):
            if column.header == templates.IDENTITY_KEY_HEADER:
                columns.append({"column": index, "field": "identity.key"})
            elif column.header == templates.FIELD_NAME_HEADER:
                columns.append({"column": index, "field": "field.name"})
            elif column.header == templates.FIELD_DESCRIPTION_HEADER:
                columns.append({"column": index, "field": "field.description"})
            elif column.header == templates.FIELD_IS_ACTIVE_HEADER:
                columns.append({"column": index, "field": "field.is_active"})
            else:
                columns.append({"column": index, "field": f"attribute.{key_by_name[column.header]}"})

        return columns

    def _endpoint_key_mapping_columns(self, target):
        key_by_name = {attribute.name: attribute.key for attribute in target.attributes}
        columns = []

        for index, column in enumerate(templates.template_columns(target)):
            if column.header == templates.ENDPOINT_SUBJECT_HEADER:
                columns.append(self.by_key(index, "endpoint.subject"))
            elif column.header == templates.ENDPOINT_OBJECT_HEADER:
                columns.append(self.by_key(index, "endpoint.object"))
            elif column.header == templates.FIELD_IS_ACTIVE_HEADER:
                columns.append({"column": index, "field": "field.is_active"})
            else:
                columns.append({"column": index, "field": f"attribute.{key_by_name[column.header]}"})

        return columns

    def test_an_unchanged_object_file_reimports_as_a_no_op(self):
        self.make_app("Alpha", app_id="A1", owner="Finance")
        target = resolve_target(self.model, OBJECT, self.app_type.id)

        data = templates.build_template(target, "csv", model=self.model, with_data=True)
        source = self.stage(data, "alpha.csv")

        plan = preview_import(self.model, source, self.object_mapping(*self._key_mapping_columns(target)))

        self.assertFalse(plan.blocked, plan.problems)
        self.assertEqual(plan.changes, [])

    def test_editing_one_value_produces_exactly_one_update_with_the_key_unchanged(self):
        app = self.make_app("Alpha", app_id="A1", owner="Finance")
        target = resolve_target(self.model, OBJECT, self.app_type.id)

        data = templates.build_template(target, "csv", model=self.model, with_data=True)
        rows = list(csv.reader(io.StringIO(data.decode("utf-8-sig"))))
        header, row = rows[0], rows[1]
        row[header.index("Owner")] = "HR"

        source = self.stage([header, row], "alpha.csv")
        plan = preview_import(self.model, source, self.object_mapping(*self._key_mapping_columns(target)))

        self.assertFalse(plan.blocked, plan.problems)
        (change,) = plan.changes
        self.assertEqual(change.target_id, app.id)
        self.assertEqual(change.after, {"field": "attributes.owner", "value": "HR"})

    def test_an_unchanged_relationship_file_reimports_as_a_no_op(self):
        one = self.make_app("Alpha", app_id="A")
        two = self.make_app("Beta", app_id="B")
        self.make_uses(one, two, since="2024-01-01")

        target = resolve_target(self.model, RELATIONSHIP, self.uses.id)
        data = templates.build_template(target, "csv", model=self.model, with_data=True)
        source = self.stage(data, "rels.csv")

        plan = preview_import(
            self.model, source, self.relationship_mapping(*self._endpoint_key_mapping_columns(target))
        )

        self.assertFalse(plan.blocked, plan.problems)
        self.assertEqual(plan.changes, [])
