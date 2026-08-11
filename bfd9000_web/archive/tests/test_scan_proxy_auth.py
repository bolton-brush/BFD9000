"""Authentication tests for the BFD9020 scan proxy routes."""
# pyright: reportUninitializedInstanceVariable=false
# ruff: noqa: S106

from __future__ import annotations

from typing import TYPE_CHECKING, override
from unittest.mock import patch

from BFD9000.conf import AuthUser
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import JsonResponse
from django.test import TestCase
from django.urls import reverse

PROXY_HANDLER = "archive.api.scan.views._handle_client_call"

PROXY_URL_NAMES: tuple[str, ...] = (
    "archive:api:scan:classify_xray",
    "archive:api:scan:classify_lateral_fliprot",
    "archive:api:scan:classify_frontal_fliprot",
    "archive:api:scan:get_xray_info",
)


def _image_upload() -> SimpleUploadedFile:
    """Build a minimal in-memory image for the 'image' form field.

    Returns:
        A fake image upload sufficient to satisfy the require_image decorator.

    """
    return SimpleUploadedFile("scan.png", b"fake-png-bytes", content_type="image/png")


class ScanProxyAuthTests(TestCase):
    """Verify the 9020 proxy routes enforce login before proxying.

    Serialization and backend behavior are covered upstream by the 9020
    test suite; here we only assert that anonymous users are redirected
    before the request can reach the internal classifier backend, and that
    authenticated users pass the login check.
    """

    if TYPE_CHECKING:
        user: AuthUser

    @override
    def setUp(self) -> None:
        self.user = AuthUser.objects.create_user(
            username="proxyuser", password="testpassword"
        )

    def test_anonymous_post_redirects_to_login_without_reaching_backend(self) -> None:
        """Anonymous POSTs redirect to login and never call the backend."""
        with patch(PROXY_HANDLER) as mock_handler:
            for url_name in PROXY_URL_NAMES:
                with self.subTest(url_name=url_name):
                    response = self.client.post(
                        reverse(url_name), {"image": _image_upload()}
                    )
                    self.assertRedirects(
                        response,
                        f"{reverse('login')}?next={reverse(url_name)}",
                        fetch_redirect_response=False,
                    )
            mock_handler.assert_not_called()

    def test_authenticated_post_passes_login_check(self) -> None:
        """Authenticated POSTs pass login_required and invoke the proxy handler."""
        self.client.force_login(self.user)
        for url_name in PROXY_URL_NAMES:
            with (
                self.subTest(url_name=url_name),
                patch(
                    PROXY_HANDLER, return_value=JsonResponse({"ok": True})
                ) as mock_handler,
            ):
                response = self.client.post(
                    reverse(url_name), {"image": _image_upload()}
                )
                self.assertEqual(response.status_code, 200)
                mock_handler.assert_called_once()

    def test_non_post_methods_are_rejected(self) -> None:
        """Authenticated non-POST requests are rejected with 405.

        Anonymous non-POST requests redirect to login before the method
        check runs, so the client must be authenticated to exercise
        require_POST.
        """
        self.client.force_login(self.user)
        with patch(PROXY_HANDLER) as mock_handler:
            for url_name in PROXY_URL_NAMES:
                for method in ("GET", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"):
                    with self.subTest(url_name=url_name, method=method):
                        response = self.client.generic(method, reverse(url_name))
                        self.assertEqual(response.status_code, 405)
                        self.assertEqual(response["Allow"], "POST")
            mock_handler.assert_not_called()

    def test_post_without_image_returns_400(self) -> None:
        """Authenticated POSTs missing the 'image' file are rejected with 400."""
        self.client.force_login(self.user)
        with patch(PROXY_HANDLER) as mock_handler:
            for url_name in PROXY_URL_NAMES:
                with self.subTest(url_name=url_name):
                    response = self.client.post(reverse(url_name))
                    self.assertEqual(response.status_code, 400)
                    self.assertIn("image", response.json()["error"])
            mock_handler.assert_not_called()
