from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "RegiManager Core"

    def ready(self):
        import core.signals  # noqa: F401
        import core.agent_portal_signals  # noqa: F401
