from django.urls import path

from . import help_views, views

app_name = "website"

urlpatterns = [
    path("", views.home, name="home"),
    path("examples/", views.examples, name="examples"),
    path("privacy/", views.privacy, name="privacy"),
    path("terms/", views.terms, name="terms"),
    path("contact/", views.contact, name="contact"),

    # "help/search/" must be registered before the "<slug:category_slug>/"
    # pattern below, or a search request would be matched as a (nonexistent)
    # category instead.
    path("help/", help_views.help_home, name="help"),
    path("help/search/", help_views.help_search, name="help_search"),
    path("help/<slug:category_slug>/", help_views.help_category, name="help_category"),
    path(
        "help/<slug:category_slug>/<slug:article_slug>/",
        help_views.help_article,
        name="help_article",
    ),
]
