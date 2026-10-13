from django.apps import AppConfig


class CandidatesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.candidates"

    def ready(self):
        # Registra los signals al arrancar la app
        from . import signals  # noqa: F401
