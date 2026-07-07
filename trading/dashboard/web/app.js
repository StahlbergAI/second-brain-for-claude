/* Trading monitor front-end: fetches the FastAPI JSON endpoints and renders. */
const $ = (id) => document.getElementById(id);
const fmt$ = (v) => v == null ? "—" : "$" + Math.round(v).toLocaleString("en-US");
const CHART_THEME = {
  textStyle: { fontFamily: "JetBrains Mono, monospace", color: "#64748b", fontSize: 10 },
  axisLine: { lineStyle: { color: "rgba(90,130,255,0.15)" } },
  splitLine: { lineStyle: { color: "rgba(90,130,255,0.07)" } },
};

async function j(url) { const r = await fetch(url); return r.json(); }

function axis(extra = {}) {
  return Object.assign({
    axisLine: CHART_THEME.axisLine, axisLabel: CHART_THEME.textStyle,
    splitLine: CHART_THEME.splitLine, axisTick: { show: false },
  }, extra);
}

async function renderSummary() {
  const s = await j("/api/summary");
  $("kpi-equity").textContent = fmt$(s.equity);
  if (s.pnl != null) {
    const el = $("kpi-pnl");
    const sign = s.pnl >= 0 ? "+" : "−";
    el.textContent = `${sign}$${Math.abs(Math.round(s.pnl)).toLocaleString()}  (${sign}${Math.abs(s.pnl_pct * 100).toFixed(2)}%) since inception`;
    el.className = "kpi-delta " + (s.pnl >= 0 ? "pos" : "neg");
  }
  $("kpi-gross").textContent = fmt$(s.gross_notional);
  $("kpi-positions").textContent = s.open_positions ?? "—";
  $("kpi-orders").textContent = s.orders_filled ?? "—";
  if (s.last_update) $("asof").textContent = "LAST RUN " + s.last_update + " UTC";
}

async function renderEquity() {
  const rows = await j("/api/equity");
  if (!rows.length) return;
  const chart = echarts.init($("equity-chart"), null, { renderer: "svg" });
  chart.setOption({
    grid: { left: 70, right: 16, top: 18, bottom: 28 },
    tooltip: { trigger: "axis", backgroundColor: "#0d1424", borderColor: "rgba(34,211,238,0.3)",
               textStyle: { color: "#d7e2f4", fontFamily: "JetBrains Mono", fontSize: 11 } },
    xAxis: axis({ type: "category", data: rows.map(r => r.ts.slice(0, 16)), boundaryGap: false }),
    yAxis: axis({ type: "value", scale: true,
                  axisLabel: Object.assign({}, CHART_THEME.textStyle,
                    { formatter: (v) => "$" + (v / 1000).toFixed(1) + "k" }) }),
    series: [{
      type: "line", data: rows.map(r => r.net_liq), smooth: 0.3, symbol: "circle", symbolSize: 5,
      lineStyle: { color: "#22d3ee", width: 2, shadowColor: "rgba(34,211,238,0.6)", shadowBlur: 12 },
      itemStyle: { color: "#22d3ee" },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: "rgba(34,211,238,0.25)" }, { offset: 1, color: "rgba(34,211,238,0)" }]) },
    }],
  });
  new ResizeObserver(() => chart.resize()).observe($("equity-chart"));
}

async function renderPositions() {
  const rows = await j("/api/positions");
  const tbody = document.querySelector("#positions-table tbody");
  if (!rows.length) { $("positions-empty").hidden = false; return; }
  tbody.innerHTML = rows.map(p => `
    <tr>
      <td class="sym">${p.symbol}</td>
      <td class="${p.side === "LONG" ? "side-long" : "side-short"}">${p.side}</td>
      <td>${Math.abs(p.contracts)}</td>
      <td>${p.last_mark_price.toLocaleString("en-US", { maximumFractionDigits: 4 })}</td>
      <td>${fmt$(p.notional)}</td>
    </tr>`).join("");
}

async function renderSignals() {
  const rows = await j("/api/signals");
  if (!rows.length) return;
  $("signals-asof").textContent = rows[0].ts + " UTC";
  $("signal-grid").innerHTML = rows.map(r => {
    const dir = r.weight > 0.05 ? "long" : (r.weight < -0.05 ? "short" : "flat");
    return `<div class="sig">
      <div class="s-sym">${r.symbol}</div>
      <div class="s-dir ${dir}">${dir.toUpperCase()}</div>
      <div class="s-w">w ${r.weight >= 0 ? "+" : ""}${r.weight.toFixed(2)} · tgt ${r.target_contracts}</div>
    </div>`;
  }).join("");
}

async function renderOrders() {
  const rows = await j("/api/orders");
  $("order-feed").innerHTML = rows.length ? rows.map(o => `
    <div class="feed-row">
      <span class="t">${o.ts}</span>
      <span class="${o.action === "Buy" ? "buy" : "sell"}">${o.action.toUpperCase()}</span>
      <span class="sym">${o.symbol}</span>
      <span>×${o.qty}</span>
      <span class="note">${o.status}${o.note ? " · " + o.note : ""}</span>
    </div>`).join("")
    : `<div class="empty">NO EXECUTIONS YET</div>`;
}

async function renderExpression() {
  const e = await j("/api/expression");
  if (!e.rows || !e.rows.length) return;
  const maxAbs = Math.max(...e.rows.map(r => Math.abs(r.ideal)), 1);
  $("expr-pct").textContent = e.expression_pct == null ? ""
    : `expressing ${(e.expression_pct * 100).toFixed(0)}% of ideal`;
  $("expression-list").innerHTML = e.rows.map(r => {
    const iw = Math.min(Math.abs(r.ideal) / maxAbs * 100, 100);
    const aw = Math.min(Math.abs(r.actual) / maxAbs * 100, 100);
    const shortCls = r.ideal < 0 ? " short" : "";
    return `<div class="expr-row">
      <span class="sym">${r.symbol}</span>
      <div class="expr-bar">
        <div class="ideal${shortCls}" style="width:${iw}%"></div>
        <div class="actual${shortCls}" style="width:${aw}%"></div>
      </div>
      <span class="nums">${r.ideal >= 0 ? "+" : ""}${r.ideal.toFixed(2)} → ${r.actual >= 0 ? "+" : ""}${r.actual}</span>
    </div>`;
  }).join("");
  const pct = e.expression_pct;
  $("expr-note").textContent = pct != null && pct < 0.5
    ? "Pale bar = contracts the strategy wants (fractional); solid = what account size allows. " +
      "Low expression means the account is too small for whole contracts - the edge exists but can't be deployed at this equity."
    : "Pale bar = ideal fractional position, solid bar = actual whole contracts held.";
}

async function renderAttribution() {
  const rows = await j("/api/attribution");
  if (!rows.length) { $("attribution-empty").hidden = false; return; }
  const maxAbs = Math.max(...rows.map(r => Math.abs(r.cum_pnl)), 1);
  $("attribution-list").innerHTML = rows.map(r => {
    const w = Math.abs(r.cum_pnl) / maxAbs * 100;
    const pos = r.cum_pnl >= 0;
    return `<div class="attr-row">
      <span class="sym">${r.symbol}</span>
      <div class="attr-bar"><div class="fill" style="width:${w}%;
        background:${pos ? "var(--green)" : "var(--red)"};
        ${pos ? "box-shadow:0 0 8px rgba(52,211,153,.4)" : "box-shadow:0 0 8px rgba(251,113,133,.4)"}"></div></div>
      <span class="val ${pos ? "pos" : "neg"}">${pos ? "+" : "−"}$${Math.abs(r.cum_pnl).toFixed(0)}</span>
    </div>`;
  }).join("");
}

async function renderHealth() {
  const [h, s] = await Promise.all([j("/api/health"), j("/api/summary")]);
  $("health-state").textContent = h.last_ok ? "nominal" : (h.runs.length ? "LAST RUN FAILED" : "no runs yet");
  const dd = s.drawdown ?? 0;
  $("dd-state").innerHTML = s.derisk_active
    ? `<span class="warn">⚠ DRAWDOWN ${(dd * 100).toFixed(1)}% — DE-RISK ACTIVE (size halved beyond −10%)</span>`
    : `<span class="ok">drawdown ${(dd * 100).toFixed(1)}% — full size (de-risk arms at −10%)</span>`;
  $("run-log").innerHTML = h.runs.map(r => `
    <div class="run-row">
      <span class="run-dot ${r.status === "ok" ? "ok" : "error"}"></span>
      <span>${r.ts}</span>
      <span class="msg">${r.status}${r.message ? " · " + r.message : ""}</span>
    </div>`).join("") || `<div class="empty">NO RUNS LOGGED</div>`;
}

async function renderBacktest() {
  const bt = await j("/api/backtest");
  if (!bt.curve.length) return;
  $("bt-chips").innerHTML = `
    <span class="chip">SHARPE <b>${bt.stats.sharpe.toFixed(2)}</b></span>
    <span class="chip">CAGR <b>${(bt.stats.cagr * 100).toFixed(1)}%</b></span>
    <span class="chip">MAX DD <b>${(bt.stats.max_dd * 100).toFixed(1)}%</b></span>
    <span class="chip">BLEND <b>${bt.stats.blend_sharpe.toFixed(2)}</b> / OOS <b>${bt.stats.blend_test_sharpe.toFixed(2)}</b></span>`;
  const chart = echarts.init($("backtest-chart"), null, { renderer: "svg" });
  chart.setOption({
    grid: { left: 54, right: 16, top: 18, bottom: 28 },
    tooltip: { trigger: "axis", backgroundColor: "#0d1424", borderColor: "rgba(167,139,250,0.3)",
               textStyle: { color: "#d7e2f4", fontFamily: "JetBrains Mono", fontSize: 11 } },
    xAxis: axis({ type: "category", data: bt.curve.map(p => p.date), boundaryGap: false }),
    yAxis: axis({ type: "value", scale: true,
                  axisLabel: Object.assign({}, CHART_THEME.textStyle, { formatter: "{value}x" }) }),
    series: [{
      type: "line", data: bt.curve.map(p => p.v), smooth: 0.2, symbol: "none",
      lineStyle: { color: "#34d399", width: 1.8, shadowColor: "rgba(52,211,153,0.4)", shadowBlur: 10 },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: "rgba(52,211,153,0.18)" }, { offset: 1, color: "rgba(52,211,153,0)" }]) },
      markLine: {
        symbol: "none", label: { formatter: "TRAIN | TEST", color: "#64748b", fontSize: 9, fontFamily: "JetBrains Mono" },
        lineStyle: { color: "rgba(251,191,36,0.55)", type: "dashed" },
        data: [{ xAxis: bt.train_end }],
      },
    }],
  });
  new ResizeObserver(() => chart.resize()).observe($("backtest-chart"));
}

(async () => {
  await Promise.all([renderSummary(), renderEquity(), renderPositions(),
                     renderSignals(), renderOrders(), renderBacktest(),
                     renderExpression(), renderAttribution(), renderHealth()]);
})();
