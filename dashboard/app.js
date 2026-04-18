/* ── app.js: GravityTrade Dashboard Logic ── */
'use strict';

const API = 'http://localhost:8080';
let ws = null;
let lastState = null;

const AGENTS = [
  { num: '01', name: 'Orchestrator',       key: 'Orchestrator' },
  { num: '02', name: 'Portfolio Ingestor', key: 'PortfolioIngestor' },
  { num: '03', name: 'Market Data',        key: 'MarketData' },
  { num: '04', name: 'Technical Analysis', key: 'TechnicalAnalysis' },
  { num: '05', name: 'Fundamental',        key: 'FundamentalAnalysis' },
  { num: '06', name: 'Sentiment',          key: 'SentimentAnalysis' },
  { num: '07', name: 'Macro Intel',        key: 'MacroIntelligence' },
  { num: '08', name: 'Smart Money 🧠',     key: 'SmartMoney' },
  { num: '09', name: 'Bull Agent 🐂',      key: 'BullAgent' },
  { num: '10', name: 'Bear Agent 🐻',      key: 'BearAgent' },
  { num: '11', name: 'Pattern Recog.',     key: 'PatternRecognition' },
  { num: '12', name: 'Stock Scanner 🔭',   key: 'StockScanner' },
  { num: '13', name: 'Pref. Scanner 🎯',  key: 'PreferenceScanner' },
  { num: '14', name: 'Risk Manager',       key: 'RiskManager' },
  { num: '15', name: 'Time Advisor ⏰',    key: 'TimePrecisionAdvisor' },
  { num: '16', name: 'Strategist 🏆',      key: 'PortfolioStrategist' },
];

const ACTION_COLORS = {
  BUY: '#22c55e', ADD: '#3b82f6', HOLD: '#6b7280',
  WATCH: '#f59e0b', TRIM: '#f97316', SELL: '#ef4444'
};

// ── Init ──────────────────────────────────────────────────
let currentStrategy = 'ALL';

document.addEventListener('DOMContentLoaded', () => {
  buildAgentGrid();
  connectWebSocket();
  checkStatus();
  loadStrategyFromServer();
  
  const savedKey = localStorage.getItem('gemini_api_key');
  if (savedKey) {
    document.getElementById('gemini-api-key').value = savedKey;
  }
});

function saveApiKey() {
  const key = document.getElementById('gemini-api-key').value.trim();
  if (key) {
    localStorage.setItem('gemini_api_key', key);
    document.getElementById('key-saved-msg').classList.add('show');
    setTimeout(() => document.getElementById('key-saved-msg').classList.remove('show'), 2000);
  }
}

function buildAgentGrid() {
  const grid = document.getElementById('agent-grid');
  grid.innerHTML = AGENTS.map(a => `
    <div class="agent-card" id="agent-${a.key}" data-key="${a.key}">
      <div class="agent-num">Agent ${a.num}</div>
      <div class="agent-name">${a.name}</div>
      <span class="agent-status-badge status-idle" id="badge-${a.key}">Idle</span>
    </div>
  `).join('');
}

// ── WebSocket — bulletproof with exponential backoff ─────
let _wsRetry = 0;
let _wsAlive = true;

function connectWebSocket() {
  _wsAlive = true;
  ws = new WebSocket(`ws://${location.hostname}:8080/ws`);

  ws.onopen = () => {
    _wsRetry = 0;
    addLog('🟢 Connected to GravityTrade Intelligence Server', 'success');
    updateConnIndicator(true);
  };

  ws.onclose = () => {
    updateConnIndicator(false);
    if (!_wsAlive) return;
    const delay = Math.min(30000, 1000 * Math.pow(2, _wsRetry));
    _wsRetry++;
    addLog(`🔴 WebSocket closed. Reconnecting in ${(delay/1000).toFixed(0)}s... (attempt ${_wsRetry})`, 'warning');
    setTimeout(connectWebSocket, delay);
  };

  ws.onerror = (e) => {
    addLog('⚠️ WebSocket error — will auto-reconnect', 'error');
  };

  ws.onmessage = (e) => {
    try { handleMessage(JSON.parse(e.data)); }
    catch(err) { console.warn('WS parse error:', err); }
  };
}

function updateConnIndicator(connected) {
  let dot = document.getElementById('ws-indicator');
  if (!dot) {
    dot = document.createElement('span');
    dot.id = 'ws-indicator';
    dot.style.cssText = 'display:inline-block;width:8px;height:8px;border-radius:50%;margin-left:8px;vertical-align:middle;transition:.3s';
    document.querySelector('.logo')?.appendChild(dot);
  }
  dot.style.background = connected ? '#22c55e' : '#ef4444';
  dot.title = connected ? 'WebSocket Connected' : 'WebSocket Disconnected';
}

function handleMessage(msg) {
  const { event, data } = msg;
  if (event === 'ping') {
    // Respond with pong to confirm we're alive
    try { ws.send(JSON.stringify({ event: 'pong' })); } catch(_) {}
    return;
  }
  if (event === 'rate_limit') {
    const el = document.getElementById('hdr-engine');
    if (el) {
      el.textContent = `Gemini | ${data.rpm || 0}/15 RPM | ${data.tpm || 0} TPM`;
      el.style.color = '#4ade80'; 
    }
    return;
  }
  if (event === 'ready') {
    addLog(data.message, 'info');
  } else if (event === 'status_update') {
    updateAgentStatuses(data.agent_statuses);
    if (data.agent_logs) streamLogs(data.agent_logs);
  } else if (event === 'phase_start') {
    addLog(`━━ PHASE ${data.phase}: ${data.name} ━━`, 'success');
  } else if (event === 'agent_done') {
    addLog(`✅ ${data.agent} → ${data.status || 'DONE'}`, 'success');
  } else if (event === 'analysis_complete') {
    lastState = data;
    if (data.agent_statuses) updateAgentStatuses(data.agent_statuses);
    renderFullDashboard(data);
    document.getElementById('run-btn').disabled = false;
    document.getElementById('run-btn').querySelector('span:last-child').textContent = 'Run Again';
    addLog('🏆 ANALYSIS COMPLETE — All 16 agents finished!', 'success');
  } else if (event === 'initial_state') {
    lastState = data;
    if (data.agent_statuses) updateAgentStatuses(data.agent_statuses);
    renderFullDashboard(data);
  } else if (event === 'error') {
    addLog(`❌ Error: ${data.message}`, 'error');
    document.getElementById('run-btn').disabled = false;
  }
}

// ── API ───────────────────────────────────────────────────
async function startAnalysis() {
  const btn = document.getElementById('run-btn');
  btn.disabled = true;
  btn.querySelector('span:last-child').textContent = 'Analyzing...';
  clearLog();
  resetAgentCards();
  addLog('🚀 Launching 16-agent analysis pipeline...', 'success');
  addLog(`🎯 Strategy: ${currentStrategy}`, 'info');
  const apiKey = localStorage.getItem('gemini_api_key') || '';
  try {
    const resp = await fetch(`${API}/api/analyze`, { 
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ api_key: apiKey })
    });
    const json = await resp.json();
    if (json.error) { addLog(`❌ ${json.error}`, 'error'); btn.disabled = false; }
    else addLog(`📡 ${json.message}`, 'info');
  } catch (err) {
    addLog(`❌ Failed to connect: ${err.message}`, 'error');
    btn.disabled = false;
  }
}

async function checkStatus() {
  try {
    const resp = await fetch(`${API}/api/status`);
    const json = await resp.json();
    if (json.has_results) {
      const res  = await fetch(`${API}/api/results`);
      const data = await res.json();
      if (!data.error) { lastState = data; if (data.agent_statuses) updateAgentStatuses(data.agent_statuses); renderFullDashboard(data); }
    }
  } catch { /* server not up yet */ }
}

// ── Agent Status ──────────────────────────────────────────
function updateAgentStatuses(statuses) {
  if (!statuses) return;
  for (const [key, status] of Object.entries(statuses)) {
    const card  = document.getElementById(`agent-${key}`);
    const badge = document.getElementById(`badge-${key}`);
    if (!card || !badge) continue;
    card.className = `agent-card ${status.toLowerCase()}`;
    const spinner = status === 'RUNNING' ? '<span class="agent-spinner"></span>' : '';
    badge.className = `agent-status-badge status-${status.toLowerCase()}`;
    badge.innerHTML = status.charAt(0) + status.slice(1).toLowerCase() + spinner;
  }
}

function resetAgentCards() {
  AGENTS.forEach(a => {
    const card  = document.getElementById(`agent-${a.key}`);
    const badge = document.getElementById(`badge-${a.key}`);
    if (card)  card.className = 'agent-card';
    if (badge) { badge.className = 'agent-status-badge status-idle'; badge.textContent = 'Idle'; }
  });
}

// ── Log Terminal ─────────────────────────────────────
const _seenLogs = new Set();   // dedup guard — tracks every line ever shown

function addLog(msg, level = 'info') {
  if (_seenLogs.has(msg)) return;   // skip duplicate
  _seenLogs.add(msg);
  const terminal = document.getElementById('log-terminal');
  const ph = terminal.querySelector('.log-placeholder');
  if (ph) ph.remove();
  const div = document.createElement('div');
  div.className = `log-line ${level}`;
  div.textContent = msg;
  terminal.appendChild(div);
  terminal.scrollTop = terminal.scrollHeight;
}

function clearLog() {
  _seenLogs.clear();    // reset dedup so next run starts fresh
  document.getElementById('log-terminal').innerHTML = '';
}

function streamLogs(agentLogs) {
  for (const [, lines] of Object.entries(agentLogs)) {
    lines.forEach(line => {
      if (!line || _seenLogs.has(line)) return;   // skip blanks + already-shown
      const lvl = line.includes('\u2705') ? 'success'
                : line.includes('\u26a0')  ? 'warning'
                : line.includes('\u274c')  ? 'error'
                : 'info';
      addLog(line, lvl);
    });
  }
}

// ── Full Dashboard Render ─────────────────────────────────
function renderFullDashboard(data) {
  renderHeader(data);
  renderPortfolio(data);
  renderMacro(data);
  renderRecommendations(data);
  renderScanner(data);
  renderPreference(data);
  renderDebate(data);
  renderRisk(data);
  renderSentiment(data);

  ['portfolio-section','macro-section','recs-section','scanner-section',
   'preference-section','debate-section','risk-section','sentiment-section'].forEach(id => {
    const el = document.getElementById(id);
    if (el) { el.style.display = 'block'; el.classList.add('animate-in'); }
  });
}

// ── Header Stats (always live) ────────────────────────────
function renderHeader(data) {
  const val   = data.total_portfolio_value;
  const pnl   = data.total_pnl_pct;
  const vix   = data.macro_data?.vix;
  const macro = data.macro_data?.macro_signal;

  setText('hdr-value', val ? `$${fmt(val)}` : '—');
  const pnlEl = document.getElementById('hdr-pnl');
  if (pnlEl && pnl != null) {
    pnlEl.textContent = `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}%`;
    pnlEl.style.color = pnl >= 0 ? 'var(--green)' : 'var(--red)';
  }
  
  const rpm = data.settings?.gemini_rpm || 0;
  const apiKey = localStorage.getItem('gemini_api_key');
  const engineEl = document.getElementById('hdr-engine');
  if (engineEl) {
    if (apiKey) {
      engineEl.textContent = `Gemini | ${rpm}/15 RPM`;
      engineEl.style.color = '#c4b5fd';
    } else {
      engineEl.textContent = 'AWAITING KEY';
      engineEl.style.color = '#c4b5fd';
    }
  }
  setText('hdr-vix', vix ? vix.toFixed(1) : '—');
  const macroEl = document.getElementById('hdr-macro');
  if (macroEl && macro) {
    macroEl.textContent = macro.replace(/_/g, ' ');
    macroEl.style.color = macro.includes('ON') || macro.includes('BULL') ? 'var(--green)'
                        : macro === 'RISK_OFF' ? 'var(--red)' : 'var(--text-1)';
  }
}

// ── Portfolio Cards ───────────────────────────────────────
function renderPortfolio(data) {
  const grid = document.getElementById('portfolio-grid');
  const holdings = data.holdings || [];
  grid.innerHTML = holdings.map(h => {
    const pnl    = h.unrealized_pnl_pct;
    const pnlStr = `${pnl >= 0 ? '+' : ''}${(pnl||0).toFixed(2)}%`;
    const ta     = (data.technical_signals || {})[h.ticker];
    const rec    = (data.recommendations || {})[h.ticker];
    const badge  = rec ? `<span class="agent-status-badge badge-${rec.action}" style="font-size:.7rem">${rec.action}</span>` : '';
    return `
      <div class="holding-card animate-in">
        <div class="holding-top">
          <div>
            <div class="holding-ticker">${h.ticker} ${badge}</div>
            <div class="holding-name">${h.name}</div>
          </div>
          <div class="holding-price">
            <div class="holding-price-val">$${(h.current_price||0).toFixed(2)}</div>
            <div class="holding-pnl ${pnl>=0?'pnl-pos':'pnl-neg'}">${pnlStr}</div>
          </div>
        </div>
        <div class="holding-stats">
          <div class="holding-stat"><span class="hstat-label">Shares</span><span class="hstat-val">${h.shares}</span></div>
          <div class="holding-stat"><span class="hstat-label">Avg Cost</span><span class="hstat-val">$${(h.avg_buy_price||0).toFixed(2)}</span></div>
          <div class="holding-stat"><span class="hstat-label">Market Val</span><span class="hstat-val">$${fmt(h.market_value||0)}</span></div>
          <div class="holding-stat"><span class="hstat-label">TA Score</span><span class="hstat-val" style="color:${scoreColor(ta?.ta_score)}">${ta?.ta_score ?? '—'}/100</span></div>
        </div>
        <div class="holding-sector">${h.sector}</div>
      </div>`;
  }).join('');
}

// ── Macro ─────────────────────────────────────────────────
function renderMacro(data) {
  const m = data.macro_data;
  if (!m) return;
  const grid = document.getElementById('macro-grid');
  const items = [
    { icon: '😰', label: 'VIX Fear Index', val: m.vix?.toFixed(1) ?? '—', extra: !m.vix?'—':m.vix<20?'CALM':m.vix<30?'ELEVATED':'FEAR', color: !m.vix?'var(--text-2)':m.vix<20?'var(--green)':m.vix<30?'var(--yellow)':'var(--red)' },
    { icon: '📈', label: 'S&P 500 Trend',  val: m.sp500_current ? `$${m.sp500_current.toFixed(0)}` : '—', extra: m.sp500_trend??'—', color: m.sp500_trend==='UP'?'var(--green)':m.sp500_trend==='DOWN'?'var(--red)':'var(--yellow)' },
    { icon: '💵', label: '10Y Treasury',   val: m.yield_10y ? `${m.yield_10y.toFixed(2)}%` : '—', extra: !m.yield_10y?'—':m.yield_10y>4.5?'HIGH':'NORMAL', color: m.yield_10y>4.5?'var(--red)':'var(--green)' },
    { icon: '📉', label: 'Yield Curve',    val: m.yield_curve_spread != null ? `${m.yield_curve_spread>0?'+':''}${m.yield_curve_spread.toFixed(3)}` : '—', extra: m.yield_curve_spread>0?'NORMAL':'INVERTED', color: m.yield_curve_spread>0?'var(--green)':'var(--red)' },
    { icon: '💪', label: 'Dollar Index',   val: m.dollar_index?.toFixed(1) ?? '—', extra: m.dollar_index>100?'STRONG':'WEAK', color: m.dollar_index>100?'var(--yellow)':'var(--green)' },
    { icon: '🌍', label: 'Macro Signal',   val: (m.macro_score?.toFixed(0)??'—')+'/100', extra: m.macro_signal?.replace(/_/g,' ')??'—', color: m.macro_signal?.includes('ON')||m.macro_signal?.includes('BULL')?'var(--green)':m.macro_signal==='RISK_OFF'?'var(--red)':'var(--yellow)' },
  ];
  grid.innerHTML = items.map(i => `
    <div class="macro-card animate-in">
      <div class="macro-icon">${i.icon}</div>
      <div class="macro-label">${i.label}</div>
      <div class="macro-val" style="color:${i.color}">${i.val}</div>
      <span class="macro-signal" style="color:${i.color};background:${i.color}22">${i.extra}</span>
    </div>`).join('');
}

// ── Portfolio Recommendations ─────────────────────────────
function renderRecommendations(data) {
  const recs = data.recommendations || {};
  const grid = document.getElementById('recs-grid');
  grid.innerHTML = Object.entries(recs).map(([ticker, rec]) => recCard(ticker, rec, false)).join('');
}

// ── Top 5 New Buys (Scanner) ──────────────────────────────
function renderScanner(data) {
  const recs = data.scan_recommendations || {};
  const sect = document.getElementById('scanner-section');
  if (!sect) return;
  const grid = document.getElementById('scanner-grid');
  if (!Object.keys(recs).length) { sect.style.display = 'none'; return; }

  // Sort by rank if available
  const sorted = Object.entries(recs).sort((a, b) => (a[1].signals_summary?.rank||99) - (b[1].signals_summary?.rank||99));
  grid.innerHTML = sorted.map(([ticker, rec]) => recCard(ticker, rec, true)).join('');
}

function recCard(ticker, rec, isNew) {
  const sig      = rec.signals_summary || {};
  const conf     = (rec.confidence * 100).toFixed(0);
  const color    = ACTION_COLORS[rec.action] || '#22c55e';
  const upside   = sig.upside_pct ? `+${sig.upside_pct}%` : '';
  const hold     = sig.hold_duration || '';
  const scores   = [
    { label: 'TA',    val: sig.ta_score?.toFixed(0)   ?? '—' },
    { label: 'Fund',  val: sig.fund_score?.toFixed(0) ?? '—' },
    { label: 'Macro', val: sig.macro_score?.toFixed(0)?? '—' },
    { label: 'Score', val: sig.composite?.toFixed(1)  ?? '—' },
  ];
  return `
    <div class="rec-card action-${rec.action} animate-in" style="border-top:2px solid ${color}">
      <div class="rec-header">
        <span class="rec-ticker">${isNew ? '🆕 ' : ''}${ticker}</span>
        <span class="rec-action-badge badge-${rec.action}">${rec.action}</span>
      </div>
      ${isNew && sig.name ? `<div style="font-size:.72rem;color:var(--text-2);margin-bottom:4px">${sig.name} · ${sig.sector||''}</div>` : ''}
      <div class="rec-confidence">
        <span class="confidence-label">Confidence</span>
        <div class="confidence-bar-wrap"><div class="confidence-bar" style="width:${conf}%;background:${color}"></div></div>
        <span class="confidence-val" style="color:${color}">${conf}%</span>
      </div>
      <div class="rec-timing">
        <div class="rec-timing-row"><span class="timing-label">Entry Window</span><span class="timing-val">${rec.entry_window_start??'—'} → ${rec.entry_window_end??'—'}</span></div>
        <div class="rec-timing-row"><span class="timing-label">Entry Zone</span><span class="timing-val">${rec.entry_price_low?'$'+rec.entry_price_low.toFixed(2):'—'} – ${rec.entry_price_high?'$'+rec.entry_price_high.toFixed(2):'—'}</span></div>
        <div class="rec-timing-row"><span class="timing-label">Urgency</span><span class="rec-urgency urgency-${rec.urgency}">${rec.urgency}</span></div>
        ${isNew && upside ? `<div class="rec-timing-row"><span class="timing-label">Upside</span><span class="timing-val" style="color:var(--green);font-weight:700">${upside}</span></div>` : ''}
        ${isNew && hold   ? `<div class="rec-timing-row"><span class="timing-label">Hold Duration</span><span class="timing-val" style="color:var(--yellow)">${hold}</span></div>` : ''}
      </div>
      <div class="rec-levels">
        <div class="rec-level"><div class="rec-level-label">Entry</div><div class="rec-level-val level-entry">$${rec.entry_price_low?.toFixed(2)??'—'}</div></div>
        <div class="rec-level"><div class="rec-level-label">Target 🎯</div><div class="rec-level-val level-target">$${rec.exit_target_1?.toFixed(2)??'—'}</div></div>
        <div class="rec-level"><div class="rec-level-label">Stop 🛑</div><div class="rec-level-val level-stop">$${rec.stop_loss?.toFixed(2)??'—'}</div></div>
      </div>
      <div class="rec-scores">
        ${scores.map(s => `<div class="score-mini"><div class="score-mini-label">${s.label}</div><div class="score-mini-val" style="color:${scoreColor(parseFloat(s.val))}">${s.val}</div></div>`).join('')}
      </div>
      <div style="font-size:.66rem;color:var(--text-3);margin-top:6px">Alloc: <strong>${rec.allocation_pct?.toFixed(0)??'—'}%</strong></div>
    </div>`;
}

// ── Debate Arena ──────────────────────────────────────────
let currentDebateTicker = null;
function renderDebate(data) {
  const tickers = Object.keys(data.bull_theses || {});
  if (!tickers.length) return;
  const selector = document.getElementById('debate-selector');
  selector.innerHTML = tickers.map(t => `<span class="debate-pill${t===tickers[0]?' active':''}" onclick="selectDebateTicker('${t}',this)">${t}</span>`).join('');
  currentDebateTicker = tickers[0];
  renderDebateForTicker(data, tickers[0]);
}
function selectDebateTicker(ticker, el) {
  document.querySelectorAll('.debate-pill').forEach(p => p.classList.remove('active'));
  el.classList.add('active');
  if (lastState) renderDebateForTicker(lastState, ticker);
}
function renderDebateForTicker(data, ticker) {
  const bull = (data.bull_theses||{})[ticker]||{};
  const bear = (data.bear_theses||{})[ticker]||{};
  document.getElementById('debate-arena').innerHTML = `
    <div class="debate-side bull">
      <div class="debate-title bull-t">🐂 Bull Case</div>
      <div class="debate-conf">Confidence: ${((bull.confidence||0)*100).toFixed(0)}% · ${bull.timeframe??'—'}</div>
      <ul class="debate-points bull">${(bull.key_points||[]).slice(0,6).map(p=>`<li>${p}</li>`).join('')||'<li>No strong bull signals</li>'}</ul>
      <div class="debate-target bull"><span>Price Target</span><span>$${bull.price_target?.toFixed(2)??'—'}</span></div>
    </div>
    <div class="debate-vs"><div class="vs-bar"></div><span>VS</span><div class="vs-bar"></div></div>
    <div class="debate-side bear">
      <div class="debate-title bear-t">🐻 Bear Case</div>
      <div class="debate-conf">Confidence: ${((bear.confidence||0)*100).toFixed(0)}% · ${bear.timeframe??'—'}</div>
      <ul class="debate-points bear">${(bear.key_points||[]).slice(0,6).map(p=>`<li>${p}</li>`).join('')||'<li>No strong bear signals</li>'}</ul>
      <div class="debate-target bear"><span>Bear Target</span><span>$${bear.price_target?.toFixed(2)??'—'}</span></div>
    </div>`;
}

// ── Risk Cards ────────────────────────────────────────────
function renderRisk(data) {
  const risks = data.risk_metrics || {};
  document.getElementById('risk-grid').innerHTML = Object.entries(risks).map(([ticker, r]) => `
    <div class="risk-card animate-in">
      <div class="risk-ticker">${ticker}<div class="risk-grade grade-${r.risk_grade??'C'}">${r.risk_grade??'?'}</div></div>
      <div class="risk-metric-row"><span class="rm-label">VaR 95%</span><span class="rm-val">${r.var_95?.toFixed(2)??'—'}%</span></div>
      <div class="risk-metric-row"><span class="rm-label">Sharpe</span><span class="rm-val" style="color:${(r.sharpe_ratio||0)>1?'var(--green)':'var(--yellow)'}">${r.sharpe_ratio?.toFixed(2)??'—'}</span></div>
      <div class="risk-metric-row"><span class="rm-label">Beta</span><span class="rm-val">${r.beta?.toFixed(2)??'—'}</span></div>
      <div class="risk-metric-row"><span class="rm-label">Max Drawdown</span><span class="rm-val" style="color:var(--red)">${r.max_drawdown?.toFixed(1)??'—'}%</span></div>
      <div class="risk-metric-row"><span class="rm-label">Ann. Volatility</span><span class="rm-val">${r.volatility_annual?.toFixed(1)??'—'}%</span></div>
      <div class="risk-metric-row"><span class="rm-label">Stop Loss</span><span class="rm-val" style="color:var(--red)">$${r.stop_loss_price?.toFixed(2)??'—'}</span></div>
      <div class="risk-metric-row"><span class="rm-label">Take Profit</span><span class="rm-val" style="color:var(--green)">$${r.take_profit_price?.toFixed(2)??'—'}</span></div>
      <div class="risk-metric-row"><span class="rm-label">Position Size</span><span class="rm-val">${r.recommended_position_pct?.toFixed(0)??'—'}%</span></div>
    </div>`).join('');
}

// ── Sentiment Cards ───────────────────────────────────────
function renderSentiment(data) {
  const sents = data.sentiment_signals || {};
  document.getElementById('sentiment-grid').innerHTML = Object.entries(sents).map(([ticker, s]) => {
    const score = s.sentiment_score ?? 0;
    const isPos = score >= 0;
    return `
      <div class="sent-card animate-in">
        <div class="sent-top">
          <span class="sent-ticker">${ticker}</span>
          <span class="sent-badge sent-${s.sentiment_label??'NEUTRAL'}">${s.sentiment_label??'NEUTRAL'}</span>
        </div>
        <div style="font-size:.72rem;color:var(--text-3);margin-bottom:8px">${s.news_count??0} articles · Score: <strong style="color:${isPos?'var(--green)':'var(--red)'}">${score>=0?'+':''}${score.toFixed(3)}</strong></div>
        <div class="sent-score-row"><div class="sent-score-bar-bg"><div class="sent-score-center"></div><div class="sent-score-bar ${isPos?'pos':'neg'}" style="width:${Math.abs(score)*50}%"></div></div></div>
        <div class="sent-headlines">${(s.top_headlines||[]).slice(0,4).map(h=>`<div class="sent-headline">📰 ${h}</div>`).join('')||'<div class="sent-headline" style="color:var(--text-3)">No headlines</div>'}</div>
      </div>`;
  }).join('');
}

// ── Utils ─────────────────────────────────────────────────
function fmt(n) {
  if (n >= 1e6) return (n/1e6).toFixed(2)+'M';
  if (n >= 1e3) return (n/1e3).toFixed(1)+'K';
  return n.toFixed(2);
}
function setText(id, val) { const el = document.getElementById(id); if (el) el.textContent = val; }
function scoreColor(score) {
  if (score == null || isNaN(score)) return 'var(--text-2)';
  if (score >= 65) return 'var(--green)';
  if (score >= 50) return 'var(--yellow)';
  return 'var(--red)';
}

// ── Strategy Selector ─────────────────────────────────────
async function loadStrategyFromServer() {
  try {
    const resp = await fetch(`${API}/api/portfolio`);
    const data = await resp.json();
    const strat = data?.settings?.strategy || 'ALL';
    currentStrategy = strat;
    document.querySelectorAll('.strat-pill').forEach(p => p.classList.remove('active'));
    const el = document.getElementById(`strat-${strat}`);
    if (el) el.classList.add('active');
  } catch { /* ignore */ }
}

async function setStrategy(strat) {
  currentStrategy = strat;
  document.querySelectorAll('.strat-pill').forEach(p => p.classList.remove('active'));
  const el = document.getElementById(`strat-${strat}`);
  if (el) el.classList.add('active');
  try {
    await fetch(`${API}/api/strategy`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ strategy: strat }),
    });
    const saved = document.getElementById('strat-saved');
    saved.classList.add('show');
    setTimeout(() => saved.classList.remove('show'), 1800);
  } catch { /* ignore */ }
}

// ── Preference Picks Section ──────────────────────────────
function renderPreference(data) {
  const recs = data.preference_recommendations || {};
  const sect = document.getElementById('preference-section');
  if (!sect) return;
  const grid = document.getElementById('preference-grid');
  if (!Object.keys(recs).length) { sect.style.display = 'none'; return; }

  const firstRec = Object.values(recs)[0];
  const strat    = firstRec?.signals_summary?.strategy || currentStrategy;
  const persona  = firstRec?.signals_summary?.persona  || '';
  const sub      = document.getElementById('preference-sub');
  if (sub) sub.textContent = `${strat} Strategy — Analyzed by ${persona}`;

  sect.style.display = 'block';
  const sorted = Object.entries(recs).sort((a,b) => (a[1].signals_summary?.rank||99)-(b[1].signals_summary?.rank||99));
  grid.innerHTML = sorted.map(([ticker, rec]) => prefCard(ticker, rec)).join('');
}

function prefCard(ticker, rec) {
  const sig      = rec.signals_summary || {};
  const conf     = (rec.confidence * 100).toFixed(0);
  const color    = '#22c55e';
  const upside   = sig.upside_pct ? `+${sig.upside_pct}%` : '';
  const hold     = sig.hold_duration || '';
  const strat    = sig.strategy || '';
  const divYield = sig.div_yield ? `${(sig.div_yield*100).toFixed(1)}%` : null;
  const pe       = sig.pe ? sig.pe.toFixed(1) : null;
  const revGrowth= sig.rev_growth ? `${(sig.rev_growth*100).toFixed(1)}%` : null;

  const stratIcons = { GROWTH:'🚀', DIVIDEND:'💰', REIT:'🏢', VALUE:'⚖️', MOMENTUM:'⚡', ALL:'🌐' };
  const icon = stratIcons[strat] || '🎯';

  const extraRows = [];
  if (divYield)  extraRows.push(`<div class="rec-timing-row"><span class="timing-label">Div Yield</span><span class="timing-val" style="color:var(--green);font-weight:700">${divYield}</span></div>`);
  if (pe)        extraRows.push(`<div class="rec-timing-row"><span class="timing-label">P/E Ratio</span><span class="timing-val">${pe}</span></div>`);
  if (revGrowth) extraRows.push(`<div class="rec-timing-row"><span class="timing-label">Rev Growth</span><span class="timing-val" style="color:#3b82f6">${revGrowth}</span></div>`);

  return `
    <div class="rec-card action-BUY animate-in" style="border-top:2px solid ${color};position:relative">
      <div style="position:absolute;top:10px;right:10px;font-size:1.4rem;opacity:.6">${icon}</div>
      <div class="rec-header">
        <span class="rec-ticker">#${sig.rank||'?'} ${ticker}</span>
        <span class="rec-action-badge badge-BUY">BUY</span>
      </div>
      <div style="font-size:.72rem;color:var(--text-2);margin-bottom:6px">${sig.name||''} · ${sig.sector||''}</div>
      <div class="rec-confidence">
        <span class="confidence-label">Confidence</span>
        <div class="confidence-bar-wrap"><div class="confidence-bar" style="width:${conf}%;background:${color}"></div></div>
        <span class="confidence-val" style="color:${color}">${conf}%</span>
      </div>
      <div class="rec-timing">
        <div class="rec-timing-row"><span class="timing-label">Entry Window</span><span class="timing-val">${rec.entry_window_start??'—'} → ${rec.entry_window_end??'—'}</span></div>
        <div class="rec-timing-row"><span class="timing-label">Entry Zone</span><span class="timing-val">$${rec.entry_price_low?.toFixed(2)??'—'} – $${rec.entry_price_high?.toFixed(2)??'—'}</span></div>
        ${upside ? `<div class="rec-timing-row"><span class="timing-label">Upside</span><span class="timing-val" style="color:var(--green);font-weight:700">${upside}</span></div>` : ''}
        ${hold   ? `<div class="rec-timing-row"><span class="timing-label">Hold Duration</span><span class="timing-val" style="color:var(--yellow)">${hold}</span></div>` : ''}
        ${extraRows.join('')}
      </div>
      <div class="rec-levels">
        <div class="rec-level"><div class="rec-level-label">Entry</div><div class="rec-level-val level-entry">$${rec.entry_price_low?.toFixed(2)??'—'}</div></div>
        <div class="rec-level"><div class="rec-level-label">Target 🎯</div><div class="rec-level-val level-target">$${rec.exit_target_1?.toFixed(2)??'—'}</div></div>
        <div class="rec-level"><div class="rec-level-label">Stop 🛑</div><div class="rec-level-val level-stop">$${rec.stop_loss?.toFixed(2)??'—'}</div></div>
      </div>
      <div class="rec-scores">
        <div class="score-mini"><div class="score-mini-label">TA</div><div class="score-mini-val" style="color:${scoreColor(sig.ta_score)}">${sig.ta_score?.toFixed(0)??'—'}</div></div>
        <div class="score-mini"><div class="score-mini-label">Fund</div><div class="score-mini-val" style="color:${scoreColor(sig.fund_score)}">${sig.fund_score?.toFixed(0)??'—'}</div></div>
        <div class="score-mini"><div class="score-mini-label">Score</div><div class="score-mini-val" style="color:${scoreColor(sig.composite)}">${sig.composite?.toFixed(1)??'—'}</div></div>
        <div class="score-mini"><div class="score-mini-label">RSI</div><div class="score-mini-val" style="color:${!sig.rsi?'var(--text-2)':sig.rsi<30?'var(--green)':sig.rsi>70?'var(--red)':'var(--yellow)'}">${sig.rsi?.toFixed(0)??'—'}</div></div>
      </div>
      <div style="font-size:.66rem;color:var(--text-3);margin-top:6px">Alloc: <strong>${rec.allocation_pct?.toFixed(0)??'—'}%</strong></div>
    </div>`;
}

// ── Portfolio Editor ──────────────────────────────────────
let _portfolioData = null;

async function openPortfolioEditor() {
  const modal = document.getElementById('portfolio-modal');
  modal.style.display = 'flex';
  document.getElementById('portfolio-save-msg').textContent = '';
  try {
    const resp = await fetch(`${API}/api/portfolio`);
    _portfolioData = await resp.json();
    renderPortfolioTable(_portfolioData.portfolio || []);
  } catch (e) {
    document.getElementById('portfolio-save-msg').textContent = '❌ Failed to load portfolio';
  }
}

function closePortfolioEditor() {
  document.getElementById('portfolio-modal').style.display = 'none';
}

function renderPortfolioTable(holdings) {
  const tbody = document.getElementById('portfolio-edit-body');
  tbody.innerHTML = holdings.map((h, i) => `
    <tr id="row-${i}">
      <td><input class="tbl-input" value="${h.ticker}" id="h-ticker-${i}" style="width:100px;text-transform:uppercase" oninput="this.value=this.value.toUpperCase()"></td>
      <td><input class="tbl-input" type="number" value="${h.shares}" id="h-shares-${i}" style="width:100px" min="0.0001" step="0.0001"></td>
      <td><input class="tbl-input" type="number" value="${h.avg_buy_price}" id="h-price-${i}" style="width:120px" min="0.01" step="0.01"></td>
      <td><button class="btn-del" onclick="deletePortfolioRow(${i})" title="Remove">🗑</button></td>
    </tr>`).join('');
}

function addPortfolioRow() {
  if (!_portfolioData) _portfolioData = { portfolio: [], settings: {} };
  _portfolioData.portfolio.push({ ticker:'', shares:1, avg_buy_price:100, currency:'USD' });
  renderPortfolioTable(_portfolioData.portfolio);
  document.getElementById('portfolio-edit-body').lastElementChild?.scrollIntoView({ behavior:'smooth' });
}

function deletePortfolioRow(i) {
  if (!_portfolioData) return;
  _portfolioData.portfolio.splice(i, 1);
  renderPortfolioTable(_portfolioData.portfolio);
}

async function savePortfolio() {
  const tbody = document.getElementById('portfolio-edit-body');
  const rows  = tbody.querySelectorAll('tr');
  const holdings = [];
  const msg = document.getElementById('portfolio-save-msg');

  msg.textContent = 'Saving... (Fetching dynamic company data)';
  msg.style.color = '#eab308'; // yellow

  for (const row of rows) {
    const i      = row.id.split('-')[1];
    const ticker = document.getElementById(`h-ticker-${i}`)?.value?.trim().toUpperCase();
    const shares = parseFloat(document.getElementById(`h-shares-${i}`)?.value);
    const price  = parseFloat(document.getElementById(`h-price-${i}`)?.value);
    if (!ticker || !shares || !price) { msg.style.color = '#ef4444'; msg.textContent = `❌ Fill all fields for ${ticker||'new row'}`; return; }
    
    let name = _portfolioData.portfolio[i]?.name || '';
    let sector = _portfolioData.portfolio[i]?.sector || '';
    const origTicker = _portfolioData.portfolio[i]?.ticker;
    
    if (ticker !== origTicker) {
      name = '';
      sector = '';
    }
    
    holdings.push({ ticker, name, shares, avg_buy_price: price, sector, currency:'USD' });
  }

  const payload = { ...(_portfolioData||{}), portfolio: holdings };
  try {
    const resp = await fetch(`${API}/api/portfolio`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const result = await resp.json();
    if (result.error) { msg.style.color = '#ef4444'; msg.textContent = `❌ ${result.error}`; }
    else {
      msg.style.color = '#22c55e';
      msg.textContent = `✅ Saved ${result.holdings} holdings — run analysis to update`;
      _portfolioData = payload;
      setTimeout(closePortfolioEditor, 1500);
    }
  } catch (e) { msg.style.color = '#ef4444'; msg.textContent = `❌ Save failed: ${e.message}`; }
}
