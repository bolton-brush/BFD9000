"""Django app configuration for the archive app."""

from typing import final

from django.apps import AppConfig


@final
class ArchiveConfig(AppConfig):
    """Configure default settings for the archive app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "archive"
