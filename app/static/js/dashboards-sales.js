/* Sales dashboard.
   Strategy: try Cube.dev first; if Cube isn't running locally (no docker),
   fall back to the FastAPI /api/analytics endpoints. Same shape so the
   downstream chart code doesn't care. Loaded after cube-client.js. */

const COLORS = ["#0f766e", "#b45309", "#1f2937", "#7e22ce", "#0e7490", "#9d174d", "#365314"];

async function safeCube(query, fallbackUrl) {
  try {
    const r = await window.cubeLoad(query);
    if (r && r.data && r.data.length) return { source: "cube", rows: r.data };
  } catch (e) {
    /* fall through */
  }
  const r2 = await fetch(fallbackUrl);
  return { source: "api", rows: await r2.json() };
}

function currentRange() {
  return Number(document.getElementById("rangeSelect").value);
}

async function loadKpi() {
  const days = currentRange();
  const r = await fetch(`/api/analytics/kpi?days=${days}`).then((r) => r.json());
  document.getElementById("kpi-revenue").textContent = fmtMoney(r.revenue);
  document.getElementById("kpi-orders").textContent = fmtInt(r.orders);
  document.getElementById("kpi-aov").textContent = fmtMoney(r.aov);
  document.getElementById("kpi-customers").textContent = fmtInt(r.unique_customers);
}

const charts = {};

async function loadRevenueByDay() {
  const days = currentRange();
  const out = await safeCube(
    {
      measures: ["orders.revenue", "orders.count"],
      timeDimensions: [{ dimension: "orders.placed_at", granularity: "day", dateRange: `last ${days} days` }],
    },
    `/api/analytics/revenue-by-day?days=${days}`
  );

  const rows = out.rows;
  const labels = rows.map((r) => r.day || r["orders.placed_at.day"]);
  const revenue = rows.map((r) => Number(r.revenue ?? r["orders.revenue"] ?? 0));
  const orders = rows.map((r) => Number(r.orders ?? r["orders.count"] ?? 0));

  charts.revenue?.destroy();
  charts.revenue = new Chart(document.getElementById("revenueChart"), {
    data: {
      labels,
      datasets: [
        { type: "bar", label: "Orders", data: orders, backgroundColor: "#e5e7eb", yAxisID: "y1" },
        { type: "line", label: "Revenue", data: revenue, borderColor: COLORS[0], backgroundColor: COLORS[0], tension: 0.25, yAxisID: "y" },
      ],
    },
    options: {
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      scales: {
        y: { position: "left", ticks: { callback: (v) => `$${(v / 1000).toFixed(0)}k` }, grid: { color: "#f3f4f6" } },
        y1: { position: "right", grid: { display: false } },
        x: { grid: { display: false } },
      },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

async function loadChannel() {
  const days = currentRange();
  const r = await fetch(`/api/analytics/revenue-by-channel?days=${days}`).then((r) => r.json());
  const labels = r.map((x) => x.channel);
  const data = r.map((x) => Number(x.revenue));
  charts.channel?.destroy();
  charts.channel = new Chart(document.getElementById("channelChart"), {
    type: "bar",
    data: { labels, datasets: [{ data, backgroundColor: COLORS[0] }] },
    options: {
      maintainAspectRatio: false,
      indexAxis: "y",
      scales: { x: { ticks: { callback: (v) => `$${(v / 1000).toFixed(0)}k` } } },
      plugins: { legend: { display: false } },
    },
  });
}

async function loadMargin() {
  const days = currentRange();
  const r = await fetch(`/api/analytics/gross-margin-by-category?days=${days}`).then((r) => r.json());
  const labels = r.map((x) => x.category);
  const margin = r.map((x) => Number(x.gross_margin));
  const pct = r.map((x) => Number(x.margin_pct) * 100);
  charts.margin?.destroy();
  charts.margin = new Chart(document.getElementById("marginChart"), {
    data: {
      labels,
      datasets: [
        { type: "bar", label: "Gross margin $", data: margin, backgroundColor: COLORS[0], yAxisID: "y" },
        { type: "line", label: "Margin %", data: pct, borderColor: COLORS[1], yAxisID: "y1" },
      ],
    },
    options: {
      maintainAspectRatio: false,
      scales: {
        y: { ticks: { callback: (v) => `$${(v / 1000).toFixed(0)}k` } },
        y1: { position: "right", grid: { display: false }, ticks: { callback: (v) => `${v.toFixed(0)}%` } },
      },
      plugins: { legend: { position: "bottom" } },
    },
  });
}

async function loadDevice() {
  const days = currentRange();
  const r = await fetch(`/api/analytics/aov-by-device?days=${days}`).then((r) => r.json());
  const labels = r.map((x) => x.device_type);
  const aov = r.map((x) => Number(x.aov));
  charts.device?.destroy();
  charts.device = new Chart(document.getElementById("deviceChart"), {
    type: "bar",
    data: { labels, datasets: [{ label: "AOV", data: aov, backgroundColor: COLORS[0] }] },
    options: {
      maintainAspectRatio: false,
      scales: { y: { ticks: { callback: (v) => `$${v}` } } },
      plugins: { legend: { display: false } },
    },
  });
}

function makeCell(text, klass) {
  const td = document.createElement("td");
  td.textContent = text;
  if (klass) td.className = klass;
  return td;
}

async function loadTopProducts() {
  const days = currentRange();
  const rows = await fetch(`/api/analytics/top-products?days=${days}&limit=10`).then((r) => r.json());
  const tbody = document.querySelector("#topProductsTable tbody");
  tbody.replaceChildren();
  for (const x of rows) {
    const tr = document.createElement("tr");
    tr.append(
      makeCell(x.sku),
      makeCell(x.name),
      makeCell(x.brand),
      makeCell(fmtInt(x.units), "num"),
      makeCell(fmtMoney(x.revenue), "num"),
      makeCell(fmtMoney(x.gross_margin), "num"),
    );
    tbody.append(tr);
  }
}

async function refresh() {
  await Promise.all([loadKpi(), loadRevenueByDay(), loadChannel(), loadMargin(), loadDevice(), loadTopProducts()]);
}

document.getElementById("rangeSelect").addEventListener("change", refresh);
refresh();
