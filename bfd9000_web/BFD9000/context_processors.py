"""Reports app version and script location to Django"""


from rest_framework.request import Request
from typing_extensions import TypedDict

from .settings import APP_VERSION, FORCE_SCRIPT_NAME


class AppVer(TypedDict):
    """Return type for app version"""

    app_version: str


def app_version(_: Request) -> AppVer:
    """Returns the app version for a request

    Args:
        _: A generic request

    Returns:
        The app version

    """
    return {"app_version": APP_VERSION}


class ScriptName(TypedDict):
    """Return type for script name"""

    script_name: str


def script_name_prefix(_: Request) -> ScriptName:
    """Returns the script name for a request

    Args:
        _: A generic request

    Returns:
        The script name

    """
    # Always defined ('' for none, never None)
    prefix = FORCE_SCRIPT_NAME or ""
    return {"script_name": prefix}
