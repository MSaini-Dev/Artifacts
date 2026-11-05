/**
 * chat.js — Multi-Conversation Chat Controller
 * Manages isolated conversations (like ChatGPT/Gemini), history retention,
 * real-time switching, context recall, and autonomous tool-execution diagnostics.
 */

const ChatManager = {
  isSending: false,
  activeConversationId: null,
  conversations: [],
  searchQuery: '',

  init() {
    this.configureMarkdown();
    this.setupEventListeners();
    this.loadConversations();
  },

  configureMarkdown() {
    if (typeof marked !== 'undefined') {
      try {
        marked.setOptions({
          gfm: true,
          breaks: true,
          highlight: (code, lang) => {
            if (typeof hljs !== 'undefined') {
              const language = hljs.getLanguage(lang) ? lang : 'plaintext';
              try {
                return hljs.highlight(code, { language }).value;
              } catch {
                return hljs.highlightAuto(code).value;
              }
            }
            return code;
          }
        });
      } catch (e) {
        console.warn('Could not configure marked:', e);
      }
    }
  },

  setupEventListeners() {
    const sendBtn = document.getElementById('btn-send-chat');
    const inputArea = document.getElementById('chat-input');
    const newChatBtn = document.getElementById('btn-new-chat');
    const searchInput = document.getElementById('chat-search-input');
    const renameBtn = document.getElementById('btn-rename-chat');
    const deleteCurrentBtn = document.getElementById('btn-delete-current-chat');

    sendBtn?.addEventListener('click', () => this.sendMessage());

    inputArea?.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        this.sendMessage();
      }
    });

    newChatBtn?.addEventListener('click', () => this.createNewChat());

    searchInput?.addEventListener('input', (e) => {
      this.searchQuery = e.target.value.toLowerCase().trim();
      this.renderConversationsList();
    });

    renameBtn?.addEventListener('click', () => this.promptRenameChat());
    deleteCurrentBtn?.addEventListener('click', () => {
      if (this.activeConversationId) {
        this.deleteConversation(this.activeConversationId);
      }
    });
  },

  async loadConversations(autoSelect = true) {
    try {
      const res = await fetch('/api/conversations');
      const data = await res.json();
      this.conversations = Array.isArray(data) ? data : [];
      this.renderConversationsList();

      if (autoSelect) {
        if (this.conversations.length > 0) {
          // If current active is still in list, stay on it; otherwise pick first
          const exists = this.conversations.some(c => c.ID === this.activeConversationId);
          if (!exists) {
            this.selectConversation(this.conversations[0].ID);
          } else {
            this.updateHeaderTitle();
          }
        } else {
          // No conversations yet — create a clean one
          await this.createNewChat();
        }
      } else {
        this.updateHeaderTitle();
      }
    } catch (e) {
      console.error('Failed to load conversations:', e);
    }
  },

  renderConversationsList() {
    const list = document.getElementById('chat-conversations-list');
    if (!list) return;

    let filtered = this.conversations;
    if (this.searchQuery) {
      filtered = filtered.filter(c => (c.Title || '').toLowerCase().includes(this.searchQuery));
    }

    if (filtered.length === 0) {
      list.innerHTML = `
        <div style="padding: 24px 12px; text-align: center; color: var(--text-faint); font-size: 12px;">
          ${this.searchQuery ? 'No matching chats' : 'No chats yet. Start one!'}
        </div>
      `;
      return;
    }

    list.innerHTML = filtered.map(c => {
      const isActive = c.ID === this.activeConversationId;
      const title = this.escapeHtml(c.Title || 'New Chat');
      const dateStr = this.formatDate(c.Updated_At || c.Created_At);
      const count = c.message_count || 0;

      return `
        <div class="conversation-item ${isActive ? 'active' : ''}" data-id="${c.ID}">
          <div class="conversation-info">
            <span class="conversation-title" title="${title}">${title}</span>
            <div class="conversation-meta">
              <span>${count} msg${count === 1 ? '' : 's'}</span>
              <span>•</span>
              <span>${dateStr}</span>
            </div>
          </div>
          <div class="conversation-actions">
            <button class="btn-icon-subtle delete btn-del-conv" data-id="${c.ID}" title="Delete chat">
              <i class="fa-solid fa-trash-can"></i>
            </button>
          </div>
        </div>
      `;
    }).join('');

    // Attach listeners to items
    list.querySelectorAll('.conversation-item').forEach(item => {
      item.addEventListener('click', (e) => {
        if (e.target.closest('.btn-del-conv')) return;
        const id = parseInt(item.getAttribute('data-id'), 10);
        this.selectConversation(id);
      });
    });

    list.querySelectorAll('.btn-del-conv').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation();
        const id = parseInt(btn.getAttribute('data-id'), 10);
        this.deleteConversation(id);
      });
    });
  },

  async selectConversation(id) {
    if (this.activeConversationId === id && document.getElementById('chat-messages')?.children.length > 1) {
      return;
    }
    this.activeConversationId = id;
    this.renderConversationsList();
    this.updateHeaderTitle();
    await this.loadMessages(id);
  },

  updateHeaderTitle() {
    const titleEl = document.getElementById('active-chat-title');
    if (!titleEl) return;
    const current = this.conversations.find(c => c.ID === this.activeConversationId);
    titleEl.textContent = current ? (current.Title || 'New Chat') : 'New Chat';
  },

  async loadMessages(convId) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    container.innerHTML = `
      <div style="padding: 30px; text-align: center; color: var(--text-muted); font-size: 13px;">
        <i class="fa-solid fa-spinner fa-spin"></i> Loading conversation history...
      </div>
    `;

    try {
      const res = await fetch(`/api/conversations/${convId}/messages`);
      if (!res.ok) throw new Error('Failed to fetch messages');
      const data = await res.json();
      const messages = data.messages || [];

      container.innerHTML = '';

      if (messages.length === 0) {
        this.renderWelcomeBubble();
      } else {
        messages.forEach(m => {
          this.appendMessage(m.role, m.content, {
            time: m.created_at,
            status: m.status,
          });
        });
      }
    } catch (e) {
      container.innerHTML = `
        <div style="padding: 20px; color: var(--danger); font-size: 13px;">
          Failed to load messages: ${e.message}
        </div>
      `;
    }
  },

  renderWelcomeBubble() {
    const container = document.getElementById('chat-messages');
    if (!container) return;
    container.innerHTML = `
      <div class="chat-bubble assistant">
        <div class="bubble-content">
          👋 <strong>Welcome to this conversation!</strong><br>
          This chat session retains complete context and memory across turns. Ask a question, give a task to the autonomous agent, or run tests with tool calling.
        </div>
        <div class="bubble-meta">
          <span>Brain Orchestrator</span>
        </div>
      </div>
    `;
  },

  async createNewChat() {
    try {
      const res = await fetch('/api/conversations', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: 'New Chat' }),
      });
      const data = await res.json();
      this.activeConversationId = data.id;
      await this.loadConversations(false);
      this.renderWelcomeBubble();
      this.updateHeaderTitle();
      document.getElementById('chat-input')?.focus();
    } catch (e) {
      App.showToast(`Failed to create new chat: ${e.message}`, 'error');
    }
  },

  async promptRenameChat() {
    if (!this.activeConversationId) return;
    const current = this.conversations.find(c => c.ID === this.activeConversationId);
    const oldTitle = current ? current.Title : 'New Chat';
    const newTitle = prompt('Enter new conversation title:', oldTitle);
    if (!newTitle || newTitle.trim() === '' || newTitle.trim() === oldTitle) return;

    try {
      const res = await fetch(`/api/conversations/${this.activeConversationId}`, {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: newTitle.trim() }),
      });
      if (!res.ok) throw new Error('Rename failed');
      App.showToast('Conversation renamed', 'success');
      await this.loadConversations(false);
    } catch (e) {
      App.showToast(`Rename error: ${e.message}`, 'error');
    }
  },

  async deleteConversation(id) {
    if (!confirm('Are you sure you want to delete this conversation and its history?')) {
      return;
    }

    try {
      const res = await fetch(`/api/conversations/${id}`, { method: 'DELETE' });
      if (!res.ok) throw new Error('Delete failed');
      App.showToast('Conversation deleted', 'info');

      if (this.activeConversationId === id) {
        this.activeConversationId = null;
      }
      await this.loadConversations(true);
      App.fetchStats();
    } catch (e) {
      App.showToast(`Delete error: ${e.message}`, 'error');
    }
  },

  async sendMessage() {
    if (this.isSending) return;

    const input = document.getElementById('chat-input');
    const text = input.value.trim();
    if (!text) return;

    if (!this.activeConversationId) {
      await this.createNewChat();
    }

    const mode = document.getElementById('chat-mode-select')?.value || 'agent';
    const temp = parseFloat(document.getElementById('chat-temp')?.value) || 0.2;
    const maxTurns = parseInt(document.getElementById('chat-turns')?.value) || 10;

    // Remove welcome bubble if it's the only one
    const container = document.getElementById('chat-messages');
    if (container && container.children.length === 1 && container.children[0].querySelector('.bubble-content')?.textContent.includes('Welcome to this conversation!')) {
      container.innerHTML = '';
    }

    // Render User Bubble
    this.appendMessage('user', text);
    input.value = '';

    // Render Loading Bubble
    const loadingId = 'loading-' + Date.now();
    this.appendLoading(loadingId, mode);

    this.isSending = true;
    const sendBtn = document.getElementById('btn-send-chat');
    if (sendBtn) sendBtn.disabled = true;

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: text,
          mode: mode,
          temperature: temp,
          max_turns: maxTurns,
          conversation_id: this.activeConversationId,
        }),
      });

      const data = await res.json();
      this.removeLoading(loadingId);

      if (data.success) {
        this.appendMessage('assistant', data.response, {
          duration_ms: data.duration_ms,
          chosen: data.chosen,
          tool_calls: data.tool_calls,
          mode: data.mode || mode,
        });

        if (data.conversation_id) {
          this.activeConversationId = data.conversation_id;
        }

        // Refresh conversation titles & count in sidebar
        await this.loadConversations(false);
      } else {
        this.appendMessage('assistant', `⚠️ **Error encountered:**\n${data.error}`, { isError: true });
      }
    } catch (e) {
      this.removeLoading(loadingId);
      this.appendMessage('assistant', `⚠️ **Network or Server Error:**\n${e.message}`, { isError: true });
    } finally {
      this.isSending = false;
      if (sendBtn) sendBtn.disabled = false;
      App.fetchStats();
    }
  },

  appendMessage(role, content, meta = {}) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    const bubble = document.createElement('div');
    bubble.className = `chat-bubble ${role}`;

    let metaHtml = '';
    const timeStr = meta.time
      ? this.formatDate(meta.time)
      : new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

    if (role === 'assistant') {
      let badgeInfo = meta.mode === 'direct' ? 'Direct Model' : 'Autonomous Agent';
      if (meta.chosen && meta.chosen.model) {
        badgeInfo = `${meta.chosen.provider}/${meta.chosen.model}`;
      }

      metaHtml = `
        <div class="bubble-meta">
          <span>${badgeInfo}</span>
          ${meta.duration_ms ? `<span>• ${meta.duration_ms} ms</span>` : ''}
          <span>• ${timeStr}</span>
        </div>
      `;
    } else {
      metaHtml = `
        <div class="bubble-meta" style="justify-content: flex-end;">
          <span>${timeStr}</span>
        </div>
      `;
    }

    // Format tool calls if present
    let toolsHtml = '';
    if (meta.tool_calls && meta.tool_calls.length > 0) {
      toolsHtml = meta.tool_calls.map(tc => `
        <div class="tool-call-trace">
          <i class="fa-solid fa-gear fa-spin"></i> <strong>Called Tool:</strong> <code>${tc.name || tc.id}</code>
          <div style="font-size: 11px; color: var(--text-muted); margin-top: 4px;">
            Args: <code>${JSON.stringify(tc.arguments || {})}</code>
          </div>
        </div>
      `).join('');
    }

    // Rich markdown rendering for assistant messages
    const formattedHtml = this.renderMarkdown(content, role === 'user');

    bubble.innerHTML = `
      <div class="bubble-content" ${meta.isError ? 'style="border-color: rgba(239, 68, 68, 0.4); background: rgba(239, 68, 68, 0.08);"' : ''}>
        ${toolsHtml}
        <div class="message-body">${formattedHtml}</div>
      </div>
      ${metaHtml}
    `;

    // Highlight any unhighlighted code blocks
    if (typeof hljs !== 'undefined') {
      bubble.querySelectorAll('pre code').forEach((block) => {
        try {
          hljs.highlightElement(block);
        } catch {}
      });
    }

    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
  },

  renderMarkdown(content, isUser = false) {
    if (!content) return '';
    content = String(content);

    if (isUser) {
      return this.escapeHtml(content).replace(/\n/g, '<br>');
    }

    // Try Marked.js first
    if (typeof marked !== 'undefined') {
      try {
        let html = marked.parse(content);
        // Wrap tables in responsive container for smooth mobile/horizontal scrolling
        html = html.replace(/<table>/g, '<div class="table-wrap"><table>').replace(/<\/table>/g, '</table></div>');
        return html;
      } catch (e) {
        console.warn('Marked parse error, using fallback parser:', e);
      }
    }

    // Built-in resilient fallback parser
    return this.fallbackMarkdown(content);
  },

  fallbackMarkdown(text) {
    // 1. Code blocks
    text = text.replace(/```([a-zA-Z0-9_-]*)\n([\s\S]*?)```/g, (match, lang, code) => {
      return `<pre><code class="language-${lang}">${this.escapeHtml(code.trim())}</code></pre>`;
    });

    // 2. Tables parsing
    const lines = text.split('\n');
    let inTable = false;
    let tableHtml = '';
    const newLines = [];

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();
      if (line.startsWith('|') && line.endsWith('|')) {
        const cells = line.split('|').slice(1, -1).map(c => c.trim());
        if (!inTable) {
          const next = (lines[i + 1] || '').trim();
          if (next.startsWith('|') && next.includes('---')) {
            inTable = true;
            tableHtml = '<div class="table-wrap"><table><thead><tr>';
            cells.forEach(c => {
              tableHtml += `<th>${this.formatInline(c)}</th>`;
            });
            tableHtml += '</tr></thead><tbody>';
            i++; // skip separator line
            continue;
          }
        } else {
          tableHtml += '<tr>';
          cells.forEach(c => {
            tableHtml += `<td>${this.formatInline(c)}</td>`;
          });
          tableHtml += '</tr>';
          continue;
        }
      } else {
        if (inTable) {
          tableHtml += '</tbody></table></div>';
          newLines.push(tableHtml);
          inTable = false;
          tableHtml = '';
        }
        newLines.push(line);
      }
    }
    if (inTable) {
      tableHtml += '</tbody></table></div>';
      newLines.push(tableHtml);
    }

    text = newLines.join('\n');

    // 3. Headers
    text = text.replace(/^#### (.*$)/gim, '<h4>$1</h4>');
    text = text.replace(/^### (.*$)/gim, '<h3>$1</h3>');
    text = text.replace(/^## (.*$)/gim, '<h2>$1</h2>');
    text = text.replace(/^# (.*$)/gim, '<h1>$1</h1>');

    // 4. Blockquotes
    text = text.replace(/^> (.*$)/gim, '<blockquote>$1</blockquote>');

    // 5. Lists
    text = text.replace(/^\s*[-*]\s+(.*$)/gim, '<li>$1</li>');
    text = text.replace(/(<li>[\s\S]*?<\/li>)/g, '<ul>$1</ul>');

    // 6. Inlines
    text = this.formatInline(text);

    // 7. Paragraphs
    return text.split('\n\n').map(p => {
      p = p.trim();
      if (!p) return '';
      if (p.startsWith('<h') || p.startsWith('<div') || p.startsWith('<pre') || p.startsWith('<ul') || p.startsWith('<blockquote')) {
        return p;
      }
      return `<p>${p.replace(/\n/g, '<br>')}</p>`;
    }).join('');
  },

  formatInline(str) {
    return str
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/`([^`]+)`/g, '<code>$1</code>')
      .replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  },

  appendLoading(id, mode) {
    const container = document.getElementById('chat-messages');
    if (!container) return;

    const bubble = document.createElement('div');
    bubble.className = 'chat-bubble assistant';
    bubble.id = id;

    const label = mode === 'agent'
      ? 'Autonomous agent is executing tools and reasoning...'
      : 'Waiting for model response...';

    bubble.innerHTML = `
      <div class="bubble-content" style="color: var(--text-muted); display: flex; align-items: center; gap: 10px;">
        <i class="fa-solid fa-spinner fa-spin" style="color: var(--accent-primary);"></i>
        <span>${label}</span>
      </div>
    `;

    container.appendChild(bubble);
    container.scrollTop = container.scrollHeight;
  },

  removeLoading(id) {
    const el = document.getElementById(id);
    if (el) el.remove();
  },

  formatDate(dateStr) {
    if (!dateStr) return '';
    try {
      const d = new Date(dateStr);
      if (isNaN(d.getTime())) return dateStr;
      const now = new Date();
      const isToday = d.toDateString() === now.toDateString();
      if (isToday) {
        return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
      }
      return `${d.getMonth() + 1}/${d.getDate()} ${d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
    } catch {
      return dateStr;
    }
  },

  escapeHtml(text) {
    if (!text) return '';
    return String(text)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
};

document.addEventListener('DOMContentLoaded', () => {
  ChatManager.init();
});

