// Atlas RTB front-end controller. Vanilla JS + Chart.js.
// Polls /api/metrics + /api/timeseries every 4s and re-renders KPI cards.

const state = {
  charts: {},
  pollInterval: null,
};

// -------------- helpers --------------
const $  = (s, ctx = document) => ctx.querySelector(s);
const $$ = (s, ctx = document) => Array.from(ctx.querySelectorAll(s));

async function api(path, opts = {}) {
  const init = { headers: { "Content-Type": "application/json" }, ...opts };
  const r = await fetch(path, init);
  if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
  return r.json();
}

function fmt(n, d = 0) {
  if (n === null || n === undefined || isNaN(n)) return "--";
  return Number(n).toLocaleString(undefined,
    { minimumFractionDigits: d, maximumFractionDigits: d });
}
function fmtPct(n, d = 2) { return n == null ? "--" : (n * 100).toFixed(d); }

// -------------- tab nav --------------
$$(".navbtn").forEach(b => {
  b.addEventListener("click", () => {
    $$(".navbtn").forEach(x => x.classList.remove("active"));
    $$(".tab").forEach(x => x.classList.remove("active"));
    b.classList.add("active");
    $(`#tab-${b.dataset.tab}`).classList.add("active");
    if (b.dataset.tab === "campaigns") refreshCampaigns();
    if (b.dataset.tab === "experiments") refreshMab();
    if (b.dataset.tab === "infra") refreshInfra();
  });
});

// -------------- charts --------------
const chartBase = {
  responsive: true,
  maintainAspectRatio: false,
  plugins: { legend: { labels: { color: "#e6ebff" } } },
  scales: {
    x: { ticks: { color: "#8a93b8" }, grid: { color: "rgba(255,255,255,0.04)" } },
    y: { ticks: { color: "#8a93b8" }, grid: { color: "rgba(255,255,255,0.04)" }, beginAtZero: true },
  },
};

function buildCharts() {
  const tCtx = $("#chart-throughput").getContext("2d");
  state.charts.throughput = new Chart(tCtx, {
    type: "line",
    data: {
      labels: [],
      datasets: [
        { label: "Impressions", data: [], borderColor: "#6ea8ff",
          backgroundColor: "rgba(110,168,255,0.15)", tension: 0.3, fill: true },
        { label: "Clicks", data: [], borderColor: "#56e0c2",
          backgroundColor: "rgba(86,224,194,0.15)", tension: 0.3, fill: true },
        { label: "Conversions", data: [], borderColor: "#f5a623",
          backgroundColor: "rgba(245,166,35,0.15)", tension: 0.3, fill: true },
      ],
    },
    options: chartBase,
  });

  const lCtx = $("#chart-latency").getContext("2d");
  state.charts.latency = new Chart(lCtx, {
    type: "bar",
    data: {
      labels: ["P50", "P95", "P99"],
      datasets: [{
        label: "ms",
        data: [0, 0, 0],
        backgroundColor: ["#56e0c2", "#6ea8ff", "#f5a623"],
        borderRadius: 6,
      }],
    },
    options: { ...chartBase, plugins: { legend: { display: false } } },
  });

  const mCtx = $("#chart-mab").getContext("2d");
  state.charts.mab = new Chart(mCtx, {
    type: "bar",
    data: { labels: [], datasets: [
      { label: "Posterior CTR mean", data: [], backgroundColor: "#6ea8ff" },
    ]},
    options: { ...chartBase, indexAxis: "y" },
  });
}

// -------------- overview --------------
async function refreshOverview() {
  try {
    const [m, ts] = await Promise.all([api("/api/metrics"), api("/api/timeseries")]);

    const eng = m.engine;
    $("#kpi-requests").textContent = fmt(eng.total_requests);
    $("#kpi-bidrate").textContent = fmtPct(eng.bid_rate);
    $("#kpi-p99").textContent = (eng.latency_ms.p99 || 0).toFixed(2);
    $("#kpi-campaigns").textContent = eng.active_campaigns;
    $("#kpi-sla").textContent = fmtPct(m.monitoring.sla_compliance, 3);

    // Latest window numbers
    const last = ts.points[ts.points.length - 1] || {};
    $("#kpi-imp").textContent = fmt(last.impressions || 0);
    $("#kpi-conv").textContent = fmt(last.conversions || 0);
    $("#kpi-rev").textContent = fmt(last.revenue || 0, 2);
    const ctr = last.impressions ? (last.clicks || 0) / last.impressions : 0;
    $("#kpi-ctr").textContent = fmtPct(ctr) + "%";

    // Throughput chart
    const labels = ts.points.map(p => new Date(p.ts).toLocaleTimeString());
    state.charts.throughput.data.labels = labels;
    state.charts.throughput.data.datasets[0].data = ts.points.map(p => p.impressions);
    state.charts.throughput.data.datasets[1].data = ts.points.map(p => p.clicks);
    state.charts.throughput.data.datasets[2].data = ts.points.map(p => p.conversions);
    state.charts.throughput.update("none");

    // Latency chart
    state.charts.latency.data.datasets[0].data = [
      eng.latency_ms.p50, eng.latency_ms.p95, eng.latency_ms.p99,
    ].map(x => +(x || 0).toFixed(2));
    state.charts.latency.update("none");
  } catch (e) {
    console.warn("overview refresh failed:", e);
  }
}

// -------------- bid form --------------
$("#bid-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const payload = Object.fromEntries(fd.entries());
  payload.user_segments = String(payload.user_segments || "")
    .split(",").map(s => s.trim()).filter(Boolean);
  payload.floor_price = Number(payload.floor_price);
  payload.width = 300; payload.height = 250;
  try {
    const r = await api("/api/bid", { method: "POST", body: JSON.stringify(payload) });
    $("#bid-response").textContent = JSON.stringify(r, null, 2);
    refreshEngine();
  } catch (err) {
    $("#bid-response").textContent = "Error: " + err.message;
  }
});

async function refreshEngine() {
  const m = await api("/api/metrics");
  $("#engine-stats").textContent = JSON.stringify(m.engine, null, 2);
}
$("#btn-refresh-engine").addEventListener("click", refreshEngine);

// -------------- burst --------------
$("#btn-burst").addEventListener("click", async () => {
  const r = await api("/api/simulate?n=200", { method: "POST" });
  console.log("burst result:", r);
  refreshOverview();
});

// -------------- campaigns --------------
async function refreshCampaigns() {
  const data = await api("/api/campaigns");
  const tbody = $("#campaign-table tbody");
  tbody.innerHTML = "";
  for (const c of data.campaigns) {
    const k = c.kpis;
    const pacing = Math.min(100, (c.daily_spent / Math.max(c.daily_budget, 1)) * 100);
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><b>${c.advertiser_name}</b><br/><span style="color:#8a93b8;font-size:11px">${c.advertiser_id}</span></td>
      <td>${c.campaign_id}</td>
      <td>$${fmt(c.bid_cpm, 2)}</td>
      <td>${fmt(k.impressions)}</td>
      <td>${fmt(k.clicks)}</td>
      <td>${fmtPct(k.ctr)}%</td>
      <td>${fmt(k.conversions)}</td>
      <td>${fmtPct(k.cvr)}%</td>
      <td>$${fmt(k.revenue, 2)}</td>
      <td>$${fmt(k.cpa, 2)}</td>
      <td>${fmt(k.roas, 2)}x</td>
      <td>
        <div class="pacing-bar"><div class="fill" style="width:${pacing.toFixed(1)}%"></div></div>
        <div style="color:#8a93b8;font-size:11px;margin-top:4px">$${fmt(c.daily_spent,0)}/$${fmt(c.daily_budget,0)}</div>
      </td>`;
    tbody.appendChild(row);
  }
}

// -------------- A/B test --------------
$("#ab-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const payload = {};
  fd.forEach((v, k) => payload[k] = Number(v));
  payload.metric_name = "ctr";
  try {
    const r = await api("/api/ab_test", { method: "POST", body: JSON.stringify(payload) });
    $("#ab-result").textContent = JSON.stringify(r, null, 2);
  } catch (err) {
    $("#ab-result").textContent = "Error: " + err.message;
  }
});

$("#ss-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const payload = {};
  fd.forEach((v, k) => payload[k] = Number(v));
  const r = await api("/api/sample_size", { method: "POST", body: JSON.stringify(payload) });
  $("#ss-result").textContent = JSON.stringify(r, null, 2);
});

async function refreshMab() {
  const r = await api("/api/mab");
  const arms = r.arms.slice(0, 12);
  state.charts.mab.data.labels = arms.map(a => a.arm_id);
  state.charts.mab.data.datasets[0].data = arms.map(a => +(a.ctr_mean * 100).toFixed(2));
  state.charts.mab.update("none");
}
$("#btn-mab-refresh").addEventListener("click", refreshMab);

$("#btn-fdr").addEventListener("click", async () => {
  const r = await api("/api/fdr");
  $("#fdr-result").textContent = JSON.stringify(r, null, 2);
});

// -------------- causal --------------
$("#did-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const payload = {};
  fd.forEach((v, k) => payload[k] = Number(v));
  try {
    const r = await api("/api/did", { method: "POST", body: JSON.stringify(payload) });
    $("#did-result").textContent = JSON.stringify(r, null, 2);
  } catch (err) { $("#did-result").textContent = "Error: " + err.message; }
});

$("#psm-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const fd = new FormData(e.target);
  const payload = {};
  fd.forEach((v, k) => payload[k] = Number(v));
  try {
    const r = await api("/api/psm", { method: "POST", body: JSON.stringify(payload) });
    $("#psm-result").textContent = JSON.stringify(r, null, 2);
  } catch (err) { $("#psm-result").textContent = "Error: " + err.message; }
});

// -------------- infra --------------
async function refreshInfra() {
  const m = await api("/api/metrics");
  $("#infra-stats").textContent = JSON.stringify(m, null, 2);
}

// -------------- bootstrap --------------
window.addEventListener("DOMContentLoaded", () => {
  buildCharts();
  refreshOverview();
  state.pollInterval = setInterval(refreshOverview, 4000);
});
