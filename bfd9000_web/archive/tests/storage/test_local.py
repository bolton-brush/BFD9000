"""Test local storage backend"""

# pyright: reportUninitializedInstanceVariable=false, reportUnknownMemberType=false, reportAny=false, reportPrivateUsage=false
# ruff: noqa: D102
from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import UTC, datetime
from pathlib import Path
from typing import override

from archive.storage.local import LocalStorageBackend

# Adjust imports to match your project's directory hierarchy
from archive.storage.storage import FileTimeInfo


class TestLocalStorageBackend(unittest.TestCase):
    """Test Box storage backend with a tmpdir"""

    @override
    def setUp(self) -> None:
        # Create an isolated, temporary directory acting as the storage base
        self.temp_dir: tempfile.TemporaryDirectory[str] = tempfile.TemporaryDirectory()
        self.base_path: Path = Path(self.temp_dir.name).resolve()

        # Instantiate the backend using a small chunk size
        # to force streaming multi-loops
        self.backend: LocalStorageBackend = LocalStorageBackend(
            base_directory=self.base_path, chunk_size=4
        )

    @override
    def tearDown(self) -> None:
        # Recursively wipe clean the OS temporary directory allocation context
        self.temp_dir.cleanup()

    # ==========================================
    # PATH RESOLUTION & SECURITY CONTROLS
    # ==========================================

    def test_resolve_safe_path_valid(self) -> None:
        """Verifies correct structural assembly of internal workspace relative paths."""
        target_path = Path("documents/archive.tar.gz")
        resolved = self.backend._resolve_safe_path(target_path)
        self.assertEqual(resolved, self.base_path / target_path)

    def test_resolve_safe_path_traversal_attack_raises_permission_error(self) -> None:
        """Guarantees path traversal escapes trigger immediate PermissionError"""
        malicious_path = Path("../../../etc/passwd")
        with self.assertRaises(PermissionError) as context:
            _ = self.backend._resolve_safe_path(malicious_path)
        self.assertIn("escapes the storage base directory", str(context.exception))

    # ==========================================
    # CORE FILESYSTEM MUTATION CONTROLS
    # ==========================================

    def test_exists(self) -> None:
        path = Path("sample.txt")
        self.assertFalse(self.backend.exists(path))

        # Physically generate the concrete file to verify state shift
        _ = (self.base_path / path).write_text("hello")
        self.assertTrue(self.backend.exists(path))

    def test_raw_open_and_close_lifecycle(self) -> None:
        """Verifies descriptor state registration and systematic pointer clearing."""
        path = Path("records/file.dat")
        handle = self.backend._raw_open(path)

        # Confirm handles scale up monotonically and save targets correctly
        self.assertEqual(handle, 1)
        self.assertIn(handle, self.backend._handles)
        self.assertEqual(self.backend._handles[handle].path, self.base_path / path)
        # Ensure parent subdirectories ('records/') are made automatically upon opening
        self.assertTrue((self.base_path / "records").exists())

        # Close out the handle session
        close_success = self.backend._raw_close(handle)
        self.assertTrue(close_success)
        self.assertNotIn(handle, self.backend._handles)

        # Ensure attempting to close an expired or
        # non-existent handle flags out False safely
        self.assertFalse(self.backend._raw_close(999))

    def test_delete_file_and_directory(self) -> None:
        # 1. Test deleting file targets
        file_path = Path("delete_me.txt")
        _ = (self.base_path / file_path).write_text("payload")
        self.assertTrue(self.backend.delete(file_path))
        self.assertFalse((self.base_path / file_path).exists())

        # 2. Test recursive directory deletion (shutil.rmtree branch)
        dir_path = Path("nested_dir")
        self.backend.mkdir(dir_path)
        _ = (self.base_path / dir_path / "child.txt").write_text("inner payload")
        self.assertTrue(self.backend.delete(dir_path))
        self.assertFalse((self.base_path / dir_path).exists())

        # 3. Non-existent returns False safely
        self.assertFalse(self.backend.delete(Path("ghost_file.txt")))

    def test_list_directory_contents(self) -> None:
        self.backend.mkdir(Path("src/dir1"))
        self.backend.mkdir(Path("src/dir2"))
        _ = (self.base_path / "src" / "file1.txt").write_text("abc")
        _ = (self.base_path / "src" / "file2.log").write_text("xyz")

        dirs, files = self.backend.list(Path("src"))

        # Assert relative-to-root path structures map back symmetrically
        self.assertCountEqual(dirs, [Path("src/dir1"), Path("src/dir2")])
        self.assertCountEqual(files, [Path("src/file1.txt"), Path("src/file2.log")])

        # Listing an invalid path target returns pair of empty arrays
        self.assertEqual(self.backend.list(Path("missing_folder")), ([], []))

    def test_mkdir_and_rmdir(self) -> None:
        target_dir = Path("structures/tree")
        self.backend.mkdir(target_dir, parents_ok=True, exists_ok=True)
        self.assertTrue((self.base_path / target_dir).is_dir())

        # Remove directory leaf node structure
        self.assertTrue(self.backend.rmdir(target_dir))
        self.assertFalse((self.base_path / target_dir).exists())

        # Removing non-existent returns False safely
        self.assertFalse(self.backend.rmdir(Path("non_existent_dir")))

    # ==========================================
    # DATA STREAMING MANAGEMENT
    # ==========================================

    def test_raw_read_stream_success(self) -> None:
        """Verifies multi-chunk iteration loops based on constrained chunk limits."""
        test_file = Path("stream_source.txt")
        # 11 characters. Chunk size is 4.
        # Iteration loop yields: 4 bytes -> 4 bytes -> 3 bytes.
        _ = (self.base_path / test_file).write_bytes(b"HelloWorld!")

        handle = self.backend._raw_open(test_file)
        chunks = list(self.backend._raw_read_stream(handle))

        self.assertEqual(chunks, [b"Hell", b"oWor", b"ld!"])
        # Verify finally clause accurately drops standard handle wrappers
        self.assertTrue(self.backend._handles[handle].open_file.closed)  # pyright: ignore[reportOptionalMemberAccess]

    def test_raw_read_stream_error_paths(self) -> None:
        # Invalid handle tracking check
        with self.assertRaises(KeyError):
            _ = list(self.backend._raw_read_stream(999))

        # Handle allocated but file missing on disk check
        handle = self.backend._raw_open(Path("ghost.dat"))
        with self.assertRaises(FileNotFoundError):
            _ = list(self.backend._raw_read_stream(handle))

    def test_raw_write_stream_success(self) -> None:
        target_file = Path("stream_output.bin")
        handle = self.backend._raw_open(target_file)

        byte_stream = iter([b"chunk_one_", b"chunk_two"])
        self.backend._raw_write_stream(
            handle, byte_stream, size=19, allow_override=False
        )

        # Validate unified payload alignment on disk
        self.assertEqual(
            (self.base_path / target_file).read_bytes(), b"chunk_one_chunk_two"
        )

    def test_raw_write_stream_collision_without_override_raises_error(self) -> None:
        target_file = Path("protected.txt")
        _ = (self.base_path / target_file).write_text("original content")

        handle = self.backend._raw_open(target_file)
        with self.assertRaises(FileExistsError):
            self.backend._raw_write_stream(
                handle, iter([b"new content"]), size=11, allow_override=False
            )

    # ==========================================
    # METADATA & SYSTEM SANITY CHECKS
    # ==========================================

    def test_get_times_and_size(self) -> None:
        path = Path("meta.dat")
        full_path = self.base_path / path
        _ = full_path.write_bytes(b"exact_length_of_18")

        # Size matching checks
        self.assertEqual(self.backend.size(path), 18)

        # Time mapping validation checks
        time_info = self.backend.get_times(path)
        self.assertIsInstance(time_info, FileTimeInfo)
        self.assertIsInstance(time_info.accessed, datetime)
        self.assertIsInstance(time_info.modified, datetime)
        self.assertIsInstance(time_info.created, datetime)

        # Verify everything anchors correctly into timezone-aware UTC structures
        self.assertEqual(time_info.modified.tzinfo, UTC)

    def test_health_check_pass(self) -> None:
        """Verifies active read/write checks pass on a healthy functional sandbox."""
        self.assertIsNone(self.backend.health())

    def test_health_check_missing_base_raises_os_error(self) -> None:
        """Wipes out base path directory dynamically to force an unmounted OSError."""
        shutil.rmtree(self.base_path)
        with self.assertRaises(OSError) as context:
            self.backend.health()
        self.assertIn("deleted or unmounted", str(context.exception))


if __name__ == "__main__":
    _ = unittest.main()
