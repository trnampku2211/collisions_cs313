"""Cluster summaries and rankings."""

from __future__ import annotations

import pandas as pd


def create_cluster_profile(location_df: pd.DataFrame) -> pd.DataFrame:
    clustered = location_df[location_df["cluster"].ne(-1)]
    profile = (
        clustered.groupby("cluster", as_index=False)
        .agg(
            locations=("cluster", "size"),
            crashes=("crash_count", "sum"),
            injured=("injured", "sum"),
            killed=("killed", "sum"),
            injury_crashes=("injury_crashes", "sum"),
            fatal_crashes=("fatal_crashes", "sum"),
            vulnerable_crashes=("vulnerable_crashes", "sum"),
            center_lat=("lat_round", "mean"),
            center_lon=("lon_round", "mean"),
        )
        .sort_values("crashes", ascending=False)
        .reset_index(drop=True)
    )
    if profile.empty:
        return profile
    profile["injured_per_100_crashes"] = profile["injured"] / profile["crashes"] * 100
    profile["killed_per_100k_crashes"] = profile["killed"] / profile["crashes"] * 100_000
    profile["injury_crash_pct"] = profile["injury_crashes"] / profile["crashes"] * 100
    profile["vulnerable_crash_pct"] = profile["vulnerable_crashes"] / profile["crashes"] * 100
    return profile


def rank_clusters_by_frequency(profile: pd.DataFrame, n: int = 20) -> pd.DataFrame:
    return profile.nlargest(n, "crashes").copy()


def rank_clusters_by_severity(
    profile: pd.DataFrame,
    n: int = 20,
    minimum_crashes: int = 100,
) -> pd.DataFrame:
    eligible = profile[profile["crashes"].ge(minimum_crashes)]
    return eligible.nlargest(n, "killed_per_100k_crashes").copy()


def attach_cluster_labels(
    event_df: pd.DataFrame,
    location_df: pd.DataFrame,
) -> pd.DataFrame:
    lookup = location_df[["lat_round", "lon_round", "cluster"]]
    return event_df.merge(
        lookup,
        on=["lat_round", "lon_round"],
        how="left",
        validate="many_to_one",
    )


def create_hour_profile(event_df: pd.DataFrame) -> pd.DataFrame:
    return (
        event_df[event_df["cluster"].ge(0) & event_df["hour"].notna()]
        .groupby(["cluster", "hour"], as_index=False)
        .agg(crashes=("COLLISION_ID", "count"))
    )


def create_factor_profile(event_df: pd.DataFrame) -> pd.DataFrame:
    factor = "CONTRIBUTING FACTOR VEHICLE 1"
    valid = (
        event_df["cluster"].ge(0)
        & event_df[factor].notna()
        & event_df[factor].ne("Unspecified")
    )
    return (
        event_df.loc[valid]
        .groupby(["cluster", factor], as_index=False)
        .agg(crashes=("COLLISION_ID", "count"))
        .sort_values(["cluster", "crashes"], ascending=[True, False])
    )

