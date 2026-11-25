/** One input per field type, and the field wrapper (label, help, error) the renderer draws. */
import { MapPin } from "lucide-react";
import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchAll } from "../api/hooks";
import { ist } from "../lib/format";
import { useInspectionTypes, useListItems } from "../api/labels";
import type { FormField, Option, User } from "../api/types";
import { Field } from "./kit";
import { keys } from "../api/keys";
import type { RenderProps } from "./FormRenderer";
import { MediaField } from "./MediaField";

type InputArgs = {
  f: FormField;
  value: unknown;
  str: string | number;
  derived: unknown;
  readOnly: boolean;
  onChange: (v: unknown) => void;
  p: RenderProps;
  common: Record<string, unknown>;
};
const textInput = ({ common, str, onChange }: InputArgs) => (
  <input {...common} value={String(str)} onChange={(e) => onChange(e.target.value)} />
);
const stamp = (type: "date" | "time" | "datetime", input: (a: InputArgs) => ReactNode) => (a: InputArgs) =>
  a.f.config.auto === true ? (
    <AutoStamp
      type={type}
      value={a.value as string | undefined}
      label={a.f.label || a.f.key}
      disabled={a.readOnly}
      preview={a.p.preview}
      onChange={a.onChange}
    />
  ) : (
    input(a)
  );
const number = ({ f, common, str, onChange }: InputArgs) => (
  <input
    {...common}
    type="number"
    inputMode="decimal"
    value={String(str)}
    placeholder={f.type === "currency" ? "₹" : String(f.config.unit ?? "")}
    onChange={(e) => onChange(e.target.value === "" ? null : Number(e.target.value))}
  />
);
const media = ({ f, value, readOnly, onChange, p }: InputArgs) => (
  <MediaField f={f} value={value} readOnly={readOnly} onChange={onChange} p={p} />
);

/** The input for each field type (lib/fieldTypes TYPES has the rest of what a type is; "image" is
 *  a picture shown above, not an input). */
export const INPUTS: Record<string, (a: InputArgs) => ReactNode> = {
  short_text: textInput,
  long_text: ({ common, str, onChange }) => <textarea {...common} value={String(str)} onChange={(e) => onChange(e.target.value)} />,
  number,
  currency: number,
  phone: ({ common, str, onChange }) => <input {...common} type="tel" value={String(str)} onChange={(e) => onChange(e.target.value)} />,
  date: stamp("date", ({ common, str, onChange }) => (
    <input {...common} type="date" value={String(str)} onChange={(e) => onChange(e.target.value)} />
  )),
  time: stamp("time", ({ common, str, onChange }) => (
    <input {...common} type="time" value={String(str)} onChange={(e) => onChange(e.target.value)} />
  )),
  datetime: stamp("datetime", ({ common, str, onChange }) => (
    <input {...common} type="datetime-local" value={String(str).slice(0, 16)} onChange={(e) => onChange(e.target.value)} />
  )),
  yes_no: ({ f, value, readOnly, onChange }) => (
    <Choices
      name={f.key}
      disabled={readOnly}
      label={f.label}
      value={value === true ? "yes" : value === false ? "no" : ""}
      plain
      options={[
        { key: "yes", label: "Yes" },
        { key: "no", label: "No" },
      ]}
      onChange={(k) => onChange(k === "yes")}
    />
  ),
  single_choice: ({ f, value, str, readOnly, onChange, common }) => {
    const opts = (f.config.options as Option[]) ?? [];
    return f.config.display === "dropdown" || (f.config.display !== "buttons" && opts.length > 5) ? (
      <select {...common} value={String(str)} onChange={(e) => onChange(e.target.value || null)}>
        <option value="">Choose…</option>
        {opts.map((o) => (
          <option key={o.key} value={o.key}>
            {o.label}
          </option>
        ))}
      </select>
    ) : (
      <Choices
        name={f.key}
        disabled={readOnly}
        label={f.label}
        value={String(str)}
        options={opts}
        onChange={(k) => onChange(value === k ? null : k)}
      />
    );
  },
  multi_choice: ({ f, value, readOnly, onChange }) => {
    const opts = (f.config.options as Option[]) ?? [];
    const chosen = Array.isArray(value) ? (value as string[]) : [];
    return (
      <div role="group" aria-label={f.label}>
        {opts.map((o) => (
          <label className="check" key={o.key}>
            <input
              type="checkbox"
              disabled={readOnly}
              checked={chosen.includes(o.key)}
              onChange={(e) => onChange(e.target.checked ? [...chosen, o.key] : chosen.filter((x) => x !== o.key))}
            />{" "}
            {o.label}
          </label>
        ))}
      </div>
    );
  },
  form_choice: ({ f, str, readOnly, onChange }) => (
    <TypeSelect value={String(str)} disabled={readOnly} label={f.label} onChange={(v) => onChange(v || null)} />
  ),
  master_list: ({ f, str, readOnly, onChange }) => (
    <ListSelect
      list={String(f.config.list ?? "")}
      value={String(str)}
      disabled={readOnly}
      label={f.label}
      onChange={(v) => onChange(v || null)}
    />
  ),
  user_picker: ({ f, value, readOnly, onChange }) => (
    <UserSelect
      role={String(f.config.role ?? "expert")}
      value={value as number | null}
      disabled={readOnly}
      label={f.label}
      onChange={onChange}
    />
  ),
  gps: ({ f, value, readOnly, onChange, p }) => (
    <Gps
      value={value as { lat: number; lng: number } | undefined}
      disabled={readOnly}
      onChange={onChange}
      preview={p.preview}
      auto={f.config.auto !== false}
    />
  ),
  photo: media,
  video: media,
  file: media,
  signature: media,
  derived: ({ f, derived }) => (
    <p>
      <strong>{derived === true ? String(f.config.true_label ?? "Yes") : String(f.config.false_label ?? "No")}</strong>
    </p>
  ),
  rating: () => <p className="muted">Calculated from the defects found.</p>,
};

export function FieldInput({
  f,
  value,
  derived,
  required,
  error,
  readOnly,
  onChange,
  p,
}: {
  f: FormField;
  value: unknown;
  derived: unknown;
  required: boolean;
  error?: string;
  readOnly: boolean;
  onChange: (v: unknown) => void;
  p: RenderProps;
}) {
  const label = `${f.label || f.key}${required ? " *" : ""}`;
  const err = error === "required" ? "This is needed." : error;
  const uid = useId();
  const ids = { help: `${uid}-help`, error: `${uid}-err` };
  // the control says it is required, whether it is wrong, and which text explains it (F-179)
  const described = [f.helper_text && ids.help, err && ids.error].filter(Boolean).join(" ") || undefined;
  const common = {
    disabled: readOnly,
    "aria-label": f.label || f.key,
    "aria-required": required || undefined,
    "aria-invalid": err ? true : undefined,
    "aria-describedby": described,
  };
  const str = (value ?? "") as string | number;
  if (f.type === "image") {
    if (p.role !== "expert" && !p.preview) return null; // shown to the expert, not in Ops' views
    const asset = typeof f.config.asset === "string" ? f.config.asset : "";
    return (
      <div className="field">
        <span className="label-row">{f.label}</span>
        {asset ? (
          <img className="static-image" src={`/api/v1/form-assets/${asset}`} alt={f.label || "Picture"} />
        ) : (
          <p className="muted">No picture yet.</p>
        )}
        {f.helper_text && <span className="help">{f.helper_text}</span>}
      </div>
    );
  }
  const input = (INPUTS[f.type] ?? INPUTS.short_text!)({ f, value, str, derived, readOnly, onChange, p, common });
  return (
    <Field bare label={label} help={f.helper_text || undefined} error={err} ids={ids}>
      {input}
    </Field>
  );
}

/** Picked answers read at a glance: green when fine, red only for a defect; Yes / No stays neutral. */
function Choices({
  name,
  options,
  value,
  onChange,
  disabled,
  label,
  plain,
}: {
  name: string;
  options: { key: string; label: string; is_defect?: boolean }[];
  value: string;
  onChange: (k: string) => void;
  disabled: boolean;
  label: string;
  plain?: boolean;
}) {
  return (
    <div role="radiogroup" aria-label={label} style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
      {options.map((o) => (
        <button
          type="button"
          key={o.key}
          role="radio"
          aria-checked={value === o.key}
          disabled={disabled}
          name={name}
          className={`choice${plain ? " plain" : o.is_defect ? " defect" : ""}`}
          onClick={() => onChange(o.key)}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

function ListSelect({
  list,
  value,
  onChange,
  disabled,
  label,
}: {
  list: string;
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
  label: string;
}) {
  const q = useListItems(list);
  const items = (q.data ?? []).filter((i) => !i.archived || i.key === value);
  return (
    <select aria-label={label} disabled={disabled} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Choose…</option>
      {items.map((i) => (
        <option key={i.key} value={i.key}>
          {i.label}
        </option>
      ))}
    </select>
  );
}

function TypeSelect({
  value,
  onChange,
  disabled,
  label,
}: {
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
  label: string;
}) {
  const types = useInspectionTypes().filter((t) => t.available || t.key === value);
  return (
    <select aria-label={label} disabled={disabled} value={value} onChange={(e) => onChange(e.target.value)}>
      <option value="">Choose…</option>
      {types.map((t) => (
        <option key={t.key} value={t.key}>
          {t.label}
        </option>
      ))}
    </select>
  );
}

function UserSelect({
  role,
  value,
  onChange,
  disabled,
  label,
}: {
  role: string;
  value: number | null | undefined;
  onChange: (v: unknown) => void;
  disabled: boolean;
  label: string;
}) {
  const q = useQuery({
    queryKey: keys.users({ role }),
    retry: false,
    staleTime: 300_000,
    queryFn: ({ signal }) => fetchAll<User>("users", { role }, signal),
  });
  if (q.isError) return <input aria-label={label} disabled value={value ?? ""} readOnly />;
  return (
    <select
      aria-label={label}
      disabled={disabled}
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value ? Number(e.target.value) : null)}
    >
      <option value="">Choose…</option>
      {(q.data ?? [])
        .filter((u) => u.is_active)
        .map((u) => (
          <option key={u.id} value={u.id}>
            {u.name || u.username}
          </option>
        ))}
    </select>
  );
}

/** Browser location, taken by itself as soon as the field appears. If it is refused or not
 *  available the field just says so (and offers another try): it never blocks the job. */
const pad = (n: number) => String(n).padStart(2, "0");
/** "Now" in the shapes the server stores, in India time: 2026-11-23, 15:30, 2026-11-23T15:30:00+05:30. */
export function nowAs(type: string, d = new Date()): string {
  const at = ist(d);
  if (type === "date") return at.day;
  if (type === "time") return at.hhmm;
  return `${at.day}T${at.hhmm}:${pad(at.seconds)}+05:30`;
}

/** A date or time the Admin set to "automatic": stamped when the page opens, never typed. */
function AutoStamp({
  type,
  value,
  label,
  disabled,
  preview,
  onChange,
}: {
  type: string;
  value?: string;
  label: string;
  disabled: boolean;
  preview?: boolean;
  onChange: (v: unknown) => void;
}) {
  const done = useRef(false);
  useEffect(() => {
    if (done.current || value || disabled || preview) return;
    done.current = true;
    onChange(nowAs(type));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- stamps once when the page opens, never again
  const shown = value
    ? type === "datetime"
      ? new Date(value).toLocaleString("en-IN", { dateStyle: "medium", timeStyle: "short" })
      : value
    : preview
      ? "Stamped when the expert opens this page"
      : "…";
  return (
    <p className="auto-stamp" data-testid={`auto-${label}`}>
      {shown} <span className="muted small">(automatic)</span>
    </p>
  );
}

function Gps({
  value,
  onChange,
  disabled,
  preview,
  auto = true,
}: {
  value?: { lat: number; lng: number; accuracy?: number };
  onChange: (v: unknown) => void;
  disabled: boolean;
  preview?: boolean;
  auto?: boolean;
}) {
  const [state, setState] = useState<"idle" | "busy" | "unavailable">("idle");
  const asked = useRef(false);
  function capture() {
    if (!("geolocation" in navigator)) return setState("unavailable");
    setState("busy");
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        setState("idle");
        onChange({
          lat: +pos.coords.latitude.toFixed(6),
          lng: +pos.coords.longitude.toFixed(6),
          accuracy: Math.round(pos.coords.accuracy),
        });
      },
      () => setState("unavailable"),
      { enableHighAccuracy: true, timeout: 10_000 },
    );
  }
  useEffect(() => {
    if (asked.current || value || disabled || preview || !auto) return;
    asked.current = true;
    capture();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps -- asks for the location once when the page opens, never again
  return (
    <div aria-live="polite">
      {value ? (
        <p className="ok" data-testid="gps-value">
          <MapPin size={14} aria-hidden /> {value.lat}, {value.lng}
          {value.accuracy !== undefined && <span className="muted small"> (±{value.accuracy} m)</span>}
        </p>
      ) : state === "busy" ? (
        <p className="muted" role="status">
          Finding your location…
        </p>
      ) : state === "unavailable" ? (
        <p className="muted" role="status">
          GPS unavailable
        </p>
      ) : preview ? (
        <p className="muted small">
          {auto ? "Taken automatically when the expert opens this page." : "The expert taps a button to capture it."}
        </p>
      ) : null}
      {!disabled && !preview && !auto && !value && state === "idle" && (
        <button type="button" onClick={capture}>
          Capture my location
        </button>
      )}
      {!disabled && !preview && (value || state === "unavailable") && state !== "busy" && (
        <button type="button" className="link" onClick={capture}>
          {value ? "Update location" : "Try again"}
        </button>
      )}
    </div>
  );
}
