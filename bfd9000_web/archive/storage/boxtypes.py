"""Types for Authenticating Box"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, final, override

from box_sdk_gen import (
    BoxClient,
    BoxDeveloperTokenAuth,
    BoxJWTAuth,
    BoxOAuth,
    FileTokenStorage,
    JWTConfig,
    OAuthConfig,
)

if TYPE_CHECKING:
    from pathlib import Path


class BoxAuthType(ABC):
    """Any Box Auth Type that can derive a Client"""

    @abstractmethod
    def get_client(self) -> BoxClient:
        """Get a Box Client given the auth type"""


@final
class BoxAuthTypes:
    """Available Box Authentication Types"""

    @dataclass(frozen=True)
    class BoxDevToken(BoxAuthType):
        """Box Developer Token"""

        token: str

        @override
        def get_client(self) -> BoxClient:
            return BoxClient(auth=BoxDeveloperTokenAuth(token=self.token))

    @dataclass(frozen=True)
    class BoxJWT(BoxAuthType):
        """Box JWT Authentication"""

        jwt: Path

        @override
        def get_client(self) -> BoxClient:
            return BoxClient(
                auth=BoxJWTAuth(
                    config=JWTConfig.from_config_file(
                        config_file_path=str(self.jwt.absolute())
                    )
                )
            )

    # Probably doesn't work properly
    # Hasnt been tested with real Box yet
    # Most likely needs to hook into a Django Token Storage
    # If we decide to use OAuth in the future instead of JWTs
    @dataclass(frozen=True)
    class BoxOA(BoxAuthType):
        """Box OAuth Authentication"""

        id: str
        secret: str
        storage: Path

        @override
        def get_client(self) -> BoxClient:
            return BoxClient(
                auth=BoxOAuth(
                    OAuthConfig(
                        client_id=self.id,
                        client_secret=self.secret,
                        token_storage=FileTokenStorage(
                            filename=str(self.storage.absolute())
                        ),
                    )
                )
            )
