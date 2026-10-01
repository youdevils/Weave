from django.apps import AppConfig


class AssistedConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "assisted"

    def ready(self):
        from assisted import signals  # noqa: F401 -- registers the two receivers
