/**
 * db_updater.js — DB Updater Controller
 * Full visual GUI management for Providers, Models, and API Keys without terminal or SQL query.
 */

const DBUpdater = {
  providers: [],
  models: [],
  apiKeys: [],

  init() {
    this.setupTabs();
    this.setupEventListeners();
  },

  setupTabs() {
    const tabBtns = document.querySelectorAll('.db-tab-btn');
    const tabPanes = document.querySelectorAll('.db-tab-pane');

    tabBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        const targetTab = btn.getAttribute('data-tab');
        if (!targetTab) return;

        tabBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');

        tabPanes.forEach(pane => {
          if (pane.id === targetTab) {
            pane.classList.add('active');
          } else {
            pane.classList.remove('active');
          }
        });
      });
    });
  },

  setupEventListeners() {
    // Add Buttons
    document.getElementById('btn-add-provider')?.addEventListener('click', () => this.openProviderModal());
    document.getElementById('btn-add-model')?.addEventListener('click', () => this.openModelModal());
    document.getElementById('btn-add-key')?.addEventListener('click', () => this.openKeyModal());

    // Save Buttons
    document.getElementById('btn-save-provider')?.addEventListener('click', () => this.saveProvider());
    document.getElementById('btn-save-model')?.addEventListener('click', () => this.saveModel());
    document.getElementById('btn-save-key')?.addEventListener('click', () => this.saveKey());

    // Search / Filter inputs
    document.getElementById('search-providers')?.addEventListener('input', (e) => this.renderProviders(e.target.value));
    document.getElementById('search-models')?.addEventListener('input', (e) => this.renderModels(e.target.value));
    document.getElementById('search-keys')?.addEventListener('input', (e) => this.renderKeys(e.target.value));
  },

  async loadAll() {
    await Promise.all([
      this.loadProviders(),
      this.loadModels(),
      this.loadKeys(),
    ]);
  },

  // --------------------------------------------------------------------------
  // Providers CRUD
  // --------------------------------------------------------------------------

  async loadProviders() {
    try {
      const res = await fetch('/api/providers');
      if (!res.ok) throw new Error(await res.text());
      this.providers = await res.json();
      this.renderProviders();
      this.populateProviderDropdowns();
    } catch (e) {
      App.toast(`Failed to load providers: ${e.message}`, 'error');
    }
  },

  renderProviders(filter = '') {
    const tbody = document.querySelector('#table-providers tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    const q = filter.toLowerCase().trim();
    const filtered = this.providers.filter(p => 
      p.name.toLowerCase().includes(q) || p.base_url.toLowerCase().includes(q)
    );

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="7" style="text-align:center; color: var(--text-faint); padding: 24px;">No providers found</td></tr>`;
      return;
    }

    filtered.forEach(p => {
      const tr = document.createElement('tr');
      const badgeClass = p.status === 'active' ? 'badge-active' : (p.status === 'cooldown' ? 'badge-cooldown' : 'badge-disabled');
      const lastMod = p.last_modify ? new Date(p.last_modify).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '-';

      tr.innerHTML = `
        <td><strong style="color: var(--text-faint);">#${p.id}</strong></td>
        <td><strong style="color: #fff; font-size: 14px;">${p.name}</strong></td>
        <td><code style="max-width: 320px; display: inline-block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${p.base_url}</code></td>
        <td><span class="badge ${badgeClass}">${p.status}</span></td>
        <td>${p.rate_limit || '<span style="color:var(--text-faint)">None</span>'}</td>
        <td style="color: var(--text-muted); font-size: 12px;">${lastMod}</td>
        <td>
          <div class="actions-cell">
            <button class="btn btn-secondary btn-sm" onclick="DBUpdater.editProvider(${p.id})">
              <i class="fa-solid fa-pen-to-square"></i> Edit
            </button>
            <button class="btn btn-secondary btn-sm" onclick="DBUpdater.toggleProviderStatus(${p.id}, '${p.status}')" title="Cycle Status">
              <i class="fa-solid fa-power-off"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="DBUpdater.deleteProvider(${p.id})">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  },

  openProviderModal(p = null) {
    document.getElementById('modal-provider-title').textContent = p ? 'Edit Provider' : 'Add New Provider';
    document.getElementById('provider-id-input').value = p ? p.id : '';
    document.getElementById('provider-name-input').value = p ? p.name : '';
    document.getElementById('provider-url-input').value = p ? p.base_url : '';
    document.getElementById('provider-status-input').value = p ? p.status : 'active';
    App.openModal('modal-provider');
  },

  editProvider(id) {
    const p = this.providers.find(x => x.id === id);
    if (p) this.openProviderModal(p);
  },

  async saveProvider() {
    const id = document.getElementById('provider-id-input').value;
    const name = document.getElementById('provider-name-input').value.trim();
    const url = document.getElementById('provider-url-input').value.trim();
    const status = document.getElementById('provider-status-input').value;

    if (!name || !url) {
      App.toast('Name and Base URL are required', 'error');
      return;
    }

    try {
      const payload = { name, base_url: url, status };
      const endpoint = id ? `/api/providers/${id}` : '/api/providers';
      const method = id ? 'PUT' : 'POST';

      const res = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error(await res.text());

      App.closeModal('modal-provider');
      App.toast(`Provider '${name}' ${id ? 'updated' : 'added'} successfully!`, 'success');
      await this.loadProviders();
      App.fetchStats();
    } catch (e) {
      App.toast(`Save failed: ${e.message}`, 'error');
    }
  },

  async toggleProviderStatus(id, current) {
    const next = current === 'active' ? 'cooldown' : (current === 'cooldown' ? 'disabled' : 'active');
    try {
      await fetch(`/api/providers/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: next }),
      });
      App.toast(`Provider status changed to ${next}`, 'info');
      await this.loadProviders();
      App.fetchStats();
    } catch (e) {
      App.toast(e.message, 'error');
    }
  },

  async deleteProvider(id) {
    if (!confirm(`Are you sure you want to delete Provider #${id}? All associated models and keys will also be removed.`)) return;
    try {
      await fetch(`/api/providers/${id}`, { method: 'DELETE' });
      App.toast(`Provider #${id} deleted`, 'info');
      await this.loadAll();
      App.fetchStats();
    } catch (e) {
      App.toast(`Delete failed: ${e.message}`, 'error');
    }
  },

  populateProviderDropdowns() {
    const modelSelect = document.getElementById('model-provider-select');
    const keySelect = document.getElementById('key-provider-select');

    const options = this.providers.map(p => `<option value="${p.id}">${p.name} (#${p.id})</option>`).join('');
    if (modelSelect) modelSelect.innerHTML = options;
    if (keySelect) keySelect.innerHTML = options;
  },

  // --------------------------------------------------------------------------
  // Models CRUD
  // --------------------------------------------------------------------------

  async loadModels() {
    try {
      const res = await fetch('/api/models');
      if (!res.ok) throw new Error(await res.text());
      this.models = await res.json();
      this.renderModels();
    } catch (e) {
      App.toast(`Failed to load models: ${e.message}`, 'error');
    }
  },

  renderModels(filter = '') {
    const tbody = document.querySelector('#table-models tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    const q = filter.toLowerCase().trim();
    const filtered = this.models.filter(m => 
      m.name.toLowerCase().includes(q) || (m.provider_name && m.provider_name.toLowerCase().includes(q))
    );

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--text-faint); padding: 24px;">No models found</td></tr>`;
      return;
    }

    filtered.forEach(m => {
      const tr = document.createElement('tr');
      const badgeClass = m.status === 'active' ? 'badge-active' : (m.status === 'cooldown' ? 'badge-cooldown' : 'badge-disabled');

      tr.innerHTML = `
        <td><strong style="color: var(--text-faint);">#${m.id}</strong></td>
        <td><span class="badge badge-info">${m.provider_name}</span></td>
        <td><strong style="color: #fff;">${m.name}</strong></td>
        <td><code style="color: var(--accent-secondary); font-weight: 600;">${m.model_size || 0}B</code></td>
        <td><span class="badge ${badgeClass}">${m.status}</span></td>
        <td style="font-size: 11px; color: var(--text-faint);">${m.RPM || '-'} / ${m.RPD || '-'}</td>
        <td style="font-size: 11px; color: var(--danger); max-width: 220px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          ${m.disabled_reason || '<span style="color:var(--text-faint)">-</span>'}
        </td>
        <td>
          <div class="actions-cell">
            <button class="btn btn-secondary btn-sm" onclick="DBUpdater.editModel(${m.id})">
              <i class="fa-solid fa-pen-to-square"></i>
            </button>
            <button class="btn btn-secondary btn-sm" onclick="DBUpdater.toggleModelStatus(${m.id}, '${m.status}')" title="Cycle Status">
              <i class="fa-solid fa-power-off"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="DBUpdater.deleteModel(${m.id})">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  },

  openModelModal(m = null) {
    document.getElementById('modal-model-title').textContent = m ? 'Edit Model' : 'Add New Model';
    document.getElementById('model-id-input').value = m ? m.id : '';
    document.getElementById('model-name-input').value = m ? m.name : '';
    document.getElementById('model-size-input').value = m ? m.model_size : 100;
    document.getElementById('model-status-input').value = m ? m.status : 'active';
    document.getElementById('model-rpm-input').value = m && m.RPM ? m.RPM : '';
    document.getElementById('model-tpm-input').value = m && m.TPM ? m.TPM : '';
    if (m && m.provider_id) {
      document.getElementById('model-provider-select').value = m.provider_id;
    }
    App.openModal('modal-model');
  },

  editModel(id) {
    const m = this.models.find(x => x.id === id);
    if (m) this.openModelModal(m);
  },

  async saveModel() {
    const id = document.getElementById('model-id-input').value;
    const provider_id = parseInt(document.getElementById('model-provider-select').value);
    const name = document.getElementById('model-name-input').value.trim();
    const model_size = parseFloat(document.getElementById('model-size-input').value) || 100.0;
    const status = document.getElementById('model-status-input').value;
    const rpmVal = document.getElementById('model-rpm-input').value;
    const tpmVal = document.getElementById('model-tpm-input').value;

    if (!name || isNaN(provider_id)) {
      App.toast('Provider and Model Name are required', 'error');
      return;
    }

    try {
      const payload = {
        provider_id,
        name,
        model_size,
        status,
        RPM: rpmVal ? parseInt(rpmVal) : null,
        TPM: tpmVal ? parseInt(tpmVal) : null,
      };

      const endpoint = id ? `/api/models/${id}` : '/api/models';
      const method = id ? 'PUT' : 'POST';

      const res = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error(await res.text());

      App.closeModal('modal-model');
      App.toast(`Model '${name}' saved successfully!`, 'success');
      await this.loadModels();
      App.fetchStats();
    } catch (e) {
      App.toast(`Save failed: ${e.message}`, 'error');
    }
  },

  async toggleModelStatus(id, current) {
    const next = current === 'active' ? 'cooldown' : (current === 'cooldown' ? 'disabled' : 'active');
    try {
      await fetch(`/api/models/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: next, disabled_reason: next === 'active' ? null : 'Manually modified from UI' }),
      });
      App.toast(`Model status set to ${next}`, 'info');
      await this.loadModels();
      App.fetchStats();
    } catch (e) {
      App.toast(e.message, 'error');
    }
  },

  async deleteModel(id) {
    if (!confirm(`Are you sure you want to delete Model #${id}?`)) return;
    try {
      await fetch(`/api/models/${id}`, { method: 'DELETE' });
      App.toast(`Model #${id} deleted`, 'info');
      await this.loadModels();
      App.fetchStats();
    } catch (e) {
      App.toast(e.message, 'error');
    }
  },

  // --------------------------------------------------------------------------
  // API Keys CRUD
  // --------------------------------------------------------------------------

  async loadKeys() {
    try {
      const res = await fetch('/api/api-keys');
      if (!res.ok) throw new Error(await res.text());
      this.apiKeys = await res.json();
      this.renderKeys();
    } catch (e) {
      App.toast(`Failed to load API keys: ${e.message}`, 'error');
    }
  },

  renderKeys(filter = '') {
    const tbody = document.querySelector('#table-keys tbody');
    if (!tbody) return;
    tbody.innerHTML = '';

    const q = filter.toLowerCase().trim();
    const filtered = this.apiKeys.filter(k => 
      k.unique_name.toLowerCase().includes(q) || k.env_key.toLowerCase().includes(q) || (k.provider_name && k.provider_name.toLowerCase().includes(q))
    );

    if (filtered.length === 0) {
      tbody.innerHTML = `<tr><td colspan="8" style="text-align:center; color: var(--text-faint); padding: 24px;">No API keys found</td></tr>`;
      return;
    }

    filtered.forEach(k => {
      const tr = document.createElement('tr');
      const badgeClass = k.status === 'active' ? 'badge-active' : (k.status === 'cooldown' ? 'badge-cooldown' : 'badge-disabled');
      const envBadge = k.env_configured 
        ? `<span class="badge badge-success"><i class="fa-solid fa-check"></i> Loaded</span>`
        : `<span class="badge badge-warning" title="Not found in .env / system environment"><i class="fa-solid fa-triangle-exclamation"></i> Missing</span>`;

      tr.innerHTML = `
        <td><strong style="color: var(--text-faint);">#${k.id}</strong></td>
        <td><span class="badge badge-info">${k.provider_name}</span></td>
        <td><strong style="color: #fff;">${k.unique_name}</strong></td>
        <td><code>${k.env_key}</code></td>
        <td>${envBadge}</td>
        <td><span class="badge ${badgeClass}">${k.status}</span></td>
        <td style="font-size: 11px; color: var(--danger); max-width: 200px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">
          ${k.disabled_reason || '<span style="color:var(--text-faint)">-</span>'}
        </td>
        <td>
          <div class="actions-cell">
            <button class="btn btn-secondary btn-sm" onclick="DBUpdater.editKey(${k.id})">
              <i class="fa-solid fa-pen-to-square"></i>
            </button>
            <button class="btn btn-secondary btn-sm" onclick="DBUpdater.toggleKeyStatus(${k.id}, '${k.status}')" title="Cycle Status">
              <i class="fa-solid fa-power-off"></i>
            </button>
            <button class="btn btn-danger btn-sm" onclick="DBUpdater.deleteKey(${k.id})">
              <i class="fa-solid fa-trash"></i>
            </button>
          </div>
        </td>
      `;
      tbody.appendChild(tr);
    });
  },

  openKeyModal(k = null) {
    document.getElementById('modal-key-title').textContent = k ? 'Edit API Key' : 'Add New API Key';
    document.getElementById('key-id-input').value = k ? k.id : '';
    document.getElementById('key-name-input').value = k ? k.unique_name : '';
    document.getElementById('key-env-input').value = k ? k.env_key : '';
    document.getElementById('key-status-input').value = k ? k.status : 'active';
    if (k && k.provider_id) {
      document.getElementById('key-provider-select').value = k.provider_id;
    }
    App.openModal('modal-key');
  },

  editKey(id) {
    const k = this.apiKeys.find(x => x.id === id);
    if (k) this.openKeyModal(k);
  },

  async saveKey() {
    const id = document.getElementById('key-id-input').value;
    const provider_id = parseInt(document.getElementById('key-provider-select').value);
    const unique_name = document.getElementById('key-name-input').value.trim();
    const env_key = document.getElementById('key-env-input').value.trim();
    const status = document.getElementById('key-status-input').value;

    if (!unique_name || !env_key || isNaN(provider_id)) {
      App.toast('Provider, Unique Name, and Env Key are required', 'error');
      return;
    }

    try {
      const payload = { provider_id, unique_name, env_key, status };
      const endpoint = id ? `/api/api-keys/${id}` : '/api/api-keys';
      const method = id ? 'PUT' : 'POST';

      const res = await fetch(endpoint, {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });

      if (!res.ok) throw new Error(await res.text());

      App.closeModal('modal-key');
      App.toast(`API Key '${unique_name}' saved!`, 'success');
      await this.loadKeys();
      App.fetchStats();
    } catch (e) {
      App.toast(`Save failed: ${e.message}`, 'error');
    }
  },

  async toggleKeyStatus(id, current) {
    const next = current === 'active' ? 'cooldown' : (current === 'cooldown' ? 'disabled' : 'active');
    try {
      await fetch(`/api/api-keys/${id}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: next, disabled_reason: next === 'active' ? null : 'Manually modified from UI' }),
      });
      App.toast(`API Key status set to ${next}`, 'info');
      await this.loadKeys();
      App.fetchStats();
    } catch (e) {
      App.toast(e.message, 'error');
    }
  },

  async deleteKey(id) {
    if (!confirm(`Are you sure you want to delete API Key #${id}?`)) return;
    try {
      await fetch(`/api/api-keys/${id}`, { method: 'DELETE' });
      App.toast(`API Key #${id} deleted`, 'info');
      await this.loadKeys();
      App.fetchStats();
    } catch (e) {
      App.toast(e.message, 'error');
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  DBUpdater.init();
});
