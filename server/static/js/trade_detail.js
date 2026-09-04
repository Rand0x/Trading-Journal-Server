/**
 * Trade Detail & Replay View powered by TradingView Lightweight Charts
 * https://github.com/tradingview/lightweight-charts
 */

const TradeDetail = {
  currentTradeId: null,
  currentTimeframe: 'M15',
  chartInstance: null,
  candleSeries: null,
  volumeSeries: null,
  priceLines: [],

  async open(tradeId, timeframe = 'M15') {
    this.currentTradeId = tradeId;
    this.currentTimeframe = timeframe;

    const modal = document.getElementById('tradeDetailModal');
    modal.classList.add('active');

    const chartContainer = document.getElementById('tvChartContainer');
    chartContainer.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#9ca3af;">Loading Chart Data...</div>';

    try {
      const data = await API.getChartData(tradeId, this.currentTimeframe, 140);
      this.renderTradeInfo(data.trade);
      this.initChart(chartContainer, data);
    } catch (err) {
      chartContainer.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef4444;">Failed to load chart: ${err.message}</div>`;
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  close() {
    const modal = document.getElementById('tradeDetailModal');
    modal.classList.remove('active');
    if (this.chartInstance) {
      try {
        this.chartInstance.remove();
      } catch (e) {}
      this.chartInstance = null;
    }
  },

  renderTradeInfo(trade) {
    document.getElementById('tdSymbol').textContent = trade.symbol;
    
    const dirBadge = document.getElementById('tdDirection');
    dirBadge.textContent = trade.direction;
    dirBadge.className = `badge ${trade.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`;

    const pnl = parseFloat(trade.net_profit || 0);
    const pnlEl = document.getElementById('tdPnl');
    pnlEl.textContent = `${pnl >= 0 ? '+' : ''}$${pnl.toFixed(2)}`;
    pnlEl.className = `metric-value ${pnl >= 0 ? 'color-green' : 'color-red'}`;

    document.getElementById('tdVolume').textContent = `${trade.volume} lots`;
    document.getElementById('tdEntryPrice').textContent = trade.open_price;
    document.getElementById('tdExitPrice').textContent = trade.close_price || 'Active';
    document.getElementById('tdSL').textContent = trade.stop_loss ? trade.stop_loss : 'None';
    document.getElementById('tdTP').textContent = trade.take_profit ? trade.take_profit : 'None';
    document.getElementById('tdCommission').textContent = `$${parseFloat(trade.commission || 0).toFixed(2)}`;
    document.getElementById('tdSwap').textContent = `$${parseFloat(trade.swap || 0).toFixed(2)}`;
    document.getElementById('tdOpenTime').textContent = trade.open_time;
    document.getElementById('tdCloseTime').textContent = trade.close_time || 'Open';

    // Form inputs
    document.getElementById('tdNotesInput').value = trade.notes || '';
    document.getElementById('tdEmotionSelect').value = trade.emotions || 'Disciplined';
    document.getElementById('tdRatingSelect').value = trade.rating || 5;

    // Populate setups dropdown
    const setupSelect = document.getElementById('tdSetupSelect');
    setupSelect.innerHTML = '<option value="">-- No Setup --</option>';
    (App.playbooks || []).forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name;
      if (trade.setup_id === p.id) opt.selected = true;
      setupSelect.appendChild(opt);
    });

    // Populate mistakes dropdown
    const mistakeSelect = document.getElementById('tdMistakeSelect');
    mistakeSelect.innerHTML = '<option value="">-- No Mistake --</option>';
    (App.mistakes || []).forEach(m => {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.name;
      if (trade.mistake_id === m.id) opt.selected = true;
      mistakeSelect.appendChild(opt);
    });
  },

  initChart(container, data) {
    container.innerHTML = ''; // Clear container

    // Check if TradingView LightweightCharts is loaded
    if (typeof LightweightCharts === 'undefined') {
      container.innerHTML = '<div style="color:#ef4444;padding:20px;">LightweightCharts library not loaded.</div>';
      return;
    }

    const chartOptions = {
      width: container.clientWidth,
      height: container.clientHeight || 450,
      layout: {
        background: { type: 'solid', color: '#090d16' },
        textColor: '#9ca3af',
        fontSize: 12,
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
      },
      grid: {
        vertLines: { color: '#161f30' },
        horzLines: { color: '#161f30' },
      },
      crosshair: {
        mode: LightweightCharts.CrosshairMode.Normal,
        vertLine: { color: '#3b82f6', width: 1, style: 3, labelBackgroundColor: '#1e293b' },
        horzLine: { color: '#3b82f6', width: 1, style: 3, labelBackgroundColor: '#1e293b' },
      },
      rightPriceScale: {
        borderColor: '#1f2937',
        scaleMargins: { top: 0.15, bottom: 0.25 },
      },
      timeScale: {
        borderColor: '#1f2937',
        timeVisible: true,
        secondsVisible: false,
      },
    };

    this.chartInstance = LightweightCharts.createChart(container, chartOptions);

    // 1. Candlestick Series
    this.candleSeries = this.chartInstance.addCandlestickSeries({
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    });
    this.candleSeries.setData(data.candles);

    // 2. Volume Histogram Series
    this.volumeSeries = this.chartInstance.addHistogramSeries({
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: '', // Overlay over chart
      scaleMargins: { top: 0.8, bottom: 0 },
    });
    this.volumeSeries.setData(data.volume);

    // 3. Trade Entry & Exit Markers
    if (data.markers && data.markers.length > 0) {
      this.candleSeries.setMarkers(data.markers);
    }

    // 4. Horizontal Price Lines (Entry, SL, TP)
    this.priceLines = [];
    if (data.price_lines) {
      data.price_lines.forEach(pl => {
        const line = this.candleSeries.createPriceLine({
          price: pl.price,
          color: pl.color,
          lineWidth: pl.lineWidth || 2,
          lineStyle: pl.lineStyle || 2,
          axisLabelVisible: true,
          title: pl.title || '',
        });
        this.priceLines.push(line);
      });
    }

    // Fit content
    this.chartInstance.timeScale().fitContent();

    // Handle responsive container resize
    const resizeObserver = new ResizeObserver(entries => {
      if (entries.length === 0 || !this.chartInstance) return;
      const { width, height } = entries[0].contentRect;
      this.chartInstance.applyOptions({ width, height: height || 450 });
    });
    resizeObserver.observe(container);
  },

  async switchTimeframe(tf) {
    if (!this.currentTradeId) return;
    this.currentTimeframe = tf;

    // Update active button state
    document.querySelectorAll('.tf-btn').forEach(btn => {
      btn.classList.toggle('btn-primary', btn.dataset.tf === tf);
      btn.classList.toggle('btn-secondary', btn.dataset.tf !== tf);
    });

    const chartContainer = document.getElementById('tvChartContainer');
    try {
      const data = await API.getChartData(this.currentTradeId, tf, 140);
      this.initChart(chartContainer, data);
    } catch (err) {
      App.showToast(`Error changing timeframe: ${err.message}`, 'error');
    }
  },

  async saveChanges() {
    if (!this.currentTradeId) return;
    const notes = document.getElementById('tdNotesInput').value;
    const setup_id = document.getElementById('tdSetupSelect').value ? parseInt(document.getElementById('tdSetupSelect').value) : null;
    const mistake_id = document.getElementById('tdMistakeSelect').value ? parseInt(document.getElementById('tdMistakeSelect').value) : null;
    const emotions = document.getElementById('tdEmotionSelect').value;
    const rating = parseInt(document.getElementById('tdRatingSelect').value);

    try {
      await API.updateTrade(this.currentTradeId, {
        notes,
        setup_id,
        mistake_id,
        emotions,
        rating
      });
      App.showToast('Trade notes and tags saved successfully!', 'success');
      App.refreshCurrentView();
    } catch (err) {
      App.showToast(`Failed to save trade: ${err.message}`, 'error');
    }
  }
};
