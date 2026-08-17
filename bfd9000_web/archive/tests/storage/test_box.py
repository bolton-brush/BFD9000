"""Test Box storage backend"""

# pyright: reportUninitializedInstanceVariable=false, reportUnknownMemberType=false, reportAny=false, reportPrivateUsage=false
# ruff: noqa: D102
from __future__ import annotations

import datetime as dt
import io
import unittest
from pathlib import Path
from typing import override
from unittest.mock import ANY, MagicMock, patch

from box_sdk_gen import (
    File,
    FileBaseTypeField,
    Folder,
    FolderBaseTypeField,
)

from archive.storage.box import (
    BoxStorageBackend,
    _ItemData,
    _SessionEntry,
)

# Adjust imports to fit your repository's structure
from archive.storage.storage import FileTimeInfo


class TestBoxStorageBackend(unittest.TestCase):  # noqa: PLR0904
    """Test Box storage backend with a mock Box client"""

    @override
    def setUp(self) -> None:
        # Clear cache tools cache before each test to guarantee isolated states
        BoxStorageBackend._get_item.cache_clear()

        # Mock Auth Engine
        self.mock_auth: MagicMock = MagicMock()
        self.mock_client: MagicMock = MagicMock()
        self.mock_auth.get_client.return_value = self.mock_client

        self.root_folder_id: str = "root_123"
        self.backend: BoxStorageBackend = BoxStorageBackend(
            box_auth=self.mock_auth, box_folder_id=self.root_folder_id
        )

    @override
    def tearDown(self) -> None:
        BoxStorageBackend._get_item.cache_clear()

    # ==========================================
    # PATH RESOLUTION & CACHING TESTS
    # ==========================================

    def test_resolve_path_empty(self) -> None:
        """Verifies that an empty path resolves instantly to the root folder ID."""
        res = self.backend._resolve_path_to_id(self.mock_client, Path(), is_folder=True)
        self.assertEqual(res.id, self.root_folder_id)
        self.assertTrue(res.is_folder)

    def test_resolve_path_success_file(self) -> None:
        """Tests successful multi-tier path resolution for a file node."""
        # Mock subfolder and final file entries
        # Can't use MagicMock here due to the "type" parameter
        mock_folder_entry = Folder(
            id="sub_999", name="docs", type=FolderBaseTypeField.FOLDER
        )

        mock_file_entry = File(
            id="file_888", name="test.txt", type=FileBaseTypeField.FILE
        )

        # First query gets folder items for root, second gets folder items for subfolder
        self.mock_client.folders.get_folder_items.side_effect = [
            MagicMock(entries=[mock_folder_entry]),
            MagicMock(entries=[mock_file_entry]),
        ]

        res = self.backend._resolve_path_to_id(
            self.mock_client, Path("docs/test.txt"), is_folder=False
        )
        self.assertEqual(res.id, "file_888")
        self.assertEqual(res.name, "test.txt")
        self.assertFalse(res.is_folder)

    def test_resolve_path_folder_not_found_raises_error(self) -> None:
        """Verifies FileNotFoundError when intermediate folder is missing."""
        self.mock_client.folders.get_folder_items.return_value = MagicMock(entries=[])

        with self.assertRaises(FileNotFoundError):
            _ = self.backend._resolve_path_to_id(
                self.mock_client, Path("missing_dir/file.txt"), is_folder=False
            )

    def test_resolve_path_mkdir_parents(self) -> None:
        """Verifies automatic recursive parent directory creation."""
        mock_new_folder = MagicMock(id="new_fold_777", name="ghost_folder")
        self.mock_client.folders.get_folder_items.return_value = MagicMock(entries=[])
        self.mock_client.folders.create_folder.return_value = mock_new_folder

        with patch.object(BoxStorageBackend, "_get_item") as mock_get:
            # First look for folder: None. Third for file: mock.
            mock_get.side_effect = [
                None,
                _ItemData("f1", "target.dat", False),
            ]

            res = self.backend._resolve_path_to_id(
                self.mock_client,
                Path("ghost_folder/target.dat"),
                is_folder=False,
                mk_parent=True,
            )
            self.assertEqual(res.id, "f1")
            self.mock_client.folders.create_folder.assert_called_once_with(
                name="ghost_folder", parent=ANY
            )
            actual_parent = self.mock_client.folders.create_folder.call_args.kwargs[
                "parent"
            ]
            self.assertEqual(actual_parent.id, "root_123")

    def test_resolve_path_mkdir_target(self) -> None:
        """Verifies leaf node directory allocation if mkdir=True and is_folder=True."""
        self.mock_client.folders.get_folder_items.return_value = MagicMock(entries=[])
        self.mock_client.folders.create_folder.return_value = MagicMock(
            id="target_folder_id", name="target_dir"
        )

        res = self.backend._resolve_path_to_id(
            self.mock_client, Path("target_dir"), is_folder=True, mkdir=True
        )
        self.assertEqual(res.id, "target_folder_id")

    def test_get_item_cached(self) -> None:
        """Verifies LRUCache handles identical lookup without repeating API requests."""
        mock_item = MagicMock(
            id="file_abc", name="cached.txt", type=FileBaseTypeField.FILE
        )
        self.mock_client.folders.get_folder_items.return_value = MagicMock(
            entries=[mock_item]
        )

        # Call twice
        res1 = self.backend._get_item(
            self.mock_client, "parent_id", "cached.txt", is_folder=False
        )
        res2 = self.backend._get_item(
            self.mock_client, "parent_id", "cached.txt", is_folder=False
        )

        self.assertEqual(res1, res2)
        # API should only get polled exactly once
        self.mock_client.folders.get_folder_items.assert_called_once_with("parent_id")

    # ==========================================
    # FILE OPERATIONS: EXISTS, OPEN, CLOSE, DELETE
    # ==========================================

    def test_exists_true(self) -> None:
        with (
            patch.object(self.backend, "_resolve_path_to_id") as mock_resolve,
            patch.object(self.backend, "_get_item") as mock_get,
        ):
            mock_resolve.return_value = _ItemData("dir_id", "uploads", True)
            mock_get.return_value = _ItemData("file_id", "photo.jpg", False)

            self.assertTrue(self.backend.exists(Path("uploads/photo.jpg")))

    def test_exists_false(self) -> None:
        with (
            patch.object(self.backend, "_resolve_path_to_id") as mock_resolve,
            patch.object(self.backend, "_get_item") as mock_get,
        ):
            mock_resolve.return_value = _ItemData("dir_id", "uploads", True)
            mock_get.return_value = None

            self.assertFalse(self.backend.exists(Path("uploads/photo.jpg")))

    def test_raw_open_new_file(self) -> None:
        """Tests that opening a non-existent path registers a session handle."""
        with (
            patch.object(self.backend, "_resolve_path_to_id") as mock_resolve,
            patch.object(self.backend, "_get_item") as mock_get,
        ):
            mock_resolve.return_value = _ItemData("dir_123", "root", True)
            mock_get.return_value = None  # File does not exist yet

            handle = self.backend._raw_open(Path("new_file.txt"))
            self.assertEqual(handle, 1)
            self.assertIn(handle, self.backend._session_registry)

            session = self.backend._session_registry[handle]
            self.assertIsNone(session.file_id)
            self.assertEqual(session.filename, "new_file.txt")

    def test_raw_close(self) -> None:
        # Inject manual session
        self.backend._session_registry[42] = _SessionEntry(
            self.mock_client, "dir", "f", "id"
        )

        # Act & Assert
        self.assertTrue(self.backend._raw_close(42))
        self.assertNotIn(42, self.backend._session_registry)

        # Closing an invalid session handle returns False safely
        self.assertFalse(self.backend._raw_close(999))

    def test_delete_success(self) -> None:
        with (
            patch.object(self.backend, "_resolve_path_to_id") as mock_resolve,
            patch.object(self.backend, "_get_item") as mock_get,
        ):
            mock_resolve.return_value = _ItemData("dir_id", "root", True)
            mock_get.return_value = _ItemData("file_id_to_delete", "killme.txt", False)

            res = self.backend.delete(Path("killme.txt"))
            self.assertTrue(res)
            self.mock_client.files.delete_file_by_id.assert_called_once_with(
                "file_id_to_delete"
            )

    def test_delete_file_not_found(self) -> None:
        with (
            patch.object(self.backend, "_resolve_path_to_id") as mock_resolve,
            patch.object(self.backend, "_get_item") as mock_get,
        ):
            mock_resolve.return_value = _ItemData("dir_id", "root", True)
            mock_get.return_value = None

            res = self.backend.delete(Path("ghost.txt"))
            self.assertFalse(res)
            self.mock_client.files.delete_file_by_id.assert_not_called()

    # ==========================================
    # DIRECTORY OPERATIONS: LIST, MKDIR, RMDIR
    # ==========================================

    def test_list_directories_and_files(self) -> None:
        with patch.object(self.backend, "_resolve_path_to_id") as mock_resolve:
            mock_resolve.return_value = _ItemData("dir_id", "target", True)

            item_fold = MagicMock(name="fold1", type=FolderBaseTypeField.FOLDER)
            item_fold.name = "sub_dir"
            item_file = MagicMock(name="file1", type=FileBaseTypeField.FILE)
            item_file.name = "doc.pdf"

            self.mock_client.folders.get_folder_items.return_value = MagicMock(
                entries=[item_fold, item_file]
            )

            dirs, files = self.backend.list(Path("target"))
            self.assertEqual(dirs, [Path("target/sub_dir")])
            self.assertEqual(files, [Path("target/doc.pdf")])

    def test_mkdir(self) -> None:
        with patch.object(self.backend, "_resolve_path_to_id") as mock_resolve:
            self.backend.mkdir(Path("a/b/c"), parents_ok=True, exists_ok=False)
            mock_resolve.assert_called_once_with(
                self.mock_client, Path("a/b"), True, mk_parent=True, mkdir=False
            )

    def test_rmdir_success(self) -> None:
        with (
            patch.object(self.backend, "_resolve_path_to_id") as mock_resolve,
            patch.object(self.backend, "_get_item") as mock_get,
        ):
            mock_resolve.return_value = _ItemData("parent_id", "a", True)
            mock_get.return_value = _ItemData("folder_id_to_kill", "b", True)

            self.assertTrue(self.backend.rmdir(Path("a/b")))
            self.mock_client.folders.delete_folder_by_id.assert_called_once_with(
                "folder_id_to_kill"
            )

    def test_rmdir_missing(self) -> None:
        with (
            patch.object(self.backend, "_resolve_path_to_id") as mock_resolve,
            patch.object(self.backend, "_get_item") as mock_get,
        ):
            mock_resolve.return_value = _ItemData("parent_id", "a", True)
            mock_get.return_value = None

            self.assertFalse(self.backend.rmdir(Path("a/missing_folder")))

    # ==========================================
    # STREAM READ & WRITE TESTS
    # ==========================================

    def test_raw_read_stream_success(self) -> None:
        self.backend._session_registry[10] = _SessionEntry(
            self.mock_client, "dir", "file.dat", "file_id_999"
        )
        fake_stream = io.BytesIO(b"chunk1chunk2")
        self.mock_client.downloads.download_file.return_value = fake_stream

        chunks = list(self.backend._raw_read_stream(10))
        self.assertEqual(chunks, [b"chunk1chunk2"])

    def test_raw_read_stream_missing_handle_or_id_raises_key_error(self) -> None:
        with self.assertRaises(KeyError):
            _ = list(self.backend._raw_read_stream(999))  # Bad handle

    def test_raw_read_stream_download_not_found_raises_file_error(self) -> None:
        self.backend._session_registry[10] = _SessionEntry(
            self.mock_client, "dir", "file.dat", "file_id_999"
        )
        self.mock_client.downloads.download_file.return_value = None

        with self.assertRaises(FileNotFoundError):
            _ = list(self.backend._raw_read_stream(10))

    def test_write_stream_file_exists_no_override_raises_error(self) -> None:
        # Set up active file target matching an existing object
        self.backend._session_registry[5] = _SessionEntry(
            self.mock_client, "dir", "file.dat", "preexisting_id"
        )

        with self.assertRaises(FileExistsError):
            self.backend._raw_write_stream(
                5, iter([b""]), size=100, allow_override=False
            )

    def test_write_stream_big_file_override_deletes_old_file(self) -> None:
        self.backend._session_registry[5] = _SessionEntry(
            self.mock_client, "dir", "huge.mp4", "old_id"
        )
        big_size = 21 * 1024**2  # Over 20MB limit trigger

        self.mock_client.chunked_uploads.upload_big_file.return_value = MagicMock(
            id="new_big_id"
        )

        self.backend._raw_write_stream(
            5, iter([b"data"]), size=big_size, allow_override=True
        )

        # Verify old asset deletion step ran
        self.mock_client.files.delete_file_by_id.assert_called_once_with("old_id")
        # Verify large file handler destination route ran
        self.mock_client.chunked_uploads.upload_big_file.assert_called_once()

    def test_write_stream_small_file_version_creation(self) -> None:
        self.backend._session_registry[5] = _SessionEntry(
            self.mock_client, "dir", "small.txt", "existing_id"
        )

        mock_entry = MagicMock(id="version_2_id")
        self.mock_client.uploads.upload_file_version.return_value = MagicMock(
            entries=[mock_entry]
        )

        self.backend._raw_write_stream(
            5, iter([b"small bytes"]), size=500, allow_override=True
        )

        self.mock_client.uploads.upload_file_version.assert_called_once()
        self.assertEqual(self.backend._session_registry[5].file_id, "version_2_id")

    def test_write_stream_brand_new_file_upload(self) -> None:
        self.backend._session_registry[5] = _SessionEntry(
            self.mock_client, "dir", "fresh.txt", None
        )

        mock_entry = MagicMock(id="brand_new_id")
        self.mock_client.uploads.upload_file.return_value = MagicMock(
            entries=[mock_entry]
        )

        self.backend._raw_write_stream(
            5, iter([b"fresh bytes"]), size=500, allow_override=False
        )

        self.mock_client.uploads.upload_file.assert_called_once()
        self.assertEqual(self.backend._session_registry[5].file_id, "brand_new_id")

    # ==========================================
    # METADATA & HEALTH CHECKS
    # ==========================================

    def test_get_times(self) -> None:
        with patch.object(self.backend, "_resolve_path_to_id") as mock_resolve:
            mock_resolve.return_value = _ItemData("file_id", "timed.txt", False)

            mock_file = MagicMock()
            mock_file.modified_at = dt.datetime(2026, 6, 11, 10, 0, tzinfo=dt.UTC)
            mock_file.created_at = dt.datetime(2026, 6, 11, 9, 0, tzinfo=dt.UTC)
            self.mock_client.files.get_file_by_id.return_value = mock_file

            times = self.backend.get_times(Path("timed.txt"))
            self.assertIsInstance(times, FileTimeInfo)
            self.assertEqual(times.modified, mock_file.modified_at)
            self.assertEqual(times.created, mock_file.created_at)

    def test_size(self) -> None:
        with patch.object(self.backend, "_resolve_path_to_id") as mock_resolve:
            mock_resolve.return_value = _ItemData("file_id", "sized.txt", False)

            mock_file = MagicMock()
            mock_file.size = 2048
            self.mock_client.files.get_file_by_id.return_value = mock_file

            self.assertEqual(self.backend.size(Path("sized.txt")), 2048)

    def test_health_pass(self) -> None:
        self.backend.health()
        self.mock_client.folders.get_folder_by_id.assert_called_once_with(
            self.root_folder_id
        )

    def test_health_failure_wraps_exception(self) -> None:
        self.mock_client.folders.get_folder_by_id.side_effect = RuntimeError(
            "Network out"
        )

        with self.assertRaises(Exception) as ctx:
            self.backend.health()
        self.assertIn("Box service connection broken", str(ctx.exception))


if __name__ == "__main__":
    _ = unittest.main()
