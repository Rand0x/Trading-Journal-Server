/**
 * Master Application Orchestrator
 * Single Page App Navigation, Filters, and Lifecycle
 */

const App = {
  currentView: 'dashboard',
  validRoutes: ['dashboard', 'trades', 'analytics', 'playbooks', 'review', 'accounts'],
  activeAccountId: null,
  dateFrom: null,
  dateTo: null,
  accounts: [],
  playbooks: [],
  mistakes: [],

  getCurrencySymbol(currency) {
    const c = (currency || 'USD').toUpperCase().trim();
    switch (c) {
      case 'USD': return '$';
      case 'EUR': return '€';
      case 'GBP': return '£';
      case 'JPY': return '¥';
      case 'CHF': return 'CHF ';
      case 'AUD': return 'A$';
      case 'CAD': return 'C$';
      default: return c ? `${c} ` : '$';
    }
  },

  getActiveAccount() {
    if (!this.activeAccountId) return null;
    return (this.accounts || []).find(a => a.id === this.activeAccountId) || null;
  },

  getActiveCurrency() {
    const acc = this.getActiveAccount();
    if (acc && acc.currency) {
      return acc.currency.toUpperCase().trim();
    }
    if (this.accounts && this.accounts.length > 0) {
      const currencies = [...new Set(this.accounts.map(a => (a.currency || 'USD').toUpperCase().trim()))];
      if (currencies.length === 1) {
        return currencies[0];
      }
    }
    return 'USD';
  },

  getActiveCurrencySymbol() {
    return this.getCurrencySymbol(this.getActiveCurrency());
  },

  formatMoney(amount, currency = null, options = {}) {
    const val = Number(amount || 0);
    const cur = currency || this.getActiveCurrency();
    const sym = this.getCurrencySymbol(cur);
    const decimals = options.decimals !== undefined ? options.decimals : 2;
    const absVal = Math.abs(val);
    const numStr = absVal.toLocaleString('en-US', {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals
    });

    if (options.absolute) {
      return `${sym}${numStr}`;
    }
    if (val < -0.0001) {
      return `-${sym}${numStr}`;
    }
    if (options.showSign && val > 0.0001) {
      return `+${sym}${numStr}`;
    }
    return `${sym}${numStr}`;
  },

  getRouteFromUrl() {
    // 1. Check hash first: e.g. #trades, #/trades, #trades?date=...
    const hash = window.location.hash || '';
    if (hash) {
      const cleanHash = hash.replace(/^#\/?/, '').split('?')[0].trim().toLowerCase();
      if (this.validRoutes.includes(cleanHash)) {
        return cleanHash;
      }
    }

    // 2. Check path fallback: e.g. /trades, /analytics
    const path = window.location.pathname.replace(/^\//, '').split('/')[0].trim().toLowerCase();
    if (this.validRoutes.includes(path)) {
      return path;
    }

    return 'dashboard';
  },

  getQueryParamsFromHash() {
    const hash = window.location.hash || '';
    const qIndex = hash.indexOf('?');
    if (qIndex === -1) {
      if (window.location.search) {
        return Object.fromEntries(new URLSearchParams(window.location.search));
      }
      return {};
    }
    return Object.fromEntries(new URLSearchParams(hash.substring(qIndex + 1)));
  },

  switchActiveViewDom(viewName) {
    if (!this.validRoutes.includes(viewName)) {
      viewName = 'dashboard';
    }
    this.currentView = viewName;

    // Update sidebar navigation
    document.querySelectorAll('.nav-item').forEach(item => {
      const link = item.querySelector('a');
      item.classList.toggle('active', link && link.dataset.view === viewName);
    });

    // Switch view containers
    document.querySelectorAll('.view-container').forEach(v => {
      v.classList.toggle('active', v.id === `view-${viewName}`);
    });

    if (viewName !== 'trades' && typeof Trades !== 'undefined' && Trades.stopAutoRefresh) {
      Trades.stopAutoRefresh();
    }
    if (viewName !== 'dashboard' && typeof Dashboard !== 'undefined' && Dashboard.stopAutoRefresh) {
      Dashboard.stopAutoRefresh();
    }
    if (viewName !== 'accounts' && typeof Accounts !== 'undefined' && Accounts.stopAutoRefresh) {
      Accounts.stopAutoRefresh();
    }
    if (viewName !== 'review' && typeof Review !== 'undefined' && Review.stopAutoRefresh) {
      Review.stopAutoRefresh();
    }
  },

  async init() {
    console.log('Initializing Trading Journal...');
    this.setupEventListeners();

    const initialRoute = this.getRouteFromUrl();
    this.switchActiveViewDom(initialRoute);

    await Accounts.load();
    await Playbooks.load();

    const query = this.getQueryParamsFromHash();
    if (initialRoute === 'trades' && (query.date || query.search)) {
      const searchInput = document.getElementById('tradeSearchInput');
      if (searchInput) {
        searchInput.value = query.date || query.search;
      }
    }

    const currentHashClean = (window.location.hash || '').replace(/^#\/?/, '').split('?')[0].trim().toLowerCase();
    if (currentHashClean !== initialRoute) {
      const queryStr = window.location.hash.includes('?')
        ? window.location.hash.substring(window.location.hash.indexOf('?'))
        : (window.location.search || '');
      history.replaceState({ view: initialRoute }, '', `#${initialRoute}${queryStr}`);
    }

    this.navigateTo(initialRoute, false);
  },

  setupEventListeners() {
    // Navigation links
    document.querySelectorAll('.nav-item a').forEach(el => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        const targetView = el.dataset.view;
        if (targetView) this.navigateTo(targetView);
      });
    });

    // Handle browser back/forward and URL hash changes
    const handleLocationChange = () => {
      const route = this.getRouteFromUrl();
      const query = this.getQueryParamsFromHash();
      if (route === 'trades') {
        const searchInput = document.getElementById('tradeSearchInput');
        if (searchInput) {
          const expectedSearch = query.date || query.search || '';
          if (searchInput.value !== expectedSearch) {
            searchInput.value = expectedSearch;
          }
        }
      }
      if (this.currentView !== route) {
        this.navigateTo(route, false);
      }
    };

    window.addEventListener('popstate', handleLocationChange);
    window.addEventListener('hashchange', handleLocationChange);

    // Global Account Filter
    const accSelect = document.getElementById('globalAccountSelect');
    if (accSelect) {
      accSelect.addEventListener('change', (e) => {
        this.activeAccountId = e.target.value ? parseInt(e.target.value) : null;
        this.refreshCurrentView();
      });
    }

    // Global Date Presets
    const datePreset = document.getElementById('globalDatePreset');
    if (datePreset) {
      datePreset.addEventListener('change', (e) => {
        this.applyDatePreset(e.target.value);
        this.refreshCurrentView();
      });
    }

    // Drag and drop setup for file imports
    const dropzone = document.getElementById('importDropzone');
    const fileInput = document.getElementById('importFileInput');
    if (dropzone && fileInput) {
      dropzone.addEventListener('click', () => fileInput.click());
      fileInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) Accounts.handleFileUpload(e.target.files[0]);
      });

      ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          dropzone.classList.add('dragover');
        });
      });

      ['dragleave', 'drop'].forEach(eventName => {
        dropzone.addEventListener(eventName, (e) => {
          e.preventDefault();
          dropzone.classList.remove('dragover');
        });
      });

      dropzone.addEventListener('drop', (e) => {
        const dt = e.dataTransfer;
        if (dt.files && dt.files.length > 0) {
          Accounts.handleFileUpload(dt.files[0]);
        }
      });
    }
  },

  navigateTo(viewName, updateUrl = true) {
    if (!this.validRoutes.includes(viewName)) {
      viewName = 'dashboard';
    }

    if (updateUrl) {
      const targetHash = `#${viewName}`;
      if (window.location.hash !== targetHash && window.location.hash !== `#/${viewName}`) {
        history.pushState({ view: viewName }, '', targetHash);
      }
    }

    this.switchActiveViewDom(viewName);
    this.refreshCurrentView();
  },

  refreshCurrentView() {
    switch (this.currentView) {
      case 'dashboard':
        Dashboard.load();
        break;
      case 'trades':
        Trades.load();
        break;
      case 'analytics':
        Analytics.load();
        break;
      case 'playbooks':
        Playbooks.load();
        break;
      case 'accounts':
        Accounts.load();
        break;
      case 'review':
        if (window.Review) Review.load();
        break;
    }
  },

  navigateToTradesWithDate(dateStr) {
    const searchInput = document.getElementById('tradeSearchInput');
    if (searchInput) {
      searchInput.value = dateStr || '';
    }
    const targetHash = dateStr ? `#trades?date=${encodeURIComponent(dateStr)}` : '#trades';
    if (window.location.hash !== targetHash) {
      history.pushState({ view: 'trades', date: dateStr }, '', targetHash);
    }
    this.navigateTo('trades', false);
  },

  getFilterParams() {
    const params = {};
    if (this.activeAccountId) params.account_id = this.activeAccountId;
    if (this.dateFrom) params.date_from = this.dateFrom;
    if (this.dateTo) params.date_to = this.dateTo;
    return params;
  },

  applyDatePreset(preset) {
    const now = new Date();
    this.dateFrom = null;
    this.dateTo = null;

    if (preset === 'today') {
      this.dateFrom = now.toISOString().substring(0, 10);
      this.dateTo = this.dateFrom;
    } else if (preset === 'week') {
      const firstDay = new Date(now.setDate(now.getDate() - now.getDay()));
      this.dateFrom = firstDay.toISOString().substring(0, 10);
    } else if (preset === 'month') {
      this.dateFrom = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-01`;
    } else if (preset === '30days') {
      const past = new Date(Date.now() - 30 * 24 * 3600 * 1000);
      this.dateFrom = past.toISOString().substring(0, 10);
    }
  },

  showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.innerHTML = `
      <span>${type === 'success' ? '✓' : (type === 'error' ? '✗' : 'ℹ')}</span>
      <span>${message}</span>
    `;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateX(100%)';
      toast.style.transition = 'all 0.2s ease';
      setTimeout(() => toast.remove(), 200);
    }, 3500);
  }
};

window.addEventListener('DOMContentLoaded', () => {
  App.init();
});
