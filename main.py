"""Command-line entry point for the NYC crash DBSCAN project."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from src.clustering import (
    aggregate_locations,
    calculate_k_distances,
    coordinates_to_radians,
    run_parameter_grid,
)
from src.config import ProjectConfig, load_config
from src.data_processing import (
    filter_valid_coordinates,
    load_crash_data,
    write_quality_outputs,
)
from src.feature_engineering import build_features
from src.geojson_export import export_browser_bundle, export_period_geojson
from src.pipeline import run_hotspot_pipeline
from src.profiling import rank_clusters_by_frequency, rank_clusters_by_severity
from src.visualization import (
    create_comparison_hotspot_map,
    create_hotspot_map,
    plot_k_distance,
    plot_top_clusters,
)


def _prepare_output_dirs(config: ProjectConfig) -> dict[str, Path]:
    paths = {
        "tables": config.output_root / "tables",
        "figures": config.output_root / "figures",
        "maps": config.output_root / "maps",
        "experiments": config.output_root / "experiment_results",
    }
    for path in paths.values():
        path.mkdir(parents=True, exist_ok=True)
    return paths


def prepare_dataset(
    config: ProjectConfig,
    force_refresh: bool,
    sample_rows: int | None,
) -> tuple[pd.DataFrame, dict[str, float | int]]:
    raw = load_crash_data(config.data, force_refresh=force_refresh)
    if sample_rows is not None:
        raw = raw.sample(n=min(sample_rows, len(raw)), random_state=42).copy()
    output_dirs = _prepare_output_dirs(config)
    quality_summary = write_quality_outputs(raw, output_dirs["tables"], config.geo)
    clean = filter_valid_coordinates(raw, config.geo)
    featured = build_features(
        clean,
        periods=config.analysis.periods,
        coordinate_precision=config.geo.coordinate_precision,
    )
    return featured, quality_summary


def run_command(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    outputs = _prepare_output_dirs(config)
    data, quality = prepare_dataset(config, args.force_refresh, args.sample_rows)
    run_summary: dict[str, object] = {"quality": quality, "periods": {}}
    period_profiles: dict[str, pd.DataFrame] = {}

    for period in config.analysis.periods:
        result = run_hotspot_pipeline(
            crash_df=data,
            period=period.name,
            eps_m=config.dbscan.eps_m,
            min_samples=config.dbscan.min_samples,
        )
        safe_period = period.name.replace("–", "_").replace("-", "_")
        result.locations.to_parquet(
            outputs["tables"] / f"locations_{safe_period}.parquet", index=False
        )
        result.profile.to_csv(
            outputs["tables"] / f"cluster_profile_{safe_period}.csv", index=False
        )
        rank_clusters_by_frequency(
            result.profile, config.analysis.top_clusters
        ).to_csv(outputs["tables"] / f"top_frequency_{safe_period}.csv", index=False)
        rank_clusters_by_severity(
            result.profile,
            n=config.analysis.top_clusters,
            minimum_crashes=config.analysis.minimum_crashes_for_severity_ranking,
        ).to_csv(outputs["tables"] / f"top_severity_{safe_period}.csv", index=False)
        plot_top_clusters(
            result.profile,
            period.name,
            outputs["figures"] / f"top_clusters_{safe_period}.png",
            top_n=config.analysis.top_clusters,
        )
        create_hotspot_map(
            result.profile,
            period.name,
            outputs["maps"] / f"hotspots_{safe_period}.html",
            top_n=50,
        )
        geojson_path = export_period_geojson(
            crash_df=data[data["period"].eq(period.name)],
            location_df=result.locations,
            profile=result.profile,
            period=period.name,
            data_dir=config.project_root / "web" / "data",
        )
        print(f"Leaflet data: {geojson_path}")
        period_profiles[period.name] = result.profile
        run_summary["periods"][period.name] = result.metrics
        print(f"{period.name}: {json.dumps(result.metrics, ensure_ascii=False)}")

    create_comparison_hotspot_map(
        period_profiles,
        outputs["maps"] / "hotspots_period_comparison.html",
        top_n=50,
    )
    bundle_path = export_browser_bundle(
        config.project_root / "web" / "data",
        [period.name for period in config.analysis.periods],
    )
    print(f"Leaflet browser bundle: {bundle_path}")

    summary_path = outputs["experiments"] / "latest_run.json"
    summary_path.write_text(
        json.dumps(run_summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"Saved run summary to {summary_path}")


def tune_command(args: argparse.Namespace) -> None:
    config = load_config(args.config)
    outputs = _prepare_output_dirs(config)
    data, _ = prepare_dataset(config, args.force_refresh, None)
    period_df = data[data["period"].eq(args.period)]
    if period_df.empty:
        raise ValueError(f"Unknown or empty period: {args.period}")
    locations = aggregate_locations(period_df)
    if args.sample_locations and len(locations) > args.sample_locations:
        locations = locations.sample(args.sample_locations, random_state=42).copy()

    coordinates = coordinates_to_radians(locations)
    k_distances = calculate_k_distances(coordinates, config.dbscan.min_samples)
    safe_period = args.period.replace("–", "_").replace("-", "_")
    plot_k_distance(
        k_distances,
        config.dbscan.min_samples,
        outputs["figures"] / f"k_distance_{safe_period}.png",
    )
    tuning = run_parameter_grid(
        locations,
        config.dbscan.eps_grid_m,
        config.dbscan.min_samples_grid,
    )
    path = outputs["tables"] / f"dbscan_tuning_{safe_period}.csv"
    tuning.to_csv(path, index=False)
    print(tuning.to_string(index=False))
    print(f"Saved tuning results to {path}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="NYC crash DBSCAN hotspot pipeline")
    parser.add_argument("--config", default="config.yaml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the configured pipeline")
    run_parser.add_argument("--force-refresh", action="store_true")
    run_parser.add_argument("--sample-rows", type=int)
    run_parser.set_defaults(handler=run_command)

    tune_parser = subparsers.add_parser("tune", help="Run a DBSCAN parameter grid")
    tune_parser.add_argument("--period", default="2017-2019")
    tune_parser.add_argument("--sample-locations", type=int, default=30000)
    tune_parser.add_argument("--force-refresh", action="store_true")
    tune_parser.set_defaults(handler=tune_command)
    return parser


if __name__ == "__main__":
    arguments = build_parser().parse_args()
    arguments.handler(arguments)

