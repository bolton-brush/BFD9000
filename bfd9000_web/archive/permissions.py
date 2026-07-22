"""Endpoint Permission"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast, override

from rest_framework.permissions import SAFE_METHODS, BasePermission

if TYPE_CHECKING:
    from BFD9000.conf import AuthUser
    from django.contrib.auth.models import AnonymousUser
    from django.db.models import Model
    from rest_framework.request import Request
    from rest_framework.views import APIView


class CuratorOrSuperuserEditPermission(BasePermission):
    """Require model add/change perms for writes and auth for reads."""

    @override
    def has_permission(self, request: Request, view: APIView) -> bool:
        """Checks if a user has permission to access a view

        Args:
            request: The request to check
            view: The view to check against

        Returns:
            True if authenticated

        """
        user = cast("AuthUser | AnonymousUser | None", request.user)
        if not user or not user.is_authenticated:
            return False
        if user.is_superuser or request.method in SAFE_METHODS:
            return True
        if request.method == "DELETE":
            return False

        qs = getattr(view, "queryset", None)
        if qs is None and hasattr(view, "get_queryset"):
            try:
                gqs = getattr(view, "get_queryset", None)
                if callable(gqs):
                    qs = gqs()
            except Exception:
                qs = None
        model: type[Model] | None = getattr(qs, "model", None)
        if model is None:
            return False

        app_label = model._meta.app_label
        model_name = model._meta.model_name
        if model_name is None:
            return False
        return (
            user.has_perm(f"{app_label}.add_{model_name}")
            if request.method == "POST"
            else user.has_perm(f"{app_label}.change_{model_name}")
            if request.method in {"PUT", "PATCH"}
            else False
        )


class RecordPermission(BasePermission):
    """Allow authenticated users to read/create/update records."""

    @override
    def has_permission(self, request: Request, view: APIView) -> bool:
        user = cast("AuthUser | AnonymousUser | None", request.user)
        if not user or not user.is_authenticated:
            return False
        if request.method == "DELETE":
            return bool(user.is_superuser)
        return True
