import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useList } from "../api/hooks";
import type { FormSummary, FormVersion, Inspection } from "../api/types";

const load = (id?: number | null) => (id ? api<FormVersion>(`form-versions/${id}`) : Promise.resolve(null));

/** The live (published) form trees: booking, start, end, and the custom form for an inspection type. */
export function useTrees(inspectionType?: string) {
  const forms = useList<FormSummary>("forms", "forms");
  const pick = (type: string) => (forms.data ?? []).find((f) => f.type === type && f.is_active && (type !== "custom" || f.inspection_type === inspectionType));
  const ids = { booking: pick("booking")?.published_version?.id, start: pick("start")?.published_version?.id, end: pick("end")?.published_version?.id, inspection: pick("custom")?.published_version?.id };
  const trees = useQuery({ queryKey: ["live-trees", ids.booking, ids.start, ids.end, ids.inspection], enabled: forms.isSuccess,
    queryFn: async () => ({ booking: await load(ids.booking), start: await load(ids.start), end: await load(ids.end), inspection: await load(ids.inspection) }) });
  return { ...(trees.data ?? { booking: null, start: null, end: null, inspection: null }), loading: forms.isLoading || trees.isLoading };
}

/** The exact versions one inspection was started on (what Ops review and edit): start / end are
 *  null when the inspection does not use them. */
export function usePinnedTrees(insp?: Pick<Inspection, "form_version" | "start_version" | "end_version">) {
  const q = useQuery({ queryKey: ["pinned-trees", insp?.form_version, insp?.start_version, insp?.end_version], enabled: !!insp,
    queryFn: async () => ({ inspection: await load(insp!.form_version), start: await load(insp!.start_version), end: await load(insp!.end_version) }) });
  return { ...(q.data ?? { inspection: null, start: null, end: null }), loading: q.isLoading };
}
