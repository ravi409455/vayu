import { useLayoutEffect, useRef, useState } from "react";

export type Series = { key: string; name: string };
export type Column = { key: string; label: string; long: string; values: Record<string, number> };

const H = 260,
  PAD_L = 40,
  PAD_B = 28,
  PAD_T = 8,
  MAX_BAR = 24,
  GAP = 2,
  R = 4,
  MAX_SERIES = 8;

/** Clean axis ticks for 0..max: 1, 2 or 5 times a power of ten, about four of them. */
export function niceTicks(max: number): number[] {
  if (max <= 0) return [0, 1];
  const raw = max / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * p).find((s) => s >= raw)!;
  const top = Math.ceil(max / step) * step;
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
}

/** More than eight series: the smallest fold into "Other" (a ninth colour is never invented). */
export function foldSeries(series: Series[], cols: Column[]): { series: Series[]; cols: Column[] } {
  if (series.length <= MAX_SERIES) return { series, cols };
  const total = (k: string) => cols.reduce((n, c) => n + (c.values[k] ?? 0), 0);
  const keep = [...series].sort((a, b) => total(b.key) - total(a.key)).slice(0, MAX_SERIES - 1);
  const kept = new Set(keep.map((s) => s.key));
  const order = series.filter((s) => kept.has(s.key));
  return {
    series: [...order, { key: "__other", name: "Other" }],
    cols: cols.map((c) => ({
      ...c,
      values: {
        ...Object.fromEntries(order.map((s) => [s.key, c.values[s.key] ?? 0])),
        __other: series.filter((s) => !kept.has(s.key)).reduce((n, s) => n + (c.values[s.key] ?? 0), 0),
      },
    })),
  };
}

/** A path for one bar segment: square at the bottom, 4px rounded only when it is the top of the bar. */
function seg(x: number, y: number, w: number, h: number, roundTop: boolean) {
  const r = roundTop ? Math.min(R, h, w / 2) : 0;
  return `M${x},${y + h}V${y + r}${r ? `Q${x},${y} ${x + r},${y}` : ""}H${x + w - r}${r ? `Q${x + w},${y} ${x + w},${y + r}` : ""}V${y + h}Z`;
}

/** Bookings per period as stacked columns: one baseline, thin bars, a 2px gap between segments,
 *  recessive grid, a legend, and a tooltip on every column (keyboard too). */
export function StackedBars({ series: s0, cols: c0, unit = "bookings" }: { series: Series[]; cols: Column[]; unit?: string }) {
  const wrap = useRef<HTMLDivElement>(null);
  const [w, setW] = useState(800);
  const [hover, setHover] = useState<number | null>(null);
  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const ro = new ResizeObserver(([e]) => setW(Math.max(320, e!.contentRect.width)));
    ro.observe(el);
    return () => ro.disconnect();
  }, []);
  const { series, cols } = foldSeries(s0, c0);
  const totals = cols.map((c) => series.reduce((n, s) => n + (c.values[s.key] ?? 0), 0));
  const ticks = niceTicks(Math.max(0, ...totals));
  const top = ticks[ticks.length - 1]!;
  const plotW = w - PAD_L,
    plotH = H - PAD_B - PAD_T;
  const band = plotW / Math.max(1, cols.length);
  const barW = Math.max(2, Math.min(MAX_BAR, band * 0.6));
  const y = (v: number) => PAD_T + plotH - (v / top) * plotH;
  const every = Math.max(1, Math.ceil(cols.length / Math.floor(plotW / 64))); // x labels that never collide
  const color = (i: number) => `var(--series-${(i % MAX_SERIES) + 1})`;
  const h = hover !== null ? cols[hover] : null;
  return (
    <div className="stacked-bars">
      {series.length > 1 && (
        <div className="legend-row" aria-hidden="true">
          {series.map((s, i) => (
            <span key={s.key} className="legend-key">
              <span style={{ background: color(i) }} />
              {s.name}
              <b>{cols.reduce((n, c) => n + (c.values[s.key] ?? 0), 0).toLocaleString("en-IN")}</b>
            </span>
          ))}
        </div>
      )}
      <div ref={wrap} className="sb-plot" onMouseLeave={() => setHover(null)}>
        <svg width={w} height={H} role="list" aria-label={`${unit} per period; the Table view lists every value`}>
          {ticks.map((t) => (
            <g key={t}>
              <line x1={PAD_L} x2={w} y1={y(t)} y2={y(t)} className={t === 0 ? "sb-base" : "sb-grid"} />
              <text x={PAD_L - 8} y={y(t)} className="sb-tick" textAnchor="end" dominantBaseline="middle">
                {t.toLocaleString("en-IN")}
              </text>
            </g>
          ))}
          {cols.map((c, ci) => {
            const x = PAD_L + ci * band + (band - barW) / 2;
            let acc = 0;
            const parts = series.map((sr, si) => ({ si, v: c.values[sr.key] ?? 0 })).filter((p) => p.v > 0);
            return (
              <g
                key={c.key}
                className={hover === ci ? "sb-col on" : "sb-col"}
                tabIndex={0}
                role="listitem"
                aria-label={`${c.long}: ${totals[ci]} ${unit}${series.length > 1 ? `, ${parts.map((p) => `${series[p.si]!.name} ${p.v}`).join(", ")}` : ""}`}
                onMouseEnter={() => setHover(ci)}
                onFocus={() => setHover(ci)}
                onBlur={() => setHover(null)}
              >
                <rect x={PAD_L + ci * band} y={PAD_T} width={band} height={plotH} className="sb-hit" />
                {parts.map((p, k) => {
                  const y1 = y(acc + p.v),
                    y0 = y(acc);
                  acc += p.v;
                  const gap = k > 0 ? GAP : 0; // a 2px surface gap above the segment below
                  return <path key={p.si} d={seg(x, y1, barW, Math.max(0, y0 - y1 - gap), k === parts.length - 1)} fill={color(p.si)} />;
                })}
                {ci % every === 0 && (
                  <text x={x + barW / 2} y={H - 8} className="sb-tick" textAnchor="middle">
                    {c.label}
                  </text>
                )}
              </g>
            );
          })}
        </svg>
        {h && (
          <div
            className="sb-tip"
            role="status"
            style={{
              left: (() => {
                const right = PAD_L + (hover! + 1) * band + 8;
                return right + 184 <= w ? right : Math.max(0, PAD_L + hover! * band - 188);
              })(),
            }}
          >
            <div className="muted small">{h.long}</div>
            <div className="sb-total">
              {totals[hover!]} <span className="muted small">{unit}</span>
            </div>
            {series.length > 1 &&
              series.map(
                (sr, i) =>
                  (h.values[sr.key] ?? 0) > 0 && (
                    <div key={sr.key} className="sb-tip-row">
                      <span className="sb-key" style={{ background: color(i) }} />
                      <strong>{h.values[sr.key]}</strong>
                      <span className="muted">{sr.name}</span>
                    </div>
                  ),
              )}
          </div>
        )}
      </div>
    </div>
  );
}
