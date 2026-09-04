/**
 * Master Application Orchestrator
 * Single Page App Navigation, Filters, and Lifecycle
 */

const App = {
  currentView: 'dashboard',
  activeAccountId: null,
  dateFrom: null,
  dateTo: null,
  accounts: [],
  playbooks: [],
  mistakes: [],

  async init() {
    console.log('Initializing Trading Journal...');
    this.setupEventListeners();
    await Accounts.load();
    await Playbooks.load();
    this.navigateTo('dashboard');
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

  navigateTo(viewName) {
    this.currentView = viewName;

    // Update sidebar navigation
    document.querySelectorAll('.nav-item').forEach(item => {
      const link = item.querySelector('a');
      item.classList.toggle('active', link && link.dataset.view === viewName);
    });

    // Switch view containers
    document.querySelectorAll('.view-container').forEach(v => {
      v.classList.remove('active');
    });

    const activeView = document.getElementById(`view-${viewName}`);
    if (activeView) activeView.classList.add('active');

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
    }
  },

  navigateToTradesWithDate(dateStr) {
    this.navigateTo('trades');
    const searchInput = document.getElementById('tradeSearchInput');
    if (searchInput) {
      searchInput.value = dateStr;
      Trades.load();
    }
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
