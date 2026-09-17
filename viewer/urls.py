from django.urls import path

from viewer import views

app_name = "viewer"

urlpatterns = [
    path("", views.harness, name="harness"),
]
