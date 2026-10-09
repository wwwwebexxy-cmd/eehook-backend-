from django.apps import AppConfig


class MyappConfig(AppConfig):
    name = 'myapp'

    def ready(self):
        # Register signal receivers only after Django's app registry is ready.
        from . import signals  # noqa: F401
