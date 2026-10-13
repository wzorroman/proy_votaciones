from django.apps import AppConfig


class VotersConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.voters"

    def ready(self):
        from . import signals  # noqa: F401
