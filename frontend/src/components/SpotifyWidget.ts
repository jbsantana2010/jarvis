const SP_REFRESH = 5_000;

interface SPData {
  available: boolean; active: boolean; track: string; artist: string;
  progress_ms: number; duration_ms: number; is_playing: boolean;
}

const SP_INACTIVE: SPData = {
  available: false, active: false, track: "Nothing playing",
  artist: "--", progress_ms: 0, duration_ms: 1, is_playing: false,
};

export function mountSpotifyWidget(el: HTMLElement): void {
  _spRender(el, SP_INACTIVE);
  _spFetch(el);
  setInterval(() => _spFetch(el), SP_REFRESH);
}

async function _spFetch(el: HTMLElement): Promise<void> {
  try {
    const res = await fetch("/api/dashboard/spotify");
    if (!res.ok) throw new Error();
    _spRender(el, await res.json());
  } catch { _spRender(el, SP_INACTIVE); }
}

function _spFmt(ms: number): string {
  const s = Math.floor(ms / 1000);
  return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
}

function _spRender(el: HTMLElement, d: SPData): void {
  const pct = d.duration_ms > 0 ? Math.round((d.progress_ms / d.duration_ms) * 100) : 0;
  const playIcon = d.is_playing
    ? `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><rect x="6" y="4" width="4" height="16"/><rect x="14" y="4" width="4" height="16"/></svg>`
    : `<svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg>`;
  const playBadge = d.active ? `<span class="badge badge-spotify">PLAYING</span>` : "";
  const inact = !d.active ? " widget-inactive" : "";
  const dis = !d.available ? " disabled" : "";
  el.innerHTML = `
    <div class="widget spotify-widget${inact}">
      <div class="widget-header">
        <span class="widget-label">SPOTIFY</span>${playBadge}
      </div>
      <div class="spotify-track" title="${_sesc(d.track)}">${_sesc(d.track)}</div>
      <div class="spotify-artist">${_sesc(d.artist)}</div>
      <div class="spotify-progress">
        <div class="progress-bar"><div class="progress-fill" style="width:${pct}%"></div></div>
        <div class="progress-times"><span>${_spFmt(d.progress_ms)}</span><span>${_spFmt(d.duration_ms)}</span></div>
      </div>
      <div class="widget-btns">
        <button class="btn-action btn-ghost sp-prev"${dis}>&laquo; Prev</button>
        <button class="btn-action btn-primary sp-pp"${dis}>${playIcon}</button>
        <button class="btn-action btn-ghost sp-next"${dis}>Next &raquo;</button>
      </div>
    </div>`;
  if (d.available) {
    el.querySelector(".sp-pp")?.addEventListener("click",
      () => _spPost(d.is_playing ? "spotify_pause" : "spotify_play"));
    el.querySelector(".sp-next")?.addEventListener("click", () => _spPost("spotify_next"));
    el.querySelector(".sp-prev")?.addEventListener("click", () => _spPost("spotify_prev"));
  }
}

function _spPost(action: string): void {
  fetch("/api/dashboard/action", { method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ action }) }).catch(() => {});
}

function _sesc(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
