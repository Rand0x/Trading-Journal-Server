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

  renderTable(trades = []) {
    const tbody = document.getElementById('tradesTableBody');
    if (!tbody) return;
    this.expandedTradeId = null;
    this.expandedRow = null;
    tbody.innerHTML = '';

    if (trades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:30px;color:#6b7280;">No trades match your filter criteria.</td></tr>';
      return;
    }

    trades.forEach(t => {
      const tr = document.createElement('tr');
      tr.className = 'trade-data-row';
      tr.dataset.tradeId = t.id;
      tr.setAttribute('aria-expanded', 'false');
      tr.title = 'Klicken, um die Trade-Details auszuklappen';
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

      if (t.status === 'PENDING') {
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

      tr.innerHTML = `
        <td style="font-weight:600;color:#fff;">${t.open_time ? t.open_time.substring(0, 16).replace('T', ' ') : ''}</td>
        <td>
          <strong style="color:#60a5fa;">${t.symbol}</strong>
          ${t.partial_close_count > 0 ? `<span style="display:block;font-size:10px;color:#a78bfa;">${t.partial_close_count} partial exit(s)</span>` : ''}
          ${t.screenshot_count > 0 ? `<span style="display:block;font-size:10px;color:#60a5fa;">${t.screenshot_count} screenshot(s)</span>` : ''}
        </td>
        <td><span class="badge ${dirClass}">${t.direction}</span></td>
        <td>${t.volume}</td>
        <td>${t.open_price}</td>
        <td>${exitDisplay}</td>
        <td style="font-size:12px;color:#9ca3af;">
          ${t.stop_loss ? `SL: ${t.stop_loss}` : ''} 
          ${t.take_profit ? `<br>TP: ${t.take_profit}` : ''}
        </td>
        <td style="font-weight:700;" class="${pnlDisplayClass}">${pnlDisplay}</td>
        <td><span class="badge ${statusClass}">${statusLabel}</span></td>
        <td>${setupBadge}</td>
        <td>${mistakeBadge}</td>
        <td style="text-align:right;">
          <button class="btn btn-secondary btn-sm" onclick="TradeDetail.open(${t.id})" title="Inspect Trade on Lightweight Charts">
            📊 Chart
          </button>
          <button class="btn btn-secondary btn-sm" onclick="Trades.openEditModal(${t.id})" title="Edit Trade">
            ✏️
          </button>
          <button class="btn btn-secondary btn-sm" onclick="Trades.deleteTrade(${t.id})" title="Delete Trade" style="color:#ef4444;">
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
          <span class="trade-expanded-loading">Trade-Details und Screenshots werden geladen ...</span>
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
        `<span class="trade-expanded-error">Details konnten nicht geladen werden: ${TradeDetail.escapeHtml(err.message)}</span>`;
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
      ? `${partials.reduce((sum, item) => sum + Number(item.volume || 0), 0).toFixed(2)} lots in ${partials.length} Teilprofit(en)`
      : 'Keine Teilprofite erfasst';

    const screenshotMarkup = screenshots.length
      ? `<div class="trade-expanded-screenshot-grid">${screenshots.map((screenshot, index) => `
          <button type="button" class="trade-expanded-screenshot" data-screenshot-index="${index}" title="Screenshot im Karussell öffnen">
            <img src="${escape(screenshot.image_url)}" alt="${escape(screenshot.caption || 'Trade Screenshot')}" loading="lazy">
            <span>${escape(screenshot.caption || 'TradingView')}</span>
          </button>`).join('')}</div>`
      : '<div class="trade-expanded-empty">Noch keine Screenshots für diesen Trade.</div>';

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

    return `
      <div class="trade-expanded-header">
        <div>
          <strong>${escape(trade.symbol)} · ${escape(trade.direction)}</strong>
          <span>${escape(trade.ticket || 'Ohne Ticket')}</span>
        </div>
        <button type="button" class="btn btn-secondary btn-sm" data-open-trade-detail>📊 Vollständige Details</button>
      </div>
      <div class="trade-expanded-grid">
        <div><span>Open / Close</span><strong>${escape(trade.open_time || '—')} → ${escape(exitText)}</strong></div>
        <div><span>Net P&L / Status</span><strong class="${pnlDisplayClass}">${pnlText} · ${escape(trade.status || '—')}</strong></div>
        <div><span>Setup / Mistake</span><strong>${escape(trade.setup_name || '—')} / ${escape(trade.mistake_name || '—')}</strong></div>
        <div><span>Beschriftung / Notiz</span><strong>${escape(trade.notes || 'Keine Notiz')}</strong></div>
      </div>
      <div class="trade-expanded-section">
        <div class="trade-expanded-section-title">Teilprofite <span>${escape(partialSummary)}</span></div>
        ${partialMarkup}
      </div>
      <div class="trade-expanded-section">
        <div class="trade-expanded-section-title">Screenshots <span>${screenshots.length} Bild(er) · Klick zum Öffnen</span></div>
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
    document.getElementById('tfOpenTime').value = nowStr;
    document.getElementById('tfCloseTime').value = nowStr;

    // Populate accounts select
    const accSelect = document.getElementById('tfAccount');
    accSelect.innerHTML = '';
    (App.accounts || []).forEach(a => {
      const opt = document.createElement('option');
      opt.value = a.id;
      opt.textContent = `${a.name} (${a.platform})`;
      accSelect.appendChild(opt);
    });

    // Populate setup and mistakes
    const setupSelect = document.getElementById('tfSetup');
    setupSelect.innerHTML = '<option value="">-- No Setup --</option>';
    (App.playbooks || []).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name;
      setupSelect.appendChild(opt);
    });

    const mistakeSelect = document.getElementById('tfMistake');
    mistakeSelect.innerHTML = '<option value="">-- No Mistake --</option>';
    (App.mistakes || []).forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.name;
      mistakeSelect.appendChild(opt);
    });

    document.getElementById('addTradeModal').classList.add('active');
  },

  async openEditModal(tradeId) {
    this.activeEditingId = tradeId;
    document.getElementById('tradeModalTitle').textContent = 'Edit Trade';

    try {
      const trade = await API.getTrade(tradeId);
      
      this.openAddModal(); // sets up dropdowns
      document.getElementById('tradeModalTitle').textContent = 'Edit Trade';
      this.activeEditingId = tradeId;

      document.getElementById('tfAccount').value = trade.account_id;
      document.getElementById('tfSymbol').value = trade.symbol;
      document.getElementById('tfDirection').value = trade.direction;
      if (document.getElementById('tfStatus')) {
        document.getElementById('tfStatus').value = trade.status || 'AUTO';
      }
      document.getElementById('tfVolume').value = trade.volume;
      document.getElementById('tfOpenPrice').value = trade.open_price;
      document.getElementById('tfClosePrice').value = trade.close_price || '';
      document.getElementById('tfStopLoss').value = trade.stop_loss || '';
      document.getElementById('tfTakeProfit').value = trade.take_profit || '';
      document.getElementById('tfNetProfit').value = trade.net_profit || 0;
      document.getElementById('tfCommission').value = trade.commission || 0;
      document.getElementById('tfSwap').value = trade.swap || 0;
      document.getElementById('tfOpenTime').value = (trade.open_time || '').substring(0, 16);
      document.getElementById('tfCloseTime').value = (trade.close_time || '').substring(0, 16);
      document.getElementById('tfSetup').value = trade.setup_id || '';
      document.getElementById('tfMistake').value = trade.mistake_id || '';
      document.getElementById('tfNotes').value = trade.notes || '';
    } catch (err) {
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  closeModal() {
    document.getElementById('addTradeModal').classList.remove('active');
  },

  async saveTradeFromForm(e) {
    e.preventDefault();

    const account_id = parseInt(document.getElementById('tfAccount').value);
    const symbol = document.getElementById('tfSymbol').value.toUpperCase().trim();
    const direction = document.getElementById('tfDirection').value;
    const selectedStatus = document.getElementById('tfStatus') ? document.getElementById('tfStatus').value : 'AUTO';
    const volume = parseFloat(document.getElementById('tfVolume').value);
    const open_price = parseFloat(document.getElementById('tfOpenPrice').value);
    const close_price = document.getElementById('tfClosePrice').value ? parseFloat(document.getElementById('tfClosePrice').value) : null;
    const stop_loss = document.getElementById('tfStopLoss').value ? parseFloat(document.getElementById('tfStopLoss').value) : null;
    const take_profit = document.getElementById('tfTakeProfit').value ? parseFloat(document.getElementById('tfTakeProfit').value) : null;
    const net_profit = parseFloat(document.getElementById('tfNetProfit').value || 0);
    const commission = parseFloat(document.getElementById('tfCommission').value || 0);
    const swap = parseFloat(document.getElementById('tfSwap').value || 0);

    let status = selectedStatus;
    if (selectedStatus === 'AUTO') {
      if (!close_price && !document.getElementById('tfCloseTime').value) {
        status = 'OPEN';
      } else {
        status = net_profit > 0.001 ? 'WIN' : (net_profit < -0.001 ? 'LOSS' : 'BE');
      }
    }

    const open_time = document.getElementById('tfOpenTime').value.replace('T', ' ');
    const close_time_val = document.getElementById('tfCloseTime').value;
    const close_time = close_time_val ? close_time_val.replace('T', ' ') : (['PENDING', 'OPEN'].includes(status) ? null : open_time);
    const setup_id = document.getElementById('tfSetup').value ? parseInt(document.getElementById('tfSetup').value) : null;
    const mistake_id = document.getElementById('tfMistake').value ? parseInt(document.getElementById('tfMistake').value) : null;
    const notes = document.getElementById('tfNotes').value;

    const payload = {
      account_id, symbol, direction, volume, open_price, close_price,
      stop_loss, take_profit, net_profit, commission, swap,
      open_time, close_time, setup_id, mistake_id, notes,
      status: status
    };

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
      Dashboard.load();
    } catch (err) {
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  async deleteTrade(tradeId) {
    if (!confirm('Are you sure you want to delete this trade?')) return;
    try {
      await API.deleteTrade(tradeId);
      App.showToast('Trade deleted successfully.', 'success');
      this.load();
      Dashboard.load();
    } catch (err) {
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  exportCSV() {
    const acc = App.activeAccountId ? `?account_id=${App.activeAccountId}` : '';
    window.location.href = `/api/trades/export/csv${acc}`;
  }
};
