"""Custom exception handling for the BFD9000 API.

This module defines a custom exception handler that standardizes error responses
across the API, ensuring a consistent JSON structure
for both DRF and unhandled exceptions.
"""

import logging
from typing import Any

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler

logger = logging.getLogger(__name__)


def custom_exception_handler(
    exc: Exception,
    context: dict[str, Any],  # pyright: ignore[reportExplicitAny]
) -> Response | None:
    """Custom exception handler for DRF.

    Standardizes the error response format to:
    {
        "error": {
            "code": "ERROR_CODE",
            "message": "Human readable message",
            "details": { ... }
        }
    }

    Args:
        exc: The exception raised.
        context: Dictionary containing context about the exception (view, args, etc).

    Returns:
        Response: A DRF Response object with the standardized error format.

    """
    # Call REST framework's default exception handler first,
    # to get the standard error response.
    response = exception_handler(exc, context)

    # If the exception handler returned None, it's not a DRF exception
    # (e.g. a standard Python exception like KeyError, ValueError, etc.)
    if response is None:
        # Log the exception for debugging
        logger.exception("Unhandled exception: %s", exc)

        # Return a generic error response
        return Response(
            {
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred",
                    "details": None,
                }
            },
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    # If the exception handler returned a response, add the standard error format.
    custom_data = {
        "error": {
            "code": "API_ERROR",
            "message": "An error occurred",
            "details": response.data,  # pyright: ignore[reportAny]
        }
    }

    # Try to determine a more specific error code based on status code
    if response.status_code == status.HTTP_400_BAD_REQUEST:
        custom_data["error"]["code"] = "VALIDATION_ERROR"
        custom_data["error"]["message"] = "Validation failed"
    elif response.status_code == status.HTTP_401_UNAUTHORIZED:
        custom_data["error"]["code"] = "AUTHENTICATION_REQUIRED"
        custom_data["error"]["message"] = (
            "Authentication credentials were not provided."
        )
    elif response.status_code == status.HTTP_403_FORBIDDEN:
        custom_data["error"]["code"] = "PERMISSION_DENIED"
        custom_data["error"]["message"] = (
            "You do not have permission to perform this action."
        )
    elif response.status_code == status.HTTP_404_NOT_FOUND:
        custom_data["error"]["code"] = "NOT_FOUND"
        custom_data["error"]["message"] = "Resource not found."
    elif response.status_code == status.HTTP_409_CONFLICT:
        custom_data["error"]["code"] = "CONFLICT"
        custom_data["error"]["message"] = "Resource conflict."

    # If response.data has a 'detail' key, use it as the message
    if isinstance(response.data, dict) and "detail" in response.data:  # pyright: ignore[reportAny, reportUnknownMemberType]
        custom_data["error"]["message"] = response.data["detail"]  # pyright: ignore[reportUnknownMemberType]
        # Remove detail from details to avoid redundancy if it's the only thing
        if len(response.data) == 1:  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            custom_data["error"]["details"] = None

    response.data = custom_data

    return response
