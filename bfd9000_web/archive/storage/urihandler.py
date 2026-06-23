"""URI handler backend for resolving URIs"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar, override
from urllib.parse import urlparse

from archive.storage.storage import FileTimeInfo, StorageBackend
from result.result import as_result

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

logger = logging.getLogger(__name__)


P = Path
# H represents the common HandleType (e.g., int or a tuple)
H = TypeVar("H")


@dataclass
class _SessionEntry[H]:
    backend: str
    handle: H


class URIStorageBackend[H](StorageBackend[str, int]):
    """A Router-Facade Storage Backend that unifies multiple backends via URIs.

    PathType: `str` (e.g., 'local://relative/path' or 'box://some/remote/path')
    HandleType: `int` (Issues handles that are internally mapped to their backend)
    """

    def __init__(self, routes: Mapping[str, StorageBackend[P, H]]) -> None:
        """Instantiates the URI routing layer

        Args:
            routes: A mapping table of string schemes to storage backend instances.
                    ex: {"local": LocalStorageBackend(), "box": BoxStorageBackend()}

        """
        self._routes: Mapping[str, StorageBackend[P, H]] = routes
        self._session_registry: dict[int, _SessionEntry[H]] = {}
        self._session_counter: int = 0

    def _split_uri(self, uri_string: str) -> tuple[str, StorageBackend[P, H], Path]:
        """Parses an incoming URI into its matching backend and Path.

        Returns:
            A tuple of the backend string and object and the resolved path

        Raises:
            ValueError: If the string formatting is corrupted or missing a scheme.
            KeyError: If no backend instance is linked to the requested scheme.

        """
        parsed = urlparse(uri_string)

        if not parsed.scheme:
            raise ValueError(
                f"Invalid URI composition: '{
                    uri_string
                }'. Path must specify a valid scheme (e.g., 'local://...')."
            )

        if parsed.scheme not in self._routes:
            raise KeyError(
                f"No storage backend engine registered to handle the '{
                    parsed.scheme
                }' scheme matrix."
            )

        # Reconstruct the path relative to that backend's target system root
        # Combining host/netloc and path strips out structural padding safely
        combined_path_str = (parsed.netloc + parsed.path).lstrip("/")
        return parsed.scheme, self._routes[parsed.scheme], Path(combined_path_str)

    @staticmethod
    def _make_uri(bstr: str, path: Path) -> str:
        """Create a URI given bstr and path

        Args:
            bstr: The backend string identifier
            path: The path

        Returns:
            A URI string

        """
        return f"{bstr}://{path.as_posix()}"

    @override
    def exists(self, path: str) -> bool:
        _, backend, sub_path = self._split_uri(path)
        return backend.exists(sub_path)

    @override
    def _raw_open(self, path: str) -> int:
        """Parses the path URI, maps it to the target backend, and opens a session

        Args:
            path: The path to resolve

        Returns:
            A handle mapped to that backend

        """
        bstr, backend, sub_path = self._split_uri(path)
        self._session_counter += 1
        self._session_registry[self._session_counter] = _SessionEntry[H](
            backend=bstr, handle=backend._raw_open(sub_path)
        )
        return self._session_counter

    @override
    def _raw_close(self, handle: int) -> bool:
        """Closes the session on the respective backend

        Args:
            handle: The handle to close

        Returns:
            True if closed successfully

        """
        session = self._session_registry[handle]
        return self._routes[session.backend]._raw_close(session.handle)

    @override
    def delete(self, path: str) -> bool:
        _, backend, sub_path = self._split_uri(path)
        return backend.delete(sub_path)

    @override
    def list(self, path: str) -> tuple[Sequence[str], Sequence[str]]:
        bstr, backend, sub_path = self._split_uri(path)

        inner_results = backend.list(sub_path)

        # Turn sub-paths back into uniform 'scheme://' strings
        return (
            [self._make_uri(bstr, p) for p in inner_results[0]],
            [self._make_uri(bstr, p) for p in inner_results[1]],
        )

    @override
    def mkdir(self, path: str, parents_ok: bool = True, exists_ok: bool = True) -> None:
        _, backend, sub_path = self._split_uri(path)
        backend.mkdir(sub_path, parents_ok=parents_ok, exists_ok=exists_ok)

    @override
    def rmdir(self, path: str) -> bool:
        _, backend, sub_path = self._split_uri(path)
        return backend.rmdir(sub_path)

    @override
    def _raw_read_stream(self, handle: int) -> Iterator[bytes]:
        session = self._session_registry[handle]
        yield from self._routes[session.backend]._raw_read_stream(session.handle)

    @override
    def _raw_write_stream(
        self,
        handle: int,
        stream: Iterator[bytes],
        size: int,
        allow_override: bool,
    ) -> None:
        session = self._session_registry[handle]
        self._routes[session.backend]._raw_write_stream(
            session.handle, stream, size, allow_override
        )

    @override
    def get_times(self, path: str) -> FileTimeInfo:
        _, backend, sub_path = self._split_uri(path)
        return backend.get_times(sub_path)

    @override
    def size(self, path: str) -> int:
        _, backend, sub_path = self._split_uri(path)
        return backend.size(sub_path)

    @override
    def health(self) -> None:
        """The fallback group is healthy if at all sub-backends are alive

        Raises:
            RuntimeError: If any backends failed

        """
        thrown_errors = [
            f"Backend {b.__class__.__name__} ({bstr}://) is not healthy, with error {
                res
            }"
            for bstr, b in self._routes.items()
            if (res := as_result(Exception)(b.health)().err())
        ]
        if thrown_errors:
            raise RuntimeError("\n".join(thrown_errors))
