from django.test import SimpleTestCase

from ai.services.provider import (
    AIProvider,
    ProviderError,
    ProviderSchemaError,
    ProviderTimeoutError,
)


class ProviderContractTests(SimpleTestCase):

    def test_ai_provider_cannot_be_instantiated_directly(self):
        with self.assertRaises(TypeError):
            AIProvider()

    def test_provider_timeout_error_is_a_provider_error(self):
        self.assertTrue(issubclass(ProviderTimeoutError, ProviderError))

    def test_provider_schema_error_is_a_provider_error(self):
        self.assertTrue(issubclass(ProviderSchemaError, ProviderError))

    def test_a_concrete_provider_must_implement_both_methods(self):
        class Incomplete(AIProvider):
            def generate_structured(self, **kwargs):
                return None

        with self.assertRaises(TypeError):
            Incomplete()
