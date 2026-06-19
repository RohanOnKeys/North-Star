from collections import defaultdict
from datetime import timedelta
from pathlib import Path
import unittest

from osps.orbital import predict_from_config
from osps.cli import load_config
from osps.simulation import build_simulator


ROOT = Path(__file__).resolve().parent.parent
SCENARIO = ROOT / "scenarios" / "real_orbits.json"


class OrbitalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config(SCENARIO)
        cls.start, cls.passes = predict_from_config(cls.config, ROOT)

    def test_windows_are_chronological_and_bounded(self):
        self.assertTrue(self.passes)
        end = self.start + timedelta(
            seconds=self.config["orbital"]["duration_seconds"]
        )
        self.assertEqual(self.passes, sorted(self.passes, key=lambda item: (item.start, item.satellite)))
        for item in self.passes:
            self.assertGreaterEqual(item.start, self.start)
            self.assertLessEqual(item.end, end)
            self.assertLess(item.start, item.end)
            self.assertGreaterEqual(
                item.max_elevation_degrees,
                self.config["orbital"]["elevation_threshold_degrees"],
            )
            self.assertGreater(item.estimated_bandwidth, 0)

    def test_no_same_satellite_windows_overlap(self):
        by_satellite = defaultdict(list)
        for item in self.passes:
            by_satellite[item.satellite].append(item)
        for satellite_passes in by_satellite.values():
            for previous, current in zip(satellite_passes, satellite_passes[1:]):
                self.assertLessEqual(previous.end, current.start)

    def test_predictor_preserves_contact_interface(self):
        simulator = build_simulator(self.config, project_root=ROOT)
        self.assertTrue(simulator.contacts)
        self.assertTrue(all(contact.duration > 0 for contact in simulator.contacts))
        self.assertTrue(all(contact.bandwidth > 0 for contact in simulator.contacts))


if __name__ == "__main__":
    unittest.main()
