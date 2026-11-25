

/** A button that opens the file picker (a label around a hidden file input). */
export function FilePick({ className, busy, disabled, accept, multiple, label, title, onPick, children }: { className: string; busy: boolean; disabled?: boolean; accept: string; multiple?: boolean; label: string; title?: string; onPick: (files: File[]) => void; children: React.ReactNode }) {
  const off = busy || disabled;
  return (
    <label className={`${className}${off ? " disabled" : ""}`} title={title} aria-disabled={off || undefined}>
      {children}
      <input type="file" hidden disabled={off} accept={accept} multiple={multiple} aria-label={label}
        onChange={(e) => { const files = Array.from(e.target.files ?? []); e.target.value = ""; onPick(files); }} />
    </label>);
}
