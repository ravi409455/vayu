import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useList } from "../api/hooks";
import type { FormSummary, FormVersion } from "../api/types";

export type RefChoice = { value: string; label: string; type: string };

/** Every field of the booking, check-in and the given inspection form, named like rules and
 *  PDF templates name them: "booking.city", "inspection.door". */
export function useRefChoices(inspectionFormId?: number): RefChoice[] {
  const forms = useList<FormSummary>("forms", "forms");
  const wanted = (forms.data ?? []).filter((f) => f.kind !== "inspection" || f.id === inspectionFormId);
  const ids = wanted.map((f) => ({ kind: f.kind, id: f.draft_version?.id ?? f.published_version?.id })).filter((x) => x.id);
  const trees = useQuery({
    queryKey: ["ref-trees", ids.map((x) => `${x.kind}:${x.id}`).join(",")],
    enabled: ids.length > 0,
    queryFn: async () => Promise.all(ids.map(async (x) => ({ kind: x.kind, v: await api<FormVersion>(`form-versions/${x.id}`) }))),
  });
  return useMemo(() => {
    const out: RefChoice[] = [];
    for (const t of trees.data ?? [])
      for (const p of t.v.pages) for (const s of p.sections) for (const f of s.fields)
        out.push({ value: `${t.kind}.${f.key}`, label: `${t.kind}: ${f.label || f.key}`, type: f.type });
    return out;
  }, [trees.data]);
}
