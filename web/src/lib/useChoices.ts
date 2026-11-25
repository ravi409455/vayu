import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useList } from "../api/hooks";
import type { FormSummary, FormVersion } from "../api/types";
import { keys } from "../api/keys";

export type RefChoice = { value: string; label: string; type: string };
type Want = { ns: string; id: number };
type Tree = { ns: string; v: FormVersion };

/** The name a form's answers go by in rules: the custom form is "inspection". */
export const nsOf = (type: string) => (type === "custom" ? "inspection" : type) as "booking" | "start" | "end" | "inspection";

/** A custom form offers start / end only while it begins / ends with them (otherwise a rule on them
 *  cannot be published). */
const offers = (type: string, own: { use_start?: boolean; use_end?: boolean } | null | undefined) =>
  !(type === "start" && own?.use_start === false) && !(type === "end" && own?.use_end === false);

/** The given form versions, fetched together. */
function useVersions(want: Want[]): Tree[] | undefined {
  const ids = want.map((x) => `${x.ns}:${x.id}`).join(",");
  return useQuery({
    queryKey: keys.formVersions("set", ids), enabled: want.length > 0,
    queryFn: async ({ signal }) => Promise.all(want.map(async (x) => ({ ns: x.ns, v: await api<FormVersion>(`form-versions/${x.id}`, { signal }) }))),
  }).data;
}

/** Every field of these versions, named like rules and PDF templates name them: "booking.city". */
function fieldsOf(trees: Tree[]): RefChoice[] {
  return trees.flatMap((t) => t.v.pages.flatMap((p) => p.sections.flatMap((s) => s.fields.map((f) =>
    ({ value: `${t.ns}.${f.key}`, label: `${t.ns}: ${f.label || f.key}`, type: f.type })))));
}

/** For a PDF template: every field of the booking, start, end and the given custom form (drafts
 *  first), plus the Key Checks the report may show. */
export function useRefChoices(customFormId?: number): RefChoice[] {
  const forms = useList<FormSummary>(keys.forms(), "forms").data ?? [];
  const own = forms.find((f) => f.id === customFormId);
  const ownV = own?.draft_version ?? own?.published_version;
  const want = forms.filter((f) => (f.type === "custom" ? f.id === customFormId : offers(f.type, ownV)))
    .map((f) => ({ ns: nsOf(f.type), id: (f.draft_version?.id ?? f.published_version?.id)! })).filter((x) => x.id);
  const trees = useVersions(want);
  return useMemo(() => [
    ...fieldsOf(trees ?? []),
    ...(trees ?? []).flatMap((t) => (t.ns === "inspection" ? t.v.key_checks ?? [] : []).filter((k) => k.in_report !== false)
      .map((k) => ({ value: `check.${k.key}`, label: `Key Check: ${k.label}`, type: "text" }))),
  ], [trees]);
}

/** For the form builder: fields a condition can point at: the version being edited plus the other
 *  forms' published ones (booking, start, end; never another custom form). */
export function useFieldChoices(f: FormSummary | undefined, v: FormVersion | undefined): RefChoice[] {
  const forms = useList<FormSummary>(keys.forms(), "forms").data ?? [];
  const want = forms.filter((x) => x.type !== "custom" && x.type !== f?.type && !!x.published_version && (f?.type !== "custom" || offers(x.type, v)))
    .map((x) => ({ ns: nsOf(x.type), id: x.published_version!.id }));
  const trees = useVersions(want);
  const nsList = want.map((x) => x.ns).join(",");
  return useMemo(() => [
    ...(v ? fieldsOf([{ ns: f ? nsOf(f.type) : "inspection", v }]) : []),
    ...fieldsOf((trees ?? []).filter((t) => nsList.split(",").includes(t.ns))),
  ], [f, v, trees, nsList]);
}
