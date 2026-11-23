import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { useList } from "../api/hooks";
import type { FormSummary, FormVersion } from "../api/types";

/** The live (published) form trees Ops work with: booking, check-in/wrap-up, and the inspection form for a type. */
export function useTrees(inspectionType?: string) {
  const forms = useList<FormSummary>("forms", "forms");
  const pick = (kind: string, type?: string) =>
    (forms.data ?? []).find((f) => f.kind === kind && f.is_active && (kind !== "inspection" || f.inspection_type === type));
  const ids = { booking: pick("booking")?.published_version?.id, ops: pick("ops")?.published_version?.id, inspection: pick("inspection", inspectionType)?.published_version?.id };
  const load = (id?: number) => (id ? api<FormVersion>(`form-versions/${id}`) : Promise.resolve(null));
  const trees = useQuery({ queryKey: ["live-trees", ids.booking, ids.ops, ids.inspection], enabled: forms.isSuccess,
    queryFn: async () => ({ booking: await load(ids.booking), ops: await load(ids.ops), inspection: await load(ids.inspection) }) });
  return { ...(trees.data ?? { booking: null, ops: null, inspection: null }), loading: forms.isLoading || trees.isLoading };
}
