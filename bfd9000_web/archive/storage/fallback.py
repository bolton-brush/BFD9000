"""Fallback storage for stacking storage backends"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import reduce
from typing import TYPE_CHECKING, TypeVar, override

from archive.storage.storage import FileTimeInfo, StorageBackend

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

logger = logging.getLogger(__name__)


# P represents the common PathType (e.g., Path or str)
P = TypeVar("P")
# H represents the common HandleType (e.g., int or a tuple)
H = TypeVar("H")


@dataclass
class _SessionEntry[H]:
    backend: int
    handle: H


class FallbackStorageBackend[P, H](StorageBackend[P, int]):
    """A Fault-Tolerant Failover Backend.

    Accepts an ordered list of backends sharing identical path/handle footprints.
    Tries operations on them in order until one succeeds.
    """

    def __init__(self, backends: Sequence[StorageBackend[P, H]]) -> None:
        """Creates a fallback backend that attempts to use backends in the order given

        Args:
            backends: An ordered sequence of backends to try

        Raises:
            ValueError: If no backends were specified

        """
        if not backends:
            raise ValueError(
                "FallbackStorageBackend requires at least one underlying backend."
            )
        self._backends: Sequence[StorageBackend[P, H]] = backends
        self._session_registry: dict[int, _SessionEntry[H]] = {}
        self._session_counter: int = 0

    @override
    def exists(self, path: P) -> bool:
        exists = next(
            (idx for idx, backend in enumerate(self._backends) if backend.exists(path)),
            None,
        )
        return exists is not None

    @override
    def _raw_open(self, path: P) -> int:
        """Tries to open the path on each backend sequentially.

        Args:
            path: The path to resolve

        Returns:
            A handle mapped to that backend

        Raises:
            FileNotFoundError: If all backends fail to open the file

        """
        exists = next(
            (idx for idx, backend in enumerate(self._backends) if backend.exists(path)),
            None,
        )

        if exists is not None:
            inner_handle = self._backends[exists]._raw_open(path)
            self._session_counter += 1
            self._session_registry[self._session_counter] = _SessionEntry[H](
                backend=exists, handle=inner_handle
            )
            return self._session_counter

        errors: list[Exception] = []
        for index, backend in enumerate(self._backends):
            try:
                # Attempt to open on this specific tier
                inner_handle = backend._raw_open(path)

                if index > 0:
                    logger.warning(
                        f"Primary storage failed. Fell back successfully to tier {
                            index
                        } ({backend.__class__.__name__}) for path: {path}"
                    )
                self._session_counter += 1
                self._session_registry[self._session_counter] = _SessionEntry[H](
                    backend=index, handle=inner_handle
                )
                return self._session_counter

            except (FileNotFoundError, PermissionError, OSError) as exc:
                logger.debug(
                    "Tier %d (%s) missed or failed for path %s: %s",
                    index,
                    backend.__class__.__name__,
                    path,
                    exc,
                )
                errors.append(exc)
                continue

        # If we exhausted the entire chain without a success, raise a collective error
        raise FileNotFoundError(
            f"Failed to open '{path}' across all configured fallback storage backends. "
            + f"Collected errors: {[type(e).__name__ for e in errors]}"
        )

    @override
    def _raw_close(self, handle: int) -> bool:
        """Route directly to the inner backend

        Args:
            handle: The handle to close

        Returns:
            True if closed successfully

        """
        inner = self._session_registry[handle]
        ret = self._backends[inner.backend]._raw_close(inner.handle)
        _ = self._session_registry.pop(handle)
        return ret

    @override
    def delete(self, path: P) -> bool:
        """Deletes the asset from all backends

        Args:
            path: The path to the file to delete

        Returns:
            True if file existed on any backend and was deleted

        """
        return reduce(
            lambda a, b: a or b, (backend.delete(path) for backend in self._backends)
        )

    @override
    def list(self, path: P) -> tuple[Sequence[P], Sequence[P]]:
        """Returns a merged, deduplicated sequence of all available contents

        Args:
            path: The path to directory to list

        Returns:
            A list of full pathes to items within that directory

        """
        backend_res = [backend.list(path) for backend in self._backends]
        return (
            list({path: None for res in backend_res for path in res[0]}.keys()),
            list({path: None for res in backend_res for path in res[1]}.keys()),
        )

    @override
    def mkdir(self, path: P, parents_ok: bool = True, exists_ok: bool = True) -> None:
        """Creates the directory on the primary backend (index 0)

        Args:
            path: The path to create
            parents_ok: Is okay to create directory parent
            exists_ok: Is okay to ignore if the directory already exists

        """
        self._backends[0].mkdir(path, parents_ok=parents_ok, exists_ok=exists_ok)

    @override
    def rmdir(self, path: P) -> bool:
        """Removes the directory from all backends

        Args:
            path: The directory to delete

        Returns:
            True if deleted, False if does not exist

        """
        return reduce(
            lambda a, b: a or b, (backend.rmdir(path) for backend in self._backends)
        )

    @override
    def _raw_read_stream(self, handle: int) -> Iterator[bytes]:
        """Stream transparently to the inner backend

        Args:
            handle: The handle to read

        Yields:
            Raw bytes of the read file

        """
        inner = self._session_registry[handle]
        yield from self._backends[inner.backend]._raw_read_stream(inner.handle)

    @override
    def _raw_write_stream(
        self,
        handle: int,
        stream: Iterator[bytes],
        size: int,
        allow_override: bool,
    ) -> None:
        """Writes data directly to the active backend tier matching the session handle.

        Args:
            handle: The file to write to
            stream: The content to write
            size: The size in bytes of the file to write
            allow_override: Allow deleting old file

        """
        inner = self._session_registry[handle]
        self._backends[inner.backend]._raw_write_stream(
            inner.handle, stream, size, allow_override
        )

    @override
    def get_times(self, path: P) -> FileTimeInfo:
        return self._backends[0].get_times(path)

    @override
    def size(self, path: P) -> int:
        return self._backends[0].size(path)

    @override
    def health(self) -> None:
        """The fallback group is healthy if at least one sub-backend is alive

        Raises:
            OSError: If all backends failed

        """
        for backend in self._backends:
            try:
                backend.health()
                return
            except Exception:
                logger.error(f"Backend {backend.__class__.__name__} is not healthy")
                continue
        raise OSError(
            "All backends inside the fallback pool are currently unmounted or down."
        )
