import { useRef, useState } from "react";
import { BAR_PROFILE, CHAINRING_R, CRANK_Q, HUB_HALF, RIM_R, WHEEL_R, circlePts, frame, pose, v } from "./fitGeometry.js";

// Drehbares Drahtmodell. Die Punkte stehen in Zentimetern im Raum (x vorn, y oben, z rechts),
// projiziert wird von Hand: erst drehen, dann perspektivisch verkleinern. Dafür braucht es keine 3D-Bibliothek.
const VIEWS = [
  ["Schräg", -38, 14], ["Seite", 0, 0], ["Vorn", -88, 10], ["Oben", -30, 52],
];
const CENTER = v(16, 38, 0);
const DIST = 340, FOV = 300;
const rad = (d) => (d * Math.PI) / 180;

function project(p, yaw, pitch) {
  const x0 = p.x - CENTER.x, y0 = p.y - CENTER.y, z0 = (p.z || 0) - CENTER.z;
  const cy = Math.cos(rad(yaw)), sy = Math.sin(rad(yaw));
  const x1 = x0 * cy + z0 * sy, z1 = -x0 * sy + z0 * cy;
  const cp = Math.cos(rad(pitch)), sp = Math.sin(rad(pitch));
  const y2 = y0 * cp - z1 * sp, z2 = y0 * sp + z1 * cp;
  const s = FOV / Math.max(60, DIST - z2);
  return { x: x1 * s, y: -y2 * s, z: z2, s };
}

const atZ = (pts, z) => pts.map((p) => v(p.x, p.y, z));

/** Teile des Modells: Punktzüge mit Stilklasse. */
function build(fr, p, cls) {
  const parts = [];
  const add = (pts, c = cls, w = 1, closed = false) => parts.push({ pts, cls: c, w, closed });
  const bar = BAR_PROFILE.map((q) => v(q.x + p.clamp.x, q.y + p.clamp.y, 0));

  // Lenker: Oberlenker nach außen, dann der Bogen auf beiden Seiten
  for (const side of [1, -1]) {
    const w = p.halfBar * side;
    add([v(p.clamp.x, p.clamp.y, 0), v(p.clamp.x + 0.7, p.clamp.y, w * 0.6), v(p.clamp.x + 0.4, p.clamp.y, w)], cls, 1.3);
    add(atZ(bar, w), cls, 1.3);
  }
  // Sattel: Umriss von oben und Seitenlinie
  const shell = p.shell;
  const half = [0.5, 1.1, 2.3, 4.6, 6.6, 7.1, 5.2];
  const ring = [...shell.map((q, i) => v(q.x, q.y, half[i])), ...shell.map((q, i) => v(q.x, q.y, -half[i])).reverse()];
  add(ring, cls, 1, true);
  add(shell, cls, 1);
  add([fr.seatTop, p.post, v(shell[3].x, shell[3].y, 0)], cls, 1.4);
  // Vorbau und Gabelschaft
  add([fr.headTop, p.steerTop], cls, 1.2);
  add([p.stemStart, p.clamp], cls, 1.6);
  return parts;
}

function bikeParts(fr, crank) {
  const parts = [];
  const add = (pts, cls, w = 1, closed = false) => parts.push({ pts, cls, w, closed });
  for (const c of [fr.rearAxle, fr.frontAxle]) {
    add(circlePts(c, WHEEL_R), "m3-tire", 1.4, true);
    add(circlePts(c, RIM_R, 40), "m3-rim", .7, true);
    add([v(c.x, c.y, -HUB_HALF), v(c.x, c.y, HUB_HALF)], "m3-rim", 1.2);
    for (let i = 0; i < 10; i++) {
      const a = (i / 10) * Math.PI * 2 + 0.3;
      const rim = v(c.x + Math.cos(a) * RIM_R, c.y + Math.sin(a) * RIM_R);
      add([v(c.x, c.y, (i % 2 ? 1 : -1) * 2.6), rim], "m3-spoke", .4);
    }
  }
  const bb = v(0, 0);
  add([bb, fr.seatTop], "m3-frame", 1.6);
  add([fr.seatTop, fr.ttFront], "m3-frame", 1.5);
  add([bb, fr.headBottom], "m3-frame", 1.8);
  add([fr.headTop, fr.headBottom], "m3-frame", 2.4);
  for (const side of [1, -1]) {
    add([v(0, 0, 1.6 * side), v(fr.rearAxle.x, fr.rearAxle.y, HUB_HALF * side)], "m3-frame", 1.2);
    add([v(fr.seatTop.x, fr.seatTop.y, 0.9 * side), v(fr.rearAxle.x, fr.rearAxle.y, HUB_HALF * side)], "m3-frame", 1.1);
    add([v(fr.headBottom.x, fr.headBottom.y, 0.9 * side), v(fr.fork.x, fr.fork.y, 3 * side),
         v(fr.frontAxle.x, fr.frontAxle.y, HUB_HALF * side)], "m3-frame", 1.2);
  }
  add(circlePts(v(0, 0, CRANK_Q * 0.4), CHAINRING_R, 36), "m3-ring", .7, true);
  for (const side of [1, -1]) {
    const a = side > 0 ? -0.38 : Math.PI - 0.38;
    const pedal = v(Math.cos(a) * crank, Math.sin(a) * crank, CRANK_Q * side);
    add([v(0, 0, CRANK_Q * side * 0.55), pedal], "m3-crank", 1.4);
    add([v(pedal.x - 4, pedal.y - 1.2, pedal.z), v(pedal.x + 4, pedal.y - 1.2, pedal.z)], "m3-crank", 1.8);
  }
  return parts;
}

function groundParts(fr, x0, x1) {
  const parts = [];
  const y = fr.ground;
  for (let x = Math.ceil(x0 / 20) * 20; x <= x1; x += 20) parts.push({ pts: [v(x, y, -30), v(x, y, 30)], cls: "m3-grid", w: .4, loose: true });
  for (let z = -30; z <= 30; z += 15) parts.push({ pts: [v(x0, y, z), v(x1, y, z)], cls: "m3-grid", w: .4, loose: true });
  return parts;
}

export default function FitModel3D({ initial, optimized, crankMm, frameSize, startYaw = -38, startPitch = 14 }) {
  const fr = frame(parseFloat(String(frameSize ?? "").replace(",", ".")));
  const a = pose(initial, fr), b = pose(optimized, fr);
  const [yaw, setYaw] = useState(startYaw);
  const [pitch, setPitch] = useState(startPitch);
  const drag = useRef(null);
  if (!a && !b) return null;

  const crank = typeof crankMm === "number" ? crankMm / 10 : 17.25;
  const parts = [
    ...groundParts(fr, fr.rearAxle.x - WHEEL_R, fr.frontAxle.x + WHEEL_R),
    ...bikeParts(fr, crank),
    ...(a && b ? build(fr, a, "m3-old") : []),
    ...build(fr, b || a, "m3-new"),
  ];
  const box = { x0: Infinity, x1: -Infinity, y0: Infinity, y1: -Infinity };
  const drawn = parts.map((part) => {
    const pts = part.pts.map((q) => project(q, yaw, pitch));
    const depth = pts.reduce((s, q) => s + q.z, 0) / pts.length;
    const sc = pts.reduce((s, q) => s + q.s, 0) / pts.length / (FOV / DIST);
    if (!part.loose) for (const q of pts) {   // das Bodenraster bestimmt den Ausschnitt nicht mit
      box.x0 = Math.min(box.x0, q.x); box.x1 = Math.max(box.x1, q.x);
      box.y0 = Math.min(box.y0, q.y); box.y1 = Math.max(box.y1, q.y);
    }
    const d = `M${pts.map((q) => `${Math.round(q.x * 100) / 100},${Math.round(q.y * 100) / 100}`).join(" L")}${part.closed ? " Z" : ""}`;
    return { d, cls: part.cls, w: Math.max(.3, part.w * sc), depth };
  }).sort((x, y) => x.depth - y.depth);

  // Bildausschnitt folgt dem Modell, damit jede Ansicht den Rahmen ausfüllt
  const ASPECT = 1.6, PAD = 1.07;
  let w = Math.max(40, (box.x1 - box.x0) * PAD), h = Math.max(30, (box.y1 - box.y0) * PAD);
  if (w / h < ASPECT) w = h * ASPECT; else h = w / ASPECT;
  const cx = (box.x0 + box.x1) / 2, cyy = (box.y0 + box.y1) / 2;
  const viewBox = [cx - w / 2, cyy - h / 2, w, h].map((n) => Math.round(n * 10) / 10).join(" ");

  function down(e) {
    drag.current = { x: e.clientX, y: e.clientY, yaw, pitch };
    e.currentTarget.setPointerCapture?.(e.pointerId);
  }
  function move(e) {
    const d = drag.current;
    if (!d) return;
    setYaw(d.yaw - (e.clientX - d.x) * 0.45);
    setPitch(Math.max(-25, Math.min(75, d.pitch + (e.clientY - d.y) * 0.3)));
  }
  function key(e) {
    const step = e.shiftKey ? 15 : 5;
    if (e.key === "ArrowLeft") setYaw((y) => y + step);
    else if (e.key === "ArrowRight") setYaw((y) => y - step);
    else if (e.key === "ArrowUp") setPitch((p) => Math.min(75, p + step));
    else if (e.key === "ArrowDown") setPitch((p) => Math.max(-25, p - step));
    else return;
    e.preventDefault();
  }

  return (
    <div className="fit-model">
      <svg viewBox={viewBox} className="m3" role="img" tabIndex="0"
        aria-label="Drehbares Modell des Rads mit der eingetragenen Sitzposition. Mit den Pfeiltasten drehen."
        onPointerDown={down} onPointerMove={move} onPointerUp={() => { drag.current = null; }}
        onPointerCancel={() => { drag.current = null; }} onKeyDown={key}>
        {drawn.map((p, i) => <path key={i} className={p.cls} d={p.d} strokeWidth={Math.round(p.w * 100) / 100} />)}
      </svg>
      <div className="m3-bar">
        <span className="muted small">Ziehen oder Pfeiltasten zum Drehen</span>
        <span className="m3-views">
          {VIEWS.map(([label, y, p]) => (
            <button key={label} type="button" className={`btn small${Math.round(yaw) === y && Math.round(pitch) === p ? " primary" : ""}`}
              onClick={() => { setYaw(y); setPitch(p); }}>{label}</button>
          ))}
        </span>
      </div>
    </div>
  );
}
