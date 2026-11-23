import { useState } from "react";
import { uploadFile } from "../../../api/client";
import { Field, Modal, Tabs, useToast } from "../../../ui/kit";
import type { Band, Definition, SlotItem } from "./model";

type Tab = "paper" | "bands" | "look" | "images" | "file";
const SIDES = ["left", "center", "right"] as const;
const COLOR_NAMES = [["brand", "Brand"], ["text", "Text"], ["ok", "Good (green)"], ["warn", "Not checked (amber)"], ["bad", "Problem (red)"], ["muted", "Not available (grey)"]] as const;
const DEFAULT_COLORS: Record<string, string> = { brand: "#a62830", text: "#1b1f27", ok: "#15703f", warn: "#b25e09", bad: "#b3261e", muted: "#8a93a3" };
const FONTS = ["Inter", "Barlow Semi Condensed", "Helvetica"];

/** Things that apply to the whole report, out of the way until needed. */
export function ReportSettings({ def, onChange, onClose, readOnly }: { def: Definition; onChange: (d: Definition) => void; onClose: () => void; readOnly: boolean }) {
  const [tab, setTab] = useState<Tab>("bands");
  const paper = def.paper ?? {};
  const theme = def.theme ?? {};
  return (
    <Modal title="Report settings" wide onClose={onClose} actions={<button className="primary" onClick={onClose}>Done</button>}>
      <Tabs value={tab} onChange={setTab} tabs={[{ id: "bands", label: "Header and footer" }, { id: "look", label: "Colours and fonts" }, { id: "images", label: "Watermark" }, { id: "paper", label: "Paper" }, { id: "file", label: "File name" }]} />
      <fieldset disabled={readOnly} className="rd-fieldset">
        {tab === "paper" && (
          <div className="grid2">
            <Field label="Size"><select value={paper.size ?? "A4"} onChange={(e) => onChange({ ...def, paper: { ...paper, size: e.target.value as "A4" } })}><option>A4</option><option>Letter</option></select></Field>
            <Field label="Orientation"><select value={paper.orientation ?? "portrait"} onChange={(e) => onChange({ ...def, paper: { ...paper, orientation: e.target.value as "portrait" } })}><option value="portrait">Portrait</option><option value="landscape">Landscape</option></select></Field>
            {(["top", "right", "bottom", "left"] as const).map((k) => (
              <Field key={k} label={`Margin ${k} (mm)`} help={k === "top" || k === "bottom" ? "Used when a page has no header or footer." : undefined}>
                <input type="number" min={0} max={60} value={paper.margins?.[k] ?? { top: 26, right: 12, bottom: 16, left: 12 }[k]} onChange={(e) => onChange({ ...def, paper: { ...paper, margins: { ...paper.margins, [k]: Number(e.target.value) } } })} /></Field>))}
          </div>)}
        {tab === "look" && (
          <>
            <div className="grid2">
              {COLOR_NAMES.map(([k, l]) => (
                <Field key={k} label={l}><input type="color" value={theme.colors?.[k] ?? DEFAULT_COLORS[k]} onChange={(e) => onChange({ ...def, theme: { ...theme, colors: { ...theme.colors, [k]: e.target.value } } })} /></Field>))}
            </div>
            <div className="grid2">
              <Field label="Text font"><select value={theme.fonts?.body ?? "Inter"} onChange={(e) => onChange({ ...def, theme: { ...theme, fonts: { ...theme.fonts, body: e.target.value } } })}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select></Field>
              <Field label="Heading font"><select value={theme.fonts?.headings ?? "Barlow Semi Condensed"} onChange={(e) => onChange({ ...def, theme: { ...theme, fonts: { ...theme.fonts, headings: e.target.value } } })}>{FONTS.map((f) => <option key={f}>{f}</option>)}</select></Field>
              <Field label="Text size (pt)"><input type="number" min={7} max={14} step={0.5} value={theme.size ?? 9.5} onChange={(e) => onChange({ ...def, theme: { ...theme, size: Number(e.target.value) } })} /></Field>
            </div>
          </>)}
        {tab === "images" && <WatermarkEditor def={def} onChange={onChange} />}
        {tab === "file" && (
          <Field label="File name" help="Values like {{ sys.booking_id }} are filled in for each report. Must end in .pdf.">
            <input value={def.filename ?? "{{ sys.booking_id }}.pdf"} onChange={(e) => onChange({ ...def, filename: e.target.value })} /></Field>)}
        {tab === "bands" && <BandsEditor def={def} onChange={onChange} />}
      </fieldset>
    </Modal>
  );
}

function WatermarkEditor({ def, onChange }: { def: Definition; onChange: (d: Definition) => void }) {
  const { fail } = useToast();
  const wm = def.watermark;
  return (
    <>
      <p className="muted small">A faint picture behind every page (not full-page designs). Tables show it through their rows.</p>
      {wm && <img src={`/api/v1/form-assets/${wm.image}`} alt="The watermark" className="rd-thumb" />}
      <div className="bar">
        <label className="btn sm">{wm ? "Replace picture" : "Upload a picture"}
          <input type="file" accept="image/png,image/jpeg" hidden aria-label="Watermark picture" onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            try { const r = await uploadFile<{ id: string }>("form-assets", file); onChange({ ...def, watermark: { opacity: 0.3, width: 60, ...wm, image: r.id } }); } catch (err) { fail(err); }
          }} /></label>
        {wm && <button type="button" className="sm danger" onClick={() => { const { watermark: _, ...rest } = def; onChange(rest as Definition); }}>Remove</button>}
      </div>
      {wm && (
        <div className="grid2">
          <Field label={`Strength ${Math.round((wm.opacity ?? 0.08) * 100)}%`}><input type="range" min={2} max={100} value={Math.round((wm.opacity ?? 0.08) * 100)} onChange={(e) => onChange({ ...def, watermark: { ...wm, opacity: Number(e.target.value) / 100 } })} /></Field>
          <Field label={`Width ${wm.width ?? 60}% of the page`}><input type="range" min={10} max={100} value={wm.width ?? 60} onChange={(e) => onChange({ ...def, watermark: { ...wm, width: Number(e.target.value) } })} /></Field>
        </div>)}
    </>
  );
}

function BandsEditor({ def, onChange }: { def: Definition; onChange: (d: Definition) => void }) {
  const [style, setStyle] = useState<"normal" | "cover">("normal");
  const bands = def.bands ?? {};
  const set = (kind: "header" | "footer", band: Band | undefined) => {
    const cur = { ...(bands[style] ?? {}) };
    if (band) cur[kind] = band; else delete cur[kind];
    onChange({ ...def, bands: { ...bands, [style]: cur } });
  };
  return (
    <>
      <div className="seg sm" role="group" aria-label="Page style">
        <button type="button" aria-pressed={style === "normal"} onClick={() => setStyle("normal")}>Normal pages</button>
        <button type="button" aria-pressed={style === "cover"} onClick={() => setStyle("cover")}>Cover pages</button>
      </div>
      {(["header", "footer"] as const).map((kind) => {
        const band = bands[style]?.[kind];
        return (
          <section key={kind} className="rd-band-ed" aria-label={`${style} ${kind}`}>
            <div className="bar" style={{ margin: "10px 0 6px" }}>
              <strong className="grow">{kind === "header" ? "Header" : "Footer"}</strong>
              <label className="check"><input type="checkbox" checked={!!band} onChange={(e) => set(kind, e.target.checked ? { background: kind === "header" ? "brand" : "none", height: kind === "header" ? 15 : 8 } : undefined)} /> Show</label>
            </div>
            {band && (
              <>
                <div className="grid2">
                  <Field label="Background"><select value={band.background ?? "none"} onChange={(e) => set(kind, { ...band, background: e.target.value as "none" })}><option value="none">None</option><option value="brand">Brand colour</option></select></Field>
                  <Field label="Height (mm)"><input type="number" min={6} max={60} value={band.height ?? 16} onChange={(e) => set(kind, { ...band, height: Number(e.target.value) })} /></Field>
                </div>
                <div className="rd-slots">
                  {SIDES.map((side) => <SlotEditor key={side} side={side} items={band[side] ?? []} onChange={(items) => set(kind, { ...band, [side]: items })} />)}
                </div>
              </>)}
          </section>);
      })}
      <p className="muted small">In a slot, a picture and the text after it sit side by side on one line; texts one after another stack. Values: {"{{ sys.booking_id }}"}, {"{{ sys.car }}"}, {"{{ sys.inspected_on }}"}, page numbers {"{{ sys.page }}"} of {"{{ sys.pages }}"}.</p>
    </>
  );
}

function SlotEditor({ side, items, onChange }: { side: string; items: SlotItem[]; onChange: (i: SlotItem[]) => void }) {
  const { fail } = useToast();
  const set = (i: number, it: SlotItem) => onChange(items.map((x, j) => (j === i ? it : x)));
  return (
    <div className="rd-slot">
      <span className="rd-col-h">{side === "center" ? "Centre" : side[0]!.toUpperCase() + side.slice(1)}</span>
      {items.map((it, i) => (
        <div key={i} className="rd-slot-item">
          {"text" in it
            ? <input aria-label={`${side} text ${i + 1}`} value={it.text} onChange={(e) => set(i, { text: e.target.value })} />
            : <span className="bar" style={{ margin: 0 }}>
                <img src={`/api/v1/form-assets/${it.image}`} alt="" className="rd-thumb sm" />
                <input type="number" aria-label="Picture height (mm)" min={3} max={40} value={it.height ?? 10} onChange={(e) => set(i, { ...it, height: Number(e.target.value) })} style={{ width: 64 }} />
                <label className="check small"><input type="checkbox" checked={!!it.tile} onChange={(e) => set(i, { ...it, tile: e.target.checked })} /> white tile</label>
              </span>}
          <button type="button" className="link" aria-label="Remove" onClick={() => onChange(items.filter((_, j) => j !== i))}>✕</button>
        </div>))}
      <div className="bar" style={{ margin: 0 }}>
        <button type="button" className="link small" onClick={() => onChange([...items, { text: "" }])}>+ Text</button>
        <label className="link small" style={{ cursor: "pointer" }}>+ Picture
          <input type="file" accept="image/png,image/jpeg" hidden aria-label={`${side} picture`} onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            try { const r = await uploadFile<{ id: string }>("form-assets", file); onChange([...items, { image: r.id, height: 10, tile: true }]); } catch (err) { fail(err); }
          }} /></label>
      </div>
    </div>
  );
}
