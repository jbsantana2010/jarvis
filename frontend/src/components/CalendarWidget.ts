/**
 * CalendarWidget.ts — Today's schedule from Google Calendar.
 * Polls /api/dashboard/calendar every 5 minutes.
 */

interface CalEvent {
  title: string;
  start: string | null;
  end: string | null;
  start_iso: string;
  location: string;
  all_day: boolean;
}

function fmt12(t: string): string {
  const [h, m] = t.split(":").map(Number);
  const ampm = h >= 12 ? "PM" : "AM";
  const h12  = h % 12 || 12;
  return `${h12}:${String(m).padStart(2, "0")} ${ampm}`;
}

function todayLabel(): string {
  return new Date().toLocaleDateString("en-US", { weekday: "long", month: "short", day: "numeric" });
}

function isNow(ev: CalEvent): boolean {
  if (ev.all_day || !ev.start_iso) return false;
  const now = Date.now();
  const start = new Date(ev.start_iso).getTime();
  // Approximate end by adding 1h if no end
  const end = ev.end ? new Date(ev.start_iso.slice(0, 11) + ev.end + ":00").getTime() : start + 3_600_000;
  return now >= start && now <= end;
}

function render(el: HTMLElement, events: CalEvent[], error?: string): void {
  const rows = events.length === 0
    ? `<div class="widget-empty">No events today</div>`
    : events.map(ev => {
        const time  = ev.all_day ? "All day" : (ev.start ? fmt12(ev.start) : "");
        const now   = isNow(ev) ? `<span class="badge badge-live" style="font-size:8px">NOW</span>` : "";
        const loc   = ev.location ? `<div class="cal-location">📍 ${ev.location}</div>` : "";
        return `
          <div class="cal-row">
            <div class="cal-time">${time}</div>
            <div class="cal-body">
              <div class="cal-title">${ev.title} ${now}</div>
              ${loc}
            </div>
          </div>`;
      }).join("");

  el.innerHTML = `
    <div class="widget-header">
      <span class="widget-label">Schedule</span>
      <span class="cal-date">${todayLabel()}</span>
    </div>
    ${error ? `<div class="widget-empty" style="color:#FF8B95">${error}</div>` : ""}
    <div class="cal-list">${rows}</div>`;
}

async function poll(el: HTMLElement): Promise<void> {
  try {
    const r = await fetch("/api/dashboard/calendar");
    if (!r.ok) throw new Error("non-ok");
    const d = await r.json();
    render(el, d.events ?? [], d.error);
  } catch {
    render(el, [], "Calendar unavailable");
  }
}

export function mountCalendarWidget(el: HTMLElement): void {
  render(el, []);           // placeholder while loading
  poll(el);
  setInterval(() => poll(el), 5 * 60 * 1000);  // refresh every 5 min
}
