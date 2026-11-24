import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useList } from "../api/hooks";
import type { FormSummary, FormVersion } from "../api/types";

export type RefChoice = { value: string; label: string; type: string };

/** Every field of the booking, start, end and the given custom form, named like rules and PDF
 *  templates name them: "booking.city", "inspection.door", "start.selfie". Start / end are offered
 *  only when the custom form begins / ends with them (otherwise a rule on them cannot be published). */
export function useRefChoices(customFormId?: number): RefChoice[] {
  const forms = useList<FormSummary>("forms", "forms");
  const own = (forms.data ?? []).find((f) => f.id === customFormId);
  const v = own?.draft_version ?? own?.published_version;
  const useStart = v?.use_start !== false, useEnd = v?.use_end !== false;
  const wanted = (forms.data ?? []).filter((f) => (f.type === "custom" ? f.id === customFormId : f.type === "start" ? useStart : f.type === "end" ? useEnd : true));
  const ids = wanted.map((f) => ({ ns: f.type === "custom" ? "inspection" : f.type, id: f.draft_version?.id ?? f.published_version?.id })).filter((x) => x.id);
  const trees = useQuery({
    queryKey: ["ref-trees", ids.map((x) => `${x.ns}:${x.id}`).join(",")],
    enabled: ids.length > 0,
    queryFn: async () => Promise.all(ids.map(async (x) => ({ ns: x.ns, v: await api<FormVersion>(`form-versions/${x.id}`) }))),
  });
  return useMemo(() => {
    const out: RefChoice[] = [];
    for (const t of trees.data ?? [])
      for (const p of t.v.pages) for (const s of p.sections) for (const f of s.fields)
        out.push({ value: `${t.ns}.${f.key}`, label: `${t.ns}: ${f.label || f.key}`, type: f.type });
    for (const t of trees.data ?? [])            // Key Checks the report may show
      for (const k of t.ns === "inspection" ? t.v.key_checks ?? [] : [])
        if (k.in_report !== false) out.push({ value: `check.${k.key}`, label: `Key Check: ${k.label}`, type: "text" });
    return out;
  }, [trees.data]);
}
