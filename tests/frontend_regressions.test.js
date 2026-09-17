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
