/**
 * Deep Quantitative Analytics Reports Module
 * High performance, zero AI, statistical analysis charts.
 */

const Analytics = {
  async load() {
    try {
      const params = App.getFilterParams();
      const data = await API.getAnalyticsOverview(params);
      const cur = data.currency || App.getActiveCurrency();
      this.currentCurrency = cur;
      this.renderDayOfWeek(data.by_day_of_week, cur);
      this.renderHourOfDay(data.by_hour, cur);
      this.renderSymbols(data.by_symbol, cur);
      this.renderSetups(data.by_setup, cur);
      this.renderMistakes(data.by_mistake, cur);
    } catch (err) {
      console.error('Failed to load analytics:', err);
      App.showToast(`Analytics error: ${err.message}`, 'error');
    }
  },

  renderDayOfWeek(days = [], currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const container = document.getElementById('analyticsDayOfWeekContainer');
    const tableBody = document.getElementById('analyticsDayOfWeekTableBody');
    if (!container || !tableBody) return;

    tableBody.innerHTML = '';
    days.forEach(d => {
      const tr = document.createElement('tr');
      const pnlClass = d.net_profit >= 0 ? 'color-green' : 'color-red';
      tr.innerHTML = `
        <td style="font-weight:600;color:#fff;">${d.day}</td>
        <td>${d.trades}</td>
        <td>${d.wins}</td>
        <td>${d.losses}</td>
        <td style="font-weight:700;color:#60a5fa;">${d.win_rate}%</td>
        <td style="font-weight:700;" class="${pnlClass}">${App.formatMoney(d.net_profit, cur, { showSign: true })}</td>
      `;
      tableBody.appendChild(tr);
    });

    // Render bar chart in canvas
    this.drawBarChart(container, days.map(d => ({ label: d.day.substring(0, 3), value: d.net_profit })), cur);
  },

  renderHourOfDay(hours = [], currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const container = document.getElementById('analyticsHourContainer');
    if (!container) return;

    // Filter to active trading hours or all 24h
    const items = hours.map(h => ({
      label: h.hour.substring(0, 2),
      value: h.net_profit
    }));
    this.drawBarChart(container, items, cur);
  },

  renderSymbols(symbols = [], currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const tbody = document.getElementById('analyticsSymbolsTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (symbols.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:20px;color:#6b7280;">No symbol performance data.</td></tr>';
      return;
    }

    symbols.forEach(s => {
      const tr = document.createElement('tr');
      const pnlClass = s.net_profit >= 0 ? 'color-green' : 'color-red';
      const pfDisplay = s.profit_factor > 100 ? '∞' : s.profit_factor.toFixed(2);
      tr.innerHTML = `
        <td style="font-weight:700;color:#60a5fa;">${s.symbol}</td>
        <td>${s.trades}</td>
        <td style="font-weight:700;color:#10b981;">${s.win_rate}%</td>
        <td style="font-weight:700;" class="${pnlClass}">${App.formatMoney(s.net_profit, cur, { showSign: true })}</td>
        <td>${pfDisplay}</td>
        <td>${s.volume} lots</td>
        <td class="${s.avg_trade >= 0 ? 'color-green' : 'color-red'}">${App.formatMoney(s.avg_trade, cur)}</td>
      `;
      tbody.appendChild(tr);
    });
  },

  renderSetups(setups = [], currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const tbody = document.getElementById('analyticsSetupsTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (setups.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:#6b7280;">No playbook setup data.</td></tr>';
      return;
    }

    setups.forEach(s => {
      const tr = document.createElement('tr');
      const pnlClass = s.net_profit >= 0 ? 'color-green' : 'color-red';
      const pfDisplay = s.profit_factor > 100 ? '∞' : s.profit_factor.toFixed(2);
      tr.innerHTML = `
        <td style="font-weight:600;color:#fff;">${s.setup_name}</td>
        <td>${s.trades}</td>
        <td style="font-weight:700;color:#10b981;">${s.win_rate}%</td>
        <td style="font-weight:700;" class="${pnlClass}">${App.formatMoney(s.net_profit, cur, { showSign: true })}</td>
        <td>${pfDisplay}</td>
      `;
      tbody.appendChild(tr);
    });
  },

  renderMistakes(mistakes = [], currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const tbody = document.getElementById('analyticsMistakesTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (mistakes.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:#6b7280;">No tagged mistakes recorded. Excellent discipline!</td></tr>';
      return;
    }

    mistakes.forEach(m => {
      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td style="font-weight:600;color:#f87171;">${m.mistake_name}</td>
        <td>${m.count}</td>
        <td style="font-weight:700;color:#ef4444;">-${App.formatMoney(m.total_loss, cur)}</td>
        <td style="color:#fca5a5;">-${App.formatMoney(m.worst_loss, cur)}</td>
        <td style="color:#fca5a5;">-${App.formatMoney(m.avg_loss, cur)}</td>
      `;
      tbody.appendChild(tr);
    });
  },

  drawBarChart(container, items = [], currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const sym = App.getCurrencySymbol(cur);
    container.innerHTML = '';
    if (items.length === 0) return;

    const canvas = document.createElement('canvas');
    canvas.width = container.clientWidth || 450;
    canvas.height = 240;
    container.appendChild(canvas);

    const ctx = canvas.getContext('2d');
    const width = canvas.width;
    const height = canvas.height;
    const padding = { top: 20, right: 20, bottom: 35, left: 55 };

    const values = items.map(i => i.value);
    const maxAbs = Math.max(...values.map(Math.abs), 50);

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

    // Axis labels
    ctx.fillStyle = '#6b7280';
    ctx.font = '10px -apple-system, sans-serif';
    ctx.textAlign = 'right';
    ctx.fillText(`+${sym}${Math.round(maxAbs)}`, padding.left - 6, padding.top + 8);
    ctx.fillText(`-${sym}${Math.round(maxAbs)}`, padding.left - 6, height - padding.bottom);

    const step = chartW / items.length;
    const barWidth = Math.max(3, Math.min(24, step - 4));

    items.forEach((item, idx) => {
      const x = padding.left + (idx * step) + (step - barWidth) / 2;
      const barH = (Math.abs(item.value) / maxAbs) * (chartH / 2);

      if (item.value >= 0) {
        ctx.fillStyle = '#10b981';
        ctx.fillRect(x, zeroY - barH, barWidth, barH);
      } else {
        ctx.fillStyle = '#ef4444';
        ctx.fillRect(x, zeroY, barWidth, barH);
      }

      // X labels
      ctx.fillStyle = '#9ca3af';
      ctx.textAlign = 'center';
      ctx.fillText(item.label, x + barWidth / 2, height - 10);
    });
  }
};
