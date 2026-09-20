from django.urls import path

from . import views

app_name = "publication"

urlpatterns = [
    path("<uuid:model_id>/publish/", views.publish, name="publish"),
    path("<uuid:model_id>/publish/search/", views.publish_search, name="publish_search"),
    path("<uuid:model_id>/publish/preview/", views.publish_preview, name="publish_preview"),
    path("<uuid:model_id>/publish/submit/", views.publish_submit, name="publish_submit"),
    path("<uuid:model_id>/publications/", views.publication_history, name="publication_history"),
]
