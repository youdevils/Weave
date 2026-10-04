from django.urls import path

from assisted import views

app_name = "assisted"

urlpatterns = [
    path("<uuid:model_id>/assisted-work/", views.landing, name="landing"),
    path("<uuid:model_id>/assisted-work/reconcile/", views.reconcile_entry, name="reconcile"),
    path("<uuid:model_id>/assisted-work/change/", views.change_entry, name="change"),
    path("<uuid:model_id>/assisted-work/assess/", views.assess_entry, name="assess"),
    path("<uuid:model_id>/assisted-work/<uuid:task_id>/", views.task_detail, name="task_detail"),
]
