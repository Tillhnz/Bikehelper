// Schematische Seitenansicht: Sattel- und Lenkerposition aus dem Maßblatt, Ausgangsposition gestrichelt, optimierte Position farbig.
// Ursprung ist das Tretlager (x nach vorn, y nach oben, alles in cm). Die Zeichnung zeigt Lage und Abstände, kein Rahmenmodell.
const SEAT_ANGLE = (73.5 * Math.PI) / 180;
const W = 560, H = 380, SCALE = 3.2, OX = 262, OY = 282;
const px = (x) => OX + x * SCALE;
const py = (y) => OY - y * SCALE;
const fmt = (v) => String(Math.round(v * 10) / 10).replace(".", ",");

function pose(v, crankMm) {
  if (!v) return null;
  const h = v.saddle_height, back = v.saddle_setback, reach = v.saddle_to_bar, drop = v.drop;
  if ([h, back, reach, drop].some((n) => typeof n !== "number")) return null;
  const sy = h * Math.sin(SEAT_ANGLE);
  const tip = { x: back, y: sy };
  const clamp = { x: -h * Math.cos(SEAT_ANGLE), y: sy };
  const bar = { x: back + reach, y: sy - drop };
  const crank = typeof crankMm === "number" ? crankMm / 10 : 17.25;
  return { tip, clamp, bar, crank, sy };
}

function Rider({ p, cls }) {
  const d = (a, b) => `M${px(a.x)},${py(a.y)} L${px(b.x)},${py(b.y)}`;
  const top = { x: p.clamp.x + 1, y: p.sy + 1 };
  // Oberrohr-/Gabel-Andeutung: Sitzrohr, Steuerrohr in Richtung Lenker
  const head = { x: p.bar.x - 3, y: p.bar.y - 7 };
  return (
    <g className={cls}>
      <path d={d({ x: 0, y: 0 }, top)} />
      <path d={d(top, head)} />
      <path d={d({ x: 0, y: 0 }, head)} />
      <path d={`M${px(p.clamp.x - 2)},${py(p.sy + 1.2)} L${px(p.tip.x)},${py(p.sy + 1.2)}`} className="fit-dg-saddle" />
      <path d={d(head, p.bar)} />
      <circle cx={px(p.bar.x)} cy={py(p.bar.y)} r="5" className="fit-dg-dot" />
      <circle cx={px(p.tip.x)} cy={py(p.sy + 1.2)} r="4" className="fit-dg-dot" />
      <circle cx={px(0)} cy={py(0)} r={p.crank * SCALE} className="fit-dg-crank" />
    </g>
  );
}

export default function FitDiagram({ initial, optimized, crankMm }) {
  const a = pose(initial, crankMm), b = pose(optimized, crankMm);
  if (!a && !b) return <p className="muted small">Für die Zeichnung fehlen Sattelhöhe, Sattelversatz, Sattel bis Lenker und Überhöhung.</p>;
  const ref = b || a;
  const dims = [
    ["1", "Sattelhöhe", initial?.saddle_height, optimized?.saddle_height],
    ["2", "Sattelversatz", initial?.saddle_setback, optimized?.saddle_setback],
    ["3", "Sattelspitze bis Lenker", initial?.saddle_to_bar, optimized?.saddle_to_bar],
    ["4", "Überhöhung", initial?.drop, optimized?.drop],
  ];
  return (
    <figure className="fit-diagram">
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label="Schematische Seitenansicht mit Sattel- und Lenkerposition, vorher und optimiert">
        <line x1="0" y1={py(-26.5)} x2={W} y2={py(-26.5)} className="fit-dg-ground" />
        <g className="fit-dg-wheel">
          <circle cx={px(-42)} cy={py(7)} r={33.5 * SCALE} />
          <circle cx={px(56)} cy={py(7)} r={33.5 * SCALE} />
        </g>
        <line x1={px(0)} y1={py(-4)} x2={px(0)} y2={py(ref.sy + 6)} className="fit-dg-axis" />
        {a && <Rider p={a} cls="fit-dg-old" />}
        {b && <Rider p={b} cls="fit-dg-new" />}
        {ref && (
          <g className="fit-dg-badges">
            <Badge n="1" x={px(ref.clamp.x) - 16} y={py(ref.sy / 2)} />
            <Badge n="2" x={px((ref.tip.x) / 2)} y={py(ref.sy + 7)} />
            <Badge n="3" x={px((ref.tip.x + ref.bar.x) / 2)} y={py(ref.sy + 12)} />
            <Badge n="4" x={px(ref.bar.x) + 16} y={py((ref.sy + ref.bar.y) / 2)} />
          </g>
        )}
        <text x="10" y="16" className="fit-dg-note">schematisch, Tretlager = Nullpunkt</text>
      </svg>
      <figcaption>
        <div className="chips">
          {a && <span className="chip chip-mute"><span className="fit-key fit-key-old" />Ausgangsposition</span>}
          {b && <span className="chip chip-strong"><span className="fit-key fit-key-new" />Optimiert</span>}
        </div>
        <ul className="fit-dg-legend">
          {dims.filter(([, , x, y]) => x != null || y != null).map(([n, label, x, y]) => (
            <li key={n}><span className="fit-badge-n">{n}</span>{label}: {x != null ? fmt(x) : "–"} → <strong>{y != null ? fmt(y) : "–"}</strong> cm</li>
          ))}
        </ul>
      </figcaption>
    </figure>
  );
}

function Badge({ n, x, y }) {
  return (
    <g>
      <circle cx={x} cy={y} r="10" />
      <text x={x} y={y + 4} textAnchor="middle">{n}</text>
    </g>
  );
}
