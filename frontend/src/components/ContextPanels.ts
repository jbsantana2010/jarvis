/**
 * ContextPanels.ts — async data fetchers for Sprint 16 context overlay panels.
 * Each function fetches from a dashboard API endpoint and returns rendered HTML.
 *
 * Sprint 19: fetchEmailPanel() added — replaces "coming soon" stub.
 */

function fmtMs(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

export async function fetchOBSPanel(): Promise<string> {
  try {
    const r = await fetch("/api/dashboard/obs");
    if (!r.ok) throw new Error("non-ok");
    const d = await r.json();
    const streaming = d.streaming;
    const recording = d.recording;
    const scene     = d.scene || "—";
    const timecode  = d.stream_timecode || "—";
    return `
      <div class="ctx-stat-row">
        <div class="ctx-stat">
          <div class="ctx-stat-label">Stream</div>
          <div class="ctx-stat-val ${streaming ? "text-success" : "text-danger"}">${streaming ? "● LIVE" : "○ OFF"}</div>
        </div>
        <div class="ctx-stat">
          <div class="ctx-stat-label">Recording</div>
          <div class="ctx-stat-val ${recording ? "text-success" : ""}">${recording ? "● REC" : "○ OFF"}</div>
        </div>
        <div class="ctx-stat">
          <div class="ctx-stat-label">Duration</div>
          <div class="ctx-stat-val">${timecode}</div>
        </div>
      </div>
      <div class="ctx-stat-row">
        <div class="ctx-stat">
          <div class="ctx-stat-label">Scene</div>
          <div class="ctx-stat-val">${scene}</div>
        </div>
      </div>`;
  } catch {
    return `<div class="ctx-loading">OBS unavailable — is it running?</div>`;
  }
}

export async function fetchSpotifyPanel(): Promise<string> {
  try {
    const r = await fetch("/api/dashboard/spotify");
    if (!r.ok) throw new Error("non-ok");
    const d = await r.json();
    if (!d.is_playing && !d.track) {
      return `<div class="ctx-loading">No active Spotify device.</div>`;
    }
    const prog = d.progress_ms || 0;
    const dur  = d.duration_ms || 1;
    const pct  = Math.round((prog / dur) * 100);
    return `
      <div class="ctx-track">${d.track || "Unknown Track"}</div>
      <div class="ctx-artist">${d.artist || "Unknown Artist"}</div>
      <div class="progress-bar" style="margin-bottom:8px">
        <div class="progress-fill" style="width:${pct}%"></div>
      </div>
      <div class="progress-times">
        <span>${fmtMs(prog)}</span><span>${fmtMs(dur)}</span>
      </div>`;
  } catch {
    return `<div class="ctx-loading">Spotify unavailable.</div>`;
  }
}

export async function fetchProjectsPanel(): Promise<string> {
  try {
    const r = await fetch("/api/dashboard/projects");
    if (!r.ok) throw new Error("non-ok");
    const d = await r.json();
    const projects: any[] = d.projects || [];
    if (projects.length === 0) return `<div class="ctx-loading">No active projects.</div>`;
    return projects.slice(0, 5).map((p: any) => {
      const pri     = p.priority ? `<span class="badge pri-${p.priority}">P${p.priority}</span>` : "";
      const blocked = p.blocked ? " ctx-blocked" : "";
      return `<div class="ctx-project-row${blocked}">${pri}<span>${p.name}</span></div>`;
    }).join("");
  } catch {
    return `<div class="ctx-loading">Projects unavailable.</div>`;
  }
}

export async function fetchBudgetPanel(): Promise<string> {
  try {
    const r = await fetch("/api/budget/summary");
    if (!r.ok) throw new Error("non-ok");
    const d = await r.json();
    const debt    = (d.total_debt   ?? d.total ?? 0).toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });
    const monthly = d.monthly_minimum ? `$${Number(d.monthly_minimum).toLocaleString()} / mo minimum` : "";
    return `
      <div class="ctx-budget-total">${debt}</div>
      <div class="ctx-budget-label">Total Debt</div>
      ${monthly ? `<div class="ctx-budget-sub">${monthly}</div>` : ""}`;
  } catch {
    return `<div class="ctx-loading">Budget data unavailable.</div>`;
  }
}

// ---------------------------------------------------------------------------
// Sprint 19: Email panel
// ---------------------------------------------------------------------------

export async function fetchEmailPanel(): Promise<string> {
  try {
    const r = await fetch("/api/dashboard/email");
    if (!r.ok) throw new Error("non-ok");
    const d = await r.json();

    if (d.error && (!d.emails || d.emails.length === 0)) {
      return `<div class="ctx-loading">Gmail unavailable — check OAuth setup.</div>`;
    }

    const emails: any[] = d.emails || [];
    if (emails.length === 0) {
      return `<div class="ctx-loading">Inbox is clear.</div>`;
    }

    const unreadCount = emails.filter((e: any) => e.unread).length;
    const header = unreadCount > 0
      ? `<div class="ctx-email-header">${unreadCount} unread of ${emails.length}</div>`
      : `<div class="ctx-email-header">${emails.length} recent — all read</div>`;

    const rows = emails.slice(0, 6).map((e: any) => {
      const unreadClass = e.unread ? " ctx-email-unread" : "";
      const dot = e.unread ? `<span class="ctx-email-dot">●</span>` : `<span class="ctx-email-dot ctx-email-dot-read">○</span>`;
      const sender  = _esc(e.sender  || "Unknown");
      const subject = _esc(e.subject || "(no subject)");
      const snippet = _esc((e.snippet || "").slice(0, 72));
      const time    = _esc(e.timestamp || "");
      return `
        <div class="ctx-email-row${unreadClass}">
          <div class="ctx-email-top">
            ${dot}
            <span class="ctx-email-sender">${sender}</span>
            <span class="ctx-email-time">${time}</span>
          </div>
          <div class="ctx-email-subject">${subject}</div>
          ${snippet ? `<div class="ctx-email-snippet">${snippet}…</div>` : ""}
        </div>`;
    }).join("");

    return header + rows;
  } catch {
    return `<div class="ctx-loading">Email unavailable — is Gmail connected?</div>`;
  }
}

function _esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
