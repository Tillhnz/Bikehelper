// Schematische Seitenansicht eines Rennrads (Rahmen nach üblicher Geometrie Größe 56 bis 58) mit den Maßen aus dem Maßblatt.
// Ausgangsposition gestrichelt, optimierte Position farbig. Ursprung = Tretlager, alle Maße in cm, 1 cm = 1 Zeichnungseinheit.
// Rahmen, Räder und Lenkervorbau sind feste Annäherungen; nur Sattel und Lenker-/Auflegerpunkt folgen den eingetragenen Werten.
const SEAT_ANGLE = 73.5, HEAD_ANGLE = 73;
const rad = (d) => (d * Math.PI) / 180;
const fmt = (v) => String(Math.round(v * 10) / 10).replace(".", ",");

// Feste Rahmengeometrie
const WHEEL_R = 33.5, BB_DROP = 7, CHAINSTAY = 41, WHEELBASE = 99;
const REAR = { x: -Math.sqrt(CHAINSTAY ** 2 - BB_DROP ** 2), y: BB_DROP };
const FRONT = { x: REAR.x + WHEELBASE, y: BB_DROP };
const SEAT_TUBE_TOP = { x: -54 * Math.cos(rad(SEAT_ANGLE)), y: 54 * Math.sin(rad(SEAT_ANGLE)) };
const HEAD_TOP = { x: 39.5, y: 57 };
const HEAD_BOTTOM = { x: HEAD_TOP.x + 15 * Math.cos(rad(HEAD_ANGLE)), y: HEAD_TOP.y - 15 * Math.sin(rad(HEAD_ANGLE)) };
const STEM_CLAMP = { x: HEAD_TOP.x - 3.5 * Math.cos(rad(HEAD_ANGLE)), y: HEAD_TOP.y + 3.5 * Math.sin(rad(HEAD_ANGLE)) };

// Sichtbereich in cm (y nach oben)
const X0 = -86, X1 = 100, Y0 = -30, Y1 = 104;
const VB = `${X0} ${-Y1} ${X1 - X0} ${Y1 - Y0}`;
const P = (p) => `${p.x},${-p.y}`;
const line = (a, b) => `M${P(a)} L${P(b)}`;

function pose(v) {
  if (!v) return null;
  const h = v.saddle_height, back = v.saddle_setback, reach = v.saddle_to_bar, drop = v.drop;
  if ([h, back, reach, drop].some((n) => typeof n !== "number")) return null;
  const top = { x: -h * Math.cos(rad(SEAT_ANGLE)), y: h * Math.sin(rad(SEAT_ANGLE)) }; // Sattelmitte oben
  const tip = { x: back, y: top.y + 0.6 };
  const tail = { x: back - 27, y: top.y + 0.6 };
  const bar = { x: back + reach, y: top.y - drop };
  return { top, tip, tail, bar };
}

function Rider({ p, cls }) {
  const post = { x: SEAT_TUBE_TOP.x, y: SEAT_TUBE_TOP.y };
  return (
    <g className={cls}>
      <path d={line(post, p.top)} />
      <path d={`M${P(p.tail)} L${P(p.tip)}`} className="fit-dg-saddle" />
      <path d={line(STEM_CLAMP, p.bar)} />
      <circle cx={p.bar.x} cy={-p.bar.y} r="1.6" className="fit-dg-dot" />
      <circle cx={p.tip.x} cy={-p.tip.y} r="1.4" className="fit-dg-dot" />
    </g>
  );
}

// Maßlinie mit Endstrichen und Zahl
function Dim({ n, a, b, label, off = { x: 0, y: 0 } }) {
  const m = { x: (a.x + b.x) / 2 + off.x, y: (a.y + b.y) / 2 + off.y };
  return (
    <g className="fit-dg-dim">
      <path d={line(a, b)} />
      <circle cx={m.x} cy={-m.y} r="3.4" className="fit-dg-badge" />
      <text x={m.x} y={-m.y + 1.3} textAnchor="middle" className="fit-dg-badge-t">{n}</text>
      {label && <text x={m.x} y={-m.y - 5.5} textAnchor="middle" className="fit-dg-val">{label}</text>}
    </g>
  );
}

export default function FitDiagram({ initial, optimized, crankMm }) {
  const a = pose(initial), b = pose(optimized);
  if (!a && !b) return <p className="muted small">Für die Zeichnung fehlen Sattelhöhe, Sattelversatz, Sattel bis Lenker und Überhöhung.</p>;
  const ref = b || a, rv = b ? optimized : initial;
  const crank = typeof crankMm === "number" ? crankMm / 10 : 17.25;
  const lift = ref.top.y + 9;
  const dims = [
    ["1", "Sattelhöhe", initial?.saddle_height, optimized?.saddle_height],
    ["2", "Sattelversatz", initial?.saddle_setback, optimized?.saddle_setback],
    ["3", "Sattelspitze bis Lenker oder Armauflage", initial?.saddle_to_bar, optimized?.saddle_to_bar],
    ["4", "Überhöhung", initial?.drop, optimized?.drop],
  ];
  return (
    <figure className="fit-diagram">
      <svg viewBox={VB} role="img" aria-label="Schematische Seitenansicht eines Rennrads mit Sattel- und Lenkerposition, vorher und optimiert">
        <line x1={X0} y1={-Y0 - 3.5} x2={X1} y2={-Y0 - 3.5} className="fit-dg-ground" />
        <g className="fit-dg-wheel">
          <circle cx={REAR.x} cy={-REAR.y} r={WHEEL_R} />
          <circle cx={FRONT.x} cy={-FRONT.y} r={WHEEL_R} />
        </g>
        <g className="fit-dg-frame">
          <path d={line({ x: 0, y: 0 }, SEAT_TUBE_TOP)} />
          <path d={line(SEAT_TUBE_TOP, HEAD_TOP)} />
          <path d={line({ x: 0, y: 0 }, HEAD_BOTTOM)} />
          <path d={line(HEAD_TOP, HEAD_BOTTOM)} className="fit-dg-head" />
          <path d={line(HEAD_BOTTOM, FRONT)} />
          <path d={line({ x: 0, y: 0 }, REAR)} />
          <path d={line(SEAT_TUBE_TOP, REAR)} />
          <path d={line(HEAD_TOP, STEM_CLAMP)} />
          <path d={`M0,0 L0,${crank}`} className="fit-dg-crank" />
          <circle cx="0" cy="0" r="1.6" className="fit-dg-bb" />
        </g>
        <line x1="0" y1={-Y1 + 8} x2="0" y2="4" className="fit-dg-axis" />
        {a && <Rider p={a} cls="fit-dg-old" />}
        {b && <Rider p={b} cls="fit-dg-new" />}
        <g>
          <Dim n="1" a={{ x: 0, y: 0 }} b={ref.top} off={{ x: -6, y: 0 }} />
          <Dim n="2" a={{ x: 0, y: lift }} b={{ x: ref.tip.x, y: lift }} />
          <Dim n="3" a={{ x: ref.tip.x, y: lift + 6 }} b={{ x: ref.bar.x, y: lift + 6 }} />
          <Dim n="4" a={{ x: ref.bar.x + 7, y: ref.top.y }} b={{ x: ref.bar.x + 7, y: ref.bar.y }} />
        </g>
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
        <p className="muted small">Schematisch: Rahmen, Räder und Vorbau sind Richtwerte (Rennrad, Größe um 57), nur Sattel und Lenker-/Auflegerpunkt folgen deinen Maßen. Die Zeichnung ersetzt kein Messen am Rad.</p>
      </figcaption>
    </figure>
  );
}
