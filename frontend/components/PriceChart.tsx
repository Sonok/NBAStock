"use client";

import { useMemo, useRef, useState } from "react";

// Price history chart, per the dataviz spec: 2px line, gradient area wash,
// hairline solid gridlines, crosshair + tooltip on hover, end dot with a
// surface ring. Timeframe tabs slice the served series client-side.
const W = 800;
const H = 260;
const PAD = { l: 52, r: 18, t: 14, b: 30 };
const RANGES = [
  { label: "30D", days: 30 },
  { label: "60D", days: 60 },
  { label: "120D", days: 120 },
];

function fmtDate(d: string): string {
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  return `${months[parseInt(d.slice(4, 6), 10) - 1]} ${parseInt(d.slice(6, 8), 10)}`;
}

function niceTicks(min: number, max: number, n = 4): number[] {
  const span = max - min || 1;
  const step = Math.pow(10, Math.floor(Math.log10(span / n)));
  const err = span / n / step;
  const mult = err >= 7.5 ? 10 : err >= 3.5 ? 5 : err >= 1.5 ? 2 : 1;
  const s = mult * step;
  const ticks = [];
  for (let v = Math.ceil(min / s) * s; v <= max; v += s) ticks.push(v);
  return ticks;
}

export default function PriceChart({
  dates: allDates,
  prices: allPrices,
}: {
  dates: string[];
  prices: number[];
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const [range, setRange] = useState(RANGES[2]);

  const dates = allDates.slice(-range.days);
  const prices = allPrices.slice(-range.days);

  const { pts, ticks, xFor, changePct } = useMemo(() => {
    const min = Math.min(...prices);
    const max = Math.max(...prices);
    const padV = (max - min || 1) * 0.08;
    const lo = min - padV;
    const hi = max + padV;
    const xFor = (i: number) => PAD.l + (i / Math.max(prices.length - 1, 1)) * (W - PAD.l - PAD.r);
    const yFor = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo)) * (H - PAD.t - PAD.b);
    return {
      pts: prices.map((v, i) => [xFor(i), yFor(v)] as const),
      ticks: niceTicks(lo, hi).map((v) => ({ v, y: yFor(v) })),
      xFor,
      changePct: prices.length >= 2 && prices[0] > 0 ? (prices[prices.length - 1] / prices[0] - 1) * 100 : 0,
    };
  }, [prices]);

  if (prices.length < 2) return null;

  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
  const area = `${PAD.l},${H - PAD.b} ${line} ${pts[pts.length - 1][0].toFixed(1)},${H - PAD.b}`;
  const [endX, endY] = pts[pts.length - 1];
  const xLabels = [0, Math.floor(dates.length / 3), Math.floor((2 * dates.length) / 3), dates.length - 1];
  const up = changePct >= 0;

  function onMove(e: React.MouseEvent) {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect) return;
    const px = ((e.clientX - rect.left) / rect.width) * W;
    const frac = (px - PAD.l) / (W - PAD.l - PAD.r);
    const i = Math.round(frac * (prices.length - 1));
    setHover(Math.max(0, Math.min(prices.length - 1, i)));
  }

  return (
    <div>
      <div className="mb-2 flex items-center justify-between">
        <p
          className="text-sm font-medium tabular-nums"
          style={{ color: up ? "var(--delta-good)" : "var(--delta-bad)" }}
        >
          {up ? "▲" : "▼"} {Math.abs(changePct).toFixed(1)}%
          <span className="ml-1.5 font-normal text-[var(--text-muted)]">
            over {range.label.toLowerCase()}
          </span>
        </p>
        <div className="flex gap-0.5 rounded-lg border border-[var(--border-hairline)] bg-[var(--page)] p-0.5">
          {RANGES.map((r) => (
            <button
              key={r.label}
              onClick={() => {
                setRange(r);
                setHover(null);
              }}
              className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                r.label === range.label
                  ? "bg-[var(--surface-1)] text-[var(--text-primary)] shadow-[inset_0_1px_0_rgba(255,255,255,0.06)]"
                  : "text-[var(--text-muted)] hover:text-[var(--text-secondary)]"
              }`}
            >
              {r.label}
            </button>
          ))}
        </div>
      </div>

      <div className="relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${W} ${H}`}
          className="w-full"
          onMouseMove={onMove}
          onMouseLeave={() => setHover(null)}
        >
          <defs>
            <linearGradient id="price-fill" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="var(--series-pos)" stopOpacity="0.22" />
              <stop offset="100%" stopColor="var(--series-pos)" stopOpacity="0" />
            </linearGradient>
          </defs>
          {ticks.map((t) => (
            <g key={t.v}>
              <line x1={PAD.l} x2={W - PAD.r} y1={t.y} y2={t.y} stroke="var(--gridline)" strokeWidth="1" />
              <text x={PAD.l - 8} y={t.y + 3.5} textAnchor="end" fontSize="11" fill="var(--text-muted)">
                ${t.v.toFixed(0)}
              </text>
            </g>
          ))}
          {xLabels.map((i) => (
            <text key={i} x={xFor(i)} y={H - 8} textAnchor="middle" fontSize="11" fill="var(--text-muted)">
              {fmtDate(dates[i])}
            </text>
          ))}
          <polygon points={area} fill="url(#price-fill)" />
          {/* soft glow under the line */}
          <polyline
            points={line}
            fill="none"
            stroke="var(--series-pos)"
            strokeWidth="6"
            strokeLinejoin="round"
            strokeLinecap="round"
            opacity="0.18"
            style={{ filter: "blur(4px)" }}
          />
          <polyline
            key={range.label} /* re-run the draw animation on range change */
            className="chart-line"
            points={line}
            fill="none"
            stroke="var(--series-pos)"
            strokeWidth="2"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
          {hover !== null && (
            <>
              <line
                x1={pts[hover][0]} x2={pts[hover][0]} y1={PAD.t} y2={H - PAD.b}
                stroke="var(--baseline)" strokeWidth="1"
              />
              <circle cx={pts[hover][0]} cy={pts[hover][1]} r="4.5" fill="var(--series-pos)" stroke="var(--surface-1)" strokeWidth="2" />
            </>
          )}
          <circle cx={endX} cy={endY} r="4" fill="var(--series-pos)" stroke="var(--surface-1)" strokeWidth="2" />
        </svg>
        {hover !== null && (
          <div
            className="pointer-events-none absolute -top-1 rounded-lg border border-[var(--border-hairline)] bg-[var(--page)] px-2.5 py-1.5 text-xs shadow-lg"
            style={{
              left: `${(pts[hover][0] / W) * 100}%`,
              transform: pts[hover][0] > W * 0.75 ? "translateX(-110%)" : "translateX(12px)",
            }}
          >
            <p className="text-[var(--text-muted)]">{fmtDate(dates[hover])}</p>
            <p className="font-semibold tabular-nums text-[var(--text-primary)]">
              ${prices[hover].toFixed(2)}
            </p>
          </div>
        )}
      </div>
      <p className="mt-1 text-right text-xs tabular-nums text-[var(--text-muted)]">
        {range.label.toLowerCase()} range ${Math.min(...prices).toFixed(2)} – ${Math.max(...prices).toFixed(2)}
      </p>
    </div>
  );
}
