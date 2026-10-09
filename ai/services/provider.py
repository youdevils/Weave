"""
Provider abstraction. The operation/orchestration layer never calls OpenAI
(or any provider SDK) directly:

    AI Operation -> AI Service (orchestrator) -> Provider abstraction -> OpenAI

`provider` is a plain constructor-injected dependency on
ai.services.orchestrator.run_ai_operation, purely for testability -- no
provider registry/plugin framework.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Type

from pydantic import BaseModel


def canonical_payload(payload) -> str:
    """Exactly the text a payload is sent as (also what traces measure)."""

    return json.dumps(payload, sort_keys=True, default=str)


class ProviderError(Exception):
    """A provider call failed in a way the caller should treat as a system/
    provider failure (never raised for a merely-malformed, retried response
    -- see ProviderSchemaError)."""


class ProviderTimeoutError(ProviderError):
    """The provider call did not complete within AI_PROVIDER_TIMEOUT_SECONDS."""


class ProviderSchemaError(ProviderError):
    """The provider's response could not be parsed against the requested
    schema, even after internal retries."""


@dataclass(frozen=True)
class ProviderConfig:
    model: str
    timeout_seconds: float
    max_retries: int


@dataclass(frozen=True)
class ProviderResult:
    # None only in an unexpected edge case the provider chose not to raise
    # on; OpenAIProvider.generate_structured otherwise guarantees either a
    # non-None parsed result or a raised ProviderError. The orchestrator
    # still defensively checks for None rather than trusting that.
    parsed: Optional[BaseModel]
    # Kept inside the provider boundary -- the orchestrator never reads this.
    raw_text: str
    usage: dict = field(default_factory=dict)
    provider: str = "openai"
    provider_model: str = ""


class AIProvider(ABC):

    @abstractmethod
    def generate_structured(
        self,
        *,
        system_prompt: str,
        user_payload: dict,
        response_schema: Type[BaseModel],
        config: ProviderConfig,
    ) -> ProviderResult:
        ...

    @abstractmethod
    def explain(self, *, context: Any, issues: list, config: ProviderConfig) -> ProviderResult:
        """A final, explanation-only call. Must never mutate model state or
        create a Proposal -- a plain text-producing call, not another
        refinement attempt. The explanation text is the result's `raw_text`;
        its `usage` is accumulated like any other call's (it is real
        provider cost)."""
        ...
