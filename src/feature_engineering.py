"""Feature engineering for temporal, severity and spatial analysis."""

from __future__ import annotations

import numpy as np
import pandas as pd

from src.config import PeriodConfig


def add_temporal_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["year"] = result["CRASH DATE"].dt.year.astype("Int64")
    result["month"] = result["CRASH DATE"].dt.month.astype("Int64")
    result["day_of_week"] = result["CRASH DATE"].dt.day_name()
    result["is_weekend"] = result["day_of_week"].isin(["Saturday", "Sunday"])
    result["hour"] = pd.to_numeric(
        result["CRASH TIME"].astype("string").str.split(":").str[0],
        errors="coerce",
    ).astype("Int64")
    result["time_period"] = pd.cut(
        result["hour"].astype("float64"),
        bins=[-1, 5, 9, 15, 19, 23],
        labels=["Late night", "Morning peak", "Midday", "Evening peak", "Night"],
    )
    return result


def add_severity_features(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["has_injury"] = result["NUMBER OF PERSONS INJURED"].fillna(0).gt(0)
    result["has_fatality"] = result["NUMBER OF PERSONS KILLED"].fillna(0).gt(0)
    vulnerable_columns = [
        "NUMBER OF PEDESTRIANS INJURED",
        "NUMBER OF PEDESTRIANS KILLED",
        "NUMBER OF CYCLIST INJURED",
        "NUMBER OF CYCLIST KILLED",
    ]
    result["vulnerable_user_involved"] = (
        result[vulnerable_columns].fillna(0).sum(axis=1).gt(0)
    )
    return result


def add_analysis_periods(
    df: pd.DataFrame,
    periods: tuple[PeriodConfig, ...],
) -> pd.DataFrame:
    result = df.copy()
    conditions = [
        result["year"].between(period.start_year, period.end_year)
        for period in periods
    ]
    choices = [period.name for period in periods]
    result["period"] = np.select(conditions, choices, default="Outside scope")
    return result


def add_rounded_coordinates(df: pd.DataFrame, precision: int) -> pd.DataFrame:
    result = df.copy()
    result["lat_round"] = result["LATITUDE"].round(precision)
    result["lon_round"] = result["LONGITUDE"].round(precision)
    return result


def build_features(
    df: pd.DataFrame,
    periods: tuple[PeriodConfig, ...],
    coordinate_precision: int,
) -> pd.DataFrame:
    result = add_temporal_features(df)
    result = add_severity_features(result)
    result = add_analysis_periods(result, periods)
    return add_rounded_coordinates(result, coordinate_precision)

