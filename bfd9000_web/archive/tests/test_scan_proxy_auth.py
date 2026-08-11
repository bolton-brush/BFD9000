"""Authentication and error-contract tests for the BFD9020 scan proxy routes."""
# pyright: reportUninitializedInstanceVariable=false
# ruff: noqa: S106

from __future__ import annotations

from typing import TYPE_CHECKING, Any, override
from unittest.mock import patch

from BFD9000.conf import AuthUser
from BFD9000.settings import MAX_9020_SIZE
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from rest_framework.response import Response
from rest_framework.test import APITestCase

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


class ScanProxyAuthTests(APITestCase):
    """Verify the 9020 proxy routes enforce auth and the API error contract.

    Serialization and backend behavior are covered upstream by the 9020
    test suite; here we assert that anonymous users are rejected before the
    request can reach the internal classifier backend, that authenticated
    users pass the permission check, and that errors follow the shared
    {"error": {"code", "message", "details"}} contract.
    """

    if TYPE_CHECKING:
        user: AuthUser

    @override
    def setUp(self) -> None:
        self.user = AuthUser.objects.create_user(
            username="proxyuser", password="testpassword"
        )

    def _assert_error_contract(
        self, response: Response, status_code: int, code: str
    ) -> dict[str, Any]:
        """Assert the response matches the nested API error contract.

        Args:
            response: The response to check
            status_code: The expected HTTP status code
            code: The expected machine-readable error code

        Returns:
            The parsed "error" object for further assertions.

        """
        self.assertEqual(response.status_code, status_code)
        body: dict[str, Any] = response.data  # pyright: ignore[reportAny]
        self.assertEqual(set(body.keys()), {"error"})
        error: dict[str, Any] = body["error"]
        self.assertEqual(set(error.keys()), {"code", "message", "details"})
        self.assertEqual(error["code"], code)
        return error

    def test_anonymous_post_rejected_without_reaching_backend(self) -> None:
        """Anonymous POSTs are rejected with 403 and never call the backend."""
        with patch(PROXY_HANDLER) as mock_handler:
            for url_name in PROXY_URL_NAMES:
                with self.subTest(url_name=url_name):
                    response = self.client.post(
                        reverse(url_name), {"image": _image_upload()}
                    )
                    self._assert_error_contract(response, 403, "PERMISSION_DENIED")
            mock_handler.assert_not_called()

    def test_authenticated_post_passes_permission_check(self) -> None:
        """Authenticated POSTs pass IsAuthenticated and invoke the proxy handler."""
        self.client.force_authenticate(user=self.user)
        for url_name in PROXY_URL_NAMES:
            with (
                self.subTest(url_name=url_name),
                patch(
                    PROXY_HANDLER, return_value=Response({"ok": True})
                ) as mock_handler,
            ):
                response = self.client.post(
                    reverse(url_name), {"image": _image_upload()}
                )
                self.assertEqual(response.status_code, 200)
                mock_handler.assert_called_once()

    def test_non_post_methods_are_rejected(self) -> None:
        """Authenticated non-POST requests are rejected with 405.

        Anonymous non-POST requests are rejected with 403 before the method
        check runs, so the client must be authenticated to exercise the
        method restriction. OPTIONS is the one exception: DRF always enables
        it for metadata introspection, so it returns 200 rather than 405.
        """
        self.client.force_authenticate(user=self.user)
        with patch(PROXY_HANDLER) as mock_handler:
            for url_name in PROXY_URL_NAMES:
                for method in ("GET", "PUT", "PATCH", "DELETE", "HEAD"):
                    with self.subTest(url_name=url_name, method=method):
                        response = self.client.generic(method, reverse(url_name))
                        if method == "HEAD":
                            # Error responses to HEAD carry no body to parse.
                            self.assertEqual(response.status_code, 405)
                        else:
                            self._assert_error_contract(response, 405, "API_ERROR")
            mock_handler.assert_not_called()

    def test_options_returns_drf_metadata(self) -> None:
        """DRF always allows OPTIONS for metadata, even on POST-only views."""
        self.client.force_authenticate(user=self.user)
        for url_name in PROXY_URL_NAMES:
            with self.subTest(url_name=url_name):
                response = self.client.options(reverse(url_name))
                self.assertEqual(response.status_code, 200)
                # DRF builds Allow from a set, so compare order-insensitively.
                self.assertEqual(
                    {m.strip() for m in response["Allow"].split(",")},
                    {"POST", "OPTIONS"},
                )

    def test_post_without_image_returns_400(self) -> None:
        """Authenticated POSTs missing the 'image' file are rejected with 400."""
        self.client.force_authenticate(user=self.user)
        with patch(PROXY_HANDLER) as mock_handler:
            for url_name in PROXY_URL_NAMES:
                with self.subTest(url_name=url_name):
                    response = self.client.post(reverse(url_name))
                    error = self._assert_error_contract(
                        response, 400, "VALIDATION_ERROR"
                    )
                    self.assertIn("image", error["message"])
            mock_handler.assert_not_called()

    def test_post_with_oversized_image_returns_400(self) -> None:
        """POSTs with an image over MAX_9020_SIZE (50MB) are rejected with 400."""
        # Pin the configured limit so the requirement is verified, not assumed.
        self.assertEqual(MAX_9020_SIZE, 50 * 1024 * 1024)
        self.client.force_authenticate(user=self.user)
        oversized = SimpleUploadedFile(
            "scan.png", b"\0" * (MAX_9020_SIZE + 1), content_type="image/png"
        )
        # The size check lives in the shared require_image decorator, so one
        # representative route is enough to verify the real limit end-to-end.
        with patch(PROXY_HANDLER) as mock_handler:
            response = self.client.post(
                reverse("archive:api:scan:classify_xray"), {"image": oversized}
            )
            error = self._assert_error_contract(response, 400, "VALIDATION_ERROR")
            self.assertIn("size limit", error["message"])
            mock_handler.assert_not_called()

    def test_post_at_size_limit_boundary(self) -> None:
        """Images exactly at the size limit pass; one byte over is rejected."""
        self.client.force_authenticate(user=self.user)
        for url_name in PROXY_URL_NAMES:
            with (
                self.subTest(url_name=url_name),
                # Shrink the limit so the boundary can be tested with tiny uploads.
                patch("archive.api.scan.views.MAX_9020_SIZE", 10),
                patch(
                    PROXY_HANDLER, return_value=Response({"ok": True})
                ) as mock_handler,
            ):
                over = SimpleUploadedFile(
                    "scan.png", b"\0" * 11, content_type="image/png"
                )
                response = self.client.post(reverse(url_name), {"image": over})
                self._assert_error_contract(response, 400, "VALIDATION_ERROR")
                mock_handler.assert_not_called()

                at_limit = SimpleUploadedFile(
                    "scan.png", b"\0" * 10, content_type="image/png"
                )
                response = self.client.post(reverse(url_name), {"image": at_limit})
                self.assertEqual(response.status_code, 200)
                mock_handler.assert_called_once()
