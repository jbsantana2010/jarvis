const OBS_REFRESH = 8_000;

interface OBSData {
  available: boolean; live: boolean; recording: boolean;
  scene: string; uptime: string; mic_muted: boolean;
}

const OBS_OFFLINE: OBSData = {
  available: false, live: false, recording: false,
  scene: "—", uptime: "—", mic_muted: false,
};

export function mountOBSWidget(el: HTMLElement): void {
  _obsRender(el, OBS_OFFLINE);
  _obsFetch(el);
  setInterval(() => _obsFetch(el), OBS_REFRESH);
}

async function _obsFetch(el: HTMLElement): Promise<void> {
  try {
    const res = await fetch("/api/dashboard/obs");
    if (!res.ok) throw new Error();
    _obsRender(el, await res.json());
  } catch { _obsRender(el, OBS_OFFLINE); }
}

function _obsRender(el: HTMLElement, d: OBSData): void {
  const badge = d.available && d.live
    ? `<span class="badge badge-live">● LIVE</span>`
    : d.available
      ? `<span class="badge badge-idle">IDLE</span>`
      : `<span class="badge badge-offline">OFFLINE</span>`;
  const micCls = d.mic_muted ? "text-danger" : "text-success";
  const micLbl = d.mic_muted ? "MUTED" : "LIVE";
  const dis = !d.available ? " disabled" : "";
  const disLive = !d.available || !d.live ? " disabled" : "";
  el.innerHTML = `
    <div class="widget obs-widget">
      <div class="widget-header"><span class="widget-label">OBS STREAM</span>${badge}</div>
      <div class="obs-stats">
        <div class="obs-stat"><span class="stat-label">Scene</span><span class="stat-val">${_oesc(d.scene)}</span></div>
        <div class="obs-stat"><span class="stat-label">Uptime</span><span class="stat-val">${_oesc(d.uptime)}</span></div>
        <div class="obs-stat"><span class="stat-label">Mic</span><span class="stat-val ${micCls}">${micLbl}</span></div>
      </div>
      <div class="widget-btns">
        <button class="btn-action btn-ghost obs-brb"${dis}>BRB</button>
        <button class="btn-action btn-ghost obs-mute"${dis}>Mute Mic</button>
        <button class="btn-action btn-danger obs-end"${disLive}>End Stream</button>
      </div>
    </div>`;
  if (d.available) {
    el.querySelector(".obs-brb")?.addEventListener("click", () => _obsPost("brb_mode"));
    el.querySelector(".obs-mute")?.addEventListener("click", () => _obsPost("mute_mic"));
    el.querySelector(".obs-end")?.addEventListener("click", () => {
      if (confirm("End the stream?")) _obsPost("end_stream");
    });
  }
}

function _obsPost(action: string): void {
  fetch("/api/dashboard/action", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }) }).catch(() => {});
}

function _oesc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}
