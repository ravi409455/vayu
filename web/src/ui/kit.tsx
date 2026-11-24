import { cloneElement, createContext, isValidElement, useCallback, useContext, useId, useState, type InputHTMLAttributes, type ReactElement, type ReactNode } from "react";
import { Inbox } from "lucide-react";
import { explain } from "../api/client";
import { fmtStamp } from "../lib/format";
import { InfoTip } from "./InfoTip";

export function Modal({ title, children, onClose, actions, wide }: { title: string; children: ReactNode; onClose: () => void; actions?: ReactNode; wide?: boolean }) {
  return (
    <div className="modal-back" role="dialog" aria-modal="true" aria-label={title} onClick={onClose}>
      <div className={`modal${wide ? " wide" : ""}`} onClick={(e) => e.stopPropagation()}>
        <h2>{title}</h2>
        {children}
        <div className="actions">{actions ?? <button onClick={onClose}>Close</button>}</div>
      </div>
    </div>
  );
}

export function Confirm({ title, children, confirmLabel = "Confirm", danger, onConfirm, onCancel }: {
  title: string; children: ReactNode; confirmLabel?: string; danger?: boolean; onConfirm: () => void; onCancel: () => void;
}) {
  return (
    <Modal title={title} onClose={onCancel}
      actions={<><button onClick={onCancel}>Cancel</button>
        <button className={danger ? "danger" : "primary"} onClick={onConfirm}>{confirmLabel}</button></>}>
      {children}
    </Modal>
  );
}

type ToastCtx = { say: (msg: string, bad?: boolean) => void; fail: (e: unknown) => void };
const Toasts = createContext<ToastCtx>({ say: () => {}, fail: () => {} });
export const useToast = () => useContext(Toasts);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [t, setT] = useState<{ msg: string; bad: boolean } | null>(null);
  const say = useCallback((msg: string, bad = false) => {
    setT({ msg, bad });
    setTimeout(() => setT(null), 4000);
  }, []);
  const fail = useCallback((e: unknown) => say(explain(e), true), [say]);
  return (
    <Toasts.Provider value={{ say, fail }}>
      {children}
      {t && <div className={`toast${t.bad ? " bad" : ""}`} role="status">{t.msg}</div>}
    </Toasts.Provider>
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
    </div>);
}

/** A labelled input. The label points at the input by id (so the little "i" next to it is not
 *  mistaken for the control). `bare` skips the label element when the content has its own buttons. */
export function Field({ label, help, error, children, bare, tip }: { label: string; help?: string; error?: string; children: ReactNode; bare?: boolean; tip?: ReactNode }) {
  const auto = useId();
  const single = isValidElement<{ id?: string }>(children) && typeof children.type === "string";
  const id = single ? (children.props.id ?? auto) : undefined;
  const control = single && !bare ? cloneElement(children as ReactElement<{ id?: string }>, { id }) : children;
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
      {help && <span className="help">{help}</span>}
      {error && <span className="error" role="alert">{error}</span>}
    </div>
  );
}

export function Pill({ children, tone }: { children: ReactNode; tone?: "ok" | "warn" | "bad" | "info" }) {
  return <span className={`pill${tone ? " " + tone : ""}`}>{children}</span>;
}

export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string }[]; value: T; onChange: (t: T) => void }) {
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
export function NameDialog({ title, label, onOk, onCancel }: { title: string; label: string; onOk: (v: string) => void; onCancel: () => void }) {
  const [v, setV] = useState("");
  return (
    <Modal title={title} onClose={onCancel}
      actions={<><button onClick={onCancel}>Cancel</button><button className="primary" disabled={!v.trim()} onClick={() => onOk(v.trim())}>Add</button></>}>
      <Field label={label}><input autoFocus value={v} onChange={(e) => setV(e.target.value)} onKeyDown={(e) => e.key === "Enter" && v.trim() && onOk(v.trim())} /></Field>
    </Modal>
  );
}

/** Page title row, the same on every page: title (and a count) on the left, the page's buttons on the right,
 *  the main one last. A one-line explanation only where a first-time Admin needs it. */
export function PageHeader({ title, count, subtitle, children }: { title: ReactNode; count?: number; subtitle?: ReactNode; children?: ReactNode }) {
  return (
    <header className="page-head">
      <div className="grow">
        <h1>{title}{count !== undefined && <span className="count">{count}</span>}</h1>
        {subtitle && <p className="muted subtitle">{subtitle}</p>}
      </div>
      {children && <div className="page-actions">{children}</div>}
    </header>
  );
}

export { InfoTip };
