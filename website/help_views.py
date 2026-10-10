"""
Help & Documentation views: landing page, category listing, article page and
search. Kept separate from ``views.py`` (the marketing pages) the same way
``examples.py``/``forms.py``/``services/emails.py`` already split this app by
concern.
"""

from django.http import Http404
from django.shortcuts import render
from django.views.decorators.http import require_safe

from . import help_content
from . import help_search as search_module
from .help_categories import HELP_CATEGORIES, get_category


def _sidebar_categories():
    """categories, each paired with its own articles, for the landing page grid
    and the left-hand sidebar tree alike."""

    return [
        (category, help_content.get_articles_in_category(category.slug))
        for category in HELP_CATEGORIES
    ]


@require_safe
def help_home(request):
    return render(
        request,
        "website/help_home.html",
        {
            "nav_active": "help",
            "categories": _sidebar_categories(),
            "page_title": "Help & documentation — OnyxJar",
            "page_description": (
                "Find answers and step-by-step guidance for getting started, building "
                "your model, working with AI, publishing, and troubleshooting OnyxJar."
            ),
        },
    )


@require_safe
def help_category(request, category_slug):
    category = get_category(category_slug)
    if category is None:
        raise Http404("Unknown help category.")

    return render(
        request,
        "website/help_category.html",
        {
            "nav_active": "help",
            "category": category,
            "categories": _sidebar_categories(),
            "articles": help_content.get_articles_in_category(category_slug),
            "page_title": f"{category.name} — Help — OnyxJar",
            "page_description": category.description,
        },
    )


@require_safe
def help_article(request, category_slug, article_slug):
    category = get_category(category_slug)
    if category is None:
        raise Http404("Unknown help category.")

    article = help_content.get_article(category_slug, article_slug)
    if article is None:
        raise Http404("Unknown help article.")

    prev_article, next_article = help_content.get_prev_next(article)

    return render(
        request,
        "website/help_article.html",
        {
            "nav_active": "help",
            "category": category,
            "categories": _sidebar_categories(),
            "article": article,
            "show_toc": len(article.headings) >= 3,
            "prev_article": prev_article,
            "next_article": next_article,
            "related_articles": help_content.get_related(article),
            "page_title": f"{article.title} — Help — OnyxJar",
            "page_description": article.summary,
        },
    )


@require_safe
def help_search(request):
    query = request.GET.get("q", "").strip()
    results = search_module.search(query) if query else ()

    return render(
        request,
        "website/help_search.html",
        {
            "nav_active": "help",
            "categories": HELP_CATEGORIES,
            "query": query,
            "results": results,
            "page_title": (
                f'Search help for "{query}" — OnyxJar' if query else "Search help — OnyxJar"
            ),
            "page_description": "Search OnyxJar's help & documentation.",
        },
    )
