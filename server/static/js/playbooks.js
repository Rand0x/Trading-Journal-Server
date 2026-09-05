/**
 * Playbooks & Mistakes Management Module
 */

const Playbooks = {
  activePlaybookId: null,

  async load() {
    try {
      const [playbooks, mistakes] = await Promise.all([
        API.getPlaybooks(),
        API.getMistakes()
      ]);
      App.playbooks = playbooks;
      App.mistakes = mistakes;
      if (typeof Trades !== 'undefined' && Trades.populateSignalFilters) {
        Trades.populateSignalFilters();
      }
      this.renderPlaybooks(playbooks);
      this.renderMistakes(mistakes);
    } catch (err) {
      console.error('Failed to load playbooks/mistakes:', err);
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  renderPlaybooks(playbooks = []) {
    const container = document.getElementById('playbooksListContainer');
    if (!container) return;
    container.innerHTML = '';

    playbooks.forEach(p => {
      const card = document.createElement('div');
      card.className = 'playbook-card';
      const pnlClass = (p.total_pnl || 0) >= 0 ? 'color-green' : 'color-red';

      card.innerHTML = `
        <div class="playbook-card-header">
          <span class="playbook-card-title">${p.name}</span>
        </div>
        <p style="font-size:13px;color:#9ca3af;">${p.description || 'No description provided.'}</p>
        ${p.rules ? `<div style="background:#0a0e17;padding:10px;border-radius:6px;font-size:12px;white-space:pre-line;color:#cbd5e1;">${p.rules}</div>` : ''}
        <div style="display:flex;align-items:center;justify-content:space-between;border-top:1px solid #1f2937;padding-top:12px;margin-top:auto;">
          <div>
            <span style="font-size:11px;color:#6b7280;display:block;">PERFORMANCE</span>
            <span style="font-size:13px;font-weight:700;color:#60a5fa;">${p.trades_count || 0} Trades (${p.win_rate || 0}% WR)</span>
          </div>
          <div style="text-align:right;">
            <span style="font-size:11px;color:#6b7280;display:block;">NET P&L</span>
            <span style="font-size:14px;font-weight:700;" class="${pnlClass}">${App.formatMoney(p.total_pnl || 0, null, { showSign: true })}</span>
          </div>
          <div style="display:flex;gap:6px;">
            <button class="btn btn-secondary btn-sm" onclick="Playbooks.openEditPlaybook(${p.id})" title="Edit Playbook">
              ✏️
            </button>
            <button class="btn btn-secondary btn-sm" onclick="Playbooks.deletePlaybook(${p.id})" style="color:#ef4444;" title="Delete Playbook">
              🗑️
            </button>
          </div>
        </div>
      `;
      container.appendChild(card);
    });
  },

  renderMistakes(mistakes = []) {
    const container = document.getElementById('mistakesListContainer');
    if (!container) return;
    container.innerHTML = '';

    mistakes.forEach(m => {
      const card = document.createElement('div');
      card.className = 'playbook-card';
      const sevColor = m.severity === 'HIGH' ? '#ef4444' : (m.severity === 'MEDIUM' ? '#f59e0b' : '#3b82f6');

      card.innerHTML = `
        <div class="playbook-card-header">
          <span class="playbook-card-title">${m.name}</span>
          <span class="badge" style="background:${sevColor}22;color:${sevColor};border:1px solid ${sevColor}55;">
            ${m.severity} SEVERITY
          </span>
        </div>
        <p style="font-size:13px;color:#9ca3af;">${m.description || 'No description.'}</p>
        <div style="display:flex;align-items:center;justify-content:space-between;border-top:1px solid #1f2937;padding-top:12px;margin-top:auto;">
          <div>
            <span style="font-size:11px;color:#6b7280;display:block;">OCCURRENCES</span>
            <span style="font-size:13px;font-weight:700;color:#fff;">${m.occurrence_count || 0} times</span>
          </div>
          <div style="text-align:right;">
            <span style="font-size:11px;color:#6b7280;display:block;">TOTAL COST</span>
            <span style="font-size:14px;font-weight:700;color:#ef4444;">-${App.formatMoney(m.total_loss || 0)}</span>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="Playbooks.deleteMistake(${m.id})" style="color:#ef4444;" title="Delete Mistake">
            🗑️
          </button>
        </div>
      `;
      container.appendChild(card);
    });
  },

  openAddPlaybookModal() {
    this.activePlaybookId = null;
    document.getElementById('playbookForm').reset();
    document.getElementById('playbookModalTitle').textContent = 'New Playbook Setup';
    document.getElementById('playbookSubmitButton').textContent = 'Save Playbook';
    document.getElementById('addPlaybookModal').classList.add('active');
  },

  openEditPlaybook(id) {
    const playbook = (App.playbooks || []).find(item => item.id === id);
    if (!playbook) {
      App.showToast('Playbook not found. Please reload the page.', 'error');
      return;
    }

    this.activePlaybookId = id;
    document.getElementById('pbName').value = playbook.name || '';
    document.getElementById('pbDesc').value = playbook.description || '';
    document.getElementById('pbRules').value = playbook.rules || '';
    document.getElementById('playbookModalTitle').textContent = 'Edit Playbook Setup';
    document.getElementById('playbookSubmitButton').textContent = 'Save Changes';
    document.getElementById('addPlaybookModal').classList.add('active');
  },

  closePlaybookModal() {
    document.getElementById('addPlaybookModal').classList.remove('active');
  },

  async savePlaybook(e) {
    e.preventDefault();
    const name = document.getElementById('pbName').value.trim();
    const description = document.getElementById('pbDesc').value.trim();
    const rules = document.getElementById('pbRules').value.trim();

    try {
      const payload = { name, description, rules };
      if (this.activePlaybookId) {
        await API.updatePlaybook(this.activePlaybookId, payload);
        App.showToast('Playbook updated!', 'success');
      } else {
        await API.createPlaybook(payload);
        App.showToast('Playbook created!', 'success');
      }
      this.activePlaybookId = null;
      this.closePlaybookModal();
      this.load();
    } catch (err) {
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  async deletePlaybook(id) {
    if (!confirm('Delete this playbook?')) return;
    try {
      await API.deletePlaybook(id);
      App.showToast('Playbook deleted.', 'success');
      this.load();
    } catch (err) {
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  openAddMistakeModal() {
    document.getElementById('mistakeForm').reset();
    document.getElementById('addMistakeModal').classList.add('active');
  },

  closeMistakeModal() {
    document.getElementById('addMistakeModal').classList.remove('active');
  },

  async saveMistake(e) {
    e.preventDefault();
    const name = document.getElementById('mkName').value.trim();
    const description = document.getElementById('mkDesc').value.trim();
    const severity = document.getElementById('mkSeverity').value;

    try {
      await API.createMistake({ name, description, severity });
      App.showToast('Mistake created!', 'success');
      this.closeMistakeModal();
      this.load();
    } catch (err) {
      App.showToast(`Error: ${err.message}`, 'error');
    }
  },

  async deleteMistake(id) {
    if (!confirm('Delete this mistake?')) return;
    try {
      await API.deleteMistake(id);
      App.showToast('Mistake deleted.', 'success');
      this.load();
    } catch (err) {
      App.showToast(`Error: ${err.message}`, 'error');
    }
  }
};
