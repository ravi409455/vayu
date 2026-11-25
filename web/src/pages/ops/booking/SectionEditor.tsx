/** Edit one section in place: its inputs, Save and Cancel. */
export function SectionEditor({
  children,
  onSave,
  onCancel,
  saving,
  changed,
}: {
  children: React.ReactNode;
  onSave: () => void;
  onCancel: () => void;
  saving: boolean;
  changed: boolean;
}) {
  return (
    <>
      <div className="two-col">{children}</div>
      <div className="bar" style={{ marginTop: 8, marginBottom: 0 }}>
        <button className="primary" disabled={!changed || saving} onClick={onSave}>
          Save changes
        </button>
        <button onClick={onCancel}>Cancel</button>
      </div>
    </>
  );
}
