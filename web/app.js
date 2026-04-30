const state = { wifiChart: null, qualityChart: null, map: null, markers: [] };

const fmt = (value, suffix = "") => value === null || value === undefined ? "-" : `${value}${suffix}`;
const timeLabel = (ts) => new Date(ts).toLocaleTimeString();
const colorForRtt = (rtt) => rtt == null ? "#64748b" : rtt < 30 ? "#16a34a" : rtt < 100 ? "#ca8a04" : "#dc2626";

async function json(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url}: ${response.status}`);
  return response.json();
}

function setText(id, value) {
  document.getElementById(id).textContent = value;
}

async function loadSnapshot() {
  const data = await json("/api/snapshot");
  const wifi = data.wifi || {};
  const wan = data.wan || {};
  const lan = data.lan || {};
  const quality = data.quality || {};

  setText("public-ip", wan.public_ip || "-");
  setText("isp", wan.org || wan.asn || "-");
  setText("wifi-now", wifi.ssid ? `${wifi.ssid} ${fmt(wifi.rssi_dbm, " dBm")}` : "-");
  setText("gw-rtt", fmt(lan.gw_rtt_avg_ms?.toFixed?.(1) ?? lan.gw_rtt_avg_ms, " ms"));
  setText("quality-now", quality.dl_mbps ? `${quality.dl_mbps} / ${quality.ul_mbps} Mbps` : fmt(quality.ping_avg_ms?.toFixed?.(1), " ms ping"));
  setText("status-line", `local ${wifi.local_ip || "-"} via ${lan.gateway_ip || "-"} / updated ${wifi.ts ? timeLabel(wifi.ts) : "-"}`);
}

function lineChart(canvasId, labels, datasets) {
  const existing = canvasId === "wifi-chart" ? state.wifiChart : state.qualityChart;
  if (existing) existing.destroy();
  const chart = new Chart(document.getElementById(canvasId), {
    type: "line",
    data: { labels, datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: { y: { beginAtZero: false } },
      plugins: { legend: { position: "bottom" } }
    }
  });
  if (canvasId === "wifi-chart") state.wifiChart = chart;
  else state.qualityChart = chart;
}

async function loadWifi() {
  const rows = await json("/api/wifi?since=1h");
  lineChart("wifi-chart", rows.map((r) => timeLabel(r.ts)), [
    { label: "RSSI dBm", data: rows.map((r) => r.rssi_dbm), borderColor: "#0d9488", tension: 0.25 },
    { label: "SNR dB", data: rows.map((r) => r.snr_db), borderColor: "#f59e0b", tension: 0.25 }
  ]);
}

async function loadQuality() {
  const rows = await json("/api/quality?since=24h");
  lineChart("quality-chart", rows.map((r) => timeLabel(r.ts)), [
    { label: "DL Mbps", data: rows.map((r) => r.dl_mbps), borderColor: "#2563eb", tension: 0.25 },
    { label: "UL Mbps", data: rows.map((r) => r.ul_mbps), borderColor: "#7c3aed", tension: 0.25 },
    { label: "Ping jitter ms", data: rows.map((r) => r.ping_jitter_ms), borderColor: "#dc2626", tension: 0.25 }
  ]);
}

function drawTree(trace) {
  const target = document.getElementById("trace-tree");
  target.innerHTML = "";
  const width = Math.max(target.clientWidth, 760);
  const height = 240;
  const root = d3.hierarchy({
    name: "自機",
    children: [{ name: "GW", children: (trace?.hops || []).map((h) => ({ name: h.ip || `hop ${h.hop_no}`, rtt: h.rtt_ms })) }]
  });
  const tree = d3.tree().size([height - 40, width - 160]);
  tree(root);
  const svg = d3.select(target).append("svg").attr("width", width).attr("height", height);
  const group = svg.append("g").attr("transform", "translate(70,20)");
  group.selectAll(".link").data(root.links()).join("path").attr("class", "link")
    .attr("d", d3.linkHorizontal().x((d) => d.y).y((d) => d.x));
  const node = group.selectAll(".node").data(root.descendants()).join("g").attr("class", "node")
    .attr("transform", (d) => `translate(${d.y},${d.x})`);
  node.append("circle").attr("r", 7).attr("fill", (d) => colorForRtt(d.data.rtt));
  node.append("text").attr("x", 12).attr("dy", "0.32em").text((d) => `${d.data.name}${d.data.rtt ? ` ${d.data.rtt}ms` : ""}`);
}

function ensureMap() {
  if (state.map) return state.map;
  state.map = L.map("map").setView([35.68, 139.76], 3);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "&copy; OpenStreetMap"
  }).addTo(state.map);
  return state.map;
}

function drawMap(trace) {
  const map = ensureMap();
  state.markers.forEach((m) => m.remove());
  state.markers = [];
  const points = (trace?.hops || []).filter((h) => h.lat && h.lng).map((h) => [h.lat, h.lng, h]);
  points.forEach(([lat, lng, hop]) => {
    state.markers.push(L.circleMarker([lat, lng], { radius: 6, color: colorForRtt(hop.rtt_ms) }).bindPopup(`${hop.ip}<br>${hop.org || ""}`).addTo(map));
  });
  if (points.length > 1) {
    state.markers.push(L.polyline(points.map((p) => [p[0], p[1]]), { color: "#0d9488" }).addTo(map));
    map.fitBounds(points.map((p) => [p[0], p[1]]), { padding: [20, 20] });
  }
}

async function loadTraces() {
  const traces = await json("/api/traces/latest");
  const trace = traces[0];
  drawTree(trace);
  drawMap(trace);
}

async function refreshAll() {
  await Promise.all([loadSnapshot(), loadWifi(), loadQuality(), loadTraces()]);
}

function refreshIntervalMs() {
  const input = document.getElementById("refresh-interval");
  const seconds = Math.max(1, Number.parseInt(input.value, 10) || 30);
  input.value = seconds;
  localStorage.setItem("netvizRefreshIntervalSec", String(seconds));
  return seconds * 1000;
}

function restartAutoRefresh() {
  clearInterval(state.timer);
  if (document.getElementById("auto").checked) {
    state.timer = setInterval(refreshAll, refreshIntervalMs());
  }
}

const savedInterval = Number.parseInt(localStorage.getItem("netvizRefreshIntervalSec"), 10);
if (savedInterval > 0) {
  document.getElementById("refresh-interval").value = savedInterval;
}

document.getElementById("refresh").addEventListener("click", refreshAll);
document.getElementById("auto").addEventListener("change", restartAutoRefresh);
document.getElementById("refresh-interval").addEventListener("change", restartAutoRefresh);
restartAutoRefresh();

refreshAll().catch((error) => setText("status-line", error.message));
