import { useCallback, useEffect, useRef, useState } from "react";
import { api, fmtDate } from "../api.js";
import { confirmDialog, toast } from "./feedback.jsx";

// Kameraanalyse der Sitzposition. Alles läuft im Browser: Die Videobilder verlassen den Rechner nicht, gespeichert werden nur Winkelwerte.
// Pose-Erkennung: MediaPipe Pose Landmarker. Bibliothek, wasm und Modell liegen unter /mediapipe/ (werden beim Bauen des Frontends angelegt).
const CAPTURE_S = 15;
const L = { shoulder: 11, elbow: 13, wrist: 15, hip: 23, knee: 25, ankle: 27 };
const R = { shoulder: 12, elbow: 14, wrist: 16, hip: 24, knee: 26, ankle: 28 };
const BONES = [[11, 13], [13, 15], [11, 23], [23, 25], [25, 27], [12, 14], [14, 16], [12, 24], [24, 26], [26, 28], [11, 12], [23, 24]];

// Typische Bereiche: Orientierung, keine Vorgabe. Jede Person und jedes Rad ist anders.
const RANGES = {
  knee_bdc: { label: "Kniewinkel unten (Pedal im tiefsten Punkt)", lo: 140, hi: 155, unit: "°",
    low: "Das Knie ist unten stark gebeugt, der Sattel könnte etwas höher stehen.", high: "Das Bein ist unten fast durchgestreckt, der Sattel könnte etwas niedriger stehen." },
  back: { label: "Rückenwinkel zur Waagerechten", lo: 35, hi: 50, unit: "°",
    low: "Sehr gestreckte, sportliche Haltung.", high: "Aufrechte Haltung, entspannt, aber mit mehr Luftwiderstand." },
  elbow: { label: "Ellbogenwinkel", lo: 145, hi: 170, unit: "°",
    low: "Die Arme sind stark angewinkelt, der Lenker könnte zu weit entfernt oder zu tief sein.", high: "Die Arme sind fast durchgestreckt, Schultern und Handgelenke werden stärker belastet." },
  arm_torso: { label: "Winkel Arm zu Oberkörper", lo: 75, hi: 95, unit: "°",
    low: "Eher kurze Reichweite zum Lenker.", high: "Eher lange Reichweite zum Lenker." },
};

const sub = (a, b) => ({ x: a.x - b.x, y: a.y - b.y });
function angle(a, b, c) { // Winkel bei b in Grad
  const u = sub(a, b), v = sub(c, b);
  const n = Math.hypot(u.x, u.y) * Math.hypot(v.x, v.y);
  if (!n) return null;
  return (Math.acos(Math.max(-1, Math.min(1, (u.x * v.x + u.y * v.y) / n))) * 180) / Math.PI;
}
const median = (xs) => { const s = xs.filter((x) => x != null).sort((a, b) => a - b); return s.length ? s[Math.floor(s.length / 2)] : null; };
const r1 = (v) => (v == null ? null : Math.round(v * 10) / 10);
const fmt = (v) => String(r1(v)).replace(".", ",");

function pickSide(lm) { // die der Kamera zugewandte Körperseite (höhere Sichtbarkeit)
  const vis = (m) => ["shoulder", "hip", "knee", "ankle"].reduce((s, k) => s + (lm[m[k]]?.visibility ?? 0), 0);
  const m = vis(L) >= vis(R) ? L : R;
  return Object.fromEntries(Object.entries(m).map(([k, i]) => [k, lm[i]]));
}

function sideSample(lm) {
  const p = pickSide(lm);
  const need = ["shoulder", "hip", "knee", "ankle"];
  if (need.some((k) => !p[k] || (p[k].visibility ?? 0) < 0.5)) return null;
  return {
    ankleY: p.ankle.y,
    knee: angle(p.hip, p.knee, p.ankle),
    hip: angle(p.shoulder, p.hip, p.knee),
    back: (Math.atan2(Math.abs(p.hip.y - p.shoulder.y), Math.abs(p.hip.x - p.shoulder.x)) * 180) / Math.PI,
    elbow: p.elbow && p.wrist && (p.elbow.visibility ?? 0) > 0.4 ? angle(p.shoulder, p.elbow, p.wrist) : null,
    armTorso: p.elbow && (p.elbow.visibility ?? 0) > 0.4 ? angle(p.hip, p.shoulder, p.elbow) : null,
  };
}

function frontSample(lm) {
  const ok = [23, 24, 25, 26, 27, 28].every((i) => (lm[i]?.visibility ?? 0) >= 0.5);
  if (!ok) return null;
  const dev = (h, k, a) => { // seitliche Abweichung des Knies von der Linie Hüfte-Knöchel, in % der Beinlänge
    const t = (lm[k].y - lm[h].y) / ((lm[a].y - lm[h].y) || 1);
    const lineX = lm[h].x + t * (lm[a].x - lm[h].x);
    const leg = Math.hypot(lm[a].x - lm[h].x, lm[a].y - lm[h].y) || 1;
    return ((lm[k].x - lineX) / leg) * 100;
  };
  const tilt = (Math.atan2(lm[24].y - lm[23].y, lm[24].x - lm[23].x) * 180) / Math.PI;
  return { devL: dev(23, 25, 27), devR: dev(24, 26, 28), tilt };
}

function summarizeSide(s) {
  if (s.length < 20) return null;
  const ys = s.map((x) => x.ankleY);
  const lo = Math.min(...ys), hi = Math.max(...ys);
  const bottom = s.filter((x) => x.ankleY >= hi - (hi - lo) * 0.1 && x.knee != null); // Fuß am tiefsten
  const top = s.filter((x) => x.ankleY <= lo + (hi - lo) * 0.1 && x.knee != null);
  if (hi - lo < 0.03 || bottom.length < 3) return { error: "Es war kaum Tretbewegung zu sehen. Bitte die ganze Pedalumdrehung im Bild lassen und die Kamera ruhig halten." };
  return {
    knee_bdc: r1(median(bottom.map((x) => x.knee))), knee_min: r1(median(top.map((x) => x.knee))),
    hip: r1(median(s.map((x) => x.hip))), back: r1(median(s.map((x) => x.back))),
    elbow: r1(median(s.map((x) => x.elbow))), arm_torso: r1(median(s.map((x) => x.armTorso))), frames: s.length,
  };
}

function summarizeFront(s) {
  if (s.length < 20) return null;
  const tilts = s.map((x) => x.tilt);
  return { knee_dev_l: r1(median(s.map((x) => x.devL))), knee_dev_r: r1(median(s.map((x) => x.devR))),
    pelvis_tilt: r1(Math.abs(median(tilts))), pelvis_range: r1(Math.max(...tilts) - Math.min(...tilts)), frames: s.length };
}

let landmarkerLib = null;
async function makeLandmarker() {
  if (!landmarkerLib) {
    const lib = await import("@mediapipe/tasks-vision");
    landmarkerLib = { lib, fileset: await lib.FilesetResolver.forVisionTasks("/mediapipe/wasm") };
  }
  const { lib, fileset } = landmarkerLib;
  const make = (delegate) => lib.PoseLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: "/mediapipe/pose_landmarker_lite.task", delegate }, runningMode: "VIDEO", numPoses: 1,
  });
  try { return await make("GPU"); } catch { return make("CPU"); }
}

function draw(canvas, video, lm) {
  const ctx = canvas.getContext("2d");
  canvas.width = video.videoWidth || 640; canvas.height = video.videoHeight || 480;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  if (!lm) return;
  ctx.lineWidth = 3; ctx.strokeStyle = "#5fd3c0"; ctx.fillStyle = "#ffffff";
  for (const [a, b] of BONES) {
    if ((lm[a].visibility ?? 0) < 0.5 || (lm[b].visibility ?? 0) < 0.5) continue;
    ctx.beginPath(); ctx.moveTo(lm[a].x * canvas.width, lm[a].y * canvas.height); ctx.lineTo(lm[b].x * canvas.width, lm[b].y * canvas.height); ctx.stroke();
  }
  for (const i of [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]) {
    if ((lm[i].visibility ?? 0) < 0.5) continue;
    ctx.beginPath(); ctx.arc(lm[i].x * canvas.width, lm[i].y * canvas.height, 4, 0, 7); ctx.fill();
  }
}

function Stage({ title, devices, deviceId, setDeviceId, optional, videoRef, canvasRef, active }) {
  return (
    <div className="cam-stage">
      <label>{title}
        <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)} disabled={active}>
          {optional && <option value="">nicht verwenden</option>}
          {devices.map((d, i) => <option key={d.deviceId} value={d.deviceId}>{d.label || `Kamera ${i + 1}`}</option>)}
        </select>
      </label>
      {deviceId && (
        <div className="cam-view">
          <video ref={videoRef} muted playsInline />
          <canvas ref={canvasRef} />
        </div>
      )}
    </div>
  );
}

function Result({ metrics }) {
  const side = metrics.side, front = metrics.front;
  const key = { knee_bdc: "knee_bdc", back: "back", elbow: "elbow", arm_torso: "arm_torso" };
  return (
    <div className="cam-result">
      {side && (
        <div className="fit-table" role="table" aria-label="Seitenansicht">
          <div className="fit-row fit-row-h cam-row" role="row"><span>Seitenansicht</span><span>Messwert</span><span>Typisch</span></div>
          {Object.entries(key).map(([k, m]) => {
            const r = RANGES[k]; const v = side[m];
            if (v == null) return null;
            const state = v < r.lo ? "low" : v > r.hi ? "high" : "ok";
            return (
              <div key={k} className="fit-row cam-row" role="row">
                <span>{r.label}</span>
                <span><span className={`chip ${state === "ok" ? "chip-strong" : "chip-wet"}`}>{fmt(v)} {r.unit}</span></span>
                <span className="muted small">{r.lo} bis {r.hi} {r.unit}</span>
                {state !== "ok" && <span className="cam-hint small">{r[state]}</span>}
              </div>
            );
          })}
          {side.hip != null && <div className="fit-row cam-row"><span>Hüftwinkel</span><span><span className="chip">{fmt(side.hip)} °</span></span><span className="muted small">Orientierung</span></div>}
        </div>
      )}
      {front && (
        <div className="fit-table" role="table" aria-label="Frontansicht">
          <div className="fit-row fit-row-h cam-row" role="row"><span>Frontansicht</span><span>Messwert</span><span>Hinweis</span></div>
          <div className="fit-row cam-row"><span>Knie seitlich (links / rechts)</span>
            <span><span className="chip">{fmt(front.knee_dev_l)} % / {fmt(front.knee_dev_r)} %</span></span>
            <span className="muted small">Abweichung von der Linie Hüfte–Knöchel, in % der Beinlänge. Gut ist nah an 0 und auf beiden Seiten ähnlich.</span></div>
          <div className="fit-row cam-row"><span>Becken, Neigung</span>
            <span><span className="chip">{fmt(front.pelvis_tilt)} °</span><span className="chip chip-mute">Schwankung {fmt(front.pelvis_range)} °</span></span>
            <span className="muted small">Eine große Schwankung kann auf einen zu hohen Sattel hindeuten.</span></div>
        </div>
      )}
      <p className="muted small">Das sind Orientierungswerte aus einem Kamerabild, keine Diagnose. Kamera auf Hüfthöhe, Abstand 2 bis 3 m, die Person im Ganzen im Bild und gleichmäßig treten. Für feine Einstellungen bleibt der Fitter die bessere Quelle.</p>
    </div>
  );
}

export default function FitCamera({ bike }) {
  const [state, setState] = useState("idle"); // idle | loading | ready | running | error
  const [error, setError] = useState("");
  const [devices, setDevices] = useState([]);
  const [sideId, setSideId] = useState("");
  const [frontId, setFrontId] = useState("");
  const [left, setLeft] = useState(CAPTURE_S);
  const [result, setResult] = useState(null);
  const [history, setHistory] = useState([]);
  const [saving, setSaving] = useState(false);
  const sideVideo = useRef(null), frontVideo = useRef(null), sideCanvas = useRef(null), frontCanvas = useRef(null);
  const streams = useRef([]);
  const stop = useRef(false);

  const loadHistory = useCallback(() => api.get(`/bikes/${bike.id}/fit-captures`).then(setHistory).catch(() => {}), [bike.id]);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const release = useCallback(() => {
    stop.current = true;
    streams.current.forEach((s) => s.getTracks().forEach((t) => t.stop()));
    streams.current = [];
  }, []);
  useEffect(() => release, [release]);

  const secure = typeof window !== "undefined" && window.isSecureContext && navigator.mediaDevices?.getUserMedia;

  async function open() {
    setError(""); setState("loading");
    try {
      const probe = await navigator.mediaDevices.getUserMedia({ video: true }); // erst die Erlaubnis, danach haben die Kameras Namen
      probe.getTracks().forEach((t) => t.stop());
      const cams = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
      if (!cams.length) throw new Error("Es wurde keine Kamera gefunden.");
      setDevices(cams); setSideId(cams[0].deviceId); setFrontId(""); setState("ready");
    } catch (e) {
      setState("error");
      setError(e?.name === "NotAllowedError" ? "Der Zugriff auf die Kamera wurde verweigert. Erlaube ihn in der Adressleiste des Browsers und versuche es noch einmal."
        : e?.message || "Die Kamera lässt sich nicht öffnen.");
    }
  }

  const live = state === "ready" || state === "running";
  useEffect(() => { // Vorschau starten, sobald eine Kamera gewählt ist
    if (!live) return undefined;
    let dead = false;
    const started = [];
    (async () => {
      for (const [id, ref] of [[sideId, sideVideo], [frontId, frontVideo]]) {
        if (!id || !ref.current) continue;
        try {
          const s = await navigator.mediaDevices.getUserMedia({ video: { deviceId: { exact: id }, width: { ideal: 1280 }, height: { ideal: 720 } } });
          if (dead) { s.getTracks().forEach((t) => t.stop()); return; }
          ref.current.srcObject = s; await ref.current.play().catch(() => {});
          started.push(s);
        } catch { setError("Eine Kamera ist nicht verfügbar. Vielleicht nutzt sie gerade ein anderes Programm."); }
      }
      streams.current = started;
    })();
    return () => { dead = true; started.forEach((s) => s.getTracks().forEach((t) => t.stop())); };
  }, [live, sideId, frontId]);

  async function capture() {
    if (!sideId || sideId === frontId) { setError("Wähle für die Seitenansicht eine Kamera, und für die Front eine andere."); return; }
    setError(""); setResult(null); setState("running"); stop.current = false;
    let sideLm = null, frontLm = null;
    try {
      sideLm = await makeLandmarker();
      if (frontId) frontLm = await makeLandmarker();
    } catch {
      setState("ready");
      setError("Die Bewegungserkennung konnte nicht geladen werden. Fehlen die Dateien unter /mediapipe/? Dann das Frontend neu bauen (./install.sh update).");
      return;
    }
    const sideS = [], frontS = [];
    const t0 = performance.now();
    let lastSide = -1, lastFront = -1;
    const tick = () => {
      if (stop.current) return;
      const elapsed = (performance.now() - t0) / 1000;
      setLeft(Math.max(0, Math.ceil(CAPTURE_S - elapsed)));
      const sv = sideVideo.current, fv = frontVideo.current;
      if (sv && sv.readyState >= 2 && sv.currentTime !== lastSide) {
        lastSide = sv.currentTime;
        const lm = sideLm.detectForVideo(sv, performance.now()).landmarks?.[0];
        if (sideCanvas.current) draw(sideCanvas.current, sv, lm);
        const x = lm && sideSample(lm); if (x) sideS.push(x);
      }
      if (frontLm && fv && fv.readyState >= 2 && fv.currentTime !== lastFront) {
        lastFront = fv.currentTime;
        const lm = frontLm.detectForVideo(fv, performance.now()).landmarks?.[0];
        if (frontCanvas.current) draw(frontCanvas.current, fv, lm);
        const x = lm && frontSample(lm); if (x) frontS.push(x);
      }
      if (elapsed >= CAPTURE_S) return finish();
      requestAnimationFrame(tick);
    };
    const finish = () => {
      sideLm.close?.(); frontLm?.close?.();
      const side = summarizeSide(sideS), front = frontLm ? summarizeFront(frontS) : null;
      setState("ready"); setLeft(CAPTURE_S);
      if (side?.error) { setError(side.error); return; }
      if (!side && !front) { setError("Es wurde keine Person erkannt. Mehr Licht, ganze Person im Bild und der Kamera die Seite zuwenden."); return; }
      setResult({ ...(side ? { side } : {}), ...(front ? { front } : {}) });
    };
    requestAnimationFrame(tick);
  }

  async function save() {
    setSaving(true);
    try { await api.post(`/bikes/${bike.id}/fit-captures`, { metrics: result }); toast("Messung gespeichert."); setResult(null); await loadHistory(); }
    catch (e) { setError(e.message); } finally { setSaving(false); }
  }
  async function remove(c) {
    if (!await confirmDialog(`Die Messung vom ${fmtDate(c.at)} löschen?`)) return;
    await api.del(`/fit-captures/${c.id}`); await loadHistory();
  }
  function close() { release(); setState("idle"); setResult(null); setError(""); }

  const active = state === "running";
  return (
    <div className="cam-panel">
      <h3>Kameraanalyse <span className="chip chip-mute">Beta</span></h3>
      <p className="muted small">Die Webcam sieht dich von der Seite auf dem Rad (Rolle oder Trainer), eine zweite Kamera optional von vorn. Die Auswertung läuft nur in deinem Browser, es wird kein Bild hochgeladen oder gespeichert, nur die Winkelwerte.</p>
      {!secure && <p className="error small">Der Browser erlaubt Kameras nur über HTTPS (oder localhost). Öffne BikeHelper über die https-Adresse.</p>}
      {secure && state === "idle" && <button className="btn" onClick={open}>Kameras suchen</button>}
      {state === "loading" && <p className="muted small">Kameras werden gesucht. Bitte den Zugriff im Browser erlauben.</p>}
      {(state === "ready" || state === "running") && (
        <>
          <div className="cam-grid">
            <Stage title="Seitenansicht" devices={devices} deviceId={sideId} setDeviceId={setSideId} videoRef={sideVideo} canvasRef={sideCanvas} active={active} />
            <Stage title="Frontansicht (optional)" devices={devices.filter((d) => d.deviceId !== sideId)} deviceId={frontId} setDeviceId={setFrontId} optional videoRef={frontVideo} canvasRef={frontCanvas} active={active} />
          </div>
          <div className="actions">
            <button className="btn primary" onClick={capture} disabled={active}>{active ? `Messe … noch ${left} s` : `Messung starten (${CAPTURE_S} s)`}</button>
            <button className="btn" onClick={close} disabled={active}>Kameras schließen</button>
          </div>
          {!active && <p className="muted small">Trete gleichmäßig in deiner normalen Haltung. Die Messung nutzt die ganze Pedalumdrehung.</p>}
        </>
      )}
      {error && <p className="error small" role="alert">{error}</p>}
      {result && (
        <>
          <Result metrics={result} />
          <div className="actions">
            <button className="btn primary" onClick={save} disabled={saving}>Messung speichern</button>
            <button className="btn" onClick={() => setResult(null)}>Verwerfen</button>
          </div>
        </>
      )}
      {history.length > 0 && (
        <details className="cam-history">
          <summary>Gespeicherte Messungen ({history.length})</summary>
          {history.map((c) => (
            <div key={c.id} className="cam-hist-item">
              <div className="fit-card-top"><strong>{fmtDate(c.at)}</strong>
                <span className="rule-actions"><button className="link small danger" onClick={() => remove(c)}>Löschen</button></span></div>
              <Result metrics={c.metrics} />
            </div>
          ))}
        </details>
      )}
    </div>
  );
}
