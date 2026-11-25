import {
  cloneElement,
  createContext,
  isValidElement,
  useCallback,
  useContext,
  useEffect,
  useId,
  useRef,
  useState,
  type InputHTMLAttributes,
  type KeyboardEvent,
  type ReactElement,
  type ReactNode,
} from "react";
import { Inbox, X } from "lucide-react";
import { ApiError, explain } from "../api/client";
import { fmtStamp } from "../lib/format";
import { InfoTip } from "./InfoTip";

/** Props that make a non-button element act like one: a click, or Enter / Space while it has focus. */
export const pressable = (fn: () => void) => ({
  role: "button" as const,
  tabIndex: 0,
  onClick: fn,
  onKeyDown: (e: KeyboardEvent) => {
    if (e.target === e.currentTarget && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      fn();
    }
  },
});

/** A native modal dialog: focus moves in and stays in (the page behind is inert), Escape closes it,
 *  and focus goes back to what opened it. A click beside it closes it only when nothing can be typed. */
export function Modal({
  title,
  children,
  onClose,
  actions,
  wide,
}: {
  title: string;
  children: ReactNode;
  onClose: () => void;
  actions?: ReactNode;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const head = useId();
  const close = useRef(onClose);
  close.current = onClose;
  useEffect(() => {
    const d = ref.current!;
    const back = document.activeElement as HTMLElement | null;
    if (!d.open) d.showModal();
    if (!d.contains(document.activeElement))
      (d.querySelector<HTMLElement>("[autofocus], input:not([type=hidden]):not([disabled]), select, textarea") ?? d).focus();
    return () => {
      if (d.open) d.close();
      back?.focus?.();
    };
  }, []);
  return (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-noninteractive-element-interactions -- a click on the backdrop; keyboards close it with Escape
    <dialog
      ref={ref}
      className="modal-dlg"
      aria-labelledby={head}
      tabIndex={-1}
      onCancel={(e) => {
        e.preventDefault();
        close.current();
      }}
      onClick={(e) => {
        if (e.target === ref.current && !ref.current.querySelector("input, select, textarea, [contenteditable]")) close.current();
      }}
    >
      <div className={`modal${wide ? " wide" : ""}`}>
        <h2 id={head}>{title}</h2>
        {children}
        <div className="actions">{actions ?? <button onClick={onClose}>Close</button>}</div>
      </div>
    </dialog>
  );
}

/** Asks before doing something. The button stays disabled while the action runs (`busy`, or the
 *  promise `onConfirm` returns), so a double click sends it once. */
export function Confirm({
  title,
  children,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger,
  onConfirm,
  onCancel,
  busy,
}: {
  title: string;
  children: ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
  onConfirm: () => void | Promise<unknown>;
  onCancel: () => void;
  busy?: boolean;
}) {
  const [running, setRunning] = useState(false);
  const go = () => {
    if (running || busy) return;
    const r = onConfirm();
    if (r instanceof Promise) {
      setRunning(true);
      void r.finally(() => setRunning(false));
    }
  };
  return (
    <Modal
      title={title}
      onClose={onCancel}
      actions={
        <>
          <button onClick={onCancel}>{cancelLabel}</button>
          <button className={danger ? "danger" : "primary"} disabled={running || busy} onClick={go}>
            {confirmLabel}
          </button>
        </>
      }
    >
      {children}
    </Modal>
  );
}

type ToastCtx = { say: (msg: string, bad?: boolean) => void; fail: (e: unknown) => void };
const Toasts = createContext<ToastCtx>({ say: () => {}, fail: () => {} });
export const useToast = () => useContext(Toasts);
/** Good news fades after 4 s; an error stays (and is announced at once) until it is closed. */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<{ msg: string; bad: boolean } | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout>>();
  const say = useCallback((msg: string, bad = false) => {
    clearTimeout(timer.current); // a new toast gets its own time
    setT({ msg, bad });
    if (!bad) timer.current = setTimeout(() => setT(null), 4000);
  }, []);
  const fail = useCallback((e: unknown) => say(explain(e), true), [say]);
  return (
    <Toasts.Provider value={{ say, fail }}>
      {children}
      {t && <Toast key={t.msg + t.bad} msg={t.msg} bad={t.bad} onClose={() => setT(null)} />}
    </Toasts.Provider>
  );
}

/** In the browser's top layer (a popover), so it shows above an open dialog too. */
function Toast({ msg, bad, onClose }: { msg: string; bad: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const el = ref.current as (HTMLDivElement & { showPopover?: () => void }) | null;
    if (!el?.showPopover) return; // no popover support: shown in place
    el.setAttribute("popover", "manual");
    try {
      el.showPopover();
    } catch {
      /* already shown */
    }
  }, []);
  return bad ? (
    <div ref={ref} className="toast bad" role="alert">
      {msg}
      <button className="icon-btn toast-x" aria-label="Close" onClick={onClose}>
        <X size={16} aria-hidden />
      </button>
    </div>
  ) : (
    <div ref={ref} className="toast" role="status">
      {msg}
    </div>
  );
}

/** A checkbox with a short name; the details go in the little "i", kept outside the label so a
 *  click on it does not tick the box. */
export function Check({ label, tip, ...input }: { label: string; tip?: ReactNode } & InputHTMLAttributes<HTMLInputElement>) {
  const id = useId();
  return (
    <div className="check-row">
      <input id={id} type="checkbox" {...input} />
      <label htmlFor={id}>{label}</label>
      {tip && <InfoTip label={`About ${label}`}>{tip}</InfoTip>}
    </div>
  );
}

/** A labelled input. The label points at the input by id (so the little "i" next to it is not
 *  mistaken for the control). `bare` skips the label element when the content has its own buttons. */
export function Field({
  label,
  help,
  error,
  children,
  bare,
  tip,
  ids,
}: {
  label: string;
  help?: string;
  error?: string;
  children: ReactNode;
  bare?: boolean;
  tip?: ReactNode;
  ids?: { help: string; error: string };
}) {
  const auto = useId();
  const single = isValidElement<{ id?: string }>(children) && typeof children.type === "string";
  const id = single ? (children.props.id ?? auto) : undefined;
  const helpId = ids?.help ?? `${auto}-help`,
    errorId = ids?.error ?? `${auto}-err`;
  // the control says which text explains it and whether it is wrong (`ids`: the control is built elsewhere)
  const described = [help && helpId, error && errorId].filter(Boolean).join(" ") || undefined;
  const control =
    single && !bare
      ? cloneElement(children as ReactElement<Record<string, unknown>>, {
          id,
          "aria-describedby": described,
          "aria-invalid": error ? true : undefined,
        })
      : children;
  const head = (
    <span className="label-row">
      {bare || !id ? <span>{label}</span> : <label htmlFor={id}>{label}</label>}
      {tip && <InfoTip>{tip}</InfoTip>}
    </span>
  );
  return (
    <div className="field">
      {head}
      {control}
      {help && (
        <span className="help" id={helpId}>
          {help}
        </span>
      )}
      {error && (
        <span className="error" role="alert" id={errorId}>
          {error}
        </span>
      )}
    </div>
  );
}

export function Pill({ children, tone }: { children: ReactNode; tone?: "ok" | "warn" | "bad" | "info" }) {
  return <span className={`pill${tone ? " " + tone : ""}`}>{children}</span>;
}

export function Tabs<T extends string>({
  tabs,
  value,
  onChange,
}: {
  tabs: { id: T; label: string }[];
  value: T;
  onChange: (t: T) => void;
}) {
  return (
    <div className="tabs" role="tablist">
      {tabs.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} className={value === t.id ? "on" : ""} onClick={() => onChange(t.id)}>
          {t.label}
        </button>
      ))}
    </div>
  );
}

/** A timestamp as people say it: "Today, 3:30 pm", "Tue 24 Nov, 10:30 am". */
export function when(iso?: string | null): string {
  return iso ? fmtStamp(iso) : "";
}

/** A list or page that could not be loaded: never shown as empty. A 404 says "not found". */
export function LoadError({ error, what, onRetry }: { error: unknown; what: string; onRetry?: () => unknown }) {
  const missing = error instanceof ApiError && error.status === 404;
  return (
    <div className="empty-state load-error" role="alert">
      <strong>{missing ? `This ${what} could not be found.` : `Could not load ${what}.`}</strong>
      <span>{missing ? "The link may be wrong, or it was deleted." : explain(error)}</span>
      {!missing && onRetry && <button onClick={() => void onRetry()}>Try again</button>}
    </div>
  );
}

/** One empty-state pattern: what is (not) here, and the next step when there is one. */
export function Empty({ children, title, action }: { children?: ReactNode; title?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty-state" role="status">
      <Inbox size={28} aria-hidden />
      {title && <strong>{title}</strong>}
      {children && <span>{children}</span>}
      {action}
    </div>
  );
}

/** Asks for one short text (a page or section name) in a proper dialog. */
export function NameDialog({
  title,
  label,
  onOk,
  onCancel,
}: {
  title: string;
  label: string;
  onOk: (v: string) => void;
  onCancel: () => void;
}) {
  const [v, setV] = useState("");
  return (
    <Modal
      title={title}
      onClose={onCancel}
      actions={
        <>
          <button onClick={onCancel}>Cancel</button>
          <button className="primary" disabled={!v.trim()} onClick={() => onOk(v.trim())}>
            Add
          </button>
        </>
      }
    >
      <Field label={label}>
        <input
          autoFocus
          value={v}
          onChange={(e) => setV(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && v.trim() && onOk(v.trim())}
        />
      </Field>
    </Modal>
  );
}

/** Page title row, the same on every page: title (and a count) on the left, the page's buttons on the right,
 *  the main one last. A one-line explanation only where a first-time Admin needs it. */
export function PageHeader({
  title,
  count,
  subtitle,
  children,
}: {
  title: ReactNode;
  count?: number;
  subtitle?: ReactNode;
  children?: ReactNode;
}) {
  usePageTitle(typeof title === "string" ? title : undefined);
  return (
    <header className="page-head">
      <div className="grow">
        <h1>
          {title}
          {count !== undefined && <span className="count">{count}</span>}
        </h1>
        {subtitle && <p className="muted subtitle">{subtitle}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}

export { InfoTip };

/** The browser tab says which page this is (R-24). */
export function usePageTitle(title?: string, app = "Vayu"): void {
  useEffect(() => {
    if (!title) return;
    const before = document.title;
    document.title = `${title} · ${app}`;
    return () => {
      document.title = before;
    };
  }, [title, app]);
}
