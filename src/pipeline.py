"""End-to-end orchestration for one analysis period."""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
from sklearn.cluster import DBSCAN

from src.clustering import aggregate_locations, fit_dbscan
from src.evaluation import calculate_cluster_metrics
from src.profiling import create_cluster_profile


@dataclass
class PipelineResult:
    period: str
    model: DBSCAN
    locations: pd.DataFrame
    profile: pd.DataFrame
    metrics: dict[str, float | int]


def run_hotspot_pipeline(
    crash_df: pd.DataFrame,
    period: str,
    eps_m: float,
    min_samples: int,
) -> PipelineResult:
    period_df = crash_df[crash_df["period"].eq(period)].copy()
    if period_df.empty:
        raise ValueError(f"No records available for period {period!r}.")
    locations = aggregate_locations(period_df)
    model, clustered_locations = fit_dbscan(locations, eps_m, min_samples)
    metrics = calculate_cluster_metrics(clustered_locations)
    profile = create_cluster_profile(clustered_locations)
    return PipelineResult(
        period=period,
        model=model,
        locations=clustered_locations,
        profile=profile,
        metrics=metrics,
    )

