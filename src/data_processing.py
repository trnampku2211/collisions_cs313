"""Chunked ingestion, type normalization and data-quality checks."""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

import pandas as pd

from src.config import DataConfig, GeoConfig


CASUALTY_COLUMNS = [
    "NUMBER OF PERSONS INJURED",
    "NUMBER OF PERSONS KILLED",
    "NUMBER OF PEDESTRIANS INJURED",
    "NUMBER OF PEDESTRIANS KILLED",
    "NUMBER OF CYCLIST INJURED",
    "NUMBER OF CYCLIST KILLED",
    "NUMBER OF MOTORIST INJURED",
    "NUMBER OF MOTORIST KILLED",
]

USE_COLUMNS = [
    "CRASH DATE",
    "CRASH TIME",
    "BOROUGH",
    "ZIP CODE",
    "ON STREET NAME",
    "CROSS STREET NAME",
    "OFF STREET NAME",
    "LATITUDE",
    "LONGITUDE",
    *CASUALTY_COLUMNS,
    "CONTRIBUTING FACTOR VEHICLE 1",
    "VEHICLE TYPE CODE 1",
    "COLLISION_ID",
]

STRING_COLUMNS = [
    "CRASH TIME",
    "BOROUGH",
    "ZIP CODE",
    "ON STREET NAME",
    "CROSS STREET NAME",
    "OFF STREET NAME",
    "CONTRIBUTING FACTOR VEHICLE 1",
    "VEHICLE TYPE CODE 1",
]


def parse_data_types(df: pd.DataFrame) -> pd.DataFrame:
    result = df.copy()
    result["CRASH DATE"] = pd.to_datetime(
        result["CRASH DATE"], format="%m/%d/%Y", errors="coerce"
    )
    result["LATITUDE"] = pd.to_numeric(result["LATITUDE"], errors="coerce")
    result["LONGITUDE"] = pd.to_numeric(result["LONGITUDE"], errors="coerce")
    result["COLLISION_ID"] = pd.to_numeric(
        result["COLLISION_ID"], errors="coerce"
    ).astype("Int64")
    for column in STRING_COLUMNS:
        result[column] = result[column].astype("string")
    for column in CASUALTY_COLUMNS:
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result


def _read_filtered_chunks(config: DataConfig) -> Iterable[pd.DataFrame]:
    start = pd.Timestamp(config.start_date)
    end = pd.Timestamp(config.end_date)

    for chunk in pd.read_csv(
        config.input_path,
        usecols=USE_COLUMNS,
        dtype={column: "string" for column in STRING_COLUMNS},
        chunksize=config.chunksize,
        low_memory=False,
    ):
        chunk = parse_data_types(chunk)
        chunk = chunk[chunk["CRASH DATE"].between(start, end)].copy()
        if not chunk.empty:
            yield chunk


def load_crash_data(
    config: DataConfig,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Load the scoped dataset, using a Parquet cache when available."""
    if config.cache_path.exists() and not force_refresh:
        cached = pd.read_parquet(config.cache_path)
        if set(USE_COLUMNS).issubset(cached.columns):
            return cached

    chunks = list(_read_filtered_chunks(config))
    if not chunks:
        raise ValueError("No records remain after applying the configured date range.")

    result = pd.concat(chunks, ignore_index=True)
    config.cache_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(config.cache_path, index=False)
    return result


def valid_coordinate_mask(df: pd.DataFrame, config: GeoConfig) -> pd.Series:
    return (
        df["LATITUDE"].between(config.min_lat, config.max_lat)
        & df["LONGITUDE"].between(config.min_lon, config.max_lon)
        & df["LATITUDE"].ne(0)
        & df["LONGITUDE"].ne(0)
    )


def filter_valid_coordinates(df: pd.DataFrame, config: GeoConfig) -> pd.DataFrame:
    return df.loc[valid_coordinate_mask(df, config)].copy()


def create_quality_report(df: pd.DataFrame) -> pd.DataFrame:
    return (
        pd.DataFrame(
            {
                "column": df.columns,
                "dtype": [str(df[column].dtype) for column in df.columns],
                "missing_count": [int(df[column].isna().sum()) for column in df.columns],
                "missing_pct": [float(df[column].isna().mean() * 100) for column in df.columns],
                "unique_count": [int(df[column].nunique(dropna=True)) for column in df.columns],
            }
        )
        .sort_values("missing_pct", ascending=False)
        .reset_index(drop=True)
    )


def validate_collision_ids(df: pd.DataFrame) -> dict[str, int]:
    return {
        "missing_collision_ids": int(df["COLLISION_ID"].isna().sum()),
        "duplicate_collision_ids": int(df["COLLISION_ID"].duplicated().sum()),
    }


def validate_casualty_totals(df: pd.DataFrame) -> dict[str, int]:
    values = df[CASUALTY_COLUMNS].fillna(0)
    injury_components = values[
        [
            "NUMBER OF PEDESTRIANS INJURED",
            "NUMBER OF CYCLIST INJURED",
            "NUMBER OF MOTORIST INJURED",
        ]
    ].sum(axis=1)
    death_components = values[
        [
            "NUMBER OF PEDESTRIANS KILLED",
            "NUMBER OF CYCLIST KILLED",
            "NUMBER OF MOTORIST KILLED",
        ]
    ].sum(axis=1)
    return {
        "injury_total_mismatches": int(
            values["NUMBER OF PERSONS INJURED"].ne(injury_components).sum()
        ),
        "death_total_mismatches": int(
            values["NUMBER OF PERSONS KILLED"].ne(death_components).sum()
        ),
    }


def write_quality_outputs(
    df: pd.DataFrame,
    output_dir: Path,
    geo_config: GeoConfig,
) -> dict[str, float | int]:
    output_dir.mkdir(parents=True, exist_ok=True)
    create_quality_report(df).to_csv(output_dir / "data_quality.csv", index=False)
    valid_coordinates = int(valid_coordinate_mask(df, geo_config).sum())
    summary: dict[str, float | int] = {
        "rows": int(len(df)),
        "valid_coordinate_rows": valid_coordinates,
        "coordinate_coverage_pct": round(valid_coordinates / len(df) * 100, 3),
    }
    summary.update(validate_collision_ids(df))
    summary.update(validate_casualty_totals(df))
    return summary

