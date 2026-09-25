"""Tests for the external provider catalog in models.json."""

import contextlib
import importlib
import json
import os
import warnings
from pathlib import Path

import pytest

from tradingagents.llm_clients import external_providers
from tradingagents.llm_clients.factory import create_llm_client
from tradingagents.llm_clients.model_catalog import (
    get_default_model,
    get_default_provider,
    get_known_models,
    get_model_options,
    get_provider_options,
)
from tradingagents.llm_clients.openai_client import _provider_endpoint
from tradingagents.llm_clients.validators import validate_model


def _write(path: Path, document, stamp: int = 1_000_000_000) -> Path:
    """Write a models file and pin its modification time to force a reload."""
    path.write_text(json.dumps(document), encoding="utf-8")
    os.utime(path, ns=(stamp * 1_000_000_000, stamp * 1_000_000_000))
    return path


@contextlib.contextmanager
def reloaded_default_config(**env):
    """Rebuild `default_config` under the given environment, then restore it.

    The module reads the environment at import time, so the test needs a fresh
    import to see a different value.
    """
    module = importlib.import_module("tradingagents.default_config")
    saved = {name: os.environ.get(name) for name in env}

    os.environ.update(env)
    try:
        yield importlib.reload(module)
    finally:
        for name, value in saved.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value
        importlib.reload(module)


@pytest.fixture()
def models_file(tmp_path, monkeypatch):
    """Point the loader at a temporary file and restore the real one after."""
    target = tmp_path / "models.json"
    monkeypatch.setenv(external_providers.MODELS_FILE_ENV, str(target))
    yield target
    monkeypatch.delenv(external_providers.MODELS_FILE_ENV, raising=False)
    external_providers.reload_external_providers()


@pytest.mark.unit
class TestExternalProviderLoading:
    def test_shipped_file_defines_the_self_hosted_providers(self):
        """models.json must define the two self-hosted endpoints."""
        providers = external_providers.get_external_providers()

        assert "unsloth-desktop" in providers
        assert "mtplx-server" in providers
        assert providers["unsloth-desktop"].base_url == "http://127.0.0.1:8888/v1"
        assert providers["mtplx-server"].api_key_env == "MTPLX_API_KEY"

    def test_shipped_file_parses_without_warnings(self):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            external_providers.reload_external_providers()

        assert [str(warning.message) for warning in caught] == []

    def test_new_provider_needs_no_python_change(self, models_file):
        _write(
            models_file,
            {
                "providers": {
                    "lab-box": {
                        "label": "Lab Box (LAN)",
                        "client": "openai",
                        "base_url": "http://10.0.0.9:8000/v1",
                        "api_key_env": "LAB_API_KEY",
                        "open_models": True,
                        "allow_custom_model": True,
                        "models": {
                            "quick": [["Lab 14B - fast", "lab-14b"]],
                            "deep": [["Lab 70B - best", "lab-70b"]],
                        },
                    }
                }
            },
        )
        external_providers.reload_external_providers()

        # Catalog and pickers
        assert [value for _, value in get_model_options("lab-box", "quick")] == [
            "lab-14b",
            "custom",
        ]
        assert "lab-70b" in get_known_models()["lab-box"]
        assert get_provider_options()["lab-box"] == (
            "Lab Box (LAN)",
            "http://10.0.0.9:8000/v1",
        )

        # Client factory and endpoint defaults
        client = create_llm_client("lab-box", "lab-14b")
        assert client.provider == "lab-box"
        assert client.base_url == "http://10.0.0.9:8000/v1"
        assert _provider_endpoint("lab-box") == (
            "http://10.0.0.9:8000/v1",
            "LAB_API_KEY",
        )

        # Open model list skips the known-model check
        assert validate_model("lab-box", "anything-goes")

    def test_supplied_base_url_wins_over_the_file(self, models_file):
        _write(
            models_file,
            {
                "providers": {
                    "lab-box": {
                        "base_url": "http://10.0.0.9:8000/v1",
                        "models": {"quick": [["Lab 14B", "lab-14b"]]},
                    }
                }
            },
        )
        external_providers.reload_external_providers()

        client = create_llm_client("lab-box", "lab-14b", "http://127.0.0.1:1234/v1")
        assert client.base_url == "http://127.0.0.1:1234/v1"

    def test_object_options_and_single_mode_list(self, models_file):
        """An object option and a single mode list are enough for a provider."""
        _write(
            models_file,
            {
                "providers": {
                    "lab-box": {
                        "models": {
                            "quick": [{"label": "Lab 14B - fast", "id": "lab-14b"}],
                        }
                    }
                }
            },
        )
        external_providers.reload_external_providers()

        provider = external_providers.get_external_provider("lab-box")
        assert provider.label == "lab-box"
        assert provider.client == "openai"
        assert provider.base_url is None
        assert provider.models["quick"] == [("Lab 14B - fast", "lab-14b")]
        # A mode that is not in the file copies the mode that is.
        assert provider.models["deep"] == [("Lab 14B - fast", "lab-14b")]

    def test_bare_provider_map_is_accepted(self, models_file):
        _write(
            models_file,
            {
                "lab-box": {
                    "models": {"quick": [["Lab 14B", "lab-14b"]]},
                }
            },
        )
        external_providers.reload_external_providers()

        assert "lab-box" in external_providers.get_external_providers()

    def test_edits_are_picked_up_without_a_restart(self, models_file):
        _write(
            models_file,
            {"providers": {"lab-box": {"models": {"quick": [["Lab 14B", "lab-14b"]]}}}},
            stamp=1_000_000_000,
        )
        external_providers.reload_external_providers()
        assert [value for _, value in get_model_options("lab-box", "quick")] == [
            "lab-14b"
        ]

        _write(
            models_file,
            {
                "providers": {
                    "lab-box": {
                        "models": {
                            "quick": [["Lab 14B", "lab-14b"], ["Lab 70B", "lab-70b"]]
                        }
                    }
                }
            },
            stamp=2_000_000_000,
        )
        assert [value for _, value in get_model_options("lab-box", "quick")] == [
            "lab-14b",
            "lab-70b",
        ]

    def test_missing_file_yields_no_providers(self, models_file):
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert external_providers.reload_external_providers() == {}

        assert any("not found" in str(warning.message) for warning in caught)

    def test_broken_json_is_ignored(self, models_file):
        models_file.write_text("{ not json", encoding="utf-8")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            assert external_providers.reload_external_providers() == {}

        assert any("models file" in str(warning.message) for warning in caught)

    def test_invalid_entries_are_skipped(self, models_file):
        _write(
            models_file,
            {
                "providers": {
                    "bad-client": {
                        "client": "llama.cpp",
                        "models": {"quick": [["Model", "model-id"]]},
                    },
                    "no-models": {"label": "No Models"},
                    "bad-option": {"models": {"quick": [["Only one field"]]}},
                    "good-box": {
                        "allow_custom_model": True,
                        "models": {"quick": [["Lab 14B", "lab-14b"]]},
                    },
                }
            },
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            providers = external_providers.reload_external_providers()

        assert set(providers) == {"good-box"}
        assert [value for _, value in get_model_options("good-box", "quick")] == [
            "lab-14b",
            "custom",
        ]
        messages = [str(warning.message) for warning in caught]
        for skipped in ("bad-client", "no-models", "bad-option"):
            assert any(skipped in message for message in messages)
        assert not any("good-box" in message for message in messages)

    def test_custom_entry_is_not_duplicated(self, models_file):
        _write(
            models_file,
            {
                "providers": {
                    "lab-box": {
                        "allow_custom_model": True,
                        "models": {
                            "quick": [
                                ["Custom model ID", "custom"],
                                ["Lab 14B", "lab-14b"],
                            ]
                        },
                    }
                }
            },
        )
        external_providers.reload_external_providers()

        values = [value for _, value in get_model_options("lab-box", "quick")]
        assert values.count("custom") == 1

    def test_repo_file_is_found_without_the_env_override(self, monkeypatch):
        """The loader finds models.json at the repository root on its own."""
        monkeypatch.delenv(external_providers.MODELS_FILE_ENV, raising=False)

        found = external_providers.find_models_file()

        assert found is not None
        assert found.name == "models.json"
        assert found.is_file()

    def test_shipped_file_marks_mtplx_as_the_default(self):
        """The shipped file starts the CLI on the MTPLX server."""
        assert get_default_provider() == "mtplx-server"
        assert (
            get_default_model("mtplx-server", "quick")
            == "mtplx-qwen36-35b-a3b-optimized-balance"
        )
        assert (
            get_default_model("mtplx-server", "deep")
            == "mtplx-qwen36-35b-a3b-optimized-balance"
        )

    def test_shipped_file_leaves_the_other_provider_unmarked(self):
        """Only the marked provider and model have defaults."""
        assert get_default_model("unsloth-desktop", "quick") is None
        # A built-in provider is not in the file, so it has no mark either.
        assert get_default_model("openai", "quick") is None
        assert get_default_model("no-such-provider", "quick") is None


@pytest.mark.unit
class TestDefaultSelection:
    """The `default_provider` key and the `"default": true` option mark."""

    def test_marked_option_is_the_default_for_its_mode(self, models_file):
        _write(
            models_file,
            {
                "providers": {
                    "lab-box": {
                        "models": {
                            "quick": [
                                ["Lab 14B - fast", "lab-14b"],
                                {
                                    "label": "Lab 70B - best",
                                    "id": "lab-70b",
                                    "default": True,
                                },
                            ],
                            "deep": [
                                {
                                    "label": "Lab 70B - best",
                                    "id": "lab-70b",
                                    "default": True,
                                }
                            ],
                        }
                    }
                }
            },
        )
        external_providers.reload_external_providers()

        assert get_default_model("lab-box", "quick") == "lab-70b"
        assert get_default_model("lab-box", "deep") == "lab-70b"
        # The mark does not reorder the picker list.
        assert [value for _, value in get_model_options("lab-box", "quick")] == [
            "lab-14b",
            "lab-70b",
        ]

    def test_a_copied_mode_keeps_the_mark(self, models_file):
        """A mode the file omits copies the options and their default."""
        _write(
            models_file,
            {
                "providers": {
                    "lab-box": {
                        "models": {
                            "quick": [
                                {
                                    "label": "Lab 70B - best",
                                    "id": "lab-70b",
                                    "default": True,
                                }
                            ]
                        }
                    }
                }
            },
        )
        external_providers.reload_external_providers()

        assert get_default_model("lab-box", "quick") == "lab-70b"
        assert get_default_model("lab-box", "deep") == "lab-70b"

    def test_unmarked_provider_has_no_default(self, models_file):
        _write(
            models_file,
            {"providers": {"lab-box": {"models": {"quick": [["Lab 14B", "lab-14b"]]}}}},
        )
        external_providers.reload_external_providers()

        assert get_default_model("lab-box", "quick") is None

    def test_default_provider_key_is_read(self, models_file):
        _write(
            models_file,
            {
                "default_provider": "lab-box",
                "providers": {
                    "lab-box": {"models": {"quick": [["Lab 14B", "lab-14b"]]}}
                },
            },
        )
        external_providers.reload_external_providers()

        assert get_default_provider() == "lab-box"

    def test_no_default_provider_key_yields_none(self, models_file):
        _write(
            models_file,
            {"providers": {"lab-box": {"models": {"quick": [["Lab 14B", "lab-14b"]]}}}},
        )
        external_providers.reload_external_providers()

        assert get_default_provider() is None

    def test_default_provider_key_does_not_break_a_bare_map(self, models_file):
        """The key configures the file, so it is not read as a provider."""
        _write(
            models_file,
            {
                "default_provider": "lab-box",
                "lab-box": {"models": {"quick": [["Lab 14B", "lab-14b"]]}},
            },
        )
        external_providers.reload_external_providers()

        assert set(external_providers.get_external_providers()) == {"lab-box"}
        assert get_default_provider() == "lab-box"

    def test_unknown_default_provider_is_reported(self, models_file):
        _write(
            models_file,
            {
                "default_provider": "typo-box",
                "providers": {
                    "lab-box": {"models": {"quick": [["Lab 14B", "lab-14b"]]}}
                },
            },
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            external_providers.reload_external_providers()

        assert get_default_provider() is None
        assert any("typo-box" in str(warning.message) for warning in caught)

    def test_two_defaults_in_one_mode_keep_the_first(self, models_file):
        _write(
            models_file,
            {
                "providers": {
                    "lab-box": {
                        "models": {
                            "quick": [
                                {
                                    "label": "Lab 14B",
                                    "id": "lab-14b",
                                    "default": True,
                                },
                                {
                                    "label": "Lab 70B",
                                    "id": "lab-70b",
                                    "default": True,
                                },
                            ]
                        }
                    }
                }
            },
        )

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            external_providers.reload_external_providers()

        assert get_default_model("lab-box", "quick") == "lab-14b"
        assert any(
            "more than one default" in str(warning.message) for warning in caught
        )

    def test_config_takes_the_default_from_the_file(self):
        with reloaded_default_config(LLM_PROVIDER="", LLM_MODEL="") as module:
            config = module.DEFAULT_CONFIG

            assert config["llm_provider"] == "mtplx-server"
            assert config["quick_think_llm"] == "mtplx-qwen36-35b-a3b-optimized-balance"
            assert config["deep_think_llm"] == "mtplx-qwen36-35b-a3b-optimized-balance"
            # The endpoint comes from the file, so config needs no URL.
            assert config["backend_url"] is None
            assert _provider_endpoint("mtplx-server")[0] == (
                "http://192.168.178.79:8000/v1"
            )

    def test_environment_provider_beats_the_file_default(self):
        """Picking a provider by hand must not keep the file's model."""
        with reloaded_default_config(LLM_PROVIDER="openai", LLM_MODEL="") as module:
            config = module.DEFAULT_CONFIG

            assert config["llm_provider"] == "openai"
            # OpenAI has no marked model, so the built-in fallback stays.
            assert config["quick_think_llm"] == "auto/best"

    def test_environment_model_beats_the_marked_model(self):
        with reloaded_default_config(LLM_PROVIDER="", LLM_MODEL="gpt-5.4") as module:
            config = module.DEFAULT_CONFIG

            assert config["llm_provider"] == "mtplx-server"
            assert config["quick_think_llm"] == "gpt-5.4"
            assert config["deep_think_llm"] == "gpt-5.4"
