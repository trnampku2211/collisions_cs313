"""Export DBSCAN hotspots and selected member locations for the Leaflet map."""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.profiling import attach_cluster_labels


def _name(value: object) -> str | None:
    if pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def _street_descriptors(
    crash_df: pd.DataFrame,
    location_df: pd.DataFrame,
) -> dict[int, dict[str, str | float | None]]:
    events = attach_cluster_labels(crash_df, location_df)
    events = events[events["cluster"].ge(0)].copy()
    events["street"] = events["ON STREET NAME"].map(_name)
    events["cross_street"] = events["CROSS STREET NAME"].map(_name)
    events["off_street"] = events["OFF STREET NAME"].map(_name)
    events["street"] = events["street"].fillna(events["off_street"])

    street_counts = (
        events.dropna(subset=["street"])
        .groupby(["cluster", "street"], dropna=False)
        .size()
        .rename("count")
        .reset_index()
        .sort_values(["cluster", "count", "street"], ascending=[True, False, True])
        .drop_duplicates("cluster")
    )
    pair_counts = (
        events.dropna(subset=["street", "cross_street"])
        .groupby(["cluster", "street", "cross_street"], dropna=False)
        .size()
        .rename("count")
        .reset_index()
        .sort_values(
            ["cluster", "count", "street", "cross_street"],
            ascending=[True, False, True, True],
        )
        .drop_duplicates("cluster")
    )
    totals = events.groupby("cluster").size().to_dict()
    descriptors: dict[int, dict[str, str | float | None]] = {}
    for row in street_counts.itertuples(index=False):
        descriptors[int(row.cluster)] = {
            "top_street": str(row.street),
            "top_street_share_pct": round(int(row.count) / totals[row.cluster] * 100, 2),
            "top_intersection": None,
        }
    for row in pair_counts.itertuples(index=False):
        descriptor = descriptors.setdefault(
            int(row.cluster),
            {"top_street": None, "top_street_share_pct": None},
        )
        descriptor["top_intersection"] = f"{row.street} & {row.cross_street}"
        descriptor["top_intersection_share_pct"] = round(
            int(row.count) / totals[row.cluster] * 100, 2
        )
    return descriptors


def _representative_coords(
    location_df: pd.DataFrame,
    profile: pd.DataFrame,
) -> dict[int, tuple[float, float]]:
    """Choose an observed crash location closest to each cluster's center."""
    centers = profile[["cluster", "center_lat", "center_lon"]]
    points = location_df[location_df["cluster"].ge(0)].merge(
        centers, on="cluster", how="inner", validate="many_to_one"
    )
    points["distance_sq"] = (
        (points["lat_round"] - points["center_lat"]) ** 2
        + ((points["lon_round"] - points["center_lon"]) * 0.75) ** 2
    )
    closest = points.sort_values(
        ["cluster", "distance_sq", "crash_count"],
        ascending=[True, True, False],
    ).drop_duplicates("cluster")
    return {
        int(row.cluster): (float(row.lon_round), float(row.lat_round))
        for row in closest.itertuples(index=False)
    }


def _write_geojson(path: Path, features: list[dict], **metadata: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    collection = {"type": "FeatureCollection", **metadata, "features": features}
    path.write_text(
        json.dumps(collection, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )


def export_period_geojson(
    crash_df: pd.DataFrame,
    location_df: pd.DataFrame,
    profile: pd.DataFrame,
    period: str,
    data_dir: Path,
    detail_clusters: int = 20,
    detail_max_locations: int = 1500,
) -> Path:
    """Export all cluster centers and sampled member locations for top clusters."""
    safe_period = period.replace("–", "_").replace("-", "_")
    descriptors = _street_descriptors(crash_df, location_df)
    marker_coords = _representative_coords(location_df, profile)
    detail_ids = set(profile.nlargest(detail_clusters, "crashes")["cluster"].astype(int))
    features: list[dict] = []
    for row in profile.itertuples(index=False):
        cluster_id = int(row.cluster)
        detail_file = (
            f"details/{safe_period}_{cluster_id}.geojson"
            if cluster_id in detail_ids
            else None
        )
        properties = {
            "cluster_id": cluster_id,
            "period": period,
            "crashes": int(row.crashes),
            "injured": int(row.injured),
            "killed": int(row.killed),
            "locations": int(row.locations),
            "injury_crashes": int(row.injury_crashes),
            "fatal_crashes": int(row.fatal_crashes),
            "vulnerable_crashes": int(row.vulnerable_crashes),
            "injured_per_100_crashes": round(float(row.injured_per_100_crashes), 2),
            "killed_per_100k_crashes": round(float(row.killed_per_100k_crashes), 2),
            "vulnerable_crash_pct": round(float(row.vulnerable_crash_pct), 2),
            "top_street": descriptors.get(cluster_id, {}).get("top_street"),
            "top_street_share_pct": descriptors.get(cluster_id, {}).get(
                "top_street_share_pct"
            ),
            "top_intersection": descriptors.get(cluster_id, {}).get(
                "top_intersection"
            ),
            "top_intersection_share_pct": descriptors.get(cluster_id, {}).get(
                "top_intersection_share_pct"
            ),
            "detail_file": detail_file,
        }
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": marker_coords[cluster_id],
                },
                "properties": properties,
            }
        )

    path = data_dir / f"hotspots_{safe_period}.geojson"
    _write_geojson(
        path,
        features,
        period=period,
        marker_represents="observed crash location nearest geometric center",
    )

    noise_locations = location_df[location_df["cluster"].eq(-1)]
    noise_features = [
        {
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [float(row.lon_round), float(row.lat_round)],
            },
            "properties": {
                "crashes": int(row.crash_count),
                "injured": int(row.injured),
                "killed": int(row.killed),
            },
        }
        for row in noise_locations.itertuples(index=False)
    ]
    _write_geojson(
        data_dir / f"noise_{safe_period}.geojson",
        noise_features,
        period=period,
        total_locations=len(noise_features),
        total_crashes=int(noise_locations["crash_count"].sum()),
    )

    detail_locations = location_df[location_df["cluster"].isin(detail_ids)]
    for cluster_id, group in detail_locations.groupby("cluster"):
        group = group.nlargest(detail_max_locations, "crash_count")
        all_locations = int((location_df["cluster"] == cluster_id).sum())
        detail_features = [
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [float(row.lon_round), float(row.lat_round)],
                },
                "properties": {
                    "crashes": int(row.crash_count),
                    "injured": int(row.injured),
                    "killed": int(row.killed),
                },
            }
            for row in group.itertuples(index=False)
        ]
        _write_geojson(
            data_dir / "details" / f"{safe_period}_{int(cluster_id)}.geojson",
            detail_features,
            period=period,
            cluster_id=int(cluster_id),
            total_locations=all_locations,
            shown_locations=len(detail_features),
            truncated=all_locations > len(detail_features),
        )
    return path


def export_browser_bundle(data_dir: Path, periods: list[str]) -> Path:
    """Package GeoJSON for browsers that open index.html via file://."""
    period_data: dict[str, dict] = {}
    details: dict[str, dict] = {}
    noise_data: dict[str, dict] = {}
    for period in periods:
        safe_period = period.replace("–", "_").replace("-", "_")
        path = data_dir / f"hotspots_{safe_period}.geojson"
        collection = json.loads(path.read_text(encoding="utf-8"))
        period_data[period] = collection
        for feature in collection["features"]:
            detail_file = feature["properties"].get("detail_file")
            if detail_file and detail_file not in details:
                details[detail_file] = json.loads(
                    (data_dir / detail_file).read_text(encoding="utf-8")
                )
        noise_path = data_dir / f"noise_{safe_period}.geojson"
        noise_collection = json.loads(noise_path.read_text(encoding="utf-8"))
        noise_data[period] = {
            "total_locations": int(noise_collection["total_locations"]),
            "total_crashes": int(noise_collection["total_crashes"]),
            "points": [
                [
                    *feature["geometry"]["coordinates"],
                    feature["properties"]["crashes"],
                    feature["properties"]["injured"],
                    feature["properties"]["killed"],
                ]
                for feature in noise_collection["features"]
            ],
        }
    bundle_path = data_dir / "bundle.js"
    bundle_path.write_text(
        "window.NYC_HOTSPOT_DATA="
        + json.dumps(period_data, ensure_ascii=False, separators=(",", ":"))
        + ";\nwindow.NYC_HOTSPOT_DETAILS="
        + json.dumps(details, ensure_ascii=False, separators=(",", ":"))
        + ";\nwindow.NYC_HOTSPOT_NOISE="
        + json.dumps(noise_data, ensure_ascii=False, separators=(",", ":"))
        + ";\n",
        encoding="utf-8",
    )
    return bundle_path
