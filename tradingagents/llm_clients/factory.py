from typing import Optional

from .base_client import BaseLLMClient
from .external_providers import get_external_provider

# Providers that use the OpenAI-compatible chat completions API
_OPENAI_COMPATIBLE = (
    "openai",
    "xai",
    "deepseek",
    "qwen",
    "glm",
    "ollama",
    "openrouter",
)

# Built-in providers that use a client other than OpenAIClient
_NATIVE_CLIENTS = ("anthropic", "google", "azure")


def _client_kind(provider: str) -> Optional[str]:
    """Return the client implementation to use for a provider.

    A provider from `models.json` decides its own client. Built-in providers
    keep the mapping coded here.
    """
    external = get_external_provider(provider)
    if external is not None:
        return external.client

    if provider in _OPENAI_COMPATIBLE:
        return "openai"

    if provider in _NATIVE_CLIENTS:
        return provider

    return None


def create_llm_client(
    provider: str,
    model: str,
    base_url: Optional[str] = None,
    **kwargs,
) -> BaseLLMClient:
    """Create an LLM client for the specified provider.

    Provider modules are imported lazily so that simply importing this
    factory (e.g. during test collection) does not pull in heavy LLM SDKs
    or fail when their API keys are absent.

    Args:
        provider: LLM provider name
        model: Model name/identifier
        base_url: Optional base URL for API endpoint
        **kwargs: Additional provider-specific arguments

    Returns:
        Configured BaseLLMClient instance

    Raises:
        ValueError: If provider is not supported
    """
    provider_lower = provider.lower()
    client_kind = _client_kind(provider_lower)

    if client_kind == "openai":
        from .openai_client import OpenAIClient

        return OpenAIClient(
            model,
            _resolve_base_url(provider_lower, base_url),
            provider=provider_lower,
            **kwargs,
        )

    if client_kind == "anthropic":
        from .anthropic_client import AnthropicClient

        return AnthropicClient(model, base_url, **kwargs)

    if client_kind == "google":
        from .google_client import GoogleClient

        return GoogleClient(model, base_url, **kwargs)

    if client_kind == "azure":
        from .azure_client import AzureOpenAIClient

        return AzureOpenAIClient(model, base_url, **kwargs)

    raise ValueError(f"Unsupported LLM provider: {provider}")


def _resolve_base_url(provider: str, base_url: Optional[str]) -> Optional[str]:
    """Return the given base URL, or the one declared for the provider."""
    if base_url:
        return base_url

    external = get_external_provider(provider)
    if external is not None:
        return external.base_url

    return None
