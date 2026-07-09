"use client";

import type { RatingAttr } from "@/lib/api";

// 2K-style attribute radar. Single series: blue wash + 2px stroke, hairline
// web rings, labels in text tokens. Values are league percentiles (25–99).
const SIZE = 320;
const C = SIZE / 2;
const R = 108;

export default function Radar({ attributes }: { attributes: RatingAttr[] }) {
  const n = attributes.length;
  if (n < 3) return null;

  const point = (i: number, r: number): [number, number] => {
    const angle = -Math.PI / 2 + (i * 2 * Math.PI) / n;
    return [C + r * Math.cos(angle), C + r * Math.sin(angle)];
  };
  const ring = (frac: number) =>
    attributes.map((_, i) => point(i, R * frac).map((v) => v.toFixed(1)).join(",")).join(" ");
  const shape = attributes
    .map((a, i) => point(i, (R * a.value) / 99).map((v) => v.toFixed(1)).join(","))
    .join(" ");

  return (
    <svg viewBox={`0 0 ${SIZE} ${SIZE}`} className="w-full max-w-[320px]">
      {[1 / 3, 2 / 3, 1].map((f) => (
        <polygon key={f} points={ring(f)} fill="none" stroke="var(--gridline)" strokeWidth="1" />
      ))}
      {attributes.map((_, i) => {
        const [x, y] = point(i, R);
        return <line key={i} x1={C} y1={C} x2={x} y2={y} stroke="var(--gridline)" strokeWidth="1" />;
      })}
      <polygon points={shape} fill="var(--series-pos)" opacity="0.14" />
      <polygon points={shape} fill="none" stroke="var(--series-pos)" strokeWidth="2" strokeLinejoin="round" />
      {attributes.map((a, i) => {
        const [x, y] = point(i, (R * a.value) / 99);
        return <circle key={a.label} cx={x} cy={y} r="3.5" fill="var(--series-pos)" stroke="var(--surface-1)" strokeWidth="2" />;
      })}
      {attributes.map((a, i) => {
        const [x, y] = point(i, R + 22);
        return (
          <text
            key={a.label}
            x={x}
            y={y}
            textAnchor="middle"
            fontSize="11"
            fill="var(--text-secondary)"
          >
            <tspan x={x} dy="-2">{a.label}</tspan>
            <tspan x={x} dy="12" fontWeight="700" fill="var(--text-primary)">{a.value}</tspan>
          </text>
        );
      })}
    </svg>
  );
}
