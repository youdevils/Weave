import datetime
import os
import tempfile
import time
from pathlib import Path
from unittest import mock

import yaml
from django.test import SimpleTestCase

from website import help_content

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "help_articles"


def write_article(directory, category, slug, metadata, body="Body text."):
    category_dir = Path(directory) / category
    category_dir.mkdir(parents=True, exist_ok=True)
    text = "---\n" + yaml.safe_dump(metadata, sort_keys=False) + "---\n\n" + body
    (category_dir / f"{slug}.md").write_text(text, encoding="utf-8")


class FixtureContentTestCase(SimpleTestCase):
    """Points help_content at website/tests/fixtures/help_articles/ for the test."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(help_content, "CONTENT_DIR", FIXTURES_DIR)
        patcher.start()
        self.addCleanup(patcher.stop)
        help_content.clear_cache()
        self.addCleanup(help_content.clear_cache)


class TempContentTestCase(SimpleTestCase):
    """Points help_content at a fresh, empty temp directory for the test."""

    def setUp(self):
        super().setUp()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp_dir.cleanup)
        patcher = mock.patch.object(help_content, "CONTENT_DIR", Path(self.tmp_dir.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        help_content.clear_cache()
        self.addCleanup(help_content.clear_cache)


class LoaderAgainstFixturesTests(FixtureContentTestCase):

    def test_the_shipped_fixture_corpus_parses_without_error(self):
        articles = help_content.get_all_articles(include_drafts=True)

        self.assertEqual(len(articles), 3)

    def test_get_article_returns_a_published_article_by_category_and_slug(self):
        article = help_content.get_article("getting-started", "what-is-onyxjar")

        self.assertIsNotNone(article)
        self.assertEqual(article.title, "What is OnyxJar?")

    def test_get_article_returns_none_for_an_unknown_slug(self):
        self.assertIsNone(help_content.get_article("getting-started", "does-not-exist"))

    def test_draft_articles_are_excluded_from_get_all_articles_by_default(self):
        slugs = [a.slug for a in help_content.get_all_articles()]

        self.assertNotIn("upcoming-integrations-preview", slugs)

    def test_get_all_articles_includes_drafts_when_requested(self):
        slugs = [a.slug for a in help_content.get_all_articles(include_drafts=True)]

        self.assertIn("upcoming-integrations-preview", slugs)

    def test_a_draft_article_is_not_returned_by_get_article_without_include_drafts(self):
        self.assertIsNone(help_content.get_article("getting-started", "upcoming-integrations-preview"))

    def test_get_articles_in_category_orders_by_nav_order(self):
        articles = help_content.get_articles_in_category("getting-started")

        self.assertEqual([a.slug for a in articles], ["what-is-onyxjar", "roles-and-permissions"])

    def test_markdown_renders_tables_fenced_code_and_admonition_callouts(self):
        article = help_content.get_article("getting-started", "what-is-onyxjar")

        self.assertIn("<table>", article.html)
        self.assertIn("<pre>", article.html)
        self.assertIn('class="admonition note"', article.html)
        self.assertIn('class="admonition warning"', article.html)

    def test_headings_get_stable_ids_matching_the_rendered_html(self):
        article = help_content.get_article("getting-started", "what-is-onyxjar")

        self.assertGreaterEqual(len(article.headings), 3)
        for heading in article.headings:
            self.assertIn(f'id="{heading.id}"', article.html)

    def test_get_prev_next_follows_nav_order_and_skips_drafts(self):
        first = help_content.get_article("getting-started", "what-is-onyxjar")
        second = help_content.get_article("getting-started", "roles-and-permissions")

        before, after = help_content.get_prev_next(first)
        self.assertIsNone(before)
        self.assertEqual(after.slug, "roles-and-permissions")

        before, after = help_content.get_prev_next(second)
        self.assertEqual(before.slug, "what-is-onyxjar")
        self.assertIsNone(after)

    def test_get_related_resolves_slugs_to_published_articles_only(self):
        article = help_content.get_article("getting-started", "what-is-onyxjar")

        related = help_content.get_related(article)

        self.assertEqual([a.slug for a in related], ["roles-and-permissions"])

    def test_get_all_articles_returns_the_same_object_when_the_corpus_is_unchanged(self):
        first = help_content.get_all_articles()
        second = help_content.get_all_articles()

        self.assertIs(first, second)


class RealContentDirectoryTests(SimpleTestCase):
    """The public corpus ships empty; the article library is added later."""

    def setUp(self):
        super().setUp()
        help_content.clear_cache()
        self.addCleanup(help_content.clear_cache)

    def test_the_real_help_articles_directory_has_no_articles_yet(self):
        self.assertEqual(help_content.get_all_articles(include_drafts=True), ())


class LoaderValidationTests(TempContentTestCase):

    def test_a_missing_required_field_raises_a_clear_error(self):
        write_article(
            self.tmp_dir.name,
            "getting-started",
            "broken",
            {"slug": "broken", "category": "getting-started", "nav_order": 1, "status": "published"},
        )

        with self.assertRaises(help_content.HelpContentError):
            help_content.get_all_articles(include_drafts=True)

    def test_a_slug_that_does_not_match_its_filename_is_rejected(self):
        write_article(
            self.tmp_dir.name,
            "getting-started",
            "broken",
            {
                "title": "Broken",
                "slug": "not-the-filename",
                "summary": "Summary.",
                "category": "getting-started",
                "nav_order": 1,
                "status": "published",
            },
        )

        with self.assertRaises(help_content.HelpContentError):
            help_content.get_all_articles(include_drafts=True)

    def test_a_category_that_does_not_match_its_directory_is_rejected(self):
        write_article(
            self.tmp_dir.name,
            "getting-started",
            "broken",
            {
                "title": "Broken",
                "slug": "broken",
                "summary": "Summary.",
                "category": "model-fundamentals",
                "nav_order": 1,
                "status": "published",
            },
        )

        with self.assertRaises(help_content.HelpContentError):
            help_content.get_all_articles(include_drafts=True)

    def test_duplicate_nav_order_within_a_category_is_rejected(self):
        write_article(
            self.tmp_dir.name,
            "getting-started",
            "first",
            {
                "title": "First",
                "slug": "first",
                "summary": "Summary.",
                "category": "getting-started",
                "nav_order": 1,
                "status": "published",
            },
        )
        write_article(
            self.tmp_dir.name,
            "getting-started",
            "second",
            {
                "title": "Second",
                "slug": "second",
                "summary": "Summary.",
                "category": "getting-started",
                "nav_order": 1,
                "status": "published",
            },
        )

        with self.assertRaises(help_content.HelpContentError):
            help_content.get_all_articles(include_drafts=True)

    def test_a_related_slug_that_does_not_exist_is_rejected(self):
        write_article(
            self.tmp_dir.name,
            "getting-started",
            "lonely",
            {
                "title": "Lonely",
                "slug": "lonely",
                "summary": "Summary.",
                "category": "getting-started",
                "nav_order": 1,
                "status": "published",
                "related": ["does-not-exist"],
            },
        )

        with self.assertRaises(help_content.HelpContentError):
            help_content.get_all_articles(include_drafts=True)

    def test_a_slug_that_collides_across_categories_is_rejected(self):
        write_article(
            self.tmp_dir.name,
            "getting-started",
            "shared-slug",
            {
                "title": "First",
                "slug": "shared-slug",
                "summary": "Summary.",
                "category": "getting-started",
                "nav_order": 1,
                "status": "published",
            },
        )
        write_article(
            self.tmp_dir.name,
            "model-fundamentals",
            "shared-slug",
            {
                "title": "Second",
                "slug": "shared-slug",
                "summary": "Summary.",
                "category": "model-fundamentals",
                "nav_order": 1,
                "status": "published",
            },
        )

        with self.assertRaises(help_content.HelpContentError):
            help_content.get_all_articles(include_drafts=True)

    def test_an_invalid_status_is_rejected(self):
        write_article(
            self.tmp_dir.name,
            "getting-started",
            "broken",
            {
                "title": "Broken",
                "slug": "broken",
                "summary": "Summary.",
                "category": "getting-started",
                "nav_order": 1,
                "status": "unpublished",
            },
        )

        with self.assertRaises(help_content.HelpContentError):
            help_content.get_all_articles(include_drafts=True)

    def test_the_cache_picks_up_a_changed_file(self):
        write_article(
            self.tmp_dir.name,
            "getting-started",
            "changeable",
            {
                "title": "Original title",
                "slug": "changeable",
                "summary": "Summary.",
                "category": "getting-started",
                "nav_order": 1,
                "status": "published",
            },
        )
        first = help_content.get_article("getting-started", "changeable")
        self.assertEqual(first.title, "Original title")

        path = Path(self.tmp_dir.name) / "getting-started" / "changeable.md"
        write_article(
            self.tmp_dir.name,
            "getting-started",
            "changeable",
            {
                "title": "Updated title",
                "slug": "changeable",
                "summary": "Summary.",
                "category": "getting-started",
                "nav_order": 1,
                "status": "published",
            },
        )
        future = time.time() + 5
        os.utime(path, (future, future))

        second = help_content.get_article("getting-started", "changeable")
        self.assertEqual(second.title, "Updated title")

    def test_a_date_frontmatter_value_is_accepted_and_normalised(self):
        """
        A YAML date like ``updated: 2026-01-01`` (no quotes) is auto-parsed by
        PyYAML into a date object, not a string — this must not be rejected.
        """

        write_article(
            self.tmp_dir.name,
            "getting-started",
            "dated",
            {
                "title": "Dated",
                "slug": "dated",
                "summary": "Summary.",
                "category": "getting-started",
                "nav_order": 1,
                "status": "published",
                "updated": datetime.date(2026, 1, 1),
            },
        )

        article = help_content.get_article("getting-started", "dated")
        self.assertEqual(article.updated, "2026-01-01")
