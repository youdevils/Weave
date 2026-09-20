from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    # path("", include(("website.urls", "website"), namespace="website")),
    path("model/", include(("model.urls", "model"), namespace="model")),
    path("model/", include(("publication.urls", "publication"), namespace="publication")),
    path("viewer/", include(("viewer.urls", "viewer"), namespace="viewer")),
    path("", include(("workspace.urls", "workspace"), namespace="workspace")),
    # path("api/", include(("api.urls", "api"), namespace="api")),
]


# Serve media files during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
