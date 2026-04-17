const API = '';
let equityChart = null;
let drawdownChart = null;
let pnlChart = null;
let refreshTimer = null;

const esc = (s) => {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
};

const fmt = {
  money: (v) => '$' + (v ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  moneyShort: (v) => '$' + Math.round(v ?? 0).toLocaleString('en-US'),
  pct: (v) => (v >= 0 ? '+' : '') + (v ?? 0).toFixed(2) + '%',
  plus: (v) => (v >= 0 ? '+$' : '-$') + Math.abs(v ?? 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }),
  dt: (s) => {
    if (!s) return '—';
    const d = new Date(s);
    return d.toLocaleTimeString('uk-UA', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  },
  date: (s) => {
    if (!s) return '—';
    const d = new Date(s);
    return d.toLocaleString('uk-UA', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  },
};

async function fetchJson(path, opts = {}) {
  const res = await fetch(path, opts);
  return res.json();
}

function setText(id, text) {
  const el = document.getElementById(id);
  if (el) el.textContent = text;
}

function setClasses(id, classes) {
  const el = document.getElementById(id);
  if (!el) return;
  Object.entries(classes).forEach(([cls, on]) => el.classList.toggle(cls, on));
}

async function loadPortfolio() {
  const p = await fetchJson('/api/portfolio');

  setText('equity', fmt.money(p.equity));
  setText('cash', fmt.moneyShort(p.cash));
  setText('positions-value', fmt.moneyShort(p.positions_value));
  setText('position-count', String(p.position_count));
  setText('unrealized-pl', fmt.plus(p.unrealized_pl));
  setClasses('unrealized-pl', { pos: p.unrealized_pl >= 0, neg: p.unrealized_pl < 0 });

  setText('equity-change', `${fmt.plus(p.total_pl)} (${fmt.pct(p.total_pl_pct)})`);
  setClasses('equity-change', { pos: p.total_pl >= 0, neg: p.total_pl < 0 });

  renderPositions(p.positions);
}

function renderPositions(positions) {
  const overview = document.getElementById('positions-overview');
  const tbody = document.getElementById('positions-tbody');

  overview.replaceChildren();
  tbody.replaceChildren();

  if (!positions.length) {
    const empty = document.createElement('div');
    empty.className = 'muted';
    empty.style.cssText = 'padding:20px;text-align:center;';
    empty.textContent = 'Немає відкритих позицій';
    overview.appendChild(empty);

    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 8;
    td.className = 'empty-row';
    td.textContent = 'Немає відкритих позицій';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  positions.forEach(p => {
    const plClass = p.unrealized_pl >= 0 ? 'pos' : 'neg';

    const card = document.createElement('div');
    card.className = `position-card ${plClass}`;

    const sym = document.createElement('div');
    sym.className = 'position-symbol';
    sym.textContent = p.symbol;
    card.appendChild(sym);

    const qty = document.createElement('div');
    qty.className = 'position-qty';
    qty.textContent = `${p.qty} акцій`;
    card.appendChild(qty);

    const pl = document.createElement('div');
    pl.className = `position-pl ${plClass}`;
    pl.textContent = fmt.plus(p.unrealized_pl);
    card.appendChild(pl);

    const pct = document.createElement('div');
    pct.className = `position-pct ${plClass}`;
    pct.textContent = fmt.pct(p.unrealized_plpc * 100);
    card.appendChild(pct);

    const prices = document.createElement('div');
    prices.className = 'position-prices';
    prices.innerHTML = `<span>Вхід: <strong>$${p.avg_entry.toFixed(2)}</strong></span><span>Зараз: <strong>$${p.current_price.toFixed(2)}</strong></span>`;
    card.appendChild(prices);

    overview.appendChild(card);

    const tr = document.createElement('tr');
    const cells = [
      { html: `<strong>${esc(p.symbol)}</strong>` },
      { text: String(p.qty), cls: 'num' },
      { text: `$${p.avg_entry.toFixed(2)}`, cls: 'num' },
      { text: `$${p.current_price.toFixed(2)}`, cls: 'num' },
      { text: p.stop_loss ? '$' + p.stop_loss.toFixed(2) : '—', cls: 'num' },
      { text: p.take_profit ? '$' + p.take_profit.toFixed(2) : '—', cls: 'num' },
      { text: fmt.plus(p.unrealized_pl), cls: `num ${plClass}` },
      { text: fmt.pct(p.unrealized_plpc * 100), cls: `num ${plClass}` },
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      if (c.html) td.innerHTML = c.html;
      else td.textContent = c.text;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

async function loadEquityChart() {
  const history = await fetchJson('/api/equity_history?limit=500');
  setText('equity-points-count', `${history.length} точок`);

  const labels = history.map(h => new Date(h.timestamp));
  const values = history.map(h => h.equity);

  if (!history.length) {
    values.push(100000);
    labels.push(new Date());
  }

  const ctx = document.getElementById('equity-chart');
  if (equityChart) {
    equityChart.data.labels = labels;
    equityChart.data.datasets[0].data = values;
    equityChart.update('none');
    return;
  }

  const gradient = ctx.getContext('2d').createLinearGradient(0, 0, 0, 260);
  gradient.addColorStop(0, 'rgba(99, 102, 241, 0.35)');
  gradient.addColorStop(1, 'rgba(99, 102, 241, 0)');

  equityChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels,
      datasets: [{
        label: 'Equity',
        data: values,
        borderColor: '#6366f1',
        backgroundColor: gradient,
        borderWidth: 2,
        fill: true,
        tension: 0.3,
        pointRadius: 0,
        pointHoverRadius: 4,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { type: 'time', time: { unit: 'hour' }, ticks: { color: '#8a94a6' }, grid: { color: 'rgba(42,52,82,0.3)' } },
        y: { ticks: { color: '#8a94a6', callback: (v) => '$' + v.toLocaleString() }, grid: { color: 'rgba(42,52,82,0.3)' } },
      },
    },
  });
}

async function loadStats() {
  const s = await fetchJson('/api/stats');
  setText('total-trades', String(s.total_trades));
  setText('win-rate', (s.win_rate * 100).toFixed(1) + '%');
  setText('wins', String(s.wins));
  setText('losses', String(s.losses));
  setText('avg-win', fmt.moneyShort(s.avg_win));
  setText('avg-loss', fmt.moneyShort(s.avg_loss));
}

async function loadTrades() {
  const trades = await fetchJson('/api/trades');
  const tbody = document.getElementById('trades-tbody');
  tbody.replaceChildren();

  if (!trades.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 9;
    td.className = 'empty-row';
    td.textContent = 'Історія порожня';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  trades.forEach(t => {
    const plClass = (t.pnl ?? 0) >= 0 ? 'pos' : 'neg';
    const tr = document.createElement('tr');
    const cells = [
      { text: String(t.id) },
      { html: `<strong>${esc(t.symbol)}</strong>` },
      { text: String(t.qty), cls: 'num' },
      { text: `$${t.entry_price.toFixed(2)}`, cls: 'num' },
      { text: t.exit_price ? '$' + t.exit_price.toFixed(2) : '—', cls: 'num' },
      { text: t.pnl != null ? fmt.plus(t.pnl) : '—', cls: `num ${plClass}` },
      { text: t.pnl_pct != null ? fmt.pct(t.pnl_pct * 100) : '—', cls: `num ${plClass}` },
      { text: fmt.date(t.opened_at) },
      { text: fmt.date(t.closed_at) },
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      if (c.html) td.innerHTML = c.html;
      else td.textContent = c.text;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

async function loadAnalyses() {
  const data = await fetchJson('/api/analyses');
  const container = document.getElementById('analyses-container');
  const info = document.getElementById('cycle-info');
  container.replaceChildren();

  if (!data.analyses || Object.keys(data.analyses).length === 0) {
    const empty = document.createElement('div');
    empty.className = 'muted';
    empty.style.cssText = 'padding:20px;text-align:center;';
    empty.textContent = 'Запусти цикл щоб побачити аналіз';
    container.appendChild(empty);
    info.textContent = 'немає даних';
    return;
  }

  info.textContent = `цикл ${data.cycle_id} • ${fmt.date(data.completed_at)}`;

  Object.entries(data.analyses).forEach(([symbol, items]) => {
    const box = document.createElement('div');
    box.className = 'analysis-symbol';

    const title = document.createElement('div');
    title.className = 'analysis-symbol-title';
    title.textContent = symbol;
    box.appendChild(title);

    const list = document.createElement('div');
    list.className = 'analysis-items';

    items.forEach(a => {
      const row = document.createElement('div');
      row.className = 'analysis-item';

      const agent = document.createElement('span');
      agent.className = 'agent-name';
      agent.textContent = a.agent;
      row.appendChild(agent);

      const badge = document.createElement('span');
      badge.className = `signal-badge signal-${esc(a.signal)}`;
      badge.textContent = a.signal;
      row.appendChild(badge);

      const conf = document.createElement('span');
      conf.className = 'conf';
      conf.textContent = (a.confidence * 100).toFixed(0) + '%';
      row.appendChild(conf);

      const reasoning = document.createElement('span');
      reasoning.className = 'reasoning';
      reasoning.title = a.reasoning || '';
      reasoning.textContent = (a.reasoning || '').slice(0, 120);
      row.appendChild(reasoning);

      list.appendChild(row);
    });

    box.appendChild(list);
    container.appendChild(box);
  });
}

async function loadMarket() {
  const grid = document.getElementById('market-grid');
  grid.replaceChildren();
  const loading = document.createElement('div');
  loading.className = 'muted';
  loading.style.padding = '20px';
  loading.textContent = 'Завантаження...';
  grid.appendChild(loading);

  const data = await fetchJson('/api/market');
  grid.replaceChildren();

  Object.entries(data).forEach(([symbol, q]) => {
    const tile = document.createElement('div');
    if (q.error) {
      tile.className = 'market-tile';
      const sym = document.createElement('div');
      sym.className = 'market-symbol';
      sym.textContent = symbol;
      tile.appendChild(sym);
      const err = document.createElement('div');
      err.className = 'muted';
      err.style.fontSize = '10px';
      err.textContent = String(q.error).slice(0, 40);
      tile.appendChild(err);
    } else {
      const cls = q.change_pct >= 0 ? 'pos' : 'neg';
      tile.className = `market-tile ${cls}`;

      const sym = document.createElement('div');
      sym.className = 'market-symbol';
      sym.textContent = symbol;
      tile.appendChild(sym);

      const price = document.createElement('div');
      price.className = 'market-price';
      price.textContent = '$' + q.price.toFixed(2);
      tile.appendChild(price);

      const change = document.createElement('div');
      change.className = `market-change ${cls}`;
      change.textContent = fmt.pct(q.change_pct);
      tile.appendChild(change);
    }
    grid.appendChild(tile);
  });
}

async function loadActivity() {
  const log = await fetchJson('/api/activity');
  const container = document.getElementById('activity-log');
  container.replaceChildren();

  if (!log.length) {
    const empty = document.createElement('div');
    empty.className = 'muted';
    empty.style.cssText = 'padding:20px;text-align:center;';
    empty.textContent = 'Немає подій';
    container.appendChild(empty);
    return;
  }

  log.forEach(entry => {
    const row = document.createElement('div');
    row.className = 'activity-row';

    const time = document.createElement('span');
    time.className = 'activity-time';
    time.textContent = fmt.dt(entry.timestamp);
    row.appendChild(time);

    const event = document.createElement('span');
    event.className = `activity-event event-${esc(entry.event)}`;
    event.textContent = entry.event;
    row.appendChild(event);

    const data = document.createElement('span');
    data.className = 'activity-data';
    data.textContent = JSON.stringify(entry.data);
    row.appendChild(data);

    container.appendChild(row);
  });
}

async function loadAnalyticsView() {
  const data = await fetchJson('/api/analytics');

  const ddCtx = document.getElementById('drawdown-chart');
  const ddLabels = data.drawdown.map(d => new Date(d.timestamp));
  const ddValues = data.drawdown.map(d => d.drawdown);

  if (drawdownChart) {
    drawdownChart.data.labels = ddLabels;
    drawdownChart.data.datasets[0].data = ddValues;
    drawdownChart.update('none');
  } else if (ddCtx) {
    const grad = ddCtx.getContext('2d').createLinearGradient(0, 0, 0, 260);
    grad.addColorStop(0, 'rgba(239, 68, 68, 0.5)');
    grad.addColorStop(1, 'rgba(239, 68, 68, 0)');
    drawdownChart = new Chart(ddCtx, {
      type: 'line',
      data: { labels: ddLabels, datasets: [{ data: ddValues, borderColor: '#ef4444', backgroundColor: grad, borderWidth: 2, fill: true, tension: 0.3, pointRadius: 0 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { type: 'time', time: { unit: 'day' }, ticks: { color: '#8a94a6' }, grid: { color: 'rgba(42,52,82,0.3)' } },
          y: { ticks: { color: '#8a94a6', callback: (v) => v + '%' }, grid: { color: 'rgba(42,52,82,0.3)' } },
        },
      },
    });
  }

  const pnlCtx = document.getElementById('pnl-chart');
  const labels = ['<-$500', '-$500..-$200', '-$200..0', '0..$200', '$200..$500', '>$500'];
  const keys = ['<-500', '-500_to_-200', '-200_to_0', '0_to_200', '200_to_500', '>500'];
  const values = keys.map(k => data.pnl_distribution[k] || 0);
  const colors = values.map((_, i) => i < 3 ? '#ef4444' : '#10b981');

  if (pnlChart) {
    pnlChart.data.datasets[0].data = values;
    pnlChart.update('none');
  } else if (pnlCtx) {
    pnlChart = new Chart(pnlCtx, {
      type: 'bar',
      data: { labels, datasets: [{ data: values, backgroundColor: colors, borderRadius: 6 }] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          x: { ticks: { color: '#8a94a6', font: { size: 10 } }, grid: { display: false } },
          y: { ticks: { color: '#8a94a6', stepSize: 1 }, grid: { color: 'rgba(42,52,82,0.3)' } },
        },
      },
    });
  }

  const tbody = document.getElementById('by-symbol-tbody');
  tbody.replaceChildren();
  const entries = Object.entries(data.by_symbol).sort((a, b) => b[1].pnl - a[1].pnl);

  if (!entries.length) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 6;
    td.className = 'empty-row';
    td.textContent = 'Немає даних';
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }

  entries.forEach(([sym, s]) => {
    const tr = document.createElement('tr');
    const winRate = s.trades ? (s.wins / s.trades * 100) : 0;
    const plClass = s.pnl >= 0 ? 'pos' : 'neg';
    const cells = [
      { html: `<strong>${esc(sym)}</strong>` },
      { text: String(s.trades), cls: 'num' },
      { text: String(s.wins), cls: 'num pos' },
      { text: String(s.losses), cls: 'num neg' },
      { text: winRate.toFixed(1) + '%', cls: 'num' },
      { text: fmt.plus(s.pnl), cls: `num ${plClass}` },
    ];
    cells.forEach(c => {
      const td = document.createElement('td');
      if (c.cls) td.className = c.cls;
      if (c.html) td.innerHTML = c.html;
      else td.textContent = c.text;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}


let allocationChart = null;
const _loadingFlags = {};

async function _throttled(key, fn) {
  if (_loadingFlags[key]) return;
  _loadingFlags[key] = true;
  try {
    await fn();
  } finally {
    _loadingFlags[key] = false;
  }
}

async function loadBenchmark() {
  const el = document.getElementById('benchmark-content');
  const statusEl = document.getElementById('benchmark-status');
  if (!el) return;

  try {
    const data = await fetchJson('/api/benchmark');
    el.replaceChildren();

    if (data.error) {
      statusEl.textContent = data.error;
      return;
    }

    statusEl.textContent = data.benchmark;

    const alpha = data.alpha_pct;
    const alphaCls = alpha >= 0 ? 'pos' : 'neg';
    const alphaLabel = document.createElement('div');
    alphaLabel.className = 'muted';
    alphaLabel.style.fontSize = '11px';
    alphaLabel.textContent = 'Alpha (відносно ринку)';
    el.appendChild(alphaLabel);

    const alphaValue = document.createElement('div');
    alphaValue.className = `benchmark-alpha ${alphaCls}`;
    alphaValue.textContent = (alpha >= 0 ? '+' : '') + alpha.toFixed(2) + '%';
    el.appendChild(alphaValue);

    const stats = [
      ['Портфель за період', (data.portfolio_return_pct >= 0 ? '+' : '') + data.portfolio_return_pct.toFixed(2) + '%'],
      [`${data.benchmark} за період`, (data.benchmark_return_pct >= 0 ? '+' : '') + data.benchmark_return_pct.toFixed(2) + '%'],
      ['Beta', data.beta.toFixed(2)],
    ];

    stats.forEach(([l, v]) => {
      const row = document.createElement('div');
      row.className = 'benchmark-stat';
      const lbl = document.createElement('span');
      lbl.className = 'benchmark-label';
      lbl.textContent = l;
      const val = document.createElement('span');
      val.className = 'benchmark-value';
      val.textContent = v;
      row.appendChild(lbl);
      row.appendChild(val);
      el.appendChild(row);
    });

    const verdict = document.createElement('div');
    verdict.className = `benchmark-verdict ${data.beating_market ? 'verdict-beating' : 'verdict-losing'}`;
    verdict.textContent = data.beating_market
      ? `✅ Обганяєш ринок на ${Math.abs(alpha).toFixed(2)}%`
      : `⚠️ Програєш ринку на ${Math.abs(alpha).toFixed(2)}%`;
    el.appendChild(verdict);
  } catch (e) {
    statusEl.textContent = 'помилка';
  }
}

async function loadAllocation() {
  const data = await fetchJson('/api/allocation');
  const ctx = document.getElementById('allocation-chart');
  if (!ctx) return;

  const labels = ['Кеш'];
  const values = [data.cash.value];
  const colors = ['#6366f1'];

  const sectorColors = {
    tech: '#10b981',
    finance: '#f59e0b',
    healthcare: '#a78bfa',
    energy: '#ef4444',
    consumer_discretionary: '#3b82f6',
    consumer_staples: '#14b8a6',
    commodities: '#eab308',
    crypto: '#ec4899',
  };

  for (const [sector, info] of Object.entries(data.by_sector || {})) {
    if (info.value > 0) {
      labels.push(sector.replace('_', ' '));
      values.push(info.value);
      colors.push(sectorColors[sector] || '#8a94a6');
    }
  }

  if (allocationChart) {
    allocationChart.data.labels = labels;
    allocationChart.data.datasets[0].data = values;
    allocationChart.data.datasets[0].backgroundColor = colors;
    allocationChart.update('none');
    return;
  }

  allocationChart = new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data: values, backgroundColor: colors, borderColor: 'rgba(0,0,0,0)', borderWidth: 2 }] },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { position: 'right', labels: { color: '#e8ecf3', font: { size: 11 }, padding: 8 } },
        tooltip: { callbacks: { label: (ctx) => `${ctx.label}: $${ctx.parsed.toLocaleString()}` } },
      },
    },
  });
}

async function loadSectorHeatmap() {
  const el = document.getElementById('sector-heatmap-content');
  if (!el) return;
  el.replaceChildren();

  const data = await fetchJson('/api/sector_heatmap');
  const entries = Object.entries(data);

  if (!entries.length) {
    const empty = document.createElement('div');
    empty.className = 'muted';
    empty.style.padding = '12px';
    empty.textContent = 'Немає даних';
    el.appendChild(empty);
    return;
  }

  entries.forEach(([sector, info]) => {
    const tile = document.createElement('div');
    const cls = info.avg_change_pct >= 0 ? 'pos' : 'neg';
    tile.className = `sector-tile ${cls}`;

    const name = document.createElement('div');
    name.className = 'sector-name';
    name.textContent = sector.replace('_', ' ');
    tile.appendChild(name);

    const change = document.createElement('div');
    change.className = `sector-change ${cls}`;
    change.textContent = (info.avg_change_pct >= 0 ? '+' : '') + info.avg_change_pct.toFixed(2) + '%';
    tile.appendChild(change);

    const stocks = document.createElement('div');
    stocks.className = 'sector-stocks';
    stocks.textContent = (info.stocks || []).map(s => s.symbol).join(', ');
    tile.appendChild(stocks);

    el.appendChild(tile);
  });
}

async function loadNewsFeed() {
  const el = document.getElementById('news-feed-content');
  if (!el) return;
  el.replaceChildren();

  const news = await fetchJson('/api/news_feed');
  if (!news.length) {
    const empty = document.createElement('div');
    empty.className = 'muted';
    empty.style.padding = '12px';
    empty.textContent = 'Немає новин';
    el.appendChild(empty);
    return;
  }

  news.slice(0, 15).forEach(n => {
    const item = document.createElement('div');
    item.className = 'news-item';

    const sym = document.createElement('div');
    sym.className = 'news-symbol';
    sym.textContent = n.symbol;
    item.appendChild(sym);

    const headline = document.createElement('div');
    headline.className = 'news-headline';
    const link = document.createElement('a');
    link.href = n.url;
    link.target = '_blank';
    link.rel = 'noopener';
    link.textContent = n.headline;
    headline.appendChild(link);
    item.appendChild(headline);

    const time = document.createElement('div');
    time.className = 'news-time';
    time.textContent = fmt.dt(n.timestamp);
    item.appendChild(time);

    el.appendChild(item);
  });
}

const REGIME_LABELS = {
  bull_trend: '📈 Бичачий тренд',
  bear_trend: '📉 Ведмежий тренд',
  low_vol_range: '😴 Боковик (низька вол)',
  choppy: '🌊 Бічний рух',
  high_vol: '⚡ Висока волатильність',
  neutral: '😐 Нейтральний',
  unknown: '❓ Недостатньо даних',
};

const STRATEGY_LABELS = {
  bb_mean_reversion: 'BB Mean Reversion',
  momentum: 'Momentum',
  momentum_breakout: 'Momentum Breakout',
};

async function loadRegime() {
  const el = document.getElementById('regime-content');
  el.replaceChildren();

  const loading = document.createElement('div');
  loading.className = 'muted';
  loading.style.padding = '12px';
  loading.textContent = 'Аналіз ринку...';
  el.appendChild(loading);

  try {
    const data = await fetchJson('/api/regime');
    el.replaceChildren();

    const badge = document.createElement('div');
    badge.className = `regime-badge regime-${esc(data.regime)}`;
    badge.textContent = REGIME_LABELS[data.regime] || data.regime;
    el.appendChild(badge);

    const rec = document.createElement('div');
    rec.className = 'regime-detail';
    rec.innerHTML = `Рекомендована стратегія: <strong>${esc(STRATEGY_LABELS[data.strategy] || data.strategy)}</strong>`;
    el.appendChild(rec);

    const conf = document.createElement('div');
    conf.className = 'regime-detail';
    conf.innerHTML = `Впевненість: <strong>${(data.confidence * 100).toFixed(0)}%</strong> • Домінування: ${(data.dominance_pct * 100).toFixed(0)}%`;
    el.appendChild(conf);

    if (data.breakdown) {
      const breakdown = document.createElement('div');
      breakdown.className = 'regime-detail';
      const parts = Object.entries(data.breakdown).map(([r, n]) => `${REGIME_LABELS[r] || r}: ${n}`);
      breakdown.innerHTML = `Розподіл по акціях: <strong>${parts.join(', ')}</strong>`;
      el.appendChild(breakdown);
    }
  } catch (e) {
    el.replaceChildren();
    const err = document.createElement('div');
    err.className = 'muted';
    err.textContent = 'Помилка завантаження';
    el.appendChild(err);
  }
}

async function loadMonteCarlo() {
  const el = document.getElementById('mc-content');
  el.replaceChildren();

  const loading = document.createElement('div');
  loading.className = 'muted';
  loading.style.padding = '12px';
  loading.textContent = '1000 симуляцій на рік... (5-10 сек)';
  el.appendChild(loading);

  try {
    const data = await fetchJson('/api/monte_carlo?days=252&simulations=1000');
    el.replaceChildren();

    if (data.error) {
      const err = document.createElement('div');
      err.className = 'muted';
      err.style.padding = '12px';
      err.textContent = data.error + (data.hint ? ` (${data.hint})` : '');
      el.appendChild(err);
      return;
    }

    const bigNum = document.createElement('div');
    const expRetClass = data.expected_return_pct >= 0 ? 'pos' : 'neg';
    bigNum.className = `mc-big-number ${expRetClass}`;
    bigNum.textContent = `${data.expected_return_pct >= 0 ? '+' : ''}${data.expected_return_pct.toFixed(1)}%`;
    el.appendChild(bigNum);

    const subtitle = document.createElement('div');
    subtitle.className = 'muted';
    subtitle.style.fontSize = '11px';
    subtitle.style.marginBottom = '12px';
    subtitle.textContent = `Очікуване зростання через рік (медіана ${fmt.money(data.median_final)})`;
    el.appendChild(subtitle);

    const rows = [
      ['Ймовірність прибутку', `${data.prob_profit_pct.toFixed(0)}%`],
      ['Ймовірність DD > 10%', `${data.prob_dd_over_10_pct.toFixed(0)}%`],
      ['Ймовірність DD > 20%', `${data.prob_dd_over_20_pct.toFixed(0)}%`],
      ['Найкращий сценарій', fmt.money(data.best_final)],
      ['95% VaR', `${data.var_95_pct.toFixed(1)}%`],
      ['Найгірший сценарій', fmt.money(data.worst_final)],
    ];

    rows.forEach(([label, value]) => {
      const row = document.createElement('div');
      row.className = 'mc-row';
      const l = document.createElement('span');
      l.className = 'mc-row-label';
      l.textContent = label;
      const v = document.createElement('span');
      v.className = 'mc-row-value';
      v.textContent = value;
      row.appendChild(l);
      row.appendChild(v);
      el.appendChild(row);
    });
  } catch (e) {
    el.replaceChildren();
    const err = document.createElement('div');
    err.className = 'muted';
    err.textContent = 'Помилка: ' + e.message;
    el.appendChild(err);
  }
}

async function loadExplain() {
  const el = document.getElementById('explain-content');
  el.replaceChildren();

  const data = await fetchJson('/api/explain');
  if (data.error) {
    const hint = document.createElement('div');
    hint.className = 'muted';
    hint.style.padding = '20px';
    hint.style.textAlign = 'center';
    hint.textContent = data.hint || data.error;
    el.appendChild(hint);
    return;
  }

  const explanations = data.explanations || [];
  if (!explanations.length) {
    const hint = document.createElement('div');
    hint.className = 'muted';
    hint.style.padding = '20px';
    hint.style.textAlign = 'center';
    hint.textContent = 'Немає даних. Запусти цикл аналізу.';
    el.appendChild(hint);
    return;
  }

  explanations.forEach(exp => {
    const box = document.createElement('div');
    box.className = 'explain-symbol';

    const header = document.createElement('div');
    header.className = 'explain-header';

    const name = document.createElement('span');
    name.className = 'explain-symbol-name';
    name.textContent = exp.symbol;
    header.appendChild(name);

    const decision = document.createElement('span');
    decision.className = `explain-decision decision-${esc(exp.decision)}`;
    decision.textContent = `${exp.decision} (${(exp.final_score || 0).toFixed(2)})`;
    header.appendChild(decision);

    box.appendChild(header);

    const drivers = document.createElement('div');
    drivers.className = 'explain-drivers';

    (exp.top_drivers || []).forEach(d => {
      const row = document.createElement('div');
      row.className = 'driver-row';

      const agent = document.createElement('span');
      agent.className = 'driver-agent';
      agent.textContent = d.agent;
      row.appendChild(agent);

      const signal = document.createElement('span');
      signal.className = `signal-badge signal-${esc(d.signal)}`;
      signal.textContent = d.signal;
      row.appendChild(signal);

      const contrib = document.createElement('span');
      contrib.style.fontVariantNumeric = 'tabular-nums';
      contrib.style.fontSize = '11px';
      contrib.className = d.contribution >= 0 ? 'pos' : 'neg';
      contrib.textContent = (d.contribution >= 0 ? '+' : '') + d.contribution.toFixed(3);
      row.appendChild(contrib);

      const bar = document.createElement('div');
      bar.className = 'driver-bar';
      const fill = document.createElement('div');
      fill.className = `driver-bar-fill ${d.contribution >= 0 ? 'pos' : 'neg'}`;
      const width = Math.min(100, Math.abs(d.contribution) * 200);
      if (d.contribution >= 0) {
        fill.style.left = '50%';
        fill.style.width = width + '%';
      } else {
        fill.style.right = '50%';
        fill.style.width = width + '%';
      }
      bar.appendChild(fill);
      row.appendChild(bar);

      drivers.appendChild(row);
    });

    box.appendChild(drivers);
    el.appendChild(box);
  });
}

async function exportDataset() {
  const resultEl = document.getElementById('export-result');
  resultEl.textContent = 'Експортую...';

  const data = await fetchJson('/api/export_dataset', { method: 'POST' });
  resultEl.replaceChildren();

  const title = document.createElement('div');
  title.style.color = 'var(--pos)';
  title.style.fontWeight = '600';
  title.textContent = '✅ Готово!';
  resultEl.appendChild(title);

  const path = document.createElement('div');
  path.style.fontSize = '11px';
  path.style.marginTop = '6px';
  path.innerHTML = `Dataset: <code>${esc(data.dataset)}</code><br>Notebook: <code>${esc(data.notebook)}</code>`;
  resultEl.appendChild(path);

  const list = document.createElement('ol');
  list.style.marginTop = '10px';
  list.style.paddingLeft = '20px';
  list.style.fontSize = '12px';
  (data.instructions || []).forEach(step => {
    const li = document.createElement('li');
    li.textContent = step.replace(/^\d+\.\s*/, '');
    list.appendChild(li);
  });
  resultEl.appendChild(list);
}

async function loadStatus() {
  const s = await fetchJson('/api/status');
  setText('model-name', s.model);

  const pipeDot = document.getElementById('pipeline-dot');
  const pipeStatus = document.getElementById('pipeline-status');

  if (s.running) {
    pipeDot.classList.add('running');
    pipeDot.classList.remove('offline');
    pipeStatus.textContent = 'виконується';
  } else {
    pipeDot.classList.remove('running');
    pipeDot.classList.remove('offline');
    pipeStatus.textContent = s.auto_mode ? 'авто-режим' : 'очікує';
  }

  const autoBtn = document.getElementById('btn-auto');
  autoBtn.classList.toggle('active', s.auto_mode);
  autoBtn.textContent = s.auto_mode ? '⏸ Пауза автотрейдингу' : '▶ Автотрейдинг';
}

async function refreshAll() {
  const active = document.querySelector('.view:not(.hidden)').id;
  await Promise.allSettled([
    loadPortfolio(),
    loadStats(),
    loadEquityChart(),
    loadStatus(),
  ]);

  if (active === 'view-overview') {
    _throttled('bench', loadBenchmark);
    _throttled('alloc', loadAllocation);
    _throttled('heat', loadSectorHeatmap);
    _throttled('news', loadNewsFeed);
  }
  if (active === 'view-trades') await loadTrades();
  if (active === 'view-analyses') await loadAnalyses();
  if (active === 'view-activity') await loadActivity();
  if (active === 'view-analytics') await loadAnalyticsView();
}

function switchView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
  document.getElementById('view-' + name).classList.remove('hidden');
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === name));

  if (name === 'trades') loadTrades();
  if (name === 'analyses') loadAnalyses();
  if (name === 'market') loadMarket();
  if (name === 'activity') loadActivity();
  if (name === 'analytics') { loadAnalyticsView(); loadRollingMetrics(); }
  if (name === 'intelligence') { loadExplain(); loadVoting(); }
}

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

function _dryRun() {
  const el = document.getElementById('dry-run-toggle');
  return el && el.checked;
}

document.getElementById('btn-run').addEventListener('click', async () => {
  await fetchJson('/api/run?dry_run=' + (_dryRun() ? 'true' : 'false'), { method: 'POST' });
  setTimeout(refreshAll, 1500);
});

document.getElementById('btn-auto').addEventListener('click', async () => {
  const status = await fetchJson('/api/status');
  if (status.auto_mode) {
    await fetchJson('/api/auto/stop', { method: 'POST' });
  } else {
    const interval = document.getElementById('interval-select').value;
    await fetchJson('/api/auto/start?interval=' + interval, { method: 'POST' });
  }
  loadStatus();
});

document.getElementById('btn-reset').addEventListener('click', async () => {
  if (!confirm('Скинути весь рахунок до $100,000?')) return;
  await fetchJson('/api/reset', { method: 'POST' });
  refreshAll();
});

document.getElementById('btn-refresh-market').addEventListener('click', loadMarket);

const btnRegime = document.getElementById('btn-refresh-regime');
if (btnRegime) btnRegime.addEventListener('click', loadRegime);

const btnMC = document.getElementById('btn-refresh-mc');
if (btnMC) btnMC.addEventListener('click', loadMonteCarlo);

const btnExport = document.getElementById('btn-export-dataset');
if (btnExport) btnExport.addEventListener('click', exportDataset);

const btnRL = document.getElementById('btn-refresh-rl');
if (btnRL) btnRL.addEventListener('click', loadRLStatus);

async function loadRollingMetrics() {
  const el = document.getElementById('rolling-metrics');
  if (!el) return;
  el.replaceChildren();

  try {
    const data = await fetchJson('/api/performance');
    const windows = [
      { key: 'd7', label: '7 днів' },
      { key: 'd30', label: '30 днів' },
      { key: 'd90', label: '90 днів' },
    ];

    const grid = document.createElement('div');
    grid.className = 'metrics-grid';

    for (const w of windows) {
      const m = data[w.key] || {};
      const card = document.createElement('div');
      card.className = 'metric-card';

      const title = document.createElement('div');
      title.className = 'metric-title';
      title.textContent = w.label;
      card.appendChild(title);

      const rows = [
        { label: 'Sharpe', value: (m.sharpe ?? 0).toFixed(2), color: (m.sharpe ?? 0) >= 1 ? '#4ade80' : (m.sharpe ?? 0) < 0 ? '#f87171' : '#facc15' },
        { label: 'Sortino', value: (m.sortino ?? 0).toFixed(2), color: (m.sortino ?? 0) >= 1.5 ? '#4ade80' : (m.sortino ?? 0) < 0 ? '#f87171' : '#facc15' },
        { label: 'Calmar', value: (m.calmar ?? 0).toFixed(2), color: (m.calmar ?? 0) >= 1 ? '#4ade80' : '#facc15' },
        { label: 'Return %', value: (m.total_return_pct ?? 0).toFixed(2) + '%', color: (m.total_return_pct ?? 0) >= 0 ? '#4ade80' : '#f87171' },
        { label: 'Max DD %', value: (m.max_drawdown_pct ?? 0).toFixed(2) + '%' },
        { label: 'Samples', value: String(m.samples ?? 0), muted: true },
      ];

      for (const r of rows) {
        const row = document.createElement('div');
        row.className = 'metric-row';
        const l = document.createElement('span');
        l.textContent = r.label;
        l.className = 'metric-label';
        const v = document.createElement('strong');
        v.textContent = r.value;
        if (r.color) v.style.color = r.color;
        if (r.muted) v.className = 'muted';
        row.appendChild(l);
        row.appendChild(v);
        card.appendChild(row);
      }

      grid.appendChild(card);
    }
    el.appendChild(grid);
  } catch (e) {
    el.replaceChildren();
    const err = document.createElement('div');
    err.className = 'muted';
    err.textContent = 'Помилка завантаження';
    el.appendChild(err);
  }
}

async function loadVoting() {
  const el = document.getElementById('voting-content');
  if (!el) return;
  el.replaceChildren();

  try {
    const data = await fetchJson('/api/voting');
    const rows = data.symbols || [];
    if (!rows.length) {
      const empty = document.createElement('div');
      empty.className = 'muted';
      empty.style.padding = '20px';
      empty.style.textAlign = 'center';
      empty.textContent = 'Поки немає голосів — запусти цикл';
      el.appendChild(empty);
      return;
    }

    const table = document.createElement('table');
    table.className = 'data-table';

    const thead = document.createElement('thead');
    const hrow = document.createElement('tr');
    ['Символ', 'Голоси', 'Рішення', 'Конф.', 'Статус'].forEach(h => {
      const th = document.createElement('th');
      th.textContent = h;
      hrow.appendChild(th);
    });
    thead.appendChild(hrow);
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    for (const row of rows) {
      const tr = document.createElement('tr');

      const symTd = document.createElement('td');
      const symStrong = document.createElement('strong');
      symStrong.textContent = row.symbol;
      symTd.appendChild(symStrong);
      tr.appendChild(symTd);

      const votesTd = document.createElement('td');
      votesTd.style.fontSize = '12px';
      for (const v of (row.votes || [])) {
        const chip = document.createElement('span');
        chip.style.display = 'inline-block';
        chip.style.padding = '2px 6px';
        chip.style.marginRight = '4px';
        chip.style.borderRadius = '4px';
        chip.style.background = v.action === 'buy' ? 'rgba(74,222,128,0.15)' : 'rgba(248,113,113,0.15)';
        chip.style.color = v.action === 'buy' ? '#4ade80' : '#f87171';
        chip.textContent = `${v.source}:${v.action}@${v.confidence.toFixed(2)}`;
        votesTd.appendChild(chip);
      }
      tr.appendChild(votesTd);

      const decTd = document.createElement('td');
      if (row.signal_emitted) {
        const strong = document.createElement('strong');
        strong.textContent = row.signal_action || '—';
        strong.style.color = row.signal_action === 'buy' ? '#4ade80' : '#f87171';
        decTd.appendChild(strong);
      } else {
        const muted = document.createElement('span');
        muted.className = 'muted';
        muted.textContent = 'HOLD';
        decTd.appendChild(muted);
      }
      tr.appendChild(decTd);

      const confTd = document.createElement('td');
      confTd.textContent = row.signal_confidence ? row.signal_confidence.toFixed(2) : '—';
      tr.appendChild(confTd);

      const statusTd = document.createElement('td');
      if (row.approved) {
        statusTd.textContent = '✅ approved';
        statusTd.style.color = '#4ade80';
      } else if (row.signal_emitted) {
        statusTd.textContent = '⚠ rejected';
        statusTd.style.color = '#facc15';
      } else {
        statusTd.textContent = '—';
        statusTd.className = 'muted';
      }
      tr.appendChild(statusTd);

      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
    el.appendChild(table);
  } catch (e) {
    el.replaceChildren();
    const err = document.createElement('div');
    err.className = 'muted';
    err.textContent = 'Помилка завантаження';
    el.appendChild(err);
  }
}

function _rlRow(label, value, valueColor) {
  const row = document.createElement('div');
  row.className = 'regime-detail';
  const l = document.createElement('span');
  l.textContent = label + ': ';
  const v = document.createElement('strong');
  v.textContent = value;
  if (valueColor) v.style.color = valueColor;
  row.appendChild(l);
  row.appendChild(v);
  return row;
}

async function loadRLStatus() {
  const el = document.getElementById('rl-content');
  if (!el) return;
  el.replaceChildren();

  const loading = document.createElement('div');
  loading.className = 'muted';
  loading.style.padding = '12px';
  loading.textContent = 'Завантаження...';
  el.appendChild(loading);

  try {
    const d = await fetchJson('/api/rl');
    el.replaceChildren();

    el.appendChild(_rlRow('Статус', d.model_available ? 'модель завантажена' : 'модель відсутня', d.model_available ? '#4ade80' : '#f87171'));
    el.appendChild(_rlRow('USE_RL_DECISION', d.enabled ? 'ON' : 'OFF', d.enabled ? '#4ade80' : '#9ca3af'));
    el.appendChild(_rlRow('Залежності', d.deps_installed ? 'встановлені' : 'відсутні'));

    if (d.model_available) {
      el.appendChild(_rlRow('Розмір чекпоінта', d.model_size_mb + ' MB'));
    }

    if (d.meta) {
      const meta = d.meta;
      el.appendChild(_rlRow('Тренована', meta.timestamp || '—'));
      el.appendChild(_rlRow('Символи', (meta.symbols || []).join(', ') || '—'));
      if (meta.config) {
        el.appendChild(_rlRow('Timesteps', (meta.config.total_timesteps || 0).toLocaleString('en-US')));
        el.appendChild(_rlRow('Period', meta.config.period || '—'));
        el.appendChild(_rlRow('Device', meta.device || '—'));
      }
    }

    if (!d.deps_installed) {
      const hint = document.createElement('div');
      hint.className = 'muted';
      hint.style.padding = '10px 0 0 0';
      hint.textContent = 'pip install -r requirements-rl.txt';
      el.appendChild(hint);
    } else if (!d.model_available) {
      const hint = document.createElement('div');
      hint.className = 'muted';
      hint.style.padding = '10px 0 0 0';
      hint.textContent = 'python main.py rl-train --timesteps 200000 --period 2y';
      el.appendChild(hint);
    }
  } catch (e) {
    el.replaceChildren();
    const err = document.createElement('div');
    err.className = 'muted';
    err.textContent = 'Помилка завантаження';
    el.appendChild(err);
  }
}

refreshAll();
refreshTimer = setInterval(refreshAll, 5000);
