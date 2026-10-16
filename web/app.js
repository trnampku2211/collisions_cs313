"use strict";

const DATA_FILES = [
  { period: "2017-2019", file: "data/hotspots_2017_2019.geojson", color: "#2166ac", toggle: "period-before" },
  { period: "2020-2022", file: "data/hotspots_2020_2022.geojson", color: "#b2182b", toggle: "period-after" },
];

const map = L.map("map", { preferCanvas: true, zoomControl: false }).setView([40.7128, -74.0060], 11);
L.control.zoom({ position: "topright" }).addTo(map);
L.control.scale({ imperial: false, position: "bottomright" }).addTo(map);
L.maplibreGL({ style: "https://tiles.openfreemap.org/styles/positron" }).addTo(map);
map.attributionControl.addAttribution(
  '<a href="https://openfreemap.org/">OpenFreeMap</a> · <a href="https://openmaptiles.org/">© OpenMapTiles</a> · Data from <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
);

const ui = {
  minCrashes: document.getElementById("min-crashes"),
  sortMetric: document.getElementById("sort-metric"),
  displayLimit: document.getElementById("display-limit"),
  fatalOnly: document.getElementById("fatal-only"),
  resultCount: document.getElementById("result-count"),
  clusterList: document.getElementById("cluster-list"),
  loading: document.getElementById("loading-state"),
  error: document.getElementById("error-state"),
  detailNote: document.getElementById("detail-note"),
};

const periodData = new Map();
const periodLayers = new Map();
const markerLookup = new Map();
let detailLayer = null;
let selectedKey = null;

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

function popupContent(properties) {
  const street = properties.top_street
    ? `<div class="popup-subtitle">Đường được ghi nhiều nhất: ${safeText(properties.top_street)} (${formatNumber(properties.top_street_share_pct, 1)}% số vụ)</div>`
    : `<div class="popup-subtitle">Chưa có tên đường đáng tin cậy</div>`;
  const intersection = properties.top_intersection && properties.top_intersection_share_pct >= 5
    ? `<div class="popup-subtitle">Cặp đường được ghi nhiều nhất: ${safeText(properties.top_intersection)} (${formatNumber(properties.top_intersection_share_pct, 1)}% số vụ)</div>`
    : "";
  return `
    <div class="popup-title">Cụm ${properties.cluster_id} · ${safeText(properties.period)}</div>
    ${street}${intersection}
    <div class="popup-row"><span>Số vụ</span><strong>${formatNumber(properties.crashes)}</strong></div>
    <div class="popup-row"><span>Người bị thương</span><strong>${formatNumber(properties.injured)}</strong></div>
    <div class="popup-row"><span>Người tử vong</span><strong>${formatNumber(properties.killed)}</strong></div>
    <div class="popup-row"><span>Vụ liên quan pedestrian/cyclist</span><strong>${formatNumber(properties.vulnerable_crash_pct, 1)}%</strong></div>
    <div class="popup-note">Marker đặt tại tọa độ va chạm gần tâm cụm nhất. Chọn cụm để xem các tọa độ khác bên trong.</div>
  `;
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
    if (selectedKey !== key) return;
    detailLayer = L.geoJSON(geojson, {
      pointToLayer: (location, latlng) => L.circleMarker(latlng, {
        radius: Math.min(9, 2.5 + Math.sqrt(location.properties.crashes) * 0.75),
        color: "#243746",
        weight: 0.7,
        fillColor: "#f5a623",
        fillOpacity: 0.72,
      }),
      onEachFeature: (location, layer) => {
        const p = location.properties;
        layer.bindTooltip(`${formatNumber(p.crashes)} vụ · ${formatNumber(p.injured)} bị thương · ${formatNumber(p.killed)} tử vong`);
      },
    }).addTo(map);
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
    .sort((a, b) => b.properties[metric] - a.properties[metric] || b.properties.crashes - a.properties.crashes)
    .slice(0, limit);
}

function selectFeature(feature) {
  const p = feature.properties;
  const marker = markerLookup.get(`${p.period}:${p.cluster_id}`);
  map.setView([feature.geometry.coordinates[1], feature.geometry.coordinates[0]], Math.max(map.getZoom(), 14));
  marker?.openPopup();
  showDetail(feature);
}

function renderList(features) {
  ui.clusterList.replaceChildren();
  const metric = ui.sortMetric.value;
  const sorted = [...features].sort((a, b) => b.properties[metric] - a.properties[metric]).slice(0, 12);
  for (const feature of sorted) {
    const p = feature.properties;
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "cluster-button";
    const title = document.createElement("span");
    title.className = "cluster-button-title";
    title.textContent = featureLabel(p);
    const meta = document.createElement("span");
    meta.className = "cluster-button-meta";
    meta.textContent = `${p.period} · Cụm ${p.cluster_id}`;
    const stat = document.createElement("span");
    stat.className = "cluster-button-stat";
    stat.textContent = `${formatNumber(p.crashes)} vụ · ${formatNumber(p.injured)} bị thương · ${formatNumber(p.killed)} tử vong`;
    button.append(title, meta, stat);
    button.addEventListener("click", () => selectFeature(feature));
    item.append(button);
    ui.clusterList.append(item);
  }
}

function render() {
  clearDetail();
  markerLookup.clear();
  const allVisible = [];
  const maxCount = Math.max(1, ...DATA_FILES.flatMap((config) => visibleFeatures(config).map((f) => f.properties.crashes)));
  for (const config of DATA_FILES) {
    const oldLayer = periodLayers.get(config.period);
    if (oldLayer) map.removeLayer(oldLayer);
    const features = visibleFeatures(config);
    allVisible.push(...features);
    const layer = L.geoJSON({ type: "FeatureCollection", features }, {
      pointToLayer: (feature, latlng) => {
        const radius = 4 + 19 * Math.sqrt(feature.properties.crashes / maxCount);
        return L.circleMarker(latlng, {
          radius,
          color: config.color,
          weight: 1.4,
          fillColor: config.color,
          fillOpacity: 0.42,
        });
      },
      onEachFeature: (feature, marker) => {
        const p = feature.properties;
        marker.bindPopup(popupContent(p));
        marker.bindTooltip(`${p.period} · ${featureLabel(p)} · ${formatNumber(p.crashes)} vụ`);
        marker.on("click", () => showDetail(feature));
        markerLookup.set(`${p.period}:${p.cluster_id}`, marker);
      },
    }).addTo(map);
    periodLayers.set(config.period, layer);
  }
  const crashes = allVisible.reduce((sum, feature) => sum + feature.properties.crashes, 0);
  ui.resultCount.textContent = `${formatNumber(allVisible.length)} cụm · ${formatNumber(crashes)} vụ được hiển thị`;
  renderList(allVisible);
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
    ui.loading.hidden = true;
    render();
  } catch (error) {
    ui.loading.hidden = true;
    ui.error.textContent = `Không nạp được dữ liệu bản đồ: ${error.message}. Hãy chạy lại python main.py run để tạo web/data/bundle.js.`;
    ui.error.hidden = false;
  }
}

for (const id of ["period-before", "period-after", "sort-metric", "display-limit", "fatal-only"]) {
  document.getElementById(id).addEventListener("change", render);
}
ui.minCrashes.addEventListener("change", render);
init();
