export type Role = "admin" | "ops" | "expert";
export type Me = {
  id: number;
  username: string;
  name: string;
  email?: string;
  phone?: string;
  role: Role;
  is_active?: boolean;
  must_change_password?: boolean;
  permissions: Record<string, "all" | "own">;
  theme?: "light" | "dark" | "system";
  avatar_url?: string | null;
};
export type User = {
  id: number;
  username: string;
  name: string;
  email: string;
  phone?: string;
  role: Role;
  is_active: boolean;
  must_change_password: boolean;
  avatar_url?: string | null;
  last_login?: string | null;
};
export type Access = Record<string, Record<string, "hidden" | "view" | "edit">>;
/** tone: the colour of this answer in the PDF report (green, amber, red, grey); unset = from the meaning. */
export type Option = { key: string; label: string; is_defect?: boolean; severity?: string | null; tone?: "ok" | "warn" | "bad" | "muted" };
export type FormField = {
  id: number;
  section: number;
  key: string;
  label: string;
  helper_text: string;
  type: string;
  config: Record<string, unknown>;
  required: boolean;
  required_if: unknown;
  show_if: unknown;
  visible: boolean;
  order: number;
  is_system: boolean;
  access: Access;
  locked: boolean;
  library: { item: number; revision: number | null; update_available: boolean } | null;
  level?: "view" | "edit";
};
export type FormSection = {
  id: number;
  page: number;
  key?: string;
  title: string;
  order: number;
  visible: boolean;
  show_if: unknown;
  access: Access;
  fields: FormField[];
  locked: boolean;
  library: { item: number; revision: number | null; update_available: boolean } | null;
};
export type FormPage = {
  id: number;
  title: string;
  order: number;
  visible: boolean;
  gate: boolean;
  show_if: unknown;
  access: Access;
  sections: FormSection[];
};
export type Check = { id: number; rule: unknown; message: string; fields: string[]; order: number };
export type FormVersion = {
  id: number;
  form: number;
  number: number;
  status: "draft" | "published";
  published_at: string | null;
  row_version: number;
  pages: FormPage[];
  checks: Check[];
  rating_config?: RatingConfig;
  key_checks?: KeyCheck[];
  use_start?: boolean;
  use_end?: boolean;
};
export type KeyCheckType = "text" | "number" | "date" | "linked" | "rule";
/** A fact Ops review on each booking (see backend apps/scoring/keychecks.py). */
export type KeyCheck = {
  key: string;
  label: string;
  type: KeyCheckType;
  default?: string;
  in_report?: boolean;
  fields?: string[];
  combine?: "join" | "template";
  separator?: string;
  template?: string;
  rule?: Record<string, unknown>;
  true_label?: string;
  false_label?: string;
};
export type KeyCheckValue = { auto: string; value: string; edited: boolean };
export type RatingConfig = {
  categories?: { key: string; label: string; sections: string[]; cap?: number | null }[];
  deductions?: { minor: number; major: number; critical: number };
  thresholds?: Record<string, number>;
};
/** booking, start and end always exist once (Admins name them); custom forms are what Admins build. */
export type FormType = "booking" | "start" | "end" | "custom";
export type FormSummary = {
  id: number;
  key: string;
  type: FormType;
  name: string;
  is_active: boolean;
  inspection_type: string;
  submission_roles?: string[];
  draft_version: { id: number; number: number; use_start?: boolean; use_end?: boolean } | null;
  published_version: { id: number; number: number; use_start?: boolean; use_end?: boolean } | null;
};
export type MasterList = { id: number; key: string; name: string; items?: MasterListItem[] };
export type MasterListItem = { id: number; key: string; label: string; order: number; archived: boolean };
export type Booking = {
  id: string;
  booking_id: string;
  stage: string;
  ops_status: string;
  inspection_type: string;
  assigned_expert: number | null;
  answers: Record<string, unknown>;
  row_version: number;
  started_at: string | null;
  finished_at?: string | null;
  cancel_reason: string;
  last_edited_by: string | null;
  last_edited_at: string | null;
  created_at: string;
  conflict?: string;
  alerts?: { code: string; detail: string; at: string }[];
  /** a time on it was stamped by a phone whose clock was not checked with the server that day (F-222) */
  unverified_time?: boolean;
  /** Admin / Ops only: started late, finished too quickly (server clock, minutes). */
  timing?: {
    late_minutes: number | null;
    duration_minutes: number | null;
    late: boolean;
    quick: boolean;
    min_minutes: number;
    grace_minutes: number;
    late_reviewed_by: string | null;
    late_reviewed_at: string | null;
    quick_reviewed_by: string | null;
    quick_reviewed_at: string | null;
  };
};
export type Inspection = {
  id: string;
  booking: string;
  expert: number;
  status: string;
  unverified_time?: boolean;
  answers: { inspection?: Record<string, unknown>; start?: Record<string, unknown>; end?: Record<string, unknown> };
  scores?: Scores;
  overrides?: Record<string, unknown>;
  row_version: number;
  form_version: number;
  start_version?: number | null;
  end_version?: number | null;
  submitted_at: string | null;
  last_edited_by?: string | null;
  last_edited_at?: string | null;
};
export type Scores = {
  derived?: Record<string, unknown>;
  defects?: string[];
  ratings?: Record<string, { suggested: number; value: number; overridden: boolean }>;
  overall?: { average: number; word: string; suggested_word: string; overridden: boolean };
  fields?: Record<string, number>;
  key_checks?: Record<string, KeyCheckValue>;
};
export type Delivery = {
  id: string;
  event: string;
  booking_id: string;
  status: string;
  attempts: number;
  response_status: number | null;
  error: string;
  next_retry_at: string | null;
  created_at: string;
};
export type Integration = {
  id: string;
  form: number;
  form_key: string;
  name: string;
  event: string;
  method: string;
  url: string;
  query: { key: string; value: string }[];
  headers: { key: string; value: string }[];
  body_mode: "standard" | "custom";
  body: unknown;
  include_data: boolean;
  include_pdf: boolean;
  include_image_zip: boolean;
  include_video_zip: boolean;
  fields: string[];
  is_active: boolean;
  broken_refs: string[];
};
/** Booking actions a key may take besides reading and editing (each off until the Admin turns it on). */
export type KeyAction = "assign" | "cancel" | "reschedule" | "change_type";
export type ApiKeyRow = {
  id: string;
  name: string;
  prefix: string;
  scope: { forms: Record<string, string[]> };
  allow_delete: boolean;
  allowed_actions: KeyAction[];
  revoked_at: string | null;
  last_used_at: string | null;
  key?: string;
};
export type PermissionRow = { key: string; group: string; label: string; scoped: boolean; grantable: boolean };
