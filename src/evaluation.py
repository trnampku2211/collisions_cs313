"""Metrics for DBSCAN hotspot outputs."""

from __future__ import annotations

import pandas as pd


def calculate_cluster_metrics(
    location_df: pd.DataFrame,
) -> dict[str, float | int]:
    clustered = location_df["cluster"].ne(-1)
    clustered_rows = location_df.loc[clustered]
    total_crashes = float(location_df["crash_count"].sum())
    total_injuries = float(location_df["injured"].sum())
    total_deaths = float(location_df["killed"].sum())

    cluster_sizes = clustered_rows.groupby("cluster")["crash_count"].sum()
    clustered_crashes = float(clustered_rows["crash_count"].sum())

    return {
        "n_locations": int(len(location_df)),
        "n_clusters": int(clustered_rows["cluster"].nunique()),
        "noise_locations_pct": round(float((~clustered).mean() * 100), 3),
        "crash_coverage_pct": round(
            clustered_crashes / total_crashes * 100 if total_crashes else 0.0, 3
        ),
        "injury_coverage_pct": round(
            float(clustered_rows["injured"].sum()) / total_injuries * 100
            if total_injuries
            else 0.0,
            3,
        ),
        "fatality_coverage_pct": round(
            float(clustered_rows["killed"].sum()) / total_deaths * 100
            if total_deaths
            else 0.0,
            3,
        ),
        "largest_cluster_share_pct": round(
            float(cluster_sizes.max()) / clustered_crashes * 100
            if clustered_crashes and not cluster_sizes.empty
            else 0.0,
            3,
        ),
        "median_cluster_crashes": round(
            float(cluster_sizes.median()) if not cluster_sizes.empty else 0.0, 3
        ),
    }

