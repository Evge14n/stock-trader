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
  autoBtn.textContent = s.auto_mode ? '⏸ Стоп авто' : 'Авто-режим';
}

async function refreshAll() {
  const active = document.querySelector('.view:not(.hidden)').id;
  await Promise.allSettled([
    loadPortfolio(),
    loadStats(),
    loadEquityChart(),
    loadStatus(),
  ]);

  if (active === 'view-trades') await loadTrades();
  if (active === 'view-analyses') await loadAnalyses();
  if (active === 'view-activity') await loadActivity();
}

function switchView(name) {
  document.querySelectorAll('.view').forEach(v => v.classList.add('hidden'));
  document.getElementById('view-' + name).classList.remove('hidden');
  document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.view === name));

  if (name === 'trades') loadTrades();
  if (name === 'analyses') loadAnalyses();
  if (name === 'market') loadMarket();
  if (name === 'activity') loadActivity();
  if (name === 'analytics') loadAnalyticsView();
}

document.querySelectorAll('.nav-btn').forEach(btn => {
  btn.addEventListener('click', () => switchView(btn.dataset.view));
});

document.getElementById('btn-run').addEventListener('click', async () => {
  await fetchJson('/api/run?dry_run=false', { method: 'POST' });
  setTimeout(refreshAll, 1500);
});

document.getElementById('btn-run-dry').addEventListener('click', async () => {
  await fetchJson('/api/run?dry_run=true', { method: 'POST' });
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

refreshAll();
refreshTimer = setInterval(refreshAll, 5000);
