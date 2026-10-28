import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { WEATHER_TEXT, api, sourceLabel, fmtDateTime, fmtDuration, fmtKm, fmtKm1, fmtNum } from "../api.js";
import { ProfileChart } from "../components/charts.jsx";
import { decodePolyline, loadMapConfig, tileOptions } from "../geo.js";
import AfterRide from "../components/AfterRide.jsx";
import { RideImpact } from "../components/StatsDeep.jsx";
import { confirmDialog, Loading, toast } from "../components/feedback.jsx";

function RouteMap({ polyline, hoverPoint, cfg }) {
  const boxRef = useRef(null);
  const marker = useRef(null);
  const mapRef = useRef(null);

  useEffect(() => {
    const pts = decodePolyline(polyline);
    const map = L.map(boxRef.current, { zoomControl: true, scrollWheelZoom: false });
    mapRef.current = map;
    L.tileLayer(cfg.url, tileOptions(cfg)).addTo(map);
    const line = L.polyline(pts, { color: cfg.dark ? "#6fd3c3" : "#d63014", weight: 4, opacity: 0.95 }).addTo(map);
    L.circleMarker(pts[0], { radius: 7, color: "#0e1620", weight: 2, fillColor: "#6fd3c3", fillOpacity: 1 }).addTo(map).bindTooltip("Start");
    L.circleMarker(pts[pts.length - 1], { radius: 7, color: "#0e1620", weight: 2, fillColor: "#f2b84b", fillOpacity: 1 }).addTo(map).bindTooltip("Ziel");
    marker.current = L.circleMarker(pts[0], { radius: 7, color: "#fff", weight: 2, fillColor: "#ff6b6b", fillOpacity: 1 });
    map.fitBounds(line.getBounds(), { padding: [24, 24] });
    return () => { map.remove(); mapRef.current = null; };
  }, [polyline, cfg]);

  useEffect(() => {
    const m = marker.current, map = mapRef.current;
    if (!m || !map) return;
    if (hoverPoint) {
      m.setLatLng(hoverPoint);
      if (!map.hasLayer(m)) m.addTo(map);
    } else if (map.hasLayer(m)) {
      map.removeLayer(m);
    }
  }, [hoverPoint]);

  return <div className="detail-map" ref={boxRef} />;
}

function Stat({ value, unit, label }) {
  if (value == null || value === "–") return null;
  return (
    <div className="kpi">
      <div className="kpi-value">{value}{unit && <small>{unit}</small>}</div>
      <div className="kpi-label">{label}</div>
    </div>
  );
}

export default function RideDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [a, setA] = useState(null);
  const [error, setError] = useState("");
  const [hover, setHover] = useState(null);
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState("");
  const [cfg, setCfg] = useState(null);
  const [bikes, setBikes] = useState([]);
  const [suggestion, setSuggestion] = useState(null);

  useEffect(() => {
    loadMapConfig(api).then(setCfg).catch(() => {});
  }, []);

  useEffect(() => {
    setA(null);
    api.get(`/activities/${id}`).then((r) => { setA(r); setName(r.name); }).catch((e) => setError(e.message));
  }, [id]);

  const unassigned = a ? !a.bike_id : false;
  useEffect(() => {
    setSuggestion(null);
    if (!unassigned) return;
    api.get("/bikes").then(setBikes).catch(() => {});
    api.get(`/activities/suggestions?activity_id=${id}`).then((r) => setSuggestion(r[id] || null)).catch(() => {});
  }, [id, unassigned]);

  const profile = a?.details?.profile;
  const llPoints = useMemo(() => (profile?.ll ? decodePolyline(profile.ll) : null), [profile]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!a) return <Loading />;

  const d = a.details;
  const wetText = a.wet_minutes != null && a.wet_minutes >= 5;

  async function saveName(e) {
    e.preventDefault();
    try {
      const r = await api.put(`/activities/${a.id}`, { name });
      setA({ ...a, name: r.name });
      setEditing(false);
    } catch (err) { setError(err.message); }
  }

  async function setBike(bikeId) {
    try {
      const r = await api.put(`/activities/${a.id}`, { bike_id: Number(bikeId) });
      setA({ ...a, bike_id: r.bike_id, bike_name: r.bike_name });
      toast("Rad zugeordnet.");
    } catch (err) { setError(err.message); }
  }

  async function remove() {
    if (!await confirmDialog(`„${a.name}“ wirklich löschen?`)) return;
    await api.del(`/activities/${a.id}`);
    navigate("/rides");
  }

  const hoverPoint = hover != null && llPoints ? llPoints[hover] : null;

  return (
    <>
      <p><Link to="/rides" className="link">← Zurück zu den Fahrten</Link></p>
      <header className="page-head">
        <div>
          {editing ? (
            <form className="inline-form" onSubmit={saveName} style={{ margin: 0 }}>
              <label className="grow">Name<input value={name} onChange={(e) => setName(e.target.value)} required autoFocus /></label>
              <button className="btn primary">Speichern</button>
              <button type="button" className="btn" onClick={() => { setEditing(false); setName(a.name); }}>Abbrechen</button>
            </form>
          ) : (
            <h1>{a.name}</h1>
          )}
          <p className="muted">
            {fmtDateTime(a.start_date)}
            {a.bike_name ? <> · <Link className="link" to={`/bikes/${a.bike_id}`}>{a.bike_name}</Link></> : a.gear_name ? ` · ${a.gear_name}` : ""}
            {sourceLabel(a.source) && <span className="source-tag" title="Woher diese Fahrt stammt">{sourceLabel(a.source)}</span>}
          </p>
        </div>
        <div className="actions" style={{ marginTop: 0 }}>
          {!editing && <button className="btn small" onClick={() => setEditing(true)}>Umbenennen</button>}
          <button className="link small danger" onClick={remove}>Löschen</button>
        </div>
      </header>

      {unassigned && (
        <section className="panel attention bike-assign">
          <strong>Kein Rad zugeordnet.</strong>{" "}
          {suggestion ? (
            <>
              Vorschlag: <strong>{suggestion.bike_name}</strong>
              <span className="muted small"> ({suggestion.reason})</span>{" "}
              <button className="btn small primary" onClick={() => setBike(suggestion.bike_id)}>Übernehmen</button>{" "}
            </>
          ) : null}
          {bikes.length > 0 && (
            <label className="inline-select">
              <span className="muted small">{suggestion ? "oder anderes Rad: " : "Rad wählen: "}</span>
              <select value="" onChange={(e) => e.target.value && setBike(e.target.value)} aria-label="Rad zuordnen">
                <option value="">–</option>
                {bikes.filter((b) => !b.retired).map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
              </select>
            </label>
          )}
        </section>
      )}

      <AfterRide bikeId={a.bike_id} />

      <div className="kpis">
        <Stat value={fmtKm1(a.distance_km)} unit="km" label="Strecke" />
        <Stat value={fmtDuration(a.moving_time_s)} label="Bewegungszeit" />
        <Stat value={d?.elapsed_s ? fmtDuration(d.elapsed_s) : null} label="Gesamtzeit" />
        <Stat value={a.avg_speed != null ? fmtNum(a.avg_speed) : null} unit="km/h" label="Ø Tempo" />
        <Stat value={d?.max_speed != null ? fmtNum(d.max_speed) : null} unit="km/h" label="Höchstes Tempo" />
        <Stat value={fmtKm(a.elevation_m)} unit="m" label="Höhenmeter" />
        <Stat value={d?.ele_max != null ? fmtKm(d.ele_max) : null} unit="m" label="Höchster Punkt" />
        <Stat value={d?.avg_hr != null ? fmtNum(d.avg_hr, 0) : null} unit="bpm" label={d?.max_hr ? `Ø Puls (max ${fmtNum(d.max_hr, 0)})` : "Ø Puls"} />
        <Stat value={d?.avg_cadence != null ? fmtNum(d.avg_cadence, 0) : null} unit="U/min" label="Ø Trittfrequenz" />
        <Stat value={d?.avg_power != null ? fmtNum(d.avg_power, 0) : null} unit="W" label={d?.max_power ? `Ø Leistung (max ${fmtNum(d.max_power, 0)})` : "Ø Leistung"} />
      </div>

      {a.polyline ? (
        cfg ? <RouteMap polyline={a.polyline} hoverPoint={hoverPoint} cfg={cfg} /> : <div className="detail-map" />
      ) : (
        <p className="muted">Zu dieser Fahrt gibt es keine GPS-Strecke.</p>
      )}

      <RideImpact id={id} />

      {profile ? (
        <section className="panel" style={{ marginTop: "1.25rem" }}>
          <h2>Verlauf</h2>
          <p className="muted small">Fahre mit der Maus über ein Diagramm, die Position erscheint auf der Karte.</p>
          {profile.e && (
            <>
              <h3 className="chart-title">Höhe</h3>
              <ProfileChart x={profile.d} y={profile.e} unit="m" fill hover={hover} onHover={setHover} height={150} />
            </>
          )}
          {profile.s && (
            <>
              <h3 className="chart-title">Tempo</h3>
              <ProfileChart x={profile.d} y={profile.s} unit="km/h" color="var(--amber)" hover={hover} onHover={setHover} decimals={1} zeroBased />
            </>
          )}
          {profile.h && (
            <>
              <h3 className="chart-title">Puls</h3>
              <ProfileChart x={profile.d} y={profile.h} unit="bpm" color="var(--signal)" hover={hover} onHover={setHover} />
            </>
          )}
          {profile.p && (
            <>
              <h3 className="chart-title">Leistung</h3>
              <ProfileChart x={profile.d} y={profile.p} unit="W" color="#a58bff" hover={hover} onHover={setHover} zeroBased />
            </>
          )}
          {profile.c && (
            <>
              <h3 className="chart-title">Trittfrequenz</h3>
              <ProfileChart x={profile.d} y={profile.c} unit="U/min" color="#7fb6ff" hover={hover} onHover={setHover} zeroBased />
            </>
          )}
        </section>
      ) : (
        <section className="panel" style={{ marginTop: "1.25rem" }}>
          <h2>Verlauf</h2>
          <p className="muted">
            Für diese Fahrt liegen noch keine Verlaufsdaten (Höhenprofil, Tempo, Puls) vor, weil sie vor dieser Funktion
            importiert wurde. Lade denselben Strava-Export oder dieselben Dateien auf der Seite „Fahrten“ einfach noch einmal
            hoch: Vorhandene Fahrten werden dabei ergänzt, nicht doppelt angelegt.
          </p>
        </section>
      )}

      <section className="panel">
        <h2>Wetter</h2>
        {a.weather_status == null && <p className="muted">Die Wetterdaten werden noch abgerufen.</p>}
        {a.weather_status === "none" && <p className="muted">Für diese Fahrt sind keine Wetterdaten verfügbar (zum Beispiel ohne GPS-Position).</p>}
        {(a.weather_status === "ok" || a.weather_status === "prelim") && (
          <>
            <div className="kpis" style={{ marginBottom: 0 }}>
              <Stat value={fmtNum(a.temp_c)} unit="°C" label={WEATHER_TEXT(a.weather_code) ?? "Temperatur"} />
              <Stat value={fmtNum(a.precip_mm)} unit="mm" label="Regen" />
              <Stat value={fmtNum(a.wind_kmh, 0)} unit="km/h" label="Wind" />
              <Stat value={a.wet_minutes != null ? fmtNum(a.wet_minutes, 0) : null} unit="min" label="auf nasser Straße" />
            </div>
            <p className="muted small" style={{ marginTop: "0.75rem" }}>
              {wetText
                ? "Die Nässe wurde bei den Wartungsintervallen deines Rades mit dem jeweiligen Nässefaktor gezählt."
                : "Trockene Fahrt: Es wird ganz normal gezählt."}
              {a.weather_status === "prelim" ? " Die Werte sind vorläufig und werden in einigen Tagen aus dem Archiv aktualisiert." : ""}
            </p>
          </>
        )}
      </section>
    </>
  );
}
