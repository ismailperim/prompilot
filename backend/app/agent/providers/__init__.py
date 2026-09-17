"""Chat providers behind one interface. See build_provider()."""

from __future__ import annotations

from app.agent.llm import ChatProvider, OpenAICompatibleProvider
from app.config import Settings


def build_provider(settings: Settings) -> ChatProvider | None:
    """The provider selected by LLM_PROVIDER, or None when it is not configured."""
    if not settings.llm_enabled:
        return None
    match settings.llm_provider:
        case "openai":
            return OpenAICompatibleProvider.from_settings(settings)
        case "azure":
            from app.agent.providers.azure import AzureOpenAIProvider

            return AzureOpenAIProvider.from_settings(settings)
        case "anthropic":
            from app.agent.providers.anthropic import AnthropicProvider

            return AnthropicProvider.from_settings(settings)
        case "gemini":
            from app.agent.providers.gemini import GeminiProvider

            return GeminiProvider.from_settings(settings)
    raise ValueError(f"unknown LLM_PROVIDER {settings.llm_provider!r}")
