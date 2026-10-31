/**
 * Dashboard & TradeZella Calendar Heatmap Module
 * Zero-dependency, lightweight rendering optimized for low-resource environments.
 */

const Dashboard = {
  currentCalendarDate: new Date(),
  dashboardData: null,
  calendarMode: 'currency', // 'currency', 'r', 'pct'

  async load() {
    try {
      const params = App.getFilterParams();
      this.dashboardData = await API.getDashboard(params);
      const cur = this.dashboardData.currency || App.getActiveCurrency();
      this.currentCurrency = cur;
      this.renderKPIs(this.dashboardData.metrics, cur);
      this.renderCalendar(this.dashboardData.calendar, cur);
      this.renderEquitySection(cur);
      this.renderDailyPnlBars(this.dashboardData.calendar, cur);
      this.checkAutoRefresh();
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      App.showToast(`Error loading dashboard: ${err.message}`, 'error');
    }
  },

  autoRefreshTimer: null,

  checkAutoRefresh() {
    this.stopAutoRefresh();
    const openCount = this.dashboardData ? (this.dashboardData.open_trades_count || (this.dashboardData.metrics && this.dashboardData.metrics.open_trades_count) || 0) : 0;
    if (openCount <= 0) return;

    this.autoRefreshTimer = setInterval(async () => {
      if (App.currentView !== 'dashboard') {
        this.stopAutoRefresh();
        return;
      }
      try {
        const params = App.getFilterParams();
        this.dashboardData = await API.getDashboard(params);
        const cur = this.dashboardData.currency || App.getActiveCurrency();
        this.currentCurrency = cur;
        this.renderKPIs(this.dashboardData.metrics, cur);
        this.renderCalendar(this.dashboardData.calendar, cur);
        this.renderEquitySection(cur);
        this.renderDailyPnlBars(this.dashboardData.calendar, cur);

        const stillOpen = this.dashboardData.open_trades_count || (this.dashboardData.metrics && this.dashboardData.metrics.open_trades_count) || 0;
        if (stillOpen <= 0) {
          this.stopAutoRefresh();
        }
      } catch (err) {
        console.error('Dashboard auto-refresh error:', err);
      }
    }, 3000);
  },

  stopAutoRefresh() {
    if (this.autoRefreshTimer) {
      clearInterval(this.autoRefreshTimer);
      this.autoRefreshTimer = null;
    }
  },

  setCalendarMode(mode) {
    this.calendarMode = mode;
    ['Currency', 'R', 'Pct'].forEach(m => {
      const btn = document.getElementById(`calMode${m}`);
      if (btn) {
        if (m.toLowerCase() === mode.toLowerCase()) {
          btn.classList.remove('btn-secondary');
          btn.classList.add('btn-primary');
        } else {
          btn.classList.remove('btn-primary');
          btn.classList.add('btn-secondary');
        }
      }
    });
    if (this.dashboardData) {
      this.renderCalendar(this.dashboardData.calendar, this.currentCurrency);
    }
  },

  renderKPIs(m, currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const closedPnl = m.net_profit || 0;
    const openPnl = (m.open_pnl !== undefined) ? m.open_pnl : (this.dashboardData?.open_pnl || 0);
    const openCount = (m.open_trades_count !== undefined) ? m.open_trades_count : (this.dashboardData?.open_trades_count || 0);
    const totalPnl = (m.total_pnl !== undefined) ? m.total_pnl : (closedPnl + openPnl);

    const pnlEl = document.getElementById('dashNetPnl');
    const pnlSubEl = document.getElementById('dashNetPnlSub');
    if (openCount > 0) {
      pnlEl.textContent = App.formatMoney(totalPnl, cur, { showSign: true });
      pnlEl.className = `metric-value ${totalPnl >= 0 ? 'color-green' : 'color-red'}`;
      if (pnlSubEl) {
        const openPnlFormatted = App.formatMoney(openPnl, cur, { showSign: true });
        const openPnlClass = openPnl >= 0 ? 'color-green' : 'color-red';
        pnlSubEl.innerHTML = `Closed: ${App.formatMoney(closedPnl, cur, { showSign: true })} · Floating: <span class="${openPnlClass}" style="font-weight:700;">${openPnlFormatted} (${openCount})</span>`;
      }
    } else {
      pnlEl.textContent = App.formatMoney(closedPnl, cur, { showSign: true });
      pnlEl.className = `metric-value ${closedPnl >= 0 ? 'color-green' : 'color-red'}`;
      if (pnlSubEl) {
        pnlSubEl.textContent = 'Closed Trades Profit';
      }
    }

    // Open Positions Card
    const openPnlEl = document.getElementById('dashOpenPnl');
    const openTradesSubEl = document.getElementById('dashOpenTradesSub');
    if (openPnlEl) {
      openPnlEl.textContent = App.formatMoney(openPnl, cur, { showSign: true });
      openPnlEl.className = `metric-value ${openPnl > 0.001 ? 'color-green' : (openPnl < -0.001 ? 'color-red' : 'color-muted')}`;
    }
    if (openTradesSubEl) {
      openTradesSubEl.textContent = `${openCount} Active Trade${openCount === 1 ? '' : 's'}`;
    }

    document.getElementById('dashWinRate').textContent = `${m.win_rate || 0}%`;
    document.getElementById('dashWinLossCount').textContent = `${m.winning_trades || 0}W - ${m.losing_trades || 0}L (${m.breakeven_trades || 0} BE)`;

    const pf = m.profit_factor || 0;
    const pfEl = document.getElementById('dashProfitFactor');
    pfEl.textContent = pf > 100 ? '∞' : pf.toFixed(2);
    pfEl.className = `metric-value ${pf >= 1.5 ? 'color-green' : (pf >= 1.0 ? 'color-blue' : 'color-red')}`;

    document.getElementById('dashTotalTrades').textContent = m.total_trades || 0;
    document.getElementById('dashAvgWin').textContent = App.formatMoney(m.avg_win || 0, cur, { showSign: true });
    document.getElementById('dashAvgLoss').textContent = App.formatMoney(-(m.avg_loss || 0), cur);
    document.getElementById('dashWinLossRatio').textContent = `${(m.win_loss_ratio || 0).toFixed(2)}:1`;

    document.getElementById('dashExpectancy').textContent = App.formatMoney(m.expectancy || 0, cur);
    document.getElementById('dashSharpe').textContent = (m.sharpe_ratio || 0).toFixed(2);
    document.getElementById('dashDrawdown').textContent = `-${App.formatMoney(m.max_drawdown_amount || 0, cur)} (${(m.max_drawdown_pct || 0).toFixed(1)}%)`;
    document.getElementById('dashStreaks').textContent = `W: ${m.max_win_streak || 0} / L: ${m.max_loss_streak || 0}`;

    // Current Drawdown & Current Streak
    const curDdEl = document.getElementById('dashCurrentDrawdown');
    if (curDdEl) {
      const ddAmt = m.current_drawdown_amount || 0;
      const ddPct = m.current_drawdown_pct || 0;
      curDdEl.textContent = `-${App.formatMoney(ddAmt, cur)} (${ddPct.toFixed(1)}%)`;
    }
    const curDdrEl = document.getElementById('dashCurrentDrawdownR');
    if (curDdrEl) {
      const ddR = m.current_drawdown_r || 0;
      curDdrEl.textContent = `${ddR > 0 ? '-' : ''}${Math.abs(ddR).toFixed(2)} R from ATH`;
    }
    const curStreakEl = document.getElementById('dashCurrentStreak');
    if (curStreakEl) {
      const stType = m.current_streak_type || 'NONE';
      const stCount = m.current_streak_count || 0;
      if (stType === 'WIN') {
        curStreakEl.textContent = `🔥 ${stCount} Win${stCount > 1 ? 's' : ''}`;
        curStreakEl.className = 'metric-value color-green';
      } else if (stType === 'LOSS') {
        curStreakEl.textContent = `❄️ ${stCount} Loss${stCount > 1 ? 'es' : ''}`;
        curStreakEl.className = 'metric-value color-red';
      } else {
        curStreakEl.textContent = 'None';
        curStreakEl.className = 'metric-value';
      }
    }
  },

  renderCalendar(calendarData = {}, currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const grid = document.getElementById('calendarDaysGrid');
    if (!grid) return;
    grid.innerHTML = '';

    const year = this.currentCalendarDate.getFullYear();
    const month = this.currentCalendarDate.getMonth();

    const monthNames = [
      'January', 'February', 'March', 'April', 'May', 'June',
      'July', 'August', 'September', 'October', 'November', 'December'
    ];
    document.getElementById('calendarMonthLabel').textContent = `${monthNames[month]} ${year}`;

    // First day of month and total days
    const firstDayIndex = new Date(year, month, 1).getDay(); // 0 = Sunday
    const daysInMonth = new Date(year, month + 1, 0).getDate();
    const prevMonthDays = new Date(year, month, 0).getDate();

    // Fill leading empty/prev-month days
    for (let i = firstDayIndex - 1; i >= 0; i--) {
      const card = document.createElement('div');
      card.className = 'calendar-day-card other-month';
      card.innerHTML = `<span class="day-number">${prevMonthDays - i}</span>`;
      grid.appendChild(card);
    }

    let monthPnl = 0;
    let monthR = 0;
    let monthWins = 0;
    let monthLosses = 0;
    let monthBE = 0;
    let monthPct = 0;

    // Fill current month days
    for (let day = 1; day <= daysInMonth; day++) {
      const dateKey = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayData = calendarData[dateKey];

      const card = document.createElement('div');
      let statusClass = '';
      let pnlText = '';
      let tradeCountBadge = '';

      if (dayData && dayData.trades_count > 0) {
        const pnl = dayData.net_profit || 0;
        const rVal = dayData.r_multiple || 0;
        const pctVal = dayData.pct_return || 0;

        monthPnl += pnl;
        monthR += rVal;
        monthWins += dayData.wins !== undefined ? dayData.wins : (dayData.winning_trades || 0);
        monthLosses += dayData.losses !== undefined ? dayData.losses : (dayData.losing_trades || 0);
        monthBE += dayData.breakevens !== undefined ? dayData.breakevens : (dayData.breakeven_trades || 0);
        monthPct += pctVal;

        if (pnl > 0.01) {
          statusClass = 'profit';
        } else if (pnl < -0.01) {
          statusClass = 'loss';
        }

        if (this.calendarMode === 'r') {
          const rSign = rVal > 0 ? '+' : '';
          pnlText = `<div class="day-pnl ${rVal >= 0 ? 'color-green' : 'color-red'}">${rSign}${rVal.toFixed(2)} R</div>`;
        } else if (this.calendarMode === 'pct') {
          const pctSign = pctVal > 0 ? '+' : '';
          pnlText = `<div class="day-pnl ${pctVal >= 0 ? 'color-green' : 'color-red'}">${pctSign}${pctVal.toFixed(2)}%</div>`;
        } else {
          if (pnl > 0.01) {
            pnlText = `<div class="day-pnl color-green">${App.formatMoney(pnl, cur, { showSign: true })}</div>`;
          } else if (pnl < -0.01) {
            pnlText = `<div class="day-pnl color-red">${App.formatMoney(pnl, cur)}</div>`;
          } else {
            pnlText = `<div class="day-pnl color-muted">${App.formatMoney(0, cur)}</div>`;
          }
        }
        tradeCountBadge = `<span class="day-badge">${dayData.trades_count} tr</span>`;
      }

      card.className = `calendar-day-card ${statusClass}`;
      card.innerHTML = `
        <div class="day-header">
          <span class="day-number">${day}</span>
          ${tradeCountBadge}
        </div>
        ${pnlText}
      `;

      if (dayData && dayData.trades_count > 0) {
        card.title = `Click to filter trades on ${dateKey}`;
        card.addEventListener('click', () => {
          App.navigateToTradesWithDate(dateKey);
        });
      }

      grid.appendChild(card);
    }

    // Render Month Summary
    const sumPnlEl = document.getElementById('calSummaryPnl');
    if (sumPnlEl) {
      sumPnlEl.textContent = App.formatMoney(monthPnl, cur, { showSign: true });
      sumPnlEl.className = monthPnl >= 0 ? 'color-green' : 'color-red';
    }
    const sumREl = document.getElementById('calSummaryR');
    if (sumREl) {
      const sign = monthR > 0 ? '+' : '';
      sumREl.textContent = `${sign}${monthR.toFixed(2)} R`;
      sumREl.style.color = monthR >= 0 ? '#60a5fa' : '#ef4444';
    }
    const sumWblEl = document.getElementById('calSummaryWBL');
    if (sumWblEl) {
      sumWblEl.textContent = `${monthWins}W · ${monthBE}BE · ${monthLosses}L`;
    }
    const sumPctEl = document.getElementById('calSummaryPct');
    if (sumPctEl) {
      const pSign = monthPct > 0 ? '+' : '';
      sumPctEl.textContent = `${pSign}${monthPct.toFixed(2)}%`;
      sumPctEl.style.color = monthPct >= 0 ? '#10b981' : '#ef4444';
    }
  },

  calendarPrevMonth() {
    // Pin to the 1st first: on the 29th-31st setMonth() overflows into the
    // following month (Oct 31 - 1 month = "Sep 31" = Oct 1).
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

  /**
   * All-accounts overview with several accounts: one % line per account
   * (relative to its own starting balance) instead of summing amounts in
   * different currencies. A single selected account keeps the currency chart.
   */
  renderEquitySection(currency) {
    const data = this.dashboardData || {};
    const curves = data.account_curves;
    const isOverview = Boolean(curves && Array.isArray(curves.accounts) && curves.accounts.length > 0);
    const title = document.getElementById('equityCurveTitle');
    const subtitle = document.getElementById('equityCurveSubtitle');
    const legend = document.getElementById('equityCurveLegend');

    if (isOverview) {
      if (title) title.textContent = 'Account Returns';
      if (subtitle) subtitle.textContent = "% of each account's starting balance";
      this.renderAccountReturnCurves(curves);
      return;
    }

    this.returnChart = null;
    if (title) title.textContent = 'Cumulative Equity Curve';
    if (subtitle) subtitle.textContent = 'Account Balance Growth';
    if (legend) {
      legend.innerHTML = '';
      legend.style.display = 'none';
    }
    this.renderEquityCurve(data.equity_curve, currency);
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
    const container = document.getElementById('equityCurveCanvasContainer');
    if (!container) return;
    container.innerHTML = '';

    const series = curves.accounts.map((acc, idx) => ({
      key: `acc-${acc.account_id}`,
      label: acc.name,
      currency: acc.currency,
      color: this.ACCOUNT_LINE_COLORS[idx % this.ACCOUNT_LINE_COLORS.length],
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
    legend.style.display = 'flex';
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
    const legend = document.getElementById('equityCurveLegend');
    const rc = this.returnChart;
    if (!legend || !rc) return;
    const hl = this.returnChartHighlight;
    legend.querySelectorAll('.equity-legend-item').forEach(item => {
      const s = rc.series.find(entry => entry.key === item.dataset.key);
      const isActive = Boolean(hl) && item.dataset.key === hl;
      item.classList.toggle('is-active', isActive);
      item.classList.toggle('is-dimmed', Boolean(hl) && !isActive);
      item.style.borderColor = isActive && s ? s.color : '';
    });
  },

  renderEquityCurve(points = [], currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const sym = App.getCurrencySymbol(cur);
    const container = document.getElementById('equityCurveCanvasContainer');
    if (!container) return;
    container.innerHTML = '';

    if (!points || points.length === 0) {
      container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#6b7280;">No trade history available yet.</div>';
      return;
    }

    // High performance HTML5 Canvas chart
    const canvas = document.createElement('canvas');
    canvas.width = container.clientWidth || 450;
    canvas.height = 260;
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const padding = { top: 20, right: 30, bottom: 40, left: 60 };

    const balances = points.map(p => p.balance);
    const minBal = Math.min(...balances) * 0.99;
    const maxBal = Math.max(...balances) * 1.01;
    const balRange = (maxBal - minBal) || 1;

    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;

    // Draw background grid
    ctx.strokeStyle = '#1a2333';
    ctx.lineWidth = 1;
    for (let i = 0; i <= 4; i++) {
      const y = padding.top + (chartH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(padding.left, y);
      ctx.lineTo(width - padding.right, y);
      ctx.stroke();

      const val = maxBal - (balRange / 4) * i;
      ctx.fillStyle = '#6b7280';
      ctx.font = '10px -apple-system, sans-serif';
      ctx.textAlign = 'right';
      ctx.fillText(`${sym}${Math.round(val).toLocaleString()}`, padding.left - 8, y + 3);
    }

    // Plot line
    const coords = points.map((p, idx) => {
      const x = padding.left + (chartW / (points.length - 1 || 1)) * idx;
      const y = padding.top + chartH - ((p.balance - minBal) / balRange) * chartH;
      return { x, y };
    });

    // Gradient fill under equity curve
    const isProfitable = points[points.length - 1].balance >= points[0].balance;
    const strokeColor = isProfitable ? '#10b981' : '#ef4444';

    const grad = ctx.createLinearGradient(0, padding.top, 0, height - padding.bottom);
    grad.addColorStop(0, isProfitable ? 'rgba(16, 185, 129, 0.25)' : 'rgba(239, 68, 68, 0.25)');
    grad.addColorStop(1, 'rgba(16, 185, 129, 0.0)');

    ctx.beginPath();
    ctx.moveTo(coords[0].x, height - padding.bottom);
    coords.forEach(c => ctx.lineTo(c.x, c.y));
    ctx.lineTo(coords[coords.length - 1].x, height - padding.bottom);
    ctx.closePath();
    ctx.fillStyle = grad;
    ctx.fill();

    // Line stroke
    ctx.beginPath();
    coords.forEach((c, idx) => {
      if (idx === 0) ctx.moveTo(c.x, c.y);
      else ctx.lineTo(c.x, c.y);
    });
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 2.5;
    ctx.stroke();

    // Start and End labels
    ctx.fillStyle = '#9ca3af';
    ctx.textAlign = 'left';
    ctx.fillText(points[0].time.substring(5, 10), padding.left, height - 12);
    ctx.textAlign = 'right';
    ctx.fillText(points[points.length - 1].time.substring(5, 10), width - padding.right, height - 12);
  },

  renderDailyPnlBars(calendarData = {}) {
    const container = document.getElementById('dailyPnlBarContainer');
    if (!container) return;
    container.innerHTML = '';

    const dates = Object.keys(calendarData).sort();
    if (dates.length === 0) {
      container.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#6b7280;">No daily P&L data yet.</div>';
      return;
    }

    const canvas = document.createElement('canvas');
    canvas.width = container.clientWidth || 450;
    canvas.height = 260;
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const padding = { top: 20, right: 20, bottom: 40, left: 60 };

    const pnls = dates.map(d => calendarData[d].net_profit);
    const maxAbsPnl = Math.max(...pnls.map(Math.abs), 100);

    const chartW = width - padding.left - padding.right;
    const chartH = height - padding.top - padding.bottom;
    const zeroY = padding.top + chartH / 2;

    // Draw zero line
    ctx.strokeStyle = '#374151';
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(padding.left, zeroY);
    ctx.lineTo(width - padding.right, zeroY);
    ctx.stroke();

    // Y Axis labels
    ctx.fillStyle = '#6b7280';
    ctx.font = '10px -apple-system, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(`+$${Math.round(maxAbsPnl)}`, padding.left - 8, padding.top + 8);
    ctx.fillText(`$0`, padding.left - 8, zeroY + 3);
    ctx.fillText(`-$${Math.round(maxAbsPnl)}`, padding.left - 8, height - padding.bottom);

    // Bars
    const barWidth = Math.max(3, Math.min(22, (chartW / dates.length) - 4));
    const step = chartW / dates.length;

    dates.forEach((d, idx) => {
      const pnl = calendarData[d].net_profit;
      const x = padding.left + (idx * step) + (step - barWidth) / 2;
      const barHeight = (Math.abs(pnl) / maxAbsPnl) * (chartH / 2);

      if (pnl >= 0) {
        ctx.fillStyle = '#10b981';
        ctx.fillRect(x, zeroY - barHeight, barWidth, barHeight);
      } else {
        ctx.fillStyle = '#ef4444';
        ctx.fillRect(x, zeroY, barWidth, barHeight);
      }
    });
  }
};
