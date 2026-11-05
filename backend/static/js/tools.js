/**
 * tools.js — Tools Page Controller
 * Allows inspecting registered tools, manually executing them with custom arguments, and creating new tools.
 */

const ToolsManager = {
  tools: {},
  selectedToolName: null,
  jsonMode: false,

  init() {
    this.setupEventListeners();
  },

  setupEventListeners() {
    // Search
    document.getElementById('tool-search-input')?.addEventListener('input', (e) => this.renderToolsList(e.target.value));

    // Toggle Form / JSON mode
    document.getElementById('btn-toggle-json-input')?.addEventListener('click', () => this.toggleJsonMode());

    // Run tool button
    document.getElementById('btn-run-tool')?.addEventListener('click', () => this.executeSelectedTool());

    // Create Tool Modal
    document.getElementById('btn-open-create-tool')?.addEventListener('click', () => {
      document.getElementById('new-tool-filename').value = '';
      document.getElementById('new-tool-code').value = '';
      App.openModal('modal-create-tool');
    });

    document.getElementById('btn-save-create-tool')?.addEventListener('click', () => this.saveNewTool());
  },

  async loadTools() {
    try {
      const res = await fetch('/api/tools');
      if (!res.ok) throw new Error(await res.text());
      this.tools = await res.json();
      this.renderToolsList();

      const toolNames = Object.keys(this.tools);
      if (toolNames.length > 0 && !this.selectedToolName) {
        this.selectTool(toolNames[0]);
      }
    } catch (e) {
      App.toast(`Failed to load tools: ${e.message}`, 'error');
    }
  },

  renderToolsList(filter = '') {
    const container = document.getElementById('tools-list-container');
    if (!container) return;
    container.innerHTML = '';

    const q = filter.toLowerCase().trim();
    const names = Object.keys(this.tools).filter(name => name.toLowerCase().includes(q));

    if (names.length === 0) {
      container.innerHTML = `<div style="color: var(--text-faint); padding: 18px; text-align: center;">No tools matched</div>`;
      return;
    }

    names.forEach(name => {
      const info = this.tools[name];
      const item = document.createElement('div');
      item.className = `tool-card-item ${name === this.selectedToolName ? 'active' : ''}`;
      item.onclick = () => this.selectTool(name);

      const paramsCount = Object.keys(info.parameter || {}).length;

      item.innerHTML = `
        <div class="tool-card-title">
          <span><i class="fa-solid fa-wrench" style="color: var(--accent-secondary); margin-right: 6px;"></i> ${name}</span>
          <span style="font-size: 11px; color: var(--text-faint);">${paramsCount} arg${paramsCount === 1 ? '' : 's'}</span>
        </div>
        <div class="tool-card-desc">${info.description || 'No description provided'}</div>
      `;
      container.appendChild(item);
    });
  },

  selectTool(name) {
    this.selectedToolName = name;
    this.renderToolsList(document.getElementById('tool-search-input')?.value || '');

    const info = this.tools[name];
    if (!info) return;

    document.getElementById('selected-tool-name').textContent = name;
    document.getElementById('selected-tool-desc').textContent = info.description || 'No description available for this tool.';
    
    const modBadge = document.getElementById('selected-tool-module');
    if (modBadge) {
      modBadge.style.display = 'inline-flex';
      modBadge.textContent = info.module || 'tool';
    }

    document.getElementById('tool-execution-section').style.display = 'flex';
    document.getElementById('tool-execution-meta').style.display = 'none';
    document.getElementById('tool-output-console').textContent = 'Ready to execute...';

    this.buildDynamicForm(info.parameter || {});
  },

  buildDynamicForm(parameters) {
    const formContainer = document.getElementById('dynamic-params-form');
    if (!formContainer) return;
    formContainer.innerHTML = '';

    const paramNames = Object.keys(parameters);
    if (paramNames.length === 0) {
      formContainer.innerHTML = `<p style="color: var(--text-muted); font-size: 13px; font-style: italic;">This tool requires no input arguments.</p>`;
      document.getElementById('raw-json-params').value = '{}';
      return;
    }

    const defaultJson = {};

    paramNames.forEach(paramName => {
      const paramInfo = parameters[paramName] || {};
      const isReq = paramInfo.required !== false;
      const defVal = paramInfo.default !== undefined ? paramInfo.default : '';
      defaultJson[paramName] = defVal;

      const group = document.createElement('div');
      group.className = 'param-form-group';

      group.innerHTML = `
        <label class="param-form-label">
          ${paramName} ${isReq ? '<span class="req">*</span>' : '<span style="color:var(--text-faint); font-weight:normal;">(optional)</span>'}
        </label>
        <input type="text" class="input-control tool-param-input" data-param="${paramName}" value="${defVal}" placeholder="Enter ${paramName}...">
      `;
      formContainer.appendChild(group);
    });

    document.getElementById('raw-json-params').value = JSON.stringify(defaultJson, null, 2);
  },

  toggleJsonMode() {
    this.jsonMode = !this.jsonMode;
    const formEl = document.getElementById('dynamic-params-form');
    const jsonEl = document.getElementById('raw-json-params-wrapper');
    const btn = document.getElementById('btn-toggle-json-input');

    if (this.jsonMode) {
      // Sync form to json
      const args = this.gatherArgsFromForm();
      document.getElementById('raw-json-params').value = JSON.stringify(args, null, 2);
      formEl.style.display = 'none';
      jsonEl.style.display = 'block';
      btn.innerHTML = `<i class="fa-solid fa-list-check"></i> Form Mode`;
    } else {
      // Sync json to form
      try {
        const parsed = JSON.parse(document.getElementById('raw-json-params').value || '{}');
        document.querySelectorAll('.tool-param-input').forEach(inp => {
          const k = inp.getAttribute('data-param');
          if (k in parsed) inp.value = parsed[k];
        });
      } catch (e) {}
      formEl.style.display = 'block';
      jsonEl.style.display = 'none';
      btn.innerHTML = `<i class="fa-solid fa-code"></i> JSON Mode`;
    }
  },

  gatherArgsFromForm() {
    const args = {};
    document.querySelectorAll('.tool-param-input').forEach(inp => {
      const k = inp.getAttribute('data-param');
      let val = inp.value;
      // Try to parse numbers or booleans if applicable
      if (val === 'true') val = true;
      else if (val === 'false') val = false;
      else if (!isNaN(val) && val.trim() !== '') {
        val = Number(val);
      }
      args[k] = val;
    });
    return args;
  },

  async executeSelectedTool() {
    if (!this.selectedToolName) return;

    let args = {};
    if (this.jsonMode) {
      try {
        args = JSON.parse(document.getElementById('raw-json-params').value || '{}');
      } catch (e) {
        App.toast('Invalid JSON in arguments: ' + e.message, 'error');
        return;
      }
    } else {
      args = this.gatherArgsFromForm();
    }

    const runBtn = document.getElementById('btn-run-tool');
    const outputConsole = document.getElementById('tool-output-console');
    const metaContainer = document.getElementById('tool-execution-meta');
    const statusBadge = document.getElementById('tool-status-badge');
    const durBadge = document.getElementById('tool-duration-badge');

    runBtn.disabled = true;
    runBtn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Executing...`;
    outputConsole.textContent = 'Running tool in background...';

    try {
      const res = await fetch('/api/tools/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          tool_name: this.selectedToolName,
          arguments: args,
        }),
      });

      const data = await res.json();
      metaContainer.style.display = 'flex';
      durBadge.textContent = `${data.duration_ms} ms`;

      if (data.success) {
        statusBadge.className = 'badge badge-success';
        statusBadge.textContent = 'Success';
        
        let outputStr = '';
        if (typeof data.result === 'object') {
          outputStr = JSON.stringify(data.result, null, 2);
        } else {
          outputStr = String(data.result);
        }
        outputConsole.textContent = outputStr;
        App.toast(`Tool '${this.selectedToolName}' executed in ${data.duration_ms}ms`, 'success');
      } else {
        statusBadge.className = 'badge badge-danger';
        statusBadge.textContent = 'Failed';
        outputConsole.textContent = `Error:\n${data.error}`;
        App.toast(`Tool execution failed: ${data.error}`, 'error');
      }
    } catch (e) {
      metaContainer.style.display = 'flex';
      statusBadge.className = 'badge badge-danger';
      statusBadge.textContent = 'Error';
      outputConsole.textContent = String(e);
      App.toast('Network error during execution', 'error');
    } finally {
      runBtn.disabled = false;
      runBtn.innerHTML = `<i class="fa-solid fa-play"></i> Run Tool`;
    }
  },

  async saveNewTool() {
    const filename = document.getElementById('new-tool-filename').value.trim();
    const content = document.getElementById('new-tool-code').value.trim();

    if (!filename || !content) {
      App.toast('File name and python code are required', 'error');
      return;
    }

    try {
      const res = await fetch('/api/tools/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ file_name: filename, content: content }),
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();

      App.closeModal('modal-create-tool');
      App.toast(`Tool '${filename}' created and registered!`, 'success');
      await this.loadTools();
      App.fetchStats();
    } catch (e) {
      App.toast(`Failed to create tool: ${e.message}`, 'error');
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  ToolsManager.init();
});
