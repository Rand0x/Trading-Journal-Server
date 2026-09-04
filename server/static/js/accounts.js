/**
 * Accounts & Broker Synchronization Module
 * Local Expert/cBot push synchronization and Open API synchronization for cTrader.
 */

const Accounts = {
  formatSyncTime(value) {
    if (!value) return 'Never';

    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;

    const parts = new Intl.DateTimeFormat('de-DE', {
      timeZone: 'Europe/Berlin',
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      hour12: false
    }).formatToParts(date).reduce((result, part) => {
      result[part.type] = part.value;
      return result;
    }, {});

    return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}`;
  },

  async load() {
    try {
      const accounts = await API.getAccounts();
      App.accounts = accounts;
      this.renderAccounts(accounts);
      this.updateGlobalAccountSelect(accounts);
    } catch (err) {
      console.error('Failed to load accounts:', err);
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  renderAccounts(accounts = []) {
    const container = document.getElementById('accountsListContainer');
    if (!container) return;
    container.innerHTML = '';

    accounts.forEach(a => {
      const card = document.createElement('div');
      card.className = 'playbook-card';
      const isProfitable = (a.equity || a.current_balance) >= a.initial_balance;
      const profitDiff = (a.equity || a.current_balance) - a.initial_balance;

      const isMT = a.platform === 'MT4' || a.platform === 'MT5';
      const isCTrader = a.platform === 'cTrader';
      const hasLocalPushSync = isMT || isCTrader;

      card.innerHTML = `
        <div class="playbook-card-header">
          <div>
            <span class="playbook-card-title">${a.name}</span>
            <span style="font-size:12px;color:#9ca3af;display:block;">
              ${a.broker || 'Broker'} • ID: <strong style="color:#60a5fa;">${a.account_number || 'N/A'}</strong>
              ${a.server_name ? ` • Server: <em>${a.server_name}</em>` : ''}
            </span>
          </div>
          <div style="display:flex;gap:6px;align-items:center;">
            <span class="badge" style="background:#3b82f622;color:#60a5fa;border:1px solid #3b82f655;">
              ${a.platform}
            </span>
            ${isMT ? '<span class="badge" style="background:#10b98122;color:#10b981;border:1px solid #10b98155;" title="Data is pushed by the installed Expert Advisor">EA Sync</span>' : ''}
            ${isCTrader ? '<span class="badge" style="background:#10b98122;color:#10b981;border:1px solid #10b98155;" title="A locally running cBot can push account data to the journal">cBot Ready</span>' : ''}
            ${isCTrader && a.auto_sync_enabled ? '<span class="badge" style="background:#10b98122;color:#10b981;border:1px solid #10b98155;" title="cTrader Auto-Sync enabled">Auto-Sync</span>' : ''}
          </div>
        </div>

        <div style="display:grid;grid-template-columns:repeat(2, 1fr);gap:10px;margin-top:4px;">
          <div style="background:#0a0e17;padding:10px;border-radius:6px;">
            <span style="font-size:11px;color:#6b7280;display:block;">BALANCE</span>
            <span style="font-size:16px;font-weight:700;color:#fff;">$${(a.current_balance || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
          </div>
          <div style="background:#0a0e17;padding:10px;border-radius:6px;">
            <span style="font-size:11px;color:#6b7280;display:block;">EQUITY</span>
            <span style="font-size:16px;font-weight:700;color:#fff;">$${(a.equity || 0).toLocaleString('en-US', { minimumFractionDigits: 2 })}</span>
          </div>
        </div>

        <div style="font-size:12px;display:flex;justify-content:space-between;color:#9ca3af;">
          <span>Initial: $${(a.initial_balance || 0).toLocaleString()}</span>
          <span style="font-weight:700;" class="${isProfitable ? 'color-green' : 'color-red'}">
            ${isProfitable ? '+' : ''}$${profitDiff.toFixed(2)} (${((profitDiff / (a.initial_balance || 1)) * 100).toFixed(1)}%)
          </span>
        </div>

        <div style="display:flex;align-items:center;justify-content:space-between;background:#0f172a;padding:8px 12px;border-radius:6px;border:1px solid #1e293b;">
          <div style="font-size:11px;color:#9ca3af;">
            <span>Last Synced: <strong>${Accounts.formatSyncTime(a.last_synced_at)}</strong></span>
          </div>
          ${isCTrader ? `
            <button class="btn btn-primary btn-sm" onclick="Accounts.triggerCTraderSyncForAccount(${a.id})" title="Fetch account data with the configured cTrader Open API credentials">
              ⚡ Sync Now
            </button>
          ` : ''}
        </div>

        ${hasLocalPushSync ? `
          <div style="margin-top:10px;padding:9px 10px;background:#0a0e17;border:1px solid #1e293b;border-radius:6px;font-size:11px;color:#9ca3af;display:flex;align-items:center;justify-content:space-between;gap:8px;">
            <span>Journal API Key (${isMT ? 'EA' : 'cBot'}): <code style="color:#c4b5fd;">${a.api_key || 'Unavailable'}</code></span>
            <button class="btn btn-secondary btn-sm" onclick="Accounts.copyApiKey('${a.api_key || ''}')" ${a.api_key ? '' : 'disabled'}>Copy</button>
          </div>
        ` : ''}

        <div style="display:flex;align-items:center;justify-content:space-between;font-size:11px;color:#6b7280;border-top:1px solid #1f2937;padding-top:10px;">
          <span>${isCTrader ? 'cTrader Open API or bundled cBot' : (isMT ? 'MetaTrader sync via bundled EA' : 'Manual account')}</span>
          <button class="btn btn-secondary btn-sm" onclick="Accounts.deleteAccount(${a.id})" style="color:#ef4444;" title="Delete Account">
            Delete
          </button>
        </div>
      `;
      container.appendChild(card);
    });
  },

  updateGlobalAccountSelect(accounts = []) {
    const selects = [
      document.getElementById('globalAccountSelect'),
      document.getElementById('importAccountSelect'),
      document.getElementById('ctraderAccountSelect')
    ];
    selects.forEach(sel => {
      if (!sel) return;
      const cur = sel.value;
      sel.innerHTML = sel.id === 'globalAccountSelect' ? '<option value="">All Accounts</option>' : '';
      accounts.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.id;
        opt.textContent = `${a.name} (${a.platform}) - #${a.account_number || a.id}`;
        if (cur && cur === String(a.id)) opt.selected = true;
        sel.appendChild(opt);
      });
    });
  },

  openAddAccountModal() {
    document.getElementById('accountForm').reset();
    document.getElementById('addAccountModal').classList.add('active');
  },

  closeAddAccountModal() {
    document.getElementById('addAccountModal').classList.remove('active');
  },

  async saveAccount(e) {
    e.preventDefault();
    const name = document.getElementById('accName').value.trim();
    const platform = document.getElementById('accPlatform').value;
    const account_number = document.getElementById('accNumber').value.trim();
    const server_name = document.getElementById('accServer').value.trim();
    // The account dialog has a server-name field, not a separate broker field.
    // Keep the optional lookup for compatibility with older/customized markup.
    const brokerField = document.getElementById('accBroker');
    const broker = brokerField ? brokerField.value.trim() : '';
    const currency = document.getElementById('accCurrency').value.trim() || 'USD';
    const initial_balance = parseFloat(document.getElementById('accInitialBal').value || 10000);

    try {
      const created = await API.createAccount({
        name,
        platform,
        account_number,
        server_name,
        broker: broker || server_name,
        currency,
        initial_balance,
        auto_sync_enabled: true,
        sync_interval_minutes: 5
      });

      App.showToast(`Account "${created.name}" created.`, 'success');
      this.closeAddAccountModal();
      await this.load();
    } catch (err) {
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  async deleteAccount(id) {
    if (!confirm('Are you sure you want to delete this account? All associated trades will be deleted!')) return;
    try {
      await API.deleteAccount(id);
      App.showToast('Account deleted.', 'success');
      this.load();
      Dashboard.load();
    } catch (err) {
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  async copyApiKey(apiKey) {
    if (!apiKey) return;
    try {
      await navigator.clipboard.writeText(apiKey);
      App.showToast('Journal API key copied.', 'success');
    } catch (err) {
      App.showToast('Could not copy the API key. Please copy it manually.', 'error');
    }
  },

  async triggerCTraderSyncForAccount(accountId) {
    App.showToast('Connecting to cTrader Open API...', 'info');
    try {
      const res = await API.syncCTrader({ account_id: accountId });
      if (res.status !== 'success') throw new Error(res.error || 'cTrader sync failed');
      App.showToast(res.message || 'cTrader sync completed successfully!', 'success');
      await this.load();
      await Dashboard.load();
      if (App.currentView === 'trades') Trades.load();
    } catch (err) {
      App.showToast(`cTrader sync error: ${err.message}`, 'error');
    }
  },

  async triggerCTraderSync(e) {
    e.preventDefault();
    const account_id = parseInt(document.getElementById('ctraderAccountSelect').value);
    const client_id = document.getElementById('ctClientId').value.trim();
    const client_secret = document.getElementById('ctClientSecret').value.trim();
    const access_token = document.getElementById('ctAccessToken').value.trim();
    const ctrader_account_id = document.getElementById('ctAccountId').value.trim();
    const is_live = document.getElementById('ctEnvironment').value === 'true';

    const statusEl = document.getElementById('ctraderSyncStatus');
    statusEl.innerHTML = '<span style="color:#60a5fa;">Connecting to cTrader Open API...</span>';

    try {
      const res = await API.syncCTrader({
        account_id,
        client_id,
        client_secret,
        access_token,
        ctrader_account_id,
        is_live
      });
      statusEl.innerHTML = `<span style="color:#10b981;">✓ ${res.message || 'Sync successful!'} Balance: $${res.balance}</span>`;
      App.showToast('cTrader synced successfully!', 'success');
      this.load();
      Dashboard.load();
    } catch (err) {
      statusEl.innerHTML = `<span style="color:#ef4444;">✗ Sync failed: ${err.message}</span>`;
      App.showToast(`cTrader sync error: ${err.message}`, 'error');
    }
  },

  async handleFileUpload(file) {
    if (!file) return;
    const account_id = document.getElementById('importAccountSelect').value;
    if (!account_id) {
      App.showToast('Please select a target account for the import.', 'error');
      return;
    }

    const formData = new FormData();
    formData.append('file', file);
    formData.append('account_id', account_id);

    const statusEl = document.getElementById('importFileStatus');
    statusEl.innerHTML = `<span style="color:#60a5fa;">Parsing and importing "${file.name}"...</span>`;

    try {
      const res = await API.importStatement(formData);
      statusEl.innerHTML = `<span style="color:#10b981;">✓ ${res.message}</span>`;
      App.showToast(res.message, 'success');
      Dashboard.load();
      Trades.load();
      Accounts.load();
    } catch (err) {
      statusEl.innerHTML = `<span style="color:#ef4444;">✗ Import failed: ${err.message}</span>`;
      App.showToast(`Import error: ${err.message}`, 'error');
    }
  }
};
