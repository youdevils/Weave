"""
Sitemap classes for the public website, including Help & Documentation.
Help sitemaps delegate to help_content's published-only filtering, so drafts
and (implicitly, once articles exist) unpublished content never appear here.
"""

import datetime

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from . import help_content
from .help_categories import HELP_CATEGORIES


class StaticViewSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.5

    def items(self):
        return [
            "website:home",
            "website:examples",
            "website:privacy",
            "website:terms",
            "website:contact",
            "website:help",
        ]

    def location(self, item):
        return reverse(item)


class HelpCategorySitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.6

    def items(self):
        return HELP_CATEGORIES

    def location(self, category):
        return reverse("website:help_category", args=[category.slug])


class HelpArticleSitemap(Sitemap):
    changefreq = "monthly"
    priority = 0.7

    def items(self):
        return help_content.get_all_articles(include_drafts=False)

    def location(self, article):
        return reverse("website:help_article", args=[article.category_slug, article.slug])

    def lastmod(self, article):
        if article.updated:
            return datetime.date.fromisoformat(article.updated)
        return None
