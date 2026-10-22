# -*- mode: python -*-
"""System checks for the registry's settings"""

from django.conf import settings
from django.core.checks import Error, register


@register()
def removed_settings(app_configs, **kwargs):
    """Settings that API 2.0 no longer supports"""
    if hasattr(settings, "NBANK_METADATA_ALIASES"):
        return [
            Error(
                "NBANK_METADATA_ALIASES is no longer supported: the registry doesn't "
                "accept core fields (experimenter, animal) or other names for them in "
                "metadata.",
                hint="Remove the setting. Normalize existing metadata with "
                "django-neurobank 0.12 or 0.13 before upgrading.",
                id="nbank_registry.E001",
            )
        ]
    return []
