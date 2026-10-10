from pathlib import Path
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from website import help_content, help_search

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "help_articles"


class FixtureContentTestCase(SimpleTestCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(help_content, "CONTENT_DIR", FIXTURES_DIR)
        patcher.start()
        self.addCleanup(patcher.stop)
        help_content.clear_cache()
        help_search.clear_cache()
        self.addCleanup(help_content.clear_cache)
        self.addCleanup(help_search.clear_cache)


class SearchFunctionTests(FixtureContentTestCase):

    def test_an_empty_query_returns_no_results(self):
        self.assertEqual(help_search.search(""), ())
        self.assertEqual(help_search.search("   "), ())

    def test_finds_an_article_by_a_title_word(self):
        results = help_search.search("OnyxJar")

        self.assertIn("what-is-onyxjar", [r.slug for r in results])

    def test_finds_an_article_by_a_keyword_not_in_the_title(self):
        results = help_search.search("orientation")

        self.assertIn("what-is-onyxjar", [r.slug for r in results])

    def test_excludes_draft_articles(self):
        results = help_search.search("integrations")

        self.assertEqual(results, ())

    def test_a_query_with_no_matches_returns_an_empty_tuple(self):
        self.assertEqual(help_search.search("zzzznomatch"), ())

    def test_a_title_match_ranks_above_a_body_only_match(self):
        results = help_search.search("roles")

        slugs = [r.slug for r in results]
        self.assertEqual(slugs[0], "roles-and-permissions")


class SearchViewTests(FixtureContentTestCase):

    def test_the_search_view_renders_results_for_a_query(self):
        response = self.client.get(reverse("website:help_search"), {"q": "roles"})

        self.assertContains(response, "Roles and permissions")

    def test_the_search_view_shows_the_empty_state_for_no_matches(self):
        response = self.client.get(reverse("website:help_search"), {"q": "zzzznomatch"})

        self.assertContains(response, "No articles matched")

    def test_the_search_view_with_no_query_shows_a_prompt_not_an_error(self):
        response = self.client.get(reverse("website:help_search"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a word or phrase")

    def test_the_search_results_page_is_not_indexed(self):
        response = self.client.get(reverse("website:help_search"), {"q": "roles"})

        self.assertContains(response, '<meta name="robots" content="noindex">')


class RealCorpusSearchTests(TestCase):

    def setUp(self):
        super().setUp()
        help_content.clear_cache()
        help_search.clear_cache()
        self.addCleanup(help_content.clear_cache)
        self.addCleanup(help_search.clear_cache)

    def test_searching_the_real_empty_corpus_returns_no_results(self):
        self.assertEqual(help_search.search("anything"), ())
