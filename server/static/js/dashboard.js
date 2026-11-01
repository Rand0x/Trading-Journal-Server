/**
 * Dashboard: KPIs, equity curve, journal score, calendar and breakdowns.
 * Every number comes from /api/dashboard; this module only renders.
 */

const Dashboard = {
  currentCalendarDate: new Date(),
  dashboardData: null,
  calendarMode: 'currency', // 'currency', 'r', 'pct'
  equityMode: 'money', // 'money', 'r'
  equityChart: null,
  equitySeries: null,
  uiBound: false,
  pctMode: false,

  // ------------------------------------------------------------ all accounts
  // "All accounts" with several accounts: no sums across currencies. Every
  // figure is in % of each account's own starting balance (equal-weighted).
  getOverview() {
    const ov = this.dashboardData && this.dashboardData.overview;
    return ov && Array.isArray(ov.accounts) ? ov : null;
  },

  getCalendarData() {
    if (!this.dashboardData) return {};
    const ov = this.getOverview();
    return (ov ? ov.calendar : this.dashboardData.calendar) || {};
  },

  /** The overview has no meaningful currency total, so "P&L" shows % instead. */
  effectiveCalendarMode() {
    return this.getOverview() && this.calendarMode === 'currency' ? 'pct' : this.calendarMode;
  },

  syncCalendarModeButtons() {
    const mode = this.effectiveCalendarMode();
    const currencyBtn = document.getElementById('calModeCurrency');
    if (currencyBtn) currencyBtn.hidden = Boolean(this.getOverview());
    [['Currency', 'currency'], ['R', 'r'], ['Pct', 'pct']].forEach(([id, key]) => {
      const btn = document.getElementById(`calMode${id}`);
      if (btn) btn.classList.toggle('active', key === mode);
    });
  },

  /** Panel amounts: % share of the average return in the overview, money otherwise. */
  amount(value, cur, opts = {}) {
    return this.pctMode ? this.formatPct(value, 1) : this.money(value, cur, opts);
  },

  amountSigned(value, cur) {
    return this.pctMode ? this.formatPct(value, 1) : this.signed(value, cur);
  },

  renderEquitySection(cur) {
    const data = this.dashboardData || {};
    const curves = data.account_curves;
    const isOverview = Boolean(this.getOverview() && curves && curves.accounts && curves.accounts.length);
    const legend = document.getElementById('equityCurveLegend');
    ['equityModeToggle', 'equityStaticLegend', 'equityReadout'].forEach(id => {
      const el = document.getElementById(id);
      if (el) el.hidden = isOverview;
    });
    this.setText('equityTitle', isOverview ? 'Account returns' : 'Equity curve');
    if (isOverview) {
      this.destroyEquityChart();
      this.setText('equitySubtitle', "% of each account's starting balance · dashed: equal-weighted average · hover a line to highlight it");
      this.renderAccountReturnCurves(curves);
      return;
    }
    this.returnChart = null;
    if (legend) {
      legend.innerHTML = '';
      legend.hidden = true;
    }
    this.renderEquityCurve(data.equity_curve, cur);
  },

  renderOverviewKPIs(m, ov) {
    const n = ov.active_accounts || 0;
    const nText = `${n} account${n === 1 ? '' : 's'}`;
    const pnlEl = document.getElementById('dashNetPnl');
    pnlEl.textContent = this.formatPct(ov.avg_return_pct);
    pnlEl.className = `kpi-value ${this.pnlClass(ov.avg_return_pct)}`;
    document.getElementById('dashNetPnlSub').innerHTML = ov.open_trades_count > 0
      ? `Equal-weighted · ${nText} · floating <span class="${this.pnlClass(ov.avg_floating_pct)}" style="font-weight:650;">${this.formatPct(ov.avg_floating_pct)}</span>`
      : `Equal-weighted · ${nText} · ${m.total_trades || 0} closed trades`;
    const delta = document.getElementById('dashReturnDelta');
    delta.textContent = 'Ø';
    delta.className = 'delta flat';
    delta.title = 'Average of the accounts, each in % of its own starting balance';
    const avg = ((this.dashboardData.account_curves || {}).average || []).map(p => Number(p.pct) || 0);
    Charts.sparkline(document.getElementById('dashPnlSpark'), avg);

    const wins = m.winning_trades || 0;
    const losses = m.losing_trades || 0;
    document.getElementById('dashWinRate').textContent = `${(m.win_rate || 0).toFixed(1)}%`;
    Charts.splitBar(document.getElementById('dashWinBar'), wins, losses);
    document.getElementById('dashWinLossCount').innerHTML =
      `<span class="color-green">${wins} won</span><span>${m.breakeven_trades || 0} BE</span><span class="color-red">${losses} lost</span>`;

    const pf = ov.profit_factor || 0;
    const pfEl = document.getElementById('dashProfitFactor');
    pfEl.textContent = pf > 100 ? '∞' : pf.toFixed(2);
    pfEl.className = `kpi-value ${pf >= 1.5 ? 'color-green' : (pf >= 1.0 ? '' : 'color-red')}`;
    Charts.splitBar(document.getElementById('dashPfBar'), ov.gross_win_pct, ov.gross_loss_pct);
    document.getElementById('dashPfLegend').innerHTML =
      `<span class="color-green">${this.formatPct(ov.gross_win_pct, 1)}</span><span class="color-red">${this.formatPct(-(ov.gross_loss_pct || 0), 1)}</span>`;

    const expEl = document.getElementById('dashExpectancy');
    expEl.textContent = this.formatPct(ov.expectancy_pct);
    expEl.className = `kpi-value ${this.pnlClass(ov.expectancy_pct)}`;
    document.getElementById('dashExpectancySub').textContent = 'per trade, % of its account';

    const ratio = ov.win_loss_ratio || 0;
    document.getElementById('dashWinLossRatio').textContent = ratio > 0 ? `${ratio.toFixed(2)} : 1` : '–';
    Charts.splitBar(document.getElementById('dashAvgBar'), ov.avg_win_pct, ov.avg_loss_pct);
    document.getElementById('dashAvgLegend').innerHTML =
      `<span class="color-green">${this.formatPct(ov.avg_win_pct)}</span><span class="color-red">${this.formatPct(-(ov.avg_loss_pct || 0))}</span>`;

    document.getElementById('dashDrawdown').textContent = `-${(ov.max_drawdown_pct || 0).toFixed(1)}%`;
    const cdd = ov.current_drawdown_pct || 0;
    document.getElementById('dashCurrentDrawdown').innerHTML =
      `average curve · now <span class="${cdd > 0.01 ? 'color-red' : 'color-green'}">${cdd > 0.01 ? `-${cdd.toFixed(1)}%` : 'at high'}</span>`;
  },

  ACCOUNT_LINE_COLORS: ['#3b82f6', '#f59e0b', '#a855f7', '#14b8a6', '#ec4899', '#84cc16', '#f97316', '#06b6d4'],
  AVERAGE_LINE_COLOR: '#e5e7eb',
  DIMMED_LINE_COLOR: '#4b5563',
  returnChart: null,
  returnChartHighlight: null,

  escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, ch => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[ch]));
  },

  formatPct(value, decimals = 2) {
    const v = Number(value || 0);
    return `${v > 0 ? '+' : ''}${v.toFixed(decimals)} %`;
  },

  /** "YYYY-MM-DD HH:MM" (or with "T") -> local epoch ms; only relative positions matter. */
  parseCurveTime(value) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[ T](\d{2}):(\d{2}))?/.exec(String(value || ''));
    if (!m) return 0;
    return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0)).getTime();
  },

  /** Last curve point at or before t (returns are realized step by step). */
  curvePointAt(points, t) {
    let found = points[0] || null;
    for (const p of points) {
      if (p.t <= t) found = p;
      else break;
    }
    return found;
  },

  distanceToSegment(px, py, a, b) {
    const dx = b.x - a.x;
    const dy = b.y - a.y;
    const lenSq = dx * dx + dy * dy;
    const t = lenSq > 0 ? Math.max(0, Math.min(1, ((px - a.x) * dx + (py - a.y) * dy) / lenSq)) : 0;
    return Math.hypot(px - (a.x + t * dx), py - (a.y + t * dy));
  },

  /** Key of the line closest to (px, py) within maxDist pixels, else null. */
  nearestSeriesKey(series, px, py, maxDist = 14) {
    let bestKey = null;
    let bestDist = maxDist;
    series.forEach(s => {
      const coords = s.coords || [];
      for (let i = 0; i < coords.length; i++) {
        const b = coords[i];
        const a = i > 0 ? coords[i - 1] : b;
        const d = this.distanceToSegment(px, py, a, b);
        if (d <= bestDist) {
          bestDist = d;
          bestKey = s.key;
        }
      }
    });
    return bestKey;
  },

  renderAccountReturnCurves(curves) {
    const container = document.getElementById('equityCurveChart');
    if (!container) return;
    container.innerHTML = '';

    const series = curves.accounts.map((acc, idx) => ({
      key: `acc-${acc.account_id}`,
      label: acc.name,
      currency: acc.currency,
      // Same colour slot as the account's row in the comparison table.
      color: this.ACCOUNT_LINE_COLORS[(acc.color_index ?? idx) % this.ACCOUNT_LINE_COLORS.length],
      dashed: false,
      account: acc,
      totalPct: acc.return_pct,
      points: acc.points.map(p => ({ t: this.parseCurveTime(p.time), pct: p.pct, time: p.time }))
    }));
    if (series.length > 1 && Array.isArray(curves.average) && curves.average.length > 0) {
      series.push({
        key: 'avg',
        label: 'Average (equal-weighted)',
        currency: '',
        color: this.AVERAGE_LINE_COLOR,
        dashed: true,
        account: null,
        totalPct: curves.average_return_pct,
        points: curves.average.map(p => ({ t: this.parseCurveTime(p.time), pct: p.pct, time: p.time }))
      });
    }
    // Keep the hovered account highlighted across auto-refresh re-renders.
    if (!series.some(s => s.key === this.returnChartHighlight)) this.returnChartHighlight = null;

    const width = container.clientWidth || 450;
    const height = container.clientHeight || 280;
    const dpr = window.devicePixelRatio || 1;
    const canvas = document.createElement('canvas');
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    canvas.style.width = `${width}px`;
    canvas.style.height = `${height}px`;
    canvas.style.touchAction = 'pan-y';
    container.appendChild(canvas);

    const tooltip = document.createElement('div');
    tooltip.className = 'equity-tooltip';
    tooltip.style.display = 'none';
    container.appendChild(tooltip);

    this.returnChart = {
      canvas, tooltip, dpr, width, height, series,
      layout: this.layoutReturnChart(series, width, height)
    };
    this.drawReturnChart();

    canvas.addEventListener('pointermove', e => this.onReturnChartPointer(e));
    canvas.addEventListener('pointerdown', e => this.onReturnChartPointer(e));
    canvas.addEventListener('pointerleave', e => {
      // A finished touch also fires pointerleave; keep a tapped line highlighted.
      if (e.pointerType === 'mouse') this.setReturnChartHighlight(null);
    });

    this.renderReturnLegend();
  },

  layoutReturnChart(series, width, height) {
    const padding = { top: 16, right: 58, bottom: 28, left: 54 };
    const all = series.flatMap(s => s.points);
    let tMin = Math.min(...all.map(p => p.t));
    let tMax = Math.max(...all.map(p => p.t));
    if (!(tMax > tMin)) {
      tMin -= 12 * 3600 * 1000;
      tMax += 12 * 3600 * 1000;
    }
    let yMin = Math.min(0, ...all.map(p => p.pct));
    let yMax = Math.max(0, ...all.map(p => p.pct));
    const span = (yMax - yMin) || 1;
    // Round the axis to readable steps (+5 %, +10 %, ...) with a little headroom.
    const yStep = this.niceStep(span / 5);
    yMin = Math.floor((yMin - span * 0.04) / yStep) * yStep;
    yMax = Math.ceil((yMax + span * 0.04) / yStep) * yStep;

    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const xOf = t => padding.left + ((t - tMin) / (tMax - tMin)) * chartW;
    const yOf = pct => padding.top + (1 - (pct - yMin) / (yMax - yMin)) * chartH;

    series.forEach(s => {
      s.coords = s.points.map(p => ({ x: xOf(p.t), y: yOf(p.pct) }));
      // Hold the latest return to the right edge so all final values line up.
      const last = s.coords[s.coords.length - 1];
      if (last && last.x < padding.left + chartW - 0.5) {
        s.coords.push({ x: padding.left + chartW, y: last.y });
      }
    });

    return { padding, tMin, tMax, yMin, yMax, yStep, chartW, chartH, xOf, yOf };
  },

  niceStep(raw) {
    if (!(raw > 0)) return 1;
    const magnitude = Math.pow(10, Math.floor(Math.log10(raw)));
    const f = raw / magnitude;
    const nice = f <= 1 ? 1 : (f <= 2 ? 2 : (f <= 2.5 ? 2.5 : (f <= 5 ? 5 : 10)));
    return nice * magnitude;
  },

  drawReturnChart() {
    const rc = this.returnChart;
    if (!rc) return;
    const ctx = rc.canvas.getContext('2d');
    const { padding, tMin, tMax, yMin, yMax, yStep, chartW, yOf } = rc.layout;
    ctx.setTransform(rc.dpr, 0, 0, rc.dpr, 0, 0);
    ctx.clearRect(0, 0, rc.width, rc.height);
    ctx.font = '10px -apple-system, sans-serif';

    // Grid with % labels on rounded steps
    const decimals = yStep >= 1 ? 0 : (yStep >= 0.1 ? 1 : 2);
    for (let val = yMin; val <= yMax + yStep / 2; val += yStep) {
      const y = yOf(val);
      ctx.strokeStyle = '#1a2333';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(padding.left + chartW, y);
      ctx.stroke();
      const rounded = Math.abs(val) < yStep / 1000 ? 0 : val;
      ctx.fillStyle = '#6b7280';
      ctx.textAlign = 'right';
      ctx.fillText(`${rounded > 0 ? '+' : ''}${rounded.toFixed(decimals)}%`, padding.left - 8, y + 3);
    }

    // 0 % baseline
    const zeroY = yOf(0);
    ctx.strokeStyle = '#374151';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding.left, zeroY);
    ctx.lineTo(padding.left + chartW, zeroY);
    ctx.stroke();

    // Date range
    const fmtDate = t => this.toLocalDateLabel(t);
    ctx.fillStyle = '#9ca3af';
    ctx.textAlign = 'left';
    ctx.fillText(fmtDate(tMin), padding.left, rc.height - 8);
    ctx.textAlign = 'right';
    ctx.fillText(fmtDate(tMax), padding.left + chartW, rc.height - 8);

    // Lines: dimmed ones first, the highlighted one on top.
    const hl = this.returnChartHighlight;
    const ordered = [...rc.series].sort((a, b) => (a.key === hl) - (b.key === hl));
    ordered.forEach(s => {
      const active = !hl || s.key === hl;
      ctx.save();
      ctx.globalAlpha = active ? 1 : 0.55;
      ctx.strokeStyle = active ? s.color : this.DIMMED_LINE_COLOR;
      ctx.lineWidth = s.key === hl ? 3 : (s.dashed ? 1.5 : 2);
      ctx.setLineDash(s.dashed ? [6, 4] : []);
      ctx.lineJoin = 'round';
      ctx.beginPath();
      s.coords.forEach((c, idx) => (idx === 0 ? ctx.moveTo(c.x, c.y) : ctx.lineTo(c.x, c.y)));
      ctx.stroke();
      ctx.restore();

      const end = s.coords[s.coords.length - 1];
      if (end && active) {
        ctx.fillStyle = s.color;
        ctx.beginPath();
        ctx.arc(end.x, end.y, s.key === hl ? 4 : 2.5, 0, Math.PI * 2);
        ctx.fill();
        if (s.key === hl) {
          ctx.textAlign = 'left';
          ctx.font = 'bold 11px -apple-system, sans-serif';
          ctx.fillText(this.formatPct(s.totalPct, 1), end.x + 7, end.y + 4);
          ctx.font = '10px -apple-system, sans-serif';
        }
      }
    });
  },

  toLocalDateLabel(t) {
    const d = new Date(t);
    const pad = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  },

  onReturnChartPointer(e) {
    const rc = this.returnChart;
    if (!rc) return;
    const rect = rc.canvas.getBoundingClientRect();
    const px = e.clientX - rect.left;
    const py = e.clientY - rect.top;
    const key = this.nearestSeriesKey(rc.series, px, py, 14);
    this.setReturnChartHighlight(key);
    this.updateReturnTooltip(key, px, py);
  },

  setReturnChartHighlight(key) {
    if (this.returnChartHighlight === key) return;
    this.returnChartHighlight = key;
    if (!this.returnChart) return;
    this.drawReturnChart();
    this.updateReturnLegendState();
    if (!key && this.returnChart.tooltip) this.returnChart.tooltip.style.display = 'none';
  },

  updateReturnTooltip(key, px, py) {
    const rc = this.returnChart;
    if (!rc || !rc.tooltip) return;
    const tip = rc.tooltip;
    const s = rc.series.find(item => item.key === key);
    if (!s) {
      tip.style.display = 'none';
      return;
    }
    const { padding, tMin, tMax, chartW } = rc.layout;
    // A few pixels of tolerance so hovering exactly on a vertex shows that
    // trade's value instead of the previous step (mouse coords are rounded).
    const snapPx = Math.max(padding.left, Math.min(px + 4, padding.left + chartW));
    const t = tMin + ((snapPx - padding.left) / chartW) * (tMax - tMin);
    const point = this.curvePointAt(s.points, t);
    const pctClass = v => (v > 0 ? 'color-green' : (v < 0 ? 'color-red' : 'color-muted'));
    const name = `${this.escapeHtml(s.label)}${s.currency ? ` (${this.escapeHtml(s.currency)})` : ''}`;
    const atLine = point
      ? `<div><span class="${pctClass(point.pct)}" style="font-weight:700;">${this.formatPct(point.pct)}</span> <span class="color-muted">· ${this.escapeHtml(String(point.time).substring(0, 16))}</span></div>`
      : '';
    let totalLine = `<div class="color-muted">Total: <span class="${pctClass(s.totalPct)}">${this.formatPct(s.totalPct)}</span></div>`;
    if (s.account) {
      const money = App.formatMoney(s.account.net_profit, s.account.currency, { showSign: true });
      totalLine = `<div class="color-muted">Total: <span class="${pctClass(s.totalPct)}">${this.formatPct(s.totalPct)}</span> · ${this.escapeHtml(money)} · ${s.account.trades} trades</div>`;
    }
    tip.innerHTML = `<div style="font-weight:700;color:${s.color};">${name}</div>${atLine}${totalLine}`;
    tip.style.display = 'block';
    const tipW = tip.offsetWidth || 180;
    const tipH = tip.offsetHeight || 60;
    const left = px + 14 + tipW > rc.width ? px - tipW - 14 : px + 14;
    tip.style.left = `${Math.max(0, left)}px`;
    tip.style.top = `${Math.max(0, Math.min(py - tipH / 2, rc.height - tipH))}px`;
  },

  renderReturnLegend() {
    const legend = document.getElementById('equityCurveLegend');
    const rc = this.returnChart;
    if (!legend || !rc) return;
    legend.innerHTML = '';
    legend.hidden = false;
    let lastPointerType = 'mouse';

    rc.series.forEach(s => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'equity-legend-item';
      item.dataset.key = s.key;
      const valueClass = s.totalPct > 0 ? 'color-green' : (s.totalPct < 0 ? 'color-red' : 'color-muted');
      const swatch = s.dashed
        ? '<span class="equity-legend-swatch is-dashed"></span>'
        : `<span class="equity-legend-swatch" style="background:${s.color};"></span>`;
      item.innerHTML = `${swatch}<span>${this.escapeHtml(s.label)}${s.currency ? ` <span class="color-muted">${this.escapeHtml(s.currency)}</span>` : ''}</span>`
        + `<span class="equity-legend-value ${valueClass}">${this.formatPct(s.totalPct, 1)}</span>`;
      item.addEventListener('pointerdown', e => { lastPointerType = e.pointerType || 'mouse'; });
      item.addEventListener('pointerenter', e => {
        if (e.pointerType === 'mouse') this.setReturnChartHighlight(s.key);
      });
      item.addEventListener('pointerleave', e => {
        if (e.pointerType === 'mouse') this.setReturnChartHighlight(null);
      });
      item.addEventListener('focus', () => this.setReturnChartHighlight(s.key));
      item.addEventListener('blur', () => this.setReturnChartHighlight(null));
      // Touch has no hover: a tap toggles the highlight.
      item.addEventListener('click', () => {
        if (lastPointerType !== 'mouse') {
          this.setReturnChartHighlight(this.returnChartHighlight === s.key ? null : s.key);
        }
      });
      legend.appendChild(item);
    });
    this.updateReturnLegendState();
  },

  updateReturnLegendState() {
    const hl = this.returnChartHighlight;
    document.querySelectorAll('#accountComparisonBody .account-compare-row').forEach(row => {
      const isActive = Boolean(hl) && row.dataset.key === hl;
      row.classList.toggle('is-active', isActive);
      row.classList.toggle('is-dimmed', Boolean(hl) && !isActive);
    });
    const legend = document.getElementById('equityCurveLegend');
    const rc = this.returnChart;
    if (!legend || !rc) return;
    legend.querySelectorAll('.equity-legend-item').forEach(item => {
      const s = rc.series.find(entry => entry.key === item.dataset.key);
      const isActive = Boolean(hl) && item.dataset.key === hl;
      item.classList.toggle('is-active', isActive);
      item.classList.toggle('is-dimmed', Boolean(hl) && !isActive);
      item.style.borderColor = isActive && s ? s.color : '';
    });
  },


  renderAccountComparison() {
    const card = document.getElementById('accountComparisonCard');
    const body = document.getElementById('accountComparisonBody');
    if (!card || !body) return;
    const ov = this.getOverview();
    body.innerHTML = '';
    card.hidden = !ov;
    if (!ov) return;

    const signClass = v => (v > 0.001 ? 'color-green' : (v < -0.001 ? 'color-red' : 'color-muted'));
    ov.accounts.forEach(row => {
      const key = `acc-${row.account_id}`;
      const color = this.ACCOUNT_LINE_COLORS[(row.color_index || 0) % this.ACCOUNT_LINE_COLORS.length];
      const hasTrades = row.total_trades > 0;
      const money = (value, opts = {}) => this.escapeHtml(App.formatMoney(value, row.currency, opts));
      const tr = document.createElement('tr');
      tr.className = 'account-compare-row';
      tr.dataset.key = key;
      tr.title = `Open ${row.name}`;
      tr.innerHTML = `
        <td>
          <span class="account-compare-name"><span class="account-compare-dot" style="background:${color};"></span>${this.escapeHtml(row.name)}</span>
          <span class="color-muted" style="font-size:11px;margin-left:6px;">${this.escapeHtml(row.currency)}${row.platform ? ` · ${this.escapeHtml(row.platform)}` : ''}</span>
        </td>
        <td>${money(row.initial_balance, { decimals: 0 })}</td>
        <td class="${signClass(row.net_profit)}">${hasTrades ? money(row.net_profit, { showSign: true }) : '—'}</td>
        <td class="${signClass(row.return_pct || 0)}" style="font-weight:700;">${hasTrades && row.return_pct !== null ? this.formatPct(row.return_pct) : '—'}</td>
        <td class="${signClass(row.open_pnl)}">${row.open_trades_count ? `${money(row.open_pnl, { showSign: true })} (${this.formatPct(row.floating_pct || 0)})` : '—'}</td>
        <td class="${hasTrades && row.max_drawdown_pct > 0 ? 'color-red' : 'color-muted'}">${hasTrades ? `-${(row.max_drawdown_pct || 0).toFixed(1)}%` : '—'}</td>
        <td>${row.total_trades}</td>
        <td>${hasTrades ? `${row.win_rate}%` : '—'}</td>
        <td class="${signClass(row.total_r)}">${hasTrades ? `${row.total_r > 0 ? '+' : ''}${row.total_r.toFixed(2)} R` : '—'}</td>
      `;
      // Hovering a row highlights the account's line in the return chart.
      const hasLine = () => Boolean(this.returnChart && this.returnChart.series.some(s => s.key === key));
      tr.addEventListener('pointerenter', e => {
        if (e.pointerType === 'mouse') this.setReturnChartHighlight(hasLine() ? key : null);
      });
      tr.addEventListener('pointerleave', e => {
        if (e.pointerType === 'mouse') this.setReturnChartHighlight(null);
      });
      tr.addEventListener('click', () => this.openAccount(row.account_id));
      body.appendChild(tr);
    });
    this.updateReturnLegendState();
  },

  /** Drill down from the overview into one account (same as the account dropdown). */
  openAccount(accountId) {
    const select = document.getElementById('globalAccountSelect');
    if (!select) return;
    select.value = String(accountId);
    select.dispatchEvent(new Event('change'));
  },


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
    const ov = this.getOverview();
    // Breakdown panels use the %-scaled insights in the overview.
    const panels = ov ? (ov.insights || {}) : insights;
    this.pctMode = Boolean(ov);
    this.renderHeader(data);
    this.renderMixedCurrencyNotice(data);
    if (ov) {
      this.setText('dashNetPnlLabel', 'Avg. return');
      this.renderOverviewKPIs(data.metrics || {}, ov);
    } else {
      this.setText('dashNetPnlLabel', 'Net P&L');
      this.renderKPIs(data.metrics || {}, cur);
    }
    this.renderEquitySection(cur);
    this.renderAccountComparison();
    this.renderScore(insights.journal_score);
    this.syncCalendarModeButtons();
    this.renderCalendar(this.getCalendarData(), cur);
    this.renderOpenPositions(insights.open_positions || [], cur);
    this.renderRecentTrades(insights.recent_trades || [], cur);
    this.renderDailyPnlBars(this.getCalendarData(), cur);
    this.renderRDistribution(insights.r_distribution || []);
    this.renderWeekdays(panels.by_weekday || [], cur);
    this.renderLongShort(panels.long_short || {}, cur);
    this.renderConsistency(panels, data.metrics || {}, cur);
    this.renderMonthly(panels.monthly || [], cur);
    this.renderSymbols(panels.top_symbols || [], panels.worst_symbols || [], cur);
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

  setText(id, text) {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
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
    // The multi-account overview shows % of each account, so nothing is summed.
    el.hidden = !(data && data.mixed_currencies) || Boolean(this.getOverview());
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
    let peak = -Infinity;
    this.equityInfo = new Map();
    pts.forEach(p => {
      let ts = Math.floor(Date.parse(`${String(p.time).replace(' ', 'T').substring(0, 16)}:00Z`) / 1000);
      if (!isFinite(ts)) return;
      if (ts <= lastTs) ts = lastTs + 1;
      lastTs = ts;
      const value = isR ? Number(p.cumulative_r) || 0 : Number(p.cumulative_pnl) || 0;
      peak = Math.max(peak, value);
      const dd = Math.min(0, value - peak);
      line.push({ time: ts, value });
      this.equityInfo.set(ts, { point: p, value, dd });
    });
    this.equityFormat = { isR, cur };

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

      this.equityChart.subscribeCrosshairMove(param => {
        const info = param && param.time !== undefined ? this.equityInfo.get(param.time) : null;
        this.renderEquityReadout(info || null);
      });
    }

    this.equitySeries.applyOptions({ priceFormat: { type: 'custom', formatter, minMove: 0.01 } });
    this.equitySeries.setData(line);
    this.equityChart.timeScale().fitContent();

    this.renderEquityReadout(null);

    const sub = document.getElementById('equitySubtitle');
    if (sub) sub.textContent = isR
      ? 'Running total in R (profit ÷ initial risk) — one point per realized exit'
      : 'Running total of realized P&L — one point per realized exit';
  },

  // Readout above the chart: the hovered exit, or the latest state when not hovering.
  renderEquityReadout(info) {
    const el = document.getElementById('equityReadout');
    if (!el || !this.equityInfo || !this.equityInfo.size) return;
    const { isR, cur } = this.equityFormat || {};
    const fmt = v => (isR ? this.formatR(v) : this.signed(v, cur));
    const latest = !info;
    if (latest) info = [...this.equityInfo.values()].pop();
    const p = info.point || {};
    const when = String(p.time || '').replace('T', ' ').substring(0, 16);
    const change = isR ? Number(p.r_multiple) || 0 : Number(p.trade_pnl) || 0;
    const exit = p.symbol === 'START'
      ? '<span>Start of period</span>'
      : `<span><span class="readout-label">${p.partial ? 'Partial exit' : 'Exit'}</span><b>${this.esc(p.symbol || '')}</b>
         <span class="${this.pnlClass(change)}">${this.esc(fmt(change))}</span></span>`;
    el.innerHTML = `
      <span><span class="readout-label">${latest ? 'Latest' : 'At'}</span><b>${this.esc(when)}</b></span>
      ${exit}
      <span><span class="readout-label">Total</span><b class="${this.pnlClass(info.value)}">${this.esc(fmt(info.value))}</b></span>
      <span><span class="readout-label">Drawdown</span><b class="${info.dd < -0.001 ? 'color-red' : 'color-muted'}">${info.dd < -0.001 ? this.esc(fmt(info.dd)) : 'none — at best total'}</b></span>`;
  },

  destroyEquityChart() {
    if (this.equityChart) {
      try { this.equityChart.remove(); } catch (e) { /* already detached */ }
    }
    this.equityChart = null;
    this.equitySeries = null;
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
      this.syncCalendarModeButtons();
      this.renderCalendar(this.getCalendarData(), this.currentCurrency);
    }
  },

  // Short form for narrow calendar cells: +1.2k, -350, +2.4R, +0.8%
  compactValue(value, cur) {
    const v = Number(value) || 0;
    const sign = v > 0 ? '+' : (v < 0 ? '-' : '');
    const abs = Math.abs(v);
    const mode = this.effectiveCalendarMode();
    if (mode === 'r') return `${sign}${abs.toFixed(1)}R`;
    if (mode === 'pct') return `${sign}${abs.toFixed(1)}%`;
    const sym = App.getCurrencySymbol(cur).trim();
    return abs >= 1000 ? `${sign}${sym}${(abs / 1000).toFixed(1)}k` : `${sign}${sym}${Math.round(abs)}`;
  },

  formatCalendarValue(pnl, r, pct, cur) {
    const mode = this.effectiveCalendarMode();
    if (mode === 'r') return { text: this.formatR(r), value: r };
    if (mode === 'pct') return { text: `${pct > 0 ? '+' : ''}${pct.toFixed(2)}%`, value: pct };
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
    // Overview days carry no currency amount; colour and scale them by return.
    const isOverview = Boolean(this.getOverview());
    const dayResult = d => Number((isOverview ? d.pct_return : d.net_profit) || 0);
    const maxAbs = Math.max(isOverview ? 0.01 : 1, ...monthKeys.map(k => Math.abs(dayResult(calendarData[k] || {}))));

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
        const result = dayResult(dayData);
        if (result > (isOverview ? 0.001 : 0.01)) cls += ' profit';
        else if (result < (isOverview ? -0.001 : -0.01)) cls += ' loss';
        card.style.setProperty('--intensity', (Math.abs(result) / maxAbs).toFixed(2));
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
        // Monday..Sunday of this calendar row (may reach into the neighbouring months)
        const monday = new Date(year, month, 1 - lead + 7 * w);
        const sunday = new Date(year, month, 1 - lead + 7 * w + 6);
        const ymd = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
        const range = `${monday.getDate()}–${sunday.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })}`;
        const card = document.createElement('div');
        card.className = `week-card${wk.trades ? ' has-trades' : ''}`;
        card.innerHTML = `
          <span class="week-label">WEEK TOTAL<br><span class="week-range">${this.esc(range)}</span></span>
          <div>
            <div class="week-pnl ${wk.trades ? this.pnlClass(shown.value) : 'color-muted'}">${wk.trades ? this.esc(shown.text) : '–'}</div>
            <div class="week-sub">${wk.days} day${wk.days === 1 ? '' : 's'} · ${wk.trades} tr</div>
          </div>`;
        if (wk.trades) {
          card.title = `Week ${range}: open all trades realized in this week`;
          card.addEventListener('click', () => App.navigateToTradesWithRange(ymd(monday), ymd(sunday)));
        }
        weeks.appendChild(card);
      }
    }

    const sumPnlBox = document.getElementById('calSummaryPnlBox');
    if (sumPnlBox) sumPnlBox.hidden = isOverview;
    this.setText('calSummaryPctLabel', isOverview ? 'Return (Ø)' : 'Return');
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
    this.renderCalendar(this.getCalendarData(), this.currentCurrency);
  },

  calendarNextMonth() {
    this.currentCalendarDate.setDate(1);
    this.currentCalendarDate.setMonth(this.currentCalendarDate.getMonth() + 1);
    this.renderCalendar(this.getCalendarData(), this.currentCurrency);
  },

  calendarToday() {
    this.currentCalendarDate = new Date();
    this.renderCalendar(this.getCalendarData(), this.currentCurrency);
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
        <div class="sym">${this.esc(t.symbol)}${t.legs > 1
          ? ` <span class="badge badge-grouped" title="Merged from ${Number(t.legs)} orders, like in the trade log">${Number(t.legs)} TPs grouped</span>`
          : ''}</div>
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
      // No total across currencies in the overview; each row keeps its own currency.
      badge.textContent = !list.length ? 'None'
        : (this.getOverview() ? `${list.length} open` : `${list.length} · ${this.signed(total, cur)}`);
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
    const isOverview = Boolean(this.getOverview());
    this.setText('dailyPnlTitle', isOverview ? 'Daily return (Ø %)' : 'Daily P&L');
    if (sub) sub.textContent = dates.length
      ? `Last ${dates.length} trading day${dates.length === 1 ? '' : 's'}${isOverview ? ' · equal-weighted across accounts' : ''}`
      : 'No trading days yet';
    Charts.bars(container, dates.map(d => {
      const day = calendarData[d];
      const value = Number((isOverview ? day.pct_return : day.net_profit) || 0);
      const shown = isOverview ? this.formatPct(value) : this.signed(value, cur);
      return {
        label: d,
        short: this.shortDate(d),
        value,
        tip: `<strong>${this.esc(d)}</strong><br>${this.esc(shown)} · ${day.trades_count} trade(s)`,
      };
    }), {
      height: 220,
      format: v => (isOverview ? this.formatPct(v, 1) : this.money(v, cur, { decimals: 0 })),
      emptyText: 'No daily results yet.',
    });
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
      tip: `<strong>${this.esc(d.day)}</strong><br>${this.esc(this.amountSigned(d.net_profit, cur))}<br>${d.trades} trades · ${d.win_rate}% win rate`,
    })), { height: 190, format: v => this.amount(v, cur, { decimals: 0 }) });
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
      <div class="compare-pnl ${this.pnlClass(s.net_profit)}">${this.esc(this.amountSigned(s.net_profit || 0, cur))}</div>
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
      item('Avg daily P&L', this.amountSigned(ds.avg_daily_pnl || 0, cur), '', this.pnlClass(ds.avg_daily_pnl)),
      item('Best day', ds.best_day ? this.amountSigned(ds.best_day.net_profit, cur) : '–', ds.best_day ? this.shortDate(ds.best_day.date) : '', 'color-green'),
      item('Worst day', ds.worst_day ? this.amountSigned(ds.worst_day.net_profit, cur) : '–', ds.worst_day ? this.shortDate(ds.worst_day.date) : '', ds.worst_day && ds.worst_day.net_profit < 0 ? 'color-red' : ''),
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
        tip: `<strong>${this.esc(label)}</strong><br>${this.esc(this.amountSigned(m.net_profit, cur))} · ${this.esc(this.formatR(m.total_r, 1))}<br>${m.trades} trades · ${m.win_rate}% win rate`,
      };
    }), { height: 210, format: v => this.amount(v, cur, { decimals: 0 }) });
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
    })), { format: v => this.amountSigned(v, cur), emptyText: 'No closed trades yet.' });
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
