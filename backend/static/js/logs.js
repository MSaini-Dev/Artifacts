/**
 * logs.js — Execution Logs & Iterations Visualizer
 * Fetches and displays records from SQLite3 tables:
 * Conversation -> Interactive -> Iteration -> (Find_Best_API, Decide, Wait)
 */

const LogsViewer = {
  init() {
    document.getElementById('btn-refresh-logs')?.addEventListener('click', () => this.loadConversations());
  },

  async loadConversations() {
    const container = document.getElementById('logs-conversations-container');
    if (!container) return;

    container.innerHTML = `<div style="text-align: center; color: var(--text-faint); padding: 24px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading logs from SQLite3...</div>`;

    try {
      const res = await fetch('/api/logs/conversations?limit=25');
      if (!res.ok) throw new Error(await res.text());
      const convs = await res.json();

      if (convs.length === 0) {
        container.innerHTML = `<div style="text-align: center; color: var(--text-faint); padding: 24px;">No conversation logs recorded yet. Run a chat or agent task to see real-time SQLite logs!</div>`;
        return;
      }

      container.innerHTML = '';
      convs.forEach(c => {
        const card = document.createElement('div');
        card.className = 'card-panel';
        card.style.padding = '18px';
        card.style.marginBottom = '12px';

        card.innerHTML = `
          <div style="display: flex; justify-content: space-between; align-items: center; cursor: pointer;" onclick="LogsViewer.toggleConvDetails(${c.ID})">
            <div>
              <span style="font-size: 11px; color: var(--accent-secondary); font-weight: 700;">CONVERSATION #${c.ID}</span>
              <h3 style="font-size: 15px; font-weight: 700; color: #fff; margin-top: 2px;">${c.Title || 'Untitled Session'}</h3>
              <div style="font-size: 12px; color: var(--text-faint); margin-top: 4px;">
                <i class="fa-regular fa-clock"></i> ${c.Created_At}
              </div>
            </div>
            <button class="btn btn-secondary btn-sm" id="btn-toggle-conv-${c.ID}">
              <i class="fa-solid fa-chevron-down"></i> Expand
            </button>
          </div>
          <div id="conv-details-${c.ID}" style="display: none; margin-top: 18px; border-top: 1px solid var(--border-subtle); padding-top: 14px;">
            <div style="color: var(--text-faint); font-size: 12px;"><i class="fa-solid fa-spinner fa-spin"></i> Loading interaction history...</div>
          </div>
        `;
        container.appendChild(card);
      });
    } catch (e) {
      container.innerHTML = `<div style="color: var(--danger); padding: 20px;">Failed to load logs: ${e.message}</div>`;
    }
  },

  async toggleConvDetails(convId) {
    const detailsDiv = document.getElementById(`conv-details-${convId}`);
    const btn = document.getElementById(`btn-toggle-conv-${convId}`);
    if (!detailsDiv) return;

    if (detailsDiv.style.display === 'block') {
      detailsDiv.style.display = 'none';
      if (btn) btn.innerHTML = `<i class="fa-solid fa-chevron-down"></i> Expand`;
      return;
    }

    detailsDiv.style.display = 'block';
    if (btn) btn.innerHTML = `<i class="fa-solid fa-chevron-up"></i> Collapse`;

    try {
      const res = await fetch(`/api/logs/conversations/${convId}`);
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      this.renderConversationDetails(detailsDiv, data);
    } catch (e) {
      detailsDiv.innerHTML = `<div style="color: var(--danger);">Failed to load details: ${e.message}</div>`;
    }
  },

  formatPayload(payload) {
    let value = payload;
    if (typeof payload === 'string') {
      try {
        value = JSON.parse(payload);
      } catch {
        value = payload;
      }
    }

    const formatted = typeof value === 'string' ? value : JSON.stringify(value, null, 2);
    return formatted.replace(/[&<>"']/g, char => ({
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#39;'
    })[char]);
  },

  renderConversationDetails(container, data) {
    const interactives = data.interactives || [];
    if (interactives.length === 0) {
      container.innerHTML = `<p style="color: var(--text-faint); font-size: 13px;">No interactions recorded for this conversation.</p>`;
      return;
    }

    let html = `<div style="display: flex; flex-direction: column; gap: 16px;">`;

    interactives.forEach((inter, i) => {
      const badgeClass = inter.Response_Status === 'Final' ? 'badge-success' : 'badge-warning';
      const iters = inter.iterations || [];
      const duration = Number(inter.Duration_Seconds);
      const durationLabel = inter.Duration_Seconds !== null && inter.Duration_Seconds !== undefined && Number.isFinite(duration)
        ? `${duration.toFixed(3)} sec`
        : 'Not recorded';

      html += `
        <div style="background: rgba(255,255,255,0.02); border: 1px solid var(--border-subtle); border-radius: var(--radius-md); padding: 14px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <div>
              <strong style="color: var(--accent-primary);">Interaction #${inter.ID}</strong>
              <span style="font-size: 12px; color: var(--text-faint); margin-left: 8px;">Turn ${inter.Iteration_No || 1} • ${inter.Created_At}</span>
            </div>
            <span class="badge ${badgeClass}">${inter.Response_Status}</span>
          </div>

          <div style="font-size: 12px; color: var(--text-faint); margin-bottom: 10px;">
            <i class="fa-regular fa-hourglass-half"></i> Total process time: ${durationLabel}
          </div>

          ${inter.Payload ? `
            <details style="margin-bottom: 10px;">
              <summary style="cursor: pointer; color: var(--text-muted); font-size: 12px; font-weight: 700;">Request Payload</summary>
              <pre style="white-space: pre-wrap; overflow-wrap: anywhere; max-height: 280px; overflow-y: auto; background: rgba(0,0,0,0.3); border-radius: 6px; padding: 10px; font-size: 11px;">${this.formatPayload(inter.Payload)}</pre>
            </details>
          ` : ''}

          ${inter.Actual_Response ? `
            <div style="background: rgba(0,0,0,0.3); border-radius: 6px; padding: 10px; font-size: 12px; margin-bottom: 10px; max-height: 120px; overflow-y: auto;">
              <strong style="color: var(--text-muted);">Actual Response:</strong><br>
              ${inter.Actual_Response}
            </div>
          ` : ''}

          <h4 style="font-size: 12px; font-weight: 700; color: var(--text-muted); margin-bottom: 8px; text-transform: uppercase;">
            Failover Attempts / Iterations (${iters.length})
          </h4>
      `;

      if (iters.length === 0) {
        html += `<p style="font-size: 11px; color: var(--text-faint);">No API iterations logged.</p>`;
      } else {
        html += `<div style="display: flex; flex-direction: column; gap: 8px;">`;
        iters.forEach(iter => {
          const iterBadge = iter.Status === 'Success' ? 'badge-success' : 'badge-danger';
          const finds = iter.find_best_api || [];
          const decides = iter.decides || [];
          const waits = iter.waits || [];

          html += `
            <div style="background: rgba(0,0,0,0.4); border: 1px solid rgba(255,255,255,0.04); border-radius: 6px; padding: 10px; font-size: 12px;">
              <div style="display: flex; justify-content: space-between; align-items: center;">
                <span>
                  <strong>Iteration #${iter.ID}</strong>
                  ${finds.length > 0 ? `• <code style="color:var(--accent-secondary);">${finds[0].Provider}/${finds[0].Model}</code> (Key: ${finds[0].API})` : ''}
                </span>
                <div style="display: flex; gap: 8px; align-items: center;">
                  <span style="color: var(--text-faint); font-family: var(--font-mono); font-size: 11px;">⏱ ${iter.Time_Take_to_Process || '-'}</span>
                  <span class="badge ${iterBadge}">${iter.Status}</span>
                </div>
              </div>

              ${decides.length > 0 ? `
                <div style="margin-top: 6px; padding-top: 6px; border-top: 1px solid rgba(255,255,255,0.06); font-size: 11px; color: var(--warning);">
                  <i class="fa-solid fa-code-branch"></i> <strong>Decide [${decides[0].Mode}]:</strong> Action: <code>${decides[0].Action}</code> (Time: ${decides[0].Time_Take_To_Process || '-'})
                </div>
              ` : ''}

              ${waits.length > 0 ? `
                <div style="margin-top: 6px; font-size: 11px; color: var(--info);">
                  <i class="fa-solid fa-hourglass-half"></i> <strong>Wait Node:</strong> Cooldown time: ${waits[0].Time_To_Be_Waited || '-'}
                </div>
              ` : ''}
            </div>
          `;
        });
        html += `</div>`;
      }

      html += `</div>`;
    });

    html += `</div>`;
    container.innerHTML = html;
  }
};

document.addEventListener('DOMContentLoaded', () => {
  LogsViewer.init();
});
