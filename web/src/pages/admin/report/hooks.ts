import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, type Page } from "../../../api/client";
import { keys } from "../../../api/keys";
import type { Booking, FormVersion } from "../../../api/types";
import type { SectionChoice } from "./PartSettings";

/** Finished bookings of this inspection type, to preview a report with. */
export function useSampleBookings(type: string | undefined) {
  return useQuery({ queryKey: keys.pdfSample(type), enabled: !!type,
    queryFn: async ({ signal }) => (await Promise.all(["completed", "submitted"].map((stage) => api<Page<Booking>>("bookings", { query: { type, stage }, signal })))).flatMap((r) => r.results) });
}

/** The form a report is for: its tree, its sections to pick from, and each section's name. */
export function useFormSections(formVersionId: number | undefined) {
  const tree = useQuery({ queryKey: keys.formVersion(formVersionId), enabled: !!formVersionId, queryFn: ({ signal }) => api<FormVersion>(`form-versions/${formVersionId}`, { signal }) });
  const sections: SectionChoice[] = useMemo(() => (tree.data?.pages ?? []).flatMap((p) => p.sections.filter((s) => s.key).map((s) => ({
    value: `inspection.${s.key}`, label: `${p.title} → ${s.title} (${s.fields.length})`, fields: s.fields.map((f) => ({ key: f.key, label: f.label || f.key, type: f.type })) }))), [tree.data]);
  const sectionNames = useMemo(() => Object.fromEntries((tree.data?.pages ?? []).flatMap((p) => p.sections.map((s) => [`inspection.${s.key}`, s.title]))), [tree.data]);
  return { tree, sections, sectionNames };
}
