/**
 * Trades Log Management Module
 * Comprehensive datagrid with sorting, filtering, searching, and modals.
 */

const Trades = {
  currentOffset: 0,
  limit: 25,
  totalTrades: 0,
  sortBy: 'open_time',
  sortOrder: 'desc',
  activeEditingId: null,
  expandedTradeId: null,
  expandedRow: null,

  async load(page = 0) {
    this.currentOffset = page * this.limit;
    const filterParams = App.getFilterParams();

    const params = {
      ...filterParams,
      limit: this.limit,
      offset: this.currentOffset,
      sort_by: this.sortBy,
      sort_order: this.sortOrder,
    };

    // Extra local filters
    const symbolVal = document.getElementById('tradeSymbolFilter')?.value;
    if (symbolVal) params.symbol = symbolVal;

    const dirVal = document.getElementById('tradeDirFilter')?.value;
    if (dirVal) params.direction = dirVal;

    const statusVal = document.getElementById('tradeStatusFilter')?.value;
    if (statusVal) params.status = statusVal;

    const setupVal = document.getElementById('tradeSetupFilter')?.value;
    if (setupVal) params.setup_id = setupVal;

    const mistakeVal = document.getElementById('tradeMistakeFilter')?.value;
    if (mistakeVal) params.mistake_id = mistakeVal;

    const searchVal = document.getElementById('tradeSearchInput')?.value;
    if (searchVal) params.search = searchVal;

    try {
      const data = await API.getTrades(params);
      this.totalTrades = data.total;
      this.renderTable(data.trades);
      this.renderPagination();
    } catch (err) {
      console.error('Failed to load trades:', err);
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  groupOpenTrades(trades = []) {
    if (!trades || !trades.length) return [];

    const result = [];
    const openGroups = new Map();

    for (const t of trades) {
      const isOpen = (t.status === 'OPEN' || t.status === 'PENDING') && !t.is_missed;
      if (!isOpen) {
        result.push(t);
        continue;
      }

      // Group key: account_id, symbol, direction, status, and open_price with 4-digit precision
      const price = parseFloat(t.open_price) || 0;
      const priceKey = price.toFixed(4);
      const groupKey = `${t.account_id || ''}_${(t.symbol || '').toUpperCase()}_${(t.direction || '').toUpperCase()}_${t.status}_${priceKey}`;

      if (!openGroups.has(groupKey)) {
        openGroups.set(groupKey, []);
      }
      openGroups.get(groupKey).push(t);
    }

    for (const group of openGroups.values()) {
      if (group.length === 1) {
        result.push(group[0]);
        continue;
      }

      // Multiple open orders with same entry and direction!
      group.sort((a, b) => (a.id || 0) - (b.id || 0));
      const primary = { ...group[0] };

      const tpsSet = new Set();
      const openP = parseFloat(primary.open_price) || 0;
      let totalVolume = 0;
      let totalNetProfit = 0;
      let totalGrossProfit = 0;
      let totalCommission = 0;
      let totalSwap = 0;
      const allIds = [];
      const allTickets = [];

      for (const leg of group) {
        allIds.push(leg.id);
        if (leg.ticket) allTickets.push(leg.ticket);
        totalVolume += parseFloat(leg.volume) || 0;
        totalNetProfit += parseFloat(leg.net_profit) || 0;
        totalGrossProfit += parseFloat(leg.gross_profit) || 0;
        totalCommission += parseFloat(leg.commission) || 0;
        totalSwap += parseFloat(leg.swap) || 0;

        if (leg.take_profit && parseFloat(leg.take_profit) > 0) {
          tpsSet.add(parseFloat(leg.take_profit));
        }
      }

      const sortedTps = Array.from(tpsSet).sort((a, b) => Math.abs(a - openP) - Math.abs(b - openP));

      primary.is_grouped = true;
      primary.grouped_count = group.length;
      primary.all_ids = allIds;
      primary.all_tickets = allTickets;
      primary.volume = parseFloat(totalVolume.toFixed(4));
      primary.net_profit = parseFloat(totalNetProfit.toFixed(2));
      primary.gross_profit = parseFloat(totalGrossProfit.toFixed(2));
      primary.commission = parseFloat(totalCommission.toFixed(2));
      primary.swap = parseFloat(totalSwap.toFixed(2));
      primary.multiple_tps = sortedTps;
      primary.sub_trades = group;

      result.push(primary);
    }

    result.sort((a, b) => (b.open_time || '').localeCompare(a.open_time || ''));
    return result;
  },

  renderTable(trades = []) {
    const tbody = document.getElementById('tradesTableBody');
    if (!tbody) return;
    this.expandedTradeId = null;
    this.expandedRow = null;
    tbody.innerHTML = '';

    const displayTrades = this.groupOpenTrades(trades);

    if (displayTrades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:30px;color:#6b7280;">No trades match your filter criteria.</td></tr>';
      return;
    }

    displayTrades.forEach(t => {
      const tr = document.createElement('tr');
      tr.className = 'trade-data-row';
      tr.dataset.tradeId = t.id;
      tr.setAttribute('aria-expanded', 'false');
      tr.title = 'Click to expand trade details';
      const tradeCurrency = t.account_currency || App.getActiveCurrency();
      const pnl = parseFloat(t.net_profit || 0);
      const isWin = pnl > 0.001;
      const isLoss = pnl < -0.001;

      const pnlFormatted = App.formatMoney(pnl, tradeCurrency, { showSign: true });
      const pnlClass = isWin ? 'color-green' : (isLoss ? 'color-red' : 'color-muted');

      const dirClass = t.direction === 'BUY' ? 'badge-buy' : 'badge-sell';
      let statusClass = 'badge-be';
      let statusLabel = t.status || 'CLOSED';
      let exitDisplay = t.close_price || 'Open';
      let pnlDisplay = pnlFormatted;
      let pnlDisplayClass = pnlClass;

      if (t.is_missed) {
        statusClass = 'badge-missed';
        statusLabel = 'MISSED';
        pnlDisplay = '—';
        pnlDisplayClass = 'color-muted';
      } else if (t.status === 'PENDING') {
        statusClass = 'badge-pending';
        statusLabel = 'LIMIT';
        exitDisplay = '<span style="color:#f59e0b;font-weight:600;">Waiting for fill</span>';
        pnlDisplay = '—';
        pnlDisplayClass = 'color-muted';
      } else if (t.status === 'CANCELLED') {
        statusClass = 'badge-cancelled';
        statusLabel = 'CANCELLED';
        exitDisplay = '<span style="color:#9ca3af;">Cancelled</span>';
        pnlDisplay = '—';
        pnlDisplayClass = 'color-muted';
      } else if (t.status === 'OPEN') {
        statusClass = 'badge-open';
        statusLabel = 'OPEN';
        exitDisplay = '<span style="color:#60a5fa;">Open</span>';
      } else if (t.status === 'WIN') {
        statusClass = 'badge-win';
      } else if (t.status === 'LOSS') {
        statusClass = 'badge-loss';
      }

      const setupBadge = t.setup_name ? `<span class="badge badge-setup">${t.setup_name}</span>` : '<span style="color:#4b5563;">—</span>';
      const mistakeBadge = t.mistake_name ? `<span class="badge badge-mistake">${t.mistake_name}</span>` : '<span style="color:#4b5563;">—</span>';
      const rDisplay = (t.r_multiple !== null && t.r_multiple !== undefined)
        ? `<span style="display:block;font-size:11px;font-weight:600;color:#60a5fa;">${t.r_multiple > 0 ? '+' : ''}${parseFloat(t.r_multiple).toFixed(2)} R</span>`
        : '';

      let slTpDisplay = t.stop_loss ? `SL: ${t.stop_loss}` : '';
      if ((!t.multiple_tps || t.multiple_tps.length <= 1) && t.tp_targets) {
        try {
          const parsed = JSON.parse(t.tp_targets);
          if (Array.isArray(parsed) && parsed.length > 0) {
            t.multiple_tps = parsed.map(x => parseFloat(x.price)).filter(p => !isNaN(p) && p > 0);
          }
        } catch (e) {}
      }
      if (t.multiple_tps && t.multiple_tps.length > 1) {
        t.multiple_tps.forEach((tp, idx) => {
          slTpDisplay += `${slTpDisplay ? '<br>' : ''}<span style="color:#10b981;font-weight:600;">TP${idx + 1}: ${tp}</span>`;
        });
      } else if (t.take_profit) {
        slTpDisplay += `${slTpDisplay ? '<br>' : ''}TP: ${t.take_profit}`;
      }

      const deleteIdsParam = (t.is_grouped && t.all_ids) ? `[${t.all_ids.join(',')}]` : 'null';

      tr.innerHTML = `
        <td style="font-weight:600;color:#fff;">${t.open_time ? t.open_time.substring(0, 16).replace('T', ' ') : ''}</td>
        <td>
          <strong style="color:#60a5fa;">${t.symbol}</strong>
          ${t.is_grouped && t.grouped_count > 1 ? `<span class="badge badge-grouped" title="Merged from ${t.grouped_count} orders with distinct TPs">${t.grouped_count} TPs Grouped</span>` : ''}
          ${t.partial_close_count > 0 ? `<span style="display:block;font-size:10px;color:#a78bfa;">${t.partial_close_count} partial exit(s)</span>` : ''}
          ${t.screenshot_count > 0 ? `<span style="display:block;font-size:10px;color:#60a5fa;">${t.screenshot_count} screenshot(s)</span>` : ''}
        </td>
        <td><span class="badge ${dirClass}">${t.direction}</span></td>
        <td>
          ${t.volume}
          ${t.is_grouped && t.grouped_count > 1 ? `<span style="display:block;font-size:10px;color:#9ca3af;">(${t.grouped_count} orders)</span>` : ''}
        </td>
        <td>${t.open_price}</td>
        <td>${exitDisplay}</td>
        <td style="font-size:12px;color:#9ca3af;">
          ${slTpDisplay}
        </td>
        <td style="font-weight:700;" class="${pnlDisplayClass}">${pnlDisplay}${rDisplay}</td>
        <td><span class="badge ${statusClass}">${statusLabel}</span></td>
        <td>${setupBadge}</td>
        <td>${mistakeBadge}</td>
        <td style="text-align:right;">
          <button class="btn btn-secondary btn-sm" onclick="TradeDetail.open(${t.id})" title="Inspect Trade Chart">
            📊 Chart
          </button>
          <button class="btn btn-secondary btn-sm" onclick="Trades.openEditModal(${t.id})" title="Edit Trade">
            ✏️
          </button>
          <button class="btn btn-secondary btn-sm" onclick="Trades.deleteTrade(${t.id}, ${deleteIdsParam})" title="Delete Trade" style="color:#ef4444;">
            🗑️
          </button>
        </td>
      `;
      tr.addEventListener('click', event => {
        if (event.target.closest?.('button, a, input, select, textarea')) return;
        this.toggleExpandedTrade(t.id, tr);
      });
      tbody.appendChild(tr);
    });
  },

  async toggleExpandedTrade(tradeId, row) {
    if (this.expandedTradeId === tradeId) {
      this.collapseExpandedTrade();
      return;
    }

    this.collapseExpandedTrade();
    this.expandedTradeId = tradeId;
    row.classList.add('is-expanded');
    row.setAttribute('aria-expanded', 'true');

    const detailRow = document.createElement('tr');
    detailRow.className = 'trade-expanded-row';
    detailRow.dataset.tradeId = tradeId;
    detailRow.innerHTML = `
      <td colspan="12">
        <div class="trade-expanded-content">
          <span class="trade-expanded-loading">Loading trade details and screenshots...</span>
        </div>
      </td>`;
    row.insertAdjacentElement('afterend', detailRow);
    this.expandedRow = detailRow;

    try {
      const trade = await API.getTrade(tradeId);
      if (this.expandedTradeId !== tradeId || this.expandedRow !== detailRow) return;
      const content = detailRow.querySelector('.trade-expanded-content');
      content.innerHTML = this.renderExpandedTrade(trade);
      this.bindExpandedTradeActions(content, trade);
    } catch (err) {
      if (this.expandedTradeId !== tradeId || this.expandedRow !== detailRow) return;
      detailRow.querySelector('.trade-expanded-content').innerHTML =
        `<span class="trade-expanded-error">Failed to load details: ${TradeDetail.escapeHtml(err.message)}</span>`;
    }
  },

  collapseExpandedTrade() {
    const sourceRow = this.expandedRow?.previousElementSibling;
    if (sourceRow) {
      sourceRow.classList.remove('is-expanded');
      sourceRow.setAttribute('aria-expanded', 'false');
    }
    if (this.expandedRow?.parentNode) this.expandedRow.remove();
    this.expandedTradeId = null;
    this.expandedRow = null;
  },

  renderExpandedTrade(trade) {
    const escape = value => TradeDetail.escapeHtml(value);
    const tradeCurrency = trade.account_currency || App.getActiveCurrency();
    const pnl = Number(trade.net_profit || 0);
    const pnlClass = pnl >= 0 ? 'color-green' : 'color-red';
    const partials = Array.isArray(trade.partial_closes) ? trade.partial_closes : [];
    const screenshots = Array.isArray(trade.screenshots) ? trade.screenshots : [];
    const partialSummary = partials.length
      ? `${partials.reduce((sum, item) => sum + Number(item.volume || 0), 0).toFixed(2)} lots across ${partials.length} partial exit(s)`
      : 'No partial exits recorded';

    const screenshotMarkup = screenshots.length
      ? `<div class="trade-expanded-screenshot-grid">${screenshots.map((screenshot, index) => `
          <button type="button" class="trade-expanded-screenshot" data-screenshot-index="${index}" title="Open screenshot in viewer">
            <img src="${escape(screenshot.image_url)}" alt="${escape(screenshot.caption || 'Trade Screenshot')}" loading="lazy">
            <span>${escape(screenshot.caption || 'TradingView')}</span>
          </button>`).join('')}</div>`
      : '<div class="trade-expanded-empty">No screenshots for this trade yet.</div>';

    const partialMarkup = partials.length
      ? `<div class="trade-expanded-partials">${partials.map(partial => `
          <div><span>${escape(partial.close_time)} · ${Number(partial.volume).toFixed(2)} lots @ ${Number(partial.close_price)}</span>
          <strong class="${Number(partial.net_profit || 0) >= 0 ? 'color-green' : 'color-red'}">${App.formatMoney(partial.net_profit || 0, tradeCurrency, { showSign: true })}</strong></div>`).join('')}</div>`
      : '';

    const isPending = trade.status === 'PENDING';
    const isCancelled = trade.status === 'CANCELLED';
    const exitText = isPending ? 'Waiting for fill' : (isCancelled ? 'Cancelled' : (trade.close_time || 'Open'));
    const pnlText = (isPending || isCancelled) ? '—' : App.formatMoney(pnl, tradeCurrency, { showSign: true });
    const pnlDisplayClass = (isPending || isCancelled) ? 'color-muted' : pnlClass;

    const subTrades = Array.isArray(trade.sub_trades) ? trade.sub_trades : [];
    const groupedMarkup = (trade.is_grouped && subTrades.length > 1)
      ? `<div class="trade-expanded-section">
          <div class="trade-expanded-section-title">
            Grouped Orders (${subTrades.length} Positions with Multiple TPs)
            <span>${Number(trade.grouped_total_volume || trade.volume).toFixed(2)} lots total</span>
          </div>
          <div class="trade-expanded-partials">
            ${subTrades.map((leg, idx) => {
              const legPnl = Number(leg.net_profit || 0);
              const legPnlClass = legPnl >= 0 ? 'color-green' : 'color-red';
              const tpStr = leg.take_profit ? `TP${idx + 1}: ${leg.take_profit}` : 'No TP';
              const slStr = leg.stop_loss ? `SL: ${leg.stop_loss}` : 'No SL';
              return `<div>
                <span>Ticket #${escape(leg.ticket || leg.id)} · ${Number(leg.volume).toFixed(2)} lots · Entry: ${leg.open_price} · <strong style="color:#10b981;">${tpStr}</strong> · <span style="color:#ef4444;">${slStr}</span></span>
                <strong class="${legPnlClass}">${App.formatMoney(legPnl, tradeCurrency, { showSign: true })}</strong>
              </div>`;
            }).join('')}
          </div>
        </div>`
      : '';

    return `
      <div class="trade-expanded-header">
        <div>
          <strong>${escape(trade.symbol)} · ${escape(trade.direction)}</strong>
          <span>${escape(trade.ticket || 'No Ticket')}</span>
        </div>
        <button type="button" class="btn btn-secondary btn-sm" data-open-trade-detail>📊 Full Details</button>
      </div>
      <div class="trade-expanded-grid">
        <div><span>Open / Close</span><strong>${escape(trade.open_time || '—')} → ${escape(exitText)}</strong></div>
        <div><span>Net P&L / Status</span><strong class="${pnlDisplayClass}">${pnlText}${trade.r_multiple != null ? ` (${Number(trade.r_multiple) >= 0 ? '+' : ''}${Number(trade.r_multiple).toFixed(2)} R)` : ''} · ${escape(trade.status || '—')}</strong></div>
        <div><span>Setup / Mistake</span><strong>${escape(trade.setup_name || '—')} / ${escape(trade.mistake_name || '—')}</strong></div>
        <div><span>Signals & Emotions</span><strong>${escape(trade.signals || '—')}${trade.emotion_pre ? ` · Pre: ${escape(trade.emotion_pre)}` : ''}${trade.emotion_during ? ` · In: ${escape(trade.emotion_during)}` : ''}</strong></div>
        <div><span>Notes / Reflections</span><strong>${escape(trade.key_learnings || trade.post_trade_notes || trade.notes || 'No notes')}</strong></div>
      </div>
      ${groupedMarkup}
      <div class="trade-expanded-section">
        <div class="trade-expanded-section-title">Partial Exits <span>${escape(partialSummary)}</span></div>
        ${partialMarkup}
      </div>
      <div class="trade-expanded-section">
        <div class="trade-expanded-section-title">Screenshots <span>${screenshots.length} image(s) · Click to view</span></div>
        ${screenshotMarkup}
      </div>`;
  },

  bindExpandedTradeActions(content, trade) {
    content.querySelector('[data-open-trade-detail]')?.addEventListener('click', event => {
      event.stopPropagation();
      TradeDetail.open(trade.id);
    });
    content.querySelectorAll('[data-screenshot-index]').forEach(button => {
      button.addEventListener('click', event => {
        event.stopPropagation();
        TradeDetail.openScreenshotCollection(trade.screenshots || [], Number(button.dataset.screenshotIndex));
      });
    });
  },

  renderPagination() {
    const pageInfo = document.getElementById('tradesPageInfo');
    const prevBtn = document.getElementById('tradesPrevBtn');
    const nextBtn = document.getElementById('tradesNextBtn');

    const currentPage = Math.floor(this.currentOffset / this.limit) + 1;
    const totalPages = Math.max(1, Math.ceil(this.totalTrades / this.limit));

    if (pageInfo) pageInfo.textContent = `Page ${currentPage} of ${totalPages} (${this.totalTrades} trades)`;
    if (prevBtn) prevBtn.disabled = this.currentOffset === 0;
    if (nextBtn) nextBtn.disabled = this.currentOffset + this.limit >= this.totalTrades;
  },

  prevPage() {
    if (this.currentOffset > 0) {
      this.load(Math.floor(this.currentOffset / this.limit) - 1);
    }
  },

  nextPage() {
    if (this.currentOffset + this.limit < this.totalTrades) {
      this.load(Math.floor(this.currentOffset / this.limit) + 1);
    }
  },

  addDynamicTpRow(data = null) {
    const list = document.getElementById('tfDynamicTpList');
    if (!list) return;
    const currentRows = list.querySelectorAll('.dynamic-tp-row');
    const nextIndex = currentRows.length + 1;

    const row = document.createElement('div');
    row.className = 'dynamic-tp-row';
    row.style = 'display:flex;gap:8px;align-items:center;background:#090e18;padding:8px 10px;border-radius:6px;border:1px solid #1e293b;';

    const priceVal = data?.close_price ?? data?.price ?? '';
    const volVal = data?.volume ?? '';
    const pnlVal = data?.net_profit ?? '';

    row.innerHTML = `
      <span class="badge tp-label" style="background:#1e293b;color:#10b981;min-width:44px;text-align:center;font-weight:700;">TP${nextIndex}</span>
      <div style="flex:2;position:relative;">
        <input type="number" class="form-input tp-price" step="any" placeholder="Target Price" value="${priceVal}" style="width:100%;" oninput="Trades.recalculateRMultiple()">
      </div>
      <div style="flex:1.2;position:relative;">
        <input type="number" class="form-input tp-vol" step="0.01" placeholder="Lots" value="${volVal}" style="width:100%;" oninput="Trades.recalculateRMultiple()">
      </div>
      <div style="flex:1.5;position:relative;">
        <input type="number" class="form-input tp-pnl" step="0.01" placeholder="P&L (Optional)" value="${pnlVal}" style="width:100%;" oninput="Trades.recalculateRMultiple()">
      </div>
      <button type="button" class="btn btn-secondary btn-sm" style="color:#ef4444;padding:4px 8px;" onclick="Trades.removeDynamicTpRow(this)" title="Remove TP">✕</button>
    `;
    list.appendChild(row);
    this.recalculateRMultiple();
  },

  removeDynamicTpRow(btn) {
    const row = btn.closest('.dynamic-tp-row');
    if (row) row.remove();
    const list = document.getElementById('tfDynamicTpList');
    if (list) {
      list.querySelectorAll('.dynamic-tp-row').forEach((r, idx) => {
        const lbl = r.querySelector('.tp-label');
        if (lbl) lbl.textContent = `TP${idx + 1}`;
      });
    }
    this.recalculateRMultiple();
  },

  collectDynamicTps() {
    const list = document.getElementById('tfDynamicTpList');
    if (!list) return [];
    const targets = [];
    const openTime = document.getElementById('tfOpenTime')?.value || new Date().toISOString();
    list.querySelectorAll('.dynamic-tp-row').forEach((r, idx) => {
      const price = parseFloat(r.querySelector('.tp-price')?.value);
      const volRaw = r.querySelector('.tp-vol')?.value;
      const vol = volRaw !== '' && !isNaN(parseFloat(volRaw)) && parseFloat(volRaw) > 0 ? parseFloat(volRaw) : null;
      const pnlRaw = r.querySelector('.tp-pnl')?.value;
      const pnl = pnlRaw !== '' && !isNaN(parseFloat(pnlRaw)) ? parseFloat(pnlRaw) : null;
      if (!isNaN(price) && price > 0) {
        targets.push({
          index: idx + 1,
          price: price,
          volume: vol,
          net_profit: pnl,
          close_time: openTime.replace('T', ' ')
        });
      }
    });
    return targets;
  },

  recalculateRMultiple() {
    const dir = document.getElementById('tfDirection')?.value || 'BUY';
    const isBuy = dir === 'BUY';
    const totalVolume = parseFloat(document.getElementById('tfVolume')?.value) || 0;
    const openPrice = parseFloat(document.getElementById('tfOpenPrice')?.value) || 0;
    const closePrice = parseFloat(document.getElementById('tfClosePrice')?.value) || 0;
    const stopLoss = parseFloat(document.getElementById('tfStopLoss')?.value) || 0;
    let takeProfit = parseFloat(document.getElementById('tfTakeProfit')?.value) || 0;
    const netProfit = parseFloat(document.getElementById('tfNetProfit')?.value) || 0;
    const initialRisk = parseFloat(document.getElementById('tfInitialRisk')?.value) || 0;

    // Inspect dynamic TP rows
    const list = document.getElementById('tfDynamicTpList');
    const tpRows = list ? Array.from(list.querySelectorAll('.dynamic-tp-row')) : [];
    const tpTargets = [];
    tpRows.forEach(r => {
      const p = parseFloat(r.querySelector('.tp-price')?.value);
      const v = parseFloat(r.querySelector('.tp-vol')?.value);
      const pnl = parseFloat(r.querySelector('.tp-pnl')?.value);
      if (!isNaN(p) && p > 0) {
        tpTargets.push({
          price: p,
          volume: !isNaN(v) && v > 0 ? v : 0,
          netProfit: !isNaN(pnl) ? pnl : null
        });
      }
    });

    // If dynamic TPs exist, sync primary takeProfit input with either the final or first TP
    if (tpTargets.length > 0) {
      takeProfit = tpTargets[tpTargets.length - 1].price;
      const tfTpInput = document.getElementById('tfTakeProfit');
      if (tfTpInput) tfTpInput.value = takeProfit;
    }

    let r = null;
    let riskDist = 0;
    let targetRR = null;

    if (openPrice > 0 && stopLoss > 0 && openPrice !== stopLoss) {
      riskDist = Math.abs(openPrice - stopLoss);

      // Target R:R from TP targets with volume weights if available
      if (tpTargets.length > 0) {
        const hasVolumes = tpTargets.some(t => t.volume > 0);
        const sumV = tpTargets.reduce((acc, t) => acc + (t.volume > 0 ? t.volume : 0), 0);
        const effectiveTotalV = sumV > 0 ? sumV : (totalVolume > 0 ? totalVolume : tpTargets.length);

        let weightedTargetReward = 0;
        let countedWeights = 0;

        tpTargets.forEach(t => {
          const reward = isBuy ? (t.price - openPrice) : (openPrice - t.price);
          const weight = hasVolumes && sumV > 0 ? (t.volume / sumV) : (1 / tpTargets.length);
          weightedTargetReward += reward * weight;
          countedWeights += weight;
        });

        if (countedWeights > 0 && riskDist > 0) {
          targetRR = weightedTargetReward / riskDist;
        }
      } else if (takeProfit > 0 && takeProfit !== openPrice) {
        const targetReward = isBuy ? (takeProfit - openPrice) : (openPrice - takeProfit);
        targetRR = targetReward / riskDist;
      }

      // Realized R-Multiple
      if (closePrice > 0) {
        const realizedReward = isBuy ? (closePrice - openPrice) : (openPrice - closePrice);
        r = realizedReward / riskDist;
      } else if (tpTargets.length > 0 && tpTargets.some(t => t.netProfit !== null && Math.abs(t.netProfit) > 0.0001)) {
        // Sum from partial profits if available
        const totalTpPnl = tpTargets.reduce((acc, t) => acc + (t.netProfit || 0), 0);
        if (initialRisk > 0) {
          r = totalTpPnl / initialRisk;
        }
      } else if (initialRisk > 0 && Math.abs(netProfit) > 0.0001) {
        r = netProfit / initialRisk;
      }
    } else if (initialRisk > 0 && Math.abs(netProfit) > 0.0001) {
      r = netProfit / initialRisk;
    }

    // Update Target R:R display
    const rrDisplay = document.getElementById('tfTargetRRDisplay');
    if (rrDisplay) {
      if (targetRR !== null) {
        const formatted = targetRR.toFixed(2);
        rrDisplay.textContent = `1 : ${formatted}${tpTargets.length > 1 ? ' (avg)' : ''}`;
        rrDisplay.style.color = targetRR >= 1 ? '#10b981' : '#f59e0b';
      } else {
        rrDisplay.textContent = '—';
        rrDisplay.style.color = '#10b981';
      }
    }

    // Update Risk Distance display
    const distDisplay = document.getElementById('tfRiskDistDisplay');
    if (distDisplay) {
      distDisplay.textContent = riskDist > 0 ? `${riskDist < 1 ? riskDist.toFixed(5) : riskDist.toFixed(2)} pts` : '—';
    }

    // Update R-Multiple input & badge
    const rInput = document.getElementById('tfRMultiple');
    const badge = document.getElementById('tfRMultipleCalcBadge');
    if (rInput) {
      if (r !== null && !isNaN(r)) {
        rInput.value = r.toFixed(2);
        if (badge) {
          badge.textContent = `${r >= 0 ? '+' : ''}${r.toFixed(2)} R`;
          badge.style.color = r >= 0 ? '#10b981' : '#ef4444';
        }
      } else {
        if (!rInput.value && badge) {
          badge.textContent = 'Auto';
          badge.style.color = '#60a5fa';
        }
      }
    }
  },

  onMissedTradeToggle() {
    const chk = document.getElementById('tfIsMissed');
    const isMissed = chk && chk.checked;
    if (isMissed) {
      const pnlInput = document.getElementById('tfNetProfit');
      if (pnlInput) pnlInput.value = '0.00';
      const stSelect = document.getElementById('tfStatus');
      if (stSelect) stSelect.value = 'CLOSED';
    }
  },

  togglePreEmotion(btn, val) {
    const input = document.getElementById('tfEmotionPre');
    if (!input) return;
    let selected = input.value ? input.value.split(',').map(s => s.trim()).filter(Boolean) : [];
    const normVal = val.trim();
    const idx = selected.findIndex(s => s.toLowerCase() === normVal.toLowerCase());
    if (idx >= 0) {
      selected.splice(idx, 1);
      if (btn) btn.classList.remove('active');
    } else {
      selected.push(normVal);
      if (btn) btn.classList.add('active');
    }
    input.value = selected.join(', ');
  },

  toggleDuringEmotion(btn, val) {
    const input = document.getElementById('tfEmotionDuring');
    if (!input) return;
    let selected = input.value ? input.value.split(',').map(s => s.trim()).filter(Boolean) : [];
    const normVal = val.trim();
    const idx = selected.findIndex(s => s.toLowerCase() === normVal.toLowerCase());
    if (idx >= 0) {
      selected.splice(idx, 1);
      if (btn) btn.classList.remove('active');
    } else {
      selected.push(normVal);
      if (btn) btn.classList.add('active');
    }
    input.value = selected.join(', ');
  },

  // Backward compatibility
  setPreEmotion(btn, val) {
    this.togglePreEmotion(btn, val);
  },

  setDuringEmotion(btn, val) {
    this.toggleDuringEmotion(btn, val);
  },

  toggleSignalTag(tag) {
    const input = document.getElementById('tfSignals');
    if (!input) return;
    const current = input.value.split(',').map(s => s.trim()).filter(Boolean);
    const idx = current.indexOf(tag);
    if (idx >= 0) {
      current.splice(idx, 1);
    } else {
      current.push(tag);
    }
    input.value = current.join(', ');
    this.checkTwinTrades();
  },

  checkTwinTrades() {
    clearTimeout(this.twinDebounceTimer);
    this.twinDebounceTimer = setTimeout(async () => {
      const symbol = document.getElementById('tfSymbol')?.value?.trim();
      const box = document.getElementById('tfTwinTradesBox');
      if (!box) return;

      if (!symbol || symbol.length < 2) {
        box.style.display = 'none';
        return;
      }

      const direction = document.getElementById('tfDirection')?.value || '';
      const setup_id = document.getElementById('tfSetup')?.value || '';
      const timeframe = document.getElementById('tfTimeframe')?.value || '';
      const signals = document.getElementById('tfSignals')?.value || '';

      try {
        const params = { symbol, direction };
        if (setup_id) params.setup_id = setup_id;
        if (timeframe) params.timeframe = timeframe;
        if (signals) params.signals = signals;
        if (this.activeEditingId) params.exclude_id = this.activeEditingId;
        params.limit = 3;

        const data = await API.getSimilarTrades(params);
        if (data && data.count > 0) {
          box.style.display = 'block';
          const statsEl = document.getElementById('tfTwinTradesStats');
          if (statsEl) {
            statsEl.textContent = `${data.count} similar trades · ${data.win_rate}% Win · Avg ${data.avg_r >= 0 ? '+' : ''}${data.avg_r} R`;
          }
          const listEl = document.getElementById('tfTwinTradesList');
          if (listEl) {
            listEl.innerHTML = (data.similar_trades || []).map(st => {
              const pnlCls = (st.net_profit || 0) >= 0 ? 'color-green' : 'color-red';
              const rStr = st.r_multiple != null ? ` · ${st.r_multiple >= 0 ? '+' : ''}${st.r_multiple}R` : '';
              return `<span class="badge" style="background:#111827;border:1px solid #1f2937;cursor:pointer;" onclick="TradeDetail.open(${st.id})" title="Click to view chart">${st.open_time?.substring(0, 10)} ${st.direction} <strong class="${pnlCls}">${st.net_profit}${rStr}</strong></span>`;
            }).join('');
          }
        } else {
          box.style.display = 'none';
        }
      } catch (e) {
        console.warn('Failed to query twin trades:', e);
      }
    }, 300);
  },

  openAddModal() {
    document.getElementById('tradeModalTitle').textContent = 'Log New Trade';
    document.getElementById('tradeForm').reset();
    this.activeEditingId = null;

    if (document.getElementById('tfStatus')) {
      document.getElementById('tfStatus').value = 'AUTO';
    }

    // Set default timestamps
    const now = new Date();
    const nowStr = now.toISOString().substring(0, 16);
    if (document.getElementById('tfOpenTime')) document.getElementById('tfOpenTime').value = nowStr;
    if (document.getElementById('tfCloseTime')) document.getElementById('tfCloseTime').value = '';

    // Reset feature inputs
    const isMissedChk = document.getElementById('tfIsMissed');
    if (isMissedChk) isMissedChk.checked = false;
    if (document.getElementById('tfInitialRisk')) document.getElementById('tfInitialRisk').value = '';
    if (document.getElementById('tfRiskMode')) document.getElementById('tfRiskMode').value = 'CURRENCY';
    if (document.getElementById('tfRMultiple')) document.getElementById('tfRMultiple').value = '';
    const badge = document.getElementById('tfRMultipleCalcBadge');
    if (badge) {
      badge.textContent = 'Auto';
      badge.style.color = '#60a5fa';
    }
    const distDisplay = document.getElementById('tfRiskDistDisplay');
    if (distDisplay) distDisplay.textContent = '—';
    const rrDisplay = document.getElementById('tfTargetRRDisplay');
    if (rrDisplay) rrDisplay.textContent = '—';

    const tpList = document.getElementById('tfDynamicTpList');
    if (tpList) {
      tpList.innerHTML = '';
      this.addDynamicTpRow();
    }
    if (document.getElementById('tfSignals')) document.getElementById('tfSignals').value = '';
    if (document.getElementById('tfPreTradeNotes')) document.getElementById('tfPreTradeNotes').value = '';
    if (document.getElementById('tfPostTradeNotes')) document.getElementById('tfPostTradeNotes').value = '';
    if (document.getElementById('tfKeyLearnings')) document.getElementById('tfKeyLearnings').value = '';
    if (document.getElementById('tfNotes')) document.getElementById('tfNotes').value = '';
    if (document.getElementById('tfEmotionPre')) document.getElementById('tfEmotionPre').value = '';
    if (document.getElementById('tfEmotionDuring')) document.getElementById('tfEmotionDuring').value = '';
    document.querySelectorAll('#tfEmotionPreGroup .chip-btn, #tfEmotionDuringGroup .chip-btn').forEach(b => b.classList.remove('active'));
    const twinBox = document.getElementById('tfTwinTradesBox');
    if (twinBox) twinBox.style.display = 'none';

    // Populate accounts select
    const accSelect = document.getElementById('tfAccount');
    if (accSelect) {
      accSelect.innerHTML = '';
      (App.accounts || []).forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.id;
        opt.textContent = `${a.name} (${a.platform})`;
        accSelect.appendChild(opt);
      });
    }

    // Populate setup and mistakes
    const setupSelect = document.getElementById('tfSetup');
    if (setupSelect) {
      setupSelect.innerHTML = '<option value="">-- No Setup --</option>';
      (App.playbooks || []).forEach(p => {
        const opt = document.createElement('option');
        opt.value = p.id;
        opt.textContent = p.name;
        setupSelect.appendChild(opt);
      });
    }

    const mistakeSelect = document.getElementById('tfMistake');
    if (mistakeSelect) {
      mistakeSelect.innerHTML = '<option value="">-- No Mistake --</option>';
      (App.mistakes || []).forEach(m => {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.name;
        mistakeSelect.appendChild(opt);
      });
    }

    document.getElementById('addTradeModal').classList.add('active');
  },

  openDetailModal(tradeId) {
    if (typeof TradeDetail !== 'undefined' && TradeDetail.open) {
      TradeDetail.open(tradeId);
    }
  },

  async openEditModal(tradeId) {
    this.activeEditingId = tradeId;
    document.getElementById('tradeModalTitle').textContent = 'Edit Trade';

    try {
      const trade = await API.getTrade(tradeId);
      
      this.openAddModal(); // sets up dropdowns and resets
      document.getElementById('tradeModalTitle').textContent = 'Edit Trade';
      this.activeEditingId = tradeId;

      if (document.getElementById('tfAccount')) document.getElementById('tfAccount').value = trade.account_id;
      if (document.getElementById('tfSymbol')) document.getElementById('tfSymbol').value = trade.symbol;
      if (document.getElementById('tfDirection')) document.getElementById('tfDirection').value = trade.direction;
      if (document.getElementById('tfStatus')) {
        document.getElementById('tfStatus').value = trade.status || 'AUTO';
      }
      if (document.getElementById('tfVolume')) document.getElementById('tfVolume').value = trade.volume;
      if (document.getElementById('tfOpenPrice')) document.getElementById('tfOpenPrice').value = trade.open_price;
      if (document.getElementById('tfClosePrice')) document.getElementById('tfClosePrice').value = trade.close_price ?? '';
      if (document.getElementById('tfStopLoss')) document.getElementById('tfStopLoss').value = trade.stop_loss ?? '';
      if (document.getElementById('tfTakeProfit')) document.getElementById('tfTakeProfit').value = trade.take_profit ?? '';
      if (document.getElementById('tfNetProfit')) document.getElementById('tfNetProfit').value = trade.net_profit ?? 0;
      if (document.getElementById('tfCommission')) document.getElementById('tfCommission').value = trade.commission ?? 0;
      if (document.getElementById('tfSwap')) document.getElementById('tfSwap').value = trade.swap ?? 0;
      if (document.getElementById('tfOpenTime')) document.getElementById('tfOpenTime').value = (trade.open_time || '').substring(0, 16);
      if (document.getElementById('tfCloseTime')) document.getElementById('tfCloseTime').value = (trade.close_time || '').substring(0, 16);
      if (document.getElementById('tfSetup')) document.getElementById('tfSetup').value = trade.setup_id || '';
      if (document.getElementById('tfMistake')) document.getElementById('tfMistake').value = trade.mistake_id || '';
      if (document.getElementById('tfNotes')) document.getElementById('tfNotes').value = trade.notes || '';

      // Populate feature fields
      if (document.getElementById('tfIsMissed')) {
        document.getElementById('tfIsMissed').checked = !!trade.is_missed;
      }
      if (document.getElementById('tfInitialRisk')) {
        document.getElementById('tfInitialRisk').value = trade.initial_risk || '';
      }
      if (document.getElementById('tfRiskMode')) {
        document.getElementById('tfRiskMode').value = trade.risk_mode || 'CURRENCY';
      }
      if (document.getElementById('tfRMultiple')) {
        document.getElementById('tfRMultiple').value = trade.r_multiple != null ? trade.r_multiple : '';
        const badge = document.getElementById('tfRMultipleCalcBadge');
        if (badge && trade.r_multiple != null) {
          badge.textContent = `${trade.r_multiple >= 0 ? '+' : ''}${parseFloat(trade.r_multiple).toFixed(2)} R`;
          badge.style.color = trade.r_multiple >= 0 ? '#10b981' : '#ef4444';
        }
      }
      if (document.getElementById('tfSignals')) {
        document.getElementById('tfSignals').value = trade.signals || '';
      }
      if (document.getElementById('tfPreTradeNotes')) {
        document.getElementById('tfPreTradeNotes').value = trade.pre_trade_notes || (!trade.post_trade_notes && !trade.key_learnings ? (trade.notes || '') : '');
      }
      if (document.getElementById('tfPostTradeNotes')) {
        document.getElementById('tfPostTradeNotes').value = trade.post_trade_notes || '';
      }
      if (document.getElementById('tfKeyLearnings')) {
        document.getElementById('tfKeyLearnings').value = trade.key_learnings || '';
      }
      if (document.getElementById('tfTimeframe') && trade.timeframe) {
        document.getElementById('tfTimeframe').value = trade.timeframe;
      }

      // Multi-select pre-trade emotions with German/English alias support
      const EMOTION_ALIASES = {
        'ruhig': 'calm',
        'fokussiert': 'focused',
        'überzeugt': 'confident',
        'fomo': 'fomo',
        'ängstlich': 'fearful',
        'gierig': 'greedy',
        'ungeduldig': 'impatient',
        'geduldig': 'patient',
        'entspannt': 'relaxed',
        'unter druck': 'under pressure',
        'frustriert': 'frustrated',
        'revanche-modus': 'revenge trading',
        'revanche': 'revenge trading'
      };

      if (document.getElementById('tfEmotionPre')) {
        document.getElementById('tfEmotionPre').value = trade.emotion_pre || '';
        const preEmos = (trade.emotion_pre || '').split(',').map(s => {
          const l = s.trim().toLowerCase();
          return EMOTION_ALIASES[l] || l;
        }).filter(Boolean);
        const group = document.getElementById('tfEmotionPreGroup');
        if (group) {
          group.querySelectorAll('.chip-btn').forEach(b => {
            const bVal = (b.dataset.val || b.textContent).trim().toLowerCase();
            const mappedVal = EMOTION_ALIASES[bVal] || bVal;
            if (preEmos.includes(bVal) || preEmos.includes(mappedVal)) {
              b.classList.add('active');
            } else {
              b.classList.remove('active');
            }
          });
        }
      }

      // Multi-select in-trade emotions
      if (document.getElementById('tfEmotionDuring')) {
        document.getElementById('tfEmotionDuring').value = trade.emotion_during || '';
        const duringEmos = (trade.emotion_during || '').split(',').map(s => {
          const l = s.trim().toLowerCase();
          return EMOTION_ALIASES[l] || l;
        }).filter(Boolean);
        const group = document.getElementById('tfEmotionDuringGroup');
        if (group) {
          group.querySelectorAll('.chip-btn').forEach(b => {
            const bVal = (b.dataset.val || b.textContent).trim().toLowerCase();
            const mappedVal = EMOTION_ALIASES[bVal] || bVal;
            if (duringEmos.includes(bVal) || duringEmos.includes(mappedVal)) {
              b.classList.add('active');
            } else {
              b.classList.remove('active');
            }
          });
        }
      }

      const tpList = document.getElementById('tfDynamicTpList');
      if (tpList) {
        tpList.innerHTML = '';
        let loaded = false;
        if (trade.tp_targets) {
          try {
            const targets = JSON.parse(trade.tp_targets);
            if (Array.isArray(targets) && targets.length > 0) {
              targets.forEach(t => {
                this.addDynamicTpRow({ close_price: t.price, volume: t.volume, net_profit: t.net_profit });
              });
              loaded = true;
            }
          } catch (e) {}
        }
        if (!loaded && trade.partial_closes && trade.partial_closes.length > 0) {
          trade.partial_closes.forEach(pc => {
            this.addDynamicTpRow(pc);
          });
          loaded = true;
        }
        if (!loaded && trade.take_profit && trade.take_profit > 0) {
          this.addDynamicTpRow({ close_price: trade.take_profit, volume: trade.volume || '' });
          loaded = true;
        }
        if (!loaded) {
          this.addDynamicTpRow();
        }
      }

      this.recalculateRMultiple();
      this.checkTwinTrades();
    } catch (err) {
      console.error('Error opening edit modal:', err);
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  closeModal() {
    document.getElementById('addTradeModal').classList.remove('active');
  },

  async saveTradeFromForm(e) {
    e.preventDefault();

    const account_id = parseInt(document.getElementById('tfAccount')?.value || '1');
    const symbol = (document.getElementById('tfSymbol')?.value || '').toUpperCase().trim();
    const direction = document.getElementById('tfDirection')?.value || 'BUY';
    const selectedStatus = document.getElementById('tfStatus')?.value || 'AUTO';
    const volume = parseFloat(document.getElementById('tfVolume')?.value || '1.0');
    const open_price = parseFloat(document.getElementById('tfOpenPrice')?.value || '0.0');
    const close_price = document.getElementById('tfClosePrice')?.value ? parseFloat(document.getElementById('tfClosePrice').value) : null;
    const stop_loss = document.getElementById('tfStopLoss')?.value ? parseFloat(document.getElementById('tfStopLoss').value) : null;
    const take_profit = document.getElementById('tfTakeProfit')?.value ? parseFloat(document.getElementById('tfTakeProfit').value) : null;
    const net_profit = parseFloat(document.getElementById('tfNetProfit')?.value || 0);
    const commission = parseFloat(document.getElementById('tfCommission')?.value || 0);
    const swap = parseFloat(document.getElementById('tfSwap')?.value || 0);

    let status = selectedStatus;
    if (selectedStatus === 'AUTO') {
      if (!close_price && !document.getElementById('tfCloseTime')?.value) {
        status = 'OPEN';
      } else {
        status = net_profit > 0.001 ? 'WIN' : (net_profit < -0.001 ? 'LOSS' : 'BE');
      }
    }

    const open_time_val = document.getElementById('tfOpenTime')?.value || new Date().toISOString().substring(0, 16);
    const open_time = open_time_val.replace('T', ' ');
    const close_time_val = document.getElementById('tfCloseTime')?.value;
    const close_time = close_time_val ? close_time_val.replace('T', ' ') : (['PENDING', 'OPEN'].includes(status) ? null : open_time);
    const setup_id = document.getElementById('tfSetup')?.value ? parseInt(document.getElementById('tfSetup').value) : null;
    const mistake_id = document.getElementById('tfMistake')?.value ? parseInt(document.getElementById('tfMistake').value) : null;

    const pre_trade_notes = document.getElementById('tfPreTradeNotes')?.value || '';
    const post_trade_notes = document.getElementById('tfPostTradeNotes')?.value || '';
    const key_learnings = document.getElementById('tfKeyLearnings')?.value || '';
    const notesInput = document.getElementById('tfNotes');
    const notes = [pre_trade_notes, post_trade_notes, key_learnings].filter(Boolean).join('\n\n') || (notesInput ? notesInput.value : '');

    const is_missed = document.getElementById('tfIsMissed') ? document.getElementById('tfIsMissed').checked : false;
    const initial_risk = document.getElementById('tfInitialRisk')?.value ? parseFloat(document.getElementById('tfInitialRisk').value) : null;
    const risk_mode = document.getElementById('tfRiskMode')?.value || 'CURRENCY';
    const r_multiple = document.getElementById('tfRMultiple')?.value ? parseFloat(document.getElementById('tfRMultiple').value) : null;
    const emotion_pre = document.getElementById('tfEmotionPre')?.value || '';
    const emotion_during = document.getElementById('tfEmotionDuring')?.value || '';
    const signals = document.getElementById('tfSignals')?.value || '';
    const timeframe = document.getElementById('tfTimeframe')?.value || 'M15';

    const payload = {
      account_id, symbol, direction, volume, open_price, close_price,
      stop_loss, take_profit, net_profit, commission, swap,
      open_time, close_time, setup_id, mistake_id, notes,
      status: status,
      is_missed, initial_risk, risk_mode, r_multiple,
      pre_trade_notes, post_trade_notes, key_learnings,
      emotion_pre, emotion_during, signals, timeframe
    };

    // Collect dynamic TP targets
    const dynamicTargets = this.collectDynamicTps();
    if (dynamicTargets.length > 0) {
      payload.tp_targets = JSON.stringify(dynamicTargets);
      if (!payload.take_profit) {
        payload.take_profit = dynamicTargets[dynamicTargets.length - 1].price;
      }
      // If the trade is CLOSED and targets have lots, also save as partial closes
      if (['CLOSED', 'WIN', 'LOSS', 'BE'].includes(status) || close_price) {
        const closedPartials = dynamicTargets
          .filter(t => t.volume && t.volume > 0)
          .map((t, idx) => ({
            ticket: `manual_tp_${idx + 1}_${Date.now()}`,
            close_price: t.price,
            volume: t.volume,
            net_profit: t.net_profit || 0,
            close_time: t.close_time
          }));
        if (closedPartials.length > 0) {
          payload.partial_closes = closedPartials;
        }
      }
    }

    try {
      if (this.activeEditingId) {
        await API.updateTrade(this.activeEditingId, payload);
        App.showToast('Trade updated successfully!', 'success');
      } else {
        await API.createTrade(payload);
        App.showToast('Trade created successfully!', 'success');
      }
      this.closeModal();
      this.load();
      if (typeof Dashboard !== 'undefined' && Dashboard.load) {
        Dashboard.load();
      }
    } catch (err) {
      console.error('Error saving trade:', err);
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  async deleteTrade(tradeId, allIds = null) {
    const isGrouped = Array.isArray(allIds) && allIds.length > 1;
    const msg = isGrouped
      ? `Are you sure you want to delete all ${allIds.length} grouped orders of this trade?`
      : 'Are you sure you want to delete this trade?';
    if (!confirm(msg)) return;
    try {
      if (isGrouped) {
        for (const id of allIds) {
          await API.deleteTrade(id);
        }
      } else {
        await API.deleteTrade(tradeId);
      }
      App.showToast('Trade deleted successfully.', 'success');
      this.load();
      if (typeof Dashboard !== 'undefined' && Dashboard.load) {
        Dashboard.load();
      }
    } catch (err) {
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  exportCSV() {
    const acc = App.activeAccountId ? `?account_id=${App.activeAccountId}` : '';
    window.location.href = `/api/trades/export/csv${acc}`;
  }
};
