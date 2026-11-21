// Zeichnen der erkannten Körperpunkte auf ein Canvas: Skelett, Hilfslinien und die gemessenen Winkel.
import { BONES, JOINTS, MIN_VIS } from "./fitPose.js";

const COL = { bone: "#6fd3c3", joint: "#ffffff", guide: "rgba(255,255,255,.55)", warn: "#f2b84b", text: "#ffffff", shadow: "rgba(0,0,0,.65)" };
const DEG = 180 / Math.PI;

const vis = (p) => (p?.visibility ?? 1) >= MIN_VIS;

/** Zeichnet Skelett und Winkel. `view` ist "side" oder "front". */
export function drawPose(canvas, video, lm, view = "side") {
  const ctx = canvas.getContext("2d");
  const w = video?.videoWidth || canvas.width || 640;
  const h = video?.videoHeight || canvas.height || 360;
  if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
  ctx.clearRect(0, 0, w, h);
  if (!lm) return;
  const P = (i) => ({ x: lm[i].x * w, y: lm[i].y * h, v: lm[i].visibility ?? 1 });
  const line = (a, b, col, width, dash) => {
    ctx.save(); ctx.setLineDash(dash || []); ctx.strokeStyle = col; ctx.lineWidth = width; ctx.lineCap = "round";
    ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke(); ctx.restore();
  };
  const scale = Math.max(1, w / 640);

  for (const [a, b] of BONES) {
    if (!vis(lm[a]) || !vis(lm[b])) continue;
    line(P(a), P(b), COL.bone, 3.5 * scale);
  }
  for (const i of [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]) {
    if (!vis(lm[i])) continue;
    const p = P(i);
    ctx.fillStyle = COL.joint; ctx.beginPath(); ctx.arc(p.x, p.y, 4 * scale, 0, 7); ctx.fill();
  }

  const k = pickSide(lm);
  if (view === "side" && k != null) {
    const sh = P(JOINTS.shoulder[k]), hi = P(JOINTS.hip[k]), kn = P(JOINTS.knee[k]), an = P(JOINTS.ankle[k]);
    const el = P(JOINTS.elbow[k]), wr = P(JOINTS.wrist[k]);
    line(hi, { x: hi.x + (sh.x > hi.x ? 1 : -1) * w * 0.25, y: hi.y }, COL.guide, 1.5 * scale, [7, 7]);  // Waagerechte für den Rückenwinkel
    arc(ctx, kn, hi, an, COL.bone, scale, "Knie");
    arc(ctx, hi, sh, kn, COL.guide, scale, "Hüfte");
    if (vis(lm[JOINTS.elbow[k]]) && vis(lm[JOINTS.wrist[k]])) arc(ctx, el, sh, wr, COL.guide, scale, "Ellbogen");
    const back = Math.atan2(Math.abs(hi.y - sh.y), Math.abs(hi.x - sh.x)) * DEG;
    label(ctx, { x: (hi.x + sh.x) / 2, y: (hi.y + sh.y) / 2 - 14 * scale }, `Rücken ${fmt(back)}°`, scale);
  }
  if (view === "front") {
    for (const side of [0, 1]) {
      const hi = P(JOINTS.hip[side]), kn = P(JOINTS.knee[side]), an = P(JOINTS.ankle[side]);
      if (!vis(lm[JOINTS.hip[side]]) || !vis(lm[JOINTS.ankle[side]])) continue;
      line(hi, an, COL.guide, 1.6 * scale, [6, 6]);                                   // Soll-Linie Hüfte zu Knöchel
      const t = (kn.y - hi.y) / ((an.y - hi.y) || 1);
      const on = { x: hi.x + t * (an.x - hi.x), y: kn.y };
      line(on, kn, COL.warn, 2.4 * scale);                                            // tatsächliche Abweichung
    }
    const hl = P(JOINTS.hip[0]), hr = P(JOINTS.hip[1]);
    if (vis(lm[23]) && vis(lm[24])) {
      line(hl, hr, COL.warn, 2 * scale);
      label(ctx, { x: (hl.x + hr.x) / 2, y: Math.min(hl.y, hr.y) - 12 * scale },
        `Becken ${fmt(Math.abs(Math.atan2(hr.y - hl.y, hr.x - hl.x) * DEG))}°`, scale);
    }
  }
}

function pickSide(lm) {
  const sum = (ids) => ids.reduce((s, i) => s + (lm[i]?.visibility ?? 0), 0);
  const l = sum([11, 23, 25, 27]), r = sum([12, 24, 26, 28]);
  if (Math.max(l, r) < 4 * MIN_VIS) return null;
  return l >= r ? 0 : 1;
}

const fmt = (x) => String(Math.round(x)).replace(".", ",");

/** Winkelbogen bei b zwischen den Strecken b-a und b-c, mit Zahl. */
function arc(ctx, b, a, c, col, scale, name) {
  const a1 = Math.atan2(a.y - b.y, a.x - b.x), a2 = Math.atan2(c.y - b.y, c.x - b.x);
  let d = a2 - a1;
  while (d > Math.PI) d -= 2 * Math.PI;
  while (d < -Math.PI) d += 2 * Math.PI;
  const r = 26 * scale;
  ctx.save();
  ctx.strokeStyle = col; ctx.lineWidth = 2 * scale;
  ctx.beginPath(); ctx.arc(b.x, b.y, r, a1, a1 + d, d < 0); ctx.stroke();
  ctx.restore();
  const mid = a1 + d / 2;
  label(ctx, { x: b.x + Math.cos(mid) * (r + 16 * scale), y: b.y + Math.sin(mid) * (r + 16 * scale) },
    `${name} ${fmt(Math.abs(d) * DEG)}°`, scale);
}

function label(ctx, p, text, scale) {
  ctx.save();
  ctx.font = `${Math.round(13 * scale)}px system-ui, sans-serif`;
  ctx.textAlign = "center"; ctx.textBaseline = "middle";
  ctx.lineWidth = 4 * scale; ctx.strokeStyle = COL.shadow; ctx.lineJoin = "round";
  ctx.strokeText(text, p.x, p.y); ctx.fillStyle = COL.text; ctx.fillText(text, p.x, p.y);
  ctx.restore();
}

/** Punkte eines Bildes aus dem gespeicherten Feld holen (x, y, Sichtbarkeit je Punkt). */
export function poseAt(times, poses, t) {
  if (!times?.length) return null;
  let lo = 0, hi = times.length - 1;
  while (lo < hi) { const m = (lo + hi) >> 1; if (times[m] < t) lo = m + 1; else hi = m; }
  const i = lo > 0 && Math.abs(times[lo - 1] - t) < Math.abs(times[lo] - t) ? lo - 1 : lo;
  const out = [];
  for (let j = 0; j < 33; j++) {
    const o = i * 99 + j * 3;
    out.push({ x: poses[o], y: poses[o + 1], visibility: poses[o + 2] });
  }
  return out;
}

/** Erkannte Bilder in ein kompaktes Feld packen. */
export function packPoses(frames) {
  const times = new Float32Array(frames.length);
  const poses = new Float32Array(frames.length * 99);
  frames.forEach((f, i) => {
    times[i] = f.t;
    for (let j = 0; j < 33; j++) {
      const p = f.lm[j] || { x: 0, y: 0 };
      poses[i * 99 + j * 3] = p.x; poses[i * 99 + j * 3 + 1] = p.y; poses[i * 99 + j * 3 + 2] = p.visibility ?? 0;
    }
  });
  return { times, poses };
}
