from django.apps import AppConfig


class NeurobankConfig(AppConfig):
    name = "nbank_registry"

    def ready(self):
        from nbank_registry import checks  # noqa: F401  (registers the checks)
