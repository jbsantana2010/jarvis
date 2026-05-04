const PW_REFRESH = 30_000;

interface PWProject {
  id: number; name: string; status: string;
  priority: number; last_update: string | null; open_blockers: number;
}

interface PWData {
  available: boolean; projects: PWProject[];
  next_action?: string; next_reason?: string;
}

const PW_MOCK: PWData = { available: true, projects: [
  { id: 1, name: "JARVIS Sprint 15", status: "active", priority: 1, last_update: "just now", open_blockers: 0 },
  { id: 2, name: "Stream Overlay", status: "active", priority: 2, last_update: "2h ago", open_blockers: 1 },
]};

export function mountProjectWidget(el: HTMLElement): void {
  _pwRender(el, PW_MOCK);
  _pwFetch(el);
  setInterval(() => _pwFetch(el), PW_REFRESH);
}

async function _pwFetch(el: HTMLElement): Promise<void> {
  try {
    const res = await fetch("/api/dashboard/projects");
    if (!res.ok) return;
    _pwRender(el, await res.json());
  } catch { /* keep mock */ }
}

const PRI_LBL: Record<number, string> = { 1: "P1", 2: "P2", 3: "P3" };
const PRI_CLS: Record<number, string> = { 1: "pri-1", 2: "pri-2", 3: "pri-3" };

function _pwRender(el: HTMLElement, d: PWData): void {
  const rows = d.projects.slice(0, 4).map(p => {
    const blocked = p.open_blockers > 0 ? " project-blocked" : "";
    const blkBadge = p.open_blockers > 0
      ? `<span class="badge badge-blocked">${p.open_blockers} blocked</span>` : "";
    const meta = p.last_update ? "Updated " + _pesc(p.last_update) : "No updates yet";
    return `
    <div class="project-row${blocked}">
      <div class="project-name-row">
        <span class="project-name">${_pesc(p.name)}</span>
        <span class="badge ${PRI_CLS[p.priority] ?? "pri-2"}">${PRI_LBL[p.priority] ?? "P?"}</span>
        ${blkBadge}
      </div>
      <div class="project-meta">${meta}</div>
    </div>`;
  }).join("");

  const body = d.projects.length === 0
    ? `<div class="widget-empty">No active projects. Say "add project" to start tracking.</div>`
    : rows;

  el.innerHTML = `
    <div class="widget project-widget">
      <div class="widget-header">
        <span class="widget-label">PROJECTS</span>
        <span class="widget-count">${d.projects.length} active</span>
      </div>
      ${body}
      <div class="widget-btns">
        <button class="btn-action btn-ghost pw-standup">Standup</button>
        <button class="btn-action btn-ghost pw-focus">Focus Next</button>
      </div>
    </div>`;
  el.querySelector(".pw-standup")?.addEventListener("click", () => _pwPost("project_standup"));
  el.querySelector(".pw-focus")?.addEventListener("click", () => _pwPost("focus_next"));
}

function _pwPost(action: string): void {
  fetch("/api/dashboard/action", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }) }).catch(() => {});
}

function _pesc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
