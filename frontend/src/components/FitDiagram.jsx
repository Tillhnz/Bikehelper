import { BAR_PROFILE, CHAINRING_R, COG_R, RIM_R, WHEEL_R, frame, pose, v } from "./fitGeometry.js";

const norm = (a, b) => { const d = Math.hypot(b.x - a.x, b.y - a.y) || 1; return v((b.x - a.x) / d, (b.y - a.y) / d); };
const perp = (u) => v(-u.y, u.x);
const move = (p, u, d) => v(p.x + u.x * d, p.y + u.y * d);

// Maßstäbliche Seitenansicht: eine Zeichnungseinheit ist ein Zentimeter, y wird für SVG gespiegelt.
const P = (p) => `${round(p.x)},${round(-p.y)}`;
const round = (n) => Math.round(n * 100) / 100;
const line = (a, b) => `M${P(a)} L${P(b)}`;
const poly = (pts, close) => `M${pts.map(P).join(" L")}${close ? " Z" : ""}`;
const shift = (pts, d) => pts.map((p) => v(p.x + d.x, p.y + d.y));
const fmt = (n) => String(Math.round(n * 10) / 10).replace(".", ",");

function Wheel({ c }) {
  const spokes = Array.from({ length: 12 }, (_, i) => {
    const a = (i / 12) * Math.PI * 2 + 0.26;
    return line(v(c.x + Math.cos(a) * 2, c.y + Math.sin(a) * 2), v(c.x + Math.cos(a) * RIM_R, c.y + Math.sin(a) * RIM_R));
  });
  return (
    <g className="fd-wheel">
      <circle className="fd-tire" cx={round(c.x)} cy={round(-c.y)} r={WHEEL_R} />
      <circle className="fd-rim" cx={round(c.x)} cy={round(-c.y)} r={RIM_R} />
      {spokes.map((d, i) => <path key={i} className="fd-spoke" d={d} />)}
      <circle className="fd-hub" cx={round(c.x)} cy={round(-c.y)} r="1.6" />
    </g>
  );
}

function Frame({ fr, crank }) {
  const bb = v(0, 0);
  const chainTop = v(CHAINRING_R * 0.1, CHAINRING_R);
  const cogTop = v(fr.rearAxle.x, fr.rearAxle.y + COG_R);
  const pedal = v(Math.cos(-0.38) * crank, Math.sin(-0.38) * crank);
  return (
    <g>
      <g className="fd-chain">
        <path d={line(chainTop, cogTop)} />
        <path d={line(v(0, -CHAINRING_R), v(fr.rearAxle.x, fr.rearAxle.y - COG_R))} />
      </g>
      <g className="fd-frame">
        <path d={line(bb, fr.seatTop)} />
        <path d={line(fr.seatTop, fr.ttFront)} />
        <path d={line(bb, fr.headBottom)} />
        <path d={line(bb, fr.rearAxle)} />
        <path d={line(fr.seatTop, fr.rearAxle)} />
        <path className="fd-head" d={line(fr.headTop, fr.headBottom)} />
        <path className="fd-fork" d={`M${P(fr.headBottom)} Q${P(fr.fork)} ${P(fr.frontAxle)}`} />
      </g>
      <g className="fd-drive">
        <circle cx="0" cy="0" r={CHAINRING_R} />
        <circle cx={round(fr.rearAxle.x)} cy={round(-fr.rearAxle.y)} r={COG_R} />
        <path className="fd-crank" d={line(bb, pedal)} />
        <path className="fd-pedal" d={line(v(pedal.x - 4, pedal.y - 1.1), v(pedal.x + 4, pedal.y - 1.1))} />
        <circle className="fd-bb" cx="0" cy="0" r="1.8" />
      </g>
    </g>
  );
}

function Position({ p, fr, cls }) {
  const bar = shift(BAR_PROFILE, p.clamp);
  return (
    <g className={cls}>
      <path d={line(fr.seatTop, p.post)} />
      <path d={line(p.post, v(p.shell[3].x, p.shell[3].y))} />
      <path className="fd-saddle" d={poly(p.shell)} />
      <path d={line(fr.headTop, p.steerTop)} />
      <path className="fd-stem" d={line(p.stemStart, p.clamp)} />
      <path className="fd-bar" d={poly(bar)} />
      <circle className="fd-pt" cx={round(p.hood.x)} cy={round(-p.hood.y)} r="1.5" />
      <circle className="fd-pt" cx={round(p.tip.x)} cy={round(-p.tip.y)} r="1.3" />
    </g>
  );
}

// Maßlinie: Hilfslinien an den gemessenen Punkten, Maßlinie um `off` versetzt, Marke und Wert in der Mitte
function Dim({ n, from, to, off, value, lab = v(0, 5.6) }) {
  const a = v(from.x + off.x, from.y + off.y), b = v(to.x + off.x, to.y + off.y);
  const u = norm(a, b), q = perp(u);
  const m = v((a.x + b.x) / 2, (a.y + b.y) / 2);
  const t = (p) => line(move(p, q, -1.5), move(p, q, 1.5));
  const at = v(m.x + lab.x, m.y + lab.y);
  return (
    <g className="fd-dim">
      <path className="fd-ext" d={line(from, a)} />
      <path className="fd-ext" d={line(to, b)} />
      <path d={line(a, b)} />
      <path d={t(a)} /><path d={t(b)} />
      {value != null && <text x={round(at.x)} y={round(-at.y) + 1.3} textAnchor="middle" className="fd-val">{fmt(value)} cm</text>}
      <circle className="fd-badge" cx={round(m.x)} cy={round(-m.y)} r="3.3" />
      <text x={round(m.x)} y={round(-m.y) + 1.4} textAnchor="middle" className="fd-badge-t">{n}</text>
    </g>
  );
}

export default function FitDiagram({ initial, optimized, crankMm, frameSize }) {
  const fr = frame(parseFloat(String(frameSize ?? "").replace(",", ".")));
  const a = pose(initial, fr), b = pose(optimized, fr);
  if (!a && !b) return <p className="muted small">Für die Zeichnung fehlen Sattelhöhe, Sattelversatz, Sattelspitze bis Lenker und Überhöhung.</p>;
  const ref = b || a, rv = b ? optimized : initial;
  const crank = typeof crankMm === "number" ? crankMm / 10 : 17.25;
  const top = Math.max(ref.top.y, a?.top.y ?? 0) + 6;
  const x0 = fr.rearAxle.x - WHEEL_R - 13, x1 = fr.frontAxle.x + WHEEL_R + 14;
  const y1 = top + 22, y0 = fr.ground - 4;
  const seatU = perp(norm(v(0, 0), ref.top));

  return (
    <figure className="fit-diagram">
      <svg viewBox={`${round(x0)} ${round(-y1)} ${round(x1 - x0)} ${round(y1 - y0)}`} role="img"
        aria-label={`Maßstäbliche Seitenansicht: Sattel auf ${fmt(ref.h)} Zentimeter Höhe, Überhöhung ${fmt(ref.drop)} Zentimeter`}>
        <path className="fd-ground" d={line(v(x0, fr.ground), v(x1, fr.ground))} />
        <Wheel c={fr.rearAxle} />
        <Wheel c={fr.frontAxle} />
        <Frame fr={fr} crank={crank} />
        <path className="fd-axis" d={line(v(0, fr.ground + 1), v(0, top + 4))} />
        {a && b && <Position p={a} fr={fr} cls="fd-old" />}
        {b ? <Position p={b} fr={fr} cls="fd-new" /> : <Position p={a} fr={fr} cls="fd-new" />}
        <Dim n="1" from={v(0, 0)} to={ref.top} off={v(seatU.x * 10, seatU.y * 10)} value={ref.h} lab={v(-11.5, -1)} />
        <Dim n="2" from={v(0, 0)} to={v(ref.tip.x, 0)} off={v(0, top + 4)} value={Math.abs(ref.back)} />
        <Dim n="3" from={ref.tip} to={v(ref.hood.x, ref.tip.y)} off={v(0, top + 13 - ref.tip.y)} value={ref.reach} />
        <Dim n="4" from={ref.top} to={v(ref.top.x, ref.hood.y)} off={v(ref.hood.x - ref.top.x + 11, 0)} value={ref.drop} lab={v(9, 0)} />
      </svg>
      <figcaption>
        <div className="chips">
          {a && b && <span className="chip chip-mute"><span className="fit-key fit-key-old" />Ausgangsposition</span>}
          <span className="chip chip-strong"><span className="fit-key fit-key-new" />{b ? "Optimiert" : "Eingetragene Position"}</span>
          {typeof rv?.bar_width === "number" && <span className="chip">Lenker {fmt(rv.bar_width / 10)} cm breit</span>}
          {typeof rv?.stem_length === "number" && <span className="chip">Vorbau {rv.stem_length} mm{typeof rv.stem_angle === "number" ? `, ${fmt(rv.stem_angle)}°` : ""}</span>}
        </div>
        <ul className="fit-dg-legend">
          {[["1", "Sattelhöhe", initial?.saddle_height, optimized?.saddle_height],
            ["2", "Sattelversatz hinter dem Tretlager", initial?.saddle_setback, optimized?.saddle_setback],
            ["3", "Sattelspitze bis Auflage", initial?.saddle_to_bar, optimized?.saddle_to_bar],
            ["4", "Überhöhung", initial?.drop, optimized?.drop]]
            .filter(([, , x, y]) => x != null || y != null).map(([n, label, x, y]) => (
              <li key={n}><span className="fit-badge-n">{n}</span>{label}: {x != null ? fmt(Math.abs(x)) : "–"}{y != null ? <> → <strong>{fmt(Math.abs(y))}</strong></> : ""} cm</li>
            ))}
        </ul>
        <p className="muted small">
          Maßstäblich in Zentimetern. Sattel, Lenker und Vorbau folgen deinen Werten, Rahmen und Räder sind Richtwerte für
          {frameSize ? ` Rahmengröße ${frameSize}` : " eine mittlere Rahmengröße"}. Positive Sattelneigung heißt: Spitze zeigt nach unten.
        </p>
      </figcaption>
    </figure>
  );
}
