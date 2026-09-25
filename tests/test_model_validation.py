import unittest
import warnings

import pytest

from tradingagents.llm_clients.base_client import BaseLLMClient
from tradingagents.llm_clients.model_catalog import refresh_model_options
from tradingagents.llm_clients.model_catalog import MODEL_OPTIONS, get_known_models
from tradingagents.llm_clients.validators import _open_model_providers, validate_model


class DummyLLMClient(BaseLLMClient):
    def __init__(self, provider: str, model: str):
        self.provider = provider
        super().__init__(model)

    def get_llm(self):
        self.warn_if_unknown_model()
        return object()

    def validate_model(self) -> bool:
        return validate_model(self.provider, self.model)


@pytest.mark.unit
class ModelValidationTests(unittest.TestCase):
    def test_every_catalog_option_is_a_display_value_pair(self):
        """Each option must unpack to exactly (display, value).

        The CLI and get_known_models() both unpack two items, so an option
        with a third element only fails later, inside the interactive picker.
        """
        for provider, mode_options in refresh_model_options().items():
            for mode, options in mode_options.items():
                for option in options:
                    with self.subTest(provider=provider, mode=mode, option=option):
                        self.assertEqual(len(option), 2)
                        display, value = option
                        self.assertTrue(display.strip())
                        self.assertTrue(value.strip())

    def test_open_providers_offer_a_custom_model_escape_hatch(self):
        """A provider that accepts any model must let the user type a model ID."""
        catalog = refresh_model_options()

        for provider in _open_model_providers() & set(catalog):
            for mode in ("quick", "deep"):
                values = {value for _, value in catalog[provider][mode]}
                with self.subTest(provider=provider, mode=mode):
                    self.assertIn("custom", values)

    def test_cli_catalog_models_are_all_validator_approved(self):
        open_providers = _open_model_providers()

        for provider, models in get_known_models().items():
            if provider in open_providers:
                continue

            for model in models:
                with self.subTest(provider=provider, model=model):
                    self.assertTrue(validate_model(provider, model))

    def test_unknown_model_emits_warning_for_strict_provider(self):
        client = DummyLLMClient("openai", "not-a-real-openai-model")

        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            client.get_llm()

        self.assertEqual(len(caught), 1)
        self.assertIn("not-a-real-openai-model", str(caught[0].message))
        self.assertIn("openai", str(caught[0].message))

    def test_open_providers_accept_custom_models_without_warning(self):
        for provider in _open_model_providers():
            client = DummyLLMClient(provider, "custom-model-name")

            with self.subTest(provider=provider):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    client.get_llm()

                self.assertEqual(caught, [])

    def test_catalog_is_not_empty(self):
        """Guard against a catalog that lost every provider during a refactor."""
        self.assertIn("openai", MODEL_OPTIONS)
