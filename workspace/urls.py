from django.urls import path
from .views import views

app_name = "workspace"

urlpatterns = [
    path("", views.index, name="index"),
]
