"""
Regression guard for the exact failure OpenAI's API raised against a real
Assisted Create run:

    Invalid schema for response_format 'AIStructuredResult': In
    context=('properties', 'fields'), 'additionalProperties' is required to
    be supplied and to be false.

That error is a server-side validation OpenAI performs against the JSON
schema generated from `response_schema=AIStructuredResult` -- the OpenAI
python SDK's own schema builder (openai.lib._pydantic.to_strict_json_schema,
the same function client.responses.parse uses internally) does not raise
client-side for a non-compliant schema, so the only reliable regression
guard is to build that schema here and assert, recursively, that every
object node is strict (additionalProperties: false) -- exactly the rule the
API enforces.
"""

import uuid

from django.test import SimpleTestCase

from openai.lib._pydantic import to_strict_json_schema

from ai.services.change_plan import ChangeAction, ChangePlan, EntityRef, FieldEntry, FieldValue
from ai.services.openai_provider import OpenAIProvider
from ai.services.provider import ProviderConfig
from ai.services.result_schema import AIStructuredResult, Interpretation


def _assert_every_object_is_strict(testcase, node, path=()):
    if isinstance(node, dict):
        if node.get("type") == "object":
            testcase.assertIs(
                node.get("additionalProperties"),
                False,
                f"Non-strict object schema at {'.'.join(map(str, path)) or '<root>'}: {node}",
            )
        for key, value in node.items():
            _assert_every_object_is_strict(testcase, value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            _assert_every_object_is_strict(testcase, value, path + (index,))


class StrictSchemaTests(SimpleTestCase):

    def setUp(self):
        self.schema = to_strict_json_schema(AIStructuredResult)

    def test_every_object_in_the_response_schema_is_strict(self):
        _assert_every_object_is_strict(self, self.schema)

    def test_change_action_fields_is_an_array_not_a_free_form_object(self):
        fields_schema = self.schema["$defs"]["ChangeAction"]["properties"]["fields"]
        self.assertEqual(fields_schema["type"], "array")
        self.assertNotIn("additionalProperties", fields_schema)

    def test_field_entry_and_field_value_are_strict_objects(self):
        for name in ("FieldEntry", "FieldValue", "AttributeDefinitionConfig"):
            self.assertIs(self.schema["$defs"][name]["additionalProperties"], False)


class SuccessfulParseSimulationTests(SimpleTestCase):
    """
    A real `responses.parse()` call returns `output_parsed` already validated
    against `response_schema` by the OpenAI SDK -- i.e. a real AIStructuredResult
    instance, built from the list[FieldEntry] shape the strict schema demands
    (never the old dict-shorthand, which is a convenience this codebase's own
    code/tests get, not something the provider ever sends or receives). This
    builds exactly such a response and drives it through OpenAIProvider with
    the real client call mocked, confirming the new schema round-trips end to
    end rather than only in isolation.
    """

    def _structured_result(self):
        return AIStructuredResult(
            interpretation=Interpretation(restated_intent="Create a widget."),
            change_plan=ChangePlan(
                summary="Create a widget.",
                actions=[
                    ChangeAction(
                        operation="create",
                        target_type="Object",
                        target_ref=EntityRef(kind="new", id="tmp:1"),
                        parent_ref=EntityRef(kind="existing", id=str(uuid.uuid4())),
                        fields=[
                            FieldEntry(key="name", value=FieldValue(string_value="New widget")),
                            FieldEntry(key="is_active", value=FieldValue(boolean_value=True)),
                            FieldEntry(
                                key="attributes.cost",
                                value=FieldValue(number_value=42.5),
                            ),
                        ],
                    )
                ],
            ),
        )

    def test_provider_round_trips_a_list_shaped_structured_response(self):
        from unittest.mock import MagicMock, patch

        structured = self._structured_result()

        with patch("ai.services.openai_provider.openai.OpenAI") as mock_openai_cls:
            mock_client = mock_openai_cls.return_value
            response = MagicMock()
            response.output_parsed = structured
            response.output_text = ""
            response.model = "gpt-4.1"
            response.usage = MagicMock(input_tokens=1, output_tokens=1, total_tokens=2)
            mock_client.responses.parse.return_value = response

            result = OpenAIProvider().generate_structured(
                system_prompt="sys",
                user_payload={},
                response_schema=AIStructuredResult,
                config=ProviderConfig(model="gpt-4.1", timeout_seconds=5, max_retries=0),
            )

        self.assertIs(result.parsed, structured)
        action = result.parsed.change_plan.actions[0]
        self.assertEqual(
            action.fields_dict(),
            {"name": "New widget", "is_active": True, "attributes": {"cost": 42.5}},
        )

    def test_structured_result_round_trips_through_json_like_a_real_response_would(self):
        """
        model_dump(mode="json") + model_validate is exactly what parsing a
        real JSON response body back into AIStructuredResult does -- proves
        the list[FieldEntry] shape survives a JSON round-trip losslessly.
        """
        structured = self._structured_result()

        rebuilt = AIStructuredResult.model_validate(structured.model_dump(mode="json"))

        self.assertEqual(rebuilt, structured)
        self.assertEqual(
            rebuilt.change_plan.actions[0].fields_dict(),
            structured.change_plan.actions[0].fields_dict(),
        )
