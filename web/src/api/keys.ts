// Every TanStack Query key, in one place (F-014). The first part is the family; refreshing a family
// (`keys.booking()`) reaches every query under it, so a screen never has to guess another's names.
type Query = Record<string, string | number | undefined>;
type Id = string | number | undefined | null;
const with_ = (root: string, ...rest: unknown[]) => (rest.length && rest[0] !== undefined ? [root, ...rest] : [root]);

export const keys = {
  me: () => ["me"],
  appLatest: () => ["app-latest"],
  /** Users: every list (all, experts, by role) shares the family, so an edit refreshes them all. */
  users: (query?: Query) => with_("users", query),
  forms: () => ["forms"],
  form: (id: Id) => ["forms", "one", id],
  /** Form versions, one or several at a time: one family, so a save refreshes every copy. */
  formVersion: (id?: Id) => with_("form-versions", id),
  formVersions: (kind?: "live" | "pinned" | "set", ...ids: Id[]) => with_("form-versions", kind, ...ids),
  masterLists: () => ["master-lists"],
  /** The items of one master list (cities, reasons...); the Admin's list with archived ones too. */
  listItems: (list?: string, archived?: boolean) => (archived ? ["list-items", list, "archived"] : with_("list-items", list)),
  inspectionTypes: () => ["inspection-types"],
  /** Booking lists and counts (pages, views, Today, my leads, search). */
  bookings: (...parts: unknown[]) => with_("bookings", ...parts),
  /** One booking, and what hangs off it (inspections, activity, report, media, missing files). */
  booking: (id?: string) => with_("booking", id),
  bookingPart: (id: string, part: "inspections" | "activity" | "report" | "media" | "missing-files", ...rest: unknown[]) => ["booking", id, part, ...rest],
  answerFields: (type: string) => ["answer-fields", type],
  problems: (...parts: unknown[]) => with_("problems", ...parts),
  mediaUrl: (id: string) => ["media-url", id],
  settings: (which?: "media" | "timing") => with_("settings", which),
  roles: () => ["roles"],
  permissions: () => ["permissions"],
  audit: (...parts: unknown[]) => with_("audit", ...parts),
  dashboards: (...parts: unknown[]) => with_("dashboards", ...parts),
  library: (query?: Query) => with_("library", query),
  libraryItem: (id?: Id) => with_("library-item", id),
  libraryHistory: (id?: Id) => with_("library-history", id),
  pushPreview: (item: Id, revision: Id) => ["push-preview", item, revision],
  integrations: () => ["integrations"],
  integration: (id?: Id) => with_("integration", id),
  deliveries: (...parts: unknown[]) => with_("deliveries", ...parts),
  catalogue: (...parts: unknown[]) => with_("catalogue", ...parts),
  apiKeys: () => ["api-keys"],
  pdfTemplates: () => ["pdf-templates"],
  pdfVersion: (id?: Id) => with_("pdf-version", id),
  pdfShared: (...parts: unknown[]) => with_("pdf-shared", ...parts),
  pdfPictures: () => ["pdf-pictures"],
  pdfSample: (type: Id) => ["pdf-sample", type],
};
