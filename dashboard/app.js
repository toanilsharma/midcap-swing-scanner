// =====================================================================
// AUTHENTICATION CONFIGURATION
// Replace PASSWORD_HASH with the SHA-256 of your own password before deploying.
// Placeholder SHA-256 hash below must be replaced with your chosen password hash before deploying.
// =====================================================================
const PASSWORD_HASH = "ad15418e84fe6e94ec8dd2c22e7f952fc90457256ffbc0f59dcffdef0509366d";

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
      <tr><td colspan="8" class="empty-state">No scan results found on GitHub repository.</td></tr>
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
      <tr><td colspan="8" class="empty-state">📋 Watchlist empty: no midcaps currently in uptrend within 5% of breakout.</td></tr>
    `;
    return;
  }

  // Sort watchlist by score descending (secondary: DistToBreakout% ascending)
  const sortedWatchlist = [...watchlist].sort((a, b) => {
    const scoreA = Number(a.score ?? a.Score ?? 0);
    const scoreB = Number(b.score ?? b.Score ?? 0);
    if (scoreB !== scoreA) {
      return scoreB - scoreA;
    }
    const distA = parseFloat(a["DistToBreakout%"]) || 0;
    const distB = parseFloat(b["DistToBreakout%"]) || 0;
    return distA - distB;
  });

  watchlistBody.innerHTML = sortedWatchlist.map(item => {
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

    const score = Number(item.score ?? item.Score ?? 0);
    let scoreBadgeClass = "badge-danger";
    if (score >= 80) {
      scoreBadgeClass = "badge-success";
    } else if (score >= 60) {
      scoreBadgeClass = "badge-warning";
    }
    const scoreBadge = `<span class="badge ${scoreBadgeClass}">${score}</span>`;

    const grade = item.grade ?? item.Grade ?? "C";
    let gradeBadgeClass = "badge-neutral";
    if (grade === "A+" || grade === "A") gradeBadgeClass = "badge-success";
    else if (grade === "B") gradeBadgeClass = "badge-warning";
    else if (grade === "C") gradeBadgeClass = "badge-danger";
    const gradeBadge = `<span class="badge ${gradeBadgeClass}">${grade}</span>`;

    return `
      <tr class="watchlist-row ${rowClass}" data-symbol="${item.Symbol}" title="Click to view 6-month chart & checklist">
        <td>
          <div style="display: flex; align-items: center; justify-content: space-between; gap: 8px;">
            <strong>${item.Symbol}</strong>
            <span class="chevron" style="font-size: 10px; color: var(--text-dim);">▼</span>
          </div>
        </td>
        <td>${scoreBadge}</td>
        <td>${gradeBadge}</td>
        <td>${formatINR(item.Close)}</td>
        <td><strong>${dist.toFixed(2)}%</strong> away</td>
        <td>${coilingBadge}</td>
        <td><span class="badge badge-neutral">${item.Sector || "^NSEI"}</span></td>
        <td>${bullishBadge}</td>
      </tr>
    `;
  }).join("");

  // Attach click listeners for expandable details
  watchlistBody.querySelectorAll(".watchlist-row").forEach(row => {
    row.addEventListener("click", () => {
      const sym = row.getAttribute("data-symbol");
      const item = sortedWatchlist.find(w => w.Symbol === sym);
      if (item) {
        toggleWatchlistDetail(row, item, scanData);
      }
    });
  });
}

// =====================================================================
// EXPANDABLE WATCHLIST DETAIL PANEL & CANVAS MINI-CHART
// =====================================================================

// Extract known earnings if within next 7 days, else returns null
function extractEarningsDays(chartData, item) {
  if (item && item.earnings_in_days != null && item.earnings_in_days >= 0 && item.earnings_in_days <= 7) {
    return item.earnings_in_days;
  }
  const events = chartData?.chart?.result?.[0]?.events;
  if (events && events.earnings) {
    const nowSec = Date.now() / 1000;
    const sevenDaysSec = 7 * 86400;
    const earningsList = Object.values(events.earnings);
    for (const e of earningsList) {
      const eDate = e.date || e.startdate || e.timestamp;
      if (eDate && eDate >= nowSec && eDate <= nowSec + sevenDaysSec) {
        return Math.max(1, Math.ceil((eDate - nowSec) / 86400));
      }
    }
  }
  return null;
}

// Fetch 6-month chart data from Yahoo with localStorage cache keyed by symbol+date
async function fetchChartData(symbol) {
  const cleanSym = symbol.endsWith(".NS") ? symbol : `${symbol}.NS`;
  const today = new Date().toISOString().slice(0, 10);
  const cacheKey = `chart_${cleanSym}_${today}`;

  // Check localStorage cache first
  const cached = localStorage.getItem(cacheKey);
  if (cached) {
    try {
      return JSON.parse(cached);
    } catch (e) {
      localStorage.removeItem(cacheKey);
    }
  }

  const directUrl = `https://query1.finance.yahoo.com/v8/finance/chart/${cleanSym}?interval=1d&range=6mo`;
  let data = null;

  try {
    const res = await fetch(directUrl);
    if (res.ok) {
      data = await res.json();
    }
  } catch (err) {
    console.warn("Direct Yahoo fetch failed, trying proxy fallback:", err);
  }

  // Graceful fallback proxies if direct fetch has CORS restriction in client browser
  if (!data || !data.chart || !data.chart.result) {
    const proxies = [
      `https://corsproxy.io/?url=${encodeURIComponent(directUrl)}`,
      `https://api.allorigins.win/raw?url=${encodeURIComponent(directUrl)}`
    ];
    for (const pUrl of proxies) {
      try {
        const res = await fetch(pUrl);
        if (res.ok) {
          data = await res.json();
          if (data && data.chart && data.chart.result) break;
        }
      } catch (e) {
        // try next
      }
    }
  }

  if (data && data.chart && data.chart.result && data.chart.result.length > 0) {
    try {
      localStorage.setItem(cacheKey, JSON.stringify(data));
    } catch (e) {
      console.warn("localStorage quota write notice:", e);
    }
    return data;
  }
  return null;
}

// Standard Wilder's RSI calculation helper
function calculateRSI(closes, period = 14) {
  if (!closes || closes.length <= period) return 50;
  let gains = 0;
  let losses = 0;
  for (let i = 1; i <= period; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff >= 0) gains += diff;
    else losses -= diff;
  }
  let avgGain = gains / period;
  let avgLoss = losses / period;

  for (let i = period + 1; i < closes.length; i++) {
    const diff = closes[i] - closes[i - 1];
    if (diff >= 0) {
      avgGain = (avgGain * (period - 1) + diff) / period;
      avgLoss = (avgLoss * (period - 1)) / period;
    } else {
      avgGain = (avgGain * (period - 1)) / period;
      avgLoss = (avgLoss * (period - 1) - diff) / period;
    }
  }

  if (avgLoss === 0) return 100;
  const rs = avgGain / avgLoss;
  return 100 - (100 / (1 + rs));
}

// Plain HTML5 Canvas Mini-Chart Renderer with SMA50, SMA200, Breakout Line, and Volume Subplot
function drawMiniChart(canvas, candles, breakoutLevel, symbol) {
  const container = canvas.parentElement;
  const width = Math.max(300, container.clientWidth || 800);
  const height = 280;
  const dpr = window.devicePixelRatio || 1;

  canvas.width = width * dpr;
  canvas.height = height * dpr;
  canvas.style.width = `${width}px`;
  canvas.style.height = `${height}px`;

  // Retain data reference for seamless redraw on window resize
  canvas._candles = candles;
  canvas._breakoutLevel = breakoutLevel;
  canvas._symbol = symbol;

  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);

  const n = candles.length;
  if (n === 0) return;

  const marginTop = 22;
  const priceHeight = 170;
  const priceBottom = marginTop + priceHeight;
  const volumeGap = 16;
  const volumeTop = priceBottom + volumeGap;
  const volumeHeight = 44;
  const volumeBottom = volumeTop + volumeHeight;
  const marginLeft = 14;
  const marginRight = 74;
  const plotWidth = width - marginLeft - marginRight;

  const barStep = plotWidth / n;
  const barWidth = Math.max(1.5, Math.min(8, barStep * 0.68));

  // Determine min & max price bounds including breakout level
  let minPrice = Infinity;
  let maxPrice = -Infinity;
  for (const c of candles) {
    if (c.low < minPrice) minPrice = c.low;
    if (c.high > maxPrice) maxPrice = c.high;
  }
  if (breakoutLevel && !isNaN(breakoutLevel)) {
    minPrice = Math.min(minPrice, breakoutLevel);
    maxPrice = Math.max(maxPrice, breakoutLevel);
  }

  const priceRange = (maxPrice - minPrice) || 1;
  const pMin = minPrice - priceRange * 0.05;
  const pMax = maxPrice + priceRange * 0.05;
  const pSpan = pMax - pMin;

  function priceToY(p) {
    return priceBottom - ((p - pMin) / pSpan) * priceHeight;
  }

  // Calculate SMA 50 and SMA 200
  const sma50 = [];
  const sma200 = [];
  for (let i = 0; i < n; i++) {
    // SMA 50
    if (i >= 49) {
      let sum50 = 0;
      for (let j = i - 49; j <= i; j++) sum50 += candles[j].close;
      sma50.push(sum50 / 50);
    } else if (i >= 5) {
      let sumProg = 0;
      for (let j = 0; j <= i; j++) sumProg += candles[j].close;
      sma50.push(sumProg / (i + 1));
    } else {
      sma50.push(null);
    }

    // SMA 200 (uses full 200 if present or progressive rolling if in 6mo chart)
    if (i >= 199) {
      let sum200 = 0;
      for (let j = i - 199; j <= i; j++) sum200 += candles[j].close;
      sma200.push(sum200 / 200);
    } else if (i >= 15) {
      let sumProg = 0;
      for (let j = 0; j <= i; j++) sumProg += candles[j].close;
      sma200.push(sumProg / (i + 1));
    } else {
      sma200.push(null);
    }
  }

  // Max volume for volume subplot
  let maxVol = 0;
  for (const c of candles) {
    if (c.volume > maxVol) maxVol = c.volume;
  }
  maxVol = maxVol || 1;

  function volToH(v) {
    return Math.max(1, (v / maxVol) * volumeHeight);
  }

  // 1. Grid Lines & Price Ticks
  ctx.strokeStyle = "rgba(255, 255, 255, 0.06)";
  ctx.lineWidth = 1;
  ctx.fillStyle = "#64748b";
  ctx.font = "10px Inter, sans-serif";
  ctx.textAlign = "left";

  const numGridTicks = 4;
  for (let t = 0; t <= numGridTicks; t++) {
    const p = pMin + (pSpan / numGridTicks) * t;
    const y = priceToY(p);
    ctx.beginPath();
    ctx.moveTo(marginLeft, y);
    ctx.lineTo(width - marginRight, y);
    ctx.stroke();
    ctx.fillText("₹" + p.toFixed(1), width - marginRight + 6, y + 3);
  }

  // Volume separator line & label
  ctx.beginPath();
  ctx.moveTo(marginLeft, volumeTop - 4);
  ctx.lineTo(width - marginRight, volumeTop - 4);
  ctx.stroke();
  ctx.fillText("Vol", width - marginRight + 6, volumeTop + 14);

  // 2. Volume Subplot Bars
  for (let i = 0; i < n; i++) {
    const c = candles[i];
    const x = marginLeft + i * barStep + barStep / 2;
    const h = volToH(c.volume);
    const y = volumeBottom - h;
    ctx.fillStyle = c.close >= c.open ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)";
    ctx.fillRect(x - barWidth / 2, y, barWidth, h);
  }

  // 3. Candlesticks (Price)
  for (let i = 0; i < n; i++) {
    const c = candles[i];
    const x = marginLeft + i * barStep + barStep / 2;
    const isGreen = c.close >= c.open;
    const color = isGreen ? "#10b981" : "#ef4444";

    // Wick line
    const highY = priceToY(c.high);
    const lowY = priceToY(c.low);
    ctx.strokeStyle = color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(x, highY);
    ctx.lineTo(x, lowY);
    ctx.stroke();

    // Body rectangle
    const openY = priceToY(c.open);
    const closeY = priceToY(c.close);
    const bodyTop = Math.min(openY, closeY);
    const bodyH = Math.max(1.5, Math.abs(closeY - openY));
    ctx.fillStyle = color;
    ctx.fillRect(x - barWidth / 2, bodyTop, barWidth, bodyH);
  }

  // 4. Overlay SMA 50 (Orange)
  ctx.strokeStyle = "#f97316";
  ctx.lineWidth = 2;
  ctx.beginPath();
  let sma50Started = false;
  for (let i = 0; i < n; i++) {
    if (sma50[i] != null) {
      const x = marginLeft + i * barStep + barStep / 2;
      const y = priceToY(sma50[i]);
      if (!sma50Started) {
        ctx.moveTo(x, y);
        sma50Started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
  }
  ctx.stroke();

  // 5. Overlay SMA 200 (Blue)
  ctx.strokeStyle = "#3b82f6";
  ctx.lineWidth = 2;
  ctx.beginPath();
  let sma200Started = false;
  for (let i = 0; i < n; i++) {
    if (sma200[i] != null) {
      const x = marginLeft + i * barStep + barStep / 2;
      const y = priceToY(sma200[i]);
      if (!sma200Started) {
        ctx.moveTo(x, y);
        sma200Started = true;
      } else {
        ctx.lineTo(x, y);
      }
    }
  }
  ctx.stroke();

  // 6. Horizontal Dashed Line at 20-Day Breakout Level
  if (breakoutLevel && !isNaN(breakoutLevel)) {
    const bY = priceToY(breakoutLevel);
    ctx.strokeStyle = "#ef4444";
    ctx.lineWidth = 1.5;
    ctx.setLineDash([5, 4]);
    ctx.beginPath();
    ctx.moveTo(marginLeft, bY);
    ctx.lineTo(width - marginRight, bY);
    ctx.stroke();
    ctx.setLineDash([]);

    // Breakout text badge on right
    ctx.fillStyle = "#ef4444";
    ctx.font = "bold 10px Inter, sans-serif";
    ctx.fillText("Breakout", width - marginRight + 6, bY - 3);
    ctx.fillStyle = "#fca5a5";
    ctx.font = "9px Inter, sans-serif";
    ctx.fillText("₹" + breakoutLevel.toFixed(1), width - marginRight + 6, bY + 9);
  }

  // 7. Date Ticks on Bottom Axis
  ctx.fillStyle = "#64748b";
  ctx.font = "10px Inter, sans-serif";
  ctx.textAlign = "center";
  const dateStep = Math.max(1, Math.floor(n / 4));
  for (let i = 0; i < n; i += dateStep) {
    if (candles[i] && candles[i].time) {
      const d = new Date(candles[i].time * 1000);
      const str = d.toLocaleDateString("en-IN", { month: "short", day: "numeric" });
      const x = marginLeft + i * barStep + barStep / 2;
      ctx.fillText(str, x, height - 3);
    }
  }
}

// Toggle detail row below the clicked stock row
async function toggleWatchlistDetail(row, item, scanData) {
  const symbol = item.Symbol;
  const existingDetail = document.getElementById(`detail-${symbol}`);

  // If already open, collapse it
  if (existingDetail) {
    existingDetail.remove();
    row.classList.remove("expanded");
    const chevron = row.querySelector(".chevron");
    if (chevron) chevron.textContent = "▼";
    return;
  }

  // Close other open detail rows to keep view tidy
  document.querySelectorAll(".detail-row").forEach(el => el.remove());
  document.querySelectorAll(".watchlist-row.expanded").forEach(el => {
    el.classList.remove("expanded");
    const ch = el.querySelector(".chevron");
    if (ch) ch.textContent = "▼";
  });

  row.classList.add("expanded");
  const chevron = row.querySelector(".chevron");
  if (chevron) chevron.textContent = "▲";

  // Initial checklist values
  const trendPass = item.Trend === "YES";
  const setupPass = item.Coiling === "YES";
  const secPass = item.SectorBullish === "YES";
  const mktPass = Boolean(scanData && scanData.market_ok);
  const volPassInit = item.VolDryup === "YES";
  const rsiPassInit = item.RsiInRange === "YES";

  const detailHtml = `
    <tr class="detail-row" id="detail-${symbol}">
      <td colspan="8">
        <div class="stock-detail-panel">
          <div class="detail-header">
            <div class="detail-title-group">
              <span class="detail-symbol">${symbol}</span>
              <span class="badge badge-neutral">${item.Sector || "^NSEI"}</span>
              <span class="badge badge-success">₹${item.Close || 0}</span>
              <span class="badge badge-warning">${parseFloat(item["DistToBreakout%"] || 0).toFixed(2)}% to Breakout</span>
              <span class="detail-hint">(Click row to collapse)</span>
            </div>
            <div id="earnings-warn-${symbol}"></div>
          </div>

          <!-- Rules Checklist -->
          <div class="checklist-title">Setup Criteria Checklist</div>
          <div class="checklist-grid" id="checklist-${symbol}">
            <div class="check-item ${trendPass ? 'pass' : 'fail'}">
              <span class="check-icon">${trendPass ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">Trend Filter</span>
                <span class="check-desc">Stage 2 Uptrend (Close > SMA50 > SMA200)</span>
              </div>
              <span class="check-status">${trendPass ? 'Passed (+25)' : 'Failed (0)'}</span>
            </div>

            <div class="check-item ${setupPass ? 'pass' : 'fail'}">
              <span class="check-icon">${setupPass ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">Setup (Coiling)</span>
                <span class="check-desc">Vol contraction & range tightness</span>
              </div>
              <span class="check-status">${setupPass ? 'Passed (+15)' : 'Failed (0)'}</span>
            </div>

            <div class="check-item ${secPass ? 'pass' : 'fail'}">
              <span class="check-icon">${secPass ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">Sector Bullish</span>
                <span class="check-desc">${item.Sector || '^NSEI'} active Stage 2 uptrend</span>
              </div>
              <span class="check-status">${secPass ? 'Passed (+15)' : 'Failed (0)'}</span>
            </div>

            <div class="check-item ${mktPass ? 'pass' : 'fail'}">
              <span class="check-icon">${mktPass ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">Market OK (M-Rule)</span>
                <span class="check-desc">NIFTY 50 Benchmark Uptrend</span>
              </div>
              <span class="check-status">${mktPass ? 'Passed (+5)' : 'Failed (Capped ≤50)'}</span>
            </div>

            <div class="check-item ${volPassInit ? 'pass' : 'fail'}" id="vol-check-${symbol}">
              <span class="check-icon">${volPassInit ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">Volume Dry-Up</span>
                <span class="check-desc">VOL5 < 80% of VOL50</span>
              </div>
              <span class="check-status">${volPassInit ? 'Passed (+10)' : 'Failed (0)'}</span>
            </div>

            <div class="check-item ${rsiPassInit ? 'pass' : 'fail'}" id="rsi-check-${symbol}">
              <span class="check-icon">${rsiPassInit ? '✅' : '❌'}</span>
              <div class="check-info">
                <span class="check-label">RSI In Range (40-65)</span>
                <span class="check-desc">Momentum healthy, not overbought</span>
              </div>
              <span class="check-status">${rsiPassInit ? 'Passed (+10)' : 'Failed (0)'}</span>
            </div>
          </div>

          <!-- Chart Section -->
          <div class="detail-chart-section">
            <div class="chart-top-bar">
              <div class="chart-title-legend">
                <span class="chart-heading">6-Month Daily Candles</span>
                <span class="legend-item"><span class="legend-dot sma50-dot"></span> SMA 50</span>
                <span class="legend-item"><span class="legend-dot sma200-dot"></span> SMA 200</span>
                <span class="legend-item"><span class="legend-line breakout-line"></span> 20D Breakout</span>
              </div>
              <div class="chart-meta-stats" id="chart-meta-${symbol}">Loading 6-month chart...</div>
            </div>
            <div class="canvas-wrapper" style="position: relative; width: 100%; height: 280px;">
              <canvas id="canvas-${symbol}" class="mini-chart-canvas"></canvas>
              <div id="chart-loader-${symbol}" class="chart-loading-overlay">
                <div class="spinner"></div>
                <span>Fetching 6-month daily data from Yahoo Finance...</span>
              </div>
            </div>
          </div>
        </div>
      </td>
    </tr>
  `;

  row.insertAdjacentHTML("afterend", detailHtml);

  // Default breakout level from item
  const distPct = parseFloat(item["DistToBreakout%"]) || 0;
  const initialBreakout = item.Close ? item.Close * (1 + distPct / 100) : null;

  try {
    const chartData = await fetchChartData(symbol);
    const canvas = document.getElementById(`canvas-${symbol}`);
    const loader = document.getElementById(`chart-loader-${symbol}`);
    const metaEl = document.getElementById(`chart-meta-${symbol}`);
    const warnEl = document.getElementById(`earnings-warn-${symbol}`);

    if (!canvas) return; // closed before fetch resolved

    if (loader) loader.style.display = "none";

    if (!chartData || !chartData.chart || !chartData.chart.result || chartData.chart.result.length === 0) {
      if (metaEl) metaEl.textContent = "Chart unavailable (Yahoo API rate limit or network error)";
      return;
    }

    const res = chartData.chart.result[0];
    const timestamps = res.timestamp || [];
    const quote = res.indicators?.quote?.[0] || {};
    const candles = [];

    for (let i = 0; i < timestamps.length; i++) {
      const o = quote.open?.[i];
      const h = quote.high?.[i];
      const l = quote.low?.[i];
      const c = quote.close?.[i];
      const v = quote.volume?.[i] || 0;
      if (o != null && h != null && l != null && c != null && !isNaN(c)) {
        candles.push({ time: timestamps[i], open: o, high: h, low: l, close: c, volume: v });
      }
    }

    if (candles.length === 0) {
      if (metaEl) metaEl.textContent = "No valid trading candles returned.";
      return;
    }

    // Determine 20D breakout level from candles if available
    const last20 = candles.slice(-21, -1);
    const calculatedBreakout = last20.length > 0 ? Math.max(...last20.map(c => c.high)) : initialBreakout;
    const finalBreakout = calculatedBreakout || initialBreakout;

    // Check earnings within next 7 days
    const earningsDays = extractEarningsDays(chartData, item);
    if (earningsDays !== null && warnEl) {
      warnEl.innerHTML = `<div class="earnings-warning-banner">⚠️ Earnings in ${earningsDays} day${earningsDays === 1 ? '' : 's'}</div>`;
    }

    // Live validation for VolDryup / RsiInRange if not pre-populated
    if (item.VolDryup === undefined && candles.length >= 50) {
      const vol5 = candles.slice(-5).reduce((s, c) => s + c.volume, 0) / 5;
      const vol50 = candles.slice(-50).reduce((s, c) => s + c.volume, 0) / 50;
      const volPass = vol5 < 0.8 * vol50;
      const el = document.getElementById(`vol-check-${symbol}`);
      if (el) {
        el.className = `check-item ${volPass ? 'pass' : 'fail'}`;
        el.querySelector(".check-icon").textContent = volPass ? '✅' : '❌';
        el.querySelector(".check-status").textContent = volPass ? 'Passed (+10)' : 'Failed (0)';
      }
    }

    if (item.RsiInRange === undefined && candles.length >= 15) {
      const closes = candles.map(c => c.close);
      const rsi = calculateRSI(closes, 14);
      const rsiPass = rsi >= 40 && rsi <= 65;
      const el = document.getElementById(`rsi-check-${symbol}`);
      if (el) {
        el.className = `check-item ${rsiPass ? 'pass' : 'fail'}`;
        el.querySelector(".check-icon").textContent = rsiPass ? '✅' : '❌';
        el.querySelector(".check-status").textContent = rsiPass ? `Passed (RSI ${rsi.toFixed(1)})` : `Failed (RSI ${rsi.toFixed(1)})`;
      }
    }

    // Draw the chart on HTML5 canvas
    drawMiniChart(canvas, candles, finalBreakout, symbol);

    if (metaEl) {
      const lastCandle = candles[candles.length - 1];
      metaEl.textContent = `${candles.length} trading days • Close: ₹${lastCandle.close.toFixed(2)} • 20D Breakout: ₹${finalBreakout.toFixed(2)}`;
    }
  } catch (err) {
    console.error("Error loading mini chart:", err);
    const metaEl = document.getElementById(`chart-meta-${symbol}`);
    if (metaEl) metaEl.textContent = "Error rendering chart: " + err.message;
  }
}

// Redraw open detail canvases on window resize
window.addEventListener("resize", () => {
  document.querySelectorAll(".detail-row").forEach(detailRow => {
    const canvas = detailRow.querySelector("canvas");
    if (canvas && canvas._candles) {
      drawMiniChart(canvas, canvas._candles, canvas._breakoutLevel, canvas._symbol);
    }
  });
});

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
