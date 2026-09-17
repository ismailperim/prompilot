"""Azure OpenAI: the OpenAI API behind Azure's endpoint/deployment/api-version scheme."""

from __future__ import annotations

from openai import AsyncAzureOpenAI

from app.agent.llm import OpenAICompatibleProvider
from app.config import Settings


class AzureOpenAIProvider(OpenAICompatibleProvider):
    """Same wire behaviour as OpenAI; only the client construction differs.

    ``LLM_MODEL`` is the *deployment name* on Azure.
    """

    @classmethod
    def from_settings(cls, settings: Settings) -> AzureOpenAIProvider:
        assert settings.azure_openai_endpoint and settings.llm_model
        provider = cls.__new__(cls)
        provider.model = settings.llm_model
        provider._client = AsyncAzureOpenAI(  # type: ignore[assignment]
            azure_endpoint=settings.azure_openai_endpoint,
            api_key=settings.llm_api_key or "not-needed",
            api_version=settings.azure_openai_api_version,
            timeout=settings.llm_timeout.total_seconds(),
            max_retries=1,
        )
        provider._max_tokens = settings.llm_max_tokens
        provider._temperature = settings.llm_temperature
        provider._extra_body = settings.llm_extra_body_json
        return provider
