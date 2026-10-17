// =====================================================================
// AUTHENTICATION CONFIGURATION
// Replace PASSWORD_HASH with the SHA-256 of your own password before deploying.
// Placeholder SHA-256 hash below must be replaced with your chosen password hash before deploying.
// =====================================================================
const PASSWORD_HASH = "fb86fb757d1241d512865070e05ccb5d17dfaa11a4b2ca04b89bacad17530ad4";

// =====================================================================
// GITHUB RAW ENDPOINTS
// =====================================================================
const REPO_BASE = "https://raw.githubusercontent.com/toanilsharma/midcap-swing-scanner/main";
const SCAN_RESULTS_URL = `${REPO_BASE}/scan_results.json`;
const OPEN_POSITIONS_URL = `${REPO_BASE}/open_positions.json`;
const TRADES_URL = `${REPO_BASE}/trades.json`;

let equityChartInstance = null;

// Currency Formatter (INR)
function formatINR(val, includeSign = false) {
  if (val === null || val === undefined || isNaN(val)) return "N/A";
  const absVal = Math.abs(val);
  const formatted = "₹" + absVal.toLocaleString("en-IN", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
  if (includeSign) {
    return val > 0 ? `+${formatted}` : val < 0 ? `-${formatted}` : formatted;
  }
  return val < 0 ? `-${formatted}` : formatted;
}

// Format Date
function formatDate(dateStr) {
  if (!dateStr) return "N/A";
  try {
    const d = new Date(dateStr);
    return d.toLocaleDateString("en-IN", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
  } catch {
    return dateStr;
  }
}

// Format Datetime
function formatDateTime(isoStr) {
  if (!isoStr) return "Unknown";
  try {
    const d = new Date(isoStr);
    return d.toLocaleString("en-IN", {
      timeZone: "Asia/Kolkata",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: true,
    }) + " IST";
  } catch {
    return isoStr;
  }
}

// Fetch helper with cache-busting
async function fetchJson(url) {
  const cacheBuster = `?t=${Date.now()}`;
  const response = await fetch(url + cacheBuster);
  if (!response.ok) {
    throw new Error(`HTTP ${response.status} fetching ${url}`);
  }
  return await response.json();
}

// Attempt to fetch live price for a symbol via Yahoo Chart API
async function fetchLivePrice(symbol) {
  try {
    const sym = symbol.endsWith(".NS") ? symbol : `${symbol}.NS`;
    const url = `https://query1.finance.yahoo.com/v8/finance/chart/${sym}?interval=1d&range=5d`;
    const res = await fetch(url, { mode: "cors" });
    if (!res.ok) return null;
    const data = await res.json();
    const meta = data?.chart?.result?.[0]?.meta;
    return meta?.regularMarketPrice || null;
  } catch {
    return null; // CORS or network blocked
  }
}

// =====================================================================
// DATA RENDERING
// =====================================================================

// 1. Render Tab: Near Buy (Watchlist & Active Signals)
function renderNearBuy(scanData) {
  const marketBadge = document.getElementById("marketBadge");
  const regimeBanner = document.getElementById("regimeBanner");
  const regimeText = document.getElementById("regimeText");
  const scannedMeta = document.getElementById("scannedMeta");
  const lastUpdated = document.getElementById("lastUpdatedText");

  if (!scanData) {
    document.getElementById("watchlistBody").innerHTML = `
      <tr><td colspan="6" class="empty-state">No scan results found on GitHub repository.</td></tr>
    `;
    return;
  }

  // Update header metadata
  lastUpdated.textContent = `Updated: ${formatDateTime(scanData.updated_at)}`;

  if (scanData.market_ok) {
    marketBadge.className = "badge badge-success";
    marketBadge.textContent = "Market: Uptrend";
    regimeBanner.className = "regime-banner uptrend";
    regimeText.textContent = "🟢 MARKET UPTREND CONFIRMED: Normal buy entry rules active.";
  } else {
    marketBadge.className = "badge badge-danger";
    marketBadge.textContent = "Market: Defensive";
    regimeBanner.className = "regime-banner defensive";
    regimeText.textContent = "🔴 MARKET FILTER ACTIVE: Index in pullback/downtrend. New entry signals blocked (O'Neil M-rule).";
  }
  scannedMeta.textContent = `${scanData.scanned_count || 100} midcap stocks scanned`;
  regimeBanner.style.display = "flex";

  // Render Signals if present
  const signalsContainer = document.getElementById("signalsContainer");
  const signalsBody = document.getElementById("signalsBody");
  if (scanData.signals && scanData.signals.length > 0) {
    signalsContainer.style.display = "block";
    signalsBody.innerHTML = scanData.signals.map(s => `
      <tr class="row-green">
        <td><span class="badge badge-success">${s.Type || "BREAKOUT"}</span></td>
        <td><strong>${s.Symbol}</strong></td>
        <td>${formatINR(s.Entry)}</td>
        <td style="color: var(--danger);">${formatINR(s.Stop)}</td>
        <td style="color: var(--success);">${formatINR(s.Target)}</td>
        <td>${s.Qty}</td>
        <td>${formatINR(s["Risk Amount"])}</td>
        <td><span class="badge badge-neutral">${s.Sector || "N/A"}</span></td>
      </tr>
    `).join("");
  } else {
    signalsContainer.style.display = "none";
  }

  // Render Watchlist
  const watchlistBody = document.getElementById("watchlistBody");
  const watchlist = scanData.watchlist || [];

  if (watchlist.length === 0) {
    watchlistBody.innerHTML = `
      <tr><td colspan="6" class="empty-state">📋 Watchlist empty: no midcaps currently in uptrend within 5% of breakout.</td></tr>
    `;
    return;
  }

  watchlistBody.innerHTML = watchlist.map(item => {
    const dist = parseFloat(item["DistToBreakout%"]) || 0;
    let rowClass = "";
    if (dist <= 2.0) rowClass = "row-green";
    else if (dist <= 5.0) rowClass = "row-yellow";

    const isBullish = item.SectorBullish === "YES";
    const bullishBadge = isBullish
      ? `<span class="badge badge-success">YES</span>`
      : `<span class="badge badge-warning">no</span>`;

    const coilingBadge = item.Coiling === "YES"
      ? `<span class="badge badge-success">Coiling</span>`
      : `<span class="badge badge-neutral">no</span>`;

    return `
      <tr class="${rowClass}">
        <td><strong>${item.Symbol}</strong></td>
        <td>${formatINR(item.Close)}</td>
        <td><strong>${dist.toFixed(2)}%</strong> away</td>
        <td>${coilingBadge}</td>
        <td><span class="badge badge-neutral">${item.Sector || "^NSEI"}</span></td>
        <td>${bullishBadge}</td>
      </tr>
    `;
  }).join("");
}

// 2. Render Tab: Open Positions
async function renderOpenPositions(positions) {
  const countBadge = document.getElementById("openCountBadge");
  const countCard = document.getElementById("openPositionsCount");
  const totalPnlCard = document.getElementById("openTotalPnl");
  const capitalCard = document.getElementById("openCapitalDeployed");
  const tableBody = document.getElementById("openPositionsBody");

  if (!positions || positions.length === 0) {
    countBadge.textContent = "0";
    countCard.textContent = "0";
    totalPnlCard.textContent = "₹0.00";
    totalPnlCard.className = "stat-value neutral";
    capitalCard.textContent = "₹0.00";
    tableBody.innerHTML = `
      <tr><td colspan="10" class="empty-state">💼 No active open positions recorded. Use /buy in Telegram to log trades.</td></tr>
    `;
    return;
  }

  countBadge.textContent = positions.length;
  countCard.textContent = positions.length;

  let totalUnrealized = 0;
  let totalCapital = 0;
  const rows = [];

  for (const pos of positions) {
    const entry = parseFloat(pos.entry_price) || 0;
    const qty = parseInt(pos.qty, 10) || 0;
    const stop = pos.stop ? parseFloat(pos.stop) : null;
    const target = pos.target ? parseFloat(pos.target) : null;
    totalCapital += (entry * qty);

    // Fetch live price or fallback
    const livePrice = await fetchLivePrice(pos.symbol);
    const currentPrice = livePrice !== null ? livePrice : entry;
    const isLive = livePrice !== null;

    const unrealized = (currentPrice - entry) * qty;
    totalUnrealized += unrealized;

    let distToStopStr = "N/A";
    let distToTargetStr = "N/A";
    let isNearStop = false;
    let isNearTarget = false;

    if (stop && currentPrice > 0) {
      const pctToStop = ((currentPrice - stop) / currentPrice) * 100;
      distToStopStr = `${pctToStop.toFixed(1)}%`;
      if (pctToStop <= 2.0 && pctToStop >= -1.0) isNearStop = true;
    }

    if (target && currentPrice > 0) {
      const pctToTarget = ((target - currentPrice) / currentPrice) * 100;
      distToTargetStr = `${pctToTarget.toFixed(1)}%`;
      if (pctToTarget <= 2.0 && pctToTarget >= -1.0) isNearTarget = true;
    }

    let rowClass = "";
    if (isNearStop) rowClass = "row-danger";
    else if (isNearTarget) rowClass = "row-green";

    const pnlSign = unrealized >= 0 ? "+" : "";
    const pnlClass = unrealized > 0 ? "style='color: var(--success); font-weight:600;'" : unrealized < 0 ? "style='color: var(--danger); font-weight:600;'" : "";

    rows.push(`
      <tr class="${rowClass}">
        <td><strong>${pos.symbol}</strong></td>
        <td>${formatDate(pos.entry_date)}</td>
        <td>${formatINR(entry)}</td>
        <td>${qty}</td>
        <td style="color: var(--danger);">${stop ? formatINR(stop) : "None"}</td>
        <td style="color: var(--success);">${target ? formatINR(target) : "None"}</td>
        <td>${formatINR(currentPrice)} ${!isLive ? "<small style='color: var(--text-dim);'>(entry)</small>" : ""}</td>
        <td ${pnlClass}>${pnlSign}${formatINR(unrealized)}</td>
        <td>${distToStopStr}</td>
        <td>${distToTargetStr}</td>
      </tr>
    `);
  }

  capitalCard.textContent = formatINR(totalCapital);
  totalPnlCard.textContent = formatINR(totalUnrealized, true);
  totalPnlCard.className = `stat-value ${totalUnrealized > 0 ? "positive" : totalUnrealized < 0 ? "negative" : "neutral"}`;
  tableBody.innerHTML = rows.join("");
}

// 3. Render Tab: Trade History & Equity Curve
function renderHistory(trades) {
  const tableBody = document.getElementById("tradesBody");
  const totalBadge = document.getElementById("equityTotalBadge");

  if (!trades || trades.length === 0) {
    totalBadge.textContent = "₹0.00";
    totalBadge.className = "badge badge-neutral";
    tableBody.innerHTML = `
      <tr><td colspan="10" class="empty-state">📜 No closed trades recorded yet.</td></tr>
    `;
    const canvas = document.getElementById("equityChart");
    if (canvas && window.Chart) {
      if (equityChartInstance) {
        equityChartInstance.destroy();
      }
      const ctx = canvas.getContext("2d");
      equityChartInstance = new Chart(ctx, {
        type: "line",
        data: {
          labels: ["Baseline", "Current"],
          datasets: [{
            label: "Cumulative Realized PnL (₹)",
            data: [0, 0],
            borderColor: "#64748b",
            borderWidth: 2,
            pointRadius: 3,
            backgroundColor: "rgba(100, 116, 139, 0.08)",
            fill: true,
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { display: false } },
          scales: {
            x: { grid: { color: "rgba(255, 255, 255, 0.04)" }, ticks: { color: "#94a3b8" } },
            y: { min: -100, max: 100, grid: { color: "rgba(255, 255, 255, 0.06)" }, ticks: { color: "#94a3b8", callback: (val) => formatINR(val) } }
          }
        }
      });
    }
    return;
  }

  // Sort trades newest first for the table
  const sortedTrades = [...trades].reverse();

  tableBody.innerHTML = sortedTrades.map(t => {
    const pnl = parseFloat(t.pnl) || 0;
    const pnlPct = parseFloat(t.pnl_pct) || 0;
    const sign = pnl >= 0 ? "+" : "";
    const colorStyle = pnl > 0 ? "style='color: var(--success); font-weight: 600;'" : "style='color: var(--danger); font-weight: 600;'";
    const rMultipleStr = t.r_multiple !== null && t.r_multiple !== undefined ? `${t.r_multiple > 0 ? "+" : ""}${t.r_multiple}R` : "N/A";

    return `
      <tr>
        <td><strong>${t.symbol}</strong></td>
        <td>${formatDate(t.entry_date)}</td>
        <td>${formatINR(t.entry_price)}</td>
        <td>${t.qty}</td>
        <td>${formatDate(t.exit_date)}</td>
        <td>${formatINR(t.exit_price)}</td>
        <td ${colorStyle}>${sign}${formatINR(pnl)}</td>
        <td ${colorStyle}>${sign}${pnlPct.toFixed(2)}%</td>
        <td><span class="badge ${pnl > 0 ? "badge-success" : "badge-danger"}">${rMultipleStr}</span></td>
        <td><small style="color: var(--text-muted);">${t.note || "-"}</small></td>
      </tr>
    `;
  }).join("");

  // Calculate Cumulative Equity Curve in chronological order
  const labels = ["Start"];
  const equityPoints = [0];
  let runningPnl = 0;

  for (let i = 0; i < trades.length; i++) {
    const t = trades[i];
    runningPnl += (parseFloat(t.pnl) || 0);
    labels.push(`${t.symbol} (#${i + 1})`);
    equityPoints.push(runningPnl);
  }

  totalBadge.textContent = formatINR(runningPnl, true);
  totalBadge.className = `badge ${runningPnl >= 0 ? "badge-success" : "badge-danger"}`;

  // Render Chart via Chart.js
  const canvas = document.getElementById("equityChart");
  if (canvas && window.Chart) {
    if (equityChartInstance) {
      equityChartInstance.destroy();
    }

    const ctx = canvas.getContext("2d");
    const gradient = ctx.createLinearGradient(0, 0, 0, 300);
    gradient.addColorStop(0, runningPnl >= 0 ? "rgba(16, 185, 129, 0.3)" : "rgba(239, 68, 68, 0.3)");
    gradient.addColorStop(1, "rgba(15, 23, 42, 0.0)");

    equityChartInstance = new Chart(ctx, {
      type: "line",
      data: {
        labels: labels,
        datasets: [{
          label: "Cumulative Realized PnL (₹)",
          data: equityPoints,
          borderColor: runningPnl >= 0 ? "#10b981" : "#ef4444",
          borderWidth: 2.5,
          pointBackgroundColor: "#fff",
          pointRadius: 3,
          backgroundColor: gradient,
          fill: true,
          tension: 0.25,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => ` PnL: ${formatINR(ctx.raw, true)}`
            }
          }
        },
        scales: {
          x: {
            grid: { color: "rgba(255, 255, 255, 0.04)" },
            ticks: { color: "#94a3b8", font: { size: 11 } }
          },
          y: {
            grid: { color: "rgba(255, 255, 255, 0.06)" },
            ticks: {
              color: "#94a3b8",
              font: { size: 11 },
              callback: (value) => formatINR(value)
            }
          }
        }
      }
    });
  }
}

// 4. Render Tab: Statistics
function renderStats(trades) {
  const statTotal = document.getElementById("statTotalTrades");
  const statWinRate = document.getElementById("statWinRate");
  const statTotalPnl = document.getElementById("statTotalPnl");
  const statProfitFactor = document.getElementById("statProfitFactor");
  const statExpectancy = document.getElementById("statExpectancy");
  const statAvgWin = document.getElementById("statAvgWin");
  const statAvgLoss = document.getElementById("statAvgLoss");
  const statMaxDD = document.getElementById("statMaxDD");
  const statBest = document.getElementById("statBestTrade");
  const statWorst = document.getElementById("statWorstTrade");

  if (!trades || trades.length === 0) {
    statTotal.textContent = "0";
    statWinRate.textContent = "0.0%";
    statTotalPnl.textContent = "₹0.00";
    statProfitFactor.textContent = "0.00";
    statExpectancy.textContent = "₹0.00";
    statAvgWin.textContent = "+₹0.00";
    statAvgLoss.textContent = "-₹0.00";
    statMaxDD.textContent = "₹0.00";
    statBest.textContent = "+₹0.00";
    statWorst.textContent = "-₹0.00";
    return;
  }

  const totalTrades = trades.length;
  const wins = trades.filter(t => (parseFloat(t.pnl) || 0) > 0);
  const losses = trades.filter(t => (parseFloat(t.pnl) || 0) <= 0);

  const winRate = (wins.length / totalTrades) * 100.0;
  const sumWins = wins.reduce((acc, t) => acc + (parseFloat(t.pnl) || 0), 0);
  const sumLosses = losses.reduce((acc, t) => acc + (parseFloat(t.pnl) || 0), 0);
  const totalPnl = sumWins + sumLosses;

  const avgWin = wins.length > 0 ? (sumWins / wins.length) : 0;
  const avgLoss = losses.length > 0 ? (sumLosses / losses.length) : 0;

  let profitFactorStr = "0.00";
  if (sumLosses !== 0) {
    profitFactorStr = (sumWins / Math.abs(sumLosses)).toFixed(2);
  } else if (sumWins > 0) {
    profitFactorStr = "∞";
  }

  const winProb = wins.length / totalTrades;
  const lossProb = 1.0 - winProb;
  const expectancy = (winProb * avgWin) - (lossProb * Math.abs(avgLoss));

  // Max Drawdown calculation
  let cum = 0;
  let peak = 0;
  let maxDD = 0;
  for (const t of trades) {
    cum += (parseFloat(t.pnl) || 0);
    if (cum > peak) peak = cum;
    const dd = peak - cum;
    if (dd > maxDD) maxDD = dd;
  }

  const pnls = trades.map(t => parseFloat(t.pnl) || 0);
  const bestTrade = Math.max(...pnls);
  const worstTrade = Math.min(...pnls);

  statTotal.textContent = `${totalTrades} (${wins.length}W / ${losses.length}L)`;
  statWinRate.textContent = `${winRate.toFixed(1)}%`;
  statTotalPnl.textContent = formatINR(totalPnl, true);
  statTotalPnl.className = `stat-value ${totalPnl >= 0 ? "positive" : "negative"}`;

  statProfitFactor.textContent = profitFactorStr;
  statExpectancy.textContent = formatINR(expectancy, true);
  statExpectancy.className = `stat-value ${expectancy >= 0 ? "positive" : "negative"}`;

  statAvgWin.textContent = `+${formatINR(avgWin)}`;
  statAvgLoss.textContent = `-${formatINR(Math.abs(avgLoss))}`;
  statMaxDD.textContent = `-${formatINR(maxDD)}`;

  statBest.textContent = formatINR(bestTrade, true);
  statWorst.textContent = formatINR(worstTrade, true);
}

// =====================================================================
// MASTER LOAD AND AUTO-REFRESH
// =====================================================================
async function loadAllData() {
  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    refreshBtn.disabled = true;
    refreshBtn.textContent = "⏳ Updating...";
  }

  try {
    const [scanData, openPositions, trades] = await Promise.all([
      fetchJson(SCAN_RESULTS_URL).catch(e => { console.warn("Scan results fetch error:", e); return null; }),
      fetchJson(OPEN_POSITIONS_URL).catch(e => { console.warn("Open positions fetch error:", e); return []; }),
      fetchJson(TRADES_URL).catch(e => { console.warn("Trades fetch error:", e); return []; }),
    ]);

    renderNearBuy(scanData);
    await renderOpenPositions(openPositions);
    renderHistory(trades);
    renderStats(trades);
  } catch (err) {
    console.error("Global dashboard data load error:", err);
  } finally {
    if (refreshBtn) {
      refreshBtn.disabled = false;
      refreshBtn.textContent = "🔄 Refresh";
    }
  }
}

// =====================================================================
// EVENT LISTENERS & INITIALIZATION
// =====================================================================
document.addEventListener("DOMContentLoaded", () => {
  // Authentication gate for dashboard
  if (window.location.pathname.endsWith("app.html")) {
    if (localStorage.getItem("auth") !== "1") {
      window.location.href = "index.html";
      return;
    }
  }

  // Logout button
  const logoutBtn = document.getElementById("logoutBtn");
  if (logoutBtn) {
    logoutBtn.addEventListener("click", () => {
      localStorage.removeItem("auth");
      window.location.href = "index.html";
    });
  }

  // Refresh button
  const refreshBtn = document.getElementById("refreshBtn");
  if (refreshBtn) {
    refreshBtn.addEventListener("click", () => {
      loadAllData();
    });
  }

  // Tab switching
  const tabButtons = document.querySelectorAll(".tab-btn");
  const tabContents = document.querySelectorAll(".tab-content");

  tabButtons.forEach(btn => {
    btn.addEventListener("click", () => {
      const targetTabId = btn.getAttribute("data-tab");

      tabButtons.forEach(b => b.classList.remove("active"));
      tabContents.forEach(c => c.classList.remove("active"));

      btn.classList.add("active");
      const targetContent = document.getElementById(targetTabId);
      if (targetContent) {
        targetContent.classList.add("active");
      }
    });
  });

  // Initial load if on app page
  if (document.getElementById("watchlistTable")) {
    loadAllData();

    // Auto-refresh every 5 minutes (300,000 ms)
    setInterval(() => {
      console.log("Auto-refreshing dashboard data...");
      loadAllData();
    }, 300000);
  }
});
