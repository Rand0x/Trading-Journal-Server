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
      this.renderTakeProfitAnalysis(data.take_profit, cur);
      this.renderSignalCombinations(data.signal_combinations, cur);
      this.renderPsychologyPerformance(data.psychology, cur);
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

  renderTakeProfitAnalysis(tpData, currency) {
    const container = document.getElementById('analyticsTpCardsContainer');
    if (!container) return;
    container.innerHTML = '';

    if (!tpData || !tpData.levels || tpData.levels.length === 0) {
      container.innerHTML = '<div style="grid-column:1/-1;text-align:center;padding:24px;color:#6b7280;">No Take-Profit scale-out data available yet.</div>';
      return;
    }

    tpData.levels.forEach(lvl => {
      const card = document.createElement('div');
      card.className = 'tp-card';
      card.style.cssText = 'background:#0d131f;border:1px solid #1f2937;border-radius:8px;padding:16px;display:flex;flex-direction:column;justify-content:space-between;';
      card.innerHTML = `
        <div>
          <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
            <span style="font-weight:700;font-size:16px;color:#60a5fa;">${lvl.name}</span>
            <span class="badge" style="background:#1e293b;color:#9ca3af;font-size:11px;">Level ${lvl.level}</span>
          </div>
          <div style="margin-bottom:8px;">
            <div style="font-size:11px;color:#9ca3af;margin-bottom:2px;">Hit Rate (All Trades)</div>
            <div style="font-size:18px;font-weight:700;color:#10b981;">${lvl.pct_of_all}% <span style="font-size:12px;font-weight:400;color:#9ca3af;">(${lvl.reached_count} / ${tpData.total_closed})</span></div>
          </div>
          <div style="margin-bottom:8px;">
            <div style="font-size:11px;color:#9ca3af;margin-bottom:2px;">Hit Rate (Wins)</div>
            <div style="font-size:14px;font-weight:600;color:#fff;">${lvl.pct_of_wins}% <span style="font-size:11px;font-weight:400;color:#9ca3af;">(${lvl.reached_count} / ${tpData.total_wins})</span></div>
          </div>
        </div>
        <div style="border-top:1px solid #1a2233;padding-top:8px;margin-top:4px;">
          <div style="font-size:11px;color:#9ca3af;margin-bottom:2px;">Avg. R Contribution</div>
          <div style="font-size:15px;font-weight:700;color:#60a5fa;">${lvl.avg_r_contribution >= 0 ? '+' : ''}${lvl.avg_r_contribution.toFixed(2)} R</div>
        </div>
      `;
      container.appendChild(card);
    });

    // Exit distribution card
    if (tpData.exit_distribution && Object.keys(tpData.exit_distribution).length > 0) {
      const exitCard = document.createElement('div');
      exitCard.className = 'tp-card';
      exitCard.style.cssText = 'background:#0d131f;border:1px solid #1f2937;border-radius:8px;padding:16px;';
      const exitRows = Object.entries(tpData.exit_distribution).map(([name, cnt]) => {
        const pct = Math.round((cnt / (tpData.total_closed || 1)) * 100);
        return `
          <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;">
            <span style="color:#d1d5db;">${name}</span>
            <span style="font-weight:600;color:#60a5fa;">${cnt} <span style="color:#9ca3af;font-size:10px;">(${pct}%)</span></span>
          </div>
        `;
      }).join('');
      exitCard.innerHTML = `
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
          <span style="font-weight:700;font-size:14px;color:#e5e7eb;">Exit Distribution</span>
          <span class="badge" style="background:#1e293b;color:#9ca3af;font-size:11px;">${tpData.total_closed} Total</span>
        </div>
        <div style="display:flex;flex-direction:column;gap:6px;">
          ${exitRows}
        </div>
      `;
      container.appendChild(exitCard);
    }
  },

  renderSignalCombinations(signalsData, currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const tbody = document.getElementById('analyticsSignalsTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (!signalsData || (!signalsData.combinations?.length && !signalsData.solo?.length)) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:20px;color:#6b7280;">No signal or confluence data available (minimum 2 trades with signals required).</td></tr>';
      return;
    }

    if (!signalsData.combinations || signalsData.combinations.length === 0) {
      const soloList = (signalsData.solo || []).map(s => s.signal).join(', ');
      tbody.innerHTML = `<tr><td colspan="6" style="text-align:center;padding:20px;color:#6b7280;">No combinations with at least 2 trades recorded yet. Individual signals: ${soloList || 'None'}</td></tr>`;
      return;
    }

    signalsData.combinations.forEach(combo => {
      const tr = document.createElement('tr');
      const pnlClass = combo.net_profit >= 0 ? 'color-green' : 'color-red';
      const upliftClass = combo.uplift > 0 ? 'color-green' : (combo.uplift < 0 ? 'color-red' : '');
      const upliftPrefix = combo.uplift > 0 ? '+' : '';
      tr.innerHTML = `
        <td>
          <span style="display:inline-flex;gap:4px;align-items:center;flex-wrap:wrap;">
            <span class="chip-btn" style="background:#1e293b;color:#93c5fd;cursor:default;padding:2px 8px;font-size:11px;border-radius:4px;">${combo.signal_a}</span>
            <span style="color:#6b7280;">+</span>
            <span class="chip-btn" style="background:#1e293b;color:#93c5fd;cursor:default;padding:2px 8px;font-size:11px;border-radius:4px;">${combo.signal_b}</span>
          </span>
        </td>
        <td>${combo.count} <span style="font-size:11px;color:#9ca3af;">(${combo.wins}W)</span></td>
        <td style="font-weight:700;color:#10b981;">${combo.win_rate}%</td>
        <td style="font-weight:700;" class="${pnlClass}">${App.formatMoney(combo.net_profit, cur, { showSign: true })}</td>
        <td style="font-weight:600;color:#60a5fa;">${combo.avg_r >= 0 ? '+' : ''}${combo.avg_r.toFixed(2)} R</td>
        <td style="font-weight:700;" class="${upliftClass}">${upliftPrefix}${combo.uplift.toFixed(2)} R</td>
      `;
      tbody.appendChild(tr);
    });
  },

  renderPsychologyPerformance(psyData, currency) {
    const cur = currency || this.currentCurrency || App.getActiveCurrency();
    const renderTable = (tbodyId, list = []) => {
      const tbody = document.getElementById(tbodyId);
      if (!tbody) return;
      tbody.innerHTML = '';

      if (!list || list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="5" style="text-align:center;padding:20px;color:#6b7280;">No emotion data recorded.</td></tr>';
        return;
      }

      list.forEach(item => {
        const tr = document.createElement('tr');
        const pnlClass = item.net_profit >= 0 ? 'color-green' : 'color-red';
        const totalR = item.total_r != null ? item.total_r : 0;
        const avgR = item.avg_r != null ? item.avg_r : 0;
        tr.innerHTML = `
          <td style="font-weight:600;color:#fff;">
            <span class="chip-btn" style="background:#1e293b;color:#a5b4fc;cursor:default;padding:2px 8px;font-size:11px;border-radius:4px;">${item.emotion}</span>
          </td>
          <td>${item.count} <span style="font-size:11px;color:#9ca3af;">(${item.wins}W / ${item.losses}L)</span></td>
          <td style="font-weight:700;color:#10b981;">${item.win_rate}%</td>
          <td style="font-weight:700;" class="${pnlClass}">${App.formatMoney(item.net_profit, cur, { showSign: true })}</td>
          <td style="font-weight:600;color:#60a5fa;">${totalR >= 0 ? '+' : ''}${totalR.toFixed(2)} R <span style="font-size:11px;color:#9ca3af;">(Ø ${avgR >= 0 ? '+' : ''}${avgR.toFixed(2)} R)</span></td>
        `;
        tbody.appendChild(tr);
      });
    };

    renderTable('analyticsEmotionPreTableBody', psyData ? psyData.emotion_pre : []);
    renderTable('analyticsEmotionDuringTableBody', psyData ? psyData.emotion_during : []);
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
