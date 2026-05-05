import { initBrain, setBrainState, setLastResponse, addActivity } from "./components/JarvisBrain";
import type { VoiceState } from "./components/JarvisBrain";
import { mountNextAction } from "./components/NextAction";
import { mountOBSWidget } from "./components/OBSWidget";
import { mountSpotifyWidget } from "./components/SpotifyWidget";
import { mountProjectWidget } from "./components/ProjectWidget";
import { mountCalendarWidget } from "./components/CalendarWidget";

export function initDashboard(): void {
  initBrain();
  const naEl  = document.getElementById("next-action-widget");
  const spEl  = document.getElementById("spotify-widget");
  const obsEl = document.getElementById("obs-widget");
  const pwEl  = document.getElementById("project-widget");
  const calEl = document.getElementById("calendar-widget");
  if (naEl)  mountNextAction(naEl);
  if (spEl)  mountSpotifyWidget(spEl);
  if (obsEl) mountOBSWidget(obsEl);
  if (pwEl)  mountProjectWidget(pwEl);
  if (calEl) mountCalendarWidget(calEl);
}

export function dashboardVoiceState(state: VoiceState): void { setBrainState(state); }
export function dashboardResponse(text: string): void { setLastResponse(text); }
export function dashboardActivity(item: string): void { addActivity(item); }
