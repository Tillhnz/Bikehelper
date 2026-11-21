// Prüfung der Messlogik mit erzeugten Körperpunkten: bekannte Geometrie rein, gemessene Winkel raus.
import { framePose, analyseSide, analyseFront, angle } from "../src/components/fitPose.js";

const D = 180 / Math.PI;
const THIGH = 42, SHANK = 43, CRANK = 17.25, ANKLE_UP = 12;
const ang = (a, b, c) => angle({x:a[0],y:a[1]}, {x:b[0],y:b[1]}, {x:c[0],y:c[1]});

// Knie per inverser Kinematik (nach vorn ausgelenkt)
function knee(hip, ankle) {
  const dx = ankle[0]-hip[0], dy = ankle[1]-hip[1], d = Math.hypot(dx,dy);
  if (d > THIGH+SHANK) return null;
  const a = (THIGH*THIGH - SHANK*SHANK + d*d)/(2*d), h = Math.sqrt(Math.max(0,THIGH*THIGH-a*a));
  const mx = hip[0]+a*dx/d, my = hip[1]+a*dy/d;
  return [mx + h*(dy/d), my - h*(-dx/d)];      // Seite so gewählt, dass das Knie vorn liegt
}

function makeClip({ hipY = 74, hipX = -20, backDeg = 40, elbowDeg = 155, rpm = 85, secs = 12, fps = 30, aspect = 16/9, noPedal = false, breakAspect = false }) {
  const frames = [], truth = [];
  const shoulder = [hipX + Math.cos(backDeg/D)*55, hipY + Math.sin(backDeg/D)*55];
  for (let i = 0; i < secs*fps; i++) {
    const t = i/fps;
    const a = noPedal ? -Math.PI/2 : (t*rpm/60)*2*Math.PI;
    const pedal = [Math.cos(a)*CRANK, Math.sin(a)*CRANK];
    const ankle = [pedal[0], pedal[1]+ANKLE_UP];
    const kn = knee([hipX,hipY], ankle);
    if (!kn) throw new Error("Bein zu kurz bei t="+t);
    truth.push({ knee: ang([hipX,hipY], kn, ankle) });
    const el = [shoulder[0]+24, shoulder[1]-14], hand = [shoulder[0]+46, shoulder[1]-12];
    truth[truth.length-1].elbow = ang(shoulder, el, hand);
    truth[truth.length-1].hip = ang(shoulder, [hipX,hipY], kn);
    const pts = {};
    const put = (i0, p, v=1) => { pts[i0] = {x:p[0], y:p[1], visibility:v}; };
    put(11, shoulder); put(12, shoulder);
    put(13, el); put(14, el);
    put(15, hand); put(16, hand);
    put(23, [hipX,hipY]); put(24, [hipX,hipY]);
    put(25, kn); put(26, kn);
    put(27, ankle); put(28, ankle);
    put(29, [ankle[0]-6, ankle[1]-2]); put(30, [ankle[0]-6, ankle[1]-2]);
    put(31, [ankle[0]+8, ankle[1]-4]); put(32, [ankle[0]+8, ankle[1]-4]);
    // in Bildkoordinaten: Ausschnitt 220 cm breit, 220/aspect hoch, y nach unten
    const W = 220, H = W/aspect, X0 = -90, YTOP = 130;
    const lm = Array.from({length:33}, (_,k) => {
      const p = pts[k] || {x:0,y:0,visibility:0};
      return { x: (p.x - X0)/W, y: (YTOP - p.y)/H, z: 0, visibility: p.visibility };
    });
    frames.push({ t, pose: framePose(lm, breakAspect ? 1 : aspect) });
  }
  return { frames, truth };
}

let fail = 0;
const check = (name, got, want, tol) => {
  const ok = got != null && Math.abs(got-want) <= tol;
  if (!ok) fail++;
  console.log(`${ok?"ok  ":"FAIL"} ${name}: ${got} (erwartet ${Math.round(want*10)/10} ±${tol})`);
};

for (const aspect of [16/9, 4/3, 1]) {
  const { frames, truth } = makeClip({ aspect });
  const r = analyseSide(frames);
  if (r.error) { console.log("FAIL analyse:", r.error); fail++; continue; }
  const kn = truth.map(x=>x.knee);
  check(`knee_bdc bei Seitenverhältnis ${Math.round(aspect*100)/100}`, r.knee_bdc, Math.max(...kn), 1.5);
  check(`knee_min  bei Seitenverhältnis ${Math.round(aspect*100)/100}`, r.knee_min, Math.min(...kn), 2.5);
  check(`Ellbogen`, r.elbow, truth[0].elbow, 1);
  check(`Trittfrequenz`, r.cadence, 85, 3);
  check(`Rücken`, r.back, 40, 1);
  check(`Ansicht erkannt als Seite`, r.view.looks === "side" ? 1 : 0, 1, 0);
}
// Ohne Korrektur des Seitenverhältnisses wäre der Wert deutlich daneben:
{
  // dasselbe Video, aber die Korrektur des Seitenverhältnisses absichtlich weggelassen
  const { frames, truth } = makeClip({ aspect: 16/9 });
  const { frames: bad } = makeClip({ aspect: 16/9, breakAspect: true });
  console.log(`Hinweis: ohne Korrektur des Seitenverhältnisses käme knee_bdc auf ${analyseSide(bad).knee_bdc}° statt ${analyseSide(frames).knee_bdc}° (wahr: ${Math.round(Math.max(...truth.map(x=>x.knee))*10)/10}°)`);
}
// Sattel zu hoch / zu tief verschiebt den Wert in die erwartete Richtung
{
  const a = analyseSide(makeClip({ hipY: 73 }).frames).knee_bdc;
  const b = analyseSide(makeClip({ hipY: 75 }).frames).knee_bdc;
  check("2 cm höhere Hüfte je cm Kniewinkel", (b-a)/2, 5.5, 1.5);
}
// Kein Treten => klare Fehlermeldung statt Zahlen
{
  const r = analyseSide(makeClip({ noPedal: true }).frames);
  check("stehendes Bein liefert Fehlermeldung", r.error ? 1 : 0, 1, 0);
}
console.log(fail ? `\n${fail} Prüfungen fehlgeschlagen` : "\nalle Prüfungen bestanden");
process.exit(fail ? 1 : 0);
