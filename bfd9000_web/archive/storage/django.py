"""Django Storage backend support for our custom composable storage backends"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, override

from django.core.files.base import File
from django.core.files.storage import Storage

if TYPE_CHECKING:
    from collections.abc import Iterator
    from datetime import datetime

    from _typeshed import WriteableBuffer
    from archive.storage.storage import ManagedHandle, StorageBackend

    ByteFile = File[bytes]
else:
    ByteFile = File


class DjangoStreamFile[H](ByteFile):
    """An internal file-like wrapper around the ABC's read_stream iterator."""

    def __init__(
        self,
        backend: StorageBackend[str, H],
        handle: ManagedHandle[str, H],
        name: str,
    ) -> None:
        """Create a new Django compatible file from our custom backend"""
        self.backend: StorageBackend[str, H] = backend
        self.handle: ManagedHandle[str, H] = handle
        self.name: str = name  # pyright: ignore[reportIncompatibleVariableOverride]
        # Convert the byte-iterator into a file-like stream using io.BufferedReader
        self._stream: io.BufferedReader[DjangoIteratorIO] = io.BufferedReader(
            DjangoIteratorIO(backend.read_stream(handle))
        )
        super().__init__(self._stream, name=name)

    @override
    def read(self, size: int = -1, /) -> bytes:  # pyright: ignore[reportIncompatibleMethodOverride]
        """Forward the read request to the underlying buffer.

        Args:
            size: The number of bytes to read

        Returns:
            Those bytes

        """
        return self._stream.read(size)

    @override
    def close(self) -> None:
        super().close()
        # Ensure the backend handle gets evicted from memory when closed
        _ = self.backend.close(self.handle)


class DjangoIteratorIO(io.RawIOBase):
    """Bridge to convert an Iterator[bytes] generator into a readable standard stream"""

    def __init__(self, iterator: Iterator[bytes]) -> None:
        """Create a Buffered Reader from a byte iterator"""
        self.iterator: Iterator[bytes] = iterator
        self.buffer: bytes = b""

    @override
    def readable(self) -> bool:
        """Explicitly tell Python's IO wrapper that this stream can be read from.

        Returns:
            True

        """
        return True

    @override
    def readinto(self, b: WriteableBuffer, /) -> int:
        """Read bytes directly into a mutable WritableBuffer wrapper.

        Args:
            b: A WriteableBuffer to write into

        Returns:
            Number of bytes remaining to write

        """
        # Cast to a memoryview to ensure safe slice allocation
        view = memoryview(b)
        size = len(view)

        while len(self.buffer) < size:
            try:
                self.buffer += next(self.iterator)
            except StopIteration:
                break

        bytes_to_copy = min(len(self.buffer), size)
        if bytes_to_copy == 0:
            return 0  # EOF reached

        # Assign raw bytes into the memoryview allocation slice
        view[:bytes_to_copy] = self.buffer[:bytes_to_copy]
        self.buffer = self.buffer[bytes_to_copy:]

        return bytes_to_copy

    @override
    def read(self, size: int = -1) -> bytes:
        if size == -1:
            return b"".join(self.iterator)
        while len(self.buffer) < size:
            try:
                self.buffer += next(self.iterator)
            except StopIteration:
                break
        result = self.buffer[:size]
        self.buffer = self.buffer[size:]
        return result


class DjangoStorageAdapter[H](Storage):
    """Adapter transforming your StorageBackend ABC into Django Storage."""

    def __init__(self, backend: StorageBackend[str, H]) -> None:
        """A Django compatible backend using our URIStorageBackend"""
        self._backend: StorageBackend[str, H] = backend

    def _open(self, name: str, mode: str = "rb") -> ByteFile:  # pyright: ignore[reportUnusedParameter]  # noqa: ARG002
        handle = self._backend.open(name)
        return DjangoStreamFile(self._backend, handle, name)

    def _save(self, name: str, content: ByteFile) -> str:
        with self._backend.open(name) as handle:
            file_size = content.size
            self._backend.write_stream(
                handle=handle,
                stream=content.chunks(),
                size=file_size,
                allow_override=True,
            )
        return name

    @override
    def exists(self, name: str) -> bool:
        return self._backend.exists(name)

    @override
    def delete(self, name: str) -> None:
        _ = self._backend.delete(name)

    @override
    def listdir(self, path: str) -> tuple[list[str], list[str]]:
        raw_sequence = self._backend.list(path)
        return (
            list(raw_sequence[0]),
            list(raw_sequence[1]),
        )

    @override
    def size(self, name: str) -> int:
        return self._backend.size(name)

    @override
    def url(self, name: str | None) -> str:
        """Return the backend-qualified stored name without creating an HTTP URL.

        Args:
            name: filename

        Returns:
            The internal qualified URL name

        """
        return name or ""

    @override
    def get_accessed_time(self, name: str) -> datetime:
        return self._backend.get_times(name).accessed

    @override
    def get_created_time(self, name: str) -> datetime:
        return self._backend.get_times(name).created

    @override
    def get_modified_time(self, name: str) -> datetime:
        return self._backend.get_times(name).modified

    # Overriden file checking functions to allow Django to handle URIs instead of pathes

    @override
    def get_valid_name(self, name: str) -> str:
        """Override Django's default filename cleanup.

        Django normally runs name through os.path.basename() which destroys URI
        schemes (e.g., 'box://file.txt' becomes 'file.txt'). Returning the name
        as-is preserves your protocols safely.

        Returns:
            The same name, as file name handling is done in the backend

        """
        return name

    @override
    def get_available_name(self, name: str, max_length: int | None = None) -> str:
        """Override Django's de-duplication loop.

        Prevents Django from trying to append suffixes like '_a8fG2' inside your
        URI string, allowing your custom storage backends to handle namespace
        collisions natively.

        Returns:
            The same name, as file name handling is done in the backend

        """
        return name
