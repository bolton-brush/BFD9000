"""Test urihandler storage backend"""

# pyright: reportUninitializedInstanceVariable=false, reportUnknownMemberType=false, reportAny=false, reportPrivateUsage=false
# ruff: noqa: D102
from __future__ import annotations

import unittest
from pathlib import Path
from typing import override
from unittest.mock import MagicMock

# Adjust these imports to align with your project's directory hierarchy
from archive.storage.storage import FileTimeInfo
from archive.storage.urihandler import URIStorageBackend, _SessionEntry


class TestURIStorageBackend(unittest.TestCase):
    """Test urihandler storage backend with mock routes"""

    @override
    def setUp(self) -> None:
        # Create two distinct downstream mock backends
        self.mock_local: MagicMock = MagicMock()
        self.mock_box: MagicMock = MagicMock()

        # Wire them into the scheme router routing map
        self.routes: dict[str, MagicMock] = {
            "local": self.mock_local,
            "box": self.mock_box,
        }
        self.uri_backend: URIStorageBackend[int] = URIStorageBackend(self.routes)

    # ==========================================
    # URI STRING PARSING & SCHEME DISPATCH
    # ==========================================

    def test_split_uri_valid_resolutions(self) -> None:
        """Verifies clean scheme parsing and accurate sub-Path isolation."""
        # 1. Test standard relative path construction
        scheme, backend, sub_path = self.uri_backend._split_uri(
            "local://documents/file.txt"
        )
        self.assertEqual(scheme, "local")
        self.assertEqual(backend, self.mock_local)
        self.assertEqual(sub_path, Path("documents/file.txt"))

        # 2. Test implicit path trimming of trailing/leading network location slashes
        _, _, sub_path_box = self.uri_backend._split_uri("box:///vault/secure.dat")
        self.assertEqual(sub_path_box, Path("vault/secure.dat"))

    def test_split_uri_missing_scheme_raises_value_error(self) -> None:
        """Guarantees bare naked path strings without a scheme fail immediately."""
        with self.assertRaises(ValueError) as context:
            _ = self.uri_backend._split_uri("/just/a/raw/path.txt")
        self.assertIn("Invalid URI composition", str(context.exception))

    def test_split_uri_unregistered_scheme_raises_key_error(self) -> None:
        """Guarantees unmapped schemes (e.g., s3://) drop clear KeyErrors."""
        with self.assertRaises(KeyError) as context:
            _ = self.uri_backend._split_uri("s3://bucket/data.tar")
        self.assertIn("No storage backend engine registered", str(context.exception))

    def test_make_uri_utility(self) -> None:
        """Verifies clean string formatting out of concrete Path structures."""
        uri_str = self.uri_backend._make_uri("local", Path("images/pic.png"))
        self.assertEqual(uri_str, "local://images/pic.png")

    # ==========================================
    # ROUTED FILESYSTEM OPERATIONS
    # ==========================================

    def test_exists_routes_correctly(self) -> None:
        self.mock_box.exists.return_value = True

        self.assertTrue(self.uri_backend.exists("box://shared/report.pdf"))
        self.mock_box.exists.assert_called_once_with(Path("shared/report.pdf"))
        self.mock_local.exists.assert_not_called()

    def test_delete_routes_correctly(self) -> None:
        self.mock_local.delete.return_value = True

        self.assertTrue(self.uri_backend.delete("local://temp/junk.tmp"))
        self.mock_local.delete.assert_called_once_with(Path("temp/junk.tmp"))

    def test_list_reconstructs_and_wraps_subpaths_into_uris(self) -> None:
        """Verifies inner primitive paths map back up into complete domain URIs."""
        # Setup mock return signature using primitive Sub-Paths
        self.mock_box.list.return_value = (
            [Path("media/dir1")],
            [Path("media/track.mp3")],
        )

        dirs, files = self.uri_backend.list("box://media")

        # Returned collections should match reconstructed
        # global URIs matching target scheme
        self.assertEqual(dirs, ["box://media/dir1"])
        self.assertEqual(files, ["box://media/track.mp3"])
        self.mock_box.list.assert_called_once_with(Path("media"))

    def test_mkdir_and_rmdir_routing(self) -> None:
        # 1. Test Directory Creation Routing
        self.uri_backend.mkdir(
            "local://configs/system", parents_ok=True, exists_ok=False
        )
        self.mock_local.mkdir.assert_called_once_with(
            Path("configs/system"), parents_ok=True, exists_ok=False
        )

        # 2. Test Directory Removal Routing
        self.mock_local.rmdir.return_value = True
        self.assertTrue(self.uri_backend.rmdir("local://configs/system"))
        self.mock_local.rmdir.assert_called_once_with(Path("configs/system"))

    # ==========================================
    # SESSION REGISTRY & VIRTUALIZED HANDLE LIFECYCLE
    # ==========================================

    def test_raw_open_and_close_session_lifecycle(self) -> None:
        """Tests sequential container handles mapping into underlying engine contexts"""
        # Setup downstream mock handle return identifier
        self.mock_box._raw_open.return_value = "box_handle_abc"
        self.mock_box._raw_close.return_value = True

        # Open structural global session handle via URI
        outer_handle = self.uri_backend._raw_open("box://records/log.txt")

        self.assertEqual(outer_handle, 1)
        self.assertIn(outer_handle, self.uri_backend._session_registry)

        session = self.uri_backend._session_registry[outer_handle]
        self.assertEqual(session.backend, "box")
        self.assertEqual(session.handle, "box_handle_abc")
        self.mock_box._raw_open.assert_called_once_with(Path("records/log.txt"))

        # Close structural global session handle
        close_success = self.uri_backend._raw_close(outer_handle)
        self.assertTrue(close_success)
        self.mock_box._raw_close.assert_called_once_with("box_handle_abc")

    # ==========================================
    # DATA STREAM TUNNELING
    # ==========================================

    def test_raw_read_stream_tunnels_transparently(self) -> None:
        # Pre-seed internal registry with a fake active local handle tracking record
        self.uri_backend._session_registry[42] = _SessionEntry(
            backend="local", handle=101
        )
        self.mock_local._raw_read_stream.return_value = iter([b"data_stream"])

        output = list(self.uri_backend._raw_read_stream(42))
        self.assertEqual(output, [b"data_stream"])
        self.mock_local._raw_read_stream.assert_called_once_with(101)

    def test_raw_write_stream_tunnels_transparently(self) -> None:
        self.uri_backend._session_registry[42] = _SessionEntry(
            backend="box", handle=202
        )
        payload = iter([b"payload_stream"])

        self.uri_backend._raw_write_stream(42, payload, size=14, allow_override=True)
        self.mock_box._raw_write_stream.assert_called_once_with(202, payload, 14, True)

    # ==========================================
    # METADATA & HEALTH POOL MONITORING
    # ==========================================

    def test_get_times_and_size_metadata_routing(self) -> None:
        mock_info = FileTimeInfo(MagicMock(), MagicMock(), MagicMock())
        self.mock_box.get_times.return_value = mock_info
        self.mock_box.size.return_value = 2048

        self.assertEqual(self.uri_backend.get_times("box://file.csv"), mock_info)
        self.assertEqual(self.uri_backend.size("box://file.csv"), 2048)

    def test_health_passes_when_all_routes_are_healthy(self) -> None:
        # No return values on health checks means they pass implicitly without crashing
        self.mock_local.health.return_value = None
        self.mock_box.health.return_value = None

        # Assert no runtime exceptions raise up
        self.assertIsNone(self.uri_backend.health())

    def test_health_fails_and_aggregates_all_crashing_route_reports(self) -> None:
        """Verifies that failures across routes collect into a report."""
        # Local crashes out with an unexpected system exception; Box passes safely
        self.mock_local.health.side_effect = PermissionError("Drive read-only")
        self.mock_box.health.return_value = None

        with self.assertRaises(RuntimeError) as context:
            self.uri_backend.health()

        # Verify specific aggregated error reports propagate in full string payload
        self.assertIn(
            "Backend MagicMock (local://) is not healthy", str(context.exception)
        )
        self.assertIn("Drive read-only", str(context.exception))


if __name__ == "__main__":
    _ = unittest.main()
