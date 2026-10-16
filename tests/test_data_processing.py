import unittest

import numpy as np
import pandas as pd

from src.config import GeoConfig
from src.data_processing import filter_valid_coordinates, validate_collision_ids


class DataProcessingTests(unittest.TestCase):
    def test_coordinate_filter(self):
        df = pd.DataFrame(
            {
                "LATITUDE": [40.7, 0.0, np.nan, 42.0],
                "LONGITUDE": [-74.0, 0.0, -74.0, -74.0],
            }
        )
        config = GeoConfig(40.3, 41.1, -74.5, -73.5, 4)
        result = filter_valid_coordinates(df, config)
        self.assertEqual(len(result), 1)

    def test_collision_id_validation(self):
        df = pd.DataFrame({"COLLISION_ID": [1, 1, 2, pd.NA]})
        result = validate_collision_ids(df)
        self.assertEqual(result["duplicate_collision_ids"], 1)
        self.assertEqual(result["missing_collision_ids"], 1)


if __name__ == "__main__":
    unittest.main()

