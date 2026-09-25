"""Load user-defined LLM providers and models from an external JSON file.

`model_catalog.py` holds the providers that ship with the package. Self-hosted
and LAN endpoints, such as a local Unsloth Desktop app or an MTPLX inference
server, change often, so their provider settings and model lists live in
`models.json` at the repository root. Add a provider or a model there; no
Python change is needed.

File resolution order:

1. The path in the `TRADINGAGENTS_MODELS_FILE` environment variable.
2. `models.json` next to the repository root (two levels above this package).
3. `models.json` in the current working directory.

The file is re-read when its modification time changes, so a long-running web
server picks up edits without a restart. A missing or invalid file is not fatal:
the built-in catalog keeps working and a `RuntimeWarning` names the problem.
"""

from __future__ import annotations

import json
import os
import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ModelOption = Tuple[str, str]

MODELS_FILENAME = "models.json"
MODELS_FILE_ENV = "TRADINGAGENTS_MODELS_FILE"

# Selection modes used by the CLI pickers.
MODES = ("quick", "deep")

# Client implementations a provider can declare.
CLIENTS = ("openai", "anthropic", "google", "azure")

DEFAULT_CLIENT = "openai"

# Top-level key that names the provider to preselect in the CLI.
DEFAULT_PROVIDER_FIELD = "default_provider"

# Option key that marks a model as the preselected one of its mode.
DEFAULT_OPTION_FIELD = "default"

# Option value that makes the CLI prompt for a model ID.
CUSTOM_MODEL_ID = "custom"
CUSTOM_MODEL_LABEL = "Custom model ID"


@dataclass(frozen=True)
class ExternalProvider:
    """One provider entry from `models.json`."""

    key: str
    label: str
    client: str
    base_url: Optional[str]
    api_key_env: Optional[str]
    open_models: bool
    allow_custom_model: bool
    models: Dict[str, List[ModelOption]]
    # Mode -> model id of the option marked with "default": true.
    defaults: Dict[str, str] = field(default_factory=dict)


# Cache keyed by file modification time so edits are picked up without a restart.
_CACHE: Dict[str, Any] = {"stamp": None, "providers": {}, "default_provider": None}


def find_models_file() -> Optional[Path]:
    """Return the path of the external models file, or None when there is none."""
    override = os.environ.get(MODELS_FILE_ENV, "").strip()
    if override:
        return Path(override).expanduser()

    # .../<repo>/tradingagents/llm_clients/external_providers.py -> <repo>/models.json
    repo_root = Path(__file__).resolve().parents[2]
    candidates = [repo_root / MODELS_FILENAME, Path.cwd() / MODELS_FILENAME]

    for candidate in candidates:
        if candidate.is_file():
            return candidate

    return None


def get_external_providers() -> Dict[str, ExternalProvider]:
    """Return providers from the external file, keyed by provider name.

    The result is empty when no file exists. Call `reload_external_providers()`
    after you rewrite the file if you need the new state without waiting for
    the modification time to change.
    """
    path = find_models_file()

    if path is None:
        _set_cache(None, {}, None)
        return {}

    if not path.is_file():
        _warn(f"Models file not found: {path}")
        _set_cache(None, {}, None)
        return {}

    try:
        stamp = path.stat().st_mtime_ns
    except OSError as exc:
        _warn(f"Cannot read models file {path}: {exc}")
        return {}

    if _CACHE["stamp"] != stamp:
        _set_cache(stamp, *_parse_file(path))

    return _CACHE["providers"]


def reload_external_providers() -> Dict[str, ExternalProvider]:
    """Drop the cache and read the external file again."""
    _set_cache(None, {}, None)
    return get_external_providers()


def get_external_provider(key: str) -> Optional[ExternalProvider]:
    """Return one external provider, or None when it is not defined."""
    return get_external_providers().get(key.strip().lower())


def get_default_provider() -> Optional[str]:
    """Return the provider key named by `default_provider`, or None.

    The result is None when the file marks no provider, or when the marked
    provider is not one the file defines.
    """
    get_external_providers()
    return _CACHE["default_provider"]


def _set_cache(
    stamp: Optional[int],
    providers: Dict[str, ExternalProvider],
    default_provider: Optional[str],
) -> None:
    _CACHE["stamp"] = stamp
    _CACHE["providers"] = providers
    _CACHE["default_provider"] = default_provider


def _warn(message: str) -> None:
    warnings.warn(message, RuntimeWarning, stacklevel=3)


def _parse_file(path: Path) -> Tuple[Dict[str, ExternalProvider], Optional[str]]:
    """Read and validate the external file. Invalid entries are skipped.

    Returns the providers and the key named by `default_provider`.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        _warn(f"Ignoring models file {path}: {exc}")
        return {}, None

    if not isinstance(document, dict):
        _warn(f"Ignoring models file {path}: top level must be a JSON object.")
        return {}, None

    raw_providers = _extract_providers(document, path)
    if not raw_providers:
        return {}, None

    providers: Dict[str, ExternalProvider] = {}
    for key, spec in raw_providers.items():
        provider = _parse_provider(key, spec, path)
        if provider is not None:
            providers[provider.key] = provider

    return providers, _parse_default_provider(document, providers, path)


def _parse_default_provider(
    document: Dict[str, Any], providers: Dict[str, ExternalProvider], path: Path
) -> Optional[str]:
    """Return the `default_provider` key when the file defines that provider."""
    raw = document.get(DEFAULT_PROVIDER_FIELD)

    if raw is None:
        return None

    key = _parse_optional_text(raw)

    if key is None:
        _warn(
            f"Ignoring '{DEFAULT_PROVIDER_FIELD}' in {path}: expected a provider key."
        )
        return None

    if key.lower() not in providers:
        _warn(
            f"Ignoring '{DEFAULT_PROVIDER_FIELD}' in {path}: "
            f"no provider named '{key}' in this file."
        )
        return None

    return key.lower()


def _extract_providers(document: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """Return the provider map from a parsed document.

    The canonical form is `{"providers": {...}}`. A bare mapping of provider
    keys is also accepted, and any other top-level key is then read as a
    provider. Keys that configure the file instead of defining a provider,
    such as `default_provider` and `_help`, are dropped before that check.
    """
    if "providers" in document:
        raw = document["providers"]
        if not isinstance(raw, dict):
            _warn(f"Ignoring 'providers' in {path}: expected a JSON object.")
            return {}
        return raw

    # A bare map: skip the keys that configure the file rather than define one.
    bare = {
        key: spec
        for key, spec in document.items()
        if not str(key).startswith("_") and key != DEFAULT_PROVIDER_FIELD
    }

    if bare and all(isinstance(spec, dict) for spec in bare.values()):
        return bare

    _warn(f"Ignoring models file {path}: no 'providers' object found.")
    return {}


def _parse_provider(key: Any, spec: Any, path: Path) -> Optional[ExternalProvider]:
    """Return one provider, or None when the entry is unusable."""
    if not isinstance(key, str) or not key.strip():
        _warn(f"Ignoring a provider in {path}: the provider key must be text.")
        return None

    provider_key = key.strip().lower()
    if not isinstance(spec, dict):
        _warn(
            f"Ignoring provider '{provider_key}' in {path}: entry must be a JSON object."
        )
        return None

    client = spec.get("client", DEFAULT_CLIENT)
    if not isinstance(client, str) or client.strip().lower() not in CLIENTS:
        _warn(
            f"Ignoring provider '{provider_key}' in {path}: "
            f"'client' must be one of {', '.join(CLIENTS)}."
        )
        return None

    parsed = _parse_models(provider_key, spec.get("models"), path)
    if parsed is None:
        return None

    models, defaults = parsed

    return ExternalProvider(
        key=provider_key,
        label=_parse_label(provider_key, spec.get("label"), path),
        client=client.strip().lower(),
        base_url=_parse_optional_text(spec.get("base_url")),
        api_key_env=_parse_optional_text(spec.get("api_key_env")),
        open_models=bool(spec.get("open_models", False)),
        allow_custom_model=bool(spec.get("allow_custom_model", False)),
        models=models,
        defaults=defaults,
    )


def _parse_label(provider_key: str, label: Any, path: Path) -> str:
    """Return the display label, which defaults to the provider key."""
    if label is None:
        return provider_key

    if not isinstance(label, str) or not label.strip():
        _warn(
            f"Ignoring 'label' of provider '{provider_key}' in {path}: expected text."
        )
        return provider_key

    return label.strip()


def _parse_optional_text(value: Any) -> Optional[str]:
    """Return stripped text, or None when the value is missing or empty."""
    if value is None:
        return None

    if not isinstance(value, str):
        return None

    stripped = value.strip()
    return stripped or None


def _parse_models(
    provider_key: str, raw_models: Any, path: Path
) -> Optional[Tuple[Dict[str, List[ModelOption]], Dict[str, str]]]:
    """Return the options per mode plus the marked default per mode.

    Returns None when the provider is unusable. A mode left out of the file
    copies the mode that is present, so a provider with one model list only
    needs that list written once. Within a mode the first option marked with
    `"default": true` wins, and a mode with several marks warns.
    """
    if not isinstance(raw_models, dict) or not raw_models:
        _warn(
            f"Ignoring provider '{provider_key}' in {path}: 'models' must be a non-empty object."
        )
        return None

    models: Dict[str, List[ModelOption]] = {}
    defaults: Dict[str, str] = {}
    marked_modes: Dict[str, str] = {}

    for mode, raw_options in raw_models.items():
        if mode not in MODES:
            _warn(f"Ignoring mode '{mode}' of provider '{provider_key}' in {path}.")
            continue

        if not isinstance(raw_options, list) or not raw_options:
            _warn(
                f"Ignoring mode '{mode}' of provider '{provider_key}' in {path}: expected a list."
            )
            continue

        options: List[ModelOption] = []
        for raw_option in raw_options:
            option, is_default = _parse_option(provider_key, mode, raw_option, path)
            if option is None:
                continue

            options.append(option)

            if is_default:
                if mode in marked_modes:
                    _warn(
                        f"Provider '{provider_key}' mode '{mode}' in {path} marks more than "
                        f"one default model; the first one wins."
                    )
                else:
                    marked_modes[mode] = option[1]

        if options:
            models[mode] = options
            if mode in marked_modes:
                defaults[mode] = marked_modes[mode]

    if not models:
        _warn(f"Ignoring provider '{provider_key}' in {path}: no usable model options.")
        return None

    for mode in MODES:
        if mode not in models:
            source = next(iter(models))
            models[mode] = list(models[source])
            if source in defaults:
                defaults[mode] = defaults[source]

    return models, defaults


def _parse_option(
    provider_key: str, mode: str, raw_option: Any, path: Path
) -> Tuple[Optional[ModelOption], bool]:
    """Return one (display, value) pair and whether it is marked as default.

    The second element is False unless the object form carries
    `"default": true`, which is how a mode marks its preselected model.
    """
    where = f"provider '{provider_key}' mode '{mode}' in {path}"

    if isinstance(raw_option, (list, tuple)):
        if len(raw_option) == 2 and all(
            isinstance(part, str) and part.strip() for part in raw_option
        ):
            return (raw_option[0].strip(), raw_option[1].strip()), False

    elif isinstance(raw_option, dict):
        display = raw_option.get("label", raw_option.get("display"))
        value = raw_option.get("id", raw_option.get("value", raw_option.get("model")))
        if (
            isinstance(display, str)
            and display.strip()
            and isinstance(value, str)
            and value.strip()
        ):
            is_default = raw_option.get(DEFAULT_OPTION_FIELD, False) is True
            return (display.strip(), value.strip()), is_default

    _warn(
        f"Ignoring a model option of {where}: use [display, id] or an object with label and id."
    )
    return None, False


def add_custom_option(options: List[ModelOption]) -> List[ModelOption]:
    """Return options with the custom model ID entry appended when it is missing."""
    if any(value == CUSTOM_MODEL_ID for _, value in options):
        return list(options)

    return [*options, (CUSTOM_MODEL_LABEL, CUSTOM_MODEL_ID)]


def with_custom_option(provider: ExternalProvider) -> Dict[str, List[ModelOption]]:
    """Return the model options of a provider, honoring `allow_custom_model`."""
    models = {mode: list(options) for mode, options in provider.models.items()}

    if provider.allow_custom_model:
        models = {mode: add_custom_option(options) for mode, options in models.items()}

    return models
