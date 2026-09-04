/**
 * API Client for Trading Journal Server
 */
const API = {
  baseUrl: '',

  async request(endpoint, options = {}) {
    try {
      const res = await fetch(`${this.baseUrl}${endpoint}`, {
        headers: {
          'Content-Type': 'application/json',
          ...(options.headers || {})
        },
        ...options
      });

      if (!res.ok) {
        let errMessage = `HTTP error ${res.status}`;
        try {
          const errData = await res.json();
          if (errData.detail) errMessage = errData.detail;
        } catch (e) {}
        throw new Error(errMessage);
      }

      // Check if response is JSON
      const contentType = res.headers.get('content-type');
      if (contentType && contentType.includes('application/json')) {
        return await res.json();
      }
      return await res.text();
    } catch (err) {
      console.error(`API Error on ${endpoint}:`, err);
      throw err;
    }
  },

  // Accounts
  getAccounts() { return this.request('/api/accounts'); },
  createAccount(data) { return this.request('/api/accounts', { method: 'POST', body: JSON.stringify(data) }); },
  updateAccount(id, data) { return this.request(`/api/accounts/${id}`, { method: 'PUT', body: JSON.stringify(data) }); },
  deleteAccount(id) { return this.request(`/api/accounts/${id}`, { method: 'DELETE' }); },
  regenerateApiKey(id) { return this.request(`/api/accounts/${id}/regenerate-key`, { method: 'POST' }); },

  // Trades
  getTrades(params = {}) {
    const q = new URLSearchParams(params).toString();
    return this.request(`/api/trades?${q}`);
  },
  getTrade(id) { return this.request(`/api/trades/${id}`); },
  createTrade(data) { return this.request('/api/trades', { method: 'POST', body: JSON.stringify(data) }); },
  updateTrade(id, data) { return this.request(`/api/trades/${id}`, { method: 'PUT', body: JSON.stringify(data) }); },
  deleteTrade(id) { return this.request(`/api/trades/${id}`, { method: 'DELETE' }); },

  // Dashboard & Analytics
  getDashboard(params = {}) {
    const q = new URLSearchParams(params).toString();
    return this.request(`/api/dashboard?${q}`);
  },
  getAnalyticsOverview(params = {}) {
    const q = new URLSearchParams(params).toString();
    return this.request(`/api/analytics/overview?${q}`);
  },

  // Playbooks & Mistakes
  getPlaybooks() { return this.request('/api/playbooks'); },
  createPlaybook(data) { return this.request('/api/playbooks', { method: 'POST', body: JSON.stringify(data) }); },
  deletePlaybook(id) { return this.request(`/api/playbooks/${id}`, { method: 'DELETE' }); },

  getMistakes() { return this.request('/api/mistakes'); },
  createMistake(data) { return this.request('/api/mistakes', { method: 'POST', body: JSON.stringify(data) }); },
  deleteMistake(id) { return this.request(`/api/mistakes/${id}`, { method: 'DELETE' }); },

  // Chart data for TradingView Lightweight Charts
  getChartData(tradeId, tf = 'M15', bars = 120) {
    return this.request(`/api/sync/chart-data/${tradeId}?timeframe=${tf}&bars=${bars}`);
  },

  // Sync & Import
  syncCTrader(data) {
    return this.request('/api/sync/ctrader', { method: 'POST', body: JSON.stringify(data) });
  },
  syncMTDirect(data) {
    return this.request('/api/sync/mt-direct', { method: 'POST', body: JSON.stringify(data) });
  },
  async importStatement(formData) {
    const res = await fetch('/api/sync/import', {
      method: 'POST',
      body: formData
    });
    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Import failed');
    }
    return await res.json();
  }
};
