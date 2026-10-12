from django.apps import AppConfig


class ApploginConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "appLogin"

    def ready(self):
        from appLogin import signals  # noqa: F401  (connects the login signal)
