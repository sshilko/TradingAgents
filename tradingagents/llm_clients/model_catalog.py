"""Shared model catalog for CLI selections and validation.

The built-in providers below ship with the package. Providers defined in the
external `models.json` file (see `external_providers.py`) are merged into
`MODEL_OPTIONS`, so adding a provider or a model needs no Python change.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from .external_providers import (
    get_default_provider as _get_file_default_provider,
)
from .external_providers import get_external_providers, with_custom_option

ModelOption = Tuple[str, str]
ProviderModeOptions = Dict[str, Dict[str, List[ModelOption]]]


_BUILTIN_MODEL_OPTIONS: ProviderModeOptions = {
    "openai": {
        "quick": [
            ("GPT-5.4 Mini - Fast, strong coding and tool use", "gpt-5.4-mini"),
            ("GPT-5.4 Nano - Cheapest, high-volume tasks", "gpt-5.4-nano"),
            ("GPT-5.4 - Latest frontier, 1M context", "gpt-5.4"),
            ("GPT-4.1 - Smartest non-reasoning model", "gpt-4.1"),
        ],
        "deep": [
            ("GPT-5.4 - Latest frontier, 1M context", "gpt-5.4"),
            ("GPT-5.2 - Strong reasoning, cost-effective", "gpt-5.2"),
            ("GPT-5.4 Mini - Fast, strong coding and tool use", "gpt-5.4-mini"),
            (
                "GPT-5.4 Pro - Most capable, expensive ($30/$180 per 1M tokens)",
                "gpt-5.4-pro",
            ),
        ],
    },
    "anthropic": {
        "quick": [
            (
                "Claude Sonnet 4.6 - Best speed and intelligence balance",
                "claude-sonnet-4-6",
            ),
            ("Claude Haiku 4.5 - Fast, near-instant responses", "claude-haiku-4-5"),
            ("Claude Sonnet 4.5 - Agents and coding", "claude-sonnet-4-5"),
        ],
        "deep": [
            (
                "Claude Opus 4.6 - Most intelligent, agents and coding",
                "claude-opus-4-6",
            ),
            ("Claude Opus 4.5 - Premium, max intelligence", "claude-opus-4-5"),
            (
                "Claude Sonnet 4.6 - Best speed and intelligence balance",
                "claude-sonnet-4-6",
            ),
            ("Claude Sonnet 4.5 - Agents and coding", "claude-sonnet-4-5"),
        ],
    },
    "google": {
        "quick": [
            ("Gemini 3 Flash - Next-gen fast", "gemini-3-flash-preview"),
            ("Gemini 2.5 Flash - Balanced, stable", "gemini-2.5-flash"),
            (
                "Gemini 3.1 Flash Lite - Most cost-efficient",
                "gemini-3.1-flash-lite-preview",
            ),
            ("Gemini 2.5 Flash Lite - Fast, low-cost", "gemini-2.5-flash-lite"),
        ],
        "deep": [
            (
                "Gemini 3.1 Pro - Reasoning-first, complex workflows",
                "gemini-3.1-pro-preview",
            ),
            ("Gemini 3 Flash - Next-gen fast", "gemini-3-flash-preview"),
            ("Gemini 2.5 Pro - Stable pro model", "gemini-2.5-pro"),
            ("Gemini 2.5 Flash - Balanced, stable", "gemini-2.5-flash"),
        ],
    },
    "xai": {
        "quick": [
            (
                "Grok 4.1 Fast (Non-Reasoning) - Speed optimized, 2M ctx",
                "grok-4-1-fast-non-reasoning",
            ),
            (
                "Grok 4 Fast (Non-Reasoning) - Speed optimized",
                "grok-4-fast-non-reasoning",
            ),
            (
                "Grok 4.1 Fast (Reasoning) - High-performance, 2M ctx",
                "grok-4-1-fast-reasoning",
            ),
        ],
        "deep": [
            ("Grok 4 - Flagship model", "grok-4-0709"),
            (
                "Grok 4.1 Fast (Reasoning) - High-performance, 2M ctx",
                "grok-4-1-fast-reasoning",
            ),
            ("Grok 4 Fast (Reasoning) - High-performance", "grok-4-fast-reasoning"),
            (
                "Grok 4.1 Fast (Non-Reasoning) - Speed optimized, 2M ctx",
                "grok-4-1-fast-non-reasoning",
            ),
        ],
    },
    "deepseek": {
        "quick": [
            ("DeepSeek V3.2", "deepseek-chat"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("DeepSeek V3.2 (thinking)", "deepseek-reasoner"),
            ("DeepSeek V3.2", "deepseek-chat"),
            ("Custom model ID", "custom"),
        ],
    },
    "qwen": {
        "quick": [
            ("Qwen 3.5 Flash", "qwen3.5-flash"),
            ("Qwen Plus", "qwen-plus"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("Qwen 3.6 Plus", "qwen3.6-plus"),
            ("Qwen 3.5 Plus", "qwen3.5-plus"),
            ("Qwen 3 Max", "qwen3-max"),
            ("Custom model ID", "custom"),
        ],
    },
    "glm": {
        "quick": [
            ("GLM-4.7", "glm-4.7"),
            ("GLM-5", "glm-5"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("GLM-5.1", "glm-5.1"),
            ("GLM-5", "glm-5"),
            ("Custom model ID", "custom"),
        ],
    },
    # OpenRouter: fetched dynamically. Azure: any deployed model name.
    "ollama": {
        "quick": [
            ("Omnicode Local - Best free model", "auto/best"),
            (
                "Omnicode Local - openrouter/openrouter/free",
                "openrouter/openrouter/free",
            ),
            ("qwen3.6:35b-a3b-q8_0", "qwen3.6:35b-a3b-q8_0"),
            ("GLM-4.7-Flash:latest (30B, local)", "glm-4.7-flash:latest"),
            ("Qwen3.5:4b (4B, local)", "qwen3.5:4b"),
            ("Qwen3:latest (8B, local)", "qwen3:latest"),
            ("GPT-OSS:latest (20B, local)", "gpt-oss:20b"),
            ("Custom model ID", "custom"),
        ],
        "deep": [
            ("Omnicode Local - Best free model", "auto/best"),
            (
                "Omnicode Local - openrouter/openrouter/free",
                "openrouter/openrouter/free",
            ),
            ("qwen3.6:35b-a3b-q8_0", "qwen3.6:35b-a3b-q8_0"),
            ("GLM-4.7-Flash:latest (30B, local)", "glm-4.7-flash:latest"),
            ("Qwen3.5:4b (4B, local)", "qwen3.5:4b"),
            ("GPT-OSS:latest (20B, local)", "gpt-oss:20b"),
            ("Qwen3:latest (8B, local)", "qwen3:latest"),
            ("Custom model ID", "custom"),
        ],
    },
}


def _build_model_options() -> ProviderModeOptions:
    """Return the built-in catalog with the external providers merged in."""
    merged: ProviderModeOptions = {
        provider: {mode: list(options) for mode, options in mode_options.items()}
        for provider, mode_options in _BUILTIN_MODEL_OPTIONS.items()
    }

    for provider_key, provider in get_external_providers().items():
        merged[provider_key] = with_custom_option(provider)

    return merged


# Built-in catalog plus every provider from the external file.
MODEL_OPTIONS: ProviderModeOptions = _build_model_options()


def refresh_model_options() -> ProviderModeOptions:
    """Reload the external providers into MODEL_OPTIONS.

    The function updates MODEL_OPTIONS in place, so modules that imported the
    name keep seeing the current catalog.
    """
    fresh = _build_model_options()

    if fresh != MODEL_OPTIONS:
        MODEL_OPTIONS.clear()
        MODEL_OPTIONS.update(fresh)

    return MODEL_OPTIONS


def get_provider_options() -> Dict[str, List[Tuple[str, Optional[str]]]]:
    """Return (label, base_url) for every external provider, in file order."""
    return {
        provider_key: (provider.label, provider.base_url)
        for provider_key, provider in get_external_providers().items()
    }


def get_model_options(provider: str, mode: str) -> List[ModelOption]:
    """Return shared model options for a provider and selection mode."""
    return refresh_model_options()[provider.lower()][mode]


def get_default_provider() -> Optional[str]:
    """Return the provider the CLI should preselect, or None.

    The value comes from the `default_provider` key in `models.json`. It is
    None when the file marks no provider, in which case callers keep their own
    built-in default.
    """
    return _get_file_default_provider()


def get_default_model(provider: str, mode: str) -> Optional[str]:
    """Return the model ID marked as default for a provider and mode.

    The mark is the option object field `"default": true` in `models.json`.
    The result is None for a built-in provider, for a mode with no mark, and
    for a provider that is not in the catalog at all, so callers can fall back
    to their own default or to the first option of the list.
    """
    entry = get_external_providers().get(provider.strip().lower())

    if entry is None:
        return None

    return entry.defaults.get(mode)


def get_known_models() -> Dict[str, List[str]]:
    """Build known model names from the shared CLI catalog."""
    return {
        provider: sorted(
            {value for options in mode_options.values() for _, value in options}
        )
        for provider, mode_options in refresh_model_options().items()
    }
