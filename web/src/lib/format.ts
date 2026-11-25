// Human dates, times and phone numbers, in one place. India: en-IN, 12-hour clock, and India time
// whatever the computer's own time zone ("today" is the server's today: Asia/Kolkata).

const pad = (n: number) => String(n).padStart(2, "0");
/** A calendar date (built from y/m/d, not a moment in time) as YYYY-MM-DD. */
export const isoDay = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const TIME_ZONE = "Asia/Kolkata";
const parts = new Intl.DateTimeFormat("en-CA", { timeZone: TIME_ZONE, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hourCycle: "h23" });
/** A moment as India sees it: its day, "HH:MM", hours since midnight and seconds. */
export function ist(d: Date): { day: string; hhmm: string; hours: number; seconds: number } {
  const p = Object.fromEntries(parts.formatToParts(d).map((x) => [x.type, x.value]));
  const h = Number(p.hour) % 24, m = Number(p.minute);
  return { day: `${p.year}-${p.month}-${p.day}`, hhmm: `${pad(h)}:${pad(m)}`, hours: h + m / 60, seconds: Number(p.second) };
}
export const today = (now = new Date()) => ist(now).day;
export function addDays(iso: string, n: number): string {
  const [y, m, d] = iso.split("-").map(Number);
  return isoDay(new Date(y!, m! - 1, d! + n));
}

/** "Today", "Tomorrow", "Yesterday", else "Tue 24 Nov" (with the year when it is not this year). */
export function fmtDay(iso: unknown, now = new Date()): string {
  if (typeof iso !== "string" || !/^\d{4}-\d{2}-\d{2}/.test(iso)) return "";
  const day = iso.slice(0, 10);
  const t = today(now);
  if (day === t) return "Today";
  if (day === addDays(t, 1)) return "Tomorrow";
  if (day === addDays(t, -1)) return "Yesterday";
  const [y, m, d] = day.split("-").map(Number);
  const date = new Date(y!, m! - 1, d!);
  const s = date.toLocaleDateString("en-IN", { weekday: "short", day: "numeric", month: "short" }).replace(",", "");
  return String(y) === t.slice(0, 4) ? s : `${s} ${y}`;
}

/** "15:30" -> "3:30 pm". */
export function fmtTime(hhmm: unknown): string {
  if (typeof hhmm !== "string" || !/^\d{1,2}:\d{2}/.test(hhmm)) return "";
  const [h, m] = hhmm.split(":").map(Number);
  return `${((h! + 11) % 12) + 1}:${pad(m!)} ${h! >= 12 ? "pm" : "am"}`;
}

/** A booking's slot: "Today, 3:30 pm". */
export function fmtSlot(day: unknown, time: unknown, now = new Date()): string {
  return [fmtDay(day, now), fmtTime(time)].filter(Boolean).join(", ");
}

/** An ISO timestamp: "Today, 3:30 pm" / "Tue 24 Nov, 3:30 pm". */
export function fmtStamp(iso: unknown, now = new Date()): string {
  if (typeof iso !== "string") return "";
  const d = new Date(iso);
  if (isNaN(d.getTime())) return "";
  const at = ist(d);
  return fmtSlot(at.day, at.hhmm, now);
}

/** "+919876500000" -> "+91 98765 00000"; anything else is shown as given. */
export function fmtPhone(p: unknown): string {
  if (typeof p !== "string") return "";
  const m = p.replace(/\s/g, "").match(/^\+91(\d{5})(\d{5})$/);
  return m ? `+91 ${m[1]} ${m[2]}` : p;
}

export const mapsUrl = (address: string) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
