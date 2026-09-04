/**
 * Accounts & Broker Synchronization Module
 * Manages MT4 / MT5 Expert Advisor setup, cTrader Open API sync, and Statement imports.
 */

const Accounts = {
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

      card.innerHTML = `
        <div class="playbook-card-header">
          <div>
            <span class="playbook-card-title">${a.name}</span>
            <span style="font-size:12px;color:#9ca3af;display:block;">${a.broker || 'Broker'} • ${a.account_number || 'N/A'}</span>
          </div>
          <span class="badge" style="background:#3b82f622;color:#60a5fa;border:1px solid #3b82f655;">
            ${a.platform}
          </span>
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

        <div style="background:#0f172a;padding:8px 12px;border-radius:6px;font-size:11px;display:flex;align-items:center;justify-content:space-between;border:1px solid #1e293b;">
          <span style="color:#6b7280;">API KEY:</span>
          <code style="color:#60a5fa;font-size:11px;">${a.api_key ? a.api_key.substring(0, 14) + '...' : 'None'}</code>
          <button class="btn btn-secondary btn-sm" onclick="Accounts.copyApiKey('${a.api_key}')" title="Copy full API Key">
            Copy
          </button>
        </div>

        <div style="display:flex;align-items:center;justify-content:space-between;font-size:11px;color:#6b7280;border-top:1px solid #1f2937;padding-top:10px;">
          <span>Last Sync: ${a.last_synced_at ? a.last_synced_at.substring(0, 16).replace('T', ' ') : 'Never'}</span>
          <button class="btn btn-secondary btn-sm" onclick="Accounts.deleteAccount(${a.id})" style="color:#ef4444;" title="Delete Account">
            Delete
          </button>
        </div>
      `;
      container.appendChild(card);
    });
  },

  updateGlobalAccountSelect(accounts = []) {
    const selects = [document.getElementById('globalAccountSelect'), document.getElementById('importAccountSelect'), document.getElementById('ctraderAccountSelect')];
    selects.forEach(sel => {
      if (!sel) return;
      const cur = sel.value;
      sel.innerHTML = sel.id === 'globalAccountSelect' ? '<option value="">All Accounts</option>' : '';
      accounts.forEach(a => {
        const opt = document.createElement('option');
        opt.value = a.id;
        opt.textContent = `${a.name} (${a.platform})`;
        if (cur && cur === String(a.id)) opt.selected = true;
        sel.appendChild(opt);
      });
    });
  },

  copyApiKey(key) {
    if (!key) return;
    navigator.clipboard.writeText(key).then(() => {
      App.showToast('API Key copied to clipboard!', 'success');
    }).catch(() => {
      prompt('Copy API Key:', key);
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
    const broker = document.getElementById('accBroker').value.trim();
    const platform = document.getElementById('accPlatform').value;
    const account_number = document.getElementById('accNumber').value.trim();
    const currency = document.getElementById('accCurrency').value.trim() || 'USD';
    const initial_balance = parseFloat(document.getElementById('accInitialBal').value || 10000);

    try {
      await API.createAccount({ name, broker, platform, account_number, currency, initial_balance });
      App.showToast('Account added successfully!', 'success');
      this.closeAddAccountModal();
      this.load();
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

  async triggerCTraderSync(e) {
    e.preventDefault();
    const account_id = parseInt(document.getElementById('ctraderAccountSelect').value);
    const client_id = document.getElementById('ctClientId').value.trim();
    const client_secret = document.getElementById('ctClientSecret').value.trim();
    const access_token = document.getElementById('ctAccessToken').value.trim();
    const ctrader_account_id = document.getElementById('ctAccountId').value.trim();

    const statusEl = document.getElementById('ctraderSyncStatus');
    statusEl.innerHTML = '<span style="color:#60a5fa;">Connecting to cTrader Open API...</span>';

    try {
      const res = await API.syncCTrader({
        account_id,
        client_id,
        client_secret,
        access_token,
        ctrader_account_id
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
