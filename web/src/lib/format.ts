// Human dates, times and phone numbers, in one place. India: en-IN, 12-hour clock.

const pad = (n: number) => String(n).padStart(2, "0");
export const isoDay = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
export const today = (now = new Date()) => isoDay(now);
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
  return y === now.getFullYear() ? s : `${s} ${y}`;
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
  return fmtSlot(isoDay(d), `${d.getHours()}:${pad(d.getMinutes())}`, now);
}

/** "+919876500000" -> "+91 98765 00000"; anything else is shown as given. */
export function fmtPhone(p: unknown): string {
  if (typeof p !== "string") return "";
  const m = p.replace(/\s/g, "").match(/^\+91(\d{5})(\d{5})$/);
  return m ? `+91 ${m[1]} ${m[2]}` : p;
}

export const mapsUrl = (address: string) => `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(address)}`;
