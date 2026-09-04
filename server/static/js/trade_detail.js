/**
 * Trade Detail & Replay View powered by TradingView Lightweight Charts
 * https://github.com/tradingview/lightweight-charts
 */

const TradeDetail = {
  currentTradeId: null,
  currentTimeframe: 'AUTO',
  chartInstance: null,
  candleSeries: null,
  volumeSeries: null,
  markerPrimitive: null,
  priceLines: [],
  screenshots: [],
  currentScreenshotIndex: 0,

  escapeHtml(value) {
    return String(value ?? '').replace(/[&<>'"]/g, character => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      "'": '&#39;',
      '"': '&quot;'
    }[character]));
  },

  async open(tradeId, timeframe = 'AUTO') {
    this.currentTradeId = tradeId;
    this.currentTimeframe = timeframe;

    const modal = document.getElementById('tradeDetailModal');
    modal.classList.add('active');

    const chartContainer = document.getElementById('tvChartContainer');
    chartContainer.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#9ca3af;">Loading Chart Data...</div>';

    const noticeEl = document.getElementById('tdChartNotice');
    if (noticeEl) noticeEl.style.display = 'none';

    try {
      const [data, trade] = await Promise.all([
        API.getChartData(tradeId, this.currentTimeframe, 140),
        API.getTrade(tradeId)
      ]);
      this.renderTradeInfo(trade);
      this.initChart(chartContainer, data);
    } catch (err) {
      chartContainer.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef4444;">Failed to load chart: ${this.escapeHtml(err.message)}</div>`;
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
    const tradeCurrency = trade.account_currency || App.getActiveCurrency();
    document.getElementById('tdSymbol').textContent = trade.symbol;
    
    const dirBadge = document.getElementById('tdDirection');
    dirBadge.textContent = trade.direction;
    dirBadge.className = `badge ${trade.direction === 'BUY' ? 'badge-buy' : 'badge-sell'}`;

    const pnl = parseFloat(trade.net_profit || 0);
    const pnlEl = document.getElementById('tdPnl');

    const statusBadge = document.getElementById('tdStatusBadge');
    if (statusBadge) {
      if (trade.status === 'PENDING') {
        statusBadge.textContent = 'PENDING LIMIT';
        statusBadge.className = 'badge badge-pending';
      } else if (trade.status === 'CANCELLED') {
        statusBadge.textContent = 'CANCELLED';
        statusBadge.className = 'badge badge-cancelled';
      } else if (trade.status === 'OPEN') {
        statusBadge.textContent = 'OPEN';
        statusBadge.className = 'badge badge-open';
      } else if (trade.status) {
        statusBadge.textContent = trade.status;
        statusBadge.className = `badge badge-${trade.status.toLowerCase()}`;
      } else {
        statusBadge.textContent = '';
        statusBadge.className = 'badge';
      }
    }

    const entryLabel = document.getElementById('tdEntryLabel');
    if (entryLabel) {
      entryLabel.textContent = (trade.status === 'PENDING') ? 'LIMIT PRICE' : 'ENTRY';
    }

    if (trade.status === 'PENDING') {
      pnlEl.textContent = '—';
      pnlEl.className = 'metric-value color-muted';
      document.getElementById('tdExitPrice').textContent = 'Waiting for fill';
      document.getElementById('tdCloseTime').textContent = '—';
    } else if (trade.status === 'CANCELLED') {
      pnlEl.textContent = '—';
      pnlEl.className = 'metric-value color-muted';
      document.getElementById('tdExitPrice').textContent = 'Cancelled';
      document.getElementById('tdCloseTime').textContent = trade.close_time || 'Cancelled';
    } else {
      pnlEl.textContent = App.formatMoney(pnl, tradeCurrency, { showSign: true });
      pnlEl.className = `metric-value ${pnl >= 0 ? 'color-green' : 'color-red'}`;
      document.getElementById('tdExitPrice').textContent = trade.close_price || 'Active';
      document.getElementById('tdCloseTime').textContent = trade.close_time || 'Open';
    }

    document.getElementById('tdVolume').textContent = `${trade.volume} lots`;
    document.getElementById('tdEntryPrice').textContent = trade.open_price;
    document.getElementById('tdSL').textContent = trade.stop_loss ? trade.stop_loss : 'None';
    document.getElementById('tdTP').textContent = trade.take_profit ? trade.take_profit : 'None';
    document.getElementById('tdCommission').textContent = App.formatMoney(trade.commission || 0, tradeCurrency);
    document.getElementById('tdSwap').textContent = App.formatMoney(trade.swap || 0, tradeCurrency);
    document.getElementById('tdOpenTime').textContent = trade.open_time;

    const partials = Array.isArray(trade.partial_closes) ? trade.partial_closes : [];
    const partialList = document.getElementById('tdPartialClosesList');
    const partialSummary = document.getElementById('tdPartialSummary');
    const partialStatus = document.getElementById('tdPartialStatus');
    const closedVolume = partials.reduce((sum, partial) => sum + Number(partial.volume || 0), 0);
    const originalVolume = Number(trade.volume || 0);
    if (partialSummary) {
      partialSummary.textContent = partials.length
        ? `${closedVolume.toFixed(2)} / ${originalVolume.toFixed(2)} lots closed in ${partials.length} partial exit(s)`
        : `Original position: ${originalVolume.toFixed(2)} lots — no partial exits recorded`;
    }
    if (partialStatus) partialStatus.textContent = '';
    if (partialList) {
      partialList.innerHTML = partials.length ? partials.map(partial => {
        const pnl = Number(partial.net_profit || 0);
        const pnlColor = pnl >= 0 ? '#10b981' : '#ef4444';
        return `
          <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:7px 8px;margin-bottom:5px;background:#0a0e17;border-radius:5px;">
            <span>${this.escapeHtml(partial.close_time)} • ${Number(partial.volume).toFixed(2)} lots @ ${Number(partial.close_price)} </span>
            <span style="display:flex;align-items:center;gap:8px;white-space:nowrap;">
              <strong style="color:${pnlColor};">${App.formatMoney(pnl, tradeCurrency, { showSign: true })}</strong>
              <button type="button" class="btn btn-secondary btn-sm" onclick="TradeDetail.deletePartialClose(${partial.id})" style="color:#ef4444;padding:3px 7px;">×</button>
            </span>
          </div>`;
      }).join('') : '<span style="color:#6b7280;">No partial exits yet. Add each cTrader scale-out here when entering trades manually.</span>';
    }

    this.screenshots = Array.isArray(trade.screenshots) ? trade.screenshots : [];
    this.currentScreenshotIndex = 0;
    this.renderScreenshots();

    const partialTimeInput = document.getElementById('tdPartialCloseTime');
    if (partialTimeInput && !partialTimeInput.value) {
      const now = new Date();
      const localNow = new Date(now.getTime() - now.getTimezoneOffset() * 60000);
      partialTimeInput.value = localNow.toISOString().slice(0, 16);
    }

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

  renderScreenshots() {
    const container = document.getElementById('tdScreenshotsList');
    if (!container) return;

    if (!this.screenshots.length) {
      container.innerHTML = '<span style="font-size:12px;color:#6b7280;">Noch keine Screenshots für diesen Trade.</span>';
      return;
    }

    container.innerHTML = this.screenshots.map((screenshot, index) => `
      <div style="position:relative;width:132px;cursor:pointer;" onclick="TradeDetail.openScreenshotViewer(${index})" title="Screenshot öffnen">
        <img src="${this.escapeHtml(screenshot.image_url)}" alt="${this.escapeHtml(screenshot.caption || 'Trade screenshot')}" loading="lazy" style="display:block;width:132px;height:88px;object-fit:cover;border-radius:6px;border:1px solid #263247;background:#090d16;">
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:4px 2px 0;font-size:11px;color:#cbd5e1;">${this.escapeHtml(screenshot.caption || 'TradingView')}</div>
        <button type="button" class="btn btn-secondary btn-sm" onclick="event.stopPropagation();TradeDetail.deleteScreenshot(${screenshot.id})" style="position:absolute;top:4px;right:4px;padding:1px 6px;color:#ef4444;background:#090d16dd;" aria-label="Screenshot löschen">×</button>
      </div>
    `).join('');
  },

  async addScreenshot() {
    if (!this.currentTradeId) return;

    const sourceInput = document.getElementById('tdScreenshotSourceUrl');
    const captionInput = document.getElementById('tdScreenshotCaption');
    const statusEl = document.getElementById('tdScreenshotStatus');
    const source_url = sourceInput.value.trim();
    const caption = captionInput.value.trim();

    if (!source_url) {
      statusEl.innerHTML = '<span style="color:#ef4444;">Bitte zuerst den TradingView-Link einfügen.</span>';
      return;
    }

    try {
      await API.addTradeScreenshot(this.currentTradeId, {
        source_url,
        caption
      });
      App.showToast('Screenshot hinzugefügt.', 'success');
      sourceInput.value = '';
      captionInput.value = '';
      statusEl.textContent = '';
      await this.open(this.currentTradeId, this.currentTimeframe);
      Trades.load();
    } catch (err) {
      statusEl.innerHTML = `<span style="color:#ef4444;">${this.escapeHtml(err.message)}</span>`;
    }
  },

  async deleteScreenshot(screenshotId) {
    if (!confirm('Diesen Screenshot wirklich löschen?')) return;
    try {
      await API.deleteTradeScreenshot(this.currentTradeId, screenshotId);
      App.showToast('Screenshot gelöscht.', 'success');
      await this.open(this.currentTradeId, this.currentTimeframe);
      Trades.load();
    } catch (err) {
      App.showToast(`Screenshot konnte nicht gelöscht werden: ${err.message}`, 'error');
    }
  },

  openScreenshotViewer(index) {
    this.openScreenshotCollection(this.screenshots, index);
  },

  openScreenshotCollection(screenshots, index = 0) {
    this.screenshots = Array.isArray(screenshots) ? screenshots : [];
    if (!this.screenshots.length) return;
    this.currentScreenshotIndex = Math.max(0, Math.min(index, this.screenshots.length - 1));
    this.renderScreenshotViewer();
    document.getElementById('tradeScreenshotLightbox').classList.add('active');
  },

  renderScreenshotViewer() {
    const screenshot = this.screenshots[this.currentScreenshotIndex];
    if (!screenshot) {
      this.closeScreenshotViewer();
      return;
    }

    const image = document.getElementById('tdScreenshotLightboxImage');
    const caption = document.getElementById('tdScreenshotLightboxCaption');
    const counter = document.getElementById('tdScreenshotLightboxCounter');
    const source = document.getElementById('tdScreenshotLightboxSource');
    const previous = document.getElementById('tdScreenshotPrevious');
    const next = document.getElementById('tdScreenshotNext');
    image.src = screenshot.image_url;
    image.alt = screenshot.caption || 'Trade screenshot';
    caption.textContent = screenshot.caption || '';
    counter.textContent = `${this.currentScreenshotIndex + 1} / ${this.screenshots.length}`;
    source.href = screenshot.source_url;
    previous.disabled = this.screenshots.length < 2;
    next.disabled = this.screenshots.length < 2;
  },

  previousScreenshot() {
    if (this.screenshots.length < 2) return;
    this.currentScreenshotIndex = (this.currentScreenshotIndex - 1 + this.screenshots.length) % this.screenshots.length;
    this.renderScreenshotViewer();
  },

  nextScreenshot() {
    if (this.screenshots.length < 2) return;
    this.currentScreenshotIndex = (this.currentScreenshotIndex + 1) % this.screenshots.length;
    this.renderScreenshotViewer();
  },

  closeScreenshotViewer() {
    const lightbox = document.getElementById('tradeScreenshotLightbox');
    if (lightbox) lightbox.classList.remove('active');
  },

  initChart(container, data) {
    container.innerHTML = ''; // Clear container

    // Check if TradingView LightweightCharts is loaded
    if (typeof LightweightCharts === 'undefined') {
      container.innerHTML = '<div style="color:#ef4444;padding:20px;">LightweightCharts library not loaded.</div>';
      return;
    }

    // Update toolbar active state
    const autoBtn = document.getElementById('tdBtnAuto');
    if (autoBtn) {
      if (this.currentTimeframe === 'AUTO' && data.timeframe) {
        autoBtn.textContent = `Auto (${data.timeframe})`;
      } else {
        autoBtn.textContent = 'Auto';
      }
    }
    document.querySelectorAll('.tf-btn').forEach(btn => {
      btn.classList.toggle('btn-primary', btn.dataset.tf === this.currentTimeframe);
      btn.classList.toggle('btn-secondary', btn.dataset.tf !== this.currentTimeframe);
    });

    const noticeEl = document.getElementById('tdChartNotice');
    if (noticeEl) {
      if (data.message && data.candles && data.candles.length > 0) {
        noticeEl.style.display = 'block';
        noticeEl.style.background = '#fef3c71a';
        noticeEl.style.color = '#f59e0b';
        noticeEl.style.border = '1px solid #f59e0b44';
        noticeEl.innerHTML = `⚠️ ${this.escapeHtml(data.message)}`;
      } else {
        noticeEl.style.display = 'none';
      }
    }

    if (!data.candles || data.candles.length === 0) {
      if (this.chartInstance) {
        try { this.chartInstance.remove(); } catch (e) {}
        this.chartInstance = null;
      }
      container.innerHTML = `
        <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;height:100%;color:#9ca3af;padding:24px;text-align:center;">
          <div style="font-size:36px;margin-bottom:12px;">📊</div>
          <div style="font-weight:600;font-size:15px;color:#e2e8f0;margin-bottom:6px;">Keine echten Broker-Kerzen gespeichert</div>
          <div style="font-size:13px;max-width:440px;line-height:1.5;color:#9ca3af;">${this.escapeHtml(data.message || 'Für diesen Trade sind noch keine echten Kerzen gespeichert. Bitte den aktualisierten EA / cBot synchronisieren.')}</div>
        </div>
      `;
      return;
    }

    if (this.chartInstance) {
      try { this.chartInstance.remove(); } catch (e) {}
      this.chartInstance = null;
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
    const candleOptions = {
      upColor: '#10b981',
      downColor: '#ef4444',
      borderVisible: false,
      wickUpColor: '#10b981',
      wickDownColor: '#ef4444',
    };
    this.candleSeries = typeof this.chartInstance.addCandlestickSeries === 'function'
      ? this.chartInstance.addCandlestickSeries(candleOptions)
      : this.chartInstance.addSeries(LightweightCharts.CandlestickSeries, candleOptions);
    this.candleSeries.setData(data.candles);

    // 2. Volume Histogram Series
    const volumeOptions = {
      color: '#26a69a',
      priceFormat: { type: 'volume' },
      priceScaleId: '', // Overlay over chart
      scaleMargins: { top: 0.8, bottom: 0 },
    };
    this.volumeSeries = typeof this.chartInstance.addHistogramSeries === 'function'
      ? this.chartInstance.addHistogramSeries(volumeOptions)
      : this.chartInstance.addSeries(LightweightCharts.HistogramSeries, volumeOptions);
    this.volumeSeries.setData(data.volume);

    // 3. Trade Entry & Exit Markers
    if (data.markers && data.markers.length > 0) {
      if (typeof this.candleSeries.setMarkers === 'function') {
        this.candleSeries.setMarkers(data.markers);
      } else if (typeof LightweightCharts.createSeriesMarkers === 'function') {
        this.markerPrimitive = LightweightCharts.createSeriesMarkers(this.candleSeries, data.markers);
      }
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
    chartContainer.innerHTML = '<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#9ca3af;">Loading Chart Data...</div>';
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
  },

  async addPartialClose() {
    if (!this.currentTradeId) return;

    const volume = parseFloat(document.getElementById('tdPartialVolume').value);
    const close_price = parseFloat(document.getElementById('tdPartialClosePrice').value);
    const net_profit = parseFloat(document.getElementById('tdPartialNetProfit').value || 0);
    const close_time = document.getElementById('tdPartialCloseTime').value.replace('T', ' ');
    const statusEl = document.getElementById('tdPartialStatus');

    if (!(volume > 0) || !(close_price > 0) || !close_time) {
      statusEl.innerHTML = '<span style="color:#ef4444;">Volume, close price and close time are required.</span>';
      return;
    }

    try {
      await API.addPartialClose(this.currentTradeId, {
        volume,
        close_price,
        net_profit,
        close_time
      });
      App.showToast('Partial exit added successfully.', 'success');
      document.getElementById('tdPartialVolume').value = '';
      document.getElementById('tdPartialClosePrice').value = '';
      document.getElementById('tdPartialNetProfit').value = '0.00';
      await this.open(this.currentTradeId, this.currentTimeframe);
      Trades.load();
      Dashboard.load();
    } catch (err) {
      statusEl.innerHTML = `<span style="color:#ef4444;">${this.escapeHtml(err.message)}</span>`;
    }
  },

  async deletePartialClose(partialId) {
    if (!confirm('Delete this partial exit?')) return;
    try {
      await API.deletePartialClose(this.currentTradeId, partialId);
      App.showToast('Partial exit deleted.', 'success');
      await this.open(this.currentTradeId, this.currentTimeframe);
      Trades.load();
      Dashboard.load();
    } catch (err) {
      App.showToast(`Failed to delete partial exit: ${err.message}`, 'error');
    }
  }
};

document.addEventListener('keydown', event => {
  const lightbox = document.getElementById('tradeScreenshotLightbox');
  if (!lightbox?.classList.contains('active')) return;
  if (event.key === 'Escape') {
    event.preventDefault();
    TradeDetail.closeScreenshotViewer();
  } else if (event.key === 'ArrowLeft') {
    event.preventDefault();
    TradeDetail.previousScreenshot();
  } else if (event.key === 'ArrowRight') {
    event.preventDefault();
    TradeDetail.nextScreenshot();
  }
});
