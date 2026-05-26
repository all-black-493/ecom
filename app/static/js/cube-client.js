// Minimal Cube.dev REST client (no npm dep needed).
// Cube /load endpoint: POST {query} -> {data: [...]}

window.cubeLoad = async function (query) {
  const r = await fetch(`${window.CUBE_API_URL}/load`, {
    method: "POST",
    headers: { "Content-Type": "application/json", Authorization: window.CUBE_TOKEN },
    body: JSON.stringify({ query }),
  });
  if (!r.ok) {
    console.warn("Cube error", r.status, await r.text());
    return { data: [] };
  }
  return r.json();
};

window.fmtMoney = (n) =>
  Number(n || 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
window.fmtInt = (n) => Number(n || 0).toLocaleString("en-US");
window.fmtPct = (n) => `${(Number(n || 0) * 100).toFixed(1)}%`;
