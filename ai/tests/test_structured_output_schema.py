"""
Regression guard for OpenAI strict structured outputs. The OpenAI python
SDK's schema builder (openai.lib._pydantic.to_strict_json_schema, the same
function client.responses.parse uses) does not raise client-side for a
non-compliant schema -- the API rejects it server-side, e.g.:

    Invalid schema for response_format '...': In context=('properties',
    'fields'), 'additionalProperties' is required to be supplied and to be
    false.

So every stage's response schema is built here and checked recursively:
every object node strict, and no `oneOf` (strict mode supports `anyOf`
only -- the ChangeSet's action union must stay a plain Union, never a
Pydantic discriminated union).
"""

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase
from openai.lib._pydantic import to_strict_json_schema

from ai.services.change_set import CreateObject, PlanResult
from ai.services.reconcile.responses import AdjudicationResult, ExtractionResult, ProbeResult, VerificationResult
from ai.services.openai_provider import OpenAIProvider
from ai.services.provider import ProviderConfig
from ai.tests.support import plan


def _violations(node, path=()):
    found = []
    if isinstance(node, dict):
        if node.get("type") == "object" and node.get("additionalProperties") is not False:
            found.append(("non-strict object", path))
        if "oneOf" in node:
            found.append(("oneOf", path))
        for key, value in node.items():
            found += _violations(value, path + (key,))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            found += _violations(value, path + (index,))
    return found


class StrictSchemaTests(SimpleTestCase):

    def test_every_stage_response_schema_is_strict(self):
        for schema in (ExtractionResult, AdjudicationResult, ProbeResult, VerificationResult, PlanResult):
            with self.subTest(schema=schema.__name__):
                self.assertEqual(_violations(to_strict_json_schema(schema)), [])

    def test_change_set_actions_are_an_any_of_union_of_every_action_kind(self):
        schema = to_strict_json_schema(PlanResult)
        items = schema["$defs"]["ChangeSet"]["properties"]["actions"]["items"]

        self.assertEqual(len(items["anyOf"]), 12)

    def test_claim_stages_have_no_mutation_fields(self):
        for response in (ExtractionResult, AdjudicationResult, ProbeResult, VerificationResult):
            with self.subTest(schema=response.__name__):
                schema = to_strict_json_schema(response)
                self.assertNotIn("ChangeSet", schema.get("$defs", {}))
                self.assertNotIn("actions", str(schema["properties"]))


class SuccessfulParseSimulationTests(SimpleTestCase):

    def test_plan_result_round_trips_through_json_like_a_real_response(self):
        structured = plan([
            {"kind": "create_object", "action_id": "a1", "token": "t", "type": {"kind": "existing", "key": "widget"},
             "name": "W", "attributes": [{"key": "cost", "number_value": 42.5}]},
        ])

        rebuilt = PlanResult.model_validate(structured.model_dump(mode="json"))

        self.assertEqual(rebuilt, structured)
        self.assertIsInstance(rebuilt.change_set.actions[0], CreateObject)

    def test_provider_returns_the_parsed_stage_result(self):
        structured = plan([])

        with patch("ai.services.openai_provider.openai.OpenAI") as mock_openai_cls:
            response = MagicMock(output_parsed=structured, output_text="", model="gpt-4.1",
                                 usage=MagicMock(input_tokens=1, output_tokens=1, total_tokens=2))
            mock_openai_cls.return_value.responses.parse.return_value = response

            result = OpenAIProvider().generate_structured(
                system_prompt="sys", user_payload={}, response_schema=PlanResult,
                config=ProviderConfig(model="gpt-4.1", timeout_seconds=5, max_retries=0),
            )

        self.assertIs(result.parsed, structured)
        self.assertEqual(result.usage["total_tokens"], 2)
