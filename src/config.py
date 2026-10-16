"""Configuration models and YAML loader."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


EARTH_RADIUS_M = 6_371_000.0


@dataclass(frozen=True)
class DataConfig:
    input_path: Path
    cache_path: Path
    start_date: str
    end_date: str
    chunksize: int


@dataclass(frozen=True)
class GeoConfig:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    coordinate_precision: int


@dataclass(frozen=True)
class DBSCANConfig:
    eps_m: float
    min_samples: int
    eps_grid_m: tuple[float, ...]
    min_samples_grid: tuple[int, ...]


@dataclass(frozen=True)
class PeriodConfig:
    name: str
    start_year: int
    end_year: int


@dataclass(frozen=True)
class AnalysisConfig:
    periods: tuple[PeriodConfig, ...]
    minimum_crashes_for_severity_ranking: int
    top_clusters: int


@dataclass(frozen=True)
class ProjectConfig:
    project_root: Path
    data: DataConfig
    geo: GeoConfig
    dbscan: DBSCANConfig
    analysis: AnalysisConfig
    output_root: Path


def _resolve(root: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (root / path).resolve()


def load_config(config_path: str | Path = "config.yaml") -> ProjectConfig:
    path = Path(config_path).resolve()
    with path.open("r", encoding="utf-8") as stream:
        raw: dict[str, Any] = yaml.safe_load(stream)

    root = path.parent
    data_raw = raw["data"]
    geo_raw = raw["geospatial"]
    dbscan_raw = raw["dbscan"]
    analysis_raw = raw["analysis"]

    periods = tuple(
        PeriodConfig(
            name=str(item["name"]),
            start_year=int(item["start_year"]),
            end_year=int(item["end_year"]),
        )
        for item in analysis_raw["periods"]
    )

    return ProjectConfig(
        project_root=root,
        data=DataConfig(
            input_path=_resolve(root, data_raw["input_path"]),
            cache_path=_resolve(root, data_raw["cache_path"]),
            start_date=str(data_raw["start_date"]),
            end_date=str(data_raw["end_date"]),
            chunksize=int(data_raw["chunksize"]),
        ),
        geo=GeoConfig(
            min_lat=float(geo_raw["min_lat"]),
            max_lat=float(geo_raw["max_lat"]),
            min_lon=float(geo_raw["min_lon"]),
            max_lon=float(geo_raw["max_lon"]),
            coordinate_precision=int(geo_raw["coordinate_precision"]),
        ),
        dbscan=DBSCANConfig(
            eps_m=float(dbscan_raw["eps_m"]),
            min_samples=int(dbscan_raw["min_samples"]),
            eps_grid_m=tuple(float(x) for x in dbscan_raw["eps_grid_m"]),
            min_samples_grid=tuple(int(x) for x in dbscan_raw["min_samples_grid"]),
        ),
        analysis=AnalysisConfig(
            periods=periods,
            minimum_crashes_for_severity_ranking=int(
                analysis_raw["minimum_crashes_for_severity_ranking"]
            ),
            top_clusters=int(analysis_raw["top_clusters"]),
        ),
        output_root=_resolve(root, raw["output"]["root"]),
    )

