from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from laser_link.profile import derive_optical_windows


class LaserLinkTests(unittest.TestCase):
    def test_cloud_block_and_acquisition_are_explicit(self):
        start = datetime(2026, 1, 1, tzinfo=timezone.utc)
        passes = [
            SimpleNamespace(satellite="A", start=start, end=start + timedelta(seconds=60)),
            SimpleNamespace(satellite="B", start=start, end=start + timedelta(seconds=60)),
        ]
        windows = derive_optical_windows(
            passes,
            bandwidth_bps=1_000_000,
            acquisition_seconds=5,
            blocked_passes={1},
        )
        self.assertEqual(len(windows), 1)
        self.assertEqual(windows[0].start, start + timedelta(seconds=5))
        self.assertEqual(windows[0].satellite, "A")


if __name__ == "__main__":
    unittest.main()
