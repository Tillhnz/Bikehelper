import { useMemo } from "react";

/**
 * Minimalistische Strichzeichnung eines Rads, gerechnet aus echten Rahmenmaßen (Radstand, Kettenstrebe,
 * Sitz- und Lenkwinkel, Stack und Reach), damit Rennrad, Gravel, Mountainbike und Stadtrad ihre eigenen Proportionen haben.
 * Die Linien zeichnen sich selbst, die Reifenbreite folgt dem Wert in mm, und mit `ride` drehen sich die Räder.
 *
 * type: road | gravel | mtb | other
 * tireMm: optional, bestimmt die Strichstärke der Reifen
 * ground: optional, asphalt | rough | hardpack | gravel | chunky
 */

const K = 0.1; // Pixel pro Millimeter
const VW = 210;
const GROUND_Y = 110;
const TIRE_TYPICAL = { road: 28, gravel: 40, mtb: 58, other: 38 };
const rad = (d) => (d * Math.PI) / 180;

// Maße in mm, Ursprung ist die Hinterachse
const SPECS = {
  road: { r: 340, wb: 990, cs: 410, drop: 70, sta: 73.5, st: 540, stack: 560, reach: 390, hta: 73, ht: 130, post: 100 },
  gravel: { r: 352, wb: 1050, cs: 428, drop: 68, sta: 73, st: 540, stack: 595, reach: 385, hta: 71, ht: 150, post: 90 },
  mtb: { r: 372, wb: 1200, cs: 436, drop: 35, sta: 76, st: 440, stack: 625, reach: 470, hta: 65, ht: 115, post: 190 },
  other: { r: 340, wb: 1090, cs: 455, drop: 60, sta: 70, st: 540, stack: 640, reach: 340, hta: 70, ht: 170, post: 110 },
};

function tireWidth(type, tireMm) {
  return Math.min(7, Math.max(2, (tireMm || TIRE_TYPICAL[type] || 30) * K));
}

function Wheel({ cx, cy, r, tw, knobs, order }) {
  const spokeLen = r - 11;
  return (
    <g>
      <circle className="ill-tire draw" style={{ "--i": order, strokeWidth: tw }} cx={cx} cy={cy} r={r - 3} pathLength="1" />
      {knobs && <circle className="ill-knobs" cx={cx} cy={cy} r={r + 1} pathLength="1" strokeDasharray="0.006 0.0115" />}
      <circle className="ill-rim" cx={cx} cy={cy} r={r - 9} />
      <g className="ill-spokes" style={{ transformOrigin: `${cx}px ${cy}px` }}>
        {[0, 45, 90, 135].map((a) => (
          <line
            key={a}
            x1={cx - spokeLen * Math.cos(rad(a))} y1={cy - spokeLen * Math.sin(rad(a))}
            x2={cx + spokeLen * Math.cos(rad(a))} y2={cy + spokeLen * Math.sin(rad(a))}
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


// ---------- Geometrie ----------

const f = (n) => n.toFixed(1);
const line = (...pts) => pts.map((p, i) => `${i ? "L" : "M"}${f(p[0])} ${f(p[1])}`).join(" ");

function frameFor(type) {
  const s = SPECS[type] ?? SPECS.other;
  const ox = (VW - (s.wb + 2 * s.r) * K) / 2 + s.r * K;
  const ay = GROUND_Y - s.r * K;
  const P = ([x, y]) => [ox + x * K, ay - y * K];
  const add = (a, b, t = 1) => [a[0] + b[0] * t, a[1] + b[1] * t];
  const R = [0, 0];
  const F = [s.wb, 0];
  const BB = [Math.sqrt(s.cs ** 2 - s.drop ** 2), -s.drop];
  const up = [-Math.cos(rad(s.sta)), Math.sin(rad(s.sta))]; // Sitzrohr nach oben
  const ST = add(BB, up, s.st);
  const HT = [BB[0] + s.reach, BB[1] + s.stack];
  const dn = [Math.cos(rad(s.hta)), -Math.sin(rad(s.hta))]; // Steuerrohr nach unten
  const HB = add(HT, dn, s.ht);
  const post = add(ST, up, s.post);
  return { s, P, add, R, F, BB, up, ST, HT, dn, HB, post, ox, ay };
}

function Bike({ type, tw }) {
  const g = frameFor(type);
  const { s, P, add, R, F, BB, up, ST, HT, dn, HB, post } = g;
  const px = (p) => P(p);
  const wheels = (
    <>
      <Wheel cx={P(R)[0]} cy={P(R)[1]} r={s.r * K} tw={tw} knobs={type === "mtb"} order={0} />
      <Wheel cx={P(F)[0]} cy={P(F)[1]} r={s.r * K} tw={tw} knobs={type === "mtb"} order={1} />
    </>
  );
  const cranks = (
    <>
      <Draw i={6} className="ill-part" width="2.4" d={`${line(px(BB), px(add(BB, [-58, -162])))} ${line(px(add(BB, [-100, -162])), px(add(BB, [0, -162])))}`} />
      <circle className="ill-rim" cx={px(BB)[0]} cy={px(BB)[1]} r="9" />
    </>
  );
  const saddle = (w0, w1) => <Draw i={4} className="ill-part" width="3" d={line(px([post[0] - w0, post[1] + 12]), px([post[0] + w1, post[1] + 12]))} />;
  const seatpost = <Draw i={3} className="ill-part" width="3" d={line(px(add(ST, up, -10)), px([post[0], post[1] + 12]))} />;

  if (type === "road" || type === "gravel") {
    const gravel = type === "gravel";
    const top = add(BB, up, s.st * 0.95);
    const stay = add(BB, up, s.st * 0.88);
    const S = [HT[0] + (gravel ? 92 : 98), HT[1] + (gravel ? 12 : 22)];
    const bar = gravel
      ? `M${px(S).map(f).join(" ")} C${px([S[0] + 95, S[1] + 5]).map(f).join(" ")} ${px([S[0] + 140, S[1] - 115]).map(f).join(" ")} ${px([S[0] + 60, S[1] - 150]).map(f).join(" ")}`
      : `M${px(S).map(f).join(" ")} C${px([S[0] + 85, S[1] + 8]).map(f).join(" ")} ${px([S[0] + 100, S[1] - 105]).map(f).join(" ")} ${px([S[0] + 25, S[1] - 142]).map(f).join(" ")}`;
    const frame = `${line(px(R), px(BB), px(stay), px(R))} ${line(px(BB), px(top), px(HT), px(HB), px(BB))} ${line(px(HB), px(F))}`;
    return (
      <>
        {wheels}
        <Draw i={2} width={gravel ? 3.2 : 3} d={frame} />
        {gravel && <path className="ill-bag" d={`${line(px(add(BB, up, s.st * 0.78)), px(add(HT, dn, 30)), px(add(BB, [95, 70])))} Z`} />}
        {seatpost}
        {saddle(75, 60)}
        <Draw i={5} className="ill-part" width="2.6" d={`${line(px(add(HT, dn, -25)), px(S))} ${bar}`} />
        {cranks}
      </>
    );
  }

  if (type === "mtb") {
    const top = add(BB, up, s.st * 0.97);
    const stay = add(BB, up, s.st * 0.85);
    const S = [HT[0] + 38, HT[1] + 32];
    const mid = add(HB, [F[0] - HB[0], F[1] - HB[1]], 0.48);
    const frame = `${line(px(R), px(BB), px(stay), px(R))} ${line(px(BB), px(top), px(HT), px(HB), px(BB))}`;
    return (
      <>
        {wheels}
        <Draw i={2} width="3.4" d={frame} />
        <Draw i={3} className="ill-part" width="2.4" d={line(px(mid), px(F))} />
        <Draw i={3} className="ill-part" width="5.6" d={line(px(add(HB, dn, -10)), px(mid))} />
        {seatpost}
        {saddle(85, 55)}
        <Draw i={5} className="ill-part" width="2.8" d={`${line(px(add(HT, dn, -20)), px(S))} ${line(px([S[0] + 35, S[1] + 5]), px([S[0] - 50, S[1] + 25]))} ${line(px([S[0] + 28, S[1] + 5]), px([S[0] + 75, S[1] - 40]))}`} />
        {cranks}
      </>
    );
  }

  // Stadtrad: offener Rahmen, aufrechter Lenker, Schutzbleche und Gepäckträger
  const low = add(BB, up, s.st * 0.5);
  const lowHead = add(HT, dn, s.ht * 0.78);
  const stay = add(BB, up, s.st * 0.9);
  const S = add(HT, dn, -150);
  const arc = (c) => {
    const a = [c[0] - 270, c[1] + 215];
    const b = [c[0] + 270, c[1] + 215];
    return `M${px(a).map(f).join(" ")} A${f((s.r + 40) * K)} ${f((s.r + 40) * K)} 0 0 1 ${px(b).map(f).join(" ")}`;
  };
  const frame = `${line(px(R), px(BB), px(stay), px(R))} ${line(px(BB), px(add(BB, up, s.st)))} ${line(px(HT), px(HB), px(BB))} ${line(px(lowHead), px(low))}`;
  const rackY = 400;
  return (
    <>
      {wheels}
      <Draw i={2} className="ill-part" width="1.8" d={`${arc(R)} ${arc(F)}`} />
      <Draw i={3} width="3" d={frame} />
      <Draw i={3} className="ill-part" width="2.2" d={`${line(px([-330, rackY]), px([120, rackY]))} ${line(px([100, rackY]), px(R))}`} />
      <rect className="ill-bag" x={px([-300, rackY + 190])[0]} y={px([-300, rackY + 190])[1]} width={f(380 * K)} height={f(180 * K)} rx="3" />
      {seatpost}
      {saddle(100, 70)}
      <Draw i={5} className="ill-part" width="2.6" d={`${line(px(add(HT, dn, -20)), px(S))} M${px([S[0] + 60, S[1] - 20]).map(f).join(" ")} Q${px([S[0] + 50, S[1] + 30]).map(f).join(" ")} ${px([S[0] - 110, S[1] + 15]).map(f).join(" ")}`} />
      {cranks}
    </>
  );
}

export default function BikeIllustration({ type = "road", tireMm, ground, ride = false, className = "", title }) {
  const tw = tireWidth(type, tireMm);
  return (
    <svg
      viewBox={`0 0 ${VW} 124`}
      className={`bike-ill ${ride ? "riding" : ""} ${className}`}
      role={title ? "img" : undefined}
      aria-label={title}
      aria-hidden={title ? undefined : true}
      focusable="false"
    >
      {ground ? <Ground surface={ground} moving={ride} /> : <path className="ill-ground-line" d={`M10 ${GROUND_Y} H${VW - 10}`} />}
      <g key={type} className="ill-bike">
        <Bike type={type} tw={tw} />
      </g>
    </svg>
  );
}
