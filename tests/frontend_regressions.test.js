const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function harness(elements = {}) {
  const events = {};
  const timers = new Map();
  let timerId = 0;
  const context = vm.createContext({
    console, URLSearchParams,
    document: {
      getElementById: id => elements[id] || null,
      querySelector: () => null,
      querySelectorAll: () => [],
      addEventListener() {},
    },
    window: {
      location: { hash: '#trades', pathname: '/', search: '' },
      addEventListener: (name, callback) => { events[name] = callback; },
    },
    setInterval: callback => { timers.set(++timerId, callback); return timerId; },
    clearInterval: id => timers.delete(id),
    API: {},
    App: { currentView: 'trades', getFilterParams: () => ({ account_id: 7, date_from: '2026-01-01' }) },
  });
  function load(file, name) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, '../server/static/js', file), 'utf8'), context, { filename: file });
    return vm.runInContext(name, context);
  }
  return { context, events, timers, load };
}

function detailHarness() {
  const elements = {
    tradeDetailModal: { classList: { contains: () => true } },
    tdPnl: { textContent: '+USD 30' }, tdExitPrice: {},
    tdPreNotesInput: { value: 'unsaved note' },
  };
  const h = harness(elements);
  h.context.App.getActiveCurrency = () => 'USD';
  h.context.App.formatMoney = (value, currency) => `${currency} ${value}`;
  const detail = h.load('trade_detail.js', 'TradeDetail');
  detail.currentTradeId = 1;
  detail.currentTrade = { id: 1, status: 'OPEN', is_grouped: true, grouped_count: 2, grouped_net_profit: 30 };
  detail.candleSeries = { update() {} };
  h.context.API.getLatestCandle = async () => ({ net_profit: 11, r_multiple: 0.5, close_price: 1.1 });
  return { ...h, detail, elements };
}

test('grouped live PNL is refreshed from detail API, not the singleton candle response', async () => {
  const h = detailHarness();
  const calls = [];
  h.context.API.getTrade = async id => {
    calls.push(id);
    return { id, status: 'OPEN', is_grouped: true, grouped_count: 2, grouped_net_profit: 45, net_profit: 11 };
  };
  await h.detail.updateLiveCandle();
  assert.equal(h.elements.tdPnl.textContent, 'USD 45');
  assert.deepEqual(calls, [1]);
  assert.equal(h.detail.currentTrade.grouped_net_profit, 45);
  assert.equal(h.elements.tdPreNotesInput.value, 'unsaved note');
});

test('late grouped detail response cannot overwrite a newly selected trade', async () => {
  const h = detailHarness();
  h.context.API.getTrade = async () => {
    h.detail.currentTradeId = 2;
    h.detail.currentTrade = { id: 2, status: 'OPEN' };
    h.elements.tdPnl.textContent = 'new trade';
    return { id: 1, is_grouped: true, grouped_count: 2, grouped_net_profit: 45 };
  };
  await h.detail.updateLiveCandle();
  assert.equal(h.detail.currentTrade.id, 2);
  assert.equal(h.elements.tdPnl.textContent, 'new trade');
});

test('failed grouped refresh retains last group PNL instead of showing a single leg', async () => {
  const h = detailHarness();
  h.context.API.getTrade = async () => { throw new Error('offline'); };
  await h.detail.updateLiveCandle();
  assert.equal(h.elements.tdPnl.textContent, '+USD 30');
});

test('single trade polling keeps the lightweight candle PNL and R multiple', async () => {
  const h = detailHarness();
  h.detail.currentTrade.is_grouped = false;
  let detailCalls = 0;
  h.context.API.getTrade = async () => { detailCalls++; };
  await h.detail.updateLiveCandle();
  assert.equal(h.elements.tdPnl.textContent, 'USD 11 (+0.50 R)');
  assert.equal(detailCalls, 0);
});

for (const event of ['hashchange', 'popstate']) {
  test(`${event} reloads same-view search/date changes and clearing, without duplicate loads`, async () => {
    const input = { value: 'old search' };
    const h = harness({ tradeSearchInput: input });
    const requests = [];
    h.context.API.getTrades = async params => {
      requests.push({ ...params });
      return { total: 0, trades: [] };
    };
    const trades = h.load('trades.js', 'Trades');
    trades.renderTable = () => {};
    const app = h.load('app.js', 'App');
    app.currentView = 'trades';
    app.setupEventListeners();
    for (const [hash, search] of [['#trades?search=EURUSD', 'EURUSD'], ['#trades?date=2026-01-02', '2026-01-02'], ['#trades', '']]) {
      trades.currentOffset = 50;
      const before = requests.length;
      h.context.window.location.hash = hash;
      h.events[event]();
      await Promise.resolve();
      assert.equal(input.value, search);
      assert.equal(requests.length, before + 1);
      assert.equal(requests.at(-1).search || '', search);
      assert.equal(requests.at(-1).offset, 0);
      h.events[event]();
      assert.equal(requests.length, before + 1);
    }
  });
}

test('auto-refresh preserves every active load filter and page', async () => {
  const values = {
    tradeSymbolFilter: 'EURUSD', tradeDirFilter: 'BUY', tradeStatusFilter: 'OPEN',
    tradeSetupFilter: '3', tradeMistakeFilter: '4', tradeSignalFilter: 'Breakout', tradeSearchInput: 'London',
  };
  const h = harness(Object.fromEntries(Object.entries(values).map(([id, value]) => [id, { value }])));
  const requests = [];
  h.context.API.getTrades = async params => {
    requests.push({ ...params });
    return { total: 60, trades: [{ status: 'OPEN' }] };
  };
  const trades = h.load('trades.js', 'Trades');
  trades.populateSignalFilters = () => {};
  trades.renderTable = () => {};
  trades.renderPagination = () => {};
  await trades.load(2);
  await [...h.timers.values()][0]();
  assert.equal(requests[0].offset, 50);
  assert.equal(requests[0].setup_id, '3');
  assert.equal(requests[0].mistake_id, '4');
  assert.equal(requests[0].signals, 'Breakout');
  assert.deepEqual(requests[1], requests[0]);
});

function tradeFormHarness(formValues) {
  const elements = Object.fromEntries(Object.entries(formValues).map(([id, value]) => [id, { value }]));
  elements.addTradeModal = { classList: { remove() {}, add() {} } };
  const h = harness(elements);
  const updates = [];
  h.context.API.updateTrade = async (id, payload) => { updates.push({ id, payload }); return {}; };
  h.context.App.showToast = () => {};
  h.context.App.toLocalDateTimeInput = () => '2026-09-01T10:00';
  const trades = h.load('trades.js', 'Trades');
  trades.load = () => {};
  return { trades, updates };
}

const closedTradeForm = {
  tfAccount: '1', tfSymbol: 'EURUSD', tfDirection: 'BUY', tfStatus: 'WIN', tfVolume: '1.00',
  tfOpenPrice: '1.1000', tfClosePrice: '1.1050', tfStopLoss: '1.0950', tfTakeProfit: '1.1200',
  tfNetProfit: '500.00', tfCommission: '-7.00', tfSwap: '0.00',
  tfOpenTime: '2026-09-01T10:00', tfCloseTime: '2026-09-01T14:00',
};

test('editing a closed trade does not turn a planned TP without P&L into a zero-P&L partial close', async () => {
  const { trades, updates } = tradeFormHarness(closedTradeForm);
  trades.activeEditingId = 9;
  trades.editingHadPartials = false;
  // The edit modal pre-fills one TP row with the TP price and the full volume, but no P&L.
  trades.collectDynamicTps = () => [{ index: 1, price: 1.12, volume: 1, net_profit: null, close_time: '2026-09-01 10:00' }];
  await trades.saveTradeFromForm({ preventDefault() {} });
  assert.equal(updates.length, 1);
  assert.equal(updates[0].payload.partial_closes, undefined);
  assert.equal(updates[0].payload.net_profit, 500);
});

test('TP rows that all carry realized P&L are still saved as partial closes at the exit time', async () => {
  const { trades, updates } = tradeFormHarness(closedTradeForm);
  trades.activeEditingId = 9;
  trades.editingHadPartials = false;
  trades.collectDynamicTps = () => [
    { index: 1, price: 1.105, volume: 0.5, net_profit: 250 },
    { index: 2, price: 1.11, volume: 0.5, net_profit: 500 },
  ];
  await trades.saveTradeFromForm({ preventDefault() {} });
  const partials = updates[0].payload.partial_closes;
  assert.equal(partials.length, 2);
  assert.deepEqual(partials.map(p => [p.volume, p.net_profit, p.close_time]), [[0.5, 250, '2026-09-01 14:00'], [0.5, 500, '2026-09-01 14:00']]);
});

test('merged-leg edit sends each leg its own P&L and volume, never the group totals', async () => {
  const groupForm = { ...closedTradeForm, tfStatus: 'OPEN', tfVolume: '1.50', tfNetProfit: '80.00', tfClosePrice: '', tfCloseTime: '' };
  const { trades, updates } = tradeFormHarness(groupForm);
  trades.activeEditingId = 11;
  trades.editingAllIds = [11, 12];
  trades.editingLegSnapshot = trades.snapshotLegFields();
  trades.collectDynamicTps = () => [
    { index: 1, price: 1.11, volume: 1, net_profit: 50 },
    { index: 2, price: 1.12, volume: 0.5, net_profit: 30 },
  ];
  await trades.saveTradeFromForm({ preventDefault() {} });
  assert.deepEqual(updates.map(u => u.id), [11, 12]);
  assert.deepEqual(updates.map(u => [u.payload.net_profit, u.payload.volume, u.payload.take_profit]), [[50, 1, 1.11], [30, 0.5, 1.12]]);
  for (const { payload } of updates) {
    assert.equal(payload.partial_closes, undefined);
    assert.equal(payload.commission, undefined);
    assert.equal(payload.open_time, undefined, 'unchanged per-leg fields keep each leg value');
    assert.equal(payload.status, undefined);
  }
});

test('overview chart: hovering picks the nearest account line, or none when far away', () => {
  const dashboard = harness().load('dashboard.js', 'Dashboard');
  const series = [
    { key: 'acc-1', coords: [{ x: 0, y: 100 }, { x: 100, y: 50 }] },
    { key: 'acc-2', coords: [{ x: 0, y: 100 }, { x: 100, y: 10 }] },
  ];
  assert.equal(dashboard.nearestSeriesKey(series, 50, 76, 14), 'acc-1');
  assert.equal(dashboard.nearestSeriesKey(series, 100, 12, 14), 'acc-2');
  assert.equal(dashboard.nearestSeriesKey(series, 50, 200, 14), null);
});

test('overview chart: accounts share one time axis and hold their last return to the right edge', () => {
  const dashboard = harness().load('dashboard.js', 'Dashboard');
  const t = s => dashboard.parseCurveTime(s);
  const series = [
    { key: 'acc-1', points: [{ t: t('2026-09-01 10:00'), pct: 0 }, { t: t('2026-09-03 10:00'), pct: 10 }] },
    { key: 'acc-2', points: [{ t: t('2026-09-02 10:00'), pct: 0 }, { t: t('2026-09-05 10:00'), pct: 20 }] },
  ];
  const layout = dashboard.layoutReturnChart(series, 400, 280);
  const right = layout.padding.left + layout.chartW;
  // acc-2 starts later on the shared axis, both lines end at the right edge.
  assert.ok(series[1].coords[0].x > series[0].coords[0].x);
  assert.equal(series[0].coords.at(-1).x, right);
  assert.equal(series[0].coords.at(-1).y, series[0].coords.at(-2).y);
  assert.equal(series[1].coords.at(-1).x, right);
  // Higher return is drawn higher up.
  assert.ok(series[1].coords.at(-1).y < series[0].coords.at(-1).y);
  // Tooltip value is the last realized step at or before the hovered time.
  assert.equal(dashboard.curvePointAt(series[0].points, t('2026-09-02 12:00')).pct, 0);
  assert.equal(dashboard.curvePointAt(series[0].points, t('2026-09-04 00:00')).pct, 10);
});

function overviewDashboardHarness() {
  const ids = ['dashNetPnl', 'dashNetPnlSub', 'dashNetPnlLabel', 'dashOpenPnl', 'dashOpenPnlLabel', 'dashOpenTradesSub',
    'dashWinRate', 'dashWinLossCount', 'dashProfitFactor', 'dashProfitFactorSub', 'dashTotalTrades', 'dashAvgWin',
    'dashAvgLoss', 'dashWinLossRatio', 'dashExpectancy', 'dashExpectancySub', 'dashSharpe', 'dashDrawdown',
    'dashStreaks', 'dashCurrentDrawdown', 'dashCurrentDrawdownR'];
  const elements = Object.fromEntries(ids.map(id => [id, { textContent: '', innerHTML: '', className: '' }]));
  const h = harness(elements);
  h.context.App.formatMoney = (value, currency) => `${currency} ${value}`;
  h.context.App.getActiveCurrency = () => 'USD';
  const dashboard = h.load('dashboard.js', 'Dashboard');
  return { dashboard, elements };
}

const overviewMetrics = { win_rate: 75, winning_trades: 3, losing_trades: 1, total_trades: 4, net_profit: 21000, profit_factor: 6, avg_win: 8666, avg_loss: 5000 };
const overviewSummary = {
  accounts: [{ account_id: 1 }, { account_id: 2 }], active_accounts: 2, avg_return_pct: 15, avg_floating_pct: 1,
  open_trades_count: 1, open_accounts_count: 1, profit_factor: 7, avg_win_pct: 11.67, avg_loss_pct: 5, win_loss_ratio: 2.33,
  expectancy_pct: 7.5, sharpe_ratio: 1.2, max_drawdown_pct: 2.13, current_drawdown_pct: 2.13, current_drawdown_r: 2.5, calendar: {},
};

test('all-accounts KPIs show percent of each account instead of summed currency amounts', () => {
  const { dashboard, elements } = overviewDashboardHarness();
  dashboard.dashboardData = { overview: overviewSummary, metrics: overviewMetrics };
  dashboard.renderKPIs(overviewMetrics, 'USD');
  assert.equal(elements.dashNetPnlLabel.textContent, 'Avg. Return (equal-weighted)');
  assert.equal(elements.dashNetPnl.textContent, '+15.00 %');
  assert.equal(elements.dashProfitFactor.textContent, '7.00');
  assert.equal(elements.dashAvgLoss.textContent, '-5.00 %');
  assert.equal(elements.dashExpectancy.textContent, '+7.50 %');
  assert.equal(elements.dashDrawdown.textContent, '-2.1%');
  for (const el of Object.values(elements)) assert.ok(!String(el.textContent).includes('USD'), 'no currency in overview KPIs');

  // Selecting one account switches back to that account's currency.
  dashboard.dashboardData = { overview: null, metrics: overviewMetrics };
  dashboard.renderKPIs(overviewMetrics, 'GBP');
  assert.equal(elements.dashNetPnlLabel.textContent, 'Net Cumulative P&L');
  assert.equal(elements.dashNetPnl.textContent, 'GBP 21000');
});

test('calendar falls back from currency to percent in the all-accounts overview', () => {
  const { dashboard } = overviewDashboardHarness();
  dashboard.calendarMode = 'currency';
  dashboard.dashboardData = { overview: overviewSummary, calendar: { money: true } };
  assert.equal(dashboard.effectiveCalendarMode(), 'pct');
  assert.equal(dashboard.getCalendarData(), overviewSummary.calendar);
  dashboard.dashboardData = { overview: null, calendar: { money: true } };
  assert.equal(dashboard.effectiveCalendarMode(), 'currency');
  assert.deepEqual(dashboard.getCalendarData(), { money: true });
});
