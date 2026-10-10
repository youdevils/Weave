from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import path, include

from website import views as website_views
from website.sitemaps import HelpArticleSitemap, HelpCategorySitemap, StaticViewSitemap

sitemaps = {
    "static": StaticViewSitemap,
    "help-categories": HelpCategorySitemap,
    "help-articles": HelpArticleSitemap,
}

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sitemap.xml", sitemap, {"sitemaps": sitemaps}, name="sitemap"),
    path("robots.txt", website_views.robots_txt, name="robots_txt"),
    path("", include(("website.urls", "website"), namespace="website")),
    path("", include(("account.urls", "account"), namespace="account")),
    path("model/", include(("model.urls", "model"), namespace="model")),
    path(
        "model/", include(("publication.urls", "publication"), namespace="publication")
    ),
    path("model/", include(("ingestion.urls", "ingestion"), namespace="ingestion")),
    path("model/", include(("assisted.urls", "assisted"), namespace="assisted")),
    path("viewer/", include(("viewer.urls", "viewer"), namespace="viewer")),
    path("workspace/", include(("workspace.urls", "workspace"), namespace="workspace")),
    # path("api/", include(("api.urls", "api"), namespace="api")),
]


# Serve media and published example files during development
if settings.DEBUG:
    urlpatterns += static(
        settings.MEDIA_URL,
        document_root=settings.MEDIA_ROOT,
    )
    urlpatterns += static(
        "/published/",
        document_root=settings.PUBLISHED_ROOT,
    )
