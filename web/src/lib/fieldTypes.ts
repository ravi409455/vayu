import {
  AlignLeft,
  Calendar,
  Image as ImageIcon,
  CalendarClock,
  CheckSquare,
  CircleDot,
  Clock,
  Camera,
  FileUp,
  Gauge,
  Hash,
  IndianRupee,
  ListChecks,
  List,
  MapPin,
  Phone,
  PenLine,
  Sparkles,
  ToggleLeft,
  Type,
  UserRound,
  Video,
  type LucideIcon,
} from "lucide-react";

/** Everything about one field type in one place (F-049): its name, where the builder offers it, its
 *  icon, the config a new field starts with, and the detail its summary adds. The form renderer's
 *  inputs (ui/FormRenderer) and the answer sheet's readers (ui/AnswerSheet) are keyed by the same
 *  ids, and a test checks every type here has both. */
export type TypeDef = {
  label: string;
  group: string;
  icon: LucideIcon;
  config?: () => Record<string, unknown>;
  detail?: (c: Record<string, unknown>) => string | undefined;
  /** Made by the system, never offered when adding a field. */
  system?: true;
};

const choices = (c: Record<string, unknown>) => {
  const n = Array.isArray(c.options) ? c.options.length : 0;
  return n ? `${n} choice${n === 1 ? "" : "s"}` : undefined;
};
const auto = (c: Record<string, unknown>) => (c.auto === true ? "automatic" : undefined);
const cameraOnly = (c: Record<string, unknown>) => (c.capture === "camera" ? "camera only" : undefined);
const media = () => ({ max_count: 1 });

export const TYPES: Record<string, TypeDef> = {
  short_text: { label: "Short text", group: "Text", icon: Type },
  long_text: { label: "Long text", group: "Text", icon: AlignLeft },
  number: { label: "Number", group: "Text", icon: Hash, detail: (c) => (c.unit ? String(c.unit) : undefined) },
  currency: { label: "Money (₹)", group: "Text", icon: IndianRupee },
  phone: { label: "Phone", group: "Text", icon: Phone },
  date: { label: "Date", group: "Text", icon: Calendar, detail: auto },
  time: { label: "Time", group: "Text", icon: Clock, detail: auto },
  datetime: { label: "Date and time", group: "Text", icon: CalendarClock, detail: auto },
  single_choice: {
    label: "Choose one",
    group: "Choices",
    icon: CircleDot,
    detail: choices,
    config: () => ({
      options: [
        { key: "ok", label: "OK" },
        { key: "not_ok", label: "Not OK", is_defect: true, severity: "minor" },
      ],
    }),
  },
  multi_choice: {
    label: "Choose several",
    group: "Choices",
    icon: ListChecks,
    detail: choices,
    config: () => ({
      options: [
        { key: "ok", label: "OK" },
        { key: "not_ok", label: "Not OK", is_defect: true, severity: "minor" },
      ],
    }),
  },
  yes_no: { label: "Yes / No", group: "Choices", icon: ToggleLeft },
  master_list: { label: "From a master list", group: "Choices", icon: List, config: () => ({ list: "" }) },
  user_picker: { label: "Pick a user", group: "Choices", icon: UserRound, config: () => ({ role: "expert" }) },
  photo: { label: "Photos", group: "Media", icon: Camera, config: media, detail: cameraOnly },
  video: { label: "Videos", group: "Media", icon: Video, config: media, detail: cameraOnly },
  file: { label: "Files", group: "Media", icon: FileUp, config: media },
  signature: { label: "Signature", group: "Media", icon: PenLine },
  gps: { label: "GPS location", group: "Media", icon: MapPin, detail: (c) => (c.auto !== false ? "automatic" : undefined) },
  image: { label: "Picture (shown to the expert)", group: "Display", icon: ImageIcon },
  derived: {
    label: "Key Check (old, Yes/No)",
    group: "Old",
    icon: Sparkles,
    config: () => ({ rule: { "!!": [{ var: "inspection.chassis_no" }] }, true_label: "Yes", false_label: "No" }),
  },
  rating: { label: "Rating (automatic)", group: "Automatic", icon: Gauge, config: () => ({ category: "" }) },
  form_choice: { label: "Pick of a custom form", group: "System", icon: CheckSquare, detail: choices, system: true },
};

/** The types the builder offers when adding a field, in order. */
export const FIELD_TYPES: { id: string; label: string; group: string }[] = Object.entries(TYPES)
  .filter(([, t]) => !t.system)
  .map(([id, t]) => ({ id, label: t.label, group: t.group }));
export const typeLabel = (type: string): string => TYPES[type]?.label ?? type;
export const iconFor = (type: string): LucideIcon => TYPES[type]?.icon ?? CheckSquare;

export const CHOICE_TYPES = ["single_choice", "multi_choice"];
/** Answers that are files (their value is a list of file ids). */
export const MEDIA_TYPES = ["photo", "video", "file", "signature"];
/** Media the person adds (or Ops adds for them) with a "most files" limit; a signature is drawn. */
export const UPLOAD_TYPES = ["photo", "video", "file"];
/** Fields with no text value to show or pick: the file answers and the builder's own pictures. */
export const NO_TEXT_TYPES = [...MEDIA_TYPES, "image"];
/** Fields nobody types into: the system works them out (derived, rating) or only shows them (image). */
export const NOT_ASKED_TYPES = ["derived", "rating", "image"];

/** What a new photo shows: the nearest check above it in its section (not a remark or another photo). */
export function photoOfDefault(fields: { key: string; type: string }[]): string | undefined {
  return [...fields].reverse().find((f) => ![...NO_TEXT_TYPES, "short_text", "long_text"].includes(f.type))?.key;
}

/** How many files a media field takes. Without its own maximum: 1, the same on the server, the phone
 *  and every web screen (agreed 2026-11-25, F-010). A signature is always one. */
export function maxFiles(f: { type: string; config: Record<string, unknown> }): number {
  return f.type === "signature" ? 1 : Number(f.config.max_count ?? 1);
}

/** A sensible starting config for a new field of this type. */
export function defaultConfig(type: string): Record<string, unknown> {
  return TYPES[type]?.config?.() ?? {};
}

/** "a-z, 0-9, _" key from a name, starting with a letter: "Car C.I.D." -> car_c_i_d. */
export function slugKey(label: string, prefix = "f_", max = 63): string {
  const k = label
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
  return /^[a-z]/.test(k) ? k.slice(0, max) : `${prefix}${k}`.slice(0, max);
}

/** The type of a field in words, with the detail that matters ("Choose one · 4 choices", "Number · km"). */
export function typeSummary(f: { type: string; config: Record<string, unknown> }): string {
  const name = typeLabel(f.type);
  const detail = TYPES[f.type]?.detail?.(f.config ?? {});
  return detail ? `${name} · ${detail}` : name;
}
