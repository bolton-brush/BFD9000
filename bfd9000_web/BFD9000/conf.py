"""Settings type cast for type checkers

Will fail if using a default global setting from Django,
but offers good type support otherwise
"""

from typing import TYPE_CHECKING

from django.conf import (
    settings as untyped_settings,  # pyright: ignore[reportUnusedImport]
)

import BFD9000.settings as typed_settings

settings = typed_settings if TYPE_CHECKING else untyped_settings
