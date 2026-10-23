import { useMemo } from "react";

/**
 * Minimalistische Strichzeichnung eines Rads. Die Linien zeichnen sich beim Erscheinen selbst,
 * die Reifenbreite folgt dem Wert in mm, und mit `ride` drehen sich die Räder über einen bewegten Untergrund.
 *
 * type: road | gravel | mtb | other
 * tireMm: optional, bestimmt die Strichstärke der Reifen
 * ground: optional, asphalt | rough | hardpack | gravel | chunky (zeigt den Untergrund unter den Rädern)
 */

const TIRE_DEFAULT = { road: 2.6, gravel: 4.2, mtb: 5.8, other: 3.6 };
const GROUND_Y = 121;

function tireWidth(type, tireMm) {
  if (!tireMm) return TIRE_DEFAULT[type] ?? 3;
  return Math.min(7, Math.max(1.8, tireMm * 0.094));
}

function Wheel({ cx, cy, r, tw, knobs, order }) {
  const spokeLen = r - 11;
  return (
    <g>
      <circle className="ill-tire draw" style={{ "--i": order, strokeWidth: tw }} cx={cx} cy={cy} r={r - 3} pathLength="1" />
      {knobs && (
        <circle className="ill-knobs" cx={cx} cy={cy} r={r + 1} pathLength="1" strokeDasharray="0.006 0.0115" />
      )}
      <circle className="ill-rim" cx={cx} cy={cy} r={r - 9} />
      <g className="ill-spokes" style={{ transformOrigin: `${cx}px ${cy}px` }}>
        {[0, 45, 90, 135].map((a) => (
          <line
            key={a}
            x1={cx - spokeLen * Math.cos((a * Math.PI) / 180)} y1={cy - spokeLen * Math.sin((a * Math.PI) / 180)}
            x2={cx + spokeLen * Math.cos((a * Math.PI) / 180)} y2={cy + spokeLen * Math.sin((a * Math.PI) / 180)}
          />
        ))}
      </g>
      <circle className="ill-hub" cx={cx} cy={cy} r="2.4" />
    </g>
  );
}

function Draw({ d, i, className = "ill-frame", width }) {
  return <path className={`${className} draw`} style={{ "--i": i }} d={d} pathLength="1" strokeWidth={width} />;
}

/** Deterministische Pseudo-Zufallszahlen, damit der Untergrund bei jedem Rendern gleich aussieht. */
function rng(seed) {
  let s = seed;
  return () => {
    s = (s * 16807) % 2147483647;
    return s / 2147483647;
  };
}

const PERIOD = 48;

function groundPattern(surface) {
  const r = rng(7);
  const dots = [];
  if (surface === "rough") {
    let d = `M0 ${GROUND_Y}`;
    for (let x = 0; x < PERIOD; x += 8) d += ` q2 ${x % 16 === 0 ? -2.2 : 2.2} 4 0 t4 0`;
    return { line: d };
  }
  if (surface === "hardpack") {
    return { line: `M0 ${GROUND_Y} h${PERIOD}`, dash: `M2 ${GROUND_Y + 5} h7 M20 ${GROUND_Y + 4} h5 M33 ${GROUND_Y + 6} h9` };
  }
  if (surface === "gravel") {
    for (let i = 0; i < 11; i++) dots.push({ x: r() * PERIOD, y: GROUND_Y + 1.5 + r() * 6, r: 0.8 + r() * 0.9 });
    return { line: `M0 ${GROUND_Y} h${PERIOD}`, dots };
  }
  if (surface === "chunky") {
    for (let i = 0; i < 6; i++) dots.push({ x: 4 + (i * PERIOD) / 6 + r() * 3, y: GROUND_Y + 1 + r() * 4, r: 1.8 + r() * 1.8 });
    return { line: `M0 ${GROUND_Y} h${PERIOD}`, dots };
  }
  return { line: `M0 ${GROUND_Y} h${PERIOD}` };
}

function Ground({ surface, moving }) {
  const pattern = useMemo(() => groundPattern(surface), [surface]);
  const tiles = Array.from({ length: 7 }, (_, i) => i);
  return (
    <g className={`ill-ground ${moving ? "moving" : ""}`} key={surface}>
      <g className="ill-ground-run">
        {tiles.map((t) => (
          <g key={t} transform={`translate(${t * PERIOD - PERIOD} 0)`}>
            <path className="ill-ground-line" d={pattern.line} />
            {pattern.dash && <path className="ill-ground-dash" d={pattern.dash} />}
            {pattern.dots?.map((d, i) => <circle key={i} className="ill-ground-dot" cx={d.x} cy={d.y} r={d.r} />)}
          </g>
        ))}
      </g>
    </g>
  );
}

function Road({ tw }) {
  return (
    <>
      <Wheel cx={52} cy={86} r={33} tw={tw} order={0} />
      <Wheel cx={188} cy={86} r={33} tw={tw} order={1} />
      <Draw i={2} d="M52 86 L106 90 L93 52 Z M93 52 L162 50 L168 64 L106 90 M168 64 L188 86" width="3" />
      <Draw i={3} className="ill-part" d="M93 52 L91 44 M82 43 L101 43" width="3" />
      <Draw i={4} className="ill-part" d="M162 50 L164 44 L174 44 Q185 44 185 54 Q185 62 177 63" width="2.6" />
      <Draw i={5} className="ill-part" d="M106 90 L113 100 M109 100 L117 100" width="2.4" />
      <circle className="ill-rim" cx="106" cy="90" r="8" />
    </>
  );
}

function Gravel({ tw }) {
  return (
    <>
      <Wheel cx={50} cy={86} r={34} tw={tw} order={0} />
      <Wheel cx={190} cy={86} r={34} tw={tw} order={1} />
      <Draw i={2} d="M50 86 L107 91 L94 52 Z M94 52 L163 50 L169 64 L107 91 M169 64 L190 86" width="3.2" />
      <path className="ill-bag" d="M101 56 L152 54 L112 80 Z" />
      <Draw i={3} className="ill-part" d="M94 52 L92 44 M83 43 L102 43" width="3" />
      <Draw i={4} className="ill-part" d="M163 50 L165 44 L173 44 Q188 41 190 52 Q191 61 183 64" width="2.6" />
      <Draw i={5} className="ill-part" d="M107 91 L114 101 M110 101 L118 101" width="2.4" />
      <circle className="ill-rim" cx="107" cy="91" r="8" />
    </>
  );
}

function Mtb({ tw }) {
  return (
    <>
      <Wheel cx={48} cy={83} r={36} tw={tw} knobs order={0} />
      <Wheel cx={192} cy={83} r={36} tw={tw} knobs order={1} />
      <Draw i={2} d="M48 83 L106 89 L86 54 Z M86 54 L158 46 L165 61 L106 89 M165 61 L192 83" width="3.4" />
      <Draw i={3} className="ill-part" d="M161 53 L172 67" width="5.5" />
      <Draw i={4} className="ill-part" d="M86 54 L85 46 M76 45 L95 45" width="3" />
      <Draw i={5} className="ill-part" d="M158 46 L160 38 M150 36 L170 35" width="2.8" />
      <Draw i={6} className="ill-part" d="M106 89 L112 99 M108 99 L116 99" width="2.4" />
      <circle className="ill-rim" cx="106" cy="89" r="8" />
    </>
  );
}

function City({ tw }) {
  const arc = (cx, cy) => `M${cx - 30} ${cy - 24} A38 38 0 0 1 ${cx + 30} ${cy - 24}`;
  return (
    <>
      <Wheel cx={54} cy={86} r={33} tw={tw} order={0} />
      <Wheel cx={186} cy={86} r={33} tw={tw} order={1} />
      <Draw i={2} className="ill-part" d={`${arc(54, 86)} ${arc(186, 86)}`} width="1.8" />
      <Draw i={3} d="M54 86 L104 90 L88 48 Z M88 48 L158 52 L166 68 L104 90 M166 68 L186 86" width="3" />
      <Draw i={4} className="ill-part" d="M88 48 L86 40 M78 39 L98 39" width="3.2" />
      <Draw i={5} className="ill-part" d="M158 52 L156 36 M170 36 Q158 29 146 34" width="2.6" />
      <Draw i={6} className="ill-part" d="M30 58 H76 M76 58 L58 84" width="2.2" />
      <rect className="ill-bag" x="34" y="44" width="38" height="14" rx="3" />
      <Draw i={7} className="ill-part" d="M104 90 L111 100 M107 100 L115 100" width="2.4" />
      <circle className="ill-rim" cx="104" cy="90" r="8" />
    </>
  );
}

const DRAW = { road: Road, gravel: Gravel, mtb: Mtb, other: City };

export default function BikeIllustration({ type = "road", tireMm, ground, ride = false, className = "", title }) {
  const Shape = DRAW[type] ?? DRAW.other;
  const tw = tireWidth(type, tireMm);
  return (
    <svg
      viewBox="0 0 240 134"
      className={`bike-ill ${ride ? "riding" : ""} ${className}`}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {ground ? <Ground surface={ground} moving={ride} /> : <path className="ill-ground-line" d={`M10 ${GROUND_Y} H230`} />}
      <g key={type} className="ill-bike">
        <Shape tw={tw} />
      </g>
    </svg>
  );
}
