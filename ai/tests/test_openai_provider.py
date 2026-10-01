from unittest.mock import MagicMock, patch

import httpx
import openai
from django.test import SimpleTestCase, override_settings
from pydantic import BaseModel

from ai.services.openai_provider import OpenAIProvider
from ai.services.provider import ProviderConfig, ProviderSchemaError, ProviderTimeoutError


class _Schema(BaseModel):
    value: str = "ok"


def _config(max_retries=0):
    return ProviderConfig(model="gpt-4.1", timeout_seconds=5, max_retries=max_retries)


def _timeout_error():
    return openai.APITimeoutError(httpx.Request("POST", "https://api.openai.com/v1/responses"))


def _fake_response(parsed=_Schema(), text="raw", model="gpt-4.1"):
    response = MagicMock()
    response.output_parsed = parsed
    response.output_text = text
    response.model = model
    response.usage = MagicMock(input_tokens=10, output_tokens=5, total_tokens=15)
    return response


@override_settings(OPENAI_API_KEY="test-key", AI_DEFAULT_OPENAI_MODEL="gpt-4.1")
class OpenAIProviderGenerateStructuredTests(SimpleTestCase):

    @patch("ai.services.openai_provider.openai.OpenAI")
    def test_reads_api_key_from_settings_at_call_time(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.responses.parse.return_value = _fake_response()

        OpenAIProvider().generate_structured(
            system_prompt="sys", user_payload={}, response_schema=_Schema, config=_config()
        )

        mock_openai_cls.assert_called_with(api_key="test-key")

    @patch("ai.services.openai_provider.openai.OpenAI")
    def test_successful_call_returns_provider_result_with_usage(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.responses.parse.return_value = _fake_response()

        result = OpenAIProvider().generate_structured(
            system_prompt="sys", user_payload={}, response_schema=_Schema, config=_config()
        )

        self.assertEqual(result.parsed, _Schema())
        self.assertEqual(result.usage, {"input_tokens": 10, "output_tokens": 5, "total_tokens": 15})
        self.assertEqual(result.provider_model, "gpt-4.1")

    @patch("ai.services.openai_provider.openai.OpenAI")
    def test_retries_up_to_configured_max_before_raising_schema_error(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.responses.parse.return_value = _fake_response(parsed=None)

        with self.assertRaises(ProviderSchemaError):
            OpenAIProvider().generate_structured(
                system_prompt="sys", user_payload={}, response_schema=_Schema, config=_config(max_retries=2)
            )

        self.assertEqual(mock_client.responses.parse.call_count, 3)

    @patch("ai.services.openai_provider.openai.OpenAI")
    def test_raises_provider_timeout_error_after_retries_exhausted(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.responses.parse.side_effect = _timeout_error()

        with self.assertRaises(ProviderTimeoutError):
            OpenAIProvider().generate_structured(
                system_prompt="sys", user_payload={}, response_schema=_Schema, config=_config(max_retries=1)
            )

        self.assertEqual(mock_client.responses.parse.call_count, 2)

    @patch("ai.services.openai_provider.openai.OpenAI")
    def test_succeeds_after_one_retry(self, mock_openai_cls):
        mock_client = mock_openai_cls.return_value
        mock_client.responses.parse.side_effect = [_timeout_error(), _fake_response()]

        result = OpenAIProvider().generate_structured(
            system_prompt="sys", user_payload={}, response_schema=_Schema, config=_config(max_retries=2)
        )

        self.assertEqual(result.parsed, _Schema())


@override_settings(OPENAI_API_KEY="test-key", AI_DEFAULT_OPENAI_MODEL="gpt-4.1")
class OpenAIProviderExplainTests(SimpleTestCase):

    @patch("ai.services.openai_provider.openai.OpenAI")
    def test_explain_returns_plain_text(self, mock_openai_cls):
        from ai.services.context_schema import ContextPacket

        mock_client = mock_openai_cls.return_value
        mock_client.responses.create.return_value = MagicMock(output_text="Here's why.")

        context = ContextPacket(intent="x", model_id="id", model_name="M", model_revision=1, byte_size=0)
        explanation = OpenAIProvider().explain(context=context, issues=[], config=_config())

        self.assertEqual(explanation, "Here's why.")
