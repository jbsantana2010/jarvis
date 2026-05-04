export type VoiceState = "idle" | "listening" | "thinking" | "speaking";

const MAX_ACTIVITY = 5;
const _activity: string[] = ["Session started"];
let _statePill: HTMLElement | null = null;
let _dashPill: HTMLElement | null = null;
let _lastResp: HTMLElement | null = null;
let _focus: HTMLElement | null = null;
let _actList: HTMLElement | null = null;
let _dateEl: HTMLElement | null = null;

const STATE_LABELS: Record<VoiceState, string> = {
  idle: "IDLE", listening: "LISTENING", thinking: "THINKING", speaking: "SPEAKING",
};

export function initBrain(): void {
  _statePill = document.getElementById("state-pill");
  _dashPill  = document.getElementById("dash-state-pill");
  _lastResp  = document.getElementById("last-response");
  _focus     = document.getElementById("current-focus");
  _actList   = document.getElementById("activity-list");
  _dateEl    = document.getElementById("dash-date");
  _renderActivity();
  _updateDate();
  setInterval(_updateDate, 60_000);
}

function _updateDate(): void {
  if (!_dateEl) return;
  _dateEl.textContent = new Date().toLocaleDateString("en-US", {
    weekday: "short", month: "short", day: "numeric",
  });
}

export function setBrainState(state: VoiceState): void {
  const lbl = STATE_LABELS[state];
  if (_statePill) {
    _statePill.textContent = lbl;
    _statePill.className = "state-pill state-" + state;
  }
  if (_dashPill) {
    _dashPill.textContent = "● " + lbl;
    _dashPill.className = "dash-state-pill dash-state-" + state;
  }
}

export function setLastResponse(text: string): void {
  if (!_lastResp || !text) return;
  _lastResp.textContent = text;
  addActivity("Said: " + text.slice(0, 46) + (text.length > 46 ? "..." : ""));
}

export function setCurrentFocus(text: string): void {
  if (_focus) _focus.textContent = text;
}

export function addActivity(item: string): void {
  _activity.unshift(item);
  if (_activity.length > MAX_ACTIVITY) _activity.pop();
  _renderActivity();
}

function _renderActivity(): void {
  if (!_actList) return;
  _actList.innerHTML = _activity.map(i => "<li>" + i + "</li>").join("");
}
