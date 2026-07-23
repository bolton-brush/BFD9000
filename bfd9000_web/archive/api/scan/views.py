"""Proxy views to securely forward image classification requests

from Django to the private internal FastAPI classifier backend using the
auto-generated bfd9020_ai_api_client SDK.
"""

from __future__ import annotations

import logging
from functools import wraps
from io import BytesIO
from typing import IO, TYPE_CHECKING, Any, BinaryIO, Protocol, cast, override

from BFD9000.conf import settings as conf
from bfd9020_ai_api_client import AuthenticatedClient, Client
from bfd9020_ai_api_client.api.default import (
    classify_frontal_fliprot_frontal_fliprot_post as frontal,
)
from bfd9020_ai_api_client.api.default import (
    classify_lateral_fliprot_lateral_fliprot_post as lateral,
)
from bfd9020_ai_api_client.api.default import (
    classify_xray_xray_class_post as xray,
)
from bfd9020_ai_api_client.api.default import (
    get_xray_info_xray_info_post as xray_info,
)
from bfd9020_ai_api_client.models.body_classify_frontal_fliprot_frontal_fliprot_post import (  # noqa: E501
    BodyClassifyFrontalFliprotFrontalFliprotPost as FrontalBody,
)
from bfd9020_ai_api_client.models.body_classify_lateral_fliprot_lateral_fliprot_post import (  # noqa: E501
    BodyClassifyLateralFliprotLateralFliprotPost as LateralBody,
)
from bfd9020_ai_api_client.models.body_classify_xray_xray_class_post import (
    BodyClassifyXrayXrayClassPost as XrayBody,
)
from bfd9020_ai_api_client.models.body_get_xray_info_xray_info_post import (
    BodyGetXrayInfoXrayInfoPost as XrayInfoBody,
)
from bfd9020_ai_api_client.models.http_validation_error import HTTPValidationError
from bfd9020_ai_api_client.types import File, Response
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.decorators.http import require_POST
from httpx import Timeout
from rest_framework.status import HTTP_200_OK
from result.result import as_result

if TYPE_CHECKING:
    from collections.abc import Callable

logger = logging.getLogger(__name__)


class ReturnProtocol(Protocol):
    """Protocol for the return type of our generated client"""

    def to_dict(self) -> dict[str, Any]:  # pyright: ignore[reportExplicitAny]
        """Protocol to serialize the return type"""
        ...


class EndpointModule[Body, Return: ReturnProtocol](Protocol):
    """Protocol matching the interface exported by each generated SDK endpoint module"""

    def sync_detailed(
        self,
        *,
        client: AuthenticatedClient | Client,
        body: Body,
    ) -> Response[Return | HTTPValidationError]:
        """Synchronous fetch from openapi-generated client"""
        ...


class StreamWrapper(BinaryIO):
    """Bridges UploadedFile to BinaryIO with zero data copy."""

    def __init__(self, uploaded_file: IO[bytes]) -> None:
        """Create a BinaryIO compatible object from Django"""
        self._stream: IO[bytes] = uploaded_file

    def __getattr__(self, name: str) -> Any:  # pyright: ignore[reportExplicitAny, reportAny]  # noqa: ANN401
        """Pass down any original methods to the stream

        Args:
            name: The attribute to find

        Returns:
            From the nested stream

        """
        # Dynamically passes read, seek, tell, close, __exit__, etc. down to the stream
        return getattr(self._stream, name)  # pyright: ignore[reportAny]

    @override
    def __enter__(self) -> BinaryIO:
        return self


def _get_api_client() -> Client:
    """Instantiate and configure the auto-generated client.

    Returns:
        The client used for connecting to the 9010 service

    """
    return Client(
        base_url=conf.BFD9020_BASE_URL,
        verify_ssl=False,
        timeout=Timeout(30.0),
        # headers={"X-Internal-Secret": getattr(settings, "CLASSIFIER_API_KEY", "")},
    )


def require_image(view_func: Callable[..., Any]) -> Callable[..., Any]:  # pyright: ignore[reportExplicitAny]
    """Decorator that validates request.FILES['image']

    Args:
        view_func: The function to wrap

    Returns:
        A wrapped function that consumes the image

    """

    @wraps(view_func)
    def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:  # pyright: ignore[reportExplicitAny, reportAny]  # noqa: ANN401

        uploaded_file = request.FILES.get("image")

        if not uploaded_file or uploaded_file.file is None:  # pyright: ignore[reportUnknownMemberType]
            return JsonResponse(
                {
                    "error": "Missing image file in request. "
                    + "Expected field name 'image'."
                },
                status=400,
            )

        file_bytes: bytes = uploaded_file.read()  # pyright: ignore[reportAny]

        file = File(
            payload=BytesIO(file_bytes),
            file_name=uploaded_file.name,
            mime_type=uploaded_file.content_type or "application/octet-stream",
        )

        # Pass the extracted SDK File object directly to the view
        return view_func(request, file, *args, **kwargs)  # pyright: ignore[reportAny]

    return wrapper


def _handle_client_call[Body, Return: ReturnProtocol](
    body: Body,
    api_func: EndpointModule[Body, Return],
    api_name: str = "",
) -> HttpResponse:
    """Helper to validate uploaded image and execute a generated client endpoint

    Args:
        body: The body to send to the proxied endpoint
        api_func: Imported OpenAPI endpoint module (e.g. `xray_info`)
        api_name: The name of the API to use in logging

    Returns:
        HttpResponse: Formatted JSON response or error details.

    """
    client = _get_api_client()

    response = as_result(Exception)(api_func.sync_detailed)(
        client=client,
        body=body,
    )

    if response.is_err():
        err = response.unwrap_err()
        logger.error(
            "Failed to reach classification API for: [%s]",
            api_name,
        )
        logger.exception("Full traceback for classifier API error:", exc_info=err)
        return JsonResponse(
            {
                "error": "Classification backend returned an error",
                "details": f"{err}",
            },
            status=500,
        )

    response = response.unwrap()
    parsed = response.parsed

    if (
        response.status_code != HTTP_200_OK
        or parsed is None
        or isinstance(parsed, HTTPValidationError)
    ):
        logger.error(
            "Classifier API error [%s]: Status %s",
            api_name,
            response.status_code,
        )
        return JsonResponse(
            {
                "error": "Classification backend returned an error",
                "details": str(response.content, encoding="utf-8", errors="ignore"),
            },
            status=response.status_code or 500,
        )

    parsed = cast("Return", parsed)
    return JsonResponse(parsed.to_dict(), status=200)


@login_required
@require_POST
@require_image
def classify_xray_proxy(_: HttpRequest, image: File) -> HttpResponse:
    """Proxy for POST /xray-class using generated SDK.

    Args:
        image: The image to process from the client

    Returns:
        The classification of the image or error

    """
    return _handle_client_call(XrayBody(image=image), xray, "xray")


@login_required
@require_POST
@require_image
def classify_lateral_fliprot_proxy(_: HttpRequest, image: File) -> HttpResponse:
    """Proxy for POST /lateral-fliprot using generated SDK.

    Args:
        image: The image to process from the client

    Returns:
        The classification of the image or error

    """
    return _handle_client_call(LateralBody(image=image), lateral, "xray")


@login_required
@require_POST
@require_image
def classify_frontal_fliprot_proxy(_: HttpRequest, image: File) -> HttpResponse:
    """Proxy for POST /frontal-fliprot using generated SDK.

    Args:
        image: The image to process from the client

    Returns:
        The classification of the image or error

    """
    return _handle_client_call(FrontalBody(image=image), frontal, "xray")


@login_required
@require_POST
@require_image
def get_xray_info_proxy(_: HttpRequest, image: File) -> HttpResponse:
    """Proxy for POST /xray-info using generated SDK.

    Args:
        image: The image to process from the client

    Returns:
        The classification of the image or error

    """
    return _handle_client_call(XrayInfoBody(image=image), xray_info, "xray")
