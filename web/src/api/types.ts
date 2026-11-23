export type Role = "admin" | "ops" | "expert";
export type Me = {
  id: number; username: string; name: string; email?: string; phone?: string; role: Role; is_active?: boolean;
  must_change_password?: boolean; permissions: Record<string, "all" | "own">;
  theme?: "light" | "dark" | "system"; avatar_url?: string | null;
};
export type User = {
  id: number; username: string; name: string; email: string; phone?: string; role: Role;
  is_active: boolean; must_change_password: boolean; avatar_url?: string | null; last_login?: string | null;
};
export type Access = Record<string, Record<string, "hidden" | "view" | "edit">>;
/** tone: the colour of this answer in the PDF report (green, amber, red, grey); unset = from the meaning. */
export type Option = { key: string; label: string; is_defect?: boolean; severity?: string | null; tone?: "ok" | "warn" | "bad" | "muted" };
export type FormField = {
  id: number; section: number; key: string; label: string; helper_text: string; type: string;
  config: Record<string, unknown>; required: boolean; required_if: unknown; show_if: unknown;
  visible: boolean; order: number; is_system: boolean; access: Access; locked: boolean;
  library: { item: number; revision: number | null; update_available: boolean } | null;
  level?: "view" | "edit";
};
export type FormSection = {
  id: number; page: number; key?: string; title: string; order: number; visible: boolean; show_if: unknown;
  access: Access; fields: FormField[]; locked: boolean;
  library: { item: number; revision: number | null; update_available: boolean } | null;
};
export type FormPage = {
  id: number; title: string; order: number; visible: boolean; gate: boolean; show_if: unknown; access: Access;
  sections: FormSection[];
};
export type Check = { id: number; rule: unknown; message: string; fields: string[]; order: number };
export type FormVersion = {
  id: number; form: number; number: number; status: "draft" | "published"; published_at: string | null;
  row_version: number; pages: FormPage[]; checks: Check[]; rating_config?: RatingConfig;
  use_start?: boolean; use_end?: boolean;
};
export type RatingConfig = {
  categories?: { key: string; label: string; sections: string[]; cap?: number | null }[];
  deductions?: { minor: number; major: number; critical: number };
  thresholds?: Record<string, number>;
};
/** booking, start and end always exist once (Admins name them); custom forms are what Admins build. */
export type FormType = "booking" | "start" | "end" | "custom";
export type FormSummary = {
  id: number; key: string; type: FormType; name: string; is_active: boolean;
  inspection_type: string; submission_roles?: string[];
  draft_version: { id: number; number: number; use_start?: boolean; use_end?: boolean } | null;
  published_version: { id: number; number: number; use_start?: boolean; use_end?: boolean } | null;
};
export type MasterList = { id: number; key: string; name: string; items?: MasterListItem[] };
export type MasterListItem = { id: number; list: number; key: string; label: string; order: number; archived: boolean };
export type Booking = {
  id: string; booking_id: string; stage: string; ops_status: string; inspection_type: string;
  assigned_expert: number | null; answers: Record<string, unknown>; row_version: number;
  started_at: string | null; cancel_reason: string; last_edited_by: string | null;
  last_edited_at: string | null; created_at: string; conflict?: string; alerts?: { code: string; detail: string; at: string }[];
};
export type Inspection = {
  id: string; booking: string; expert: number; status: string; answers: { inspection?: Record<string, unknown>; start?: Record<string, unknown>; end?: Record<string, unknown> };
  scores?: Scores; overrides?: Record<string, unknown>; row_version: number; form_version: number; start_version?: number | null; end_version?: number | null;
  submitted_at: string | null; last_edited_by?: string | null; last_edited_at?: string | null;
};
export type Scores = {
  derived?: Record<string, unknown>; defects?: string[];
  ratings?: Record<string, { suggested: number; value: number; overridden: boolean }>;
  overall?: { average: number; word: string; suggested_word: string; overridden: boolean };
  fields?: Record<string, number>;
};
export type Delivery = {
  id: string; event: string; booking_id: string; status: string; attempts: number;
  response_status: number | null; error: string; next_retry_at: string | null; created_at: string;
};
export type BodyRow = { key: string; value?: string; as_text?: boolean; fixed?: string | number | boolean; rows?: BodyRow[] };
export type Integration = {
  id: string; form: number; form_key: string; name: string; event: string; method: string; url: string;
  query: { key: string; value: string }[]; headers: { key: string; value: string }[];
  body_mode: "standard" | "custom"; body: { rows?: BodyRow[] };
  include_data: boolean; include_pdf: boolean; include_image_zip: boolean; include_video_zip: boolean;
  fields: string[]; is_active: boolean; broken_refs: string[];
};
export type ApiKeyRow = {
  id: string; name: string; prefix: string; scope: { forms: Record<string, string[]> };
  allow_delete: boolean; revoked_at: string | null; last_used_at: string | null; key?: string;
};
export type AuditRow = { id: number; actor_name?: string; actor?: string; action: string; target_type: string; target_id: string; summary: string; created_at: string };
export type PermissionRow = { key: string; group: string; label: string; scoped: boolean; grantable: boolean };
export type Role_ = { role: string; permissions: Record<string, "all" | "own"> };
