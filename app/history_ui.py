from __future__ import annotations

import json

HISTORY_LIST_PAGE_HTML = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Reeve History - Sessions</title>
  <style>
    :root {
      --bg: #eef2f7;
      --panel: #ffffff;
      --ink: #102237;
      --muted: #5f7085;
      --line: #d8e2ec;
      --accent: #0d5bd7;
      --accent-soft: #eaf2ff;
    }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at 0% 0%, #f7faff 0%, var(--bg) 55%);
    }
    .wrap {
      max-width: 1120px;
      margin: 0 auto;
      padding: 24px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
      box-shadow: 0 4px 16px rgba(13, 35, 61, 0.05);
    }
    h1 {
      margin: 0 0 12px 0;
      font-size: 28px;
      letter-spacing: 0.2px;
    }
    .sub {
      color: var(--muted);
      margin-bottom: 16px;
      font-size: 14px;
    }
    .toolbar {
      display: flex;
      gap: 10px;
      flex-wrap: wrap;
      align-items: end;
      margin-bottom: 14px;
    }
    .field label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }
    select, button {
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 14px;
      background: #fff;
      color: var(--ink);
    }
    button.primary {
      border-color: var(--accent);
      background: var(--accent);
      color: #fff;
      font-weight: 600;
      cursor: pointer;
    }
    button.secondary {
      cursor: pointer;
      background: #fff;
    }
    .pager {
      margin-top: 12px;
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
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
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    tr:hover td {
      background: var(--accent-soft);
    }
    a.session-link {
      color: var(--accent);
      text-decoration: none;
      font-weight: 600;
    }
    .session-id {
      color: var(--muted);
      font-weight: 500;
    }
    .meta {
      color: var(--muted);
      font-size: 13px;
    }
    .empty {
      padding: 20px 8px;
      color: var(--muted);
      text-align: center;
      font-size: 14px;
    }
    @media (max-width: 900px) {
      .wrap {
        padding: 14px;
      }
      table, thead, tbody, tr, th, td {
        display: block;
      }
      thead {
        display: none;
      }
      tr {
        border: 1px solid var(--line);
        border-radius: 10px;
        margin-bottom: 10px;
        overflow: hidden;
      }
      td {
        border-bottom: 1px solid var(--line);
      }
      td:last-child {
        border-bottom: 0;
      }
      td::before {
        content: attr(data-label);
        display: block;
        font-size: 11px;
        color: var(--muted);
        text-transform: uppercase;
        margin-bottom: 4px;
        letter-spacing: 0.06em;
      }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"panel\">
      <h1>History Sessions</h1>
      <div class=\"sub\">Browse all session records, then open detail page for full message history. | <a href=\"/monitor\" style=\"color:#0d5bd7;font-weight:600;text-decoration:none;\">Session Monitor</a></div>

      <div class=\"toolbar\">
        <div class=\"field\">
          <label for=\"page-size\">Page Size</label>
          <select id=\"page-size\">
            <option value=\"20\">20</option>
            <option value=\"50\" selected>50</option>
            <option value=\"100\">100</option>
          </select>
        </div>
        <button id=\"reload\" class=\"primary\">Reload</button>
      </div>

      <div id=\"meta\" class=\"meta\"></div>

      <div style=\"overflow-x:auto; margin-top:10px;\">
        <table>
          <thead>
            <tr>
              <th>Session</th>
              <th>Messages</th>
              <th>Last Active</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody id=\"rows\"></tbody>
        </table>
      </div>

      <div class=\"pager\">
        <button id=\"prev\" class=\"secondary\">Prev</button>
        <button id=\"next\" class=\"secondary\">Next</button>
        <span id=\"page-meta\" class=\"meta\"></span>
      </div>
    </div>
  </div>

  <script>
    const rowsEl = document.getElementById("rows");
    const metaEl = document.getElementById("meta");
    const pageMetaEl = document.getElementById("page-meta");
    const pageSizeEl = document.getElementById("page-size");
    const reloadBtn = document.getElementById("reload");
    const prevBtn = document.getElementById("prev");
    const nextBtn = document.getElementById("next");

    const url = new URL(window.location.href);
    let page = Number(url.searchParams.get("page") || 1);
    let pageSize = Number(url.searchParams.get("page_size") || 50);
    if (page < 1) page = 1;
    if (![20, 50, 100].includes(pageSize)) pageSize = 50;
    pageSizeEl.value = String(pageSize);

    let totalPages = 1;

    function syncUrl() {
      const u = new URL(window.location.href);
      u.searchParams.set("page", String(page));
      u.searchParams.set("page_size", String(pageSize));
      window.history.replaceState({}, "", u.toString());
    }

    function setEmpty(text) {
      rowsEl.innerHTML = `<tr><td colspan=\"4\" class=\"empty\">${text}</td></tr>`;
    }

    async function load() {
      syncUrl();
      metaEl.textContent = "Loading sessions...";
      const res = await fetch(`/api/history/sessions?page=${page}&page_size=${pageSize}`);
      if (!res.ok) {
        metaEl.textContent = "Failed to load sessions.";
        setEmpty("Cannot load sessions.");
        return;
      }

      const data = await res.json();
      const sessions = data.sessions || [];
      totalPages = data.total_pages || 1;

      rowsEl.innerHTML = "";
      if (sessions.length === 0) {
        setEmpty("No sessions found.");
      } else {
        sessions.forEach((s) => {
          const row = document.createElement("tr");

          const sessionCell = document.createElement("td");
          sessionCell.setAttribute("data-label", "Session");
          const link = document.createElement("a");
          link.className = "session-link";
          link.href = `/history/session/${encodeURIComponent(s.session_key)}`;
          const firstUser = (s.first_user_message || "[no user message]").replace(/\\s+/g, " ").trim();
          const shortFirstUser = firstUser.length > 80 ? `${firstUser.slice(0, 77)}...` : firstUser;
          link.textContent = `${shortFirstUser} (${s.session_key})`;
          sessionCell.appendChild(link);

          const messageCell = document.createElement("td");
          messageCell.setAttribute("data-label", "Messages");
          messageCell.textContent = String(s.message_count);

          const lastActiveCell = document.createElement("td");
          lastActiveCell.setAttribute("data-label", "Last Active");
          lastActiveCell.textContent = s.last_active;

          const createdCell = document.createElement("td");
          createdCell.setAttribute("data-label", "Created");
          createdCell.textContent = s.created_at;

          row.appendChild(sessionCell);
          row.appendChild(messageCell);
          row.appendChild(lastActiveCell);
          row.appendChild(createdCell);
          rowsEl.appendChild(row);
        });
      }

      prevBtn.disabled = page <= 1;
      nextBtn.disabled = page >= totalPages;
      metaEl.textContent = `Total sessions: ${data.total}`;
      pageMetaEl.textContent = `Page ${data.page} / ${data.total_pages}`;
    }

    reloadBtn.addEventListener("click", () => {
      pageSize = Number(pageSizeEl.value || 50);
      page = 1;
      load();
    });
    prevBtn.addEventListener("click", () => {
      if (page > 1) {
        page -= 1;
        load();
      }
    });
    nextBtn.addEventListener("click", () => {
      if (page < totalPages) {
        page += 1;
        load();
      }
    });

    load().catch(() => {
      metaEl.textContent = "Failed to initialize page.";
      setEmpty("Failed to initialize page.");
    });
  </script>
</body>
</html>
"""


HISTORY_DETAIL_PAGE_TEMPLATE = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Reeve History - Detail</title>
  <style>
    :root {
      --bg: #eef2f7;
      --panel: #ffffff;
      --ink: #102237;
      --muted: #5f7085;
      --line: #d8e2ec;
      --accent: #0d5bd7;
      --user: #e8f2ff;
      --assistant: #edf8ec;
    }
    body {
      margin: 0;
      font-family: "Avenir Next", "Segoe UI", sans-serif;
      color: var(--ink);
      background: radial-gradient(circle at 0% 0%, #f7faff 0%, var(--bg) 55%);
    }
    .wrap {
      max-width: 1080px;
      margin: 0 auto;
      padding: 24px;
    }
    .panel {
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px;
      box-shadow: 0 4px 16px rgba(13, 35, 61, 0.05);
      margin-bottom: 14px;
    }
    h1 {
      margin: 0;
      font-size: 24px;
      word-break: break-all;
    }
    .meta {
      color: var(--muted);
      font-size: 13px;
      margin-top: 10px;
    }
    .top {
      display: flex;
      justify-content: space-between;
      gap: 10px;
      align-items: center;
      flex-wrap: wrap;
    }
    .btn {
      display: inline-block;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      text-decoration: none;
      color: var(--ink);
      background: #fff;
      font-size: 14px;
    }
    .controls {
      display: grid;
      grid-template-columns: 1fr 120px 120px;
      gap: 10px;
      align-items: end;
      margin-top: 12px;
    }
    label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }
    input, button {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid var(--line);
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 14px;
      background: #fff;
      color: var(--ink);
    }
    button {
      cursor: pointer;
      background: var(--accent);
      border-color: var(--accent);
      color: #fff;
      font-weight: 600;
    }
    .messages {
      display: flex;
      flex-direction: column;
      gap: 10px;
      max-height: 72vh;
      overflow: auto;
      padding-right: 4px;
    }
    .msg {
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 10px 12px;
      white-space: pre-wrap;
      word-break: break-word;
      line-height: 1.45;
    }
    .msg.user { background: var(--user); }
    .msg.assistant { background: var(--assistant); }
    .msg-head {
      display: flex;
      justify-content: space-between;
      gap: 8px;
      margin-bottom: 6px;
      font-size: 12px;
      color: var(--muted);
    }
    .empty {
      color: var(--muted);
      text-align: center;
      padding: 16px;
      font-size: 14px;
    }
    @media (max-width: 900px) {
      .wrap { padding: 14px; }
      .controls { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"panel\">
      <div class=\"top\">
        <h1 id=\"title\"></h1>
        <a class=\"btn\" href=\"/history\">Back to Sessions</a>
      </div>
      <div class=\"controls\">
        <div>
          <label for=\"since\">Since (ISO time, optional)</label>
          <input id=\"since\" placeholder=\"2026-02-23T00:00:00+00:00\" />
        </div>
        <div>
          <label for=\"limit\">Limit</label>
          <input id=\"limit\" type=\"number\" min=\"1\" max=\"2000\" value=\"300\" />
        </div>
        <div>
          <label>&nbsp;</label>
          <button id=\"load\">Load</button>
        </div>
      </div>
      <div id=\"meta\" class=\"meta\"></div>
    </div>

    <div class=\"panel\">
      <div id=\"messages\" class=\"messages\"></div>
    </div>
  </div>

  <script>
    const sessionKey = __SESSION_KEY_JSON__;
    const titleEl = document.getElementById("title");
    const sinceEl = document.getElementById("since");
    const limitEl = document.getElementById("limit");
    const loadBtn = document.getElementById("load");
    const metaEl = document.getElementById("meta");
    const messagesEl = document.getElementById("messages");

    titleEl.textContent = `Session Detail: ${sessionKey}`;

    function setMeta(text) { metaEl.textContent = text; }

    function showEmpty(text) {
      messagesEl.innerHTML = `<div class=\"empty\">${text}</div>`;
    }

    async function loadMessages() {
      const limit = Number(limitEl.value || 300);
      const since = sinceEl.value.trim();
      const params = new URLSearchParams({ session_key: sessionKey, limit: String(limit) });
      if (since) params.set("since", since);

      setMeta(`Loading messages for ${sessionKey}...`);
      const res = await fetch(`/api/history/messages?${params.toString()}`);
      if (!res.ok) {
        setMeta("Failed to load messages");
        showEmpty("Cannot load messages.");
        return;
      }

      const data = await res.json();
      const list = data.messages || [];
      messagesEl.innerHTML = "";

      if (list.length === 0) {
        setMeta("No messages found.");
        showEmpty("No messages found.");
        return;
      }

      list.forEach((m) => {
        const card = document.createElement("div");
        card.className = `msg ${m.role === "assistant" ? "assistant" : "user"}`;

        const head = document.createElement("div");
        head.className = "msg-head";
        const left = document.createElement("span");
        left.textContent = `${m.role} | id=${m.id}`;
        const right = document.createElement("span");
        right.textContent = m.created_at;
        head.appendChild(left);
        head.appendChild(right);

        const body = document.createElement("div");
        body.textContent = m.content;

        card.appendChild(head);
        card.appendChild(body);
        messagesEl.appendChild(card);
      });

      messagesEl.scrollTop = messagesEl.scrollHeight;
      setMeta(`Loaded ${list.length} messages`);
    }

    loadBtn.addEventListener("click", loadMessages);
    loadMessages().catch(() => {
      setMeta("Failed to initialize detail page.");
      showEmpty("Failed to initialize detail page.");
    });
  </script>
</body>
</html>
"""


def render_history_detail_page(session_key: str) -> str:
    return HISTORY_DETAIL_PAGE_TEMPLATE.replace("__SESSION_KEY_JSON__", json.dumps(session_key))
