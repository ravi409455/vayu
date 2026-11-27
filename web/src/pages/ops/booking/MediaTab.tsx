import { useQuery } from "@tanstack/react-query";
import { Download } from "lucide-react";
import { useMemo, useState } from "react";
import { api } from "../../../api/client";
import { keys } from "../../../api/keys";
import type { Booking, Inspection } from "../../../api/types";
import { useAuth } from "../../../auth";
import { Thumb } from "../../../ui/MediaThumb";
import { MoreMenu } from "../../../ui/Menu";
import { Empty, useToast } from "../../../ui/kit";
import { AnswerNear } from "./AnswerNear";
import { OpsFileActions } from "./OpsFileActions";
import { PreviewMedia } from "./PreviewMedia";
import { defectFor, idsOf, mediaFields, type Trees } from "./parts";

const TYPE_GROUPS = [
  ["photo", "Photos"],
  ["video", "Videos"],
  ["file", "Documents"],
  ["signature", "Signatures"],
] as const;

export function MediaTab({
  booking,
  insp,
  trees,
  onChanged,
}: {
  booking: Booking;
  insp?: Inspection;
  trees: Trees;
  onChanged: () => void;
}) {
  const { can } = useAuth();
  const { fail } = useToast();
  const [zip, setZip] = useState<string>("");
  const [view, setView] = useState<"section" | "type">(() => {
    try {
      return localStorage.getItem("vayu:media-view") === "type" ? "type" : "section";
    } catch {
      return "section";
    }
  });
  const pickView = (v: "section" | "type") => {
    setView(v);
    try {
      localStorage.setItem("vayu:media-view", v);
    } catch {
      /* private window: not remembered */
    }
  };
  const [showEmpty, setShowEmpty] = useState(false);
  const [sel, setSel] = useState<string | null>(null);
  const fields = useMemo(() => mediaFields(trees), [trees]);
  const onServer = useQuery({
    queryKey: keys.bookingPart(booking.id, "media"),
    enabled: can("media.manage"),
    queryFn: ({ signal }) =>
      api<{ id: string; by_ops: boolean; hidden_from_customer?: boolean }[]>(`bookings/${booking.id}/media`, { signal }),
  });
  const byOps = new Set((onServer.data ?? []).filter((m) => m.by_ops).map((m) => m.id));
  const internal = new Set((onServer.data ?? []).filter((m) => m.hidden_from_customer).map((m) => m.id));
  // Ops add or replace photos and videos once the expert has submitted; nobody deletes
  if (!insp) return <Empty title="No inspection yet">Photos and videos show here once the expert starts uploading.</Empty>;
  const all = fields.flatMap((f) => idsOf(insp, f.part, f.key).map((id) => ({ id, f })));
  const empty = fields.filter((f) => idsOf(insp, f.part, f.key).length === 0);
  // by section (form order) or by type (photos, videos, documents, signatures)
  const groups = (
    view === "type"
      ? TYPE_GROUPS.map(([type, title]) => ({ title, items: all.filter((x) => x.f.type === type) }))
      : [...new Set(fields.map((f) => f.section))].map((title) => ({ title, items: all.filter((x) => x.f.section === title) }))
  ).filter((g) => g.items.length > 0);
  const items = groups.flatMap((g) => g.items); // ‹ › follow what is on screen
  const current = items.find((x) => x.id === sel) ?? items[0];
  const at = current ? items.indexOf(current) : -1;
  const refreshed = () => {
    void onServer.refetch();
    onChanged();
  };
  async function makeZip(k: "image" | "video") {
    try {
      const r = await api<{ url: string }>(`bookings/${booking.id}/media-zip`, { body: { kind: k } });
      setZip(`/zip/${r.url.split("/zips/")[1]}`);
    } catch (e) {
      fail(e);
    }
  }
  return (
    <>
      <div className="bar">
        <div className="seg" role="group" aria-label="Group files">
          {(
            [
              ["section", "By section"],
              ["type", "By type"],
            ] as const
          ).map(([k, l]) => (
            <button key={k} aria-pressed={view === k} onClick={() => pickView(k)}>
              {l}
            </button>
          ))}
        </div>
        <span className="muted small">
          {all.length} {all.length === 1 ? "file" : "files"}
        </span>
        <label className="check small">
          <input type="checkbox" checked={showEmpty} onChange={(e) => setShowEmpty(e.target.checked)} /> Show empty fields ({empty.length})
        </label>
        <span className="grow" />
        {can("media.download") && (
          <MoreMenu
            label="Download"
            items={[
              { label: "All images (ZIP)", onClick: () => void makeZip("image") },
              { label: "All videos (ZIP)", onClick: () => void makeZip("video") },
            ]}
          >
            <Download size={16} aria-hidden /> ZIP
          </MoreMenu>
        )}
        {zip && (
          <a href={zip} target="_blank" rel="noreferrer">
            Open the ZIP page
          </a>
        )}
      </div>
      {items.length === 0 && !showEmpty && (
        <Empty title="No photos or videos yet">
          {fields.length ? "Files show here as the expert uploads them." : "This form has no photo or video fields."}
        </Empty>
      )}
      <div className="gallery-wrap">
        <div className="gallery">
          {groups.map((g) => (
            <section key={g.title} aria-label={g.title}>
              <h3 className="gallery-h">
                {g.title} <span className="muted small">{g.items.length}</span>
              </h3>
              <div className="tile-grid">
                {g.items.map((x) => {
                  const sev = defectFor(insp, trees, x.f);
                  return (
                    <button
                      key={x.id}
                      className={`tile-btn${current?.id === x.id ? " on" : ""}`}
                      data-testid="gallery-item"
                      onClick={() => setSel(x.id)}
                      aria-label={`${x.f.label}${sev ? `, ${sev}` : ""}`}
                    >
                      <Thumb id={x.id} video={x.f.type === "video"} />
                      {sev && <span className="pill bad tile-tag">{sev}</span>}
                      {byOps.has(x.id) && <span className="pill tile-tag ops-tag">Added by Ops</span>}
                      {internal.has(x.id) && <span className="pill tile-tag hidden-tag">Hidden from customer</span>}
                      <span className="tile-label ellipsis" title={`${x.f.section} › ${x.f.label}`}>
                        {view === "type" ? `${x.f.section} › ${x.f.label}` : x.f.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </section>
          ))}
          {showEmpty && empty.length > 0 && (
            <section aria-label="Empty fields">
              <h3 className="gallery-h">
                Empty fields <span className="muted small">{empty.length}</span>
              </h3>
              <div className="empty-list">
                {empty.map((f) => (
                  <div key={`${f.part}.${f.key}`} className="empty-row">
                    <span className="grow">
                      {f.section} › {f.label}
                    </span>
                    <OpsFileActions booking={booking} f={f} count={0} onDone={refreshed} />
                  </div>
                ))}
              </div>
            </section>
          )}
        </div>
        {current && (
          <aside className="card preview-pane" aria-label="Selected file">
            <PreviewMedia id={current.id} video={current.f.type === "video"} />
            <div className="bar" style={{ margin: "8px 0" }}>
              <button className="sm" aria-label="Previous file" disabled={at <= 0} onClick={() => setSel(items[at - 1]!.id)}>
                ‹
              </button>
              <span className="muted small grow" style={{ textAlign: "center" }}>
                {at + 1} of {items.length}
              </span>
              <button className="sm" aria-label="Next file" disabled={at >= items.length - 1} onClick={() => setSel(items[at + 1]!.id)}>
                ›
              </button>
            </div>
            <div style={{ fontWeight: 600 }}>{current.f.label}</div>
            <div className="muted small">{current.f.section}</div>
            <AnswerNear insp={insp} trees={trees} f={current.f} />
            {byOps.has(current.id) && (
              <p className="muted small" style={{ margin: "6px 0 0" }}>
                Added by Ops
              </p>
            )}
            {internal.has(current.id) && (
              <p className="small warn-text" style={{ margin: "6px 0 0" }}>
                Hidden from customer: not in the report, its downloads or any ZIP
              </p>
            )}
            <OpsFileActions
              booking={booking}
              f={current.f}
              count={idsOf(insp, current.f.part, current.f.key).length}
              replaceId={current.id}
              onDone={refreshed}
              onReplaced={setSel}
            />
          </aside>
        )}
      </div>
    </>
  );
}
