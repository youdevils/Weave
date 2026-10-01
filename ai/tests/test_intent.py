from django.test import SimpleTestCase, override_settings

from ai.services.intent import InvalidIntent, validate_intent


class ValidateIntentTests(SimpleTestCase):

    def test_empty_intent_is_rejected(self):
        with self.assertRaises(InvalidIntent):
            validate_intent("")

    def test_whitespace_only_intent_is_rejected(self):
        with self.assertRaises(InvalidIntent):
            validate_intent("   \n\t  ")

    @override_settings(AI_MAX_INTENT_CHARS=10)
    def test_intent_over_max_chars_is_rejected(self):
        with self.assertRaises(InvalidIntent):
            validate_intent("this is far too long")

    def test_valid_intent_is_normalised(self):
        intent = validate_intent("  Add a new widget type.  ")

        self.assertEqual(intent.text, "Add a new widget type.")
