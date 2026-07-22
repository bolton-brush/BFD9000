"""Tests for project auth endpoints."""
# pyright: reportUnknownMemberType=false, reportAttributeAccessIssue=false
# ruff: noqa: S106

from __future__ import annotations

from BFD9000.conf import AuthUser
from django.test import TestCase
from django.urls import reverse


class AuthViewTests(TestCase):
    """Validate login/logout view behavior."""

    def test_logout_get_redirects_without_error(self) -> None:
        """Test logging out redirects without erroring"""
        user = AuthUser.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.client.force_login(user)

        response = self.client.get(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_logout_post_logs_user_out(self) -> None:
        """Test logging out redirects without erroring"""
        user = AuthUser.objects.create_user(
            username="testuser", password="testpassword"
        )
        self.client.force_login(user)

        response = self.client.post(reverse("logout"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("login"))
        self.assertNotIn("_auth_user_id", self.client.session)
