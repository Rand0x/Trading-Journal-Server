/**
 * Dashboard & TradeZella Calendar Heatmap Module
 * Zero-dependency, lightweight rendering optimized for low-resource environments.
 */

const Dashboard = {
  currentCalendarDate: new Date(),
  dashboardData: null,

  async load() {
    try {
      const params = App.getFilterParams();
      this.dashboardData = await API.getDashboard(params);
      this.renderKPIs(this.dashboardData.metrics);
      this.renderCalendar(this.dashboardData.calendar);
      this.renderEquityCurve(this.dashboardData.equity_curve);
      this.renderDailyPnlBars(this.dashboardData.calendar);
    } catch (err) {
      console.error('Failed to load dashboard:', err);
      App.showToast(`Error loading dashboard: ${err.message}`, 'error');
    }
  },

  renderKPIs(m) {
    const pnl = m.net_profit || 0;
    const pnlEl = document.getElementById('dashNetPnl');
    pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toLocaleString('en-US', { minimumFractionDigits: 2 })}`;
    pnlEl.className = `metric-value ${pnl >= 0 ? 'color-green' : 'color-red'}`;

    document.getElementById('dashWinRate').textContent = `${m.win_rate || 0}%`;
    document.getElementById('dashWinLossCount').textContent = `${m.winning_trades || 0}W - ${m.losing_trades || 0}L (${m.breakeven_trades || 0} BE)`;

    const pf = m.profit_factor || 0;
    const pfEl = document.getElementById('dashProfitFactor');
    pfEl.textContent = pf > 100 ? '∞' : pf.toFixed(2);
    pfEl.className = `metric-value ${pf >= 1.5 ? 'color-green' : (pf >= 1.0 ? 'color-blue' : 'color-red')}`;

    document.getElementById('dashTotalTrades').textContent = m.total_trades || 0;
    document.getElementById('dashAvgWin').textContent = `+$${(m.avg_win || 0).toFixed(2)}`;
    document.getElementById('dashAvgLoss').textContent = `-$${(m.avg_loss || 0).toFixed(2)}`;
    document.getElementById('dashWinLossRatio').textContent = `${(m.win_loss_ratio || 0).toFixed(2)}:1`;

    document.getElementById('dashExpectancy').textContent = `$${(m.expectancy || 0).toFixed(2)}`;
    document.getElementById('dashSharpe').textContent = (m.sharpe_ratio || 0).toFixed(2);
    document.getElementById('dashDrawdown').textContent = `-$${(m.max_drawdown_amount || 0).toFixed(2)} (${(m.max_drawdown_pct || 0).toFixed(1)}%)`;
    document.getElementById('dashStreaks').textContent = `W: ${m.max_win_streak || 0} / L: ${m.max_loss_streak || 0}`;
  },

  renderCalendar(calendarData = {}) {
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

    // Fill current month days
    for (let day = 1; day <= daysInMonth; day++) {
      const dateKey = `${year}-${String(month + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
      const dayData = calendarData[dateKey];

      const card = document.createElement('div');
      let statusClass = '';
      let pnlText = '';
      let tradeCountBadge = '';

      if (dayData && dayData.trades_count > 0) {
        const pnl = dayData.net_profit;
        if (pnl > 0.01) {
          statusClass = 'profit';
          pnlText = `<div class="day-pnl color-green">+$${pnl.toFixed(2)}</div>`;
        } else if (pnl < -0.01) {
          statusClass = 'loss';
          pnlText = `<div class="day-pnl color-red">-$${Math.abs(pnl).toFixed(2)}</div>`;
        } else {
          pnlText = `<div class="day-pnl color-muted">$0.00</div>`;
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
  },

  calendarPrevMonth() {
    this.currentCalendarDate.setMonth(this.currentCalendarDate.getMonth() - 1);
    this.renderCalendar(this.dashboardData ? this.dashboardData.calendar : {});
  },

  calendarNextMonth() {
    this.currentCalendarDate.setMonth(this.currentCalendarDate.getMonth() + 1);
    this.renderCalendar(this.dashboardData ? this.dashboardData.calendar : {});
  },

  calendarToday() {
    this.currentCalendarDate = new Date();
    this.renderCalendar(this.dashboardData ? this.dashboardData.calendar : {});
  },

  renderEquityCurve(points = []) {
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
      ctx.fillText(`$${Math.round(val).toLocaleString()}`, padding.left - 8, y + 3);
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
