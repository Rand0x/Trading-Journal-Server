/**
 * Lightweight SVG chart helpers (bars, rings, sparklines, split bars).
 * Pure DOM/SVG, no dependencies; colours come from the CSS design tokens.
 */
const Charts = {
  COLORS: {
    pos: '#10b981',
    neg: '#ef4444',
    accent: '#4f8cff',
    track: '#161e2c',
    muted: '#647087',
  },

  esc(value) {
    return String(value ?? '').replace(/[&<>'"]/g, c => ({
      '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
    }[c]));
  },

  empty(container, message) {
    if (!container) return;
    container.innerHTML = `<div class="empty-state">${this.esc(message)}</div>`;
  },

  // ---------- Tooltip (one shared element, driven by data-tip attributes) ----------
  _tooltip: null,

  ensureTooltip() {
    if (this._tooltip || typeof document === 'undefined' || !document.body) return;
    const tip = document.createElement('div');
    tip.className = 'chart-tooltip';
    document.body.appendChild(tip);
    this._tooltip = tip;
    document.addEventListener('mouseover', e => {
      const target = e.target.closest && e.target.closest('[data-tip]');
      if (!target) { tip.classList.remove('visible'); return; }
      tip.innerHTML = target.getAttribute('data-tip');
      tip.classList.add('visible');
    });
    document.addEventListener('mousemove', e => {
      if (!tip.classList.contains('visible')) return;
      const pad = 14;
      let x = e.clientX + pad;
      let y = e.clientY + pad;
      const rect = tip.getBoundingClientRect();
      if (x + rect.width > window.innerWidth - 8) x = e.clientX - rect.width - pad;
      if (y + rect.height > window.innerHeight - 8) y = e.clientY - rect.height - pad;
      tip.style.left = `${x}px`;
      tip.style.top = `${y}px`;
    });
  },

  // ---------- Vertical bar chart with a zero baseline ----------
  /**
   * items: [{ label, value, tip?, color? }]
   * opts: { height, format(value), showValues, minBarWidth }
   */
  bars(container, items, opts = {}) {
    if (!container) return;
    this.ensureTooltip();
    if (!items || !items.length) {
      this.empty(container, opts.emptyText || 'No data for this period yet.');
      return;
    }
    const width = Math.max(container.clientWidth || 0, 280);
    const height = opts.height || 220;
    const pad = { top: 14, right: 8, bottom: opts.hideLabels ? 8 : 26, left: 54 };
    const chartW = width - pad.left - pad.right;
    const chartH = height - pad.top - pad.bottom;
    const format = opts.format || (v => String(v));

    const values = items.map(i => Number(i.value) || 0);
    let max = Math.max(0, ...values);
    let min = Math.min(0, ...values);
    if (max === min) { max += 1; }
    const range = max - min;
    const y = v => pad.top + ((max - v) / range) * chartH;
    const zeroY = y(0);

    const step = chartW / items.length;
    const barW = Math.max(opts.minBarWidth || 2, Math.min(38, step * 0.66));

    // Gridlines: max, zero, min
    const ticks = [max, 0, min].filter((v, idx, arr) => arr.indexOf(v) === idx);
    let svg = `<svg class="svg-chart" viewBox="0 0 ${width} ${height}" height="${height}" preserveAspectRatio="none">`;
    ticks.forEach(t => {
      const ty = y(t);
      svg += `<line class="${t === 0 ? 'zero-line' : 'grid-line'}" x1="${pad.left}" x2="${width - pad.right}" y1="${ty}" y2="${ty}" ${t === 0 ? '' : 'stroke-dasharray="3 4"'}/>`;
      svg += `<text x="${pad.left - 8}" y="${ty + 4}" text-anchor="end">${this.esc(format(t, true))}</text>`;
    });

    const labelEvery = Math.max(1, Math.ceil(items.length / Math.max(1, Math.floor(chartW / 46))));
    items.forEach((item, idx) => {
      const v = Number(item.value) || 0;
      const x = pad.left + idx * step + (step - barW) / 2;
      const top = v >= 0 ? y(v) : zeroY;
      const h = Math.max(v === 0 ? 0 : 1.5, Math.abs(y(v) - zeroY));
      const color = item.color || (v >= 0 ? this.COLORS.pos : this.COLORS.neg);
      const tip = item.tip || `<strong>${this.esc(item.label)}</strong><br>${this.esc(format(v))}`;
      svg += `<rect class="bar" x="${x}" y="${top}" width="${barW}" height="${h}" rx="${Math.min(4, barW / 3)}" fill="${color}" data-tip="${this.esc(tip)}"/>`;
      // Invisible hit area so thin bars are easy to hover
      svg += `<rect x="${pad.left + idx * step}" y="${pad.top}" width="${step}" height="${chartH}" fill="transparent" data-tip="${this.esc(tip)}"/>`;
      if (!opts.hideLabels && idx % labelEvery === 0) {
        svg += `<text x="${x + barW / 2}" y="${height - 8}" text-anchor="middle">${this.esc(item.short || item.label)}</text>`;
      }
    });
    svg += '</svg>';
    container.innerHTML = svg;
  },

  // ---------- Horizontal bars (ranked lists) ----------
  /** items: [{ label, value, sub? }] */
  hbars(container, items, opts = {}) {
    if (!container) return;
    if (!items || !items.length) {
      this.empty(container, opts.emptyText || 'No data yet.');
      return;
    }
    const format = opts.format || (v => String(v));
    const maxAbs = Math.max(...items.map(i => Math.abs(Number(i.value) || 0)), 1);
    container.innerHTML = `<div class="meter-list">${items.map(item => {
      const v = Number(item.value) || 0;
      const pct = Math.max(2, Math.abs(v) / maxAbs * 100);
      const color = v >= 0 ? this.COLORS.pos : this.COLORS.neg;
      return `<div class="meter-row">
        <span class="meter-name">${this.esc(item.label)}${item.sub ? ` <span style="color:var(--text-dim);">· ${this.esc(item.sub)}</span>` : ''}</span>
        <span class="meter-value" style="color:${color};">${this.esc(format(v))}</span>
        <div class="meter-track"><div class="meter-fill" style="width:${pct}%;background:${color};"></div></div>
      </div>`;
    }).join('')}</div>`;
  },

  // ---------- Donut ring ----------
  /** segments: [{ value, color }] or a single percent via opts.percent */
  ring(container, opts = {}) {
    if (!container) return;
    const size = opts.size || 64;
    const stroke = opts.stroke || 7;
    const r = (size - stroke) / 2;
    const c = 2 * Math.PI * r;
    let segments = opts.segments;
    if (!segments) {
      const pct = Math.max(0, Math.min(100, Number(opts.percent) || 0));
      segments = [{ value: pct, color: opts.color || this.COLORS.accent }];
    }
    const total = opts.segments ? segments.reduce((s, seg) => s + seg.value, 0) || 1 : 100;
    let offset = 0;
    let arcs = '';
    segments.forEach(seg => {
      const len = (seg.value / total) * c;
      if (len <= 0) return;
      arcs += `<circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${seg.color}" stroke-width="${stroke}"
        stroke-dasharray="${len} ${c - len}" stroke-dashoffset="${-offset}" stroke-linecap="${segments.length === 1 ? 'round' : 'butt'}"/>`;
      offset += len;
    });
    container.style.width = `${size}px`;
    container.style.height = `${size}px`;
    container.innerHTML = `
      <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
        <circle cx="${size / 2}" cy="${size / 2}" r="${r}" fill="none" stroke="${this.COLORS.track}" stroke-width="${stroke}"/>
        ${arcs}
      </svg>
      ${opts.label !== undefined ? `<div class="ring-label" style="font-size:${opts.fontSize || 15}px;">
        <span>${this.esc(opts.label)}${opts.sub ? `<small>${this.esc(opts.sub)}</small>` : ''}</span></div>` : ''}`;
  },

  // ---------- Sparkline ----------
  sparkline(container, values, opts = {}) {
    if (!container) return;
    if (!values || values.length < 2) { container.innerHTML = ''; return; }
    const width = 200;
    const height = 34;
    const min = Math.min(...values);
    const max = Math.max(...values);
    const range = (max - min) || 1;
    const pts = values.map((v, i) => [
      (i / (values.length - 1)) * width,
      height - 2 - ((v - min) / range) * (height - 4),
    ]);
    const color = opts.color || (values[values.length - 1] >= values[0] ? this.COLORS.pos : this.COLORS.neg);
    const line = pts.map((p, i) => `${i ? 'L' : 'M'}${p[0].toFixed(1)},${p[1].toFixed(1)}`).join(' ');
    const gid = `spark-${Math.random().toString(36).slice(2, 8)}`;
    container.innerHTML = `
      <svg viewBox="0 0 ${width} ${height}" preserveAspectRatio="none">
        <defs><linearGradient id="${gid}" x1="0" x2="0" y1="0" y2="1">
          <stop offset="0" stop-color="${color}" stop-opacity="0.28"/><stop offset="1" stop-color="${color}" stop-opacity="0"/>
        </linearGradient></defs>
        <path d="${line} L${width},${height} L0,${height} Z" fill="url(#${gid})"/>
        <path d="${line}" fill="none" stroke="${color}" stroke-width="1.8" vector-effect="non-scaling-stroke"/>
      </svg>`;
  },

  // ---------- Positive vs negative split bar ----------
  splitBar(container, pos, neg) {
    if (!container) return;
    const p = Math.max(0, Number(pos) || 0);
    const n = Math.max(0, Number(neg) || 0);
    const total = p + n;
    if (!total) { container.innerHTML = ''; return; }
    container.innerHTML = `<span class="pos" style="width:${(p / total) * 100}%"></span><span class="neg" style="width:${(n / total) * 100}%"></span>`;
  },
};
