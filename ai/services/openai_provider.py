"""
OpenAI implementation of the provider abstraction (ai.services.provider).

Reads all configuration from Django settings at call time -- never hardcoded
in this class -- mirroring account.services.emails's existing Resend
pattern. Retries internally, bounded by config.max_retries, before raising a
typed ProviderError; the orchestration layer never sees a raw openai SDK
exception.
"""

from __future__ import annotations

import logging
from typing import Type

import openai
from django.conf import settings
from pydantic import BaseModel

from ai.services.provider import (
    AIProvider,
    ProviderConfig,
    ProviderError,
    ProviderResult,
    ProviderSchemaError,
    ProviderTimeoutError,
    canonical_payload,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(AIProvider):

    def _client(self) -> openai.OpenAI:
        return openai.OpenAI(api_key=settings.OPENAI_API_KEY)

    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_payload: dict,
        response_schema: Type[BaseModel],
        config: ProviderConfig,
    ) -> ProviderResult:
        client = self._client()
        attempts = max(1, config.max_retries + 1)
        last_error: Exception | None = None

        for attempt in range(attempts):
            try:
                response = client.responses.parse(
                    model=config.model,
                    instructions=system_prompt,
                    input=canonical_payload(user_payload),
                    text_format=response_schema,
                    timeout=config.timeout_seconds,
                )
            except openai.APITimeoutError as error:
                last_error = error
                continue
            except openai.OpenAIError as error:
                raise ProviderError(str(error)) from error

            if response.output_parsed is not None:
                return ProviderResult(
                    parsed=response.output_parsed,
                    raw_text=response.output_text or "",
                    usage=_usage_dict(response.usage),
                    provider="openai",
                    provider_model=response.model or config.model,
                )

            # Parsed cleanly as a response but didn't satisfy the schema --
            # retry within budget, same as a timeout.
            last_error = ProviderSchemaError("Provider response did not match the requested schema.")

        if isinstance(last_error, openai.APITimeoutError):
            raise ProviderTimeoutError(str(last_error)) from last_error

        raise ProviderSchemaError(
            "Provider returned no structured result after "
            f"{attempts} attempt(s)."
        ) from last_error

    def explain(self, *, context, issues: list, config: ProviderConfig) -> ProviderResult:
        client = self._client()

        try:
            response = client.responses.create(
                model=config.model,
                instructions=(
                    "Explain, in plain language and without proposing any further "
                    "changes, why this AI operation could not produce a reviewable "
                    "result. Do not request more context."
                ),
                input=canonical_payload(
                    {
                        "context": context.model_dump(mode="json") if hasattr(context, "model_dump") else context,
                        "issues": [
                            issue.model_dump(mode="json") if hasattr(issue, "model_dump") else str(issue)
                            for issue in issues
                        ],
                    }
                ),
                timeout=config.timeout_seconds,
            )
        except openai.APITimeoutError as error:
            raise ProviderTimeoutError(str(error)) from error
        except openai.OpenAIError as error:
            raise ProviderError(str(error)) from error

        return ProviderResult(
            parsed=None,
            raw_text=response.output_text or "",
            usage=_usage_dict(response.usage),
            provider="openai",
            provider_model=response.model or config.model,
        )


def _usage_dict(usage) -> dict:
    if usage is None:
        return {}
    result = {
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "total_tokens": usage.total_tokens,
    }
    # The part of the input served from OpenAI's prompt cache, when the SDK
    # reports it (a real count only -- never a stand-in object).
    cached = getattr(getattr(usage, "input_tokens_details", None), "cached_tokens", None)
    if isinstance(cached, int) and not isinstance(cached, bool):
        result["cached_tokens"] = cached
    return result
