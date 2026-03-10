from __future__ import annotations

MONITOR_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Reborn - Session Monitor</title>
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
    }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at 0% 0%, #f7faff 0%, var(--bg) 55%);
    }
    .wrap { max-width: 1120px; margin: 0 auto; padding: 24px; }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
      box-shadow: 0 4px 16px rgba(13, 35, 61, 0.05);
      margin-bottom: 18px;
    }
    h1 { margin: 0 0 4px 0; font-size: 28px; }
    h2 { margin: 0 0 10px 0; font-size: 20px; }
    .sub { color: var(--muted); margin-bottom: 16px; font-size: 14px; }
    .nav { margin-bottom: 14px; font-size: 14px; }
    .nav a { color: var(--accent); text-decoration: none; font-weight: 600; margin-right: 16px; }
    table { width: 100%; border-collapse: collapse; font-size: 14px; }
    th, td { padding: 10px 8px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; }
    th { font-size: 12px; color: var(--muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; }
    tr.clickable { cursor: pointer; }
    tr.clickable:hover td { background: var(--accent-soft); }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      border-radius: 6px;
      font-size: 12px;
      font-weight: 600;
    }
    .badge.running { background: var(--yellow-soft); color: var(--yellow); }
    .badge.completed { background: var(--green-soft); color: var(--green); }
    .badge.failed { background: var(--red-soft); color: var(--red); }
    .empty { padding: 20px 8px; color: var(--muted); text-align: center; font-size: 14px; }
    .events-panel {
      background: #f8fafc;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 12px;
      margin-top: 8px;
      max-height: 400px;
      overflow: auto;
      font-size: 13px;
      font-family: monospace;
    }
    .event-row { padding: 3px 0; border-bottom: 1px solid #eef1f4; }
    .event-kind { font-weight: 600; color: var(--accent); min-width: 120px; display: inline-block; }
    .event-time { color: var(--muted); font-size: 11px; margin-right: 8px; }
    .event-data { color: var(--ink); }
    .meta { color: var(--muted); font-size: 13px; }
    .tools-list { color: var(--muted); font-size: 12px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <h1>Session Monitor</h1>
      <div class="sub">Real-time visibility into active and recently completed agent sessions.</div>
      <div class="nav">
        <a href="/dashboard">Dashboard</a>
        <a href="/history">History</a>
        <a href="/health">Health</a>
      </div>
    </div>

    <div class="panel">
      <h2>Active Executions</h2>
      <div id="active-meta" class="meta"></div>
      <div style="overflow-x:auto; margin-top:10px;">
        <table>
          <thead>
            <tr>
              <th>Session</th>
              <th>Channel</th>
              <th>Backend</th>
              <th>Status</th>
              <th>Turn</th>
              <th>Tools</th>
              <th>Events</th>
              <th>Elapsed</th>
            </tr>
          </thead>
          <tbody id="active-rows"></tbody>
        </table>
      </div>
      <div id="active-detail"></div>
    </div>

    <div class="panel">
      <h2>Recently Completed</h2>
      <div id="completed-meta" class="meta"></div>
      <div style="overflow-x:auto; margin-top:10px;">
        <table>
          <thead>
            <tr>
              <th>Session</th>
              <th>Channel</th>
              <th>Backend</th>
              <th>Status</th>
              <th>Turns</th>
              <th>Tools</th>
              <th>Events</th>
              <th>Elapsed</th>
            </tr>
          </thead>
          <tbody id="completed-rows"></tbody>
        </table>
      </div>
      <div id="completed-detail"></div>
    </div>
  </div>

  <script>
    const activeRows = document.getElementById("active-rows");
    const activeMeta = document.getElementById("active-meta");
    const activeDetail = document.getElementById("active-detail");
    const completedRows = document.getElementById("completed-rows");
    const completedMeta = document.getElementById("completed-meta");
    const completedDetail = document.getElementById("completed-detail");

    let expandedKey = null;
    let expandedSection = null;

    function elapsed(startedAt, completedAt) {
      if (!startedAt) return "-";
      const end = completedAt || (Date.now() / 1000);
      const ms = Math.round((end - startedAt) * 1000);
      if (ms < 1000) return ms + "ms";
      return (ms / 1000).toFixed(1) + "s";
    }

    function badgeHtml(status) {
      return `<span class="badge ${status}">${status}</span>`;
    }

    function formatTime(ts) {
      if (!ts) return "";
      return new Date(ts * 1000).toLocaleTimeString();
    }

    function truncate(s, n) {
      if (!s) return "";
      return s.length > n ? s.slice(0, n) + "..." : s;
    }

    function renderEvents(events) {
      if (!events || events.length === 0) return "<div class='empty'>No events</div>";
      return events.map(e => {
        const dataStr = e.data ? Object.entries(e.data).map(([k,v]) => `${k}=${truncate(String(v), 120)}`).join(" ") : "";
        return `<div class="event-row"><span class="event-time">${formatTime(e.timestamp)}</span><span class="event-kind">${e.kind}</span> <span class="event-data">${dataStr}</span></div>`;
      }).join("");
    }

    function setEmpty(el, text) {
      el.innerHTML = `<tr><td colspan="8" class="empty">${text}</td></tr>`;
    }

    function buildRow(item, section) {
      const tr = document.createElement("tr");
      tr.className = "clickable";
      tr.innerHTML = `
        <td>${truncate(item.session_key, 50)}</td>
        <td>${item.channel || "-"}</td>
        <td>${item.backend || "-"}</td>
        <td>${badgeHtml(item.status)}</td>
        <td>${item.current_turn}</td>
        <td class="tools-list">${(item.tools_used || []).join(", ") || "-"}</td>
        <td>${item.event_count != null ? item.event_count : (item.events || []).length}</td>
        <td>${item.elapsed_ms != null ? item.elapsed_ms + "ms" : elapsed(item.started_at, item.completed_at)}</td>
      `;
      tr.addEventListener("click", () => toggleDetail(item.session_key, section));
      return tr;
    }

    async function toggleDetail(key, section) {
      const detailEl = section === "active" ? activeDetail : completedDetail;
      if (expandedKey === key && expandedSection === section) {
        detailEl.innerHTML = "";
        expandedKey = null;
        expandedSection = null;
        return;
      }
      expandedKey = key;
      expandedSection = section;
      detailEl.innerHTML = "<div class='meta'>Loading...</div>";
      try {
        const res = await fetch(`/api/monitor/${section}/${encodeURIComponent(key)}`);
        if (!res.ok) { detailEl.innerHTML = "<div class='meta'>Failed to load detail.</div>"; return; }
        const data = await res.json();
        detailEl.innerHTML = `
          <div class="events-panel">
            <div class="meta" style="margin-bottom:8px;">
              <strong>${data.session_key}</strong> | ${data.channel || "-"} | ${data.backend || "-"} | ${badgeHtml(data.status)} |
              Turn ${data.current_turn} | ${(data.tools_used || []).join(", ") || "no tools"}
              ${data.reply_preview ? " | Reply: " + truncate(data.reply_preview, 200) : ""}
              ${data.error_message ? " | Error: " + truncate(data.error_message, 200) : ""}
            </div>
            ${renderEvents(data.events)}
          </div>
        `;
      } catch {
        detailEl.innerHTML = "<div class='meta'>Failed to load detail.</div>";
      }
    }

    async function loadActive() {
      try {
        const res = await fetch("/api/monitor/active");
        if (!res.ok) { activeMeta.textContent = "Failed to load."; return; }
        const items = await res.json();
        activeRows.innerHTML = "";
        if (items.length === 0) {
          setEmpty(activeRows, "No active executions");
        } else {
          items.forEach(item => activeRows.appendChild(buildRow(item, "active")));
        }
        activeMeta.textContent = `${items.length} active`;
      } catch {
        activeMeta.textContent = "Failed to load active executions.";
      }
    }

    async function loadCompleted() {
      try {
        const res = await fetch("/api/monitor/completed");
        if (!res.ok) { completedMeta.textContent = "Failed to load."; return; }
        const items = await res.json();
        completedRows.innerHTML = "";
        if (items.length === 0) {
          setEmpty(completedRows, "No completed executions");
        } else {
          items.forEach(item => completedRows.appendChild(buildRow(item, "completed")));
        }
        completedMeta.textContent = `${items.length} recently completed (max 50)`;
      } catch {
        completedMeta.textContent = "Failed to load completed executions.";
      }
    }

    async function refresh() {
      await Promise.all([loadActive(), loadCompleted()]);
    }

    refresh();
    setInterval(loadActive, 2000);
    setInterval(loadCompleted, 5000);
  </script>
</body>
</html>
"""
