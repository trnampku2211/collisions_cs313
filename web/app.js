"use strict";

const DATA_FILES = [
  { period: "2017-2019", file: "data/hotspots_2017_2019.geojson", color: "#2166ac", toggle: "period-before" },
  { period: "2020-2022", file: "data/hotspots_2020_2022.geojson", color: "#b2182b", toggle: "period-after" },
];

// Bright subset derived from Colorcet's glasbey_light palette. Near-black,
// brown, and muddy olive entries are intentionally excluded for this basemap.
const GLASBEY_20 = [
  "#d70000", "#b600ff", "#06acc6", "#98ff00", "#ffa530",
  "#ff8fc8", "#00fecf", "#b0a5ff", "#d3008c", "#fef590",
  "#9fe3ff", "#00c946", "#ff28fd", "#00a07d", "#ff6200",
  "#ff3465", "#a0e492", "#72b9ff", "#e58fff", "#00d494",
];

const map = L.map("map", { preferCanvas: true, zoomControl: false }).setView([40.7128, -74.0060], 11);
L.control.zoom({ position: "topright" }).addTo(map);
L.control.scale({ imperial: false, position: "bottomright" }).addTo(map);
L.maplibreGL({ style: "https://tiles.openfreemap.org/styles/positron" }).addTo(map);
map.attributionControl.addAttribution(
  '<a href="https://openfreemap.org/">OpenFreeMap</a> · <a href="https://openmaptiles.org/">© OpenMapTiles</a> · Data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
);

const ui = {
  colorModes: [...document.querySelectorAll('input[name="color-mode"]')],
  colorModeNote: document.getElementById("color-mode-note"),
  periodLegend: document.getElementById("period-legend"),
  minCrashes: document.getElementById("min-crashes"),
  sortMetric: document.getElementById("sort-metric"),
  displayLimit: document.getElementById("display-limit"),
  fatalOnly: document.getElementById("fatal-only"),
  resultCount: document.getElementById("result-count"),
  clusterList: document.getElementById("cluster-list"),
  loading: document.getElementById("loading-state"),
  error: document.getElementById("error-state"),
  detailNote: document.getElementById("detail-note"),
  summaryNote: document.getElementById("summary-note"),
  mapCaption: document.getElementById("map-caption"),
};

const periodData = new Map();
const periodLayers = new Map();
const markerLookup = new Map();
const clusterPaletteLookup = new Map();
let detailLayer = null;
let selectedKey = null;
const DETAIL_ZOOM = 14;

function colorMode() {
  return document.querySelector('input[name="color-mode"]:checked')?.value ?? "period";
}

function mixHex(hex, target, amount) {
  const source = hex.match(/[a-f\d]{2}/gi).map((part) => parseInt(part, 16));
  const mixed = source.map((channel, index) => Math.round(channel + (target[index] - channel) * amount));
  return `#${mixed.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;
}

function clusterColors(period, clusterId) {
  const key = `${period}:${clusterId}`;
  const fallback = Math.abs(Number(clusterId) || 0) % GLASBEY_20.length;
  const base = GLASBEY_20[clusterPaletteLookup.get(key) ?? fallback];
  return {
    stroke: mixHex(base, [18, 30, 42], 0.2),
    fill: mixHex(base, [255, 255, 255], 0.5),
  };
}

function assignClusterPalette() {
  clusterPaletteLookup.clear();
  for (const config of DATA_FILES) {
    const detailed = [...(periodData.get(config.period)?.features ?? [])]
      .filter((feature) => bundledDetail(feature))
      .sort((a, b) => b.properties.crashes - a.properties.crashes);
    detailed.forEach((feature, index) => {
      clusterPaletteLookup.set(`${config.period}:${feature.properties.cluster_id}`, index % GLASBEY_20.length);
    });
  }
}

function featureColor(feature) {
  if (colorMode() === "cluster") {
    return clusterColors(feature.properties.period, feature.properties.cluster_id).stroke;
  }
  return DATA_FILES.find((config) => config.period === feature.properties.period)?.color ?? "#5a6b7c";
}

function enforceSingleClusterPeriod(changedToggle = null) {
  if (colorMode() !== "cluster") return;
  const checked = DATA_FILES.filter((config) => document.getElementById(config.toggle).checked);
  if (!checked.length) {
    document.getElementById(changedToggle === "period-before" ? "period-after" : "period-before").checked = true;
    return;
  }
  if (checked.length > 1) {
    const keep = changedToggle ?? checked[0].toggle;
    for (const config of checked) document.getElementById(config.toggle).checked = config.toggle === keep;
  }
}

function updateModeGuidance() {
  const clusterMode = colorMode() === "cluster";
  ui.periodLegend.textContent = clusterMode ? "Giai đoạn (chọn một)" : "Giai đoạn";
  ui.colorModeNote.textContent = clusterMode
    ? "Các chấm cùng màu là những vị trí thuộc cùng một cụm DBSCAN."
    : "Màu xanh và đỏ phân biệt hai giai đoạn phân tích.";
  ui.summaryNote.textContent = clusterMode
    ? "Vòng có viền đậm đánh dấu điểm đại diện. Phóng to mức 14 để xem mẫu vị trí của 20 cụm nhiều vụ nhất."
    : "Vòng tròn đặt tại tọa độ va chạm gần tâm cụm nhất. Bấm một cụm và phóng to mức 14 để xem các vị trí tai nạn.";
  ui.mapCaption.innerHTML = clusterMode
    ? '<span class="cluster-spectrum"></span><strong>Cùng màu = cùng cụm</strong><span class="caption-hint">Ruột nhạt + viền đậm · vòng lớn = tâm đại diện</span>'
    : '<span class="caption-dot caption-blue"></span> 2017–2019 <span class="caption-dot caption-red"></span> 2020–2022 <span class="caption-hint">Kích thước vòng tròn ∝ căn bậc hai số vụ</span>';
}

function bundledDetail(feature) {
  const path = feature.properties.detail_file;
  return path ? window.NYC_HOTSPOT_DETAILS?.[path] ?? null : null;
}

function sampleMemberLocations(geojson, maxPoints = 600) {
  const features = geojson?.features ?? [];
  if (features.length <= maxPoints) return features;
  const step = features.length / maxPoints;
  return Array.from({ length: maxPoints }, (_, index) => features[Math.floor(index * step)]);
}

function formatNumber(value, digits = 0) {
  return Number(value).toLocaleString("vi-VN", { maximumFractionDigits: digits });
}

function safeText(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function featureLabel(properties) {
  return properties.top_street && properties.top_street_share_pct >= 10
    ? properties.top_street
    : `Cụm ${properties.cluster_id} · nhiều tuyến đường`;
}

function percentile(values, fraction) {
  if (!values.length) return 0;
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.min(sorted.length - 1, Math.floor(fraction * sorted.length))];
}

function riskLevel(properties) {
  const features = periodData.get(properties.period)?.features ?? [];
  const crashCounts = features.map((feature) => Number(feature.properties.crashes) || 0);
  const median = percentile(crashCounts, 0.5);
  const highThreshold = percentile(crashCounts, 0.8);
  if (properties.crashes >= highThreshold) return { label: "Nguy cơ cao", className: "risk-high" };
  if (properties.crashes >= median) return { label: "Trung bình", className: "risk-medium" };
  return { label: "Thấp", className: "risk-low" };
}

function popupContent(feature) {
  const properties = feature.properties;
  const [longitude, latitude] = feature.geometry.coordinates;
  const risk = riskLevel(properties);
  const street = properties.top_street
    ? `<div class="popup-location"><span>Khu vực đại diện</span><strong>${safeText(properties.top_street)}</strong><small>Được ghi nhận trong ${formatNumber(properties.top_street_share_pct, 1)}% số vụ</small></div>`
    : `<div class="popup-location"><span>Khu vực đại diện</span><strong>Nhiều tuyến đường</strong></div>`;
  const intersection = properties.top_intersection && properties.top_intersection_share_pct >= 5
    ? `<div class="popup-intersection">Giao lộ thường gặp: ${safeText(properties.top_intersection)}</div>`
    : "";
  return `
    <div class="popup-title">Cụm ${properties.cluster_id} · ${safeText(properties.period)}</div>
    ${street}${intersection}
    <div class="popup-row popup-risk"><span>Mức độ</span><strong class="risk-badge ${risk.className}" title="Phân loại theo số vụ so với các cụm trong cùng giai đoạn">${risk.label}</strong></div>
    <div class="popup-row"><span>Số vụ</span><strong>${formatNumber(properties.crashes)}</strong></div>
    <div class="popup-row"><span>Số vị trí</span><strong>${formatNumber(properties.locations)}</strong></div>
    <div class="popup-row"><span>Vụ có người bị thương</span><strong>${formatNumber(properties.injury_crashes)}</strong></div>
    <div class="popup-row"><span>Vụ có tử vong</span><strong>${formatNumber(properties.fatal_crashes)}</strong></div>
    <div class="popup-row"><span>Người bị thương</span><strong>${formatNumber(properties.injured)}</strong></div>
    <div class="popup-row"><span>Người tử vong</span><strong>${formatNumber(properties.killed)}</strong></div>
    <div class="popup-row"><span>Bị thương / 100 vụ</span><strong>${formatNumber(properties.injured_per_100_crashes, 1)}</strong></div>
    <div class="popup-row"><span>Vụ có người bị thương (%)</span><strong>${formatNumber(properties.injury_crashes / properties.crashes * 100, 1)}%</strong></div>
    <div class="popup-row"><span>Vụ có tử vong (%)</span><strong>${formatNumber(properties.fatal_crashes / properties.crashes * 100, 2)}%</strong></div>
    <div class="popup-row"><span>Vụ liên quan pedestrian/cyclist</span><strong>${formatNumber(properties.vulnerable_crash_pct, 1)}%</strong></div>
    <div class="popup-technical">
      <span>Tọa độ điểm đại diện</span>
      <code>${Number(latitude).toFixed(5)}, ${Number(longitude).toFixed(5)}</code>
    </div>
    <div class="popup-note">Mức độ được xác định theo số vụ trong cùng giai đoạn. Marker là tọa độ va chạm gần tâm cụm nhất, không phải địa chỉ của toàn cụm.</div>
  `;
}

function clusterTooltip(feature) {
  const p = feature.properties;
  return `<strong>${safeText(featureLabel(p))}</strong><br>
    Cluster ${p.cluster_id} · ${safeText(p.period)}<br>
    ${formatNumber(p.crashes)} vụ · ${formatNumber(p.injured)} bị thương · ${formatNumber(p.killed)} tử vong<br>
    Vụ có người bị thương: ${formatNumber(p.injury_crashes / p.crashes * 100, 1)}%<br>
    Vụ có tử vong: ${formatNumber(p.fatal_crashes / p.crashes * 100, 2)}%`;
}

function clearDetail() {
  if (detailLayer) map.removeLayer(detailLayer);
  detailLayer = null;
  selectedKey = null;
  ui.detailNote.hidden = true;
}

async function showDetail(feature) {
  clearDetail();
  const properties = feature.properties;
  const key = `${properties.period}:${properties.cluster_id}`;
  selectedKey = key;
  if (map.getZoom() < DETAIL_ZOOM) {
    ui.detailNote.textContent = `Cụm ${properties.cluster_id}: ${formatNumber(properties.crashes)} vụ. Phóng to mức ${DETAIL_ZOOM} để xem các vị trí chi tiết.`;
    ui.detailNote.hidden = false;
    return;
  }
  if (colorMode() === "cluster") {
    const geojson = bundledDetail(feature);
    const shown = Math.min(geojson?.features?.length ?? 0, 600);
    ui.detailNote.textContent = `Cụm ${properties.cluster_id}: đang hiện ${formatNumber(shown)} vị trí mẫu trên tổng ${formatNumber(geojson?.total_locations ?? properties.locations)} vị trí.`;
    ui.detailNote.hidden = false;
    return;
  }
  if (!properties.detail_file) {
    ui.detailNote.textContent = "Chi tiết từng tọa độ được xuất cho 20 cụm nhiều vụ nhất mỗi giai đoạn.";
    ui.detailNote.hidden = false;
    return;
  }
  try {
    const bundled = window.NYC_HOTSPOT_DETAILS?.[properties.detail_file];
    let geojson = bundled;
    if (!geojson) {
      const response = await fetch(`data/${properties.detail_file}`);
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      geojson = await response.json();
    }
    if (selectedKey !== key || map.getZoom() < DETAIL_ZOOM) return;
    const color = featureColor(feature);
    detailLayer = L.geoJSON(geojson, {
      pointToLayer: (location, latlng) => L.circleMarker(latlng, {
        radius: Math.min(4, 1.5 + Math.sqrt(location.properties.crashes) * 0.25),
        color: "#243746",
        opacity: 0.4,
        weight: 0.4,
        fillColor: color,
        fillOpacity: 0.4,
      }),
      onEachFeature: (location, layer) => {
        const p = location.properties;
        layer.bindTooltip(`${formatNumber(p.crashes)} vụ · ${formatNumber(p.injured)} bị thương · ${formatNumber(p.killed)} tử vong`);
      },
    }).addTo(map);
    markerLookup.get(key)?.bringToFront();
    const count = `${formatNumber(geojson.shown_locations)}/${formatNumber(geojson.total_locations)}`;
    ui.detailNote.textContent = geojson.truncated
      ? `Đang hiện ${count} tọa độ có nhiều vụ nhất trong cụm. Các tọa độ còn lại không hiển thị để giữ bản đồ mượt.`
      : `Đang hiện toàn bộ ${count} tọa độ trong cụm.`;
    ui.detailNote.hidden = false;
  } catch (error) {
    ui.detailNote.textContent = `Không nạp được chi tiết cụm: ${error.message}`;
    ui.detailNote.hidden = false;
  }
}

function visibleFeatures(config) {
  const data = periodData.get(config.period);
  if (!data || !document.getElementById(config.toggle).checked) return [];
  const min = Math.max(0, Number(ui.minCrashes.value) || 0);
  const metric = ui.sortMetric.value;
  const limit = ui.displayLimit.value === "all" ? Infinity : Number(ui.displayLimit.value);
  return data.features
    .filter((feature) => feature.properties.crashes >= min)
    .filter((feature) => !ui.fatalOnly.checked || feature.properties.killed > 0)
    .filter((feature) => colorMode() !== "cluster" || bundledDetail(feature))
    .sort((a, b) => b.properties[metric] - a.properties[metric] || b.properties.crashes - a.properties.crashes)
    .slice(0, limit);
}

function selectFeature(feature) {
  const p = feature.properties;
  map.setView([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], Math.max(map.getZoom(), DETAIL_ZOOM), { animate: false });
  markerLookup.get(`${p.period}:${p.cluster_id}`)?.openPopup();
  showDetail(feature);
}

function renderList(features) {
  ui.clusterList.replaceChildren();
  const metric = ui.sortMetric.value;
  const sorted = [...features].sort((a, b) => b.properties[metric] - a.properties[metric] || b.properties.crashes - a.properties.crashes).slice(0, 10);
  for (const [index, feature] of sorted.entries()) {
    const p = feature.properties;
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "cluster-button";
    const title = document.createElement("span");
    title.className = "cluster-button-title";
    title.textContent = `${index + 1}. ${featureLabel(p)}`;
    const meta = document.createElement("span");
    meta.className = "cluster-button-meta";
    meta.textContent = `${p.period} · Cụm ${p.cluster_id}`;
    const stat = document.createElement("span");
    stat.className = "cluster-button-stat";
    stat.textContent = `${formatNumber(p.crashes)} vụ · ${formatNumber(p.injured)} bị thương · ${formatNumber(p.killed)} tử vong`;
    const risk = riskLevel(p);
    const badge = document.createElement("span");
    badge.className = `risk-badge cluster-risk ${risk.className}`;
    badge.textContent = risk.label;
    badge.title = "Mức độ theo số vụ so với các cụm trong cùng giai đoạn";
    button.append(title, meta, stat, badge);
    button.addEventListener("click", () => selectFeature(feature));
    item.append(button);
    ui.clusterList.append(item);
  }
  if (!sorted.length) {
    const empty = document.createElement("li");
    empty.textContent = "Không có cụm phù hợp với bộ lọc.";
    ui.clusterList.append(empty);
  }
}

function renderComparisonLayer(config, features, maxCount) {
  return L.geoJSON({ type: "FeatureCollection", features }, {
    pointToLayer: (feature, latlng) => {
      const radius = 4 + 10 * Math.sqrt(feature.properties.crashes / maxCount);
      return L.circleMarker(latlng, {
        pane: "markerPane",
        radius,
        color: config.color,
        weight: 2,
        fillColor: config.color,
        fillOpacity: 0.35,
      });
    },
    onEachFeature: (feature, marker) => {
      const p = feature.properties;
      marker.bindPopup(popupContent(feature));
      marker.bindTooltip(clusterTooltip(feature), { className: "cluster-tooltip" });
      marker.on("click", () => showDetail(feature));
      markerLookup.set(`${p.period}:${p.cluster_id}`, marker);
    },
  });
}

function renderClusterMembersLayer(features) {
  const layer = L.layerGroup();
  let shownLocations = 0;
  for (const feature of features) {
    const detail = bundledDetail(feature);
    if (!detail) continue;
    const colors = clusterColors(feature.properties.period, feature.properties.cluster_id);
    const sampled = map.getZoom() >= DETAIL_ZOOM ? sampleMemberLocations(detail) : [];
    shownLocations += sampled.length;
    L.geoJSON({ type: "FeatureCollection", features: sampled }, {
      pointToLayer: (location, latlng) => L.circleMarker(latlng, {
        radius: 1.5 + Math.min(1, Math.sqrt(location.properties.crashes || 1) * 0.12),
        color: colors.stroke,
        opacity: 0.4,
        weight: 0.4,
        fillColor: colors.fill,
        fillOpacity: 0.4,
        interactive: false,
      }),
    }).addTo(layer);

    const p = feature.properties;
    const [longitude, latitude] = feature.geometry.coordinates;
    const center = L.circleMarker([latitude, longitude], {
      pane: "markerPane",
      radius: 6.5,
      color: colors.stroke,
      opacity: 1,
      weight: 2.4,
      fillColor: colors.fill,
      fillOpacity: 0.94,
    });
    center.bindPopup(popupContent(feature));
    center.bindTooltip(clusterTooltip(feature), { className: "cluster-tooltip" });
    center.on("click", () => showDetail(feature));
    center.addTo(layer);
    markerLookup.set(`${p.period}:${p.cluster_id}`, center);
  }
  return { layer, shownLocations };
}

function render(preserveSelection = false) {
  const previousKey = preserveSelection === true ? selectedKey : null;
  updateModeGuidance();
  clearDetail();
  markerLookup.clear();
  const allVisible = [];
  const clusterMode = colorMode() === "cluster";
  let shownLocations = 0;
  const maxCount = Math.max(1, ...DATA_FILES.flatMap((config) => visibleFeatures(config).map((f) => f.properties.crashes)));
  for (const config of DATA_FILES) {
    const oldLayer = periodLayers.get(config.period);
    if (oldLayer) map.removeLayer(oldLayer);
    const features = visibleFeatures(config);
    allVisible.push(...features);
    const rendered = clusterMode
      ? renderClusterMembersLayer(features)
      : { layer: renderComparisonLayer(config, features, maxCount), shownLocations: 0 };
    shownLocations += rendered.shownLocations;
    const layer = rendered.layer.addTo(map);
    periodLayers.set(config.period, layer);
  }
  const crashes = allVisible.reduce((sum, feature) => sum + feature.properties.crashes, 0);
  ui.resultCount.textContent = clusterMode
    ? map.getZoom() < DETAIL_ZOOM
      ? `${formatNumber(allVisible.length)} cụm · phóng to mức ${DETAIL_ZOOM} để xem vị trí mẫu`
      : `${formatNumber(allVisible.length)} cụm · ${formatNumber(shownLocations)} vị trí mẫu được hiển thị`
    : `${formatNumber(allVisible.length)} cụm · ${formatNumber(crashes)} vụ được hiển thị`;
  renderList(allVisible);
  const previousFeature = allVisible.find((feature) => `${feature.properties.period}:${feature.properties.cluster_id}` === previousKey);
  if (previousFeature) {
    markerLookup.get(previousKey)?.openPopup();
    showDetail(previousFeature);
  }
}

async function init() {
  try {
    const results = await Promise.all(DATA_FILES.map(async (config) => {
      const bundled = window.NYC_HOTSPOT_DATA?.[config.period];
      let data = bundled;
      if (!data) {
        const response = await fetch(config.file);
        if (!response.ok) throw new Error(`${config.file}: HTTP ${response.status}`);
        data = await response.json();
      }
      if (data.type !== "FeatureCollection" || !Array.isArray(data.features)) {
        throw new Error(`GeoJSON không hợp lệ: ${config.file}`);
      }
      return [config.period, data];
    }));
    for (const [period, data] of results) periodData.set(period, data);
    assignClusterPalette();
    ui.loading.hidden = true;
    render();
  } catch (error) {
    ui.loading.hidden = true;
    ui.error.textContent = `Không nạp được dữ liệu bản đồ: ${error.message}. Hãy chạy lại python main.py run để tạo web/data/bundle.js.`;
    ui.error.hidden = false;
  }
}

for (const config of DATA_FILES) {
  document.getElementById(config.toggle).addEventListener("change", () => {
    enforceSingleClusterPeriod(config.toggle);
    render();
  });
}
for (const input of ui.colorModes) {
  input.addEventListener("change", () => {
    enforceSingleClusterPeriod();
    render();
  });
}
for (const id of ["sort-metric", "display-limit", "fatal-only"]) {
  document.getElementById(id).addEventListener("change", render);
}
ui.minCrashes.addEventListener("change", render);
let showingMemberLocations = map.getZoom() >= DETAIL_ZOOM;
map.on("zoomend", () => {
  const showMembers = map.getZoom() >= DETAIL_ZOOM;
  if (showMembers !== showingMemberLocations) {
    showingMemberLocations = showMembers;
    render(true);
  }
});
init();
