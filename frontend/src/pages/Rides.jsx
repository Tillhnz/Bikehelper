import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { WEATHER_TEXT, api, fmtDateTime, fmtDuration, fmtKm1, fmtNum, upload } from "../api.js";
import { EmptyState } from "../components/ui.jsx";
import { dismiss, isBusy, startFileImport, startStravaImport, useUploads } from "../uploads.js";

// ---------- Hilfsbausteine ----------

function Dropzone({ accept, multiple, files, onFiles, label }) {
  const [over, setOver] = useState(false);
  const text = files.length
    ? files.length === 1
      ? `${files[0].name} (${(files[0].size / 1048576).toFixed(1).replace(".", ",")} MB)`
      : `${files.length} Dateien ausgewählt`
    : label;
  return (
    <label
      className={`dropzone ${over ? "over" : ""} ${files.length ? "filled" : ""}`}
      onDragOver={(e) => { e.preventDefault(); setOver(true); }}
      onDragLeave={() => setOver(false)}
      onDrop={(e) => { e.preventDefault(); setOver(false); onFiles(Array.from(e.dataTransfer.files)); }}
    >
      <input type="file" accept={accept} multiple={multiple} onChange={(e) => onFiles(Array.from(e.target.files))} />
      <span>{text}</span>
    </label>
  );
}

function Progress({ value, label }) {
  const pct = Math.round(Math.min(Math.max(value, 0), 1) * 100);
  return (
    <div className="progress-wrap">
      <div className="progress" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label={label}>
        <div className="progress-bar" style={{ width: `${pct}%` }} />
      </div>
      <span className="muted small">{label} · {pct} %</span>
    </div>
  );
}

function ResultSummary({ s }) {
  const unmatched = Object.entries(s.unmatched_gear || {});
  return (
    <div className="result" role="status">
      <p>
        <strong>{s.imported}</strong> {s.imported === 1 ? "Fahrt" : "Fahrten"} importiert
        {s.duplicates > 0 && `, ${s.duplicates} waren schon vorhanden`}.
      </p>
      {s.updated > 0 && <p>Bei {s.updated} vorhandenen Fahrten wurden Rad und Radname nachgetragen.</p>}
      {s.notes?.map((n) => <p key={n} className="error">{n}</p>)}
      {s.created_bikes?.length > 0 && <p>Neue Räder angelegt: {s.created_bikes.join(", ")}.</p>}
      {s.skipped_other_sport > 0 && (
        <p className="muted small">{s.skipped_other_sport} andere Aktivitäten (zum Beispiel Laufen) wurden übersprungen.</p>
      )}
      {s.skipped_no_file > 0 && (
        <p className="muted small">{s.skipped_no_file} Aktivitäten ohne GPS-Datei (zum Beispiel manuell eingetragen) wurden übersprungen.</p>
      )}
      {unmatched.length > 0 && (
        <p className="muted small">
          Ohne passendes Rad geblieben: {unmatched.map(([n, c]) => `${n} (${c})`).join(", ")}. Ordne sie unten zu.
        </p>
      )}
      {s.errors?.length > 0 && (
        <details>
          <summary>{s.errors.length} {s.errors.length === 1 ? "Datei konnte" : "Dateien konnten"} nicht gelesen werden</summary>
          <ul className="small">
            {s.errors.map((e, i) => <li key={i}><code>{e.file}</code>: {e.message}</li>)}
          </ul>
        </details>
      )}
    </div>
  );
}

// ---------- Strava-Export ----------

function StravaImport() {
  const [files, setFiles] = useState([]);
  const [createBikes, setCreateBikes] = useState(true);
  const { strava } = useUploads();
  const { phase, pct: uploadPct, job, error } = strava;

  function start(e) {
    e.preventDefault();
    if (!files.length) return;
    startStravaImport(files[0], createBikes);
    setFiles([]);
  }

  const busy = isBusy(strava);

  return (
    <section className="panel">
      <h2>Strava-Export importieren</h2>
      <p className="muted">
        Mit deinem Strava-Datenexport übernimmst du deine komplette Historie auf einmal. Es ist kein Strava-Abo nötig.
      </p>
      <details className="howto">
        <summary>So bekommst du den Export</summary>
        <ol className="steps">
          <li>Öffne Strava im Browser: Einstellungen, dann „Mein Konto“, dann „Dein Konto herunterladen“, „Loslegen“ und „Download anfordern“. Die Menünamen können sich ändern.</li>
          <li>Strava schickt dir eine E-Mail mit dem Download-Link. Das kann einige Stunden dauern.</li>
          <li>Stelle die Sprache deines Strava-Kontos vor der Anforderung auf Englisch. Sonst werden die Fahrten zwar importiert, aber die Räder nicht automatisch zugeordnet.</li>
          <li>Lade die ZIP-Datei hier hoch, ohne sie zu entpacken.</li>
        </ol>
      </details>

      <form onSubmit={start}>
        <Dropzone accept=".zip" files={files} onFiles={setFiles} label="ZIP-Datei hierher ziehen oder auswählen" />
        <label className="check">
          <input type="checkbox" checked={createBikes} onChange={(e) => setCreateBikes(e.target.checked)} />
          Räder aus dem Export automatisch anlegen
        </label>
        <div className="actions">
          <button className="btn primary" disabled={!files.length || busy}>
            {busy ? "Import läuft …" : "Export importieren"}
          </button>
        </div>
      </form>

      {busy && <p className="muted small">Du kannst die Seite wechseln, Upload und Import laufen weiter. Am Ende erscheint eine Meldung.</p>}
      {phase === "uploading" && <Progress value={uploadPct} label="Wird hochgeladen" />}
      {phase === "processing" && (
        <Progress value={job && job.total ? job.processed / job.total : 0} label={job ? `Fahrt ${job.processed} von ${job.total}` : "Wird gestartet"} />
      )}
      {phase === "error" && <p className="error" role="alert">{error}</p>}
      {phase === "done" && job && (
        <>
          <ResultSummary s={job.summary} />
          <button className="link small" onClick={() => dismiss("strava")}>Meldung ausblenden</button>
        </>
      )}
    </section>
  );
}

// ---------- Einzelne Dateien ----------

function FileImport({ bikes }) {
  const [files, setFiles] = useState([]);
  const [bikeId, setBikeId] = useState("");
  const { files: up } = useUploads();
  const busy = isBusy(up);

  function send(e) {
    e.preventDefault();
    if (!files.length) return;
    startFileImport(files, bikeId);
    setFiles([]);
  }

  return (
    <section className="panel">
      <h2>Fahrtdateien hochladen</h2>
      <p className="muted">
        GPX-, FIT- und TCX-Dateien deines Radcomputers oder deiner App, auch mehrere auf einmal. Bereits vorhandene Fahrten werden erkannt und übersprungen.
      </p>
      <form onSubmit={send}>
        <Dropzone
          accept=".fit,.gpx,.tcx,.gz"
          multiple
          files={files}
          onFiles={setFiles}
          label="Dateien hierher ziehen oder auswählen"
        />
        <label>
          Rad
          <select value={bikeId} onChange={(e) => setBikeId(e.target.value)}>
            <option value="">Später zuordnen</option>
            {bikes.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
        </label>
        <div className="actions">
          <button className="btn primary" disabled={!files.length || busy}>
            {busy ? "Wird hochgeladen …" : "Dateien importieren"}
          </button>
        </div>
      </form>
      {busy && <Progress value={up.pct} label="Wird hochgeladen" />}
      {up.phase === "error" && <p className="error" role="alert">{up.error}</p>}
      {up.phase === "done" && up.result && (
        <>
          <ResultSummary s={up.result} />
          <button className="link small" onClick={() => dismiss("files")}>Meldung ausblenden</button>
        </>
      )}
    </section>
  );
}

// ---------- Zuordnung nach Radname ----------

function GearAssign({ gear, bikes, onDone }) {
  const open = gear.filter((g) => g.gear_name && g.unassigned > 0);
  const [choice, setChoice] = useState({});
  const [error, setError] = useState("");
  if (open.length === 0) return null;

  async function assign(g) {
    const bikeId = choice[g.gear_name];
    if (!bikeId) return;
    setError("");
    try {
      await api.post("/activities/assign", { bike_id: Number(bikeId), gear_name: g.gear_name, only_unassigned: true });
      onDone();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="panel attention">
      <h2>Fahrten ohne Rad</h2>
      <p className="muted">
        Diese Radnamen stehen im Strava-Export, haben aber noch kein Rad in BikeHelper. Wähle das passende Rad, dann werden alle Fahrten auf einmal zugeordnet.
      </p>
      {bikes.length === 0 ? (
        <p>Lege zuerst in der <Link to="/">Garage</Link> ein Rad an.</p>
      ) : (
        <ul className="gear-list">
          {open.map((g) => (
            <li key={g.gear_name}>
              <div>
                <strong>{g.gear_name}</strong>
                <span className="muted small"> · {g.unassigned} Fahrten ohne Rad, {fmtKm1(g.km)} km gesamt</span>
              </div>
              <div className="gear-actions">
                <select
                  aria-label={`Rad für ${g.gear_name}`}
                  value={choice[g.gear_name] || ""}
                  onChange={(e) => setChoice({ ...choice, [g.gear_name]: e.target.value })}
                >
                  <option value="">Rad wählen</option>
                  {bikes.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                </select>
                <button className="btn small" disabled={!choice[g.gear_name]} onClick={() => assign(g)}>Zuordnen</button>
              </div>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

// ---------- Wetter ----------

function WeatherCell({ a }) {
  if (a.weather_status == null) return <span className="muted small">offen</span>;
  if (a.weather_status === "none" || a.temp_c == null) return <span className="muted small">–</span>;
  const wet = a.wet_minutes != null && a.wet_minutes >= 5;
  const text = WEATHER_TEXT(a.weather_code);
  return (
    <span title={`Wind ${fmtNum(a.wind_kmh, 0)} km/h, Regen ${fmtNum(a.precip_mm)} mm${a.weather_status === "prelim" ? " (vorläufig)" : ""}`}>
      {fmtNum(a.temp_c)} °C{text ? `, ${text}` : ""}
      {wet && <span className="pill pill-soon" style={{ marginLeft: "0.4rem" }}>{Math.round(a.wet_minutes)} min nass</span>}
    </span>
  );
}

function WeatherPanel({ refreshKey }) {
  const [st, setSt] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setSt(await api.get("/weather/status"));
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => { load(); }, [load, refreshKey]);
  useEffect(() => {
    if (!st?.running) return undefined;
    const t = setInterval(load, 3000);
    return () => clearInterval(t);
  }, [st?.running, load]);

  async function start() {
    setError("");
    try {
      setSt(await api.post("/weather/enrich"));
    } catch (err) {
      setError(err.message);
    }
  }

  if (!st) return null;
  if (!st.enabled) {
    return <section className="panel"><h2>Wetter</h2><p className="muted">Die Wetterabfrage ist auf diesem Server abgeschaltet.</p></section>;
  }
  const open = st.pending;
  return (
    <section className="panel">
      <h2>Wetter zu deinen Fahrten</h2>
      <p className="muted">
        {st.ok + st.prelim} von {st.with_location} Fahrten mit Ort haben Wetterdaten
        {st.without_location > 0 ? ` (${st.without_location} Fahrten ohne GPS-Position werden übersprungen)` : ""}.
        Die Daten stammen von Open-Meteo; dorthin werden nur gerundete Startkoordinaten und Zeiträume gesendet.
      </p>
      {st.running && (
        <div className="progress-wrap">
          <div className="progress"><div className="progress-bar" style={{ width: `${st.progress_total ? (st.progress_done / st.progress_total) * 100 : 5}%` }} /></div>
          <span className="muted small">Wetter wird abgerufen … {st.progress_done} von {st.progress_total}</span>
        </div>
      )}
      {(st.error || error) && <p className="error" role="alert">{st.error || error}</p>}
      {!st.running && (open > 0 || st.prelim > 0) && (
        <div className="actions">
          <button className="btn primary" onClick={start}>{open > 0 ? `Wetter für ${open} Fahrten abrufen` : "Vorläufige Daten aktualisieren"}</button>
        </div>
      )}
    </section>
  );
}

// ---------- Liste der Fahrten ----------

const PAGE = 50;

function ActivityList({ bikes, refreshKey, onChanged }) {
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [unassigned, setUnassigned] = useState(false);
  const [q, setQ] = useState("");
  const [debouncedQ, setDebouncedQ] = useState("");
  const [error, setError] = useState("");

  useEffect(() => {
    const t = setTimeout(() => setDebouncedQ(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  const load = useCallback(async (offset) => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
      if (unassigned) params.set("unassigned", "true");
      if (debouncedQ.trim()) params.set("q", debouncedQ.trim());
      const page = await api.get(`/activities?${params}`);
      setTotal(page.total);
      setItems((prev) => (offset === 0 ? page.items : [...prev, ...page.items]));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [unassigned, debouncedQ]);

  useEffect(() => { load(0); }, [load, refreshKey]);

  async function changeBike(a, value) {
    const bikeId = value ? Number(value) : null;
    setItems((prev) => prev.map((x) => (x.id === a.id ? { ...x, bike_id: bikeId } : x)));
    try {
      await api.put(`/activities/${a.id}`, { bike_id: bikeId });
      onChanged();
    } catch (err) {
      setError(err.message);
      load(0);
    }
  }

  async function remove(a) {
    if (!window.confirm(`„${a.name}“ wirklich löschen?`)) return;
    try {
      await api.del(`/activities/${a.id}`);
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section>
      <header className="page-head">
        <h2>Alle Fahrten <span className="muted small">{total}</span></h2>
        <div className="filters">
          <input type="search" placeholder="Fahrt suchen" aria-label="Fahrt suchen" value={q} onChange={(e) => setQ(e.target.value)} />
          <label className="check">
            <input type="checkbox" checked={unassigned} onChange={(e) => setUnassigned(e.target.checked)} />
            Nur ohne Rad
          </label>
        </div>
      </header>

      {error && <p className="error" role="alert">{error}</p>}

      {!loading && items.length === 0 ? (
        <EmptyState
          title={unassigned || debouncedQ ? "Keine passenden Fahrten" : "Noch keine Fahrten"}
          text={unassigned || debouncedQ ? "Ändere den Filter oder die Suche." : "Importiere oben deinen Strava-Export oder lade Fahrtdateien hoch."}
        />
      ) : (
        <div className="table-wrap">
          <table className="rides">
            <thead>
              <tr>
                <th>Datum</th>
                <th>Name</th>
                <th className="num">Strecke</th>
                <th className="num">Zeit</th>
                <th className="num">Höhenmeter</th>
                <th>Wetter</th>
                <th>Rad</th>
                <th><span className="sr-only">Aktionen</span></th>
              </tr>
            </thead>
            <tbody>
              {items.map((a) => (
                <tr key={a.id}>
                  <td className="nowrap">{fmtDateTime(a.start_date)}</td>
                  <td><Link className="ride-link" to={`/rides/${a.id}`}>{a.name}</Link></td>
                  <td className="num nowrap">{fmtKm1(a.distance_km)} km</td>
                  <td className="num nowrap">{fmtDuration(a.moving_time_s)}</td>
                  <td className="num nowrap">{Math.round(a.elevation_m)} m</td>
                  <td className="nowrap"><WeatherCell a={a} /></td>
                  <td>
                    <select aria-label={`Rad für ${a.name}`} value={a.bike_id ?? ""} onChange={(e) => changeBike(a, e.target.value)}>
                      <option value="">Kein Rad</option>
                      {bikes.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
                    </select>
                  </td>
                  <td><button className="link small danger" onClick={() => remove(a)}>Löschen</button></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {items.length < total && (
        <div className="actions">
          <button className="btn" disabled={loading} onClick={() => load(items.length)}>
            {loading ? "Lädt …" : "Weitere Fahrten laden"}
          </button>
        </div>
      )}
    </section>
  );
}

// ---------- Alle Fahrten löschen ----------

function DeleteAll({ onDone }) {
  const [open, setOpen] = useState(false);
  const [word, setWord] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function run(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const r = await api.del("/activities?confirm=true");
      setMsg(`${r.deleted} Fahrten gelöscht. Du kannst den Export jetzt neu hochladen.`);
      setOpen(false);
      setWord("");
      onDone();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel danger-zone">
      <h2>Alle Fahrten löschen</h2>
      <p className="muted">
        Entfernt alle importierten Fahrten samt Wetter, Karte und Statistik, zum Beispiel für einen sauberen Neuimport.
        Deine Räder, Komponenten und Wartungseinträge bleiben erhalten. Dort gezählte Kilometer richten sich nach den
        Fahrten und sind bis zum Neuimport entsprechend niedriger.
      </p>
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {!open ? (
        <button className="btn" onClick={() => { setOpen(true); setMsg(""); }}>Alle Fahrten löschen …</button>
      ) : (
        <form className="inline-form" onSubmit={run}>
          <label className="grow">
            Tippe LÖSCHEN, um zu bestätigen
            <input value={word} onChange={(e) => setWord(e.target.value)} autoFocus autoComplete="off" />
          </label>
          <button className="btn primary" disabled={word.trim().toUpperCase() !== "LÖSCHEN" || busy}>
            {busy ? "Lösche …" : "Endgültig löschen"}
          </button>
          <button type="button" className="btn" onClick={() => { setOpen(false); setWord(""); }}>Abbrechen</button>
        </form>
      )}
    </section>
  );
}

// ---------- Seite ----------

export default function Rides() {
  const [bikes, setBikes] = useState([]);
  const [gear, setGear] = useState([]);
  const [refreshKey, setRefreshKey] = useState(0);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    try {
      const [b, g] = await Promise.all([api.get("/bikes"), api.get("/activities/gear")]);
      setBikes(b);
      setGear(g);
    } catch (err) {
      setError(err.message);
    }
    setRefreshKey((k) => k + 1);
  }, []);

  useEffect(() => { refresh(); }, [refresh]);
  const { doneCount } = useUploads();
  useEffect(() => { if (doneCount > 0) refresh(); }, [doneCount, refresh]);

  return (
    <>
      <header className="page-head"><h1>Fahrten</h1></header>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="import-grid">
        <StravaImport />
        <FileImport bikes={bikes} />
      </div>
      <GearAssign gear={gear} bikes={bikes} onDone={refresh} />
      <WeatherPanel refreshKey={refreshKey} />
      <ActivityList bikes={bikes} refreshKey={refreshKey} onChanged={refresh} />
      <DeleteAll onDone={refresh} />
    </>
  );
}
