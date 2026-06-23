"""Test fallback layered storage backend"""

# pyright: reportUninitializedInstanceVariable=false, reportUnknownMemberType=false, reportAny=false, reportPrivateUsage=false
# ruff: noqa: D102

from __future__ import annotations

import unittest
from pathlib import Path
from typing import override
from unittest.mock import MagicMock

from archive.storage.fallback import FallbackStorageBackend, _SessionEntry

# Adjust these imports to align with your project's directory hierarchy
from archive.storage.storage import FileTimeInfo


class TestFallbackStorageBackend(unittest.TestCase):
    """Test fallback layered storage backend with fake mock layers"""

    @override
    def setUp(self) -> None:
        # Construct two separate mock sub-backends (Tiers 0 and 1)
        self.mock_tier0: MagicMock = MagicMock()
        self.mock_tier1: MagicMock = MagicMock()

        self.backends: list[MagicMock] = [self.mock_tier0, self.mock_tier1]
        self.fallback_backend: FallbackStorageBackend[Path, str] = (
            FallbackStorageBackend(self.backends)
        )
        self.sample_path: Path = Path("shared/asset.txt")

    def test_init_raises_value_error_on_empty_sequence(self) -> None:
        """Guarantees instantiation crashes if an empty backend pool is provided."""
        with self.assertRaises(ValueError):
            _ = FallbackStorageBackend([])  # pyright: ignore[reportUnknownVariableType]

    # ==========================================
    # STRUCTURAL CHECK & COMBINATION ROUTINES
    # ==========================================

    def test_exists_checks_sequentially(self) -> None:
        # Tier 0 misses, Tier 1 intercepts the path target successfully
        self.mock_tier0.exists.return_value = False
        self.mock_tier1.exists.return_value = True

        self.assertTrue(self.fallback_backend.exists(self.sample_path))
        self.mock_tier0.exists.assert_called_once_with(self.sample_path)
        self.mock_tier1.exists.assert_called_once_with(self.sample_path)

    def test_exists_fails_completely_if_all_miss(self) -> None:
        self.mock_tier0.exists.return_value = False
        self.mock_tier1.exists.return_value = False

        self.assertFalse(self.fallback_backend.exists(self.sample_path))

    def test_delete_applies_cascading_reduction(self) -> None:
        """Verifies true is returned if any single backend successfully deletes."""
        self.mock_tier0.delete.return_value = False
        self.mock_tier1.delete.return_value = True

        res = self.fallback_backend.delete(self.sample_path)
        self.assertTrue(res)
        self.mock_tier0.delete.assert_called_once_with(self.sample_path)
        self.mock_tier1.delete.assert_called_once_with(self.sample_path)

    def test_list_merges_and_deduplicates_cross_platform_results(self) -> None:
        """Verifies deduplication dictionary keys behave like custom set unions."""
        path = Path("docs")
        self.mock_tier0.list.return_value = (
            [Path("docs/dirA")],
            [Path("docs/file1.txt")],
        )
        self.mock_tier1.list.return_value = (
            [Path("docs/dirA"), Path("docs/dirB")],
            [Path("docs/file2.txt")],
        )

        dirs, files = self.fallback_backend.list(path)

        # Output structures must contain unique elements extracted across all layers
        self.assertCountEqual(dirs, [Path("docs/dirA"), Path("docs/dirB")])
        self.assertCountEqual(files, [Path("docs/file1.txt"), Path("docs/file2.txt")])

    def test_mkdir_routes_exclusively_to_primary_tier(self) -> None:
        path = Path("new_workspace")
        self.fallback_backend.mkdir(path, parents_ok=True, exists_ok=True)

        self.mock_tier0.mkdir.assert_called_once_with(
            path, parents_ok=True, exists_ok=True
        )
        self.mock_tier1.mkdir.assert_not_called()

    def test_rmdir_cascades_recursively(self) -> None:
        path = Path("old_workspace")
        self.mock_tier0.rmdir.return_value = True
        self.mock_tier1.rmdir.return_value = False

        self.assertTrue(self.fallback_backend.rmdir(path))
        self.mock_tier0.rmdir.assert_called_once_with(path)
        self.mock_tier1.rmdir.assert_called_once_with(path)

    # ==========================================
    # SESSION LIFECYCLE & FAILOVER OPERATIONS
    # ==========================================

    def test_raw_open_intercepts_preexisting_file(self) -> None:
        """Verifies routing when a file is explicitly spotted alive on Tier 1 first."""
        self.mock_tier0.exists.return_value = False
        self.mock_tier1.exists.return_value = True
        self.mock_tier1._raw_open.return_value = "inner_h_123"

        outer_handle = self.fallback_backend._raw_open(self.sample_path)

        self.assertEqual(outer_handle, 1)
        session = self.fallback_backend._session_registry[outer_handle]
        self.assertEqual(session.backend, 1)  # Mapped to Tier 1
        self.assertEqual(session.handle, "inner_h_123")

    def test_raw_open_handles_primary_failure_and_recovers_to_fallback(self) -> None:
        """Tests sequential fallback loop if no target files pre-exist anywhere."""
        self.mock_tier0.exists.return_value = False
        self.mock_tier1.exists.return_value = False

        # Tier 0 throws an OS error on open; Tier 1 takes it over cleanly
        self.mock_tier0._raw_open.side_effect = PermissionError("Restricted access")
        self.mock_tier1._raw_open.return_value = "inner_h_999"

        outer_handle = self.fallback_backend._raw_open(self.sample_path)

        self.assertEqual(outer_handle, 1)
        session = self.fallback_backend._session_registry[outer_handle]
        self.assertEqual(session.backend, 1)  # Recovers to Tier 1 index context
        self.assertEqual(session.handle, "inner_h_999")

    def test_raw_open_raises_file_not_found_if_all_tiers_crash(self) -> None:
        self.mock_tier0.exists.return_value = False
        self.mock_tier1.exists.return_value = False

        self.mock_tier0._raw_open.side_effect = FileNotFoundError("Missing A")
        self.mock_tier1._raw_open.side_effect = OSError("Drive broken B")

        with self.assertRaises(FileNotFoundError) as context:
            _ = self.fallback_backend._raw_open(self.sample_path)

        # Confirm underlying crash reports roll up into collective logging strings
        self.assertIn("FileNotFoundError", str(context.exception))
        self.assertIn("OSError", str(context.exception))

    def test_raw_close_lifecycle(self) -> None:
        # Setup pre-registered surrogate context session pointing inside Tier 1
        self.fallback_backend._session_registry[1] = _SessionEntry(
            backend=1, handle="inner_h"
        )
        self.mock_tier1._raw_close.return_value = True

        self.assertTrue(self.fallback_backend._raw_close(1))
        self.mock_tier1._raw_close.assert_called_once_with("inner_h")
        self.assertNotIn(1, self.fallback_backend._session_registry)

    # ==========================================
    # STREAM ENCAPSULATION & DATA PASSING
    # ==========================================

    def test_raw_read_stream_tunnels_transparently(self) -> None:
        self.fallback_backend._session_registry[1] = _SessionEntry(
            backend=0, handle="h0"
        )
        self.mock_tier0._raw_read_stream.return_value = iter([b"data_block"])

        stream_output = list(self.fallback_backend._raw_read_stream(1))
        self.assertEqual(stream_output, [b"data_block"])
        self.mock_tier0._raw_read_stream.assert_called_once_with("h0")

    def test_raw_write_stream_tunnels_transparently(self) -> None:
        self.fallback_backend._session_registry[1] = _SessionEntry(
            backend=1, handle="h1"
        )
        payload = iter([b"write_block"])

        self.fallback_backend._raw_write_stream(
            1, payload, size=11, allow_override=True
        )
        self.mock_tier1._raw_write_stream.assert_called_once_with(
            "h1", payload, 11, True
        )

    # ==========================================
    # POOL METADATA & HEALTH EVALUATION
    # ==========================================

    def test_get_times_and_size_reads_from_primary(self) -> None:
        mock_info = FileTimeInfo(MagicMock(), MagicMock(), MagicMock())
        self.mock_tier0.get_times.return_value = mock_info
        self.mock_tier0.size.return_value = 4096

        self.assertEqual(self.fallback_backend.get_times(self.sample_path), mock_info)
        self.assertEqual(self.fallback_backend.size(self.sample_path), 4096)

        # Verify completely skipped on fallback tier
        self.mock_tier1.get_times.assert_not_called()
        self.mock_tier1.size.assert_not_called()

    def test_health_passes_if_at_least_one_tier_is_functional(self) -> None:
        # Tier 0 is broken, but Tier 1 answers health requests normally
        self.mock_tier0.health.side_effect = RuntimeError("Service Down")

        # Should not raise an error
        self.assertIsNone(self.fallback_backend.health())
        self.mock_tier0.health.assert_called_once()
        self.mock_tier1.health.assert_called_once()

    def test_health_raises_os_error_if_all_tiers_are_dead(self) -> None:
        self.mock_tier0.health.side_effect = Exception("Crash A")
        self.mock_tier1.health.side_effect = Exception("Crash B")

        with self.assertRaises(OSError) as context:
            self.fallback_backend.health()
        self.assertIn(
            "fallback pool are currently unmounted or down", str(context.exception)
        )


if __name__ == "__main__":
    _ = unittest.main()
