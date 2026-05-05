import { fetchOBSPanel, fetchSpotifyPanel, fetchProjectsPanel, fetchBudgetPanel } from "./components/ContextPanels";

export type UIMode = "ambient" | "dashboard" | "context";
export type ActivePanel = "obs" | "spotify" | "budget" | "projects" | "email" | null;

let currentMode: UIMode = "dashboard";
let activePanel: ActivePanel = null;
let dismissTimer: ReturnType<typeof setTimeout> | null = null;

const CONTEXT_DISMISS_MS = 15_000;

const PANEL_TRIGGERS: Array<{ keywords: string[]; panel: ActivePanel }> = [
  { keywords: ["go live", "start stream", "stop stream", "end stream", "obs", "streaming", "am i live", "are we live"], panel: "obs" },
  { keywords: ["what's playing", "whats playing", "spotify", "play music", "pause music", "skip track", "next track", "play something"], panel: "spotify" },
  { keywords: ["my debt", "budget", "spending", "how much do i owe", "my finances", "my balance", "credit card"], panel: "budget" },
  { keywords: ["work on", "should i work", "what should", "my projects", "next task", "sprint", "project status", "what to work"], panel: "projects" },
  { keywords: ["check email", "my email", "inbox", "any emails", "new emails", "check my email"], panel: "email" },
];

export function detectPanelTrigger(text: string): void {
  const lower = text.toLowerCase();
  if (/\b(show|open|display)\b.*dashboard/.test(lower) || lower.trim() === "show dashboard") {
    setMode("dashboard");
    return;
  }
  if (/\b(hide|close|minimize)\b.*dashboard/.test(lower)) {
    setMode("ambient");
    return;
  }
  for (const { keywords, panel } of PANEL_TRIGGERS) {
    if (keywords.some(kw => lower.includes(kw))) {
      showContextPanel(panel!);
      return;
    }
  }
}

export function setMode(mode: UIMode): void {
  currentMode = mode;
  document.body.classList.remove("mode-ambient", "mode-dashboard", "mode-context");
  document.body.classList.add(`mode-${mode}`);
  if (mode !== "context") {
    _clearDismissTimer();
    activePanel = null;
  }
  // Let CSS apply new canvas width, then tell the orb renderer to resize
  requestAnimationFrame(() => window.dispatchEvent(new Event("resize")));
}

export function getMode(): UIMode { return currentMode; }

export async function showContextPanel(panel: ActivePanel): Promise<void> {
  activePanel = panel;
  setMode("context");

  const titleEl = document.getElementById("context-panel-title");
  const bodyEl  = document.getElementById("context-panel-body");
  if (!titleEl || !bodyEl) return;

  const titles: Record<string, string> = {
    obs: "STREAM", spotify: "NOW PLAYING", budget: "BUDGET",
    projects: "PROJECTS", email: "INBOX",
  };
  titleEl.textContent = titles[panel ?? ""] ?? "INFO";
  bodyEl.innerHTML = `<div class="ctx-loading">Loading…</div>`;

  _resetDismissTimer();

  let html = "";
  switch (panel) {
    case "obs":      html = await fetchOBSPanel(); break;
    case "spotify":  html = await fetchSpotifyPanel(); break;
    case "budget":   html = await fetchBudgetPanel(); break;
    case "projects": html = await fetchProjectsPanel(); break;
    case "email":    html = `<div class="ctx-loading">Email integration coming soon.</div>`; break;
    default:         html = `<div class="ctx-loading">—</div>`;
  }

  if (currentMode === "context" && activePanel === panel) {
    bodyEl.innerHTML = html;
  }
}

export function dismissPanel(): void {
  _clearDismissTimer();
  activePanel = null;
  setMode("ambient");
}

export function updateAmbientState(state: string): void {
  const dot   = document.getElementById("ambient-dot");
  const label = document.getElementById("ambient-state");
  if (!dot || !label) return;
  dot.className = `ambient-dot ambient-dot-${state}`;
  label.textContent = state === "idle" ? "ready" : state;
}

function _clearDismissTimer(): void {
  if (dismissTimer !== null) { clearTimeout(dismissTimer); dismissTimer = null; }
  const bar = document.getElementById("context-dismiss-progress");
  if (bar) { (bar as HTMLElement).style.transition = "none"; (bar as HTMLElement).style.width = "100%"; }
}

function _resetDismissTimer(): void {
  _clearDismissTimer();
  dismissTimer = setTimeout(dismissPanel, CONTEXT_DISMISS_MS);
  const bar = document.getElementById("context-dismiss-progress");
  if (bar) {
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        (bar as HTMLElement).style.transition = `width ${CONTEXT_DISMISS_MS}ms linear`;
        (bar as HTMLElement).style.width = "0%";
      });
    });
  }
}
