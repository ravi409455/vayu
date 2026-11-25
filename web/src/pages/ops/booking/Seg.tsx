

/** 1 to 5 (or words) as one row of buttons; the suggestion is marked; Auto clears an override. */
export function Seg<T extends string | number>({ label, value, suggested, options, onPick, disabled }: { label: string; value: T | null; suggested?: T; options: { v: T; label: string }[]; onPick: (v: T | null) => void; disabled: boolean }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      <button role="radio" aria-checked={value === null} disabled={disabled} onClick={() => onPick(null)}>Auto</button>
      {options.map((o) => <button key={String(o.v)} role="radio" aria-checked={value === o.v} disabled={disabled} onClick={() => onPick(o.v)} title={o.v === suggested ? "Suggested" : undefined}>{o.label}{o.v === suggested ? <span className="sugg" aria-label="suggested">•</span> : null}</button>)}
    </div>
  );
}
