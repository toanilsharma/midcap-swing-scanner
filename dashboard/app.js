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

// =====================================================================
// SITE-WIDE TERMS & DEFINITIONS DICTIONARY
// =====================================================================
const TERMS = {
  // Moving Averages & Trend
  "SMA50": {
    short: "50-day Simple Moving Average representing 10 weeks of institutional price trend.",
    long: "The 50-day Simple Moving Average calculates the mean closing price over the last 10 calendar weeks. In Minervini Stage 2 uptrends, leading stocks stay above their rising SMA 50, which serves as primary institutional support.",
    where_used: "Near Buy (Trend Filter), Help Guide",
    anchor: "glossary-sma50"
  },
  "SMA150": {
    short: "150-day Simple Moving Average tracking intermediate-term institutional support.",
    long: "The 150-day Simple Moving Average reflects roughly 7 months of price action. It validates healthy intermediate trend structure by staying positioned between the 50 SMA and 200 SMA in Stage 2 leaders.",
    where_used: "Near Buy (Trend Filter), Help Guide",
    anchor: "glossary-sma150"
  },
  "SMA200": {
    short: "200-day Simple Moving Average defining the macro boundary between bull and bear trends.",
    long: "The premier long-term benchmark average representing ~10 months of trading. Minervini rules require the 200 SMA to be trending up for at least 1 month before taking any long swing trades.",
    where_used: "Near Buy (Trend Filter), Help Guide",
    anchor: "glossary-sma200"
  },
  "EMA10": {
    short: "10-period Exponential Moving Average used as our mechanical trailing stop line.",
    long: "A fast moving average heavily weighted toward recent prices. Once a winning swing trade surpasses its initial 2R target, we trail our stop loss along the daily 10 EMA to ride multi-week momentum runners.",
    where_used: "Open Positions, Trade Management, Help Guide",
    anchor: "glossary-ema10"
  },
  "EMA20": {
    short: "20-period Exponential Moving Average capturing short-term pullbacks and base support.",
    long: "The 20-period Exponential Moving Average approximates a 1-month trading trend. Strong momentum stocks routinely test and bounce off their rising 20 EMA while forming volatility squeezes.",
    where_used: "Indicators, Mini Charts, Help Guide",
    anchor: "glossary-ema20"
  },
  "ATR14": {
    short: "14-day Average True Range measuring true daily volatility in rupees.",
    long: "ATR measures the average rupee swing per session, accounting for overnight gap moves. It allows us to set dynamic, volatility-based stop losses rather than using arbitrary percentage stops.",
    where_used: "Position Sizer, Watchlist, Help Guide",
    anchor: "glossary-atr14"
  },
  "RSI14": {
    short: "Standard 14-day Relative Strength Index oscillator filtering momentum extremes.",
    long: "Bounded between 0 and 100, RSI14 measures the magnitude of recent gains versus losses. Our scanner rewards candidates with RSI14 between 40 and 65, ensuring positive momentum without chasing overbought tops.",
    where_used: "Near Buy (Score Filter), Help Guide",
    anchor: "glossary-rsi14"
  },
  "RSI2": {
    short: "Ultra-fast 2-period RSI oscillator designed to spot short-term rubber-band dips.",
    long: "Popularized by Larry Connors, 2-period RSI drops into extreme oversold territory (<10) during quick 2-3 day pullbacks. Buying the subsequent green reversal candle offers exceptional reward-to-risk asymmetry.",
    where_used: "Pullback Setup, Help Guide",
    anchor: "glossary-rsi2"
  },
  "Volume": {
    short: "Total number of shares transacted during a trading day.",
    long: "Volume confirms the validity of price movements. Without volume, price breakouts lack genuine institutional sponsorship and frequently fail due to low liquidity.",
    where_used: "Turnover Filter, Volume Dry-up, Help Guide",
    anchor: "glossary-volume"
  },
  "Volume dry-up": {
    short: "Trading activity shrinking below 80% of normal, proving sellers are exhausted.",
    long: "When 5-day average volume drops below 80% of the 50-day average, supply has completely dried up. With few shares left for sale, it takes minimal buyer interest to trigger an explosive breakout.",
    where_used: "Near Buy (Coiling Setup), Help Guide",
    anchor: "glossary-volumedryup"
  },
  "50-day average volume": {
    short: "The 50-session moving average of volume acting as our liquidity baseline.",
    long: "Calculates baseline turnover and participation. Serves as the quantitative yardstick against which both volume dry-ups (<80%) and breakout volume spikes (>150%) are measured.",
    where_used: "Near Buy Filter, Help Guide",
    anchor: "glossary-vol50"
  },
  "VCP / coiling": {
    short: "Volatility Contraction Pattern showing shrinking price swings and dried-up volume.",
    long: "Mark Minervini's signature institutional pattern where each successive pullback becomes shallower (e.g. -15% then -8% then -3%). When accompanied by volume dry-up, it indicates institutional absorption.",
    where_used: "Near Buy (Coiling Badge), Help Guide",
    anchor: "glossary-vcp"
  },
  "Coiling": {
    short: "A tight consolidation where price range and volume both contract significantly.",
    long: "Indicates that buyers and sellers have reached price equilibrium under resistance. A 'Coiling: YES' tag confirms the stock is spring-loaded and eligible for immediate breakout triggers.",
    where_used: "Near Buy Table Header & Badges, Help Guide",
    anchor: "glossary-vcp"
  },
  "price contraction": {
    short: "Daily candle trading range narrowing below 80% of historical average range.",
    long: "Measured as 5-day average high-low range dropping below 80% of the 50-day range. Confirms volatility compression before a rapid expansion in price.",
    where_used: "Near Buy (VCP Setup), Help Guide",
    anchor: "glossary-pricecontraction"
  },
  "20-day breakout level": {
    short: "The highest intra-day price reached across the previous 20 trading sessions.",
    long: "Represents the overhead resistance level that trapped prior buyers. Penetrating this level on high volume signals that all overhead sellers are cleared.",
    where_used: "Near Buy Table, Mini Charts, Help Guide",
    anchor: "glossary-high20"
  },
  "breakout": {
    short: "Price crossing and closing above a critical resistance ceiling on heavy volume.",
    long: "A valid breakout occurs when a coiled Stage 2 stock closes above its 20-day high on volume >1.5x average. It triggers our automated /buy signal on Telegram.",
    where_used: "Signals Table, Telegram Alerts, Help Guide",
    anchor: "glossary-breakout"
  },
  "volume spike": {
    short: "Daily volume exceeding 1.5 times the 50-day average volume.",
    long: "The indispensable fuel behind every genuine breakout. Institutional funds cannot enter or accumulate a stock quietly on a breakout without creating an obvious volume spike.",
    where_used: "Breakout Confirmation, Help Guide",
    anchor: "glossary-volumespike"
  },
  "strong close": {
    short: "Session candle finishing in the top 40% of its daily high-to-low range.",
    long: "Calculated as (Close - Low) / (High - Low) > 0.60. Filters out intraday upper rejection wicks and proves that buyers retained aggressive control into the closing bell.",
    where_used: "Signal Confirmation, Help Guide",
    anchor: "glossary-strongclose"
  },
  "52-week high and low": {
    short: "The annual peak and trough prices defining the stock's 1-year trading boundary.",
    long: "Minervini Stage 2 criteria require price to trade at least 30% above its 52-week low and within 25% of its 52-week high. Winning swing trades emerge near 52-week highs, not lows.",
    where_used: "Trend Filter, Help Guide",
    anchor: "glossary-52whighlow"
  },
  "Relative Strength vs index": {
    short: "Outperformance of an individual stock compared to the NIFTY 50 benchmark.",
    long: "Stocks with high Relative Strength resist market sell-offs and reach new highs first. Our strategy focuses strictly on market leaders with sector and index outperformance.",
    where_used: "Trend Ranking, Help Guide",
    anchor: "glossary-rs"
  },
  "Sector filter": {
    short: "Requirement that the stock's industry sector index is also in an active Stage 2 uptrend.",
    long: "Verifies that the stock's broader industry index (e.g. NIFTY IT, NIFTY Bank) is trading above its 50 and 200 SMAs. Prevents buying isolated winners in declining sector groups.",
    where_used: "Near Buy (Sector Bullish), Help Guide",
    anchor: "glossary-sectorfilter"
  },
  "Sector Bullish": {
    short: "Confirmation that the stock's sector index is in an active Stage 2 uptrend.",
    long: "Displays 'YES' if the company's sector index satisfies Close > SMA50 > SMA200. Adds +15 points to the Setup Score and is required for Grade A and A+ status.",
    where_used: "Near Buy Table Column & Badges, Help Guide",
    anchor: "glossary-sectorfilter"
  },
  "Market regime (M-rule)": {
    short: "O'Neil benchmark index filter based on NIFTY 50 moving averages.",
    long: "75% of individual stocks follow the broader market trend. If the NIFTY 50 index falls below its 50 or 200 SMA, the market flips to Defensive, capping all scores at 50 and blocking buy signals.",
    where_used: "Top Bar Market Badge, Regime Banner, Help Guide",
    anchor: "glossary-mrule"
  },
  "Market regime": {
    short: "Macro market environment filter: Uptrend (trading permitted) vs Defensive (cash only).",
    long: "Evaluates whether NIFTY 50 is trading cleanly above its 50-day and 200-day moving averages. If market conditions deteriorate, capital preservation mandates holding cash.",
    where_used: "Top Bar Header, Near Buy Tab, Help Guide",
    anchor: "glossary-mrule"
  },
  "Defensive": {
    short: "Market regime indicating benchmark downtrend; cash is held to protect capital.",
    long: "When NIFTY 50 breaks below key moving averages, the terminal badge displays 'Market: Defensive'. All setup scores are capped at 50 and no new purchases are allowed.",
    where_used: "Market Badge, Regime Banner, FAQ, Help Guide",
    anchor: "glossary-mrule"
  },
  "Distance to breakout": {
    short: "Percentage distance from current closing price to the 20-day high resistance level.",
    long: "Stocks within 0-2% of breakout receive top priority for immediate entry. Stocks between 2% and 5% are kept on the watchlist for observation.",
    where_used: "Near Buy Table, Score Calculation, Help Guide",
    anchor: "glossary-dist"
  },
  "Dist to Breakout": {
    short: "Percentage distance remaining before the stock reaches its 20-day breakout trigger.",
    long: "Quantifies how close the setup is to breaking out. Scaled into the Setup Score (up to +20 points for candidates within 2% of the breakout line).",
    where_used: "Near Buy Table Header, Help Guide",
    anchor: "glossary-dist"
  },
  "Setup window": {
    short: "10-day lookback buffer during which a prior coiling pattern remains valid.",
    long: "Breakouts do not always trigger on the exact session a stock finishes coiling. A 10-day memory window ensures eligible setups are rewarded when the volume spike arrives.",
    where_used: "Scanner Engine, Help Guide",
    anchor: "glossary-setupwindow"
  },
  "Stop loss": {
    short: "Predefined price level where a trade is automatically liquidated to prevent major losses.",
    long: "Calculated dynamically as Entry minus 1.5x ATR, capped at a maximum of 7% from entry. Strictly executed without hesitation or emotional debate.",
    where_used: "Position Sizer, Open Positions, Help Guide",
    anchor: "glossary-stoploss"
  },
  "1.5x ATR stop": {
    short: "Dynamic stop loss buffer set at 1.5 times the 14-day Average True Range below entry.",
    long: "Adapts stop loss distance to the specific volatility of the stock, preventing normal intraday noise from triggering premature exits.",
    where_used: "Signal Generation, Position Sizer, Help Guide",
    anchor: "glossary-15atr"
  },
  "7% max stop": {
    short: "Absolute hard ceiling capping initial stop loss distance at 7% from entry price.",
    long: "Even if ATR volatility would dictate a wider buffer, the system clamps the stop loss at 7% below entry to maintain favorable expectancy and prevent outsized losses.",
    where_used: "Signal Generation, Position Sizer, Help Guide",
    anchor: "glossary-maxstop"
  },
  "Target": {
    short: "Pre-planned exit price where profits are locked in at a 2:1 reward-to-risk ratio.",
    long: "Set at Entry + 2 * (Entry - Stop). Exiting at predefined 2R targets ensures consistent profitability even when win rate hovers around 45-50%.",
    where_used: "Position Sizer, Open Positions, Help Guide",
    anchor: "glossary-target"
  },
  "2R": {
    short: "Profit target delivering exactly twice the rupee risk taken on the trade.",
    long: "A 2R target produces asymmetric returns: risking ₹1,000 to make ₹2,000. This mathematical asymmetry is the bedrock of profitable swing trading.",
    where_used: "Position Sizer, Open Positions, Help Guide",
    anchor: "glossary-2rtarget"
  },
  "R-multiple": {
    short: "Trade outcome expressed as a multiple of initial risk (1R = Risk Budget).",
    long: "Normalizes performance across different stocks and account sizes. A win of +₹2,000 on a ₹1,000 risk trade is scored as +2.0R, while a stop loss is -1.0R.",
    where_used: "Trade History Table, Help Guide",
    anchor: "glossary-rmultiple"
  },
  "Position size": {
    short: "Exact number of shares to buy so potential loss equals your 1% risk budget.",
    long: "Calculated as floor((Capital * Risk%) / (Entry - Stop)). Sizing according to risk distance rather than capital allocation protects you from oversized losses on volatile stocks.",
    where_used: "Position Sizer, Signals Table, Help Guide",
    anchor: "glossary-positionsize"
  },
  "1% risk rule": {
    short: "Risking no more than 1% of total portfolio capital on any single swing trade.",
    long: "On a ₹100,000 capital account, max loss per trade is strictly capped at ₹1,000. Ensures survival across normal losing streaks without inflicting severe psychological damage.",
    where_used: "Position Sizer, Risk Commandments, Help Guide",
    anchor: "glossary-1percentsizing"
  },
  "Expectancy": {
    short: "Expected average rupee payoff per trade over a large series of trades.",
    long: "Formula: (Win% * AvgWin) - (Loss% * AvgLoss). A positive expectancy (e.g. >₹500 per trade) proves that your trading edge is mathematically sound and profitable.",
    where_used: "Performance Stats Tab, Help Guide",
    anchor: "glossary-expectancy"
  },
  "Win rate": {
    short: "The percentage of closed trades that resulted in a positive realized profit.",
    long: "Calculated as Winning Trades / Total Trades. Because our 2R target delivers twice what our stop loses, a 45-50% win rate generates steady capital growth.",
    where_used: "Performance Stats Tab, Help Guide",
    anchor: "glossary-winrate"
  },
  "Profit factor": {
    short: "Ratio of gross winning rupees divided by gross losing rupees across closed trades.",
    long: "A key health metric of any trading system. A profit factor above 1.5 indicates a robust, reliable edge, while values above 2.0 represent exceptional efficiency.",
    where_used: "Performance Stats Tab, Help Guide",
    anchor: "glossary-profitfactor"
  },
  "Max drawdown": {
    short: "The largest peak-to-trough decline in total portfolio capital.",
    long: "Quantifies the worst drawdown period experienced by the account. Strict adherence to 1% risk and 2% daily loss rules keeps drawdowns well under 8%.",
    where_used: "Performance Stats Tab, Help Guide",
    anchor: "glossary-maxdrawdown"
  },
  "Time stop": {
    short: "Discipline rule to cut a stagnant breakout after 5 trading days without follow-through.",
    long: "Genuine momentum breakouts follow through swiftly. If a stock trades sideways near entry for 5 trading sessions, we close the trade to liberate capital for better setups.",
    where_used: "Trade Management, Risk Commandments, Help Guide",
    anchor: "glossary-timestop"
  },
  "Breakeven ratchet": {
    short: "Moving stop loss up to entry price once trade reaches +8% unrealized profit.",
    long: "Eliminates downside risk by locking in a free trade once price rallies +8%. Guarantees that a substantial winning trade never turns into a losing trade.",
    where_used: "Trade Management, Help Guide",
    anchor: "glossary-breakeven"
  },
  "Breakeven": {
    short: "Adjusting your stop loss to the exact entry price to guarantee zero loss.",
    long: "Triggered mechanically at +8% gain. Once at breakeven, you hold the position risk-free while letting profits run toward the 2R target or 10 EMA trailing exit.",
    where_used: "Trade Management, Help Guide",
    anchor: "glossary-breakeven"
  },
  "Trailing stop (10 EMA)": {
    short: "Dynamic exit technique riding big winners until a session closes below the 10 EMA.",
    long: "Once a stock exceeds its initial 2R target, we hold until a daily candle closes below the rising 10 EMA line. This allows exceptional trends to turn into 3R+ mega winners.",
    where_used: "Trade Management, Help Guide",
    anchor: "glossary-trailingema10"
  },
  "Grade": {
    short: "Setup quality rating (A+, A, B, C) based on score and sector/market confirmation.",
    long: "Grade A+ (Score ≥80 with Bullish Sector & Market OK) and Grade A (Score ≥70 with Bullish Sector) represent top-tier setups. Grade B and C are for observation only.",
    where_used: "Near Buy Table, Signals Table, Help Guide",
    anchor: "glossary-gradescore"
  },
  "Setup score": {
    short: "Composite setup rating from 0 to 100 evaluating trend, coiling, volume, and sector.",
    long: "Combines 7 quantitative factors: Trend (+25), Breakout Proximity (+20), Coiling (+15), Sector (+15), Volume Dry-up (+10), RSI in range (+10), and Market filter (+5).",
    where_used: "Near Buy Table, Help Guide",
    anchor: "glossary-gradescore"
  },
  "Score": {
    short: "Composite setup score (0-100) ranking the statistical edge of each candidate.",
    long: "Scores 80+ indicate Grade A+ setups; scores 70-79 indicate Grade A setups. Directs attention and capital exclusively to the highest probability opportunities.",
    where_used: "Near Buy Table Column & Pills, Help Guide",
    anchor: "glossary-gradescore"
  },
  "Watchlist": {
    short: "Candidate stocks meeting Minervini Stage 2 criteria and within 5% of 20-day high.",
    long: "Refreshed after every market close. Provides early visibility into coiling stocks that are preparing to break out, allowing you to prepare order sizing in advance.",
    where_used: "Near Buy Tab, Help Guide",
    anchor: "glossary-dist"
  },
  "Open positions": {
    short: "Live swing trades currently active in the portfolio with active stops and targets.",
    long: "Monitored against daily market closes. Each position displays real-time paper PnL, percentage distance to protective stop loss, and percentage distance to 2R target.",
    where_used: "Open Positions Tab, Telegram /open, Help Guide",
    anchor: "glossary-positionsize"
  },
  "Unrealized PnL": {
    short: "Floating paper profit or loss on active open positions based on current prices.",
    long: "Reflects mark-to-market performance of active trades. Becomes Realized PnL only after closing the position with a /sell command.",
    where_used: "Open Positions Table & Summary Strip",
    anchor: "glossary-positionsize"
  },
  "Realized PnL": {
    short: "Net rupee profit or loss booked upon closing a position.",
    long: "Recorded in trades.json upon executing /sell. Forms the data points for the cumulative equity curve, win rate, and profit factor calculations.",
    where_used: "Trade History Table, Stats Tab, Help Guide",
    anchor: "glossary-expectancy"
  },
  "% to Stop": {
    short: "Percentage distance from the current price down to your protective stop loss.",
    long: "Highlights how close a position is to triggering its exit stop. Low values (<1.5%) indicate positions requiring defensive attention.",
    where_used: "Open Positions Table Column"
  },
  "% to Target": {
    short: "Percentage distance remaining from current price up to your 2R profit target.",
    long: "Shows progress toward your predefined exit target. As price approaches target, prepare to exit or activate the 10 EMA trailing stop.",
    where_used: "Open Positions Table Column"
  },
  "Equity curve": {
    short: "Cumulative line chart tracking total realized profits and losses over time.",
    long: "Visualizes the trajectory of your trading account. A rising equity curve with shallow pullbacks demonstrates a consistent statistical edge and sound risk management.",
    where_used: "Trade History Tab, Help Guide"
  }
};

// Safe HTML Escaper
function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

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
      <tr><td colspan="9" class="empty-state">No scan results found on GitHub repository.</td></tr>
    `;
    return;
  }

  // Update header metadata
  lastUpdated.textContent = `Updated: ${formatDateTime(scanData.updated_at)}`;

  if (scanData.market_ok) {
    marketBadge.className = "badge badge-success term-lookup";
    marketBadge.setAttribute("data-term", "Market regime");
    marketBadge.textContent = "Market: Uptrend";
    regimeBanner.className = "regime-banner uptrend";
    regimeText.textContent = "🟢 MARKET UPTREND CONFIRMED: Normal buy entry rules active.";
  } else {
    marketBadge.className = "badge badge-danger term-lookup";
    marketBadge.setAttribute("data-term", "Market regime");
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
      <tr><td colspan="9" class="empty-state">📋 Watchlist empty: no midcaps currently in uptrend within 5% of breakout.</td></tr>
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
      ? `<span class="badge badge-success term-lookup" data-term="Sector Bullish">YES</span>`
      : `<span class="badge badge-warning term-lookup" data-term="Sector Bullish">no</span>`;

    const coilingBadge = item.Coiling === "YES"
      ? `<span class="badge badge-success term-lookup" data-term="Coiling">Coiling</span>`
      : `<span class="badge badge-neutral term-lookup" data-term="Coiling">no</span>`;

    const score = Number(item.score ?? item.Score ?? 0);
    let scoreBadgeClass = "badge-danger";
    if (score >= 80) {
      scoreBadgeClass = "badge-success";
    } else if (score >= 60) {
      scoreBadgeClass = "badge-warning";
    }
    const scoreBadge = `<span class="badge ${scoreBadgeClass} term-lookup" data-term="Score">${score}</span>`;

    const grade = item.grade ?? item.Grade ?? "C";
    let gradeBadgeClass = "badge-neutral";
    if (grade === "A+" || grade === "A") gradeBadgeClass = "badge-success";
    else if (grade === "B") gradeBadgeClass = "badge-warning";
    else if (grade === "C") gradeBadgeClass = "badge-danger";
    const gradeBadge = `<span class="badge ${gradeBadgeClass} term-lookup" data-term="Grade">${grade}</span>`;

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
        <td>
          <button class="btn btn-xs btn-outline-primary size-trade-btn" data-symbol="${item.Symbol}" title="Size this trade with Position Sizer">
            Size this trade
          </button>
        </td>
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

  // Attach click listeners for "Size this trade" buttons on rows
  watchlistBody.querySelectorAll(".size-trade-btn").forEach(btn => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const sym = btn.getAttribute("data-symbol");
      const item = sortedWatchlist.find(w => w.Symbol === sym);
      if (item) {
        openPositionSizerFor(item);
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
      <td colspan="9">
        <div class="stock-detail-panel">
          <div class="detail-header">
            <div class="detail-title-group">
              <span class="detail-symbol">${symbol}</span>
              <span class="badge badge-neutral">${item.Sector || "^NSEI"}</span>
              <span class="badge badge-success">₹${item.Close || 0}</span>
              <span class="badge badge-warning">${parseFloat(item["DistToBreakout%"] || 0).toFixed(2)}% to Breakout</span>
              <button class="btn btn-sm btn-primary size-trade-btn" data-symbol="${symbol}">
                🎯 Size this trade
              </button>
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

  // Attach listener to "Size this trade" button inside the detail panel
  const detailEl = document.getElementById(`detail-${symbol}`);
  if (detailEl) {
    const detailSizeBtn = detailEl.querySelector(".size-trade-btn");
    if (detailSizeBtn) {
      detailSizeBtn.addEventListener("click", (e) => {
        e.stopPropagation();
        openPositionSizerFor(item);
      });
    }
  }

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

// =====================================================================
// POSITION SIZER & RISK CALCULATOR
// =====================================================================

// Open and pre-fill Position Sizer from a Watchlist row
function openPositionSizerFor(item) {
  if (!item) return;

  // 1. Switch tab to Open Positions
  const openTabBtn = document.querySelector('.tab-btn[data-tab="tabOpen"]');
  if (openTabBtn) {
    openTabBtn.click();
  }

  // 2. Pre-fill Entry and Stop
  const symbol = item.Symbol || "";
  const close = parseFloat(item.Close) || 0;
  const dist = parseFloat(item["DistToBreakout%"]) || 0;

  // Entry: breakout price if dist > 0, else current close
  const entryPrice = close > 0 ? (dist > 0 ? Number((close * (1 + dist / 100)).toFixed(2)) : Number(close.toFixed(2))) : 0;

  // Stop Loss: 1.5 * ATR14 floor at max 7% loss (or default 5% stop if ATR not available)
  let stopPrice = 0;
  if (entryPrice > 0) {
    if (item.ATR14 && !isNaN(item.ATR14)) {
      const atrStop = entryPrice - 1.5 * parseFloat(item.ATR14);
      const floorStop = entryPrice * 0.93; // 7% max stop loss rule
      stopPrice = Number(Math.max(floorStop, atrStop).toFixed(2));
    } else {
      stopPrice = Number((entryPrice * 0.95).toFixed(2));
    }
  }

  const symInput = document.getElementById("sizerSymbol");
  const entryInput = document.getElementById("sizerEntry");
  const stopInput = document.getElementById("sizerStop");

  if (symInput) symInput.value = symbol;
  if (entryInput) entryInput.value = entryPrice > 0 ? entryPrice : "";
  if (stopInput) stopInput.value = stopPrice > 0 ? stopPrice : "";

  // Auto-calculate outputs
  updatePositionSizer();

  // 3. Highlight and smooth scroll into view
  const card = document.getElementById("positionSizerCard");
  if (card) {
    card.scrollIntoView({ behavior: "smooth", block: "start" });
    card.classList.add("highlight-flash");
    setTimeout(() => card.classList.remove("highlight-flash"), 1500);
  }
}

// Auto-compute Position Sizer metrics & /buy command
function updatePositionSizer() {
  const symbolInput = document.getElementById("sizerSymbol");
  const capitalInput = document.getElementById("sizerCapital");
  const riskPctInput = document.getElementById("sizerRiskPct");
  const entryInput = document.getElementById("sizerEntry");
  const stopInput = document.getElementById("sizerStop");

  if (!capitalInput) return; // not mounted

  const symbol = (symbolInput?.value || "").trim().toUpperCase();
  const capital = parseFloat(capitalInput.value) || 0;
  const riskPct = parseFloat(riskPctInput.value) || 0;
  const entry = parseFloat(entryInput?.value) || 0;
  const stop = parseFloat(stopInput?.value) || 0;

  const riskPerUnitEl = document.getElementById("sizerRiskPerUnit");
  const qtyEl = document.getElementById("sizerQty");
  const maxLossEl = document.getElementById("sizerMaxLoss");
  const targetEl = document.getElementById("sizerTarget");
  const exposureEl = document.getElementById("sizerExposure");
  const cmdPreviewEl = document.getElementById("sizerCmdPreview");
  const errorEl = document.getElementById("sizerError");

  if (entry <= 0 || stop <= 0) {
    if (riskPerUnitEl) riskPerUnitEl.textContent = "₹0.00";
    if (qtyEl) qtyEl.textContent = "0 units";
    if (maxLossEl) maxLossEl.textContent = "₹0.00";
    if (targetEl) targetEl.textContent = "₹0.00";
    if (exposureEl) exposureEl.textContent = "₹0.00";
    if (cmdPreviewEl) cmdPreviewEl.textContent = `/buy ${symbol || "SYMBOL"} ${entry || 0} 0 ${stop || 0} 0`;
    if (errorEl) errorEl.style.display = "none";
    return;
  }

  if (stop >= entry) {
    if (riskPerUnitEl) riskPerUnitEl.textContent = "Invalid";
    if (qtyEl) qtyEl.textContent = "0 units";
    if (maxLossEl) maxLossEl.textContent = "₹0.00";
    if (targetEl) targetEl.textContent = "₹0.00";
    if (exposureEl) exposureEl.textContent = "₹0.00";
    if (errorEl) {
      errorEl.textContent = "⚠️ Stop Loss must be lower than Entry Price for a swing trade.";
      errorEl.style.display = "block";
    }
    if (cmdPreviewEl) cmdPreviewEl.textContent = `/buy ${symbol || "SYMBOL"} ${entry} 0 ${stop} 0`;
    return;
  }

  if (errorEl) errorEl.style.display = "none";

  const riskPerUnit = entry - stop;
  const maxRiskBudget = capital * (riskPct / 100);
  const suggestedQty = Math.floor(maxRiskBudget / riskPerUnit);
  const maxLoss = suggestedQty * riskPerUnit;
  const target = entry + (2 * riskPerUnit);
  const totalExposure = suggestedQty * entry;

  if (riskPerUnitEl) riskPerUnitEl.textContent = formatINR(riskPerUnit);
  if (qtyEl) qtyEl.textContent = `${suggestedQty} unit${suggestedQty === 1 ? "" : "s"}`;
  if (maxLossEl) maxLossEl.textContent = formatINR(maxLoss);
  if (targetEl) targetEl.textContent = formatINR(target);
  if (exposureEl) exposureEl.textContent = formatINR(totalExposure);

  const cleanEntry = Number(entry.toFixed(2));
  const cleanStop = Number(stop.toFixed(2));
  const cleanTarget = Number(target.toFixed(2));

  const cmdString = `/buy ${symbol || "SYMBOL"} ${cleanEntry} ${suggestedQty} ${cleanStop} ${cleanTarget}`;
  if (cmdPreviewEl) cmdPreviewEl.textContent = cmdString;
}

// Copy /buy command string to clipboard and show toast
async function copyBuyCommand() {
  const cmdPreviewEl = document.getElementById("sizerCmdPreview");
  const cmd = cmdPreviewEl ? cmdPreviewEl.textContent.trim() : "";
  if (!cmd) return;

  try {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      await navigator.clipboard.writeText(cmd);
    } else {
      const ta = document.createElement("textarea");
      ta.value = cmd;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
    }
    showToast("Copied!");
  } catch (err) {
    try {
      const ta = document.createElement("textarea");
      ta.value = cmd;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      showToast("Copied!");
    } catch (e2) {
      showToast("Copied!");
    }
  }
}

// Toast notification helper
function showToast(message) {
  let toastContainer = document.getElementById("toastContainer");
  if (!toastContainer) {
    toastContainer = document.createElement("div");
    toastContainer.id = "toastContainer";
    toastContainer.className = "toast-container";
    document.body.appendChild(toastContainer);
  }

  const toast = document.createElement("div");
  toast.className = "toast";
  toast.innerHTML = `<span style="font-size: 16px;">📋</span> <span>${message}</span>`;
  toastContainer.appendChild(toast);

  setTimeout(() => toast.classList.add("show"), 10);

  setTimeout(() => {
    toast.classList.remove("show");
    setTimeout(() => toast.remove(), 300);
  }, 2500);
}

// Initialize Position Sizer listeners & initial state
function initPositionSizer() {
  const capitalInput = document.getElementById("sizerCapital");
  const riskPctInput = document.getElementById("sizerRiskPct");
  const entryInput = document.getElementById("sizerEntry");
  const stopInput = document.getElementById("sizerStop");
  const symbolInput = document.getElementById("sizerSymbol");
  const resetBtn = document.getElementById("sizerResetBtn");
  const copyBtn = document.getElementById("copyBuyCmdBtn");

  if (!capitalInput) return;

  const inputs = [capitalInput, riskPctInput, entryInput, stopInput, symbolInput];
  inputs.forEach(inp => {
    if (inp) {
      inp.addEventListener("input", updatePositionSizer);
      inp.addEventListener("change", updatePositionSizer);
    }
  });

  if (resetBtn) {
    resetBtn.addEventListener("click", () => {
      capitalInput.value = "100000";
      riskPctInput.value = "1";
      if (entryInput) entryInput.value = "";
      if (stopInput) stopInput.value = "";
      if (symbolInput) symbolInput.value = "";
      updatePositionSizer();
    });
  }

  if (copyBtn) {
    copyBtn.addEventListener("click", copyBuyCommand);
  }

  updatePositionSizer();
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
// HELP CENTER & HANDBOOK HELPERS
// =====================================================================
function initHelpCenter() {
  // 1. Floating circular '?' button
  const floatingHelpBtn = document.getElementById("floatingHelpBtn");
  const helpTabBtn = document.getElementById("helpTabBtn");
  if (floatingHelpBtn && helpTabBtn) {
    floatingHelpBtn.addEventListener("click", () => {
      helpTabBtn.click();
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  // 2. Glossary live search
  const searchInput = document.getElementById("glossarySearchInput");
  const glossaryGrid = document.getElementById("glossaryGrid");
  if (searchInput && glossaryGrid) {
    const cards = glossaryGrid.querySelectorAll(".glossary-card");
    searchInput.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase().trim();
      cards.forEach(card => {
        const text = card.textContent.toLowerCase();
        if (!q || text.includes(q)) {
          card.style.display = "flex";
        } else {
          card.style.display = "none";
        }
      });
    });
  }

  // 3. FAQ Accordion toggle
  const faqItems = document.querySelectorAll(".faq-item");
  faqItems.forEach(item => {
    const question = item.querySelector(".faq-question");
    if (question) {
      question.addEventListener("click", () => {
        item.classList.toggle("active");
      });
    }
  });

  // 4. Sticky TOC active state handling
  const tocLinks = document.querySelectorAll(".help-toc-link");
  tocLinks.forEach(link => {
    link.addEventListener("click", () => {
      tocLinks.forEach(l => l.classList.remove("active"));
      link.classList.add("active");
    });
  });

  // Scrollspy for TOC
  const sections = document.querySelectorAll(".help-section");
  if (sections.length > 0 && tocLinks.length > 0) {
    window.addEventListener("scroll", () => {
      let currentId = "";
      sections.forEach(sec => {
        const top = sec.getBoundingClientRect().top;
        if (top <= 200) {
          currentId = sec.getAttribute("id");
        }
      });
      if (currentId) {
        tocLinks.forEach(l => {
          if (l.getAttribute("href") === `#${currentId}`) {
            l.classList.add("active");
          } else {
            l.classList.remove("active");
          }
        });
      }
    }, { passive: true });
  }
}

// =====================================================================
// TERM SEARCH, INLINE DEFINITIONS & TAB BANNERS
// =====================================================================

// Helper to switch to Help tab and flash target glossary card
function jumpToHelpTerm(anchor) {
  const helpTabBtn = document.getElementById("helpTabBtn");
  if (helpTabBtn) {
    helpTabBtn.click();
  }
  if (!anchor) return;

  setTimeout(() => {
    const el = document.getElementById(anchor);
    if (el) {
      el.scrollIntoView({ behavior: "smooth", block: "center" });
      el.classList.remove("term-highlight-flash");
      void el.offsetWidth; // trigger reflow
      el.classList.add("term-highlight-flash");
      setTimeout(() => el.classList.remove("term-highlight-flash"), 2600);
    }
  }, 120);
}

// Show term definition popover positioned near targetElement
function showTermPopover(termKey, targetElement) {
  const popover = document.getElementById("termPopover");
  if (!popover) return;

  // Search case-insensitive match in TERMS
  const normKey = Object.keys(TERMS).find(k => k.toLowerCase() === termKey.toLowerCase()) || termKey;
  const termData = TERMS[normKey];
  if (!termData) return;

  document.getElementById("termPopoverTitle").textContent = normKey;
  document.getElementById("termPopoverBody").textContent = termData.short;
  document.getElementById("termPopoverWhere").textContent = termData.where_used ? `Used in: ${termData.where_used}` : "";

  const guideLink = document.getElementById("termPopoverGuideLink");
  if (termData.anchor) {
    guideLink.style.display = "inline-block";
    guideLink.onclick = (e) => {
      e.preventDefault();
      popover.style.display = "none";
      jumpToHelpTerm(termData.anchor);
    };
  } else {
    guideLink.style.display = "none";
  }

  popover.style.display = "flex";
  const rect = targetElement.getBoundingClientRect();
  const popoverWidth = 320;
  let left = rect.left + window.scrollX;
  let top = rect.bottom + window.scrollY + 8;

  // Viewport clamping
  if (left + popoverWidth > window.innerWidth - 20) {
    left = window.innerWidth - popoverWidth - 20;
  }
  if (left < 10) left = 10;

  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
}

function hideTermPopover() {
  const popover = document.getElementById("termPopover");
  if (popover) {
    popover.style.display = "none";
  }
}

// Global Term Search Modal State & Handlers
let currentSearchIndex = -1;

function openTermSearchModal() {
  const modal = document.getElementById("termSearchModal");
  const input = document.getElementById("termSearchInput");
  if (!modal || !input) return;
  modal.style.display = "flex";
  input.value = "";
  currentSearchIndex = -1;
  renderTermSearchResults("");
  input.focus();
}

function closeTermSearchModal() {
  const modal = document.getElementById("termSearchModal");
  if (modal) {
    modal.style.display = "none";
  }
}

function renderTermSearchResults(query) {
  const resultsContainer = document.getElementById("termSearchResults");
  if (!resultsContainer) return;

  const q = (query || "").toLowerCase().trim();
  const entries = Object.entries(TERMS);

  const matched = entries.filter(([name, data]) => {
    if (!q) return true;
    const matchName = name.toLowerCase().includes(q);
    const matchShort = data.short.toLowerCase().includes(q);
    const matchLong = (data.long || "").toLowerCase().includes(q);
    const matchWhere = (data.where_used || "").toLowerCase().includes(q);
    return matchName || matchShort || matchLong || matchWhere;
  });

  if (matched.length === 0) {
    resultsContainer.innerHTML = `
      <div class="term-search-empty">
        No terms found matching "<strong>${escapeHtml(query)}</strong>". Try searching for SMA, ATR, PnL, or Grade.
      </div>
    `;
    currentSearchIndex = -1;
    return;
  }

  resultsContainer.innerHTML = matched.map(([name, data], idx) => `
    <div class="term-search-item ${idx === currentSearchIndex ? "selected" : ""}" data-term="${escapeHtml(name)}" data-anchor="${data.anchor || ""}">
      <div class="term-search-item-top">
        <span class="term-search-item-title">${escapeHtml(name)}</span>
        ${data.where_used ? `<span class="term-search-item-where">${escapeHtml(data.where_used)}</span>` : ""}
      </div>
      <div class="term-search-item-meaning">${escapeHtml(data.short)}</div>
    </div>
  `).join("");

  // Attach click handlers
  resultsContainer.querySelectorAll(".term-search-item").forEach(item => {
    item.addEventListener("click", () => {
      const termName = item.getAttribute("data-term");
      const anchor = item.getAttribute("data-anchor");
      closeTermSearchModal();
      if (anchor) {
        jumpToHelpTerm(anchor);
      } else {
        showTermPopover(termName, item);
      }
    });
  });
}

// "How to read this tab" Dismissible Info Banners
function initTabGuideBanners() {
  const banners = document.querySelectorAll(".tab-guide-banner");
  banners.forEach(banner => {
    const bannerKey = banner.getAttribute("data-tab-banner");
    const storageKey = `dismissed_tab_banner_${bannerKey}`;
    if (localStorage.getItem(storageKey) === "1") {
      banner.style.display = "none";
      return;
    }

    const dismissBtn = banner.querySelector(".tab-guide-dismiss");
    if (dismissBtn) {
      dismissBtn.addEventListener("click", () => {
        banner.classList.add("dismissing");
        localStorage.setItem(storageKey, "1");
        setTimeout(() => {
          banner.style.display = "none";
        }, 220);
      });
    }
  });
}

// Initialize Global Search and Clickable Term Lookups
function initTermSearchAndLookups() {
  // Magnifier button in top bar
  const globalSearchBtn = document.getElementById("globalSearchBtn");
  if (globalSearchBtn) {
    globalSearchBtn.addEventListener("click", openTermSearchModal);
  }

  // Search backdrop click
  const backdrop = document.getElementById("termSearchBackdrop");
  if (backdrop) {
    backdrop.addEventListener("click", closeTermSearchModal);
  }

  // Search input typing
  const searchInput = document.getElementById("termSearchInput");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      currentSearchIndex = -1;
      renderTermSearchResults(e.target.value);
    });

    // Arrow navigation & Enter selection
    searchInput.addEventListener("keydown", (e) => {
      const items = document.querySelectorAll("#termSearchResults .term-search-item");
      if (items.length === 0) return;

      if (e.key === "ArrowDown") {
        e.preventDefault();
        currentSearchIndex = (currentSearchIndex + 1) % items.length;
        items.forEach((it, idx) => {
          if (idx === currentSearchIndex) {
            it.classList.add("selected");
            it.scrollIntoView({ block: "nearest" });
          } else {
            it.classList.remove("selected");
          }
        });
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        currentSearchIndex = (currentSearchIndex - 1 + items.length) % items.length;
        items.forEach((it, idx) => {
          if (idx === currentSearchIndex) {
            it.classList.add("selected");
            it.scrollIntoView({ block: "nearest" });
          } else {
            it.classList.remove("selected");
          }
        });
      } else if (e.key === "Enter") {
        e.preventDefault();
        const target = currentSearchIndex >= 0 && currentSearchIndex < items.length
          ? items[currentSearchIndex]
          : items[0];
        if (target) target.click();
      }
    });
  }

  // Keyboard shortcuts: "/" to open, "Escape" to close
  document.addEventListener("keydown", (e) => {
    if (e.key === "/") {
      const activeEl = document.activeElement;
      const isInput = activeEl && (activeEl.tagName === "INPUT" || activeEl.tagName === "TEXTAREA" || activeEl.isContentEditable);
      if (!isInput) {
        e.preventDefault();
        openTermSearchModal();
      }
    } else if (e.key === "Escape") {
      const modal = document.getElementById("termSearchModal");
      if (modal && modal.style.display !== "none") {
        closeTermSearchModal();
      }
      hideTermPopover();
    }
  });

  // Popover close button
  const popoverClose = document.getElementById("termPopoverClose");
  if (popoverClose) {
    popoverClose.addEventListener("click", hideTermPopover);
  }

  // Clickable terms event delegation across all tabs
  document.addEventListener("click", (e) => {
    const lookupEl = e.target.closest(".term-lookup");
    if (lookupEl) {
      e.preventDefault();
      e.stopPropagation();
      const termKey = lookupEl.getAttribute("data-term") || lookupEl.textContent.trim();
      showTermPopover(termKey, lookupEl);
      return;
    }

    // Outside click closes popover
    const popover = document.getElementById("termPopover");
    if (popover && popover.style.display !== "none" && !popover.contains(e.target)) {
      hideTermPopover();
    }
  });
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

  // Initialize Help Center
  initHelpCenter();

  // Initialize Term Search, Inline Definitions & Tab Banners
  initTabGuideBanners();
  initTermSearchAndLookups();

  // Initial load if on app page
  if (document.getElementById("watchlistTable")) {
    initPositionSizer();
    loadAllData();

    // Auto-refresh every 5 minutes (300,000 ms)
    setInterval(() => {
      console.log("Auto-refreshing dashboard data...");
      loadAllData();
    }, 300000);
  }
});

