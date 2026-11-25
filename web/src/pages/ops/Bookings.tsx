import { LayoutGrid, List, Plus } from "lucide-react";
import { Fragment, useEffect, useState } from "react";
import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, type Page } from "../../api/client";
import { useList, useRefresh } from "../../api/hooks";
import { STAGE_LABEL, STAGE_TONE, useInspectionTypes, useLabels, useListItems, useTypeLabels } from "../../api/labels";
import type { Booking, User } from "../../api/types";
import { useAuth } from "../../auth";
import { allowedActions } from "../../lib/actions";
import { useCount, viewQuery, type View } from "../../lib/bookingViews";
import { useDebounced } from "../../lib/useDebounced";
import { fmtSlot } from "../../lib/format";
import { loadJSON, saveJSON } from "../../lib/store";
import { fmtMinutes } from "../../lib/timing";
import { ExpertCell } from "../../ui/ExpertCell";
import { Confirm, Empty, LoadError, PageHeader, Pill, useToast } from "../../ui/kit";
import { MoreMenu } from "../../ui/Menu";
import { Actions } from "./booking/Actions";
import { keys } from "../../api/keys";

/** Admin may delete any booking; Ops only one that is still an untouched draft. */
export function canDelete(role: string, stage: string): boolean {
  return role === "admin" || stage === "draft";
}

export type Filters = {
  search: string;
  city: string;
  expert: string;
  type: string;
  stage: string;
  date_from: string;
  date_to: string;
  answer: string;
  value: string;
};
export const EMPTY: Filters = { search: "", city: "", expert: "", type: "", stage: "", date_from: "", date_to: "", answer: "", value: "" };
/** A field Bookings can be filtered by (server: bookings/answer-fields). */
export type AnswerField = { field: string; label: string; type: string; form: string; options: { value: string; label: string }[] };
export const NOT_FILLED = "__none__";

const VIEWS: { id: View; label: string; counted?: boolean; perm?: string }[] = [
  { id: "today", label: "Today", counted: true },
  { id: "unassigned", label: STAGE_LABEL.draft!, counted: true },
  { id: "in_progress", label: STAGE_LABEL.in_progress!, counted: true },
  { id: "uploading", label: STAGE_LABEL.submitted!, counted: true },
  { id: "upcoming", label: "Upcoming" },
  { id: "completed", label: STAGE_LABEL.completed! },
  { id: "late", label: "Started late", counted: true, perm: "bookings.review_timing" },
  { id: "quick", label: "Too quick", counted: true, perm: "bookings.review_timing" },
  { id: "all", label: "All" },
];
/** The red pills a row gets for a late start or a too-quick job ("Late 40 min", "Too quick 25 min"). */
export function timingPills(b: Booking): string[] {
  const t = b.timing;
  return t
    ? [...(t.late ? [`Late ${fmtMinutes(t.late_minutes)}`] : []), ...(t.quick ? [`Too quick ${fmtMinutes(t.duration_minutes)}`] : [])]
    : [];
}
const BOARD: string[] = ["draft", "assigned", "in_progress", "submitted", "completed"];

function ViewTab({ v, on, onPick, own }: { v: (typeof VIEWS)[number]; on: boolean; onPick: () => void; own: Record<string, string> }) {
  const n = useCount({ ...own, ...viewQuery(v.id) }); // the person's filters apply to the numbers too
  return (
    <button role="tab" aria-selected={on} className={on ? "on" : ""} onClick={onPick}>
      {v.label}
      {v.counted && n !== undefined && (
        <span className={`count-pill${(v.id === "unassigned" || v.id === "late" || v.id === "quick") && n > 0 ? " warn" : ""}`}>{n}</span>
      )}
    </button>
  );
}

/** Every booking: saved views as tabs, one row of filters (remembered per person), a list or a board. */
export function Bookings() {
  const { me, can } = useAuth();
  const nav = useNavigate();
  const { say, fail } = useToast();
  const refresh = useRefresh();
  const [sp, setSp] = useSearchParams();
  const view = (sp.get("view") as View | null) ?? (sp.get("search") ? "all" : "today");
  const key = `vayu:bookings:${me?.id}`;
  // Arriving from a number on Today (?all=1) shows exactly what that number counted: saved filters are set aside.
  const [f, setF] = useState<Filters>(() => ({
    ...EMPTY,
    ...(sp.get("all") ? EMPTY : loadJSON<Filters>(key, EMPTY)),
    search: sp.get("search") ?? "",
    ...Object.fromEntries((["stage", "date_from", "date_to"] as const).filter((k) => sp.get(k)).map((k) => [k, sp.get(k)!])),
  }));
  const [layout, setLayout] = useState<"list" | "board">(() => loadJSON(`${key}:layout`, "list"));
  const [page, setPage] = useState(1);
  const [acting, setActing] = useState<{ kind: "assign" | "reschedule" | "cancel"; b: Booking } | null>(null);
  const [deleting, setDeleting] = useState<Booking | null>(null);
  useEffect(() => saveJSON(key, { ...f, search: "" }), [key, f]);
  useEffect(() => saveJSON(`${key}:layout`, layout), [key, layout]);
  const urlSearch = sp.get("search");
  useEffect(() => {
    if (urlSearch !== null) {
      setF((x) => ({ ...x, search: urlSearch }));
      setPage(1);
    }
  }, [urlSearch]);
  const set = (p: Partial<Filters>) => {
    setF({ ...f, ...p });
    setPage(1);
  };
  const pick = (v: View) => {
    setSp(v === "today" ? {} : { view: v });
    setPage(1);
  };
  // an answer filter counts only once its value is chosen too
  // typing in the filter asks the server once it pauses, not on every key (F-085)
  const search = useDebounced(f.search, 250);
  const own = Object.fromEntries(
    Object.entries({ ...f, search }).filter(
      ([k, v]) => v !== "" && !((k === "answer" || k === "value") && !(f.type && f.answer && f.value)),
    ),
  );
  const query = { ...own, ...viewQuery(view), page };
  // a new filter keeps the rows on screen until its answer arrives (no flash, an open menu stays put)
  const q = useQuery({
    queryKey: keys.bookings("page", query),
    queryFn: ({ signal }) => api<Page<Booking>>("bookings", { query, signal }),
    placeholderData: keepPreviousData,
  });
  const experts = useList<User>(keys.users(), "users", { role: "expert" });
  const cities = useListItems("city");
  const types = useInspectionTypes();
  // an answer is picked once a type is: only that type's questions (plus check-in and wrap-up)
  const answerFields = useQuery({
    queryKey: keys.answerFields(f.type),
    enabled: can("submissions.view") && !!f.type,
    queryFn: ({ signal }) => api<AnswerField[]>("bookings/answer-fields", { query: { type: f.type }, signal }),
  });
  const picked = f.type ? (answerFields.data ?? []).find((a) => a.field === f.answer) : undefined;
  const car = useLabels("car_make_model");
  const city = useLabels("city");
  const type = useTypeLabels();
  const remove = useMutation({
    mutationFn: (b: Booking) => api(`bookings/${b.id}`, { method: "DELETE" }),
    onSuccess: () => {
      setDeleting(null);
      say("Booking deleted.");
      void refresh(keys.bookings());
    },
    onError: (e) => {
      setDeleting(null);
      fail(e);
    },
  });
  const rows = q.data?.results ?? [];
  // the server's page size: a full page has more after it; the last page follows full ones (F-036)
  const size = !q.data ? 0 : q.data.next || page === 1 ? rows.length : Math.round((q.data.count - rows.length) / (page - 1));
  const filtered = Object.keys(own).some((k) => k !== "search");
  const menu = (b: Booking) => {
    const allowed = allowedActions(b, can);
    return [
      { label: "Open booking", onClick: () => nav(`/booking/${b.id}`) },
      {
        label: b.assigned_expert ? "Reassign expert" : "Assign expert",
        onClick: () => setActing({ kind: "assign", b }),
        hidden: !allowed.has("assign"),
      },
      { label: "Reschedule", onClick: () => setActing({ kind: "reschedule", b }), hidden: !allowed.has("reschedule") },
      { label: "Cancel booking…", danger: true, onClick: () => setActing({ kind: "cancel", b }), hidden: !allowed.has("cancel") },
      {
        label: "Delete…",
        danger: true,
        onClick: () => setDeleting(b),
        hidden: !(can("bookings.delete") && canDelete(me?.role ?? "", b.stage)),
      },
    ];
  };
  const assignBtn = (b: Booking) =>
    can("bookings.assign") && b.stage === "draft" ? (
      <button
        className="sm assign-btn"
        onClick={(e) => {
          e.stopPropagation();
          setActing({ kind: "assign", b });
        }}
      >
        Assign expert
      </button>
    ) : (
      <ExpertCell id={b.assigned_expert} experts={experts.data ?? []} />
    );
  return (
    <>
      <PageHeader title="Bookings" count={q.data?.count}>
        <div className="seg" role="group" aria-label="Layout">
          <button aria-pressed={layout === "list"} onClick={() => setLayout("list")}>
            <List size={14} aria-hidden /> List
          </button>
          <button aria-pressed={layout === "board"} onClick={() => setLayout("board")}>
            <LayoutGrid size={14} aria-hidden /> Board
          </button>
        </div>
        {can("bookings.create") && (
          <button className="primary" onClick={() => nav("/booking/new")}>
            <Plus size={15} aria-hidden /> New booking
          </button>
        )}
      </PageHeader>
      <div className="tabs" role="tablist" aria-label="Views">
        {VIEWS.filter((v) => !v.perm || can(v.perm)).map((v) => (
          <ViewTab key={v.id} v={v} on={view === v.id} onPick={() => pick(v.id)} own={own} />
        ))}
      </div>
      <div className="filters">
        <input
          aria-label="Filter bookings"
          className="filter-search"
          placeholder="Filter: booking ID, customer, phone, chassis"
          value={f.search}
          onChange={(e) => {
            set({ search: e.target.value });
            if (e.target.value && view !== "all") setSp({ view: "all" });
          }}
        />
        <select aria-label="City" className={f.city ? "set" : ""} value={f.city} onChange={(e) => set({ city: e.target.value })}>
          <option value="">City</option>
          {(cities.data ?? []).map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
        <select
          aria-label="Type"
          className={f.type ? "set" : ""}
          value={f.type}
          onChange={(e) => set({ type: e.target.value, answer: "", value: "" })}
        >
          <option value="">Type</option>
          {types.map((c) => (
            <option key={c.key} value={c.key}>
              {c.label}
            </option>
          ))}
        </select>
        <select aria-label="Expert" className={f.expert ? "set" : ""} value={f.expert} onChange={(e) => set({ expert: e.target.value })}>
          <option value="">Expert</option>
          {(experts.data ?? []).map((u) => (
            <option key={u.id} value={u.id}>
              {u.name || u.username}
            </option>
          ))}
        </select>
        {view === "all" && (
          <select aria-label="Stage" className={f.stage ? "set" : ""} value={f.stage} onChange={(e) => set({ stage: e.target.value })}>
            <option value="">Stage</option>
            {Object.entries(STAGE_LABEL).map(([k, l]) => (
              <option key={k} value={k}>
                {l}
              </option>
            ))}
          </select>
        )}
        {(view === "all" || view === "completed" || view === "late" || view === "quick") && (
          <label className="date-range">
            <span>From</span>
            <input aria-label="From" type="date" value={f.date_from} onChange={(e) => set({ date_from: e.target.value })} />
            <span>to</span>
            <input aria-label="To" type="date" value={f.date_to} onChange={(e) => set({ date_to: e.target.value })} />
          </label>
        )}
        {f.type && (answerFields.data ?? []).length > 0 && (
          <select
            aria-label="Answer"
            className={f.answer ? "set" : ""}
            value={f.answer}
            onChange={(e) => set({ answer: e.target.value, value: "" })}
          >
            <option value="">Answer</option>
            {(answerFields.data ?? []).map((a) => (
              <option key={a.field} value={a.field}>
                {a.label}
              </option>
            ))}
          </select>
        )}
        {picked && (
          <select
            aria-label="Answer value"
            className={f.value ? "set" : ""}
            value={f.value}
            onChange={(e) => set({ value: e.target.value })}
          >
            <option value="">Any answer</option>
            {picked.options.map((o) => (
              <option key={o.value} value={o.value}>
                {o.label}
              </option>
            ))}
            <option value={NOT_FILLED}>Not filled</option>
          </select>
        )}
        {filtered && (
          <button className="link" onClick={() => setF({ ...EMPTY, search: f.search })}>
            Clear filters
          </button>
        )}
      </div>
      {layout === "list" ? (
        <div className="table-card">
          <table className="rows">
            <thead>
              <tr>
                <th>Booking</th>
                <th>Car</th>
                <th>When</th>
                <th className="opt">Where</th>
                <th>Expert</th>
                <th>Status</th>
                <th>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((b) => (
                <tr key={b.id} className="click" onClick={() => nav(`/booking/${b.id}`)}>
                  <td>
                    <Link to={`/booking/${b.id}`} className="cell-main" onClick={(e) => e.stopPropagation()}>
                      {b.booking_id}
                    </Link>
                    <div className="cell-sub">{String(b.answers.customer_name ?? "")}</div>
                  </td>
                  <td>
                    <div>{car(b.answers.car_make_model)}</div>
                    <div className="cell-sub">{type(b.inspection_type)}</div>
                  </td>
                  <td className="nowrap">{fmtSlot(b.answers.inspection_date, b.answers.inspection_time) || "—"}</td>
                  <td className="opt">{city(b.answers.city)}</td>
                  <td>{assignBtn(b)}</td>
                  <td>
                    <Pill tone={STAGE_TONE[b.stage]}>{STAGE_LABEL[b.stage] ?? b.stage}</Pill>
                    {b.conflict && (
                      <>
                        {" "}
                        <Pill tone="bad">Conflict</Pill>
                      </>
                    )}
                    {timingPills(b).map((t) => (
                      <Fragment key={t}>
                        {" "}
                        <Pill tone="warn">{t}</Pill>
                      </Fragment>
                    ))}
                  </td>
                  <td style={{ textAlign: "right" }}>
                    <MoreMenu label={`Actions for ${b.booking_id}`} items={menu(b)} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {q.isError && <LoadError error={q.error} what="bookings" onRetry={q.refetch} />}
          {q.data && rows.length === 0 && (
            <Empty title="No bookings here">
              {filtered || f.search
                ? "Nothing matches these filters."
                : view === "today"
                  ? "Nothing is booked for today."
                  : "Nothing in this view right now."}
            </Empty>
          )}
          {q.data && (q.data.next || q.data.previous) && (
            <div className="table-foot">
              <span className="muted grow">
                {(page - 1) * size + 1}–{(page - 1) * size + rows.length} of {q.data.count}
              </span>
              <button className="sm" disabled={!q.data.previous} onClick={() => setPage(page - 1)}>
                Previous
              </button>
              <button className="sm" disabled={!q.data.next} onClick={() => setPage(page + 1)}>
                Next
              </button>
            </div>
          )}
        </div>
      ) : (
        <div className="board">
          {BOARD.filter((s) => view === "all" || view === "today" || view === "upcoming" || rows.some((b) => b.stage === s)).map((s) => {
            const col = rows.filter((b) => b.stage === s);
            return (
              <section key={s} className="board-col" aria-label={STAGE_LABEL[s]}>
                <h3>
                  <Pill tone={STAGE_TONE[s]}>{STAGE_LABEL[s]}</Pill> <span className="muted small">{col.length}</span>
                </h3>
                {col.map((b) => (
                  // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions -- a bigger mouse target; the booking link inside is the keyboard path
                  <div key={b.id} className="board-card" onClick={() => nav(`/booking/${b.id}`)}>
                    <div className="bar" style={{ margin: 0 }}>
                      <Link to={`/booking/${b.id}`} className="cell-main grow" onClick={(e) => e.stopPropagation()}>
                        {b.booking_id}
                      </Link>
                      <MoreMenu label={`Actions for ${b.booking_id}`} items={menu(b)} />
                    </div>
                    <div className="small">{String(b.answers.customer_name ?? "")}</div>
                    <div className="cell-sub">
                      {car(b.answers.car_make_model)} · {fmtSlot(b.answers.inspection_date, b.answers.inspection_time)}
                    </div>
                    <div style={{ marginTop: 6 }}>{assignBtn(b)}</div>
                  </div>
                ))}
                {col.length === 0 && <p className="muted small">None</p>}
              </section>
            );
          })}
        </div>
      )}
      {acting && (
        <Actions
          kind={acting.kind}
          booking={acting.b}
          experts={experts.data ?? []}
          onClose={() => setActing(null)}
          fail={fail}
          onDone={() => {
            setActing(null);
            say("Done.");
            void refresh(keys.bookings());
          }}
        />
      )}
      {deleting && (
        <Confirm
          title={`Delete ${deleting.booking_id}?`}
          danger
          confirmLabel="Delete booking"
          busy={remove.isPending}
          onCancel={() => setDeleting(null)}
          onConfirm={() => remove.mutate(deleting)}
        >
          <p>
            The booking{deleting.stage === "draft" ? "" : " and everything recorded on it"} is removed for good. This cannot be undone and
            is written to the audit log.
          </p>
          {me?.role !== "admin" && (
            <p className="muted small">
              Ops can only delete a draft that nobody has worked on. To stop a booking that is under way, cancel it instead.
            </p>
          )}
        </Confirm>
      )}
    </>
  );
}
