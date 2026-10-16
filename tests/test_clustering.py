import unittest

import pandas as pd

from src.clustering import fit_dbscan
from src.evaluation import calculate_cluster_metrics


class ClusteringTests(unittest.TestCase):
    def test_weighted_dbscan_finds_cluster_and_noise(self):
        locations = pd.DataFrame(
            {
                "lat_round": [40.7000, 40.7002, 40.7001, 40.9000],
                "lon_round": [-74.0000, -74.0001, -74.0002, -73.6000],
                "crash_count": [10, 8, 7, 1],
                "injured": [1, 2, 1, 0],
                "killed": [0, 0, 0, 0],
                "injury_crashes": [1, 2, 1, 0],
                "fatal_crashes": [0, 0, 0, 0],
                "vulnerable_crashes": [0, 1, 0, 0],
            }
        )
        _, result = fit_dbscan(locations, eps_m=100, min_samples=5)
        self.assertEqual(result.loc[3, "cluster"], -1)
        self.assertEqual(result.loc[:2, "cluster"].nunique(), 1)
        metrics = calculate_cluster_metrics(result)
        self.assertEqual(metrics["n_clusters"], 1)


if __name__ == "__main__":
    unittest.main()

