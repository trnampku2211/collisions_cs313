import json
import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.geojson_export import export_browser_bundle, export_period_geojson


class GeoJsonExportTests(unittest.TestCase):
    def test_coordinates_and_street_labels(self):
        crashes = pd.DataFrame(
            {
                "lat_round": [40.7000, 40.7000, 40.7001],
                "lon_round": [-74.0000, -74.0000, -74.0001],
                "ON STREET NAME": ["BROADWAY", "BROADWAY", "7 AVENUE"],
                "CROSS STREET NAME": ["W 34 STREET", "W 34 STREET", "W 35 STREET"],
                "OFF STREET NAME": [None, None, None],
            }
        )
        locations = pd.DataFrame(
            {
                "lat_round": [40.7000, 40.7001],
                "lon_round": [-74.0000, -74.0001],
                "cluster": [5, 5],
                "crash_count": [2, 1],
                "injured": [1, 0],
                "killed": [0, 0],
            }
        )
        profile = pd.DataFrame(
            {
                "cluster": [5],
                "locations": [2],
                "crashes": [3],
                "injured": [1],
                "killed": [0],
                "injury_crashes": [1],
                "fatal_crashes": [0],
                "vulnerable_crashes": [0],
                "center_lat": [40.70005],
                "center_lon": [-74.00005],
                "injured_per_100_crashes": [33.333],
                "killed_per_100k_crashes": [0.0],
                "vulnerable_crash_pct": [0.0],
            }
        )
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as temp_dir:
            path = export_period_geojson(
                crashes, locations, profile, "2017-2019", Path(temp_dir)
            )
            data = json.loads(path.read_text(encoding="utf-8"))
            feature = data["features"][0]
            self.assertIn(
                feature["geometry"]["coordinates"],
                [[-74.0000, 40.7000], [-74.0001, 40.7001]],
            )
            self.assertEqual(feature["properties"]["top_street"], "BROADWAY")
            self.assertEqual(
                feature["properties"]["top_intersection"], "BROADWAY & W 34 STREET"
            )
            detail_path = Path(temp_dir) / feature["properties"]["detail_file"]
            detail = json.loads(detail_path.read_text(encoding="utf-8"))
            self.assertEqual(detail["total_locations"], 2)
            self.assertEqual(len(detail["features"]), 2)
            bundle = export_browser_bundle(Path(temp_dir), ["2017-2019"])
            bundle_text = bundle.read_text(encoding="utf-8")
            self.assertIn('window.NYC_HOTSPOT_DATA={"2017-2019"', bundle_text)
            self.assertIn(f'"{feature["properties"]["detail_file"]}"', bundle_text)


if __name__ == "__main__":
    unittest.main()
