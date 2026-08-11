"""Proxy views to securely forward image classification requests

from Django to the private internal FastAPI classifier backend using the
auto-generated bfd9020_ai_api_client SDK.

These are DRF views so that authentication, multipart parsing, and error
responses follow the same API stack as the rest of the /api/ namespace:
anonymous requests get a 403 JSON error (not an HTML login redirect), and
all errors use the shared {"error": {"code", "message", "details"}} contract.
"""

from __future__ import annotations

import logging
from functools import wraps
from io import BytesIO
from typing import TYPE_CHECKING, Any, Protocol

from BFD9000.conf import settings as conf
from BFD9000.settings import MAX_9020_SIZE
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
from bfd9020_ai_api_client.types import File
from bfd9020_ai_api_client.types import Response as SdkResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import (
    extend_schema,  # pyright: ignore[reportUnknownVariableType]
)
from httpx import Timeout
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import ParseError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.status import HTTP_200_OK, HTTP_502_BAD_GATEWAY
from result.result import as_result

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.core.files.uploadedfile import UploadedFile
    from rest_framework.request import Request

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
    ) -> SdkResponse[Return | HTTPValidationError]:
        """Synchronous fetch from openapi-generated client"""
        ...


_PROXY_REQUEST_SCHEMA: dict[str, Any] = {  # pyright: ignore[reportExplicitAny]
    "multipart/form-data": {
        "type": "object",
        "properties": {"image": {"type": "string", "format": "binary"}},
        "required": ["image"],
    }
}


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


def require_image(
    view_func: Callable[..., Response],
) -> Callable[..., Response]:
    """Decorator that validates request.FILES['image']

    Args:
        view_func: The function to wrap

    Returns:
        A wrapped function that consumes the image

    """

    @wraps(view_func)
    def wrapper(request: Request, *args: Any, **kwargs: Any) -> Response:  # pyright: ignore[reportExplicitAny, reportAny]  # noqa: ANN401
        uploaded_file: UploadedFile | None = request.FILES.get("image")  # pyright: ignore[reportAny]

        if not uploaded_file or uploaded_file.file is None:  # pyright: ignore[reportUnknownMemberType]
            raise ParseError(
                "Missing image file in request. Expected field name 'image'."
            )

        if (uploaded_file.size or 0) > MAX_9020_SIZE:
            raise ParseError(
                "File exceeds size limit (50MB). Expected field name 'image'."
            )

        file_bytes: bytes = uploaded_file.read()  # pyright: ignore[reportAny]

        file = File(
            payload=BytesIO(file_bytes),
            file_name=uploaded_file.name,
            mime_type=uploaded_file.content_type or "application/octet-stream",
        )

        # Pass the extracted SDK File object directly to the view
        return view_func(request, file, *args, **kwargs)

    return wrapper


def _error_response(code: str, message: str, details: object, status: int) -> Response:
    """Build an error response matching the shared API error contract.

    Args:
        code: Machine-readable error code
        message: Human-readable error message
        details: Optional structured details about the error
        status: HTTP status code for the response

    Returns:
        DRF Response with the nested {"error": {"code", "message", "details"}} body

    """
    return Response(
        {"error": {"code": code, "message": message, "details": details}},
        status=status,
    )


def _handle_client_call[Body, Return: ReturnProtocol](
    body: Body,
    api_func: EndpointModule[Body, Return],
    api_name: str = "",
) -> Response:
    """Helper to validate uploaded image and execute a generated client endpoint

    All backend failures are normalized to 502 Bad Gateway with the shared
    nested error contract so clients only deal with this API's own status
    codes; the upstream status is preserved in the error details.

    Args:
        body: The body to send to the proxied endpoint
        api_func: Imported OpenAPI endpoint module (e.g. `xray_info`)
        api_name: The name of the API to use in logging

    Returns:
        Response: Formatted JSON response or error details.

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
        return _error_response(
            "UPSTREAM_UNAVAILABLE",
            "Classification backend could not be reached",
            f"{err}",
            HTTP_502_BAD_GATEWAY,
        )

    response_ok = response.unwrap()
    parsed = response_ok.parsed

    if (
        response_ok.status_code != HTTP_200_OK
        or parsed is None
        or isinstance(parsed, HTTPValidationError)
    ):
        logger.error(
            "Classifier API error [%s]: Status %s",
            api_name,
            response_ok.status_code,
        )
        return _error_response(
            "UPSTREAM_ERROR",
            "Classification backend returned an error",
            {
                "upstream_status": response_ok.status_code,
                "body": str(response_ok.content, encoding="utf-8", errors="ignore"),
            },
            HTTP_502_BAD_GATEWAY,
        )

    return Response(parsed.to_dict(), status=HTTP_200_OK)


@extend_schema(request=_PROXY_REQUEST_SCHEMA, responses={200: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@require_image
def classify_xray_proxy(_: Request, image: File) -> Response:
    """Proxy for POST /xray-class using generated SDK.

    Args:
        image: The image to process from the client

    Returns:
        The classification of the image or error

    """
    return _handle_client_call(XrayBody(image=image), xray, "xray")


@extend_schema(request=_PROXY_REQUEST_SCHEMA, responses={200: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@require_image
def classify_lateral_fliprot_proxy(_: Request, image: File) -> Response:
    """Proxy for POST /lateral-fliprot using generated SDK.

    Args:
        image: The image to process from the client

    Returns:
        The classification of the image or error

    """
    return _handle_client_call(LateralBody(image=image), lateral, "xray")


@extend_schema(request=_PROXY_REQUEST_SCHEMA, responses={200: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@require_image
def classify_frontal_fliprot_proxy(_: Request, image: File) -> Response:
    """Proxy for POST /frontal-fliprot using generated SDK.

    Args:
        image: The image to process from the client

    Returns:
        The classification of the image or error

    """
    return _handle_client_call(FrontalBody(image=image), frontal, "xray")


@extend_schema(request=_PROXY_REQUEST_SCHEMA, responses={200: OpenApiTypes.OBJECT})
@api_view(["POST"])
@permission_classes([IsAuthenticated])
@require_image
def get_xray_info_proxy(_: Request, image: File) -> Response:
    """Proxy for POST /xray-info using generated SDK.

    Args:
        image: The image to process from the client

    Returns:
        The classification of the image or error

    """
    return _handle_client_call(XrayInfoBody(image=image), xray_info, "xray")
