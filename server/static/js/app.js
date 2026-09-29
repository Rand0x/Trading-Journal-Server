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
  datePreset: 'all',
  viewTitles: {
    dashboard: 'Dashboard', trades: 'Trade Log', analytics: 'Analytics',
    playbooks: 'Playbooks', review: 'Weekly Review', accounts: 'Accounts & Sync',
  },
  presetLabels: {
    all: 'All time', today: 'Today', week: 'This week', month: 'This month',
    '30days': 'Last 30 days', '90days': 'Last 90 days', year: 'Year to date',
  },
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

    const title = document.getElementById('topbarTitle');
    if (title) title.textContent = this.viewTitles[viewName] || '';
    if (document.title !== undefined) document.title = `${this.viewTitles[viewName] || 'Dashboard'} · Trading Journal`;
    this.toggleSidebar(false);

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
    if (initialRoute === 'trades') {
      this.applyTradeQuery(query);
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
      let searchChanged = false;
      if (route === 'trades') {
        searchChanged = this.applyTradeQuery(query);
      }
      if (this.currentView !== route) {
        this.navigateTo(route, false);
      } else if (searchChanged) {
        this.refreshCurrentView();
      }
    };

    window.addEventListener('popstate', handleLocationChange);
    window.addEventListener('hashchange', handleLocationChange);

    // Global Account Filter
    const accSelect = document.getElementById('globalAccountSelect');
    if (accSelect) {
      accSelect.addEventListener('change', (e) => {
        this.activeAccountId = e.target.value ? parseInt(e.target.value) : null;
        this.updateSidebarAccount();
        this.refreshCurrentView();
      });
    }

    // Global Date Presets (segmented control)
    const presets = document.getElementById('globalDatePresets');
    if (presets) {
      presets.addEventListener('click', (e) => {
        const btn = e.target.closest('button[data-preset]');
        if (!btn) return;
        presets.querySelectorAll('button').forEach(b => b.classList.toggle('active', b === btn));
        this.applyDatePreset(btn.dataset.preset);
        this.refreshCurrentView();
      });
    }

    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') this.toggleSidebar(false);
    });

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
        // Top-level `const` modules are not properties of window.
        if (typeof Review !== 'undefined') Review.load();
        break;
    }
  },

  /**
   * Apply #trades?date=YYYY-MM-DD (realized-on-day filter) and ?search=...
   * Returns true when either filter changed.
   */
  applyTradeQuery(query) {
    let changed = false;
    const searchInput = document.getElementById('tradeSearchInput');
    const expectedSearch = query.search || '';
    if (searchInput && searchInput.value !== expectedSearch) {
      searchInput.value = expectedSearch;
      changed = true;
    }
    // ?date=YYYY-MM-DD (one day) or ?from=...&to=... (e.g. a calendar week)
    const from = query.date || query.from || '';
    const to = query.date || query.to || from;
    const expected = !from ? '' : (from === to ? from : `${from}..${to}`);
    if (typeof Trades !== 'undefined' && Trades.closedOnFilter !== expected) {
      Trades.setClosedRange(from, to);
      changed = true;
    }
    return changed;
  },

  navigateToTradesWithDate(dateStr) {
    this.navigateToTradesWithRange(dateStr, dateStr);
  },

  navigateToTradesWithRange(from, to) {
    const single = from && (!to || to === from);
    this.applyTradeQuery(single ? { date: from } : { from: from || '', to: to || '' });
    const targetHash = !from ? '#trades'
      : single ? `#trades?date=${encodeURIComponent(from)}`
        : `#trades?from=${encodeURIComponent(from)}&to=${encodeURIComponent(to)}`;
    if (window.location.hash !== targetHash) {
      history.pushState({ view: 'trades', from, to }, '', targetHash);
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
    // Local calendar dates (toISOString would shift the day across timezones).
    const ymd = d => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    const daysAgo = n => new Date(now.getFullYear(), now.getMonth(), now.getDate() - n);
    this.datePreset = this.presetLabels[preset] ? preset : 'all';
    this.dateFrom = null;
    this.dateTo = null;

    if (preset === 'today') {
      this.dateFrom = ymd(now);
      this.dateTo = this.dateFrom;
    } else if (preset === 'week') {
      this.dateFrom = ymd(daysAgo((now.getDay() + 6) % 7)); // Monday
    } else if (preset === 'month') {
      this.dateFrom = ymd(new Date(now.getFullYear(), now.getMonth(), 1));
    } else if (preset === '30days') {
      this.dateFrom = ymd(daysAgo(30));
    } else if (preset === '90days') {
      this.dateFrom = ymd(daysAgo(90));
    } else if (preset === 'year') {
      this.dateFrom = `${now.getFullYear()}-01-01`;
    }
  },

  getPeriodLabel() {
    return this.presetLabels[this.datePreset] || 'All time';
  },

  toggleSidebar(force) {
    if (typeof document === 'undefined' || !document.body || !document.body.classList) return;
    const open = force === undefined ? !document.body.classList.contains('sidebar-open') : force;
    document.body.classList.toggle('sidebar-open', open);
  },

  updateSidebarAccount() {
    const nameEl = document.getElementById('sidebarAccountName');
    const metaEl = document.getElementById('sidebarAccountMeta');
    if (!nameEl || !metaEl) return;
    const acc = this.getActiveAccount();
    if (acc) {
      nameEl.textContent = acc.name || 'Account';
      metaEl.textContent = [acc.platform, acc.broker, acc.currency].filter(Boolean).join(' · ');
    } else {
      const count = (this.accounts || []).length;
      nameEl.textContent = 'All accounts';
      metaEl.textContent = `${count} account${count === 1 ? '' : 's'} · data stays on this server`;
    }
  },

  showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    const icon = document.createElement('span');
    icon.textContent = type === 'success' ? '✓' : (type === 'error' ? '✕' : 'ℹ');
    const text = document.createElement('span');
    text.textContent = message;
    toast.append(icon, text);

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
