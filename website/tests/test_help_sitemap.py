from pathlib import Path
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from website import help_content
from website.help_categories import HELP_CATEGORIES

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "help_articles"


class FixtureContentTestCase(TestCase):

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(help_content, "CONTENT_DIR", FIXTURES_DIR)
        patcher.start()
        self.addCleanup(patcher.stop)
        help_content.clear_cache()
        self.addCleanup(help_content.clear_cache)


class SitemapWithFixturesTests(FixtureContentTestCase):

    def test_the_sitemap_lists_static_category_and_published_article_urls(self):
        xml = self.client.get("/sitemap.xml").content.decode()

        self.assertIn(reverse("website:help"), xml)
        self.assertIn(reverse("website:help_category", args=["getting-started"]), xml)
        self.assertIn(
            reverse("website:help_article", args=["getting-started", "what-is-onyxjar"]), xml
        )

    def test_the_sitemap_excludes_draft_articles(self):
        xml = self.client.get("/sitemap.xml").content.decode()

        self.assertNotIn(
            reverse("website:help_article", args=["getting-started", "upcoming-integrations-preview"]),
            xml,
        )


class SitemapWithRealCorpusTests(TestCase):

    def setUp(self):
        super().setUp()
        help_content.clear_cache()
        self.addCleanup(help_content.clear_cache)

    def test_the_sitemap_lists_every_category_but_no_articles_yet(self):
        xml = self.client.get("/sitemap.xml").content.decode()

        for category in HELP_CATEGORIES:
            self.assertIn(reverse("website:help_category", args=[category.slug]), xml)


class RobotsTxtTests(TestCase):

    def test_robots_txt_references_the_sitemap(self):
        response = self.client.get("/robots.txt")
        content = response.content.decode()

        self.assertEqual(response["Content-Type"], "text/plain")
        self.assertIn("Sitemap:", content)
        self.assertIn(reverse("sitemap"), content)

    def test_robots_txt_disallows_the_search_results_page(self):
        content = self.client.get("/robots.txt").content.decode()

        self.assertIn(f"Disallow: {reverse('website:help_search')}", content)
