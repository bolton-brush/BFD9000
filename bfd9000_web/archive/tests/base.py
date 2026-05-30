"""Base test classes with automatic media cleanup."""
# pyright: reportUninitializedInstanceVariable=false

import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from django.test import TestCase, override_settings
from rest_framework.test import APITestCase
from typing_extensions import override

if TYPE_CHECKING:
    _MixinBase = TestCase
else:
    _MixinBase = object


class _CleanupMediaMixin(_MixinBase):
    if TYPE_CHECKING:
        _media_root: str
        _override: override_settings

    @override
    @classmethod
    def setUpClass(cls) -> None:
        """Sets up the media root and overrides necessary settings"""
        super().setUpClass()
        cls._media_root = tempfile.mkdtemp(prefix="bfd9000_test_media_")
        cls._override = override_settings(MEDIA_ROOT=cls._media_root)
        _ = cls._override.enable()  # pyright: ignore[reportAny]

    @override
    @classmethod
    def tearDownClass(cls) -> None:
        if getattr(cls, "_override", None):
            cls._override.disable()
        if getattr(cls, "_media_root", None) and Path(cls._media_root).exists():
            shutil.rmtree(cls._media_root, ignore_errors=True)
        super().tearDownClass()


class CleanupTestCase(_CleanupMediaMixin, TestCase):
    """Base TestCase with automatic media cleanup."""


class CleanupAPITestCase(_CleanupMediaMixin, APITestCase):
    """Base APITestCase with automatic media cleanup."""
