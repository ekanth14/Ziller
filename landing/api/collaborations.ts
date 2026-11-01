import type { VercelRequest, VercelResponse } from '@vercel/node';
import { createClient } from '@supabase/supabase-js';

const MASTER_PASSCODE = process.env.COLLAB_DESK_PASSCODE || 'Ekanthbs@4514';
const SUPABASE_URL = process.env.SUPABASE_URL || '';
const SUPABASE_KEY = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY || '';

function parseCookies(cookieHeader: string | undefined): Record<string, string> {
  const list: Record<string, string> = {};
  if (!cookieHeader) return list;
  cookieHeader.split(';').forEach((cookie) => {
    const parts = cookie.split('=');
    if (parts.length >= 2) {
      list[parts[0].trim()] = decodeURIComponent(parts.slice(1).join('=').trim());
    }
  });
  return list;
}

function renderLockedScreenHtml(): string {
  return `<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Restricted Access | ZILLERS Research Desk</title>
  <link rel="icon" type="image/png" href="/assets/emblem.png">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: #050505;
      color: #F4F4F5;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 20px;
    }
    .card {
      width: 100%;
      max-width: 440px;
      background: #09090A;
      border: 1px solid #38383C;
      border-radius: 24px;
      padding: 36px 32px;
      box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.7);
      text-align: center;
      position: relative;
      overflow: hidden;
    }
    .halo {
      position: absolute;
      top: -60px;
      left: 50%;
      transform: translateX(-50%);
      width: 260px;
      height: 120px;
      background: rgba(229, 192, 123, 0.08);
      filter: blur(40px);
      border-radius: 50%;
      pointer-events: none;
    }
    .crest-wrap {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 64px;
      height: 64px;
      background: #151515;
      border: 1px solid #4D4D51;
      border-radius: 18px;
      margin-bottom: 20px;
    }
    .crest-wrap img {
      width: 38px;
      height: 38px;
      object-fit: contain;
    }
    .eyebrow {
      font-family: ui-monospace, monospace;
      font-size: 10px;
      letter-spacing: 0.2em;
      color: #A2A2A8;
      text-transform: uppercase;
      margin-bottom: 8px;
    }
    h1 {
      font-size: 20px;
      font-weight: 700;
      color: #FFFFFF;
      letter-spacing: -0.02em;
      margin-bottom: 8px;
    }
    p.desc {
      font-size: 13px;
      color: #888890;
      line-height: 1.5;
      margin-bottom: 28px;
    }
    .form-group {
      margin-bottom: 18px;
      text-align: left;
    }
    label {
      display: block;
      font-size: 11px;
      font-family: ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: #A2A2A8;
      margin-bottom: 6px;
    }
    .input-wrap {
      position: relative;
    }
    input[type="password"], input[type="text"] {
      width: 100%;
      padding: 12px 14px;
      border-radius: 12px;
      background: #151515;
      border: 1px solid #38383C;
      color: #FFFFFF;
      font-size: 14px;
      font-family: inherit;
      outline: none;
      transition: all 0.2s;
    }
    input:focus {
      border-color: #D8D8DC;
      box-shadow: 0 0 0 1px #D8D8DC;
    }
    .btn-submit {
      width: 100%;
      padding: 12px;
      border-radius: 12px;
      background: #F4F4F5;
      color: #050505;
      border: none;
      font-size: 13px;
      font-weight: 600;
      cursor: pointer;
      transition: all 0.15s;
    }
    .btn-submit:hover {
      background: #FFFFFF;
      transform: translateY(-1px);
    }
    .error-msg {
      margin-top: 14px;
      padding: 8px 12px;
      border-radius: 8px;
      background: rgba(239, 68, 68, 0.1);
      border: 1px solid rgba(239, 68, 68, 0.25);
      color: #F87171;
      font-size: 12px;
      display: none;
    }
    .footer-link {
      margin-top: 24px;
      font-size: 12px;
    }
    .footer-link a {
      color: #A2A2A8;
      text-decoration: none;
      transition: color 0.15s;
    }
    .footer-link a:hover {
      color: #FFF;
      text-decoration: underline;
    }
  </style>
</head>
<body>
  <div class="card">
    <div class="halo"></div>
    <div class="crest-wrap">
      <img src="/assets/emblem.png" alt="ZILLERS" onerror="this.src='/assets/logo.png'">
    </div>
    <div class="eyebrow">ZIEN ORGANISATION · RESEARCH DESK</div>
    <h1>Restricted Access</h1>
    <p class="desc">Enter the verified operator passcode to unlock and view the ZILLERS Collaboration Proposals Dossiers.</p>

    <form id="auth-form" onsubmit="handleUnlock(event)">
      <div class="form-group">
        <label for="passcode">Desk Operator Passcode</label>
        <div class="input-wrap">
          <input type="password" id="passcode" placeholder="Enter passcode..." autocomplete="current-password" required autofocus />
        </div>
      </div>

      <button type="submit" id="btn-unlock" class="btn-submit">Unlock Proposals Desk</button>
      <div id="error-box" class="error-msg"></div>
    </form>

    <div class="footer-link">
      <a href="https://zillers.zienorganisation.online/collaborate">← Return to Public Showcase</a>
    </div>
  </div>

  <script>
    async function handleUnlock(e) {
      e.preventDefault();
      const code = document.getElementById('passcode').value;
      const btn = document.getElementById('btn-unlock');
      const errBox = document.getElementById('error-box');

      btn.disabled = true;
      btn.textContent = 'Verifying Passcode...';
      errBox.style.display = 'none';

      try {
        const res = await fetch('/api/auth', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ passcode: code })
        });
        const data = await res.json();

        if (res.ok && data.success) {
          btn.textContent = 'Passcode Verified! Loading...';
          window.location.reload();
        } else {
          errBox.textContent = data.error || 'Incorrect passcode. Access denied.';
          errBox.style.display = 'block';
          btn.disabled = false;
          btn.textContent = 'Unlock Proposals Desk';
        }
      } catch (err) {
        errBox.textContent = 'Connection error. Please try again.';
        errBox.style.display = 'block';
        btn.disabled = false;
        btn.textContent = 'Unlock Proposals Desk';
      }
    }
  </script>
</body>
</html>`;
}

function renderUnlockedDashboardHtml(records: Array<Record<string, any>>): string {
  const sorted = [...records].sort(
    (a, b) => new Date(b.timestamp || 0).getTime() - new Date(a.timestamp || 0).getTime()
  );
  const jsonStr = JSON.stringify(sorted);
  const totalCount = sorted.length;

  return `<!DOCTYPE html>
<html lang="en" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Collaboration Proposals Desk | ZILLERS — Zien Organisation</title>
  <link rel="icon" type="image/png" href="/assets/emblem.png">
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: #050505;
      color: #F4F4F5;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      padding: 24px 16px 80px;
      min-height: 100vh;
    }
    .max-container { max-width: 1200px; margin: 0 auto; }
    .header {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding-bottom: 24px;
      border-bottom: 1px solid #222224;
      margin-bottom: 32px;
    }
    .brand-group { display: flex; align-items: center; gap: 14px; }
    .brand-logo {
      width: 42px;
      height: 42px;
      border-radius: 12px;
      background: #111;
      border: 1px solid #38383C;
      padding: 6px;
      object-fit: contain;
    }
    .brand-titles h1 {
      font-size: 18px;
      font-weight: 700;
      letter-spacing: 0.05em;
      color: #FFFFFF;
      text-transform: uppercase;
      font-family: ui-monospace, monospace;
    }
    .brand-titles p { font-size: 12px; color: #A2A2A8; }
    .brand-titles a { color: #E5C07B; text-decoration: none; font-weight: 600; }
    .brand-titles a:hover { color: #FFF; text-decoration: underline; }
    .header-actions { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
    .btn {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 8px 16px;
      border-radius: 9999px;
      font-size: 12px;
      font-weight: 600;
      text-decoration: none;
      border: 1px solid #38383C;
      background: #151515;
      color: #D8D8DC;
      cursor: pointer;
      transition: all 0.15s ease;
      font-family: inherit;
    }
    .btn:hover { background: #222224; border-color: #666; color: #FFF; }
    .btn-primary { background: #F4F4F5; color: #050505; border-color: #FFF; }
    .btn-primary:hover { background: #FFF; color: #000; transform: translateY(-1px); }
    .btn-danger { background: rgba(239, 68, 68, 0.1); border-color: rgba(239, 68, 68, 0.3); color: #F87171; }
    .btn-danger:hover { background: rgba(239, 68, 68, 0.2); border-color: #F87171; color: #FFF; }
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 10px;
      border-radius: 9999px;
      background: rgba(16, 185, 129, 0.1);
      border: 1px solid rgba(16, 185, 129, 0.25);
      color: #34D399;
      font-size: 11px;
      font-family: ui-monospace, monospace;
    }
    .status-dot {
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background: #10B981;
      animation: pulse 2s infinite;
    }
    @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }
    .stats-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 32px;
    }
    .stat-card {
      background: #0D0D0E;
      border: 1px solid #222224;
      border-radius: 16px;
      padding: 18px 20px;
    }
    .stat-card .label {
      font-size: 11px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #888890;
      font-family: ui-monospace, monospace;
      margin-bottom: 6px;
    }
    .stat-card .value { font-size: 26px; font-weight: 700; color: #F4F4F5; }
    .controls-bar {
      background: #0D0D0E;
      border: 1px solid #222224;
      border-radius: 16px;
      padding: 16px;
      margin-bottom: 24px;
      display: flex;
      flex-direction: column;
      gap: 14px;
    }
    .search-input-wrap { position: relative; width: 100%; }
    .search-input {
      width: 100%;
      padding: 12px 16px 12px 42px;
      border-radius: 10px;
      background: #151515;
      border: 1px solid #38383C;
      color: #F4F4F5;
      font-size: 13px;
      outline: none;
      transition: border-color 0.2s;
    }
    .search-input:focus { border-color: #D8D8DC; }
    .search-icon {
      position: absolute;
      left: 14px;
      top: 50%;
      transform: translateY(-50%);
      color: #666;
      font-size: 14px;
      pointer-events: none;
    }
    .filter-tabs { display: flex; flex-wrap: wrap; gap: 8px; }
    .filter-tab {
      padding: 6px 12px;
      border-radius: 8px;
      border: 1px solid #262629;
      background: #151515;
      color: #A2A2A8;
      font-size: 12px;
      cursor: pointer;
      transition: all 0.15s;
    }
    .filter-tab.active, .filter-tab:hover {
      background: #252528;
      color: #FFF;
      border-color: #4D4D51;
    }
    .proposals-grid { display: flex; flex-direction: column; gap: 16px; }
    .proposal-card {
      background: #09090A;
      border: 1px solid #26262A;
      border-radius: 16px;
      padding: 22px;
      transition: border-color 0.2s;
    }
    .proposal-card:hover { border-color: #4D4D51; }
    .card-top {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      padding-bottom: 14px;
      border-bottom: 1px solid #1C1C1F;
      margin-bottom: 16px;
    }
    .ref-pill {
      font-family: ui-monospace, monospace;
      font-size: 11px;
      font-weight: 700;
      color: #D8D8DC;
      background: #151516;
      border: 1px solid #38383C;
      padding: 4px 10px;
      border-radius: 6px;
      cursor: pointer;
    }
    .ref-pill:hover { background: #222224; color: #FFF; }
    .timestamp { font-size: 11px; color: #71717A; font-family: ui-monospace, monospace; }
    .author-info {
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 12px 24px;
      margin-bottom: 14px;
    }
    .author-name { font-size: 16px; font-weight: 600; color: #FFF; }
    .author-email { font-size: 13px; color: #A2A2A8; text-decoration: none; }
    .author-email:hover { color: #FFF; text-decoration: underline; }
    .author-links { display: flex; align-items: center; gap: 8px; }
    .profile-link {
      display: inline-flex;
      align-items: center;
      gap: 4px;
      font-size: 11px;
      font-family: ui-monospace, monospace;
      color: #D8D8DC;
      background: #141416;
      border: 1px solid #2D2D31;
      padding: 3px 8px;
      border-radius: 6px;
      text-decoration: none;
      transition: all 0.15s;
    }
    .profile-link:hover { border-color: #666; color: #FFF; background: #202024; }
    .track-tag {
      display: inline-block;
      font-size: 11px;
      font-weight: 600;
      color: #A1A1AA;
      background: #18181B;
      border: 1px solid #2E2E33;
      padding: 3px 10px;
      border-radius: 9999px;
      margin-bottom: 12px;
    }
    .proposal-box {
      background: #111113;
      border: 1px solid #222226;
      border-radius: 10px;
      padding: 14px 16px;
      font-size: 13px;
      line-height: 1.6;
      color: #E4E4E7;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: ui-monospace, monospace;
    }
    .proposal-box-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-size: 10px;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: #71717A;
      margin-bottom: 8px;
      font-family: ui-monospace, monospace;
    }
    .copy-btn {
      background: transparent;
      border: 1px solid #38383C;
      color: #A2A2A8;
      border-radius: 4px;
      padding: 2px 8px;
      font-size: 10px;
      cursor: pointer;
    }
    .copy-btn:hover { color: #FFF; border-color: #888; }
    .empty-state {
      text-align: center;
      padding: 60px 20px;
      background: #09090A;
      border: 1px dashed #2A2A2E;
      border-radius: 16px;
      color: #71717A;
    }
    #toast {
      position: fixed;
      bottom: 24px;
      right: 24px;
      background: #F4F4F5;
      color: #050505;
      padding: 10px 18px;
      border-radius: 8px;
      font-size: 12px;
      font-weight: 600;
      box-shadow: 0 10px 25px rgba(0,0,0,0.5);
      display: none;
      z-index: 1000;
    }
  </style>
</head>
<body>
  <div class="max-container">
    <header class="header">
      <div class="brand-group">
        <img src="/assets/emblem.png" alt="ZILLERS" class="brand-logo" onerror="this.src='/assets/logo.png'">
        <div class="brand-titles">
          <h1>ZILLERS Collaboration Proposals Desk</h1>
          <p>Supervised under <a href="https://ziennexus.app/" target="_blank" rel="noopener noreferrer">Zien Organisation</a> · Research Intakes</p>
        </div>
      </div>

      <div class="header-actions">
        <span class="status-badge">
          <span class="status-dot"></span>
          <span>${totalCount} RECORDED</span>
        </span>
        <a href="https://zillers.zienorganisation.online/collaborate" class="btn">← Back to Showcase</a>
        <button class="btn" onclick="exportCSV()">Export CSV</button>
        <button class="btn" onclick="exportJSON()">Export JSON</button>
        <button class="btn btn-danger" onclick="handleLogout()">Lock Desk</button>
      </div>
    </header>

    <div class="stats-grid">
      <div class="stat-card">
        <div class="label">Total Proposals</div>
        <div class="value">${totalCount}</div>
      </div>
      <div class="stat-card">
        <div class="label">Authentication</div>
        <div class="value" style="font-size: 16px; color: #34D399; margin-top: 4px;">OPERATOR VERIFIED</div>
      </div>
      <div class="stat-card">
        <div class="label">Access Status</div>
        <div class="value" style="font-size: 16px; color: #E5C07B; margin-top: 4px;">PASSCODE PROTECTED</div>
      </div>
    </div>

    <div class="controls-bar">
      <div class="search-input-wrap">
        <span class="search-icon">🔍</span>
        <input
          type="text"
          id="search-input"
          class="search-input"
          placeholder="Filter proposals by researcher name, email, GitHub handle, proposal text, or reference ID..."
          oninput="filterProposals()"
        />
      </div>
      <div class="filter-tabs" id="track-filters">
        <button class="filter-tab active" data-track="ALL" onclick="setTrack('ALL')">All Tracks (${totalCount})</button>
      </div>
    </div>

    <div id="proposals-list" class="proposals-grid"></div>

    <div id="empty-state" class="empty-state" style="display: none;">
      <h3>No proposals found</h3>
      <p>Try modifying your search keywords or selecting another focus track.</p>
    </div>
  </div>

  <div id="toast"></div>

  <script>
    const allRecords = ${jsonStr};
    let currentTrack = 'ALL';

    function showToast(msg) {
      const t = document.getElementById('toast');
      t.textContent = msg;
      t.style.display = 'block';
      setTimeout(() => { t.style.display = 'none'; }, 2500);
    }

    function copyToClipboard(text, label) {
      navigator.clipboard.writeText(text).then(() => {
        showToast((label || 'Content') + ' copied to clipboard');
      }).catch(() => {
        showToast('Failed to copy');
      });
    }

    function copyProposalById(id) {
      const match = allRecords.find(item => item.id === id);
      if (match && match.message) {
        copyToClipboard(match.message, 'Proposal Statement');
      }
    }

    async function handleLogout() {
      await fetch('/api/auth', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action: 'logout' })
      });
      window.location.reload();
    }

    const trackCounts = {};
    allRecords.forEach(r => {
      const t = r.track || 'General Quantitative Research';
      trackCounts[t] = (trackCounts[t] || 0) + 1;
    });

    const tabsContainer = document.getElementById('track-filters');
    Object.keys(trackCounts).sort().forEach(t => {
      const btn = document.createElement('button');
      btn.className = 'filter-tab';
      btn.dataset.track = t;
      btn.textContent = \`\${t} (\${trackCounts[t]})\`;
      btn.onclick = () => setTrack(t);
      tabsContainer.appendChild(btn);
    });

    function setTrack(t) {
      currentTrack = t;
      document.querySelectorAll('.filter-tab').forEach(btn => {
        btn.classList.toggle('active', btn.dataset.track === t);
      });
      filterProposals();
    }

    function formatDate(isoStr) {
      if (!isoStr) return 'N/A';
      try {
        const d = new Date(isoStr);
        return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' }) + ' ' +
               d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hour12: false });
      } catch (e) {
        return isoStr;
      }
    }

    function filterProposals() {
      const q = document.getElementById('search-input').value.toLowerCase().trim();
      const container = document.getElementById('proposals-list');
      const emptyState = document.getElementById('empty-state');
      container.innerHTML = '';

      const filtered = allRecords.filter(r => {
        const matchesTrack = (currentTrack === 'ALL') || (r.track === currentTrack);
        if (!matchesTrack) return false;
        if (!q) return true;

        const haystack = [
          r.id, r.name, r.email, r.github, r.linkedin, r.website, r.track, r.message
        ].filter(Boolean).join(' ').toLowerCase();

        return haystack.includes(q);
      });

      if (filtered.length === 0) {
        emptyState.style.display = 'block';
        return;
      }
      emptyState.style.display = 'none';

      filtered.forEach(r => {
        const card = document.createElement('div');
        card.className = 'proposal-card';

        const githubLink = r.github ? \`<a href="\${escapeAttr(r.github)}" target="_blank" rel="noopener noreferrer" class="profile-link">GitHub ↗</a>\` : '';
        const linkedinLink = r.linkedin ? \`<a href="\${escapeAttr(r.linkedin)}" target="_blank" rel="noopener noreferrer" class="profile-link">LinkedIn ↗</a>\` : '';
        const websiteLink = r.website ? \`<a href="\${escapeAttr(r.website)}" target="_blank" rel="noopener noreferrer" class="profile-link">Website ↗</a>\` : '';

        card.innerHTML = \`
          <div class="card-top">
            <div style="display: flex; align-items: center; gap: 8px;">
              <span class="ref-pill" onclick="copyToClipboard('\${r.id}', 'Reference ID')" title="Click to copy ID">\${escapeHtml(r.id)}</span>
              <span class="status-badge" style="padding: 2px 8px; font-size: 10px;">VERIFIED PROPOSAL</span>
            </div>
            <div class="timestamp">\${formatDate(r.timestamp)}</div>
          </div>

          <div class="author-info">
            <span class="author-name">\${escapeHtml(r.name || 'Anonymous Researcher')}</span>
            <a href="mailto:\${escapeAttr(r.email)}" class="author-email">\${escapeHtml(r.email || '')}</a>
            <div class="author-links">
              \${githubLink}
              \${linkedinLink}
              \${websiteLink}
            </div>
          </div>

          <div class="track-tag">\${escapeHtml(r.track || 'Quantitative Research')}</div>

          <div class="proposal-box">
            <div class="proposal-box-header">
              <span>RESEARCH PROPOSAL & STATEMENT</span>
              <button class="copy-btn" onclick="copyProposalById('\${r.id}')">Copy Statement</button>
            </div>
            <div>\${escapeHtml(r.message || 'No proposal text provided.')}</div>
          </div>
        \`;
        container.appendChild(card);
      });
    }

    function escapeHtml(str) {
      return (str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }
    function escapeAttr(str) { return (str || '').replace(/"/g, '&quot;'); }

    function exportJSON() {
      const dataStr = "data:text/json;charset=utf-8," + encodeURIComponent(JSON.stringify(allRecords, null, 2));
      const a = document.createElement('a');
      a.setAttribute("href", dataStr);
      a.setAttribute("download", "zillers_collaborations_" + new Date().toISOString().slice(0, 10) + ".json");
      document.body.appendChild(a);
      a.click();
      a.remove();
      showToast('Exported JSON successfully');
    }

    function exportCSV() {
      if (allRecords.length === 0) {
        showToast('No records to export');
        return;
      }
      const headers = ['ID', 'Timestamp', 'Name', 'Email', 'GitHub', 'LinkedIn', 'Website', 'Track', 'Proposal Message', 'Client IP'];
      const rows = allRecords.map(r => [
        r.id || '',
        r.timestamp || '',
        r.name || '',
        r.email || '',
        r.github || '',
        r.linkedin || '',
        r.website || '',
        r.track || '',
        (r.message || '').replace(/\\r?\\n/g, ' '),
        r.client_ip || ''
      ]);

      let csv = headers.join(',') + '\\n';
      rows.forEach(row => {
        csv += row.map(v => '"' + String(v).replace(/"/g, '""') + '"').join(',') + '\\n';
      });

      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.setAttribute('href', url);
      a.setAttribute('download', 'zillers_collaborations_' + new Date().toISOString().slice(0, 10) + '.csv');
      document.body.appendChild(a);
      a.click();
      a.remove();
      showToast('Exported CSV successfully');
    }

    filterProposals();
  </script>
</body>
</html>`;
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  const cookies = parseCookies(req.headers.cookie);
  const isAuthenticated = cookies['zillers_collab_auth'] === MASTER_PASSCODE;

  if (!isAuthenticated) {
    res.setHeader('Content-Type', 'text/html; charset=utf-8');
    return res.status(200).send(renderLockedScreenHtml());
  }

  let records: Array<Record<string, any>> = [];
  try {
    if (SUPABASE_URL && SUPABASE_KEY) {
      const supabase = createClient(SUPABASE_URL, SUPABASE_KEY, {
        auth: { persistSession: false },
      });
      const { data, error } = await supabase
        .from('collaborations')
        .select('*')
        .order('timestamp', { ascending: false });

      if (!error && Array.isArray(data)) {
        records = data;
      }
    }
  } catch (err) {
    console.error('Failed to load proposals for desk view:', err);
  }

  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  return res.status(200).send(renderUnlockedDashboardHtml(records));
}
