import { useState } from "react";
import { fmtNum } from "../api.js";

const MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

/** Einfaches Säulendiagramm. data: [{label, value, sub?}] */
export function Bars({ data, unit = "", height = 180, color = "var(--celeste)", labelEvery = 1, format = (v) => fmtNum(v, 0) }) {
  const [hover, setHover] = useState(null);
  const max = Math.max(1, ...data.map((d) => d.value));
  const W = 640, padB = 26, padT = 16;
  const bw = W / Math.max(1, data.length);
  const h = height - padB - padT;
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="chart" role="img" aria-label="Säulendiagramm">
      {[0.5, 1].map((f) => (
        <line key={f} x1="0" x2={W} y1={padT + h * (1 - f)} y2={padT + h * (1 - f)} className="chart-grid" />
      ))}
      {data.map((d, i) => {
        const bh = (d.value / max) * h;
        const x = i * bw;
        return (
          <g key={i} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect x={x} y="0" width={bw} height={height} fill="transparent" />
            <rect
              className="bar-grow" style={{ "--i": i }}
              x={x + bw * 0.14} y={padT + h - bh} width={bw * 0.72} height={Math.max(bh, d.value > 0 ? 1 : 0)}
              rx="2" fill={color} opacity={hover === null || hover === i ? 1 : 0.45}
            />
            {i % labelEvery === 0 && (
              <text x={x + bw / 2} y={height - 8} textAnchor="middle" className="chart-label">{d.label}</text>
            )}
          </g>
        );
      })}
      {hover !== null && (
        <text x={Math.min(Math.max(hover * bw + bw / 2, 60), W - 60)} y="11" textAnchor="middle" className="chart-tip">
          {data[hover].label}: {format(data[hover].value)} {unit}{data[hover].sub ? ` · ${data[hover].sub}` : ""}
        </text>
      )}
    </svg>
  );
}

/** Kumulierte Kilometer je Jahr als Linien über den Jahrestag. cumulative: {jahr: [[tag, km], ...]} */
export function CumulativeLines({ cumulative, height = 240 }) {
  const years = Object.keys(cumulative).sort();
  const W = 640, padL = 44, padB = 24, padT = 12, padR = 70;
  const finals = years.map((y) => {
    const arr = cumulative[y];
    return arr[arr.length - 1][1];
  });
  const max = Math.max(1, ...finals);
  const sx = (d) => padL + (d / 366) * (W - padL - padR);
  const sy = (v) => padT + (1 - v / max) * (height - padT - padB);
  const shades = years.map((_, i) => (i === years.length - 1 ? 1 : 0.25 + 0.5 * (i / Math.max(1, years.length - 1))));
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="chart" role="img" aria-label="Kumulierte Kilometer je Jahr">
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line x1={padL} x2={W - padR} y1={sy(max * f)} y2={sy(max * f)} className="chart-grid" />
          <text x={padL - 6} y={sy(max * f) + 4} textAnchor="end" className="chart-label">{fmtNum(max * f, 0)}</text>
        </g>
      ))}
      {MONTHS.map((m, i) => (
        <text key={m} x={sx(i * 30.5 + 15)} y={height - 6} textAnchor="middle" className="chart-label">{m}</text>
      ))}
      {years.map((y, i) => {
        const pts = [[0, 0], ...cumulative[y]];
        const d = pts.map(([day, km], k) => `${k ? "L" : "M"}${sx(day).toFixed(1)},${sy(km).toFixed(1)}`).join("");
        const last = pts[pts.length - 1];
        return (
          <g key={y}>
            <path d={d} fill="none" stroke="var(--celeste)" strokeWidth={i === years.length - 1 ? 2.5 : 1.5} opacity={shades[i]} strokeLinejoin="round" className="line-draw" pathLength="1" style={{ "--i": i }} />
            <text x={sx(last[0]) + 5} y={sy(last[1]) + 4} className="chart-label" opacity={Math.max(shades[i], 0.6)}>
              {y} · {fmtNum(last[1], 0)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/** Kalender-Heatmap (Tage x Wochen) für ein Jahr. daily: {"2026-05-01": km} */
export function CalendarHeat({ year, daily }) {
  const first = new Date(Date.UTC(year, 0, 1));
  const offset = (first.getUTCDay() + 6) % 7; // Montag = 0
  const days = (Date.UTC(year + 1, 0, 1) - Date.UTC(year, 0, 1)) / 86400000;
  const weeks = Math.ceil((days + offset) / 7);
  const cell = 11, gap = 3, padL = 24, padT = 16;
  const vals = Object.entries(daily).filter(([k]) => k.startsWith(`${year}-`)).map(([, v]) => v);
  const max = Math.max(1, ...vals);
  const cells = [];
  for (let i = 0; i < days; i++) {
    const d = new Date(Date.UTC(year, 0, 1 + i));
    const key = d.toISOString().slice(0, 10);
    const v = daily[key] || 0;
    const idx = i + offset;
    const level = v === 0 ? 0 : Math.min(4, 1 + Math.floor((v / max) * 3.999));
    cells.push(
      <rect
        key={key} x={padL + Math.floor(idx / 7) * (cell + gap)} y={padT + (idx % 7) * (cell + gap)}
        width={cell} height={cell} rx="2" className={`cal cal-${level}`}
      >
        <title>{`${d.toLocaleDateString("de-DE", { timeZone: "UTC" })}: ${v ? fmtNum(v, 1) + " km" : "keine Fahrt"}`}</title>
      </rect>,
    );
  }
  return (
    <svg viewBox={`0 0 ${padL + weeks * (cell + gap)} ${padT + 7 * (cell + gap)}`} className="chart cal-chart" role="img" aria-label={`Fahrtage ${year}`}>
      {["Mo", "Mi", "Fr"].map((l, i) => (
        <text key={l} x="0" y={padT + i * 2 * (cell + gap) + cell - 1} className="chart-label">{l}</text>
      ))}
      {MONTHS.map((m, i) => {
        const idx = Math.floor((Date.UTC(year, i, 1) - Date.UTC(year, 0, 1)) / 86400000) + offset;
        return <text key={m} x={padL + Math.floor(idx / 7) * (cell + gap)} y="9" className="chart-label">{m}</text>;
      })}
      {cells}
    </svg>
  );
}

/** Waagerechte Balken mit Beschriftung. rows: [{label, value, text}] */
export function HBars({ rows, color = "var(--celeste)" }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ul className="hbars">
      {rows.map((r) => (
        <li key={r.label} style={{ "--i": rows.indexOf(r) }}>
          <span className="hbar-label">{r.label}</span>
          <span className="hbar-track"><span className="hbar-fill" style={{ width: `${(r.value / max) * 100}%`, background: color }} /></span>
          <span className="hbar-val">{r.text}</span>
        </li>
      ))}
    </ul>
  );
}

/**
 * Verlaufsdiagramm über die Strecke (z. B. Höhe, Tempo, Puls). x in km, y mit möglichen Lücken (null).
 * hover/onHover verbinden mehrere Diagramme und die Karte über den Index des Stützpunkts.
 */
export function ProfileChart({ x, y, unit, color = "var(--celeste)", fill = false, hover, onHover, height = 130, decimals = 0, zeroBased = false }) {
  const W = 640, padL = 44, padR = 8, padT = 8, padB = 20;
  const vals = y.filter((v) => v != null);
  if (vals.length < 2) return null;
  let lo = zeroBased ? 0 : Math.min(...vals);
  let hi = Math.max(...vals);
  if (hi - lo < 1) { hi = lo + 1; }
  const pad = zeroBased ? 0 : (hi - lo) * 0.08;
  lo -= pad; hi += pad;
  const xmax = x[x.length - 1] || 1;
  const sx = (v) => padL + (v / xmax) * (W - padL - padR);
  const sy = (v) => padT + (1 - (v - lo) / (hi - lo)) * (height - padT - padB);

  let d = "";
  let area = "";
  let open = false;
  y.forEach((v, i) => {
    if (v == null) { open = false; return; }
    d += `${open ? "L" : "M"}${sx(x[i]).toFixed(1)},${sy(v).toFixed(1)}`;
    open = true;
  });
  if (fill) {
    area = `${d}L${sx(x[y.length - 1]).toFixed(1)},${height - padB}L${sx(x[0]).toFixed(1)},${height - padB}Z`;
  }

  function move(e) {
    const r = e.currentTarget.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    const km = ((px - padL) / (W - padL - padR)) * xmax;
    let best = 0;
    for (let i = 1; i < x.length; i++) if (Math.abs(x[i] - km) < Math.abs(x[best] - km)) best = i;
    onHover?.(best);
  }

  const hv = hover != null && y[hover] != null ? hover : null;
  const ticks = [0, 0.5, 1];
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="chart profile" role="img" aria-label={`Verlauf in ${unit}`}
      onMouseMove={move} onMouseLeave={() => onHover?.(null)}>
      {ticks.map((f) => (
        <g key={f}>
          <line x1={padL} x2={W - padR} y1={sy(lo + (hi - lo) * f)} y2={sy(lo + (hi - lo) * f)} className="chart-grid" />
          <text x={padL - 6} y={sy(lo + (hi - lo) * f) + 4} textAnchor="end" className="chart-label">
            {fmtNum(lo + (hi - lo) * f, decimals)}
          </text>
        </g>
      ))}
      {[0, 0.25, 0.5, 0.75, 1].map((f) => (
        <text key={f} x={sx(xmax * f)} y={height - 5} textAnchor={f === 0 ? "start" : f === 1 ? "end" : "middle"} className="chart-label">
          {fmtNum(xmax * f, 0)}{f === 1 ? " km" : ""}
        </text>
      ))}
      {fill && <path d={area} fill={color} opacity="0.18" />}
      <path d={d} fill="none" stroke={color} strokeWidth="1.8" strokeLinejoin="round" className="line-draw" pathLength="1" />
      {hv !== null && (
        <g>
          <line x1={sx(x[hv])} x2={sx(x[hv])} y1={padT} y2={height - padB} stroke="var(--chalk)" strokeWidth="1" opacity="0.5" />
          <circle cx={sx(x[hv])} cy={sy(y[hv])} r="4" fill={color} stroke="var(--ink)" strokeWidth="2" />
          <text x={Math.min(Math.max(sx(x[hv]), padL + 40), W - 50)} y={padT + 10} textAnchor="middle" className="chart-tip">
            {fmtNum(y[hv], decimals)} {unit} · km {fmtNum(x[hv], 1)}
          </text>
        </g>
      )}
    </svg>
  );
}
