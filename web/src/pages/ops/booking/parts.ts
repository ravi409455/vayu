import type { FormPage, FormSection, FormVersion, Inspection } from "../../../api/types";
import { maxFiles, MEDIA_TYPES, UPLOAD_TYPES } from "../../../lib/fieldTypes";
import type { Answers } from "../../../lib/formSpec";
import { usePinnedTrees } from "../../../lib/useTrees";
import { defectOf } from "../../../ui/AnswerSheet";

export type Activity = {
  at: string;
  kind: string;
  by: { id: number; name: string; role: string } | null;
  changes: Record<string, [unknown, unknown]>;
  keys: string[];
};
export const labelOf = (tree: FormVersion | null | undefined, key: string) =>
  tree?.pages.flatMap((p) => p.sections.flatMap((s) => s.fields)).find((f) => f.key === key)?.label || key;

export const onlySection = (page: FormPage, s: FormSection): FormPage[] => [{ ...page, sections: [s] }];

export type Trees = ReturnType<typeof usePinnedTrees>;
export type Part = "inspection" | "start" | "end";
export type Parts = Record<Part, Answers>;
export const NO_ANSWERS: Parts = { inspection: {}, start: {}, end: {} };
export const PART_ORDER: Part[] = ["start", "inspection", "end"];

export type MediaField = {
  key: string;
  label: string;
  type: string;
  part: Part;
  section: string;
  max: number;
  opsOk: boolean;
  accept: string;
};
// what the file picker offers (the server checks the same: a file field's "allowed" setting)
const FILE_ACCEPT: Record<string, string> = { image: "image/jpeg,image/png", pdf: "application/pdf" };
const acceptFor = (f: { type: string; config: Record<string, unknown> }) =>
  f.type === "video"
    ? "video/*"
    : f.type === "file"
      ? ((f.config.allowed as string[] | undefined) ?? ["image", "pdf"]).map((a) => FILE_ACCEPT[a]).join(",")
      : "image/*";

export const toMediaField = (f: FormPage["sections"][number]["fields"][number], part: Part, section: string): MediaField => ({
  key: f.key,
  label: f.label || f.key,
  type: f.type,
  part,
  section,
  max: maxFiles(f),
  accept: acceptFor(f),
  opsOk: UPLOAD_TYPES.includes(f.type) && f.config.ops_upload !== false,
});

export function mediaFields(trees: Trees): MediaField[] {
  const out: MediaField[] = [];
  for (const part of PART_ORDER)
    trees[part]?.pages.forEach((p) =>
      p.sections.forEach((s) =>
        s.fields.forEach((f) => {
          if (MEDIA_TYPES.includes(f.type)) out.push(toMediaField(f, part, s.title || p.title));
        }),
      ),
    );
  return out;
}

export const idsOf = (insp: Inspection, part: Part, key: string): string[] => {
  const v = (insp.answers[part] ?? {})[key];
  return Array.isArray(v) ? (v as string[]) : v ? [String(v)] : [];
};

/** The choice question in the same section a photo belongs to (what it shows: OK, dented...). */
export function nearestChoice(trees: Trees, f: MediaField) {
  const tree = trees[f.part];
  const sec = tree?.pages.flatMap((p) => p.sections).find((s) => s.fields.some((x) => x.key === f.key));
  const fields = sec?.fields ?? [];
  const i = fields.findIndex((x) => x.key === f.key);
  return [...fields.slice(0, i)].reverse().find((x) => x.type === "single_choice" || x.type === "multi_choice");
}
export function defectFor(insp: Inspection, trees: Trees, f: MediaField): string | null {
  const q = nearestChoice(trees, f);
  return q ? defectOf(q, (insp.answers[f.part] ?? {})[q.key]) : null;
}
