"""Weighted geospatial DBSCAN utilities."""

from __future__ import annotations

from itertools import product

import numpy as np
import pandas as pd
from sklearn.cluster import DBSCAN
from sklearn.neighbors import NearestNeighbors

from src.config import EARTH_RADIUS_M
from src.evaluation import calculate_cluster_metrics


def aggregate_locations(df: pd.DataFrame) -> pd.DataFrame:
    required = {"lat_round", "lon_round", "COLLISION_ID"}
    missing = required.difference(df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {sorted(missing)}")

    return (
        df.groupby(["lat_round", "lon_round"], as_index=False)
        .agg(
            crash_count=("COLLISION_ID", "count"),
            injured=("NUMBER OF PERSONS INJURED", "sum"),
            killed=("NUMBER OF PERSONS KILLED", "sum"),
            injury_crashes=("has_injury", "sum"),
            fatal_crashes=("has_fatality", "sum"),
            vulnerable_crashes=("vulnerable_user_involved", "sum"),
        )
        .sort_values(["lat_round", "lon_round"])
        .reset_index(drop=True)
    )


def coordinates_to_radians(location_df: pd.DataFrame) -> np.ndarray:
    return np.radians(location_df[["lat_round", "lon_round"]].to_numpy())


def calculate_k_distances(
    coordinates_rad: np.ndarray,
    n_neighbors: int,
) -> np.ndarray:
    if len(coordinates_rad) < n_neighbors:
        raise ValueError("n_neighbors cannot exceed the number of locations.")
    model = NearestNeighbors(
        n_neighbors=n_neighbors,
        metric="haversine",
        algorithm="ball_tree",
        n_jobs=-1,
    )
    model.fit(coordinates_rad)
    distances, _ = model.kneighbors(coordinates_rad)
    return np.sort(distances[:, -1] * EARTH_RADIUS_M)


def fit_dbscan(
    location_df: pd.DataFrame,
    eps_m: float,
    min_samples: int,
) -> tuple[DBSCAN, pd.DataFrame]:
    if eps_m <= 0 or min_samples <= 0:
        raise ValueError("eps_m and min_samples must be positive.")
    coordinates = coordinates_to_radians(location_df)
    model = DBSCAN(
        eps=eps_m / EARTH_RADIUS_M,
        min_samples=min_samples,
        metric="haversine",
        algorithm="ball_tree",
        n_jobs=-1,
    )
    labels = model.fit_predict(
        coordinates,
        sample_weight=location_df["crash_count"].to_numpy(),
    )
    result = location_df.copy()
    result["cluster"] = labels.astype(int)
    return model, result


def run_parameter_grid(
    location_df: pd.DataFrame,
    eps_values_m: tuple[float, ...],
    min_samples_values: tuple[int, ...],
) -> pd.DataFrame:
    rows: list[dict[str, float | int]] = []
    for eps_m, min_samples in product(eps_values_m, min_samples_values):
        _, clustered = fit_dbscan(location_df, eps_m, min_samples)
        metrics = calculate_cluster_metrics(clustered)
        rows.append({"eps_m": eps_m, "min_samples": min_samples, **metrics})
    return pd.DataFrame(rows).sort_values(
        ["largest_cluster_share_pct", "crash_coverage_pct"],
        ascending=[True, False],
    )

