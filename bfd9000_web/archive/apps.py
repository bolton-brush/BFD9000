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

    # @override
    # def ready(self) -> None:
    #     """Initialize the archive app and start background tasks."""
    #     # Guard against running twice in development (autoreloader issue)
    #     if "runserver" in sys.argv:
    #         if self._is_main_process():
    #             self._start_background_task()
    #     # are we in production (gunicorn)?
    #     elif Path(sys.argv[0]).name == "gunicorn":
    #         self._start_background_task()
    #     else:
    #         logger.info("Background tasks not started: not main thread")

    # @staticmethod
    # def _is_main_process() -> bool:
    #     """Check if this is the main process (development only).

    #     Returns:
    #         If this is the main process in development

    #     """
    #     return os.environ.get("RUN_MAIN") == "true"

    # @staticmethod
    # def _start_background_task() -> None:
    #     """Start the background media upload thread."""
    #     thread = threading.Thread(target=media_upload_worker, daemon=True)
    #     thread.start()
