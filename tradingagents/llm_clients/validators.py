"""Model name validators for each provider."""

from .external_providers import get_external_providers
from .model_catalog import get_known_models


# Self-hosted OpenAI-compatible servers expose whatever models their operator
# loaded, so their model names cannot be checked against a fixed list.
# Providers in `models.json` join this group when they set "open_models": true.
_OPEN_MODEL_PROVIDERS = ("ollama", "openrouter")


def _open_model_providers() -> set[str]:
    """Return providers that accept any model name."""
    external = {
        provider_key
        for provider_key, provider in get_external_providers().items()
        if provider.open_models
    }
    return set(_OPEN_MODEL_PROVIDERS) | external


def get_valid_models() -> dict[str, list[str]]:
    """Return known model names per provider, skipping open model providers."""
    open_providers = _open_model_providers()
    return {
        provider: models
        for provider, models in get_known_models().items()
        if provider not in open_providers
    }


def validate_model(provider: str, model: str) -> bool:
    """Check if model name is valid for the given provider.

    Providers with an open model list, such as ollama, openrouter and every
    provider in `models.json` that sets "open_models", accept any model.
    """
    provider_lower = provider.lower()

    if provider_lower in _open_model_providers():
        return True

    valid_models = get_valid_models()

    if provider_lower not in valid_models:
        return True

    return model in valid_models[provider_lower]
