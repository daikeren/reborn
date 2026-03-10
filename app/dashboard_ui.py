from __future__ import annotations


DASHBOARD_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Reborn Dashboard</title>
  <style>
    :root {
      --bg: #eef2f7;
      --panel: #ffffff;
      --ink: #102237;
      --muted: #5f7085;
      --line: #d8e2ec;
      --accent: #0d5bd7;
      --accent-soft: #eaf2ff;
      --green: #22863a;
      --green-soft: #e6f6e8;
      --red: #d73a49;
      --red-soft: #fce8ea;
      --yellow: #b08800;
      --yellow-soft: #fff8e1;
      --note: #fff6db;
      --shadow: 0 6px 20px rgba(13, 35, 61, 0.06);
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at 0% 0%, #f7faff 0%, var(--bg) 55%);
    }
    .wrap {
      max-width: 1280px;
      margin: 0 auto;
      padding: 24px;
    }
    .hero, .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 16px;
      box-shadow: var(--shadow);
    }
    .hero {
      padding: 22px;
      margin-bottom: 18px;
    }
    .hero-top {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: center;
      flex-wrap: wrap;
    }
    h1 { margin: 0; font-size: 30px; }
    h2 { margin: 0 0 10px 0; font-size: 20px; }
    .sub { color: var(--muted); font-size: 14px; margin-top: 6px; }
    .nav {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      margin-top: 18px;
    }
    .tab-btn, .link-btn, button, select, input, textarea {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 9px 12px;
      font-size: 14px;
      background: #fff;
      color: var(--ink);
    }
    .tab-btn {
      cursor: pointer;
      font-weight: 600;
    }
    .tab-btn.active {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
    }
    .grid {
      display: grid;
      gap: 18px;
    }
    .cards {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
    }
    .card {
      background: linear-gradient(180deg, #ffffff 0%, #f8fbff 100%);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
    }
    .card-label {
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
      margin-bottom: 8px;
    }
    .card-value {
      font-size: 28px;
      font-weight: 700;
    }
    .card-meta {
      margin-top: 8px;
      font-size: 13px;
      color: var(--muted);
    }
    .panel {
      padding: 18px;
    }
    .panel.hidden { display: none; }
    .toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: end;
      margin-bottom: 14px;
    }
    .field {
      min-width: 160px;
      flex: 1 1 160px;
    }
    .field label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }
    input, select, textarea, button {
      width: 100%;
    }
    textarea {
      min-height: 120px;
      resize: vertical;
      font-family: inherit;
    }
    button {
      cursor: pointer;
      font-weight: 600;
    }
    .primary {
      background: var(--accent);
      color: #fff;
      border-color: var(--accent);
    }
    .secondary {
      background: #fff;
    }
    .danger {
      background: var(--red);
      color: #fff;
      border-color: var(--red);
    }
    .soft {
      background: var(--accent-soft);
      border-color: #c7d9f7;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }
    th, td {
      padding: 10px 8px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }
    th {
      font-size: 12px;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    tr.clickable { cursor: pointer; }
    tr.clickable:hover td { background: var(--accent-soft); }
    .meta { color: var(--muted); font-size: 13px; }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
    }
    .badge.running { background: var(--yellow-soft); color: var(--yellow); }
    .badge.completed { background: var(--green-soft); color: var(--green); }
    .badge.failed, .badge.blocked, .badge.cancelled { background: var(--red-soft); color: var(--red); }
    .badge.loaded { background: var(--green-soft); color: var(--green); }
    .badge.enabled { background: var(--green-soft); color: var(--green); }
    .badge.disabled { background: var(--red-soft); color: var(--red); }
    .split {
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(320px, 0.8fr);
      gap: 16px;
    }
    .stack {
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .detail-box {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      background: #fbfdff;
    }
    .messages {
      max-height: 56vh;
      overflow: auto;
      display: flex;
      flex-direction: column;
      gap: 10px;
      padding-right: 4px;
    }
    .msg {
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 12px;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.45;
      background: #fff;
    }
    .msg.user { background: #e8f2ff; }
    .msg.assistant { background: #edf8ec; }
    .msg.note { background: var(--note); }
    .msg-head {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 6px;
      font-size: 12px;
      color: var(--muted);
    }
    .event-log {
      background: #0f1d2f;
      color: #d7e5ff;
      border-radius: 12px;
      padding: 12px;
      max-height: 240px;
      overflow: auto;
      font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
      font-size: 12px;
    }
    .empty {
      color: var(--muted);
      text-align: center;
      padding: 18px;
    }
    .two-col {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 12px;
    }
    .job-editor {
      display: grid;
      gap: 12px;
    }
    .inline-actions {
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }
    .inline-actions button { width: auto; }
    .link-row {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: center;
    }
    @media (max-width: 980px) {
      .wrap { padding: 14px; }
      .split, .two-col { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="hero">
      <div class="hero-top">
        <div>
          <h1>Reborn Dashboard</h1>
          <div class="sub">Unified control surface for sessions, web chat, jobs, and runtime readiness.</div>
        </div>
        <div class="link-row">
          <a class="link-btn" href="/history" style="text-decoration:none;">History</a>
          <a class="link-btn" href="/monitor" style="text-decoration:none;">Monitor</a>
          <a class="link-btn" href="/health" style="text-decoration:none;">Health</a>
        </div>
      </div>
      <div class="nav">
        <button class="tab-btn active" data-tab="overview">Overview</button>
        <button class="tab-btn" data-tab="sessions">Sessions</button>
        <button class="tab-btn" data-tab="chat">Chat</button>
        <button class="tab-btn" data-tab="jobs">Jobs</button>
        <button class="tab-btn" data-tab="config">Config</button>
      </div>
    </div>

    <div id="panel-overview" class="panel">
      <h2>Overview</h2>
      <div id="overview-cards" class="cards"></div>
      <div class="split" style="margin-top:16px;">
        <div class="detail-box">
          <div style="font-weight:700; margin-bottom:8px;">Runtime</div>
          <div id="overview-runtime" class="meta"></div>
        </div>
        <div class="detail-box">
          <div style="font-weight:700; margin-bottom:8px;">Channels</div>
          <div id="overview-channels" class="meta"></div>
        </div>
      </div>
    </div>

    <div id="panel-sessions" class="panel hidden">
      <h2>Sessions</h2>
      <div class="split">
        <div class="stack">
          <div class="toolbar">
            <div class="field">
              <label for="sessions-channel">Channel</label>
              <select id="sessions-channel">
                <option value="">All</option>
                <option value="web">Web</option>
                <option value="telegram">Telegram</option>
                <option value="slack">Slack</option>
                <option value="scheduler">Scheduler</option>
              </select>
            </div>
            <div class="field">
              <label for="sessions-status">Status</label>
              <select id="sessions-status">
                <option value="">Any</option>
                <option value="running">Running</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
                <option value="cancelled">Cancelled</option>
              </select>
            </div>
            <div class="field" style="flex:2 1 240px;">
              <label for="sessions-query">Search</label>
              <input id="sessions-query" placeholder="session key, chat key, first user message" />
            </div>
            <div class="field" style="flex:0 0 110px;">
              <label>&nbsp;</label>
              <button id="sessions-load" class="primary">Reload</button>
            </div>
          </div>
          <div id="sessions-meta" class="meta"></div>
          <div style="overflow-x:auto;">
            <table>
              <thead>
                <tr>
                  <th>Session</th>
                  <th>Channel</th>
                  <th>Status</th>
                  <th>Messages</th>
                  <th>Last Active</th>
                </tr>
              </thead>
              <tbody id="sessions-rows"></tbody>
            </table>
          </div>
        </div>
        <div class="stack">
          <div class="detail-box">
            <div style="font-weight:700; margin-bottom:8px;">Session Detail</div>
            <div id="session-detail" class="meta">Select a session.</div>
          </div>
        </div>
      </div>
    </div>

    <div id="panel-chat" class="panel hidden">
      <h2>Browser Chat</h2>
      <div class="split">
        <div class="stack">
          <div class="toolbar">
            <div class="field" style="flex:0 0 180px;">
              <label>&nbsp;</label>
              <button id="chat-new" class="primary">New Web Session</button>
            </div>
            <div class="field">
              <label for="chat-session">Current Session</label>
              <select id="chat-session"></select>
            </div>
            <div class="field" style="flex:0 0 140px;">
              <label>&nbsp;</label>
              <button id="chat-refresh" class="secondary">Refresh</button>
            </div>
          </div>
          <div id="chat-meta" class="meta">No web session selected.</div>
          <div id="chat-messages" class="messages"></div>
        </div>
        <div class="stack">
          <div class="detail-box">
            <div style="font-weight:700; margin-bottom:8px;">Send Message</div>
            <div class="field">
              <label for="chat-input">Message</label>
              <textarea id="chat-input" placeholder="Ask Reborn something from the browser dashboard."></textarea>
            </div>
            <div class="inline-actions" style="margin-top:10px;">
              <button id="chat-send" class="primary">Send</button>
              <button id="chat-cancel" class="danger">Cancel Active Run</button>
            </div>
          </div>
          <div class="detail-box">
            <div style="font-weight:700; margin-bottom:8px;">Operator Note</div>
            <div class="field">
              <label for="chat-note">Note</label>
              <textarea id="chat-note" placeholder="Inject a control note into this web session."></textarea>
            </div>
            <button id="chat-note-send" class="soft" style="margin-top:10px;">Send Note</button>
          </div>
          <div class="detail-box">
            <div style="font-weight:700; margin-bottom:8px;">Active Execution</div>
            <div id="chat-execution-meta" class="meta">Idle.</div>
            <div id="chat-execution-log" class="event-log"></div>
          </div>
        </div>
      </div>
    </div>

    <div id="panel-jobs" class="panel hidden">
      <h2>Scheduler Jobs</h2>
      <div class="split">
        <div class="stack">
          <div id="jobs-meta" class="meta"></div>
          <div style="overflow-x:auto;">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Schedule</th>
                  <th>Status</th>
                  <th>Tools</th>
                  <th>Last Run</th>
                </tr>
              </thead>
              <tbody id="jobs-rows"></tbody>
            </table>
          </div>
        </div>
        <div class="stack">
          <div class="detail-box">
            <div style="font-weight:700; margin-bottom:8px;">Job Editor</div>
            <div id="job-empty" class="meta">Select a job.</div>
            <div id="job-editor" class="job-editor" style="display:none;">
              <div class="two-col">
                <div class="field">
                  <label for="job-name">Name</label>
                  <input id="job-name" disabled />
                </div>
                <div class="field">
                  <label for="job-source">Source</label>
                  <input id="job-source" disabled />
                </div>
              </div>
              <div class="two-col">
                <div class="field">
                  <label for="job-schedule">Schedule</label>
                  <input id="job-schedule" />
                </div>
                <div class="field">
                  <label for="job-max-turns">Max Turns</label>
                  <input id="job-max-turns" type="number" min="1" />
                </div>
              </div>
              <div class="two-col">
                <div class="field">
                  <label for="job-tools">Tools (comma-separated)</label>
                  <input id="job-tools" />
                </div>
                <div class="field">
                  <label for="job-suppress-token">Suppress Token</label>
                  <input id="job-suppress-token" />
                </div>
              </div>
              <div class="field">
                <label for="job-enabled">Enabled</label>
                <select id="job-enabled">
                  <option value="true">Enabled</option>
                  <option value="false">Disabled</option>
                </select>
              </div>
              <div class="field">
                <label for="job-prompt">Prompt</label>
                <textarea id="job-prompt"></textarea>
              </div>
              <div class="inline-actions">
                <button id="job-save" class="primary">Save</button>
                <button id="job-run" class="secondary">Run Now</button>
                <button id="job-toggle" class="soft">Toggle Enabled</button>
              </div>
              <div id="job-last-run" class="meta"></div>
            </div>
          </div>
        </div>
      </div>
    </div>

    <div id="panel-config" class="panel hidden">
      <h2>Config and Skills</h2>
      <div class="split">
        <div class="stack">
          <div class="detail-box">
            <div style="font-weight:700; margin-bottom:8px;">Runtime Readiness</div>
            <div id="config-runtime" class="meta"></div>
          </div>
          <div class="detail-box">
            <div style="font-weight:700; margin-bottom:8px;">Blocking Problems</div>
            <div id="config-blockers" class="meta"></div>
          </div>
        </div>
        <div class="stack">
          <div class="detail-box">
            <div style="font-weight:700; margin-bottom:8px;">Skills</div>
            <div id="skills-meta" class="meta"></div>
            <div id="skills-list"></div>
          </div>
        </div>
      </div>
    </div>
  </div>

  <script>
    const tabs = [...document.querySelectorAll(".tab-btn")];
    const panels = {
      overview: document.getElementById("panel-overview"),
      sessions: document.getElementById("panel-sessions"),
      chat: document.getElementById("panel-chat"),
      jobs: document.getElementById("panel-jobs"),
      config: document.getElementById("panel-config"),
    };

    let selectedSessionKey = null;
    let currentWebSessionKey = null;
    let activeExecutionId = null;
    let executionPollTimer = null;
    let selectedJobName = null;

    function escapeHtml(value) {
      return String(value ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
    }

    function badge(status) {
      const safe = escapeHtml(status || "unknown");
      return `<span class="badge ${safe.toLowerCase()}">${safe}</span>`;
    }

    function formatList(values) {
      return values && values.length ? values.join(", ") : "-";
    }

    function formatJson(obj) {
      return `<pre style="margin:0; white-space:pre-wrap; word-break:break-word;">${escapeHtml(JSON.stringify(obj, null, 2))}</pre>`;
    }

    async function api(path, options = {}) {
      const res = await fetch(path, {
        headers: { "Content-Type": "application/json", ...(options.headers || {}) },
        ...options,
      });
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const data = await res.json();
          detail = data.detail || JSON.stringify(data);
        } catch {}
        throw new Error(detail);
      }
      if (res.status === 204) return null;
      return res.json();
    }

    function setTab(tabName) {
      tabs.forEach(btn => btn.classList.toggle("active", btn.dataset.tab === tabName));
      Object.entries(panels).forEach(([name, panel]) => panel.classList.toggle("hidden", name !== tabName));
      const url = new URL(window.location.href);
      url.searchParams.set("tab", tabName);
      window.history.replaceState({}, "", url);
      if (tabName === "overview") loadOverview();
      if (tabName === "sessions") loadSessions();
      if (tabName === "chat") loadWebSessions();
      if (tabName === "jobs") loadJobs();
      if (tabName === "config") loadConfig();
    }

    tabs.forEach(btn => btn.addEventListener("click", () => setTab(btn.dataset.tab)));

    async function loadOverview() {
      const data = await api("/api/dashboard/overview");
      const cards = [
        { label: "Active Executions", value: data.active_executions, meta: `completed tracked: ${data.completed_executions}` },
        { label: "24h Active Sessions", value: data.health.active_sessions, meta: `max message count: ${data.health.max_message_count}` },
        { label: "Backend", value: data.backend, meta: `chat=${data.chat_model} background=${data.background_model}` },
        { label: "Timezone", value: data.timezone, meta: data.workspace_dir },
      ];
      document.getElementById("overview-cards").innerHTML = cards.map(card => `
        <div class="card">
          <div class="card-label">${escapeHtml(card.label)}</div>
          <div class="card-value">${escapeHtml(card.value)}</div>
          <div class="card-meta">${escapeHtml(card.meta)}</div>
        </div>
      `).join("");
      document.getElementById("overview-runtime").innerHTML = formatJson(data);
      document.getElementById("overview-channels").innerHTML = formatJson(data.channels);
    }

    async function loadSessions() {
      const channel = document.getElementById("sessions-channel").value;
      const status = document.getElementById("sessions-status").value;
      const q = document.getElementById("sessions-query").value.trim();
      const params = new URLSearchParams({ page: "1", page_size: "100" });
      if (channel) params.set("channel", channel);
      if (status) params.set("status", status);
      if (q) params.set("q", q);
      const data = await api(`/api/dashboard/sessions?${params.toString()}`);
      document.getElementById("sessions-meta").textContent = `Total: ${data.total}`;
      const rows = data.sessions || [];
      const tbody = document.getElementById("sessions-rows");
      if (!rows.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty">No sessions found.</td></tr>`;
        return;
      }
      tbody.innerHTML = rows.map(item => `
        <tr class="clickable" data-session-key="${escapeHtml(item.session_key)}">
          <td><div>${escapeHtml(item.first_user_message || item.session_key)}</div><div class="meta">${escapeHtml(item.session_key)}</div></td>
          <td>${escapeHtml(item.channel)}</td>
          <td>${badge(item.execution_status || "idle")}</td>
          <td>${escapeHtml(item.message_count)}</td>
          <td>${escapeHtml(item.last_active)}</td>
        </tr>
      `).join("");
      [...tbody.querySelectorAll("tr[data-session-key]")].forEach(row => {
        row.addEventListener("click", () => {
          selectedSessionKey = row.dataset.sessionKey;
          loadSessionDetail(selectedSessionKey);
        });
      });
    }

    async function loadSessionDetail(sessionKey) {
      const data = await api(`/api/dashboard/sessions/${encodeURIComponent(sessionKey)}`);
      const actions = [];
      if ((data.available_actions || []).includes("reset")) {
        actions.push(`<button id="session-reset" class="danger">Reset</button>`);
      }
      if (data.channel === "web") {
        actions.push(`<button id="session-open-chat" class="secondary">Open in Chat</button>`);
      }
      document.getElementById("session-detail").innerHTML = `
        <div style="font-weight:700; margin-bottom:8px;">${escapeHtml(data.session_key)}</div>
        <div class="meta" style="margin-bottom:8px;">channel=${escapeHtml(data.channel)} | pending_question=${escapeHtml(data.pending_question)}</div>
        <div class="inline-actions" style="margin-bottom:10px;">${actions.join("")}</div>
        <div class="detail-box" style="margin-bottom:10px;">${formatJson(data.summary)}</div>
        <div style="font-weight:700; margin-bottom:6px;">Executions</div>
        <div style="margin-bottom:10px;">${(data.executions || []).map(ex => `
          <div class="meta">${badge(ex.status)} ${escapeHtml(ex.execution_id)} | turns=${escapeHtml(ex.current_turn)} | tools=${escapeHtml(formatList(ex.tools_used || []))}</div>
        `).join("") || "<div class='meta'>No executions.</div>"}</div>
        <div style="font-weight:700; margin-bottom:6px;">Transcript</div>
        <div class="messages">${renderMessages(data.messages || [])}</div>
      `;
      const resetBtn = document.getElementById("session-reset");
      if (resetBtn) {
        resetBtn.addEventListener("click", async () => {
          await api(`/api/dashboard/sessions/${encodeURIComponent(sessionKey)}/reset`, { method: "POST" });
          await loadSessions();
          await loadSessionDetail(sessionKey);
        });
      }
      const openChatBtn = document.getElementById("session-open-chat");
      if (openChatBtn) {
        openChatBtn.addEventListener("click", async () => {
          currentWebSessionKey = sessionKey;
          document.getElementById("chat-session").value = sessionKey;
          setTab("chat");
          await loadCurrentWebSession();
        });
      }
    }

    function renderMessages(messages) {
      if (!messages.length) {
        return `<div class="empty">No messages.</div>`;
      }
      return messages.map(msg => `
        <div class="msg ${escapeHtml(msg.role)}">
          <div class="msg-head">
            <span>${escapeHtml(msg.role)}</span>
            <span>${escapeHtml(msg.created_at || "")}</span>
          </div>
          <div>${escapeHtml(msg.content || "")}</div>
        </div>
      `).join("");
    }

    async function loadWebSessions() {
      const data = await api("/api/dashboard/sessions?channel=web&page=1&page_size=100");
      const select = document.getElementById("chat-session");
      const sessions = data.sessions || [];
      if (!sessions.length) {
        select.innerHTML = `<option value="">No web sessions</option>`;
        currentWebSessionKey = null;
        document.getElementById("chat-meta").textContent = "No web session selected.";
        document.getElementById("chat-messages").innerHTML = `<div class="empty">Create a web session to start chatting.</div>`;
        return;
      }
      select.innerHTML = sessions.map(item => `<option value="${escapeHtml(item.session_key)}">${escapeHtml(item.session_key)}</option>`).join("");
      if (!currentWebSessionKey || !sessions.some(item => item.session_key === currentWebSessionKey)) {
        currentWebSessionKey = sessions[0].session_key;
      }
      select.value = currentWebSessionKey;
      await loadCurrentWebSession();
    }

    async function loadCurrentWebSession() {
      if (!currentWebSessionKey) return;
      const data = await api(`/api/dashboard/web/sessions/${encodeURIComponent(currentWebSessionKey)}`);
      document.getElementById("chat-meta").textContent = `${data.session_key} | messages=${data.summary.message_count}`;
      document.getElementById("chat-messages").innerHTML = renderMessages(data.messages || []);
      const running = (data.executions || []).find(ex => ex.status === "running");
      if (running) {
        activeExecutionId = running.execution_id;
        startExecutionPolling(running.execution_id);
      }
    }

    async function createWebSession() {
      const data = await api("/api/dashboard/web/sessions", { method: "POST" });
      currentWebSessionKey = data.session_key;
      await loadWebSessions();
    }

    function executionLogHtml(execution) {
      const events = execution.events || [];
      if (!events.length) return "No events.";
      return events.map(event => {
        const payload = Object.entries(event.data || {}).map(([k, v]) => `${k}=${String(v)}`).join(" ");
        return `[${new Date((event.timestamp || 0) * 1000).toLocaleTimeString()}] ${event.kind} ${payload}`;
      }).join("\\n");
    }

    function startExecutionPolling(executionId) {
      activeExecutionId = executionId;
      if (executionPollTimer) window.clearInterval(executionPollTimer);
      const tick = async () => {
        if (!activeExecutionId) return;
        const data = await api(`/api/dashboard/executions/${encodeURIComponent(activeExecutionId)}`);
        document.getElementById("chat-execution-meta").innerHTML = `${badge(data.status)} ${escapeHtml(data.execution_id)} | tools=${escapeHtml(formatList(data.tools_used || []))}`;
        document.getElementById("chat-execution-log").textContent = executionLogHtml(data);
        if (data.partial_reply) {
          document.getElementById("chat-messages").innerHTML = renderMessages([
            ...(data.messages || []),
            { role: "assistant", content: data.partial_reply, created_at: "streaming" },
          ]);
        }
        if (data.status !== "running") {
          window.clearInterval(executionPollTimer);
          executionPollTimer = null;
          activeExecutionId = null;
          await loadCurrentWebSession();
        }
      };
      tick().catch(err => {
        document.getElementById("chat-execution-meta").textContent = err.message;
      });
      executionPollTimer = window.setInterval(() => tick().catch(() => {}), 1000);
    }

    async function sendChatMessage() {
      if (!currentWebSessionKey) return;
      const message = document.getElementById("chat-input").value.trim();
      if (!message) return;
      const data = await api(`/api/dashboard/web/sessions/${encodeURIComponent(currentWebSessionKey)}/messages`, {
        method: "POST",
        body: JSON.stringify({ message }),
      });
      document.getElementById("chat-input").value = "";
      startExecutionPolling(data.execution_id);
      await loadCurrentWebSession();
    }

    async function sendOperatorNote() {
      if (!currentWebSessionKey) return;
      const note = document.getElementById("chat-note").value.trim();
      if (!note) return;
      const data = await api(`/api/dashboard/web/sessions/${encodeURIComponent(currentWebSessionKey)}/notes`, {
        method: "POST",
        body: JSON.stringify({ note }),
      });
      document.getElementById("chat-note").value = "";
      startExecutionPolling(data.execution_id);
      await loadCurrentWebSession();
    }

    async function cancelExecution() {
      if (!activeExecutionId) return;
      await api(`/api/dashboard/executions/${encodeURIComponent(activeExecutionId)}/cancel`, { method: "POST" });
    }

    async function loadJobs() {
      const data = await api("/api/dashboard/jobs");
      document.getElementById("jobs-meta").textContent = `${data.jobs.length} jobs`;
      const tbody = document.getElementById("jobs-rows");
      if (!data.jobs.length) {
        tbody.innerHTML = `<tr><td colspan="5" class="empty">No jobs found.</td></tr>`;
        return;
      }
      tbody.innerHTML = data.jobs.map(job => `
        <tr class="clickable" data-job-name="${escapeHtml(job.name)}">
          <td>${escapeHtml(job.name)}</td>
          <td>${escapeHtml(job.schedule || "-")}</td>
          <td>${badge(job.enabled ? "enabled" : "disabled")}</td>
          <td>${escapeHtml(formatList(job.tools || []))}</td>
          <td>${job.last_execution ? badge(job.last_execution.status) + " " + escapeHtml(job.last_execution.completed_at || "") : "-"}</td>
        </tr>
      `).join("");
      [...tbody.querySelectorAll("tr[data-job-name]")].forEach(row => {
        row.addEventListener("click", () => {
          selectedJobName = row.dataset.jobName;
          loadJobDetail(selectedJobName);
        });
      });
    }

    async function loadJobDetail(name) {
      const data = await api(`/api/dashboard/jobs/${encodeURIComponent(name)}`);
      document.getElementById("job-empty").style.display = "none";
      document.getElementById("job-editor").style.display = "grid";
      document.getElementById("job-name").value = data.name;
      document.getElementById("job-source").value = data.source;
      document.getElementById("job-schedule").value = data.schedule || "";
      document.getElementById("job-max-turns").value = data.max_turns;
      document.getElementById("job-tools").value = (data.tools || []).join(", ");
      document.getElementById("job-suppress-token").value = data.suppress_token || "";
      document.getElementById("job-enabled").value = String(data.enabled);
      document.getElementById("job-prompt").value = data.prompt || "";
      document.getElementById("job-last-run").innerHTML = data.last_execution ? formatJson(data.last_execution) : "No tracked execution yet.";
      document.getElementById("job-toggle").textContent = data.enabled ? "Disable" : "Enable";
    }

    async function saveJob() {
      if (!selectedJobName) return;
      await api(`/api/dashboard/jobs/${encodeURIComponent(selectedJobName)}`, {
        method: "PUT",
        body: JSON.stringify({
          schedule: document.getElementById("job-schedule").value.trim() || null,
          max_turns: Number(document.getElementById("job-max-turns").value || 10),
          tools: document.getElementById("job-tools").value.split(",").map(v => v.trim()).filter(Boolean),
          suppress_token: document.getElementById("job-suppress-token").value.trim() || null,
          enabled: document.getElementById("job-enabled").value === "true",
          prompt: document.getElementById("job-prompt").value,
        }),
      });
      await loadJobs();
      await loadJobDetail(selectedJobName);
    }

    async function runJobNow() {
      if (!selectedJobName) return;
      await api(`/api/dashboard/jobs/${encodeURIComponent(selectedJobName)}/run`, { method: "POST" });
      await loadJobs();
      await loadJobDetail(selectedJobName);
      await loadOverview();
    }

    async function toggleJob() {
      if (!selectedJobName) return;
      const enabled = document.getElementById("job-enabled").value === "true";
      const path = enabled ? "disable" : "enable";
      await api(`/api/dashboard/jobs/${encodeURIComponent(selectedJobName)}/${path}`, { method: "POST" });
      await loadJobs();
      await loadJobDetail(selectedJobName);
    }

    async function loadConfig() {
      const [config, skills] = await Promise.all([
        api("/api/dashboard/config"),
        api("/api/dashboard/skills"),
      ]);
      document.getElementById("config-runtime").innerHTML = formatJson(config);
      document.getElementById("config-blockers").innerHTML = (config.blocking_problems || []).length
        ? `<ul>${config.blocking_problems.map(item => `<li>${escapeHtml(item)}</li>`).join("")}</ul>`
        : "<div class='meta'>No blocking problems detected.</div>";
      document.getElementById("skills-meta").textContent = `${skills.skills.length} skill entries`;
      document.getElementById("skills-list").innerHTML = skills.skills.map(skill => `
        <div class="detail-box" style="margin-top:10px;">
          <div style="display:flex; justify-content:space-between; gap:10px; align-items:center;">
            <div style="font-weight:700;">${escapeHtml(skill.name)}</div>
            <div>${badge(skill.status)}</div>
          </div>
          <div class="meta">${escapeHtml(skill.path)}</div>
          <div style="margin-top:8px;">${escapeHtml(skill.description || skill.error || "")}</div>
        </div>
      `).join("") || "<div class='meta'>No skills found.</div>";
    }

    document.getElementById("sessions-load").addEventListener("click", () => loadSessions().catch(err => alert(err.message)));
    document.getElementById("chat-new").addEventListener("click", () => createWebSession().catch(err => alert(err.message)));
    document.getElementById("chat-refresh").addEventListener("click", () => loadCurrentWebSession().catch(err => alert(err.message)));
    document.getElementById("chat-session").addEventListener("change", event => {
      currentWebSessionKey = event.target.value || null;
      loadCurrentWebSession().catch(err => alert(err.message));
    });
    document.getElementById("chat-send").addEventListener("click", () => sendChatMessage().catch(err => alert(err.message)));
    document.getElementById("chat-note-send").addEventListener("click", () => sendOperatorNote().catch(err => alert(err.message)));
    document.getElementById("chat-cancel").addEventListener("click", () => cancelExecution().catch(err => alert(err.message)));
    document.getElementById("job-save").addEventListener("click", () => saveJob().catch(err => alert(err.message)));
    document.getElementById("job-run").addEventListener("click", () => runJobNow().catch(err => alert(err.message)));
    document.getElementById("job-toggle").addEventListener("click", () => toggleJob().catch(err => alert(err.message)));

    const initialTab = new URL(window.location.href).searchParams.get("tab") || "overview";
    setTab(initialTab);
  </script>
</body>
</html>
"""
