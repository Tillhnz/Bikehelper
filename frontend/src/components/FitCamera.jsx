import { useCallback, useEffect, useRef, useState } from "react";
import { api, fmtDateTime } from "../api.js";
import { confirmDialog, toast } from "./feedback.jsx";
import { FRONT_RANGES, RANGES, advise, analyseFront, analyseSide, framePose } from "./fitPose.js";
import { drawPose, packPoses, poseAt } from "./fitDraw.js";
import { MAX_PER_BIKE, deleteClip, listClips, loadClip, saveClip } from "./fitClips.js";

// Kameraanalyse der Sitzposition. Aufnahme, Auswertung und Abspielen laufen im Browser:
// Die Bilder verlassen den Rechner nicht. Zum Server gehen nur Zahlen, und das nur auf Knopfdruck.
// Die Erkennung (MediaPipe Pose Landmarker) liegt unter /mediapipe/ und wird beim Bauen des Frontends abgelegt.
const CAPTURE_S = 15;
const STEP_FPS = 20;              // so dicht wird die Aufnahme nachher abgetastet

const VIEWS = {
  side: {
    name: "Seitenansicht", short: "Seite",
    how: "Kamera seitlich neben das Rad, im rechten Winkel, auf Hüfthöhe, 2 bis 3 m entfernt. Die ganze Person von Kopf bis Pedal muss ins Bild.",
    gives: "Kniewinkel, Hüfte, Rücken, Ellbogen",
  },
  front: {
    name: "Frontansicht", short: "Front",
    how: "Kamera mittig vor das Rad, auf Hüfthöhe. Hüfte, Knie und Füße müssen ins Bild, am besten in enger Kleidung.",
    gives: "Kniespur, Beckenschaukeln, Schulterschiefe",
  },
};

// Nur diese Zahlen gehen zum Server (passend zur Prüfung im Backend)
const SAVE_KEYS = {
  side: ["knee_bdc", "knee_min", "knee_spread", "hip_min", "back", "elbow", "arm_torso", "ankle", "cadence", "cycles", "frames"],
  front: ["knee_dev_l", "knee_dev_r", "knee_sway_l", "knee_sway_r", "pelvis_tilt", "pelvis_range", "shoulder_tilt", "frames"],
};
const forServer = (res) => Object.fromEntries(Object.entries(res)
  .flatMap(([view, m]) => (!m || m.error ? [] : [[view, Object.fromEntries(SAVE_KEYS[view].filter((k) => typeof m[k] === "number").map((k) => [k, m[k]]))]])));

const fmt = (x) => (x == null ? "–" : String(Math.round(x * 10) / 10).replace(".", ","));
const pct = (n) => `${Math.round(n * 100)} %`;

// ---------- Erkennung ----------

let visionLib = null;
async function makeLandmarker() {
  if (!visionLib) {
    const lib = await import("@mediapipe/tasks-vision");
    visionLib = { lib, fileset: await lib.FilesetResolver.forVisionTasks("/mediapipe/wasm") };
  }
  const { lib, fileset } = visionLib;
  const make = (delegate) => lib.PoseLandmarker.createFromOptions(fileset, {
    baseOptions: { modelAssetPath: "/mediapipe/pose_landmarker_lite.task", delegate },
    runningMode: "VIDEO", numPoses: 1, minPoseDetectionConfidence: 0.5, minTrackingConfidence: 0.5,
  });
  try { return await make("GPU"); } catch { return make("CPU"); }
}

const seek = (video, t) => new Promise((res) => {
  let fired = false;
  const go = () => { if (!fired) { fired = true; video.removeEventListener("seeked", go); res(); } };
  video.addEventListener("seeked", go);
  video.currentTime = t;
  setTimeout(go, 400);
});

/** Aufnahme Bild für Bild auswerten. Gibt die Messwerte und die Punkte je Bild zurück. */
async function analyseClip(blob, view, onProgress) {
  const landmarker = await makeLandmarker();
  const url = URL.createObjectURL(blob);
  const video = document.createElement("video");
  video.src = url; video.muted = true; video.playsInline = true; video.preload = "auto";
  try {
    await new Promise((res, rej) => {
      video.onloadeddata = () => res();
      video.onerror = () => rej(new Error("Die Aufnahme lässt sich nicht lesen."));
      setTimeout(() => rej(new Error("Die Aufnahme lässt sich nicht lesen.")), 15000);
    });
    let dur = video.duration;
    if (!Number.isFinite(dur) || dur <= 0) {                     // manche Browser melden die Länge erst am Ende
      await seek(video, 3600);
      dur = Number.isFinite(video.duration) ? video.duration : CAPTURE_S;
    }
    const aspect = (video.videoWidth || 16) / (video.videoHeight || 9);
    const frames = [];
    let stamp = 0;
    for (let t = 0; t < dur - 0.02; t += 1 / STEP_FPS) {
      await seek(video, t);
      const found = landmarker.detectForVideo(video, (stamp += 50));
      const lm = found.landmarks?.[0];
      if (lm) frames.push({ t, lm, pose: framePose(lm, aspect) });
      onProgress?.(Math.min(1, t / dur));
    }
    const metrics = view === "side" ? analyseSide(frames) : analyseFront(frames);
    return { metrics, aspect, duration: dur, ...packPoses(frames) };
  } finally {
    landmarker.close?.();
    URL.revokeObjectURL(url);
  }
}

// ---------- Anzeige ----------

function Row({ label, value, unit, range, hint }) {
  const bad = range && value != null && (value < range.lo || value > range.hi);
  return (
    <div className="fit-row cam-row" role="row">
      <span role="cell">{label}</span>
      <span role="cell"><span className={`chip ${value == null ? "chip-mute" : bad ? "chip-wet" : "chip-strong"}`}>{fmt(value)} {unit}</span></span>
      <span role="cell" className="muted small">{range ? `üblich ${range.lo} bis ${range.hi} ${unit}` : hint || ""}</span>
    </div>
  );
}

function Metrics({ metrics, view }) {
  if (!metrics || metrics.error) return <p className="error small">{metrics?.error}</p>;
  if (view === "side") {
    return (
      <div className="fit-table" role="table" aria-label="Messwerte Seitenansicht">
        <div className="fit-row fit-row-h cam-row" role="row"><span>Seitenansicht</span><span>gemessen</span><span>Einordnung</span></div>
        {["knee_bdc", "knee_min", "hip_min", "back", "elbow", "arm_torso", "cadence"].map((k) => (
          <Row key={k} label={RANGES[k].label} value={metrics[k]} unit={RANGES[k].unit} range={RANGES[k]} />
        ))}
        <Row label="Ausgewertete Umdrehungen" value={metrics.cycles} unit="" hint={`${metrics.frames} Bilder, Körperseite ${metrics.side === "l" ? "links" : "rechts"}`} />
      </div>
    );
  }
  return (
    <div className="fit-table" role="table" aria-label="Messwerte Frontansicht">
      <div className="fit-row fit-row-h cam-row" role="row"><span>Frontansicht</span><span>gemessen</span><span>Einordnung</span></div>
      <Row label="Kniespur links" value={metrics.knee_dev_l} unit="%" range={FRONT_RANGES.knee_dev_l} />
      <Row label="Kniespur rechts" value={metrics.knee_dev_r} unit="%" range={FRONT_RANGES.knee_dev_r} />
      <Row label="Beckenschaukeln" value={metrics.pelvis_range} unit="°" range={FRONT_RANGES.pelvis_range} />
      <Row label="Schulterschiefe" value={metrics.shoulder_tilt} unit="°" range={FRONT_RANGES.shoulder_tilt} />
      <p className="muted small" style={{ gridColumn: "1 / -1", margin: ".4rem 0 0" }}>
        Kniespur: Abweichung von der Linie Hüfte–Knöchel in Prozent der Beinlänge, plus heißt nach innen. Dafür gibt es keinen belastbaren Richtwert, die Grenze von 6 % ist eine Faustzahl.
      </p>
    </div>
  );
}

function Advice({ items }) {
  if (!items?.length) return null;
  return (
    <ul className="cam-advice">
      {items.map((a, i) => (
        <li key={i} className={`cam-tip cam-${a.level}`}>
          <strong>{a.title}</strong>
          <span>{a.text}</span>
        </li>
      ))}
    </ul>
  );
}

/** Abspieler mit eingezeichneten Linien und Winkeln. */
function Player({ src, times, poses, view, marks, label }) {
  const video = useRef(null), canvas = useRef(null), raf = useRef(0);
  const [t, setT] = useState(0);
  const [dur, setDur] = useState(0);
  const [playing, setPlaying] = useState(false);

  const paint = useCallback(() => {
    const v = video.current, c = canvas.current;
    if (!v || !c) return;
    drawPose(c, v, poseAt(times, poses, v.currentTime), view);
    setT(v.currentTime);
  }, [times, poses, view]);

  useEffect(() => {
    const loop = () => { paint(); raf.current = requestAnimationFrame(loop); };
    raf.current = requestAnimationFrame(loop);
    return () => cancelAnimationFrame(raf.current);
  }, [paint]);

  const jump = (to) => { if (video.current) { video.current.currentTime = Math.max(0, Math.min(dur, to)); paint(); } };
  const toggle = () => {
    const v = video.current;
    if (!v) return;
    if (v.paused) { v.play().catch(() => {}); setPlaying(true); } else { v.pause(); setPlaying(false); }
  };

  return (
    <div className="cam-player">
      <div className="cam-view">
        <video ref={video} src={src} muted playsInline loop
          onLoadedMetadata={(e) => setDur(e.currentTarget.duration || 0)}
          onPause={() => setPlaying(false)} onPlay={() => setPlaying(true)} onClick={toggle} />
        <canvas ref={canvas} />
        {label && <span className="cam-tag">{label}</span>}
      </div>
      <div className="cam-controls">
        <button type="button" className="btn small" onClick={toggle} aria-label={playing ? "Anhalten" : "Abspielen"}>{playing ? "❚❚" : "▶"}</button>
        <button type="button" className="btn small" onClick={() => jump(t - 1 / STEP_FPS)} aria-label="Ein Bild zurück">‹</button>
        <button type="button" className="btn small" onClick={() => jump(t + 1 / STEP_FPS)} aria-label="Ein Bild vor">›</button>
        <input type="range" min="0" max={dur || 1} step="0.02" value={t} aria-label="Zeitpunkt"
          onChange={(e) => { if (video.current) video.current.pause(); jump(Number(e.target.value)); }} />
        <span className="muted small cam-time">{t.toFixed(1)} s</span>
      </div>
      {marks?.length > 0 && (
        <div className="chips">
          <span className="muted small">Größte Kniestreckung:</span>
          {marks.slice(0, 8).map((m, i) => <button key={i} type="button" className="chip chip-mute" onClick={() => { video.current?.pause(); jump(m); }}>{fmt(m)} s</button>)}
        </div>
      )}
    </div>
  );
}

// ---------- Hauptteil ----------

export default function FitCamera({ bike, fitting }) {
  const [stage, setStage] = useState("idle");      // idle | setup | record | analyse | review
  const [error, setError] = useState("");
  const [devices, setDevices] = useState([]);
  const [deviceId, setDeviceId] = useState("");
  const [view, setView] = useState("side");
  const [left, setLeft] = useState(CAPTURE_S);
  const [progress, setProgress] = useState(0);
  const [result, setResult] = useState({});        // { side: {metrics, blob, url, times, poses}, front: {...} }
  const [shown, setShown] = useState("side");
  const [clips, setClips] = useState([]);
  const [saved, setSaved] = useState([]);
  const [compare, setCompare] = useState([]);      // bis zu zwei Kennungen aus dem Zwischenspeicher
  const [busy, setBusy] = useState(false);

  const live = useRef(null), overlay = useRef(null), viewRef = useRef(view), urls = useRef([]);
  viewRef.current = view;
  const stream = useRef(null), recorder = useRef(null), landmarker = useRef(null), raf = useRef(0), stop = useRef(false);

  const loadHistory = useCallback(async () => {
    api.get(`/bikes/${bike.id}/fit-captures`).then(setSaved).catch(() => {});
    listClips(bike.id).then(setClips).catch(() => {});
  }, [bike.id]);
  useEffect(() => { loadHistory(); }, [loadHistory]);

  const release = useCallback(() => {
    stop.current = true;
    cancelAnimationFrame(raf.current);
    try { recorder.current?.state === "recording" && recorder.current.stop(); } catch { /* egal */ }
    stream.current?.getTracks().forEach((t) => t.stop());
    stream.current = null;
    landmarker.current?.close?.();
    landmarker.current = null;
  }, []);
  useEffect(() => () => { release(); urls.current.forEach(URL.revokeObjectURL); }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const secure = typeof window !== "undefined" && window.isSecureContext && navigator.mediaDevices?.getUserMedia;

  async function findCameras() {
    setError(""); setBusy(true);
    try {
      const probe = await navigator.mediaDevices.getUserMedia({ video: true });
      probe.getTracks().forEach((t) => t.stop());
      const cams = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "videoinput");
      if (!cams.length) throw new Error("Es wurde keine Kamera gefunden.");
      setDevices(cams); setDeviceId(cams[0].deviceId); setStage("setup");
    } catch (e) {
      setError(e?.name === "NotAllowedError"
        ? "Der Zugriff auf die Kamera wurde abgelehnt. Erlaube ihn in der Adressleiste des Browsers und versuche es noch einmal."
        : e?.message || "Die Kamera lässt sich nicht öffnen.");
    } finally { setBusy(false); }
  }

  // Vorschau mit eingezeichnetem Skelett, damit man die Kamera ausrichten kann
  useEffect(() => {
    if (stage !== "setup" && stage !== "record") return undefined;
    let dead = false;
    stop.current = false;
    (async () => {
      try {
        stream.current?.getTracks().forEach((t) => t.stop());
        const s = await navigator.mediaDevices.getUserMedia({
          video: deviceId ? { deviceId: { exact: deviceId }, width: { ideal: 1280 }, height: { ideal: 720 } } : true,
        });
        if (dead) { s.getTracks().forEach((t) => t.stop()); return; }
        stream.current = s;
        if (live.current) { live.current.srcObject = s; await live.current.play().catch(() => {}); }
        if (!landmarker.current) landmarker.current = await makeLandmarker();
        let stamp = 0, last = -1;
        const loop = () => {
          if (dead || stop.current) return;
          const v = live.current;
          if (v && v.readyState >= 2 && v.currentTime !== last && landmarker.current) {
            last = v.currentTime;
            try {
              const found = landmarker.current.detectForVideo(v, (stamp += 40));
              if (overlay.current) drawPose(overlay.current, v, found.landmarks?.[0], viewRef.current);
            } catch { /* einzelne Bilder dürfen ausfallen */ }
          }
          raf.current = requestAnimationFrame(loop);
        };
        raf.current = requestAnimationFrame(loop);
      } catch (e) {
        setError(e?.message || "Die Kamera ist belegt. Schließe andere Programme, die sie nutzen.");
      }
    })();
    return () => { dead = true; cancelAnimationFrame(raf.current); };
  }, [stage === "setup" || stage === "record", deviceId]); // eslint-disable-line react-hooks/exhaustive-deps

  function pickMime() {
    const list = ["video/webm;codecs=vp9", "video/webm;codecs=vp8", "video/webm", "video/mp4"];
    return list.find((m) => window.MediaRecorder?.isTypeSupported?.(m)) || "";
  }

  async function record() {
    if (!stream.current) { setError("Die Kamera läuft nicht."); return; }
    if (!window.MediaRecorder) { setError("Dieser Browser kann kein Video aufnehmen."); return; }
    setError(""); setStage("record"); setLeft(CAPTURE_S);
    const mimeType = pickMime();
    const chunks = [];
    const rec = new MediaRecorder(stream.current, mimeType ? { mimeType, videoBitsPerSecond: 2_500_000 } : undefined);
    recorder.current = rec;
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const finished = new Promise((res) => { rec.onstop = () => res(new Blob(chunks, { type: mimeType || "video/webm" })); });
    rec.start(250);
    const t0 = Date.now();
    const tick = setInterval(() => setLeft(Math.max(0, Math.ceil(CAPTURE_S - (Date.now() - t0) / 1000))), 200);
    await new Promise((r) => setTimeout(r, CAPTURE_S * 1000));
    clearInterval(tick);
    try { rec.stop(); } catch { /* war schon aus */ }
    const blob = await finished;
    setStage("analyse"); setProgress(0);
    try {
      const out = await analyseClip(blob, view, setProgress);
      const url = URL.createObjectURL(blob);
      urls.current.push(url);
      setResult((p) => {
        p[view]?.url && URL.revokeObjectURL(p[view].url);
        return { ...p, [view]: { ...out, blob, url, view } };
      });
      setShown(view);
      setStage("review");
      if (out.metrics?.error) setError(out.metrics.error);
    } catch (e) {
      setError(e?.message || "Die Auswertung ist fehlgeschlagen.");
      setStage("setup");
    }
  }

  const metrics = Object.fromEntries(Object.entries(result).map(([k, r]) => [k, r.metrics]));
  const tips = Object.keys(metrics).length ? advise(metrics, fitting) : [];

  async function saveMeasurement() {
    const payload = forServer(metrics);
    if (!Object.keys(payload).length) { setError("Es gibt keine gültigen Messwerte zum Speichern."); return; }
    setBusy(true);
    try {
      await api.post(`/bikes/${bike.id}/fit-captures`, { metrics: payload });
      toast("Messung gespeichert.");
      await loadHistory();
    } catch (e) { setError(e.message); } finally { setBusy(false); }
  }

  async function keepClip(v) {
    const r = result[v];
    if (!r) return;
    setBusy(true);
    try {
      await saveClip({ bikeId: bike.id, view: v, blob: r.blob, metrics: r.metrics, times: r.times, poses: r.poses });
      toast(`Video behalten. Es bleibt in diesem Browser, höchstens ${MAX_PER_BIKE} Aufnahmen je Rad.`);
      await loadHistory();
    } catch (e) { setError(e.message || "Das Video ließ sich nicht zwischenspeichern."); } finally { setBusy(false); }
  }

  async function removeClip(c) {
    if (!await confirmDialog(`Die Aufnahme vom ${fmtDateTime(c.at)} löschen?`)) return;
    await deleteClip(c.id);
    setCompare((p) => p.filter((x) => x !== c.id));
    await loadHistory();
  }

  async function removeSaved(c) {
    if (!await confirmDialog(`Die Messung vom ${fmtDateTime(c.at)} löschen?`)) return;
    await api.del(`/fit-captures/${c.id}`);
    await loadHistory();
  }

  function close() {
    release();
    urls.current.forEach(URL.revokeObjectURL);
    urls.current = [];
    setResult({}); setStage("idle"); setError("");
  }

  const shots = Object.keys(result);

  return (
    <div className="cam-panel">
      <h3>Kameraanalyse <span className="chip chip-mute">Beta</span></h3>
      <p className="muted small">
        Die Kamera sieht dich auf dem Rad (Rolle oder Trainer) und misst die Winkel deiner Sitzposition. Erst die Seite, dann
        bei Bedarf die Front: Wenn du nur eine Kamera hast, stellst du sie einfach nacheinander um. Erkennung und Auswertung
        laufen nur in deinem Browser, es wird kein Bild hochgeladen. Videos bleiben auf Wunsch in diesem Browser, zum Vergleich
        vorher und nachher.
      </p>

      {!secure && <p className="error small">Der Browser gibt die Kamera nur über HTTPS frei (oder auf localhost). Öffne BikeHelper über die https-Adresse.</p>}
      {secure && stage === "idle" && <div className="actions"><button className="btn primary" onClick={findCameras} disabled={busy}>Kameraanalyse starten</button></div>}

      {(stage === "setup" || stage === "record") && (
        <>
          <div className="cam-setup">
            <div className="seg">
              {Object.entries(VIEWS).map(([k, cfg]) => (
                <button key={k} type="button" className={`btn small${view === k ? " primary" : ""}`} disabled={stage === "record"}
                  onClick={() => setView(k)}>{cfg.short}{result[k] ? " ✓" : ""}</button>
              ))}
            </div>
            {devices.length > 1 && (
              <label className="cam-pick">Kamera
                <select value={deviceId} onChange={(e) => setDeviceId(e.target.value)} disabled={stage === "record"}>
                  {devices.map((d, i) => <option key={d.deviceId} value={d.deviceId}>{d.label || `Kamera ${i + 1}`}</option>)}
                </select>
              </label>
            )}
          </div>
          <p className="muted small">{VIEWS[view].how} Gemessen wird: {VIEWS[view].gives}.</p>
          <div className="cam-view">
            <video ref={live} muted playsInline />
            <canvas ref={overlay} />
            {stage === "record" && <span className="cam-rec">● Aufnahme, noch {left} s</span>}
          </div>
          <div className="actions">
            <button className="btn primary" onClick={record} disabled={stage === "record"}>
              {stage === "record" ? `Läuft … ${left} s` : `${VIEWS[view].name} aufnehmen (${CAPTURE_S} s)`}
            </button>
            {shots.length > 0 && stage === "setup" && <button className="btn" onClick={() => setStage("review")}>Zur Auswertung</button>}
            <button className="btn" onClick={close} disabled={stage === "record"}>Kamera schließen</button>
          </div>
          <p className="muted small">Trete gleichmäßig in deiner gewohnten Haltung, am besten mit 80 bis 90 Umdrehungen. Die Linien im Bild zeigen, was erkannt wird.</p>
        </>
      )}

      {stage === "analyse" && (
        <div className="cam-progress">
          <p className="muted small">Die Aufnahme wird Bild für Bild ausgewertet … {pct(progress)}</p>
          <progress value={progress} max="1" />
        </div>
      )}

      {error && <p className="error small" role="alert">{error}</p>}

      {stage === "review" && shots.length > 0 && (
        <div className="cam-review">
          {shots.length > 1 && (
            <div className="seg">
              {shots.map((k) => (
                <button key={k} type="button" className={`btn small${shown === k ? " primary" : ""}`} onClick={() => setShown(k)}>{VIEWS[k].name}</button>
              ))}
            </div>
          )}
          {result[shown] && (
            <Player src={result[shown].url} times={result[shown].times} poses={result[shown].poses} view={shown}
              marks={result[shown].metrics?.marks} label={VIEWS[shown].name} />
          )}
          <Metrics metrics={result[shown]?.metrics} view={shown} />
          <h4>Was du daraus machen kannst</h4>
          <Advice items={tips} />
          <p className="muted small">
            Die Vorschläge rechnen mit etwa 5 Grad Kniewinkel je Zentimeter Sattelhöhe und sind auf einen Zentimeter begrenzt.
            Ändere immer nur eine Sache und fahre sie ein paar Ausfahrten, bevor du weitermisst. Bei Schmerzen ist ein Fitter
            oder Arzt die richtige Adresse, nicht diese Rechnung.
          </p>
          <div className="actions">
            <button className="btn primary" onClick={saveMeasurement} disabled={busy}>Messwerte speichern</button>
            <button className="btn" onClick={() => keepClip(shown)} disabled={busy}>Video behalten</button>
            <button className="btn" onClick={() => setStage("setup")}>Weitere Aufnahme</button>
            <button className="btn" onClick={close}>Fertig</button>
          </div>
        </div>
      )}

      {(clips.length > 0 || saved.length > 0) && (
        <details className="cam-history">
          <summary>Gespeichertes ({saved.length} Messungen, {clips.length} Videos)</summary>
          {clips.length > 0 && (
            <>
              <p className="muted small">Videos liegen nur in diesem Browser. Wähle zwei aus, um vorher und nachher nebeneinander zu sehen.</p>
              <ul className="cam-clips">
                {clips.map((c) => (
                  <li key={c.id}>
                    <label>
                      <input type="checkbox" checked={compare.includes(c.id)}
                        onChange={(e) => setCompare((p) => (e.target.checked ? [...p, c.id].slice(-2) : p.filter((x) => x !== c.id)))} />
                      {fmtDateTime(c.at)} · {VIEWS[c.view]?.short || c.view} · {Math.round(c.bytes / 1e5) / 10} MB
                    </label>
                    <button className="link small danger" onClick={() => removeClip(c)}>Löschen</button>
                  </li>
                ))}
              </ul>
              {compare.length === 2 && <CompareClips ids={compare} />}
            </>
          )}
          {saved.map((c) => (
            <div key={c.id} className="cam-hist-item">
              <div className="fit-card-top">
                <strong>{fmtDateTime(c.at)}</strong>
                <span className="rule-actions"><button className="link small danger" onClick={() => removeSaved(c)}>Löschen</button></span>
              </div>
              {Object.entries(c.metrics || {}).map(([v, m]) => <Metrics key={v} metrics={m} view={v} />)}
            </div>
          ))}
        </details>
      )}
    </div>
  );
}

/** Zwei zwischengespeicherte Aufnahmen nebeneinander, mit den Unterschieden. */
function CompareClips({ ids }) {
  const [pair, setPair] = useState(null);
  useEffect(() => {
    let dead = false;
    const urls = [];
    (async () => {
      const loaded = await Promise.all(ids.map(loadClip));
      if (dead || loaded.some((x) => !x)) return;
      const withUrl = loaded.map((c) => { const url = URL.createObjectURL(c.blob); urls.push(url); return { ...c, url }; });
      withUrl.sort((a, b) => (a.at < b.at ? -1 : 1));
      setPair(withUrl);
    })();
    return () => { dead = true; urls.forEach(URL.revokeObjectURL); setPair(null); };
  }, [ids.join(",")]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!pair) return <p className="muted small">Aufnahmen werden geladen …</p>;
  const [a, b] = pair;
  const keys = a.view === b.view && a.view === "side"
    ? ["knee_bdc", "knee_min", "hip_min", "back", "elbow", "cadence"]
    : a.view === b.view ? ["knee_dev_l", "knee_dev_r", "pelvis_range", "shoulder_tilt"] : [];
  const R = a.view === "side" ? RANGES : FRONT_RANGES;
  return (
    <div className="cam-compare">
      <div className="cam-compare-grid">
        {pair.map((c, i) => (
          <Player key={c.id} src={c.url} times={c.times} poses={c.poses} view={c.view}
            marks={c.metrics?.marks} label={`${i === 0 ? "vorher" : "nachher"} · ${fmtDateTime(c.at)}`} />
        ))}
      </div>
      {keys.length > 0 ? (
        <div className="fit-table" role="table" aria-label="Unterschied">
          <div className="fit-row fit-row-h cam-row" role="row"><span>Messwert</span><span>vorher → nachher</span><span>Änderung</span></div>
          {keys.map((k) => {
            const x = a.metrics?.[k], y = b.metrics?.[k];
            if (x == null && y == null) return null;
            return (
              <div key={k} className="fit-row cam-row" role="row">
                <span>{R[k]?.label || k}</span>
                <span>{fmt(x)} → <strong>{fmt(y)}</strong> {R[k]?.unit}</span>
                <span>{x != null && y != null && <span className="chip chip-wet">{y - x > 0 ? "+" : y - x < 0 ? "−" : "±"}{fmt(Math.abs(y - x))} {R[k]?.unit}</span>}</span>
              </div>
            );
          })}
        </div>
      ) : <p className="muted small">Für einen Vergleich der Zahlen müssen beide Aufnahmen dieselbe Ansicht zeigen.</p>}
    </div>
  );
}
