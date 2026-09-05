/**
 * Weekly Review Module
 * Weekend reflection on trade discipline, performance, emotions, and missed setups.
 */
const Review = {
  weekOffset: 0,
  currentCurrency: 'USD',

  async load() {
    try {
      const params = App.getFilterParams();
      const query = {
        week_offset: this.weekOffset
      };
      if (params.account_id) {
        query.account_id = params.account_id;
      }

      const data = await API.getWeeklyReview(query);
      this.currentCurrency = App.getActiveCurrency();
      this.renderReview(data);
    } catch (err) {
      console.error('Failed to load weekly review:', err);
      App.showToast(`Weekly review error: ${err.message}`, 'error');
    }
  },

  prevWeek() {
    this.weekOffset -= 1;
    this.load();
  },

  nextWeek() {
    this.weekOffset += 1;
    this.load();
  },

  currentWeek() {
    this.weekOffset = 0;
    this.load();
  },

  renderReview(data) {
    const cur = this.currentCurrency || 'USD';

    // Week label
    const weekLabelEl = document.getElementById('reviewWeekLabel');
    if (weekLabelEl) {
      const offsetDesc = this.weekOffset === 0 ? ' (Current Week)' : (this.weekOffset === -1 ? ' (Previous Week)' : ` (CW offset: ${this.weekOffset > 0 ? '+' : ''}${this.weekOffset})`);
      weekLabelEl.textContent = (data.week_label || 'CW') + offsetDesc;
    }

    // Weekly Summary Cards
    const pnlEl = document.getElementById('revNetPnl');
    if (pnlEl) {
      pnlEl.textContent = App.formatMoney(data.net_profit || 0, cur, { showSign: true });
      pnlEl.className = `metric-value ${(data.net_profit || 0) >= 0 ? 'color-green' : 'color-red'}`;
    }

    const rEl = document.getElementById('revTotalR');
    if (rEl) {
      const totalR = data.total_r || 0;
      rEl.textContent = `${totalR >= 0 ? '+' : ''}${totalR.toFixed(2)} R`;
      rEl.style.color = totalR >= 0 ? '#10b981' : '#ef4444';
    }

    const wrEl = document.getElementById('revWinRate');
    if (wrEl) {
      wrEl.textContent = `${data.win_rate || 0}%`;
    }

    const winLossEl = document.getElementById('revWinLossCount');
    if (winLossEl) {
      winLossEl.textContent = `${data.wins_count || 0}W - ${data.losses_count || 0}L (${data.be_count || 0} BE)`;
    }

    const totalTradesEl = document.getElementById('revTotalTrades');
    if (totalTradesEl) {
      totalTradesEl.textContent = `${data.trades_count || 0}`;
    }

    const missingREl = document.getElementById('revMissingR');
    if (missingREl) {
      missingREl.textContent = `${data.missing_r_count || 0} without R-Multiple`;
    }

    const streaksEl = document.getElementById('revStreaks');
    if (streaksEl) {
      streaksEl.textContent = `W: ${data.max_win_streak || 0} / L: ${data.max_loss_streak || 0}`;
    }

    const lossEmoEl = document.getElementById('revLossEmotion');
    if (lossEmoEl) {
      lossEmoEl.textContent = data.top_loss_emotion || 'None';
      lossEmoEl.className = `metric-value ${data.top_loss_emotion ? 'color-red' : 'color-gray'}`;
    }

    const topPbEl = document.getElementById('revTopPlaybook');
    if (topPbEl) {
      topPbEl.textContent = data.top_playbook || 'None';
    }

    // Best & Worst Trade Cards
    this.renderTradeCard(
      'revBestBadge',
      'revBestTradeContent',
      data.best_trade,
      cur,
      'WIN',
      'No closed winners this week.'
    );

    this.renderTradeCard(
      'revWorstBadge',
      'revWorstTradeContent',
      data.worst_trade,
      cur,
      'LOSS',
      'No closed losses this week.'
    );

    // Missed Trades Table
    this.renderMissedTrades(data.missed_trades || []);
  },

  renderTradeCard(badgeId, contentId, trade, cur, type, emptyMsg) {
    const badgeEl = document.getElementById(badgeId);
    const contentEl = document.getElementById(contentId);
    if (!badgeEl || !contentEl) return;

    if (!trade) {
      badgeEl.textContent = '';
      badgeEl.className = 'badge';
      contentEl.innerHTML = `<div style="color:#9ca3af;font-size:13px;padding:10px 0;">${emptyMsg}</div>`;
      return;
    }

    const rText = trade.r_multiple != null ? `${Number(trade.r_multiple) >= 0 ? '+' : ''}${Number(trade.r_multiple).toFixed(2)} R` : '';
    const pnlText = App.formatMoney(trade.net_profit, cur, { showSign: true });
    badgeEl.textContent = rText ? `${pnlText} (${rText})` : pnlText;
    badgeEl.className = `badge badge-${type.toLowerCase()}`;

    const setupName = trade.setup_name || (trade.setup_id ? `Setup #${trade.setup_id}` : 'No Setup');
    const mistakeTag = trade.mistake_name ? `<span class="badge badge-loss" style="font-size:11px;">⚠️ ${trade.mistake_name}</span>` : '';
    const dateStr = (trade.close_time || trade.open_time || '').substring(0, 16).replace('T', ' ');

    let emotionHtml = '';
    if (trade.emotion_pre) {
      emotionHtml += `<span class="chip-btn" style="background:#1e293b;color:#a5b4fc;font-size:11px;padding:2px 8px;cursor:default;">Pre: ${trade.emotion_pre}</span> `;
    }
    if (trade.emotion_during) {
      emotionHtml += `<span class="chip-btn" style="background:#1e293b;color:#93c5fd;font-size:11px;padding:2px 8px;cursor:default;">In: ${trade.emotion_during}</span>`;
    }

    const notesSnippet = trade.key_learnings || trade.post_trade_notes || trade.notes || '';

    contentEl.innerHTML = `
      <div style="display:flex;flex-direction:column;gap:10px;">
        <div style="display:flex;justify-content:space-between;align-items:center;">
          <div style="display:flex;align-items:center;gap:8px;">
            <span style="font-weight:700;font-size:16px;color:#fff;">${trade.symbol}</span>
            <span class="badge badge-${(trade.direction || 'BUY').toLowerCase()}">${trade.direction}</span>
            <span style="font-size:12px;color:#9ca3af;">${trade.volume} Lots</span>
          </div>
          <span style="font-size:12px;color:#9ca3af;">${dateStr}</span>
        </div>

        <div style="display:flex;align-items:center;gap:12px;font-size:12px;color:#d1d5db;background:#0d131f;padding:8px 12px;border-radius:6px;">
          <span>Entry: <strong>${trade.open_price}</strong></span>
          <span>Exit: <strong>${trade.close_price || '-'}</strong></span>
          ${trade.stop_loss ? `<span>SL: <strong style="color:#ef4444;">${trade.stop_loss}</strong></span>` : ''}
          ${trade.take_profit ? `<span>TP: <strong style="color:#10b981;">${trade.take_profit}</strong></span>` : ''}
        </div>

        <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
          <span class="badge" style="background:#1e293b;color:#60a5fa;font-size:11px;">🎯 ${setupName}</span>
          ${mistakeTag}
          ${emotionHtml}
        </div>

        ${notesSnippet ? `
          <div style="font-size:12px;color:#9ca3af;font-style:italic;background:#111827;padding:8px;border-radius:4px;border-left:3px solid ${type === 'WIN' ? '#10b981' : '#ef4444'};">
            "${notesSnippet.length > 140 ? notesSnippet.substring(0, 140) + '...' : notesSnippet}"
          </div>
        ` : ''}

        <div style="display:flex;justify-content:flex-end;margin-top:4px;">
          <button class="btn btn-secondary btn-sm" onclick="TradeDetail.open(${trade.id})">
            🔍 Trade Details & Chart Replay
          </button>
        </div>
      </div>
    `;
  },

  renderMissedTrades(missedTrades = []) {
    const badgeEl = document.getElementById('revMissedCountBadge');
    if (badgeEl) {
      badgeEl.textContent = `${missedTrades.length} Missed`;
    }

    const tbody = document.getElementById('revMissedTableBody');
    if (!tbody) return;
    tbody.innerHTML = '';

    if (missedTrades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;color:#6b7280;padding:20px;">No missed trades this week. Flawless execution!</td></tr>';
      return;
    }

    missedTrades.forEach(t => {
      const tr = document.createElement('tr');
      const dateStr = (t.open_time || '').substring(0, 16).replace('T', ' ');
      const rVal = t.r_multiple != null ? `${Number(t.r_multiple) >= 0 ? '+' : ''}${Number(t.r_multiple).toFixed(2)} R` : '-';
      const reason = t.notes || t.pre_trade_notes || t.key_learnings || '-';

      tr.innerHTML = `
        <td style="color:#9ca3af;font-size:12px;">${dateStr}</td>
        <td style="font-weight:700;color:#60a5fa;">${t.symbol}</td>
        <td><span class="badge badge-${(t.direction || 'BUY').toLowerCase()}">${t.direction}</span></td>
        <td>${t.setup_name || (t.setup_id ? `Setup #${t.setup_id}` : '-')}</td>
        <td style="font-weight:700;color:#f59e0b;">${rVal}</td>
        <td style="font-size:12px;color:#d1d5db;max-width:280px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;" title="${reason}">
          ${reason}
        </td>
      `;
      tr.style.cursor = 'pointer';
      tr.title = 'Click to edit';
      tr.onclick = () => Trades.openEditModal(t.id);
      tbody.appendChild(tr);
    });
  }
};
