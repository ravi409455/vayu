export const FIELD_TYPES: { id: string; label: string; group: string }[] = [
  { id: "short_text", label: "Short text", group: "Text" }, { id: "long_text", label: "Long text", group: "Text" },
  { id: "number", label: "Number", group: "Text" }, { id: "currency", label: "Money (₹)", group: "Text" },
  { id: "phone", label: "Phone", group: "Text" }, { id: "date", label: "Date", group: "Text" },
  { id: "time", label: "Time", group: "Text" }, { id: "datetime", label: "Date and time", group: "Text" },
  { id: "single_choice", label: "Choose one", group: "Choices" }, { id: "multi_choice", label: "Choose several", group: "Choices" },
  { id: "yes_no", label: "Yes / No", group: "Choices" }, { id: "master_list", label: "From a master list", group: "Choices" },
  { id: "user_picker", label: "Pick a user", group: "Choices" },
  { id: "photo", label: "Photos", group: "Media" }, { id: "video", label: "Videos", group: "Media" },
  { id: "file", label: "Files", group: "Media" }, { id: "signature", label: "Signature", group: "Media" },
  { id: "gps", label: "GPS location", group: "Media" },
  { id: "image", label: "Picture (shown to the expert)", group: "Display" },
  { id: "derived", label: "Key Check (old, Yes/No)", group: "Old" }, { id: "rating", label: "Rating (automatic)", group: "Automatic" },
];
/** Types the system makes (not offered when adding a field) with the name to show for them. */
export const SYSTEM_TYPE_LABELS: Record<string, string> = { form_choice: "Pick of a custom form" };
export const CHOICE_TYPES = ["single_choice", "multi_choice"];
export const MEDIA_TYPES = ["photo", "video", "file", "signature"];

/** What a new photo shows: the nearest check above it in its section (not a remark or another photo). */
export function photoOfDefault(fields: { key: string; type: string }[]): string | undefined {
  return [...fields].reverse().find((f) => ![...MEDIA_TYPES, "image", "short_text", "long_text"].includes(f.type))?.key;
}

/** A sensible starting config for a new field of this type. */
export function defaultConfig(type: string): Record<string, unknown> {
  switch (type) {
    case "single_choice": case "multi_choice": return { options: [{ key: "ok", label: "OK" }, { key: "not_ok", label: "Not OK", is_defect: true, severity: "minor" }] };
    case "master_list": return { list: "" };
    case "user_picker": return { role: "expert" };
    case "photo": case "video": case "file": return { max_count: type === "video" ? 1 : 5 };
    case "image": return {};
    case "derived": return { rule: { "!!": [{ var: "inspection.chassis_no" }] }, true_label: "Yes", false_label: "No" };
    case "rating": return { category: "" };
    default: return {};
  }
}

export function slugKey(label: string): string {
  const k = label.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "");
  return /^[a-z]/.test(k) ? k.slice(0, 63) : `f_${k}`.slice(0, 63);
}

/** The type of a field in words, with the detail that matters ("Choose one · 4 choices", "Number · km"). */
export function typeSummary(f: { type: string; config: Record<string, unknown> }): string {
  const name = FIELD_TYPES.find((t) => t.id === f.type)?.label ?? SYSTEM_TYPE_LABELS[f.type] ?? f.type;
  const c = f.config ?? {};
  const n = Array.isArray(c.options) ? c.options.length : 0;
  if (CHOICE_TYPES.includes(f.type) || f.type === "form_choice") return n ? `${name} · ${n} choice${n === 1 ? "" : "s"}` : name;
  if (f.type === "number" && c.unit) return `${name} · ${String(c.unit)}`;
  if ((f.type === "photo" || f.type === "video") && c.capture === "camera") return `${name} · camera only`;
  if (["date", "time", "datetime", "gps"].includes(f.type) && (c.auto === true || (f.type === "gps" && c.auto !== false))) return `${name} · automatic`;
  return name;
}
