"""Storage backend abstraction for media files"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING, Self

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from datetime import datetime
    from types import TracebackType

logger = logging.getLogger(__name__)


@dataclass
class FileTimeInfo:
    """Represents the ACM times for a file"""

    accessed: datetime
    created: datetime
    modified: datetime


class ManagedHandle[PathType, RawHandle]:
    """A context-managed wrapper around a backend's raw file handle."""

    def __init__(
        self,
        backend: StorageBackend[PathType, RawHandle],
        path: PathType,
        raw_handle: RawHandle,
    ) -> None:
        """Creates a managed handle for the storage backend

        Suports __enter__ and __exit__

        Args:
            backend: The backend this is from
            path: The path representing the handle
            raw_handle: The raw handle for the backend

        """
        self._backend: StorageBackend[PathType, RawHandle] = backend
        self.path: PathType = path
        self._raw_handle: RawHandle = raw_handle

    def __enter__(self) -> Self:
        """Enter a protected scope with this file opened

        Returns:
            The file handle

        """
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Closes the file"""
        _ = self._backend.close(self)

    def read_stream(self) -> Iterator[bytes]:
        """Reads data sequentially from the handle using a memory-safe chunk generator.

        Yields:
            An iterator of bytes read from the file

        """
        yield from self._backend.read_stream(self)

    def read(self) -> bytes:
        """Read data from a handle, collecting it into a single object

        Returns:
            Raw bytes read from the file

        """
        return self._backend.read(self)

    def write_stream(
        self,
        stream: Iterator[bytes],
        size: int,
        allow_override: bool,
    ) -> None:
        """Consumes a byte generator stream and writes it sequentially to the file.

        Args:
            stream: The content to write
            size: The size of the file to write
            allow_override: Allow overwriting a file if it exists

        """
        self._backend.write_stream(self, stream, size, allow_override)

    def write(
        self,
        content: bytes,
        allow_override: bool,
    ) -> None:
        """Writes bytes sequentially to the file.

        Args:
            content: The content to write
            allow_override: Allow overwriting a file if it exists

        """
        self._backend.write(self, content, allow_override)


class StorageBackend[PathType, FileHandle](ABC):
    """Storage backend interface"""

    @abstractmethod
    def exists(self, path: PathType) -> bool:
        """Checks whether a file exists at a path or not

        Args:
            path: The path to check

        Returns:
            True if the file exists

        """

    @abstractmethod
    def _raw_open(self, path: PathType) -> FileHandle:
        """Opens or references a file path

        Args:
            path: The path to open

        Returns:
            A session handle

        """

    @abstractmethod
    def _raw_close(self, handle: FileHandle) -> bool:
        """Closes the file linked to the handle and evicts it from memory.

        Args:
            handle: The file handle to close

        Returns:
            True if closed, False if already closed

        """

    @abstractmethod
    def delete(self, path: PathType) -> bool:
        """Deletes a file or directory from the file system.

        This is a low-level storage capability, not authorization to remove archival
        data. Callers must follow the deletion policy documented in
        ``docs/storage_layer/storage_layer.md``.

        Args:
            path: The file or directory to delete

        Returns:
            True if deleted, False if doesn't exist

        """

    @abstractmethod
    def list(self, path: PathType) -> tuple[Sequence[PathType], Sequence[PathType]]:
        """Lists directory contents relative to the storage engine root directory.

        Args:
            path: The path to retrieve contents from

        Returns:
            A tuple of sequences of full pathes from the backend root if a directory
            The tuple is in the order of a sequence of directories,
            then a sequence of files

        """

    @abstractmethod
    def mkdir(
        self, path: PathType, parents_ok: bool = True, exists_ok: bool = True
    ) -> None:
        """Makes a directory at the specified path

        Args:
            path: The path to create
            parents_ok: Is okay to create directory parent
            exists_ok: Is okay to ignore if the directory already exists

        """

    @abstractmethod
    def rmdir(self, path: PathType) -> bool:
        """Removes a directory given a path.

        This is a low-level storage capability, not authorization to remove archival
        data. Callers must follow the deletion policy documented in
        ``docs/storage_layer/storage_layer.md``.

        Args:
            path: The directory to delete

        Returns:
            True if deleted, False if does not exist

        """

    @abstractmethod
    def _raw_read_stream(self, handle: FileHandle) -> Iterator[bytes]:
        """Reads data sequentially from the handle using a memory-safe chunk generator.

        Args:
            handle: The handle to read from

        Yields:
            An iterator of bytes read from the file

        Raises:
            KeyError: If handle does not exist
            FileNotFoundError: If the file does not exist

        """

    @abstractmethod
    def _raw_write_stream(
        self,
        handle: FileHandle,
        stream: Iterator[bytes],
        size: int,
        allow_override: bool,
    ) -> None:
        """Consumes a byte generator stream and writes it sequentially to the file.

        Args:
            handle: The handle to write to
            stream: The content to write
            size: The size of the file to write
            allow_override: Allow overwriting a file if it exists

        Raises:
            KeyError: If handle does not exist
            FileExistsError: If file exists and overwriting is not allowed

        """

    @abstractmethod
    def get_times(self, path: PathType) -> FileTimeInfo:
        """Get the ACM times for a specified file

        Args:
            path: The path to a file to look up

        Returns:
            ACM times

        """

    @abstractmethod
    def size(self, path: PathType) -> int:
        """Gets the size in byes of a file

        Args:
            path: The path to a file to look up

        Returns:
            The size of the file in bytes

        """

    @abstractmethod
    def health(self) -> None:
        """Checks if the base directory remains read/write accessible

        Raises:
            An Exception if the directory does not exist or no permissions

        """

    # TODO: Support mode strings (rb, wb, ab)
    def open(self, path: PathType) -> ManagedHandle[PathType, FileHandle]:
        """Opens or references a file path

        Args:
            path: The path to open

        Returns:
            A session handle

        """
        return ManagedHandle[PathType, FileHandle](self, path, self._raw_open(path))

    def close(self, handle: ManagedHandle[PathType, FileHandle]) -> bool:
        """Closes the file linked to the handle and evicts it from memory.

        Args:
            handle: The file handle to close

        Returns:
            True if closed, False if already closed

        """
        return self._raw_close(handle._raw_handle)  # pyright: ignore[reportPrivateUsage]

    def read_stream(
        self, handle: ManagedHandle[PathType, FileHandle]
    ) -> Iterator[bytes]:
        """Reads data sequentially from the handle using a memory-safe chunk generator.

        Args:
            handle: The handle to read from

        Yields:
            An iterator of bytes read from the file

        """
        yield from self._raw_read_stream(handle._raw_handle)  # pyright: ignore[reportPrivateUsage]

    def read(self, handle: ManagedHandle[PathType, FileHandle]) -> bytes:
        """Read data from a handle, collecting it into a single object

        Args:
            handle: The handle to read from

        Returns:
            Raw bytes read from the file

        """
        return b"".join(self.read_stream(handle))

    def write_stream(
        self,
        handle: ManagedHandle[PathType, FileHandle],
        stream: Iterator[bytes],
        size: int,
        allow_override: bool,
    ) -> None:
        """Consumes a byte generator stream and writes it sequentially to the file.

        Args:
            handle: The handle to write to
            stream: The content to write
            size: The size of the file to write
            allow_override: Allow overwriting a file if it exists

        """
        self._raw_write_stream(handle._raw_handle, stream, size, allow_override)  # pyright: ignore[reportPrivateUsage]

    def write(
        self,
        handle: ManagedHandle[PathType, FileHandle],
        content: bytes,
        allow_override: bool,
    ) -> None:
        """Writes bytes sequentially to the file.

        Args:
            handle: The handle to write to
            content: The content to write
            allow_override: Allow overwriting a file if it exists

        """
        self.write_stream(handle, iter((content,)), len(content), allow_override)
