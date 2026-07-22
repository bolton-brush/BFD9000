"""UI permission tests for subject and encounter create buttons."""
# ruff: noqa: S106

from __future__ import annotations

from BFD9000.conf import AuthUser
from django.contrib.auth.models import Permission
from django.test import override_settings
from django.urls import reverse

from .base import CleanupTestCase


@override_settings(
    STORAGES={
        "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
        "staticfiles": {
            "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
        },
    }
)
class PermissionUiTests(CleanupTestCase):
    """Verify template button visibility follows Django permissions."""

    def test_regular_user_does_not_see_create_buttons(self) -> None:
        """Ensures regular users are not able to create new subjects/encounters"""
        user = AuthUser.objects.create_user(username="regular", password="testpassword")
        self.client.force_login(user)

        subjects_response = self.client.get(reverse("archive:subjects"))
        encounters_response = self.client.get(reverse("archive:encounters"))

        self.assertEqual(subjects_response.status_code, 200)
        self.assertEqual(encounters_response.status_code, 200)
        self.assertNotContains(subjects_response, "New Subject")
        self.assertNotContains(encounters_response, "New Encounter")

    def test_curator_like_user_sees_create_buttons(self) -> None:
        """Ensures curators are not able to create new subjects/encounters"""
        user = AuthUser.objects.create_user(username="curator", password="testpassword")
        add_subject = Permission.objects.get(codename="add_subject")
        add_encounter = Permission.objects.get(codename="add_encounter")
        user.user_permissions.add(add_subject, add_encounter)  # pyright: ignore[reportUnknownMemberType]

        self.client.force_login(user)

        subjects_response = self.client.get(reverse("archive:subjects"))
        encounters_response = self.client.get(reverse("archive:encounters"))

        self.assertEqual(subjects_response.status_code, 200)
        self.assertEqual(encounters_response.status_code, 200)
        self.assertContains(subjects_response, "New Subject")
        self.assertContains(encounters_response, "New Encounter")
