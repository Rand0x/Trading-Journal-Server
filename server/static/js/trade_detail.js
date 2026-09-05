/**
 * Trade Detail & Replay View powered by TradingView Lightweight Charts
 * https://github.com/tradingview/lightweight-charts
 */

const TradeDetail = {
  currentTradeId: null,
  currentTimeframe: 'AUTO',
  activeTimeframe: 'M15',
  liveUpdateTimer: null,
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
    this.stopLiveUpdate();
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
        API.getChartData(tradeId, this.currentTimeframe, 2000),
        API.getTrade(tradeId)
      ]);
      this.currentTrade = trade;
      this.renderTradeInfo(trade);
      this.initChart(chartContainer, data);
      this.startLiveUpdate();
    } catch (err) {
      chartContainer.innerHTML = `<div style="display:flex;align-items:center;justify-content:center;height:100%;color:#ef4444;">Failed to load chart: ${this.escapeHtml(err.message)}</div>`;
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  close() {
    this.stopLiveUpdate();
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

    const isGrouped = trade.is_grouped && trade.grouped_count > 1;
    const pnl = parseFloat((isGrouped && trade.grouped_net_profit !== undefined) ? trade.grouped_net_profit : (trade.net_profit || 0));
    const pnlEl = document.getElementById('tdPnl');

    const statusBadge = document.getElementById('tdStatusBadge');
    if (statusBadge) {
      if (trade.is_missed) {
        statusBadge.textContent = 'MISSED';
        statusBadge.className = 'badge badge-missed';
      } else if (trade.status === 'PENDING') {
        statusBadge.textContent = isGrouped ? `LIMIT (${trade.grouped_count} TPs)` : 'PENDING LIMIT';
        statusBadge.className = 'badge badge-pending';
      } else if (trade.status === 'CANCELLED') {
        statusBadge.textContent = 'CANCELLED';
        statusBadge.className = 'badge badge-cancelled';
      } else if (trade.status === 'OPEN') {
        statusBadge.textContent = isGrouped ? `OPEN (${trade.grouped_count} TPs)` : 'OPEN';
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

    if (trade.is_missed) {
      pnlEl.textContent = '— (Missed)';
      pnlEl.className = 'metric-value color-muted';
      document.getElementById('tdExitPrice').textContent = trade.close_price || '—';
      document.getElementById('tdCloseTime').textContent = trade.close_time || '—';
    } else if (trade.status === 'PENDING') {
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
      const rStr = trade.r_multiple != null ? ` (${Number(trade.r_multiple) >= 0 ? '+' : ''}${Number(trade.r_multiple).toFixed(2)} R)` : '';
      pnlEl.textContent = `${App.formatMoney(pnl, tradeCurrency, { showSign: true })}${rStr}`;
      pnlEl.className = `metric-value ${pnl >= 0 ? 'color-green' : 'color-red'}`;
      document.getElementById('tdExitPrice').textContent = trade.close_price || 'Active';
      document.getElementById('tdCloseTime').textContent = trade.close_time || 'Open';
    }

    const volText = isGrouped
      ? `${Number(trade.grouped_total_volume || trade.volume).toFixed(2)} lots (${trade.grouped_count} orders)`
      : `${Number(trade.volume).toFixed(2)} lots`;
    document.getElementById('tdVolume').textContent = volText;
    document.getElementById('tdEntryPrice').textContent = trade.open_price;
    document.getElementById('tdSL').textContent = trade.stop_loss ? trade.stop_loss : 'None';

    const openP = parseFloat(trade.open_price) || 0;
    const slP = parseFloat(trade.stop_loss) || 0;
    const isBuy = trade.direction === 'BUY';
    const subTrades = Array.isArray(trade.sub_trades) ? trade.sub_trades : [];

    // Parse all TP targets (from sub_trades, tp_targets, or multiple_tps)
    let tpTargetsList = [];

    if (isGrouped && subTrades.length > 1) {
      subTrades.forEach((leg, idx) => {
        const p = parseFloat(leg.take_profit);
        if (p > 0 && (openP <= 0 || (p >= 0.05 * openP && p <= 20 * openP))) {
          tpTargetsList.push({
            index: idx + 1,
            price: p,
            volume: leg.volume ? parseFloat(leg.volume) : null,
            net_profit: leg.net_profit != null ? parseFloat(leg.net_profit) : null,
            ticket: leg.ticket || leg.id,
            status: leg.status
          });
        }
      });
      if (openP > 0) {
        tpTargetsList.sort((a, b) => Math.abs(a.price - openP) - Math.abs(b.price - openP));
        tpTargetsList.forEach((t, i) => { t.index = i + 1; });
      }
    }

    if (tpTargetsList.length === 0 && trade.tp_targets) {
      try {
        const parsed = JSON.parse(trade.tp_targets);
        if (Array.isArray(parsed) && parsed.length > 0) {
          parsed.forEach((t, idx) => {
            const p = parseFloat(t.price || t.close_price || t.tp || t);
            if (p > 0 && (openP <= 0 || (p >= 0.05 * openP && p <= 20 * openP))) {
              tpTargetsList.push({
                index: idx + 1,
                price: p,
                volume: t.volume != null ? parseFloat(t.volume) : (t.lots != null ? parseFloat(t.lots) : null),
                net_profit: t.net_profit != null ? parseFloat(t.net_profit) : null,
                ticket: t.ticket || null,
                status: t.status || null
              });
            }
          });
        }
      } catch (e) {}
    }

    if (tpTargetsList.length === 0 && trade.multiple_tps && trade.multiple_tps.length > 1) {
      trade.multiple_tps.forEach((tp, idx) => {
        const p = parseFloat(tp);
        if (p > 0 && (openP <= 0 || (p >= 0.05 * openP && p <= 20 * openP))) {
          tpTargetsList.push({
            index: idx + 1,
            price: p,
            volume: null
          });
        }
      });
    }

    const tdTpElement = document.getElementById('tdTP');
    if (tdTpElement) {
      if (tpTargetsList.length > 1) {
        tdTpElement.innerHTML = tpTargetsList.map((t, idx) => `<div style="color:#10b981;font-weight:700;line-height:1.35;">TP${t.index || (idx + 1)}: ${t.price}</div>`).join('');
      } else if (trade.multiple_tps && trade.multiple_tps.length > 1) {
        tdTpElement.innerHTML = trade.multiple_tps.map((tp, idx) => `<div style="color:#10b981;font-weight:700;line-height:1.35;">TP${idx + 1}: ${tp}</div>`).join('');
      } else {
        tdTpElement.textContent = trade.take_profit ? trade.take_profit : 'None';
      }
    }

    // Risk Distance & Target R:R Calculation
    const riskDist = (openP > 0 && slP > 0 && openP !== slP) ? Math.abs(openP - slP) : 0;
    const riskDistEl = document.getElementById('tdRiskDist');
    if (riskDistEl) {
      riskDistEl.textContent = riskDist > 0 ? `${riskDist < 1 ? riskDist.toFixed(5) : riskDist.toFixed(2)} pts` : '—';
    }

    let targetRR = null;
    if (riskDist > 0) {
      if (tpTargetsList.length > 0) {
        const sumV = tpTargetsList.reduce((acc, t) => acc + (t.volume > 0 ? t.volume : 0), 0);
        let weightedReward = 0;
        tpTargetsList.forEach(t => {
          const reward = isBuy ? (t.price - openP) : (openP - t.price);
          const weight = sumV > 0 && t.volume > 0 ? (t.volume / sumV) : (1 / tpTargetsList.length);
          weightedReward += reward * weight;
        });
        targetRR = weightedReward / riskDist;
      } else if (trade.take_profit && parseFloat(trade.take_profit) > 0) {
        const reward = isBuy ? (parseFloat(trade.take_profit) - openP) : (openP - parseFloat(trade.take_profit));
        targetRR = reward / riskDist;
      }
    }

    const targetRREl = document.getElementById('tdTargetRR');
    if (targetRREl) {
      if (targetRR !== null) {
        targetRREl.textContent = `1 : ${targetRR.toFixed(2)}${tpTargetsList.length > 1 ? ' (avg)' : ''}`;
        targetRREl.style.color = targetRR >= 1 ? '#10b981' : '#f59e0b';
      } else {
        targetRREl.textContent = '—';
        targetRREl.style.color = '#9ca3af';
      }
    }

    const rMultEl = document.getElementById('tdRMultiple');
    if (rMultEl) {
      if (trade.r_multiple != null) {
        const rVal = parseFloat(trade.r_multiple);
        rMultEl.textContent = `${rVal >= 0 ? '+' : ''}${rVal.toFixed(2)} R`;
        rMultEl.style.color = rVal >= 0 ? '#10b981' : '#ef4444';
      } else {
        rMultEl.textContent = '—';
        rMultEl.style.color = '#9ca3af';
      }
    }

    document.getElementById('tdCommission').textContent = App.formatMoney((isGrouped && trade.grouped_commission !== undefined) ? trade.grouped_commission : (trade.commission || 0), tradeCurrency);
    document.getElementById('tdSwap').textContent = App.formatMoney((isGrouped && trade.grouped_swap !== undefined) ? trade.grouped_swap : (trade.swap || 0), tradeCurrency);
    
    const tfEl = document.getElementById('tdTimeframe');
    if (tfEl) tfEl.textContent = trade.timeframe || this.currentTimeframe || 'M15';

    const accEl = document.getElementById('tdAccount');
    if (accEl) accEl.textContent = trade.account_name || ('Account #' + (trade.account_id || 1));

    document.getElementById('tdOpenTime').textContent = trade.open_time;

    // Take Profit Targets & Lots card in modal
    const tpCard = document.getElementById('tdTpTargetsCard');
    const tpSummary = document.getElementById('tdTpTargetsSummary');
    const tpList = document.getElementById('tdTpTargetsList');
    if (tpCard && tpList) {
      if (tpTargetsList.length > 0) {
        tpCard.style.display = 'block';
        if (tpSummary) {
          const totalLots = tpTargetsList.reduce((acc, t) => acc + (t.volume > 0 ? t.volume : 0), 0);
          tpSummary.textContent = `${tpTargetsList.length} Targets${totalLots > 0 ? ` · ${totalLots.toFixed(2)} lots total` : ''}`;
        }
        tpList.innerHTML = tpTargetsList.map((t, idx) => {
          const rewardPts = openP > 0 ? (isBuy ? (t.price - openP) : (openP - t.price)) : 0;
          const targetR = riskDist > 0 ? (rewardPts / riskDist) : null;
          const rrStr = targetR !== null ? ` · <strong>1 : ${targetR.toFixed(2)} R</strong>` : '';
          const volStr = t.volume ? ` · <span style="color:#60a5fa;font-weight:600;">${Number(t.volume).toFixed(2)} lots</span>` : '';
          const pnlStr = t.net_profit != null && t.net_profit !== '' ? ` · <span style="color:${Number(t.net_profit) >= 0 ? '#10b981' : '#ef4444'};">${App.formatMoney(t.net_profit, tradeCurrency, { showSign: true })}</span>` : '';
          const ticketStr = t.ticket ? ` <span style="font-size:11px;color:#6b7280;">(Ticket #${t.ticket})</span>` : '';

          return `
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 10px;background:#0a0e17;border-radius:6px;border:1px solid #1e293b;">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                <span class="badge" style="background:#1e293b;color:#10b981;font-weight:700;">TP${t.index || (idx + 1)}</span>
                <span style="font-weight:700;color:#fff;">${t.price}</span>
                <span style="font-size:12px;color:#9ca3af;">${rewardPts >= 0 ? '+' : ''}${rewardPts < 1 ? rewardPts.toFixed(5) : rewardPts.toFixed(2)} pts</span>
                <span style="font-size:12px;color:#d1d5db;">${volStr}${rrStr}${pnlStr}${ticketStr}</span>
              </div>
              <div>
                <span class="badge" style="background:#10b98122;color:#10b981;">Target</span>
              </div>
            </div>
          `;
        }).join('');
      } else {
        tpCard.style.display = 'none';
        tpList.innerHTML = '';
      }
    }

    // Grouped Orders list in modal
    const groupedCard = document.getElementById('tdGroupedOrdersCard');
    const groupedSummary = document.getElementById('tdGroupedSummary');
    const groupedBadge = document.getElementById('tdGroupedBadge');
    const groupedList = document.getElementById('tdGroupedOrdersList');

    if (groupedCard && groupedList) {
      if (isGrouped && subTrades.length > 1) {
        groupedCard.style.display = 'block';
        if (groupedBadge) groupedBadge.textContent = `${trade.grouped_count} Orders Merged`;
        if (groupedSummary) {
          groupedSummary.textContent = `Total Volume: ${Number(trade.grouped_total_volume || trade.volume).toFixed(2)} lots across ${subTrades.length} positions`;
        }
        groupedList.innerHTML = subTrades.map((leg, idx) => {
          const legPnl = Number(leg.net_profit || 0);
          const pnlColor = legPnl >= 0 ? '#10b981' : '#ef4444';
          const tpStr = leg.take_profit ? `TP${idx + 1}: ${leg.take_profit}` : 'No TP';
          const slStr = leg.stop_loss ? `SL: ${leg.stop_loss}` : 'No SL';
          const statusCls = `badge badge-${(leg.status || 'open').toLowerCase()}`;
          return `
            <div style="display:flex;align-items:center;justify-content:space-between;gap:8px;padding:8px 10px;background:#0a0e17;border-radius:6px;border:1px solid #1e293b;">
              <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap;">
                <span class="${statusCls}" style="font-size:10px;">${this.escapeHtml(leg.status || 'OPEN')}</span>
                <span style="color:#cbd5e1;font-weight:600;">Ticket #${this.escapeHtml(leg.ticket || leg.id)}</span>
                <span style="color:#60a5fa;font-weight:700;">${Number(leg.volume).toFixed(2)} lots</span>
                <span style="color:#9ca3af;">@ ${leg.open_price}</span>
                <strong style="color:#10b981;">${tpStr}</strong>
                <span style="color:#ef4444;">${slStr}</span>
              </div>
              <strong style="color:${pnlColor};font-size:13px;">${App.formatMoney(legPnl, tradeCurrency, { showSign: true })}</strong>
            </div>`;
        }).join('');
      } else {
        groupedCard.style.display = 'none';
        groupedList.innerHTML = '';
      }
    }

    // Setup Signals & Confluence
    const signalsCard = document.getElementById('tdSignalsCard');
    const signalsList = document.getElementById('tdSignalsList');
    const signalsCount = document.getElementById('tdSignalsCount');
    if (signalsCard && signalsList) {
      const sigs = (trade.signals || '').split(',').map(s => s.trim()).filter(Boolean);
      if (sigs.length > 0) {
        signalsCard.style.display = 'block';
        if (signalsCount) signalsCount.textContent = `${sigs.length} Signal${sigs.length > 1 ? 's' : ''}`;
        signalsList.innerHTML = sigs.map(s => `<span class="chip-btn active" style="cursor:default;background:#3b82f622;color:#60a5fa;border-color:#3b82f655;">✓ ${this.escapeHtml(s)}</span>`).join('');
      } else {
        signalsCard.style.display = 'none';
        signalsList.innerHTML = '';
      }
    }

    // 2-Phase Emotions
    const preEmoEl = document.getElementById('tdEmotionPreDisplay');
    if (preEmoEl) {
      const preList = (trade.emotion_pre || '').split(',').map(s => s.trim()).filter(Boolean);
      preEmoEl.innerHTML = preList.length > 0
        ? preList.map(e => `<span class="chip-btn active" style="cursor:default;">${this.escapeHtml(e)}</span>`).join('')
        : '<span style="color:#6b7280;font-size:12px;">No pre-trade emotion logged</span>';
    }

    const duringEmoEl = document.getElementById('tdEmotionDuringDisplay');
    if (duringEmoEl) {
      const duringList = (trade.emotion_during || '').split(',').map(s => s.trim()).filter(Boolean);
      duringEmoEl.innerHTML = duringList.length > 0
        ? duringList.map(e => `<span class="chip-btn active" style="cursor:default;">${this.escapeHtml(e)}</span>`).join('')
        : '<span style="color:#6b7280;font-size:12px;">No in-trade emotion logged</span>';
    }

    // Structured Notes
    if (document.getElementById('tdPreNotesInput')) {
      document.getElementById('tdPreNotesInput').value = trade.pre_trade_notes || '';
    }
    if (document.getElementById('tdPostNotesInput')) {
      document.getElementById('tdPostNotesInput').value = trade.post_trade_notes || '';
    }
    if (document.getElementById('tdKeyLearningsInput')) {
      document.getElementById('tdKeyLearningsInput').value = trade.key_learnings || '';
    }
    const legacyNotesEl = document.getElementById('tdNotesInput');
    const legacyContainer = document.getElementById('tdLegacyNotesContainer');
    if (legacyNotesEl) {
      legacyNotesEl.value = trade.notes || '';
      if (legacyContainer) {
        const combined = [trade.pre_trade_notes, trade.post_trade_notes, trade.key_learnings].filter(Boolean).join('\n\n');
        if (trade.notes && trade.notes !== combined) {
          legacyContainer.style.display = 'block';
        } else {
          legacyContainer.style.display = 'none';
        }
      }
    }

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
    const tdNotesIn = document.getElementById('tdNotesInput');
    if (tdNotesIn) tdNotesIn.value = trade.notes || '';
    const tdEmoSel = document.getElementById('tdEmotionSelect');
    if (tdEmoSel) tdEmoSel.value = trade.emotions || 'Disciplined';
    const tdRatingSel = document.getElementById('tdRatingSelect');
    if (tdRatingSel) tdRatingSel.value = trade.rating || 5;

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
      container.innerHTML = '<span style="font-size:12px;color:#6b7280;">No screenshots for this trade yet.</span>';
      return;
    }

    container.innerHTML = this.screenshots.map((screenshot, index) => `
      <div style="position:relative;width:132px;cursor:pointer;" onclick="TradeDetail.openScreenshotViewer(${index})" title="Open screenshot">
        <img src="${this.escapeHtml(screenshot.image_url)}" alt="${this.escapeHtml(screenshot.caption || 'Trade screenshot')}" loading="lazy" style="display:block;width:132px;height:88px;object-fit:cover;border-radius:6px;border:1px solid #263247;background:#090d16;">
        <div style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap;padding:4px 2px 0;font-size:11px;color:#cbd5e1;">${this.escapeHtml(screenshot.caption || 'TradingView')}</div>
        <button type="button" class="btn btn-secondary btn-sm" onclick="event.stopPropagation();TradeDetail.deleteScreenshot(${screenshot.id})" style="position:absolute;top:4px;right:4px;padding:1px 6px;color:#ef4444;background:#090d16dd;" aria-label="Delete screenshot">×</button>
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
      statusEl.innerHTML = '<span style="color:#ef4444;">Please enter a TradingView link first.</span>';
      return;
    }

    try {
      await API.addTradeScreenshot(this.currentTradeId, {
        source_url,
        caption
      });
      App.showToast('Screenshot added.', 'success');
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
    if (!confirm('Are you sure you want to delete this screenshot?')) return;
    try {
      await API.deleteTradeScreenshot(this.currentTradeId, screenshotId);
      App.showToast('Screenshot deleted.', 'success');
      await this.open(this.currentTradeId, this.currentTimeframe);
      Trades.load();
    } catch (err) {
      App.showToast(`Failed to delete screenshot: ${err.message}`, 'error');
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
    this.activeTimeframe = data.timeframe || (this.currentTimeframe !== 'AUTO' ? this.currentTimeframe : 'M15');

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
          <div style="font-weight:600;font-size:15px;color:#e2e8f0;margin-bottom:6px;">No Real Broker Candles Stored</div>
          <div style="font-size:13px;max-width:440px;line-height:1.5;color:#9ca3af;">${this.escapeHtml(data.message || 'No real broker candles have been stored for this trade yet. Please run a sync in the updated EA or cBot.')}</div>
          <div style="display:flex;gap:8px;margin-top:14px;flex-wrap:wrap;justify-content:center;">
            ${this.currentTimeframe !== 'AUTO' ? '<button type="button" class="btn btn-primary btn-sm" onclick="TradeDetail.switchTimeframe(\'AUTO\')">🎯 Switch to Auto Timeframe</button>' : ''}
            <button type="button" class="btn btn-secondary btn-sm" onclick="TradeDetail.syncAndReload()">🔄 Refresh / Check Sync</button>
          </div>
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
        scaleMargins: { top: 0.1, bottom: 0.1 },
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

    // 2. Trade Entry & Exit Markers
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

    // Synchronize KPI cards with detected SL and multiple TPs
    const tpLines = (data.price_lines || []).filter(pl => pl.title && pl.title.startsWith('TP'));
    const tpEl = document.getElementById('tdTP');
    if (tpEl && tpLines.length > 0) {
      if (tpLines.length > 1) {
        tpEl.innerHTML = tpLines.map((l, idx) => {
          const tpLabel = l.title.includes(':') ? l.title.split(':')[0].trim() : `TP${idx + 1}`;
          return `<div style="color:#10b981;font-weight:700;line-height:1.35;">${this.escapeHtml(tpLabel)}: ${l.price}</div>`;
        }).join('');
      } else {
        tpEl.textContent = tpLines[0].price;
      }
    }
    const slLine = (data.price_lines || []).find(pl => pl.title && pl.title.startsWith('SL'));
    const slEl = document.getElementById('tdSL');
    if (slEl && slLine) {
      slEl.textContent = slLine.price;
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
      const data = await API.getChartData(this.currentTradeId, tf, 2000);
      this.initChart(chartContainer, data);
      this.updateLiveCandle();
    } catch (err) {
      App.showToast(`Error changing timeframe: ${err.message}`, 'error');
    }
  },

  async saveChanges() {
    if (!this.currentTradeId) return;
    const pre_trade_notes = document.getElementById('tdPreNotesInput')?.value || '';
    const post_trade_notes = document.getElementById('tdPostNotesInput')?.value || '';
    const key_learnings = document.getElementById('tdKeyLearningsInput')?.value || '';
    const legacyNotes = document.getElementById('tdNotesInput')?.value || '';
    const notes = [pre_trade_notes, post_trade_notes, key_learnings].filter(Boolean).join('\n\n') || legacyNotes;

    const setup_id = document.getElementById('tdSetupSelect')?.value ? parseInt(document.getElementById('tdSetupSelect').value) : null;
    const mistake_id = document.getElementById('tdMistakeSelect')?.value ? parseInt(document.getElementById('tdMistakeSelect').value) : null;
    const rating = parseInt(document.getElementById('tdRatingSelect')?.value || 5);

    const updatePayload = {
      notes,
      pre_trade_notes,
      post_trade_notes,
      key_learnings,
      setup_id,
      mistake_id,
      rating
    };

    try {
      const subTrades = (this.currentTrade && Array.isArray(this.currentTrade.sub_trades)) ? this.currentTrade.sub_trades : [];
      if (subTrades.length > 1) {
        for (const leg of subTrades) {
          await API.updateTrade(leg.id, updatePayload);
        }
      } else {
        await API.updateTrade(this.currentTradeId, updatePayload);
      }
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
  },

  async syncAndReload() {
    if (!this.currentTradeId) return;
    const btn = document.getElementById('tdBtnSync');
    const origText = btn ? btn.innerHTML : '';
    if (btn) {
      btn.disabled = true;
      btn.innerHTML = '🔄 Syncing...';
    }

    try {
      // If the trade belongs to a cTrader Open API account, attempt an active cloud sync
      const trade = this.currentTrade || await API.getTrade(this.currentTradeId);
      if (trade && trade.account_id) {
        try {
          const accounts = await API.getAccounts();
          const acc = accounts.find(a => a.id === trade.account_id);
          if (acc && acc.platform === 'cTrader' && acc.ctrader_account_id) {
            await API.syncCtrader({ account_id: acc.id });
          }
        } catch (syncErr) {
          console.warn('Active sync attempt skipped:', syncErr);
        }
      }

      // Re-fetch chart data and trade details
      const [data, updatedTrade] = await Promise.all([
        API.getChartData(this.currentTradeId, this.currentTimeframe, 2000),
        API.getTrade(this.currentTradeId)
      ]);
      this.currentTrade = updatedTrade;
      this.renderTradeInfo(updatedTrade);
      const chartContainer = document.getElementById('tvChartContainer');
      this.initChart(chartContainer, data);

      if (data.candles && data.candles.length > 0) {
        App.showToast('Chart candles loaded successfully.', 'success');
      } else {
        App.showToast(
          'No broker candles received yet. To sync candles, run or click "Sync to Journal" in your MetaTrader EA or cBot.',
          'info'
        );
      }
    } catch (err) {
      App.showToast(`Refresh failed: ${err.message}`, 'error');
    } finally {
      if (btn) {
        btn.disabled = false;
        btn.innerHTML = origText;
      }
    }
  },

  startLiveUpdate() {
    this.stopLiveUpdate();
    this.liveUpdateTimer = setInterval(() => {
      this.updateLiveCandle();
    }, 5000);
  },

  stopLiveUpdate() {
    if (this.liveUpdateTimer) {
      clearInterval(this.liveUpdateTimer);
      this.liveUpdateTimer = null;
    }
  },

  async updateLiveCandle() {
    if (!this.currentTradeId || !this.candleSeries) return;
    const modal = document.getElementById('tradeDetailModal');
    if (!modal || !modal.classList.contains('active')) {
      this.stopLiveUpdate();
      return;
    }
    const tf = (this.currentTimeframe === 'AUTO' || !this.currentTimeframe)
      ? (this.activeTimeframe || 'M15')
      : this.currentTimeframe;
    try {
      const res = await API.getLatestCandle(this.currentTradeId, tf);
      if (res && res.candle && this.candleSeries) {
        this.candleSeries.update(res.candle);
        if (this.volumeSeries && res.candle.volume !== undefined) {
          this.volumeSeries.update({
            time: res.candle.time,
            value: res.candle.volume,
            color: res.candle.close >= res.candle.open ? 'rgba(16, 185, 129, 0.4)' : 'rgba(239, 68, 68, 0.4)'
          });
        }
        if (this.currentTrade && this.currentTrade.status === 'OPEN') {
          const exitEl = document.getElementById('tdExitPrice');
          if (exitEl) {
            exitEl.textContent = Number(res.candle.close).toFixed(5);
          }
        }
      }
    } catch (e) {
      // Non-fatal, live polling can fail silently on network interruptions
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
