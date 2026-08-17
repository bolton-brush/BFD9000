"""Settings type cast for type checkers

Will fail if using a default global setting from Django,
but offers good type support otherwise
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from django.conf import (
    settings as untyped_settings,
)
from django.contrib.auth.models import User

settings = untyped_settings
if TYPE_CHECKING:
    import BFD9000.settings as typed_settings

    class TypedUser(User):
        """Add missing attributes for type checking"""

        is_superuser: bool
        username: str

    AuthUser = TypedUser
    settings = typed_settings  # type: ignore
else:
    AuthUser = User
