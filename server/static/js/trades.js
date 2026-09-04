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
    tbody.innerHTML = '';

    if (trades.length === 0) {
      tbody.innerHTML = '<tr><td colspan="12" style="text-align:center;padding:30px;color:#6b7280;">No trades match your filter criteria.</td></tr>';
      return;
    }

    trades.forEach(t => {
      const tr = document.createElement('tr');
      const pnl = parseFloat(t.net_profit || 0);
      const isWin = pnl > 0.001;
      const isLoss = pnl < -0.001;

      const pnlFormatted = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
      const pnlClass = isWin ? 'color-green' : (isLoss ? 'color-red' : 'color-muted');

      const dirClass = t.direction === 'BUY' ? 'badge-buy' : 'badge-sell';
      const statusClass = t.status === 'WIN' ? 'badge-win' : (t.status === 'LOSS' ? 'badge-loss' : 'badge-be');

      const setupBadge = t.setup_name ? `<span class="badge badge-setup">${t.setup_name}</span>` : '<span style="color:#4b5563;">—</span>';
      const mistakeBadge = t.mistake_name ? `<span class="badge badge-mistake">${t.mistake_name}</span>` : '<span style="color:#4b5563;">—</span>';

      tr.innerHTML = `
        <td style="font-weight:600;color:#fff;">${t.open_time ? t.open_time.substring(0, 16).replace('T', ' ') : ''}</td>
        <td><strong style="color:#60a5fa;">${t.symbol}</strong></td>
        <td><span class="badge ${dirClass}">${t.direction}</span></td>
        <td>${t.volume}</td>
        <td>${t.open_price}</td>
        <td>${t.close_price || 'Open'}</td>
        <td style="font-size:12px;color:#9ca3af;">
          ${t.stop_loss ? `SL: ${t.stop_loss}` : ''} 
          ${t.take_profit ? `<br>TP: ${t.take_profit}` : ''}
        </td>
        <td style="font-weight:700;" class="${pnlClass}">${pnlFormatted}</td>
        <td><span class="badge ${statusClass}">${t.status}</span></td>
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
      tbody.appendChild(tr);
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
    const volume = parseFloat(document.getElementById('tfVolume').value);
    const open_price = parseFloat(document.getElementById('tfOpenPrice').value);
    const close_price = document.getElementById('tfClosePrice').value ? parseFloat(document.getElementById('tfClosePrice').value) : null;
    const stop_loss = document.getElementById('tfStopLoss').value ? parseFloat(document.getElementById('tfStopLoss').value) : null;
    const take_profit = document.getElementById('tfTakeProfit').value ? parseFloat(document.getElementById('tfTakeProfit').value) : null;
    const net_profit = parseFloat(document.getElementById('tfNetProfit').value || 0);
    const commission = parseFloat(document.getElementById('tfCommission').value || 0);
    const swap = parseFloat(document.getElementById('tfSwap').value || 0);
    const open_time = document.getElementById('tfOpenTime').value.replace('T', ' ');
    const close_time = document.getElementById('tfCloseTime').value ? document.getElementById('tfCloseTime').value.replace('T', ' ') : open_time;
    const setup_id = document.getElementById('tfSetup').value ? parseInt(document.getElementById('tfSetup').value) : null;
    const mistake_id = document.getElementById('tfMistake').value ? parseInt(document.getElementById('tfMistake').value) : null;
    const notes = document.getElementById('tfNotes').value;

    const payload = {
      account_id, symbol, direction, volume, open_price, close_price,
      stop_loss, take_profit, net_profit, commission, swap,
      open_time, close_time, setup_id, mistake_id, notes,
      status: net_profit > 0.001 ? 'WIN' : (net_profit < -0.001 ? 'LOSS' : 'BE')
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
