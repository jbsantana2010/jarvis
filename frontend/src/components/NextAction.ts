const NA_REFRESH = 60_000;

interface NAData { action: string; reason: string; }

const NA_MOCK: NAData = {
  action: "Run morning briefing",
  reason: "Start the day with a full situational update.",
};

export function mountNextAction(el: HTMLElement): void {
  _naRender(el, NA_MOCK);
  _naFetch(el);
  setInterval(() => _naFetch(el), NA_REFRESH);
}

async function _naFetch(el: HTMLElement): Promise<void> {
  try {
    const res = await fetch("/api/dashboard/projects");
    if (!res.ok) return;
    const d = await res.json();
    if (d.next_action) _naRender(el, { action: d.next_action, reason: d.next_reason ?? "" });
  } catch { /* keep mock */ }
}

function _naRender(el: HTMLElement, d: NAData): void {
  const reason = d.reason ? `<div class="next-action-reason">${_esc(d.reason)}</div>` : "";
  el.innerHTML = `
    <div class="widget next-action-widget">
      <div class="widget-header"><span class="widget-label">NEXT ACTION</span></div>
      <div class="next-action-text">${_esc(d.action)}</div>
      ${reason}
      <div class="widget-btns">
        <button class="btn-action btn-primary na-start">Start</button>
        <button class="btn-action btn-ghost na-snooze">Snooze</button>
        <button class="btn-action btn-ghost na-log">Log Update</button>
      </div>
    </div>`;
  el.querySelector(".na-start")?.addEventListener("click", () => _naPost("morning_brief"));
  el.querySelector(".na-snooze")?.addEventListener("click", () => console.log("[na] snoozed"));
  el.querySelector(".na-log")?.addEventListener("click", () => _naPost("project_standup"));
}

function _naPost(action: string): void {
  fetch("/api/dashboard/action", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }) }).catch(() => {});
}

function _esc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
