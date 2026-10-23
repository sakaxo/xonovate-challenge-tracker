from django.apps import AppConfig


class TrackerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tracker"
    verbose_name = "Xonovate Challenge Tracker"

    def ready(self):
        from . import signals  # noqa: F401
