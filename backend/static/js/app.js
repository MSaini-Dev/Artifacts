/**
 * app.js — Main UI application orchestrator
 * Handles Left Sidebar navigation, Header Titles, Modals, Toasts, and Stats polling.
 */

const App = {
  activePage: 'chat',

  init() {
    this.setupSidebarNav();
    this.setupModals();
    this.setupGlobalRefresh();
    this.fetchStats();
  },

  // Switch between left sidebar tabs
  setupSidebarNav() {
    const navItems = document.querySelectorAll('.nav-item');
    const pageViews = document.querySelectorAll('.page-view');
    const headerTitle = document.getElementById('header-page-title');

    const titles = {
      chat: 'Interactive Chat & Autonomous Agent',
      tools: 'Tools Manager — Manual Execution & Creation',
      db: 'DB Updater — Providers, Models & Keys',
      logs: 'Execution Logs & Failover Visualizer',
    };

    navItems.forEach(item => {
      item.addEventListener('click', () => {
        const targetPage = item.getAttribute('data-page');
        if (!targetPage || targetPage === this.activePage) return;

        navItems.forEach(n => n.classList.remove('active'));
        item.classList.add('active');

        pageViews.forEach(view => {
          if (view.id === `page-${targetPage}`) {
            view.classList.add('active');
          } else {
            view.classList.remove('active');
          }
        });

        this.activePage = targetPage;
        if (headerTitle) {
          headerTitle.textContent = titles[targetPage] || 'Brain Studio';
        }

        // Trigger page-specific loads on switch
        if (targetPage === 'db') DBUpdater.loadAll();
        if (targetPage === 'tools') ToolsManager.loadTools();
        if (targetPage === 'logs') LogsViewer.loadConversations();
      });
    });
  },

  setupModals() {
    // Open modal buttons and close modal triggers
    document.querySelectorAll('[data-close]').forEach(btn => {
      btn.addEventListener('click', () => {
        const modalId = btn.getAttribute('data-close');
        App.closeModal(modalId);
      });
    });

    // Close on overlay background click
    document.querySelectorAll('.modal-overlay').forEach(modal => {
      modal.addEventListener('click', (e) => {
        if (e.target === modal) {
          modal.classList.remove('active');
        }
      });
    });

    // Close on ESC
    document.addEventListener('keydown', (e) => {
      if (e.key === 'Escape') {
        document.querySelectorAll('.modal-overlay.active').forEach(m => m.classList.remove('active'));
      }
    });
  },

  openModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.add('active');
  },

  closeModal(modalId) {
    const modal = document.getElementById(modalId);
    if (modal) modal.classList.remove('active');
  },

  // Toast notifications
  toast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    
    let icon = 'fa-info-circle';
    if (type === 'success') icon = 'fa-check-circle';
    if (type === 'error') icon = 'fa-circle-exclamation';

    toast.innerHTML = `
      <i class="fa-solid ${icon}" style="font-size: 16px;"></i>
      <span style="flex-grow: 1;">${message}</span>
    `;

    container.appendChild(toast);
    setTimeout(() => {
      toast.style.opacity = '0';
      toast.style.transform = 'translateY(10px)';
      toast.style.transition = 'all 0.3s ease';
      setTimeout(() => toast.remove(), 300);
    }, duration);
  },

  setupGlobalRefresh() {
    const btn = document.getElementById('btn-global-refresh');
    if (btn) {
      btn.addEventListener('click', () => {
        btn.querySelector('i').classList.add('fa-spin');
        Promise.all([
          App.fetchStats(),
          DBUpdater.loadAll(),
          ToolsManager.loadTools(),
        ]).finally(() => {
          setTimeout(() => btn.querySelector('i').classList.remove('fa-spin'), 600);
          App.toast('State refreshed from SQLite3 database', 'success');
        });
      });
    }
  },

  async fetchStats() {
    try {
      const res = await fetch('/api/stats');
      if (!res.ok) return;
      const data = await res.json();
      
      const sp = document.getElementById('stat-providers');
      const sm = document.getElementById('stat-models');
      const sk = document.getElementById('stat-keys');
      const stBadge = document.getElementById('sidebar-tools-badge');
      const stText = document.getElementById('sidebar-stats-text');

      if (sp) sp.textContent = data.providers_count;
      if (sm) sm.textContent = `${data.active_models}/${data.models_count}`;
      if (sk) sk.textContent = data.keys_count;
      if (stBadge) stBadge.textContent = data.tools_count;
      if (stText) stText.textContent = `${data.providers_count} Providers | ${data.active_models} Active Models`;
    } catch (e) {
      console.warn('Failed to fetch stats:', e);
    }
  }
};

document.addEventListener('DOMContentLoaded', () => {
  App.init();
});
