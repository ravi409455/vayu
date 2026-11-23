// A library item's definition is plain JSON. The editor works on it through these small helpers:
// turn it into the field / tree shapes the form screens already know, and change it safely.
import type { Access, FormField, FormPage, FormVersion } from "../api/types";
import { defaultConfig } from "./fieldTypes";

export type FieldDef = {
  key: string; label: string; type: string; helper_text?: string; config?: Record<string, unknown>;
  required?: boolean; required_if?: unknown; show_if?: unknown; visible?: boolean; access?: Access;
};
export type SectionDef = { title: string; visible?: boolean; show_if?: unknown; access?: Access; fields: FieldDef[] };
export type Definition = FieldDef | SectionDef;
export const isSection = (d: Definition): d is SectionDef => "fields" in d;

/** The definition of a field as the FormField the field editor expects. */
export function asField(d: FieldDef, id = 0): FormField {
  return {
    id, section: 0, key: d.key, label: d.label, helper_text: d.helper_text ?? "", type: d.type as FormField["type"], config: d.config ?? {},
    required: d.required ?? false, required_if: d.required_if ?? null, show_if: d.show_if ?? null, visible: d.visible ?? true, order: id,
    is_system: false, access: d.access ?? {}, locked: false, library: null,
  } as FormField;
}

/** What the field editor hands back, written into the definition (key and type never change). */
export function withDraft(d: FieldDef, draft: Partial<FieldDef>): FieldDef {
  const { label, helper_text, config, required, required_if, show_if, visible, access } = draft;
  return {
    ...d,
    ...(label !== undefined && { label }), ...(helper_text !== undefined && { helper_text }), ...(config !== undefined && { config }),
    ...(required !== undefined && { required }), ...(required_if !== undefined && { required_if }), ...(show_if !== undefined && { show_if }),
    ...(visible !== undefined && { visible }), ...(access !== undefined && { access }),
  };
}

/** A one-page, one-section tree for the live preview. */
export function previewTree(kind: "field" | "section", d: Definition): Pick<FormVersion, "pages" | "checks"> {
  const fields = kind === "field" ? [d as FieldDef] : (d as SectionDef).fields;
  const page: FormPage = {
    id: 1, title: "Preview", order: 0, visible: true, gate: false, show_if: null, access: {},
    sections: [{
      id: 1, page: 1, title: kind === "section" ? (d as SectionDef).title : "Field", order: 0, visible: kind === "field" || ((d as SectionDef).visible ?? true),
      show_if: kind === "section" ? (d as SectionDef).show_if ?? null : null, access: kind === "section" ? (d as SectionDef).access ?? {} : {},
      fields: fields.map((f, i) => asField(f, i + 1)), locked: false, library: null,
    }],
  };
  return { pages: [page], checks: [] };
}

export function newFieldDef(key: string, label: string, type: string): FieldDef {
  return { key, label, type, helper_text: "", config: defaultConfig(type), required: false, visible: true, access: {} };
}

export const addFieldTo = (d: SectionDef, f: FieldDef): SectionDef => ({ ...d, fields: [...d.fields, f] });
export const removeFieldFrom = (d: SectionDef, key: string): SectionDef => ({ ...d, fields: d.fields.filter((f) => f.key !== key) });
export function moveField(d: SectionDef, key: string, by: -1 | 1): SectionDef {
  const i = d.fields.findIndex((f) => f.key === key);
  const j = i + by;
  if (i < 0 || j < 0 || j >= d.fields.length) return d;
  const fields = [...d.fields];
  [fields[i], fields[j]] = [fields[j]!, fields[i]!];
  return { ...d, fields };
}
export const replaceField = (d: SectionDef, f: FieldDef): SectionDef => ({ ...d, fields: d.fields.map((x) => (x.key === f.key ? f : x)) });

/** The names a rule inside an item may point at: its own fields and the system fields every form has. */
export function ruleChoices(kind: "field" | "section", d: Definition, system: { value: string; label: string }[]): { value: string; label: string }[] {
  const fields = kind === "field" ? [d as FieldDef] : (d as SectionDef).fields;
  return [...fields.map((f) => ({ value: `inspection.${f.key}`, label: `this item: ${f.label || f.key}` })), ...system];
}

export const SYSTEM_RULE_FIELDS = [
  { value: "inspection.chassis_no", label: "inspection: Chassis number" },
  ...["booking_id", "customer_name", "customer_phone", "address", "city", "inspection_date", "inspection_time", "inspection_type", "car_make_model", "lead_owner", "assigned_expert"]
    .map((k) => ({ value: `booking.${k}`, label: `booking: ${k.replace(/_/g, " ")}` })),
];

/** The same definition, to tell whether the editor has unsaved changes. */
export const sameDef = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);
