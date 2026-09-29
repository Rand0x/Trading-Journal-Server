/**
 * Dashboard: KPIs, equity & drawdown, journal score, calendar and breakdowns.
 * Every number comes from /api/dashboard; this module only renders.
 */

const Dashboard = {
  currentCalendarDate: new Date(),
  dashboardData: null,
  calendarMode: 'currency', // 'currency', 'r', 'pct'
  equityMode: 'money', // 'money', 'r'
  equityChart: null,
  equitySeries: null,
  drawdownSeries: null,
  uiBound: false,

  async load() {
    this.bindUi();
    try {
      const params = App.getFilterParams();
      this.dashboardData = await API.getDashboard(params);
      this.renderAll();
      this.checkAutoRefresh();
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      App.showToast(`Error loading dashboard: ${err.message}`, 'error');
    }
  },

  renderAll() {
    const data = this.dashboardData;
    if (!data) return;
    const cur = data.currency || App.getActiveCurrency();
    this.currentCurrency = cur;
    const insights = data.insights || {};
    this.renderHeader(data);
    this.renderMixedCurrencyNotice(data);
    this.renderKPIs(data.metrics || {}, cur);
    this.renderEquityCurve(data.equity_curve, cur);
    this.renderScore(insights.journal_score);
    this.renderCalendar(data.calendar, cur);
    this.renderOpenPositions(insights.open_positions || [], cur);
    this.renderRecentTrades(insights.recent_trades || [], cur);
    this.renderDailyPnlBars(data.calendar, cur);
    this.renderRDistribution(insights.r_distribution || []);
    this.renderWeekdays(insights.by_weekday || [], cur);
    this.renderLongShort(insights.long_short || {}, cur);
    this.renderConsistency(insights, data.metrics || {}, cur);
    this.renderMonthly(insights.monthly || [], cur);
    this.renderSymbols(insights.top_symbols || [], insights.worst_symbols || [], cur);
  },

  bindUi() {
    if (this.uiBound) return;
    this.uiBound = true;
    const toggle = document.getElementById('equityModeToggle');
    if (toggle) {
      toggle.addEventListener('click', e => {
        const btn = e.target.closest('button[data-mode]');
        if (!btn) return;
        this.equityMode = btn.dataset.mode;
        toggle.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
        if (this.dashboardData) this.renderEquityCurve(this.dashboardData.equity_curve, this.currentCurrency);
      });
    }
  },

  // ---------------------------------------------------------------- helpers
  esc(value) {
    return Charts.esc(value);
  },

  money(value, cur, opts = {}) {
    return App.formatMoney(value, cur || this.currentCurrency, opts);
  },

  signed(value, cur) {
    return this.money(value, cur, { showSign: true });
  },

  pnlClass(value) {
    const v = Number(value) || 0;
    return v > 0.001 ? 'color-green' : (v < -0.001 ? 'color-red' : 'color-muted');
  },

  formatR(value, digits = 2) {
    if (value === null || value === undefined || isNaN(value)) return '–';
    const v = Number(value);
    return `${v > 0 ? '+' : ''}${v.toFixed(digits)}R`;
  },

  formatDuration(minutes) {
    if (minutes === null || minutes === undefined) return '–';
    const m = Math.round(minutes);
    if (m < 60) return `${m}m`;
    const h = Math.floor(m / 60);
    if (h < 48) return `${h}h ${m % 60}m`;
    return `${Math.floor(h / 24)}d ${h % 24}h`;
  },

  shortDate(value) {
    if (!value) return '';
    const d = new Date(String(value).replace(' ', 'T'));
    if (isNaN(d)) return String(value).substring(0, 10);
    return d.toLocaleDateString('en-GB', { day: '2-digit', month: 'short' });
  },

  // ---------------------------------------------------------------- header
  renderHeader(data) {
    const label = document.getElementById('dashPeriodLabel');
    if (label) {
      const account = App.getActiveAccount();
      const accountText = account ? account.name : 'all accounts';
      const trades = (data.metrics && data.metrics.total_trades) || 0;
      label.textContent = `${App.getPeriodLabel()} · ${accountText} · ${trades} closed trade${trades === 1 ? '' : 's'}`;
    }
  },

  renderMixedCurrencyNotice(data) {
    const el = document.getElementById('dashMixedCurrencyNotice');
    if (!el) return;
    el.hidden = !(data && data.mixed_currencies);
    if (!el.hidden) {
      el.textContent = `Your accounts use different currencies (${data.currencies.join(', ')}). ` +
        'Totals add them up without conversion - select a single account for exact figures.';
    }
  },

  // ---------------------------------------------------------------- KPIs
  renderKPIs(m, currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const data = this.dashboardData || {};
    // Realized P&L incl. partial exits of open positions (same basis as calendar and equity curve)
    const insights = data.insights || {};
    const closedPnl = insights.realized_pnl !== undefined ? insights.realized_pnl : (m.net_profit || 0);
    const openPnl = (m.open_pnl !== undefined) ? m.open_pnl : (data.open_pnl || 0);
    const openCount = (m.open_trades_count !== undefined) ? m.open_trades_count : (data.open_trades_count || 0);

    // Net P&L
    const pnlEl = document.getElementById('dashNetPnl');
    pnlEl.textContent = this.signed(closedPnl, cur);
    pnlEl.className = `kpi-value ${this.pnlClass(closedPnl)}`;
    const pnlSub = document.getElementById('dashNetPnlSub');
    pnlSub.innerHTML = openCount > 0
      ? `Realized · floating <span class="${this.pnlClass(openPnl)}" style="font-weight:650;">${this.esc(this.signed(openPnl, cur))}</span>`
      : `Realized · ${m.total_trades || 0} closed trades · ${this.formatR(m.total_r, 1)}`;

    const initial = Number(data.initial_balance) || 0;
    const retPct = initial > 0 ? (closedPnl / initial) * 100 : 0;
    const delta = document.getElementById('dashReturnDelta');
    delta.textContent = `${retPct > 0 ? '+' : ''}${retPct.toFixed(1)}%`;
    delta.className = `delta ${retPct > 0.05 ? 'up' : (retPct < -0.05 ? 'down' : 'flat')}`;
    delta.title = 'Return on starting balance';
    const curve = (data.equity_curve || []).map(p => Number(p.cumulative_pnl) || 0);
    Charts.sparkline(document.getElementById('dashPnlSpark'), curve);

    // Win rate + ring
    const wins = m.winning_trades || 0;
    const losses = m.losing_trades || 0;
    const be = m.breakeven_trades || 0;
    document.getElementById('dashWinRate').textContent = `${(m.win_rate || 0).toFixed(1)}%`;
    Charts.splitBar(document.getElementById('dashWinBar'), wins, losses);
    document.getElementById('dashWinLossCount').innerHTML =
      `<span class="color-green">${wins} won</span><span>${be} BE</span><span class="color-red">${losses} lost</span>`;

    // Profit factor
    const pf = m.profit_factor || 0;
    const pfEl = document.getElementById('dashProfitFactor');
    pfEl.textContent = pf > 100 ? '∞' : pf.toFixed(2);
    pfEl.className = `kpi-value ${pf >= 1.5 ? 'color-green' : (pf >= 1.0 ? '' : 'color-red')}`;
    Charts.splitBar(document.getElementById('dashPfBar'), m.gross_profit, m.gross_loss);
    document.getElementById('dashPfLegend').innerHTML =
      `<span class="color-green">${this.esc(this.money(m.gross_profit || 0, cur, { decimals: 0 }))}</span>` +
      `<span class="color-red">-${this.esc(this.money(m.gross_loss || 0, cur, { decimals: 0 }))}</span>`;

    // Expectancy
    const exp = m.expectancy || 0;
    const expEl = document.getElementById('dashExpectancy');
    expEl.textContent = this.signed(exp, cur);
    expEl.className = `kpi-value ${this.pnlClass(exp)}`;
    document.getElementById('dashExpectancySub').textContent =
      m.avg_r !== undefined && m.avg_r !== null ? `per trade · ${this.formatR(m.avg_r)} avg` : 'per trade';

    // Avg win / avg loss
    const ratio = m.win_loss_ratio || 0;
    document.getElementById('dashWinLossRatio').textContent = ratio > 0 ? `${ratio.toFixed(2)} : 1` : '–';
    Charts.splitBar(document.getElementById('dashAvgBar'), m.avg_win, m.avg_loss);
    document.getElementById('dashAvgLegend').innerHTML =
      `<span class="color-green">${this.esc(this.signed(m.avg_win || 0, cur))}</span>` +
      `<span class="color-red">${this.esc(this.money(-(m.avg_loss || 0), cur))}</span>`;

    // Drawdown
    document.getElementById('dashDrawdown').textContent =
      `-${this.money(m.max_drawdown_amount || 0, cur)}`;
    const cdd = m.current_drawdown_amount || 0;
    document.getElementById('dashCurrentDrawdown').innerHTML =
      `${(m.max_drawdown_pct || 0).toFixed(1)}% max · now ` +
      `<span class="${cdd > 0.01 ? 'color-red' : 'color-green'}">${cdd > 0.01 ? `-${this.esc(this.money(cdd, cur))}` : 'at high'}</span>`;
  },

  // ---------------------------------------------------------------- equity
  renderEquityCurve(points = [], currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const container = document.getElementById('equityCurveChart');
    if (!container) return;
    const isR = this.equityMode === 'r';

    const pts = (points || []).filter(p => p && p.time);
    if (pts.length < 2 || typeof LightweightCharts === 'undefined') {
      this.destroyEquityChart();
      Charts.empty(container, 'The equity curve appears after your first closed trades.');
      return;
    }

    // Strictly increasing UTC timestamps (several exits can share a minute).
    let lastTs = 0;
    const line = [];
    const drawdown = [];
    let peak = -Infinity;
    pts.forEach(p => {
      let ts = Math.floor(Date.parse(`${String(p.time).replace(' ', 'T').substring(0, 16)}:00Z`) / 1000);
      if (!isFinite(ts)) return;
      if (ts <= lastTs) ts = lastTs + 1;
      lastTs = ts;
      const value = isR ? Number(p.cumulative_r) || 0 : Number(p.cumulative_pnl) || 0;
      peak = Math.max(peak, value);
      line.push({ time: ts, value });
      drawdown.push({ time: ts, value: Math.min(0, value - peak) });
    });

    const formatter = v => (isR ? `${v.toFixed(1)}R` : this.money(v, cur, { decimals: 0 }));

    if (!this.equityChart || !container.contains(this.equityChartEl)) {
      this.destroyEquityChart();
      container.innerHTML = '';
      this.equityChart = LightweightCharts.createChart(container, {
        autoSize: true,
        layout: {
          background: { type: 'solid', color: 'transparent' },
          textColor: '#647087',
          fontFamily: getComputedStyle(document.body).fontFamily,
          fontSize: 11,
          panes: { separatorColor: '#1c2433', enableResize: false },
        },
        grid: { vertLines: { visible: false }, horzLines: { color: '#161d2a' } },
        rightPriceScale: { borderVisible: false, scaleMargins: { top: 0.12, bottom: 0.08 } },
        timeScale: {
          borderVisible: false,
          timeVisible: true,
          secondsVisible: false,
          // Day and month changes as "24 Sep" / "Sep 26", several exits on one day as clock times.
          tickMarkFormatter: (ts, type) => {
            const d = new Date(ts * 1000);
            const T = LightweightCharts.TickMarkType;
            if (type === T.Year) return String(d.getUTCFullYear());
            if (type === T.Month) return d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit', timeZone: 'UTC' });
            if (type === T.DayOfMonth) return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short', timeZone: 'UTC' });
            return d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit', timeZone: 'UTC' });
          },
        },
        localization: {
          timeFormatter: ts => new Date(ts * 1000).toLocaleString('en-GB', {
            day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC',
          }),
        },
        crosshair: { mode: LightweightCharts.CrosshairMode.Magnet },
        handleScroll: false,
        handleScale: false,
      });
      this.equityChartEl = container.firstElementChild;
      // Baseline at zero: green while in profit, red while under water.
      this.equitySeries = this.equityChart.addSeries(LightweightCharts.BaselineSeries, {
        baseValue: { type: 'price', price: 0 },
        topLineColor: Charts.COLORS.pos,
        topFillColor1: 'rgba(16, 185, 129, 0.28)',
        topFillColor2: 'rgba(16, 185, 129, 0.02)',
        bottomLineColor: Charts.COLORS.neg,
        bottomFillColor1: 'rgba(239, 68, 68, 0.02)',
        bottomFillColor2: 'rgba(239, 68, 68, 0.28)',
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
      });
      this.drawdownSeries = this.equityChart.addSeries(LightweightCharts.AreaSeries, {
        lineColor: 'rgba(239, 68, 68, 0.9)',
        topColor: 'rgba(239, 68, 68, 0.05)',
        bottomColor: 'rgba(239, 68, 68, 0.35)',
        invertFilledArea: true,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
      }, 1);
      try {
        const panes = this.equityChart.panes();
        if (panes[1]) panes[1].setHeight(80);
      } catch (e) { /* older builds without pane sizing */ }
    }

    this.equitySeries.applyOptions({ priceFormat: { type: 'custom', formatter, minMove: 0.01 } });
    this.drawdownSeries.applyOptions({ priceFormat: { type: 'custom', formatter, minMove: 0.01 } });
    this.equitySeries.setData(line);
    this.drawdownSeries.setData(drawdown);
    this.equityChart.timeScale().fitContent();

    const sub = document.getElementById('equitySubtitle');
    if (sub) sub.textContent = isR ? 'Realized R over time, drawdown below' : 'Realized P&L over time (incl. partial exits), drawdown below';
  },

  destroyEquityChart() {
    if (this.equityChart) {
      try { this.equityChart.remove(); } catch (e) { /* already detached */ }
    }
    this.equityChart = null;
    this.equitySeries = null;
    this.drawdownSeries = null;
    this.equityChartEl = null;
  },

  // ---------------------------------------------------------------- score
  renderScore(scoreData) {
    const ring = document.getElementById('dashScoreRing');
    const caption = document.getElementById('dashScoreCaption');
    const list = document.getElementById('dashScoreComponents');
    if (!ring || !caption || !list) return;
    const score = scoreData ? Number(scoreData.score) || 0 : 0;
    const color = score >= 70 ? Charts.COLORS.pos : (score >= 45 ? '#f59e0b' : Charts.COLORS.neg);
    Charts.ring(ring, { size: 86, stroke: 9, percent: score, color, label: Math.round(score), sub: 'of 100', fontSize: 22 });
    const verdict = score >= 80 ? 'Excellent edge' : score >= 65 ? 'Solid and improving' : score >= 45 ? 'Mixed — find the leak' : 'Needs work';
    const comps = (scoreData && scoreData.components) || [];
    const weakest = comps.length ? comps.reduce((a, b) => (a.score <= b.score ? a : b)) : null;
    caption.innerHTML = `<strong>${this.esc(verdict)}</strong>` +
      (weakest ? `Weakest area: <span style="color:var(--text-main);">${this.esc(weakest.label)}</span>` : 'Log trades to build your score.');
    list.innerHTML = comps.map(c => {
      const col = c.score >= 70 ? Charts.COLORS.pos : (c.score >= 45 ? '#f59e0b' : Charts.COLORS.neg);
      return `<div class="meter-row" data-tip="${this.esc(`<strong>${this.esc(c.label)}</strong><br>${this.esc(c.hint)}`)}">
        <span class="meter-name">${this.esc(c.label)}</span>
        <span class="meter-value">${Math.round(c.score)}</span>
        <div class="meter-track"><div class="meter-fill" style="width:${Math.max(2, c.score)}%;background:${col};"></div></div>
      </div>`;
    }).join('');
  },

  // ---------------------------------------------------------------- calendar
  setCalendarMode(mode) {
    this.calendarMode = mode;
    [['Currency', 'currency'], ['R', 'r'], ['Pct', 'pct']].forEach(([id, key]) => {
      const btn = document.getElementById(`calMode${id}`);
      if (btn) btn.classList.toggle('active', key === mode);
    });
    if (this.dashboardData) {
      this.renderCalendar(this.dashboardData.calendar, this.currentCurrency);
    }
  },

  // Short form for narrow calendar cells: +1.2k, -350, +2.4R, +0.8%
  compactValue(value, cur) {
    const v = Number(value) || 0;
    const sign = v > 0 ? '+' : (v < 0 ? '-' : '');
    const abs = Math.abs(v);
    if (this.calendarMode === 'r') return `${sign}${abs.toFixed(1)}R`;
    if (this.calendarMode === 'pct') return `${sign}${abs.toFixed(1)}%`;
    const sym = App.getCurrencySymbol(cur).trim();
    return abs >= 1000 ? `${sign}${sym}${(abs / 1000).toFixed(1)}k` : `${sign}${sym}${Math.round(abs)}`;
  },

  formatCalendarValue(pnl, r, pct, cur) {
    if (this.calendarMode === 'r') return { text: this.formatR(r), value: r };
    if (this.calendarMode === 'pct') return { text: `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%`, value: pct };
    return { text: pnl > 0.01 ? this.signed(pnl, cur) : this.money(pnl, cur), value: pnl };
  },

  renderCalendar(calendarData = {}, currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const grid = document.getElementById('calendarDaysGrid');
    const weeks = document.getElementById('calendarWeeks');
    if (!grid) return;
    calendarData = calendarData || {};
    grid.innerHTML = '';
    if (weeks) weeks.innerHTML = '';

    const year = this.currentCalendarDate.getFullYear();
    const month = this.currentCalendarDate.getMonth();
    const monthLabel = this.currentCalendarDate.toLocaleDateString('en-GB', { month: 'long', year: 'numeric' });
    document.getElementById('calendarMonthLabel').textContent = monthLabel;

    // Monday-first grid
    const lead = (new Date(year, month, 1).getDay() + 6) % 7;
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const prevMonthDays = new Date(year, month, 0).getDate();
    const todayKey = new Date().toISOString().substring(0, 10);

    const monthKeys = [];
    for (let day = 1; day <= daysInMonth; day++) {
      monthKeys.push(`${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`);
    }
    const maxAbs = Math.max(1, ...monthKeys.map(k => Math.abs((calendarData[k] || {}).net_profit || 0)));

    for (let i = lead - 1; i >= 0; i--) {
      const card = document.createElement('div');
      card.className = 'calendar-day-card other-month';
      card.innerHTML = `<span class="day-number">${prevMonthDays - i}</span>`;
      grid.appendChild(card);
    }

    const totals = { pnl: 0, r: 0, wins: 0, losses: 0, be: 0, pct: 0 };
    const weekTotals = [];

    monthKeys.forEach((dateKey, idx) => {
      const day = idx + 1;
      const cellIndex = lead + idx;
      const weekIdx = Math.floor(cellIndex / 7);
      if (!weekTotals[weekIdx]) weekTotals[weekIdx] = { pnl: 0, r: 0, pct: 0, trades: 0, days: 0 };

      const dayData = calendarData[dateKey];
      const card = document.createElement('div');
      let cls = 'calendar-day-card';
      let body = '';
      if (dayData && dayData.trades_count > 0) {
        const pnl = dayData.net_profit || 0;
        const r = dayData.r_multiple || 0;
        const pct = dayData.pct_return || 0;
        totals.pnl += pnl; totals.r += r; totals.pct += pct;
        totals.wins += dayData.wins || 0;
        totals.losses += dayData.losses || 0;
        totals.be += dayData.breakevens || 0;
        const wk = weekTotals[weekIdx];
        wk.pnl += pnl; wk.r += r; wk.pct += pct; wk.trades += dayData.trades_count; wk.days += 1;

        cls += ' has-trades';
        if (pnl > 0.01) cls += ' profit';
        else if (pnl < -0.01) cls += ' loss';
        card.style.setProperty('--intensity', (Math.abs(pnl) / maxAbs).toFixed(2));
        const shown = this.formatCalendarValue(pnl, r, pct, cur);
        body = `<div>
            <div class="day-pnl ${this.pnlClass(shown.value)}">${this.esc(shown.text)}</div>
            <div class="day-pnl-compact ${this.pnlClass(shown.value)}">${this.esc(this.compactValue(shown.value, cur))}</div>
            <div class="day-sub">${dayData.wins || 0}W · ${dayData.losses || 0}L</div>
          </div>`;
        card.title = `${dateKey}: ${dayData.trades_count} trade(s) — click to open`;
        card.addEventListener('click', () => App.navigateToTradesWithDate(dateKey));
      }
      if (dateKey === todayKey) cls += ' today';
      card.className = cls;
      card.innerHTML = `
        <div class="day-header">
          <span class="day-number">${day}</span>
          ${dayData && dayData.trades_count ? `<span class="day-badge">${dayData.trades_count} tr</span>` : ''}
        </div>
        ${body}`;
      grid.appendChild(card);
    });

    // Trailing cells to complete the last week
    const trailing = (7 - ((lead + daysInMonth) % 7)) % 7;
    for (let i = 1; i <= trailing; i++) {
      const card = document.createElement('div');
      card.className = 'calendar-day-card other-month';
      card.innerHTML = `<span class="day-number">${i}</span>`;
      grid.appendChild(card);
    }

    if (weeks) {
      const rows = Math.ceil((lead + daysInMonth) / 7);
      for (let w = 0; w < rows; w++) {
        const wk = weekTotals[w] || { pnl: 0, r: 0, pct: 0, trades: 0, days: 0 };
        const shown = this.formatCalendarValue(wk.pnl, wk.r, wk.pct, cur);
        const card = document.createElement('div');
        card.className = 'week-card';
        card.innerHTML = `
          <span class="week-label">WEEK ${w + 1}</span>
          <div>
            <div class="week-pnl ${wk.trades ? this.pnlClass(shown.value) : 'color-muted'}">${wk.trades ? this.esc(shown.text) : '–'}</div>
            <div class="week-sub">${wk.days} day${wk.days === 1 ? '' : 's'} · ${wk.trades} tr</div>
          </div>`;
        weeks.appendChild(card);
      }
    }

    const sumPnlEl = document.getElementById('calSummaryPnl');
    sumPnlEl.textContent = this.signed(totals.pnl, cur);
    sumPnlEl.className = `sum-value ${this.pnlClass(totals.pnl)}`;
    const sumREl = document.getElementById('calSummaryR');
    sumREl.textContent = this.formatR(totals.r);
    sumREl.className = `sum-value ${this.pnlClass(totals.r)}`;
    document.getElementById('calSummaryWBL').textContent = `${totals.wins} · ${totals.be} · ${totals.losses}`;
    const sumPctEl = document.getElementById('calSummaryPct');
    sumPctEl.textContent = `${totals.pct > 0 ? '+' : ''}${totals.pct.toFixed(2)}%`;
    sumPctEl.className = `sum-value ${this.pnlClass(totals.pct)}`;
  },

  calendarPrevMonth() {
    this.currentCalendarDate.setDate(1);
    this.currentCalendarDate.setMonth(this.currentCalendarDate.getMonth() - 1);
    this.renderCalendar(this.dashboardData ? this.dashboardData.calendar : {}, this.currentCurrency);
  },

  calendarNextMonth() {
    this.currentCalendarDate.setDate(1);
    this.currentCalendarDate.setMonth(this.currentCalendarDate.getMonth() + 1);
    this.renderCalendar(this.dashboardData ? this.dashboardData.calendar : {}, this.currentCurrency);
  },

  calendarToday() {
    this.currentCalendarDate = new Date();
    this.renderCalendar(this.dashboardData ? this.dashboardData.calendar : {}, this.currentCurrency);
  },

  // ---------------------------------------------------------------- lists
  tradeListItem(t, cur, opts = {}) {
    const dir = (t.direction || '').toUpperCase() === 'SELL' ? 'sell' : 'buy';
    const pnl = Number(t.net_profit) || 0;
    const when = opts.open ? `opened ${this.shortDate(t.open_time)}` : this.shortDate(t.close_time || t.open_time);
    const meta = [when, t.setup_name, t.volume ? `${Number(t.volume).toFixed(2)} lots` : ''].filter(Boolean).join(' · ');
    return `<div class="trade-list-item" data-trade-id="${Number(t.id)}" title="Open trade details">
      <span class="dir-dot ${dir}">${dir === 'sell' ? 'SELL' : 'BUY'}</span>
      <div style="min-width:0;">
        <div class="sym">${this.esc(t.symbol)}</div>
        <div class="meta">${this.esc(meta)}</div>
      </div>
      <div class="val ${this.pnlClass(pnl)}">${this.esc(this.signed(pnl, t.account_currency || cur))}
        <small>${t.r_multiple !== null && t.r_multiple !== undefined ? this.esc(this.formatR(t.r_multiple)) : (opts.open ? 'floating' : '')}</small>
      </div>
    </div>`;
  },

  bindTradeList(container) {
    container.querySelectorAll('[data-trade-id]').forEach(el => {
      el.addEventListener('click', () => {
        if (typeof TradeDetail !== 'undefined' && TradeDetail.open) TradeDetail.open(Number(el.dataset.tradeId));
      });
    });
  },

  renderOpenPositions(list, cur) {
    const container = document.getElementById('dashOpenList');
    const badge = document.getElementById('dashOpenPnl');
    if (!container) return;
    const total = list.reduce((s, t) => s + (Number(t.net_profit) || 0), 0);
    if (badge) {
      badge.textContent = list.length ? `${list.length} · ${this.signed(total, cur)}` : 'None';
      badge.className = `badge ${list.length ? (total >= 0 ? 'badge-win' : 'badge-loss') : 'badge-be'}`;
    }
    if (!list.length) {
      container.innerHTML = '<div class="empty-state" style="min-height:64px;">No open positions.</div>';
      return;
    }
    container.innerHTML = list.map(t => this.tradeListItem(t, cur, { open: true })).join('');
    this.bindTradeList(container);
  },

  renderRecentTrades(list, cur) {
    const container = document.getElementById('dashRecentList');
    if (!container) return;
    if (!list.length) {
      container.innerHTML = '<div class="empty-state">No closed trades in this period.</div>';
      return;
    }
    container.innerHTML = list.map(t => this.tradeListItem(t, cur)).join('');
    this.bindTradeList(container);
  },

  // ---------------------------------------------------------------- breakdowns
  renderDailyPnlBars(calendarData = {}, currency) {
    const cur = currency || this.currentCurrency;
    const container = document.getElementById('dailyPnlBarContainer');
    if (!container) return;
    const dates = Object.keys(calendarData || {}).sort().slice(-60);
    const sub = document.getElementById('dailyPnlSubtitle');
    if (sub) sub.textContent = dates.length ? `Last ${dates.length} trading day${dates.length === 1 ? '' : 's'}` : 'No trading days yet';
    Charts.bars(container, dates.map(d => {
      const day = calendarData[d];
      return {
        label: d,
        short: this.shortDate(d),
        value: day.net_profit || 0,
        tip: `<strong>${this.esc(d)}</strong><br>${this.esc(this.signed(day.net_profit || 0, cur))} · ${day.trades_count} trade(s)`,
      };
    }), { height: 220, format: v => this.money(v, cur, { decimals: 0 }), emptyText: 'No daily results yet.' });
  },

  renderRDistribution(buckets) {
    const container = document.getElementById('rDistributionChart');
    if (!container) return;
    const total = buckets.reduce((s, b) => s + b.count, 0);
    const sub = document.getElementById('rDistSubtitle');
    if (sub) sub.textContent = total ? `${total} closed trades with a known risk` : 'Add a stop loss or risk amount to see R';
    if (!total) {
      Charts.empty(container, 'No trades with an R-multiple yet.');
      return;
    }
    Charts.bars(container, buckets.map(b => ({
      label: b.label,
      value: b.count,
      color: b.positive ? Charts.COLORS.pos : Charts.COLORS.neg,
      tip: `<strong>${this.esc(b.label)}</strong><br>${b.count} trade(s) · ${((b.count / total) * 100).toFixed(0)}%`,
    })), { height: 220, format: v => String(Math.round(v)) });
  },

  renderWeekdays(days, cur) {
    const container = document.getElementById('weekdayChart');
    if (!container) return;
    if (!days.some(d => d.trades > 0)) {
      Charts.empty(container, 'No closed trades yet.');
      return;
    }
    Charts.bars(container, days.map(d => ({
      label: d.day,
      short: d.day.substring(0, 3),
      value: d.net_profit,
      tip: `<strong>${this.esc(d.day)}</strong><br>${this.esc(this.signed(d.net_profit, cur))}<br>${d.trades} trades · ${d.win_rate}% win rate`,
    })), { height: 190, format: v => this.money(v, cur, { decimals: 0 }) });
  },

  renderLongShort(ls, cur) {
    const container = document.getElementById('longShortPanel');
    if (!container) return;
    const long = ls.long || {};
    const short = ls.short || {};
    const total = (long.trades || 0) + (short.trades || 0);
    if (!total) {
      Charts.empty(container, 'No closed trades yet.');
      return;
    }
    const card = (name, s, dir) => `<div class="compare-card">
      <div class="compare-head"><span class="badge badge-${dir}">${name}</span><span class="panel-sub">${s.trades || 0} trades</span></div>
      <div class="compare-pnl ${this.pnlClass(s.net_profit)}">${this.esc(this.signed(s.net_profit || 0, cur))}</div>
      <dl style="margin-top:8px;">
        <dt>Win rate</dt><dd>${(s.win_rate || 0).toFixed(1)}%</dd>
        <dt>Avg R</dt><dd>${this.esc(this.formatR(s.avg_r))}</dd>
      </dl>
    </div>`;
    const longShare = ((long.trades || 0) / total) * 100;
    container.innerHTML = `<div class="compare-grid">${card('Long', long, 'buy')}${card('Short', short, 'sell')}</div>
      <div style="margin-top:14px;">
        <div class="split-legend" style="margin-bottom:6px;"><span>Long ${longShare.toFixed(0)}%</span><span>Short ${(100 - longShare).toFixed(0)}%</span></div>
        <div class="split-bar"><span class="pos" style="width:${longShare}%"></span><span class="neg" style="width:${100 - longShare}%"></span></div>
      </div>`;
  },

  renderConsistency(insights, m, cur) {
    const container = document.getElementById('consistencyPanel');
    if (!container) return;
    const ds = insights.day_stats || {};
    const hold = insights.holding || {};
    const item = (label, value, note, cls = '') => `<div class="stat-item">
      <span class="stat-label">${this.esc(label)}</span>
      <span class="stat-value ${cls}">${this.esc(value)}</span>
      ${note ? `<span class="stat-note">${this.esc(note)}</span>` : ''}
    </div>`;
    const streak = m.current_streak_type === 'WIN'
      ? { text: `${m.current_streak_count} win${m.current_streak_count === 1 ? '' : 's'}`, cls: 'color-green' }
      : m.current_streak_type === 'LOSS'
        ? { text: `${m.current_streak_count} loss${m.current_streak_count === 1 ? '' : 'es'}`, cls: 'color-red' }
        : { text: '–', cls: '' };
    container.innerHTML = [
      item('Green days', `${ds.green_days || 0} / ${ds.trading_days || 0}`, `${(ds.green_day_rate || 0).toFixed(0)}% of trading days`),
      item('Avg daily P&L', this.signed(ds.avg_daily_pnl || 0, cur), '', this.pnlClass(ds.avg_daily_pnl)),
      item('Best day', ds.best_day ? this.signed(ds.best_day.net_profit, cur) : '–', ds.best_day ? this.shortDate(ds.best_day.date) : '', 'color-green'),
      item('Worst day', ds.worst_day ? this.signed(ds.worst_day.net_profit, cur) : '–', ds.worst_day ? this.shortDate(ds.worst_day.date) : '', ds.worst_day && ds.worst_day.net_profit < 0 ? 'color-red' : ''),
      item('Current streak', streak.text, `best ${m.max_win_streak || 0}W · worst ${m.max_loss_streak || 0}L`, streak.cls),
      item('Hold time', this.formatDuration(hold.all_min), `win ${this.formatDuration(hold.winners_min)} · loss ${this.formatDuration(hold.losers_min)}`),
    ].join('');
  },

  renderMonthly(months, cur) {
    const container = document.getElementById('monthlyChart');
    if (!container) return;
    if (!months.length) {
      Charts.empty(container, 'No closed trades yet.');
      return;
    }
    const recent = months.slice(-12);
    Charts.bars(container, recent.map(m => {
      const d = new Date(`${m.month}-01T00:00:00`);
      const label = isNaN(d) ? m.month : d.toLocaleDateString('en-GB', { month: 'short', year: '2-digit' });
      return {
        label,
        value: m.net_profit,
        tip: `<strong>${this.esc(label)}</strong><br>${this.esc(this.signed(m.net_profit, cur))} · ${this.esc(this.formatR(m.total_r, 1))}<br>${m.trades} trades · ${m.win_rate}% win rate`,
      };
    }), { height: 210, format: v => this.money(v, cur, { decimals: 0 }) });
  },

  renderSymbols(top, worst, cur) {
    const container = document.getElementById('symbolsPanel');
    if (!container) return;
    const seen = new Set();
    const rows = [...top, ...worst].filter(s => {
      if (seen.has(s.symbol)) return false;
      seen.add(s.symbol);
      return true;
    }).sort((a, b) => b.net_profit - a.net_profit);
    Charts.hbars(container, rows.map(s => ({
      label: s.symbol,
      sub: `${s.trades} trades · ${s.win_rate}%`,
      value: s.net_profit,
    })), { format: v => this.signed(v, cur), emptyText: 'No closed trades yet.' });
  },

  // ---------------------------------------------------------------- refresh
  autoRefreshTimer: null,
  refreshInFlight: false,

  checkAutoRefresh() {
    this.stopAutoRefresh();
    const data = this.dashboardData;
    const openCount = data ? (data.open_trades_count || (data.metrics && data.metrics.open_trades_count) || 0) : 0;
    if (openCount <= 0) return;

    this.autoRefreshTimer = setInterval(async () => {
      if (App.currentView !== 'dashboard') {
        this.stopAutoRefresh();
        return;
      }
      // Skip ticks while the tab is hidden or the previous request is still running.
      if (document.hidden || this.refreshInFlight) return;
      this.refreshInFlight = true;
      try {
        const params = App.getFilterParams();
        this.dashboardData = await API.getDashboard(params);
        this.renderAll();

        const stillOpen = this.dashboardData.open_trades_count || (this.dashboardData.metrics && this.dashboardData.metrics.open_trades_count) || 0;
        if (stillOpen <= 0) {
          this.stopAutoRefresh();
        }
      } catch (err) {
        console.error('Dashboard auto-refresh error:', err);
      } finally {
        this.refreshInFlight = false;
      }
    }, 10000);
  },

  stopAutoRefresh() {
    if (this.autoRefreshTimer) {
      clearInterval(this.autoRefreshTimer);
      this.autoRefreshTimer = null;
    }
  }
};
