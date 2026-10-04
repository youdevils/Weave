"""
Exercises model.migrations.0024_backfill_object_key's pure helper
functions directly. The migration's own `backfill_object_keys` is mostly
a DB query + loop + bulk_update around these helpers -- its end-to-end
correctness was validated empirically against this project's real dev
data (80 pre-existing Objects, backfilled with zero collisions) when the
migration was first written, rather than via a synthetic test here: the
current schema's own uniqueness constraint (added by the very next
migration, 0025) makes it impossible to reconstruct the pre-backfill
"multiple blank-key rows" state in a normal TestCase, which is exactly
the invariant the constraint exists to guarantee going forward.
"""

import importlib

from django.test import SimpleTestCase

_migration = importlib.import_module("model.migrations.0024_backfill_object_key")
_slugify_key = _migration._slugify_key
_make_unique_key = _migration._make_unique_key


class SlugifyKeyTests(SimpleTestCase):

    def test_matches_the_service_convention(self):
        self.assertEqual(_slugify_key("Customer Account"), "customer_account")

    def test_unsluggable_name_returns_empty_string(self):
        self.assertEqual(_slugify_key("???"), "")


class MakeUniqueKeyTests(SimpleTestCase):

    def test_returns_base_slug_when_unused(self):
        self.assertEqual(_make_unique_key("Acme Ltd", set()), "acme_ltd")

    def test_appends_deterministic_numeric_suffix_on_collision(self):
        self.assertEqual(_make_unique_key("Acme Ltd", {"acme_ltd"}), "acme_ltd_2")
        self.assertEqual(
            _make_unique_key("Acme Ltd", {"acme_ltd", "acme_ltd_2"}), "acme_ltd_3",
        )

    def test_unsluggable_name_falls_back_to_object(self):
        self.assertEqual(_make_unique_key("???", set()), "object")

    def test_fallback_is_suffixed_on_collision_too(self):
        self.assertEqual(_make_unique_key("???", {"object"}), "object_2")

    def test_respects_max_length_after_suffixing(self):
        long_name = "x" * 150
        used = {"x" * _migration.MAX_KEY_LENGTH}

        candidate = _make_unique_key(long_name, used)

        self.assertLessEqual(len(candidate), _migration.MAX_KEY_LENGTH)
        self.assertNotIn(candidate, used)
        self.assertTrue(candidate.endswith("_2"))

    def test_is_deterministic(self):
        used = {"acme_ltd"}
        self.assertEqual(
            _make_unique_key("Acme Ltd", used), _make_unique_key("Acme Ltd", used),
        )
