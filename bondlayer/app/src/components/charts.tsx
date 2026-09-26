"use client";

import { useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import styles from "./charts.module.css";

/**
 * Small dependency-free SVG charts for the insights dashboard.
 *
 * Series colours are dataviz reference slots in an order validated for this
 * console's white cards (validate_palette.js, light, surface #ffffff): every
 * hard check passes. Aqua and yellow sit below 3:1 contrast on white, so each
 * chart ships a legend with values and a table view.
 */
export const SERIES = ["#1baf7a", "#eb6834", "#2a78d6", "#eda100"] as const;
const GRID = "#e8ecf1";
const AXIS = "#c9d1dc";
const TRACK = "#d5f2e7";

export type TableData = { columns: string[]; rows: (string | number)[][] };

function useWidth<T extends HTMLElement>(fallback = 600) {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(fallback);
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(260, Math.floor(entry.contentRect.width))));
    observer.observe(element);
    return () => observer.disconnect();
  }, []);
  return [ref, width] as const;
}

/** Clean integer ticks from 0: steps of 1, 2 or 5 × 10ⁿ. */
function ticksFor(max: number) {
  const raw = Math.max(1, max) / 4;
  const magnitude = 10 ** Math.floor(Math.log10(raw));
  const step = Math.max(1, [1, 2, 5, 10].map((m) => m * magnitude).find((s) => s >= raw) ?? 10 * magnitude);
  const top = step * Math.max(1, Math.ceil(max / step));
  return Array.from({ length: Math.round(top / step) + 1 }, (_, i) => i * step);
}

export function ChartCard({ title, subtitle, table, action, className, children }: {
  title: string; subtitle?: string; table?: TableData; action?: ReactNode; className?: string; children: ReactNode;
}) {
  const [view, setView] = useState<"chart" | "table">("chart");
  return (
    <section className={`${styles.card} ${className ?? ""}`}>
      <header className={styles.cardHeader}>
        <div><h2>{title}</h2>{subtitle && <p>{subtitle}</p>}</div>
        <div className={styles.cardTools}>
          {action}
          {table && (
            <button type="button" className={styles.viewToggle} aria-pressed={view === "table"}
              onClick={() => setView(view === "chart" ? "table" : "chart")}>
              {view === "chart" ? "Table" : "Chart"}
            </button>
          )}
        </div>
      </header>
      {view === "table" && table ? (
        <div className={styles.tableWrap}>
          <table>
            <thead><tr>{table.columns.map((column) => <th key={column}>{column}</th>)}</tr></thead>
            <tbody>{table.rows.map((row, i) => <tr key={i}>{row.map((cell, j) => <td key={j}>{cell}</td>)}</tr>)}</tbody>
          </table>
        </div>
      ) : children}
    </section>
  );
}

export function Legend({ items }: { items: { name: string; color: string; value?: string; shape?: "line" | "rect" }[] }) {
  return (
    <ul className={styles.legend}>
      {items.map((item) => (
        <li key={item.name}>
          <i className={item.shape === "line" ? styles.keyLine : styles.keyRect} style={{ background: item.color }} />
          <span>{item.name}</span>
          {item.value !== undefined && <strong>{item.value}</strong>}
        </li>
      ))}
    </ul>
  );
}

/** `hidden` series are not drawn; they appear only in the tooltip (and the card's table view). */
export type Series = { name: string; color: string; values: number[]; hidden?: boolean };

/** Multi-series line chart with a snapping crosshair and one tooltip for every series. */
export function LineChart({ labels, series, height = 230 }: { labels: string[]; series: Series[]; height?: number }) {
  const [ref, width] = useWidth<HTMLDivElement>();
  const [active, setActive] = useState<number | null>(null);
  const n = labels.length;
  if (n === 0) return <p className={styles.empty}>No data in this period.</p>;

  const pad = { top: 12, right: 16, bottom: 28, left: 34 };
  const plotW = width - pad.left - pad.right;
  const plotH = height - pad.top - pad.bottom;
  const ticks = ticksFor(Math.max(0, ...series.flatMap((s) => s.values)));
  const top = ticks[ticks.length - 1];
  const x = (i: number) => pad.left + (n === 1 ? plotW / 2 : (i / (n - 1)) * plotW);
  const y = (v: number) => pad.top + plotH - (v / top) * plotH;
  const every = Math.max(1, Math.ceil(n / 6));
  const showLabel = (i: number) => i === n - 1 || (i % every === 0 && n - 1 - i >= every / 2);

  function onKey(event: KeyboardEvent<SVGSVGElement>) {
    if (event.key === "ArrowRight") { event.preventDefault(); setActive((a) => Math.min(n - 1, (a ?? -1) + 1)); }
    else if (event.key === "ArrowLeft") { event.preventDefault(); setActive((a) => Math.max(0, (a ?? n) - 1)); }
    else if (event.key === "Escape") setActive(null);
  }

  const point = active ?? n - 1;
  return (
    <div ref={ref} className={styles.plot}>
      <svg width={width} height={height} role="img" tabIndex={0}
        aria-label={`${series.map((s) => s.name).join(" and ")} over time. Use the arrow keys to read values.`}
        onKeyDown={onKey} onBlur={() => setActive(null)} onPointerLeave={() => setActive(null)}
        onPointerMove={(event) => {
          const rect = event.currentTarget.getBoundingClientRect();
          const ratio = (event.clientX - rect.left - pad.left) / Math.max(1, plotW);
          setActive(Math.min(n - 1, Math.max(0, Math.round(ratio * (n - 1)))));
        }}>
        {ticks.map((tick) => (
          <g key={tick}>
            <line x1={pad.left} x2={pad.left + plotW} y1={y(tick)} y2={y(tick)} stroke={tick === 0 ? AXIS : GRID} strokeWidth={1} />
            <text x={pad.left - 8} y={y(tick)} dy="0.32em" textAnchor="end" className={styles.tick}>{tick}</text>
          </g>
        ))}
        {labels.map((label, i) => showLabel(i) && (
          <text key={i} x={x(i)} y={height - 8} className={styles.tick}
            textAnchor={n === 1 ? "middle" : i === 0 ? "start" : i === n - 1 ? "end" : "middle"}>{label}</text>
        ))}
        {series[0] && n > 1 && (
          <path d={`M${x(0)},${y(0)} ${series[0].values.map((v, i) => `L${x(i)},${y(v)}`).join(" ")} L${x(n - 1)},${y(0)} Z`}
            fill={series[0].color} opacity={0.1} />
        )}
        {series.map((s) => !s.hidden && (
          <path key={s.name} d={s.values.map((v, i) => `${i ? "L" : "M"}${x(i)},${y(v)}`).join(" ")}
            fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        ))}
        {active !== null && <line x1={x(active)} x2={x(active)} y1={pad.top} y2={pad.top + plotH} stroke={AXIS} strokeWidth={1} />}
        {series.map((s) => !s.hidden && (
          <circle key={s.name} cx={x(point)} cy={y(s.values[point])} r={4} fill={s.color} stroke="#fff" strokeWidth={2} />
        ))}
      </svg>
      {active !== null && (
        <div className={styles.tooltip} style={{ left: Math.min(Math.max(x(active), 90), width - 90) }}>
          <p className={styles.tipLabel}>{labels[active]}</p>
          {series.map((s) => (
            <p key={s.name} className={styles.tipRow}>
              <i style={{ background: s.hidden ? "transparent" : s.color }} /><strong>{s.values[active]}</strong><span>{s.name}</span>
            </p>
          ))}
        </div>
      )}
    </div>
  );
}

export type Slice = { label: string; value: number; color: string };

/** Part-to-whole donut (≤ 4 slices) with a value legend; hover or focus shows a slice in the centre. */
export function Donut({ slices, centerLabel, unit = "requests" }: { slices: Slice[]; centerLabel: string; unit?: string }) {
  const [active, setActive] = useState<number | null>(null);
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  const size = 176;
  const stroke = 22;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const gap = slices.filter((slice) => slice.value > 0).length > 1 ? 2 : 0;
  const starts = slices.map((_, i) => slices.slice(0, i).reduce((sum, slice) => sum + slice.value, 0));
  const shown = active !== null ? slices[active] : null;
  const pct = (value: number) => (total ? Math.round((value / total) * 100) : 0);

  return (
    <div className={styles.donut}>
      <div className={styles.donutPlot}>
        <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img"
          aria-label={`${centerLabel}: ${slices.map((s) => `${s.label} ${s.value}`).join(", ")}`}>
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={GRID} strokeWidth={stroke} />
          <g transform={`rotate(-90 ${size / 2} ${size / 2})`}>
            {total > 0 && slices.map((slice, i) => slice.value > 0 && (
              <circle key={slice.label} cx={size / 2} cy={size / 2} r={radius} fill="none" stroke={slice.color}
                strokeWidth={active === i ? stroke + 4 : stroke}
                strokeDasharray={`${Math.max(0, (slice.value / total) * circumference - gap)} ${circumference}`}
                strokeDashoffset={-(starts[i] / total) * circumference}
                className={styles.slice} onPointerEnter={() => setActive(i)} onPointerLeave={() => setActive(null)} />
            ))}
          </g>
        </svg>
        <div className={styles.donutCenter} aria-hidden="true">
          <strong>{shown ? shown.value : total}</strong>
          <span>{shown ? shown.label : centerLabel}</span>
        </div>
      </div>
      <ul className={styles.sliceLegend}>
        {slices.map((slice, i) => (
          <li key={slice.label}>
            <button type="button" className={active === i ? styles.sliceActive : ""}
              onPointerEnter={() => setActive(i)} onPointerLeave={() => setActive(null)}
              onFocus={() => setActive(i)} onBlur={() => setActive(null)}
              aria-label={`${slice.label}: ${slice.value} ${unit}, ${pct(slice.value)}%`}>
              <i className={styles.keyRect} style={{ background: slice.color }} />
              <span>{slice.label}</span>
              <strong>{slice.value}</strong>
              <small>{pct(slice.value)}%</small>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Horizontal bars for one series: label above, value at the bar tip. */
export function BarList({ items, unit = "requests", onSelect, color = SERIES[0], limit = 6 }: {
  items: { label: string; value: number; ids?: string[] }[];
  unit?: string; onSelect?: (label: string, ids: string[]) => void; color?: string; limit?: number;
}) {
  if (items.length === 0) return <p className={styles.empty}>None yet.</p>;
  const shown = items.slice(0, limit);
  const max = Math.max(1, ...shown.map((item) => item.value));
  return (
    <ul className={styles.barList}>
      {shown.map((item) => {
        const body = (
          <>
            <span className={styles.barLabel}>{item.label}</span>
            <span className={styles.barRow}>
              <span className={styles.bar} style={{ width: `${(item.value / max) * 100}%`, background: color }} />
              <strong>{item.value}</strong>
            </span>
          </>
        );
        return (
          <li key={item.label}>
            {onSelect && item.ids
              ? <button type="button" onClick={() => onSelect(item.label, item.ids ?? [])} aria-label={`${item.label}: ${item.value} ${unit}. Show these requests.`}>{body}</button>
              : <div>{body}</div>}
          </li>
        );
      })}
    </ul>
  );
}

/** Stacked horizontal bars; a hovered or focused segment names itself beside the row label. */
export function StackedBars({ rows, keys, unit = "requests" }: {
  rows: { label: string; values: number[] }[]; keys: { name: string; color: string }[]; unit?: string;
}) {
  const [hover, setHover] = useState<{ row: string; text: string } | null>(null);
  if (rows.length === 0) return <p className={styles.empty}>No benefit data yet.</p>;
  const totals = rows.map((row) => row.values.reduce((a, b) => a + b, 0));
  const max = Math.max(1, ...totals);
  return (
    <>
      <Legend items={keys.map((key) => ({ name: key.name, color: key.color }))} />
      <ul className={styles.stackList}>
        {rows.map((row, r) => (
          <li key={row.label}>
            <div className={styles.stackHead}>
              <span>{row.label}</span>
              <small>{hover?.row === row.label ? hover.text : `${totals[r]} ${unit}`}</small>
            </div>
            <div className={styles.stackTrack} style={{ width: `${(totals[r] / max) * 100}%` }}>
              {row.values.map((value, i) => value > 0 && (
                <span key={keys[i].name} tabIndex={0} className={styles.segment}
                  style={{ flexGrow: value, background: keys[i].color }}
                  aria-label={`${row.label}, ${keys[i].name}: ${value} ${unit}`}
                  onPointerEnter={() => setHover({ row: row.label, text: `${keys[i].name}: ${value}` })}
                  onPointerLeave={() => setHover(null)}
                  onFocus={() => setHover({ row: row.label, text: `${keys[i].name}: ${value}` })}
                  onBlur={() => setHover(null)} />
              ))}
            </div>
          </li>
        ))}
      </ul>
    </>
  );
}

export function Sparkline({ values, color = SERIES[0] }: { values: number[]; color?: string }) {
  if (values.length < 2) return null;
  const w = 112;
  const h = 30;
  const max = Math.max(1, ...values);
  const points = values.map((v, i) => [2 + (i / (values.length - 1)) * (w - 6), h - 3 - (v / max) * (h - 8)]);
  const [lastX, lastY] = points[points.length - 1];
  return (
    <svg className={styles.sparkline} width={w} height={h} aria-hidden="true">
      <path d={points.map(([px, py], i) => `${i ? "L" : "M"}${px},${py}`).join(" ")} fill="none" stroke="#a3adba"
        strokeWidth={1.5} strokeLinejoin="round" strokeLinecap="round" />
      <circle cx={lastX} cy={lastY} r={3.5} fill={color} stroke="#fff" strokeWidth={1.5} />
    </svg>
  );
}

export function Meter({ value, color = SERIES[0] }: { value: number; color?: string }) {
  const width = `${Math.round(Math.max(0, Math.min(1, value)) * 100)}%`;
  return <span className={styles.meter} style={{ background: TRACK }}><span style={{ width, background: color }} /></span>;
}

export function StatTile({ label, value, detail, children }: { label: string; value: string; detail?: string; children?: ReactNode }) {
  return (
    <article className={styles.stat}>
      <p>{label}</p>
      <strong>{value}</strong>
      {detail && <small>{detail}</small>}
      {children && <div className={styles.statTrend}>{children}</div>}
    </article>
  );
}
