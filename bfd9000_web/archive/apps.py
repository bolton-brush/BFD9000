"""Django app configuration for the archive app."""

from __future__ import annotations

import logging
from typing import final

from django.apps import AppConfig

# from .media_upload import media_upload_worker

logger = logging.getLogger(__name__)


@final
class ArchiveConfig(AppConfig):
    """Configure default settings for the archive app."""

    default_auto_field = "django.db.models.BigAutoField"
    name = "archive"
