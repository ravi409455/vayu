import { useEffect, useState } from "react";
import { api, ApiError, explain } from "../../../api/client";
import type { Booking, FormPage, FormSection, FormVersion } from "../../../api/types";
import { useAuth } from "../../../auth";
import type { Answers } from "../../../lib/formSpec";
import { saveDirty } from "../../../lib/saveDirty";
import { AnswerSheet } from "../../../ui/AnswerSheet";
import { FormRenderer } from "../../../ui/FormRenderer";
import { type Stale, StaleDialog } from "../../../ui/StaleDialog";
import { useToast } from "../../../ui/kit";
import { SectionEditor } from "./SectionEditor";
import { onlySection } from "./parts";

export function BookingTab({ booking, tree, onSaved }: { booking: Booking; tree: FormVersion; onSaved: () => void }) {
  const { can } = useAuth();
  const { say, fail } = useToast();
  const [values, setValues] = useState<Answers>(booking.answers);
  const [dirty, setDirty] = useState<Answers>({});
  const [stale, setStale] = useState<Stale | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});
  const [editing, setEditing] = useState<{ page: FormPage; section: FormSection } | null>(null);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setValues({ ...booking.answers, ...dirty });
  }, [booking.row_version]); // eslint-disable-line react-hooks/exhaustive-deps -- takes the server's answers only for a new row version; unsaved edits stay on top
  const change = (k: string, v: unknown) => {
    setValues({ ...values, [k]: v });
    setDirty({ ...dirty, [k]: v });
    setErrors({ ...errors, [k]: "" });
  };
  const cancel = () => {
    setDirty({});
    setErrors({});
    setValues(booking.answers);
    setEditing(null);
  };
  async function save(rowVersion = booking.row_version) {
    setSaving(true);
    try {
      const r = await saveDirty(
        (rv, ch) => api(`bookings/${booking.id}`, { method: "PATCH", body: { row_version: rv, answers: ch } }),
        rowVersion,
        dirty,
      );
      if (!r.ok) return setStale(r.stale);
      setDirty({});
      setStale(null);
      setEditing(null);
      say("Saved.");
      onSaved();
    } catch (e) {
      if (e instanceof ApiError && e.body.errors) setErrors(e.body.errors as Record<string, string>);
      else if (e instanceof ApiError && e.code === "FIELD_ACCESS")
        setErrors(Object.fromEntries(((e.body.keys as string[]) ?? []).map((k) => [k, "You cannot change this now."])));
      else if (e instanceof ApiError && e.code === "DUPLICATE_BOOKING_ID") setErrors({ booking_id: explain(e) });
      else fail(e);
    } finally {
      setSaving(false);
    }
  }
  const editor = editing && (
    <SectionEditor changed={Object.keys(dirty).length > 0} saving={saving} onSave={() => save()} onCancel={cancel}>
      <FormRenderer
        kind="booking"
        tree={tree}
        pages={onlySection(editing.page, editing.section)}
        values={values}
        errors={errors}
        readOnlyKeys={["assigned_expert", "inspection_type"]}
        onChange={change}
      />
    </SectionEditor>
  );
  return (
    <>
      <AnswerSheet
        part={{ kind: "booking", tree, values }}
        onEdit={
          can("bookings.edit")
            ? (page, section) => {
                cancel();
                setEditing({ page, section });
              }
            : undefined
        }
        editing={editing ? { sectionId: editing.section.id, node: editor } : null}
      />
      {stale && (
        <StaleDialog
          info={stale}
          mine={Object.keys(dirty)}
          onRetry={() => save(stale.rowVersion)}
          onReload={() => {
            setDirty({});
            setStale(null);
            onSaved();
          }}
        />
      )}
    </>
  );
}
