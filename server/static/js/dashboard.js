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
      this.renderEquityCurve(this.dashboardData.equity_curve, cur);
      this.renderDailyPnlBars(this.dashboardData.calendar, cur);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      App.showToast(`Error loading dashboard: ${err.message}`, 'error');
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
    const pnl = m.net_profit || 0;
    const pnlEl = document.getElementById('dashNetPnl');
    pnlEl.textContent = App.formatMoney(pnl, cur, { showSign: true });
    pnlEl.className = `metric-value ${pnl >= 0 ? 'color-green' : 'color-red'}`;

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
    this.currentCalendarDate.setMonth(this.currentCalendarDate.getMonth() - 1);
    this.renderCalendar(this.dashboardData ? this.dashboardData.calendar : {}, this.currentCurrency);
  },

  calendarNextMonth() {
    this.currentCalendarDate.setMonth(this.currentCalendarDate.getMonth() + 1);
    this.renderCalendar(this.dashboardData ? this.dashboardData.calendar : {}, this.currentCurrency);
  },

  calendarToday() {
    this.currentCalendarDate = new Date();
    this.renderCalendar(this.dashboardData ? this.dashboardData.calendar : {}, this.currentCurrency);
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
