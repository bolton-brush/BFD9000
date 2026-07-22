"""A Local file implementation as a Storage Backend"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, override

from archive.storage.storage import FileTimeInfo, StorageBackend

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence
    from io import BufferedReader, BufferedWriter


@dataclass
class _PathHandle:
    path: Path
    open_file: BufferedReader | BufferedWriter | None


class LocalStorageBackend(StorageBackend[Path, int]):
    """A local disk implementation for Storage Backend."""

    def __init__(self, base_directory: Path, chunk_size: int = 65536) -> None:
        """Create a local disk storage backend based on a directory

        Args:
            base_directory: The parent directory of all files
            chunk_size: Default chunk size to read/write with

        """
        self.base_dir: Path = Path(base_directory).resolve()
        # Ensure the base storage sandbox exists
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.chunk_size: int = chunk_size

        # Registry table to track active handle sessions: int -> open file object
        self._handles: dict[int, _PathHandle] = {}
        self._counter: int = 0
        self._sentinel: object = object()

    def _resolve_safe_path(self, path: Path) -> Path:
        """Helper to enforce sandbox security and prevent path traversal attacks.

        Returns:
            The resolved path relative to the base directory

        Raises:
            PermissionError: If path leaves the base directory

        """
        resolved = (self.base_dir / path).resolve()
        if not resolved.is_relative_to(self.base_dir):
            raise PermissionError(
                f"Access denied: Path {path} escapes the storage base directory."
            )
        return resolved

    @override
    def exists(self, path: Path) -> bool:
        full_path = self._resolve_safe_path(path)
        return full_path.exists()

    @override
    def _raw_open(self, path: Path) -> int:
        """Opens or references a local file path

        Args:
            path: The path to open

        Returns:
            An integer session handle

        """
        full_path = self._resolve_safe_path(path)

        # Ensure parent directories exist for the file
        full_path.parent.mkdir(parents=True, exist_ok=True)

        self._counter += 1
        handle_id = self._counter

        # We store the physical path target. The specific stream operations
        # will open file descriptors in the correct modes as requested.
        self._handles[handle_id] = _PathHandle(full_path, None)
        return handle_id

    @override
    def _raw_close(self, handle: int) -> bool:
        """Closes any open file pointers linked to the handle and evicts it from memory.

        Args:
            handle: The file handle to close

        Returns:
            True if closed, False if already closed

        """
        if handle not in self._handles:
            return False

        session = self._handles[handle]
        file_obj = session.open_file

        if file_obj and not file_obj.closed:
            file_obj.close()

        del self._handles[handle]
        return True

    @override
    def delete(self, path: Path) -> bool:
        """Deletes a file or directory safely from the local file system.

        Args:
            path: The file or directory to delete

        Returns:
            True if deleted, False if doesn't exist

        """
        full_path = self._resolve_safe_path(path)
        if not full_path.exists():
            return False

        if full_path.is_dir():
            shutil.rmtree(full_path)
        else:
            full_path.unlink()

        return True

    @override
    def list(self, path: Path) -> tuple[Sequence[Path], Sequence[Path]]:
        """Lists directory contents relative to the storage engine root directory.

        Args:
            path: The path to retrieve contents from

        Returns:
            A sequence of full pathes from the backend root, or nothing if a file

        """
        full_path = self._resolve_safe_path(path)
        if not full_path.exists() or not full_path.is_dir():
            return ([], [])

        files = list(full_path.iterdir())

        # Return paths relative to the base storage directory for consistency
        return (
            [p.relative_to(self.base_dir) for p in files if p.is_dir()],
            [p.relative_to(self.base_dir) for p in files if p.is_file()],
        )

    @override
    def mkdir(
        self, path: Path, parents_ok: bool = True, exists_ok: bool = True
    ) -> None:
        """Makes a directory at the specified path

        Args:
            path: The path to create
            parents_ok: Is okay to create directory parent
            exists_ok: Is okay to ignore if the directory already exists

        """
        p = self._resolve_safe_path(path)
        p.mkdir(parents=parents_ok, exist_ok=exists_ok)

    @override
    def rmdir(self, path: Path) -> bool:
        """Removes a directory given a path

        Args:
            path: The directory to delete

        Returns:
            True if deleted, False if does not exist

        """
        p = self._resolve_safe_path(path)
        exists = p.exists()
        if not exists:
            return False
        p.rmdir()
        return True

    @override
    def _raw_read_stream(self, handle: int) -> Iterator[bytes]:
        """Reads data sequentially from the handle using a memory-safe chunk generator.

        Args:
            handle: The handle to read from

        Yields:
            An iterator of bytes read from the file

        Raises:
            KeyError: If handle does not exist
            FileNotFoundError: If the file does not exist

        """
        if handle not in self._handles:
            raise KeyError(f"Invalid or expired handle: {handle}")

        session = self._handles[handle]
        full_path = session.path

        if not full_path.exists():
            raise FileNotFoundError(f"File target missing for handle {handle}")

        # Open the file in binary-read mode and assign it to the tracking session
        f = full_path.open("rb")
        session.open_file = f

        try:
            while chunk := f.read(self.chunk_size):
                yield chunk
        finally:
            f.close()

    @override
    def _raw_write_stream(
        self, handle: int, stream: Iterator[bytes], size: int, allow_override: bool
    ) -> None:
        """Consumes a byte generator stream and writes it sequentially to disk.

        Args:
            handle: The handle to write to
            stream: The content to write
            size: The size of the file to write
            allow_override: Allow overwriting a file if it exists

        Raises:
            KeyError: If handle does not exist
            FileExistsError: If file exists and overwriting is not allowed

        """
        if handle not in self._handles:
            raise KeyError(f"Invalid or expired handle: {handle}")

        session = self._handles[handle]
        full_path = session.path

        # Open in binary-write mode
        if full_path.exists() and not allow_override:
            raise FileExistsError("File already exists")

        with full_path.open("wb") as f:
            session.open_file = f
            for chunk in stream:
                _ = f.write(chunk)

    @override
    def get_times(self, path: Path) -> FileTimeInfo:
        p = self._resolve_safe_path(path)
        stats = p.stat()
        return FileTimeInfo(
            accessed=datetime.fromtimestamp(stats.st_atime, tz=UTC),
            modified=datetime.fromtimestamp(stats.st_mtime, tz=UTC),
            # Note: st_ctime is "metadata change time" on Unix,
            # but "birth/creation time" on Windows.
            # For a cross-platform birthtime,
            # st_birthtime is available on macOS/BSD/some Linux.
            created=datetime.fromtimestamp(
                getattr(stats, "st_birthtime", stats.st_ctime), tz=UTC
            ),
        )

    @override
    def size(self, path: Path) -> int:
        p = self._resolve_safe_path(path)
        return p.stat().st_size

    @override
    def health(self) -> None:
        """Checks if the base directory remains read/write accessible

        Raises:
            OSError: If storage root does not exist
            PermissionError: If no permissions to read/write to the root

        """
        if not self.base_dir.exists():
            raise OSError("Base storage path has been deleted or unmounted.")
        if not os.access(self.base_dir, os.W_OK | os.R_OK):
            raise PermissionError("Storage directory permissions lost.")
