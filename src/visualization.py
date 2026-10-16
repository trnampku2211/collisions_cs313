"""Static charts and interactive hotspot maps."""

from __future__ import annotations

import os
from pathlib import Path

import folium

os.environ.setdefault("MPLCONFIGDIR", str(Path("outputs/.matplotlib").resolve()))
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd


def plot_k_distance(
    distances_m,
    min_samples: int,
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(distances_m, color="#1f77b4", linewidth=1.2)
    ax.set_title(f"K-distance plot (k={min_samples})")
    ax.set_xlabel("Sorted locations")
    ax.set_ylabel(f"Distance to {min_samples}th neighbor (m)")
    ax.grid(alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def plot_top_clusters(
    profile: pd.DataFrame,
    period: str,
    output_path: Path,
    top_n: int = 20,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    top = profile.nlargest(top_n, "crashes").sort_values("crashes")
    fig, ax = plt.subplots(figsize=(10, 7))
    ax.barh(top["cluster"].astype(str), top["crashes"], color="#1f77b4")
    ax.set_title(f"Top DBSCAN hotspots by crash count — {period}")
    ax.set_xlabel("Crashes")
    ax.set_ylabel("Cluster")
    ax.grid(axis="x", alpha=0.2)
    fig.tight_layout()
    fig.savefig(output_path, dpi=160)
    plt.close(fig)


def create_hotspot_map(
    profile: pd.DataFrame,
    period: str,
    output_path: Path,
    top_n: int = 50,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    center = [40.7128, -74.0060]
    hotspot_map = folium.Map(location=center, zoom_start=11, tiles="OpenStreetMap")
    top = profile.nlargest(top_n, "crashes")
    max_crashes = max(float(top["crashes"].max()), 1.0) if not top.empty else 1.0
    for row in top.itertuples(index=False):
        radius = 5 + 18 * float(row.crashes) / max_crashes
        popup = (
            f"<b>{period} — Cluster {row.cluster}</b><br>"
            f"Crashes: {int(row.crashes):,}<br>"
            f"Injured: {int(row.injured):,}<br>"
            f"Killed: {int(row.killed):,}<br>"
            f"Injury crashes: {float(row.injury_crash_pct):.1f}%<br>"
            f"Vulnerable-user crashes: {float(row.vulnerable_crash_pct):.1f}%"
        )
        folium.CircleMarker(
            location=[float(row.center_lat), float(row.center_lon)],
            radius=radius,
            tooltip=f"Cluster {row.cluster}: {int(row.crashes):,} crashes",
            popup=folium.Popup(popup, max_width=320),
            color="#8b1e1e",
            weight=1,
            fill=True,
            fill_color="#d7301f",
            fill_opacity=0.55,
        ).add_to(hotspot_map)
    hotspot_map.save(str(output_path))


def create_comparison_hotspot_map(
    profiles: dict[str, pd.DataFrame],
    output_path: Path,
    top_n: int = 50,
) -> None:
    """Create one map with toggleable layers for multiple analysis periods."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    hotspot_map = folium.Map(
        location=[40.7128, -74.0060],
        zoom_start=11,
        tiles="OpenStreetMap",
        control_scale=True,
    )
    colors = ["#2166ac", "#b2182b", "#1b7837", "#762a83"]
    selected = {
        period: profile.nlargest(top_n, "crashes").copy()
        for period, profile in profiles.items()
    }
    global_max = max(
        (
            float(frame["crashes"].max())
            for frame in selected.values()
            if not frame.empty
        ),
        default=1.0,
    )

    legend_rows: list[str] = []
    for index, (period, frame) in enumerate(selected.items()):
        color = colors[index % len(colors)]
        layer = folium.FeatureGroup(name=f"Hotspots {period}", show=True)
        for row in frame.itertuples(index=False):
            radius = 5 + 20 * (float(row.crashes) / global_max) ** 0.5
            popup = (
                f"<b>{period} — Cluster {row.cluster}</b><br>"
                f"Crashes: {int(row.crashes):,}<br>"
                f"Injured: {int(row.injured):,}<br>"
                f"Killed: {int(row.killed):,}<br>"
                f"Injured per 100 crashes: "
                f"{float(row.injured_per_100_crashes):.1f}<br>"
                f"Killed per 100,000 crashes: "
                f"{float(row.killed_per_100k_crashes):.1f}"
            )
            folium.CircleMarker(
                location=[float(row.center_lat), float(row.center_lon)],
                radius=radius,
                tooltip=f"{period} · Cluster {row.cluster} · {int(row.crashes):,} crashes",
                popup=folium.Popup(popup, max_width=340),
                color=color,
                weight=2,
                fill=True,
                fill_color=color,
                fill_opacity=0.45,
            ).add_to(layer)
        layer.add_to(hotspot_map)
        legend_rows.append(
            f'<div><span style="display:inline-block;width:12px;height:12px;'
            f'background:{color};border-radius:50%;margin-right:6px"></span>{period}</div>'
        )

    legend_html = (
        '<div style="position:fixed;bottom:24px;left:24px;z-index:9999;'
        'background:white;padding:10px 12px;border:1px solid #999;'
        'font:13px Arial;line-height:1.6">'
        '<b>DBSCAN hotspots</b>'
        + "".join(legend_rows)
        + '<div style="margin-top:4px">Circle size = crash count</div></div>'
    )
    hotspot_map.get_root().html.add_child(folium.Element(legend_html))
    folium.LayerControl(collapsed=False).add_to(hotspot_map)
    hotspot_map.save(str(output_path))

