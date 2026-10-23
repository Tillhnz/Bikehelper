import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { WEATHER_TEXT, api, fmtNum } from "../api.js";

const STORE = "bikehelper_advisor";

function defaultStart() {
  const d = new Date();
  if (d.getHours() >= 17) {
    d.setDate(d.getDate() + 1);
    d.setHours(9, 0, 0, 0);
  } else {
    d.setHours(d.getHours() + 1, 0, 0, 0);
  }
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:00`;
}

function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORE) || "{}");
  } catch {
    return {};
  }
}

const DURATIONS = [
  [60, "1 Std."], [90, "1,5 Std."], [120, "2 Std."], [180, "3 Std."], [240, "4 Std."], [300, "5 Std."], [360, "6 Std."], [480, "8 Std."],
];

function WeatherCard({ w }) {
  const text = WEATHER_TEXT(w.weather_code);
  return (
    <section className="panel">
      <h2>Wetter während der Tour</h2>
      <p className="muted small">
        {w.source === "forecast" ? "Vorhersage von Open-Meteo, Ortszeit des Startorts." : "Deine Angaben, ohne Vorhersage."}
      </p>
      <div className="kpis" style={{ marginBottom: 0 }}>
        <div className="kpi">
          <div className="kpi-value">{fmtNum(w.temp_avg, 0)}<small>°C</small></div>
          <div className="kpi-label">
            {w.temp_min != null && w.temp_max != null && Math.round(w.temp_min) !== Math.round(w.temp_max)
              ? `${fmtNum(w.temp_min, 0)} bis ${fmtNum(w.temp_max, 0)} °C` : "Ø Temperatur"}{text ? ` · ${text}` : ""}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-value">{fmtNum(w.precip_mm)}<small>mm</small></div>
          <div className="kpi-label">Regen{w.precip_prob != null ? ` · bis ${Math.round(w.precip_prob)} % Wahrscheinlichkeit` : ""}</div>
        </div>
        <div className="kpi">
          <div className="kpi-value">{fmtNum(w.wind_kmh, 0)}<small>km/h</small></div>
          <div className="kpi-label">Wind{w.gust_kmh != null ? ` · Böen bis ${fmtNum(w.gust_kmh, 0)}` : ""}</div>
        </div>
        {w.dark_minutes > 0 && (
          <div className="kpi">
            <div className="kpi-value">{Math.round(w.dark_minutes)}<small>min</small></div>
            <div className="kpi-label">in der Dunkelheit</div>
          </div>
        )}
      </div>
      {w.hours?.length > 0 && (
        <div className="table-wrap" style={{ marginTop: "1rem" }}>
          <table className="rides">
            <thead>
              <tr><th>Uhr</th><th className="num">°C</th><th className="num">Regen</th><th className="num">Wind</th><th>Wetter</th></tr>
            </thead>
            <tbody>
              {w.hours.map((h) => (
                <tr key={h.time}>
                  <td>{h.time}</td>
                  <td className="num">{fmtNum(h.temp, 0)}</td>
                  <td className="num">{h.precip ? `${fmtNum(h.precip)} mm` : "–"}{h.pop != null ? ` (${h.pop} %)` : ""}</td>
                  <td className="num">{fmtNum(h.wind, 0)}{h.gust ? ` / ${fmtNum(h.gust, 0)}` : ""}</td>
                  <td>{WEATHER_TEXT(h.code) ?? "–"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ClothingCard({ c }) {
  return (
    <section className="panel advice">
      <h2>Das ziehst du an</h2>
      <p className="advice-headline">{c.headline}</p>
      <p className="muted">
        Gefühlt wie {fmtNum(c.effective_temp, 0)} °C für diese Fahrt · {c.top}, {c.legs.toLowerCase()}
      </p>
      {c.warnings.map((w) => <p key={w} className="error" role="alert">{w}</p>)}
      <div className="advice-groups">
        {Object.entries(c.groups).map(([name, items]) => (
          <div key={name} className="advice-group">
            <h3>{name}</h3>
            <ul>{items.map((i) => <li key={i}>{i}</li>)}</ul>
          </div>
        ))}
      </div>
      {c.reasons.length > 0 && (
        <details className="howto" style={{ marginTop: "1rem" }}>
          <summary>Warum diese Empfehlung?</summary>
          <ul className="steps">{c.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </details>
      )}
    </section>
  );
}

function TiresCard({ t, missing }) {
  if (!t) {
    return (
      <section className="panel">
        <h2>Reifendruck</h2>
        <p className="muted">Für den Reifendruck fehlen noch: {missing.join(" und ")}. Trage sie oben ein.</p>
      </section>
    );
  }
  const wet = { dry: "trocken", damp: "feucht", wet: "nass" }[t.wetness];
  return (
    <section className="panel advice">
      <h2>Reifendruck</h2>
      <div className="pressure">
        <div className="pressure-box">
          <span className="pressure-label">Vorne</span>
          <span className="pressure-bar">{fmtNum(t.front_bar)}<small>bar</small></span>
          <span className="muted">{t.front_psi} psi</span>
        </div>
        <div className="pressure-box">
          <span className="pressure-label">Hinten</span>
          <span className="pressure-bar">{fmtNum(t.rear_bar)}<small>bar</small></span>
          <span className="muted">{t.rear_psi} psi</span>
        </div>
      </div>
      <p className="muted small">
        Berechnet für {fmtNum(t.system_kg)} kg Systemgewicht (Fahrer, Rad, Gepäck), echte Reifenbreite {fmtNum(t.real_width_mm)} mm, Straße {wet}.
        Als Startwert gedacht: Im Zweifel 0,1 bis 0,2 bar anpassen, bis es sich richtig anfühlt.
      </p>
      {t.notes.length > 0 && <ul className="steps">{t.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      {t.warnings.map((w) => <p key={w} className={/Hookless|niedrig|Mountain/.test(w) ? "error" : "muted small"}>{w}</p>)}
    </section>
  );
}

export default function Advisor() {
  const saved = useMemo(loadSaved, []);
  const [defs, setDefs] = useState(null);
  const [form, setForm] = useState({
    bike_id: saved.bike_id ?? "",
    start: defaultStart(),
    duration_min: saved.duration_min ?? 120,
    intensity: saved.intensity ?? "normal",
    sensitivity: saved.sensitivity ?? "normal",
    elevation_gain_m: "",
    surface: saved.surface ?? "asphalt",
    casing: saved.casing ?? "standard",
    wetness: "auto",
    rider_kg: "",
    bike_kg: "",
    luggage_kg: saved.luggage_kg ?? 1.5,
    tire_width_mm: "",
    rim_inner_mm: "",
    tubeless: true,
    hookless: false,
    bike_type: "road",
  });
  const [place, setPlace] = useState(saved.place ?? null); // {lat, lng, name}
  const [manual, setManual] = useState(!!saved.manual);
  const [manualWx, setManualWx] = useState(saved.manualWx ?? { temp_c: 12, wind_kmh: 10, rain: "none" });
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState([]);
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [note, setNote] = useState("");

  useEffect(() => {
    api.get("/advisor/defaults").then((d) => {
      setDefs(d);
      setForm((f) => ({ ...f, rider_kg: f.rider_kg || d.weight_kg || "" }));
      if (!saved.place && d.last_location) {
        setPlace({ ...d.last_location, name: "Ort deiner letzten Fahrt" });
      }
      if (!d.weather_enabled) setManual(true);
    }).catch((e) => setError(e.message));
  }, [saved.place]);

  // Rad gewählt: Reifendaten übernehmen
  function pickBike(id) {
    const b = defs?.bikes.find((x) => String(x.id) === String(id));
    setForm((f) => ({
      ...f,
      bike_id: id,
      ...(b ? {
        bike_type: b.type,
        tire_width_mm: b.tire_width_mm ?? "",
        rim_inner_mm: b.rim_inner_mm ?? "",
        bike_kg: b.bike_weight_kg ?? "",
        tubeless: b.tubeless,
        hookless: b.hookless,
        surface: b.type === "gravel" && f.surface === "asphalt" ? "hardpack" : f.surface,
      } : {}),
    }));
  }

  useEffect(() => {
    if (defs && form.bike_id && !form.tire_width_mm) pickBike(form.bike_id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defs]);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const num = (v) => (v === "" || v == null ? null : Number(v));

  async function search(e) {
    e.preventDefault();
    if (query.trim().length < 2) return;
    setSearching(true);
    setError("");
    try {
      setHits(await api.get(`/advisor/geocode?q=${encodeURIComponent(query.trim())}`));
    } catch (err) {
      setError(err.message);
    } finally {
      setSearching(false);
    }
  }

  function useMyLocation() {
    if (!navigator.geolocation) return setError("Dein Browser kann den Standort nicht bestimmen.");
    navigator.geolocation.getCurrentPosition(
      (p) => setPlace({ lat: Math.round(p.coords.latitude * 100) / 100, lng: Math.round(p.coords.longitude * 100) / 100, name: "Dein Standort" }),
      () => setError("Der Standort konnte nicht bestimmt werden. Suche stattdessen einen Ort."),
      { timeout: 10000 },
    );
  }

  async function saveWeight() {
    try {
      await api.put("/settings/profile", { weight_kg: num(form.rider_kg) });
      setNote("Gewicht im Profil gespeichert.");
    } catch (err) {
      setError(err.message);
    }
  }

  async function submit(e) {
    e.preventDefault();
    setError("");
    setNote("");
    setBusy(true);
    try {
      const body = {
        start: form.start.length === 16 ? `${form.start}:00` : form.start,
        duration_min: Number(form.duration_min),
        intensity: form.intensity,
        sensitivity: form.sensitivity,
        elevation_gain_m: num(form.elevation_gain_m),
        bike_id: form.bike_id ? Number(form.bike_id) : null,
        bike_type: form.bike_type,
        rider_kg: num(form.rider_kg),
        bike_kg: num(form.bike_kg),
        luggage_kg: Number(form.luggage_kg) || 0,
        tire_width_mm: num(form.tire_width_mm),
        rim_inner_mm: num(form.rim_inner_mm),
        tubeless: form.tubeless,
        hookless: form.hookless,
        casing: form.casing,
        surface: form.surface,
        wetness: form.wetness,
      };
      if (manual) {
        body.manual = { temp_c: Number(manualWx.temp_c), wind_kmh: Number(manualWx.wind_kmh) || 0, rain: manualWx.rain };
      } else {
        if (!place) throw new Error("Bitte wähle einen Ort oder gib das Wetter von Hand ein.");
        body.lat = place.lat;
        body.lng = place.lng;
      }
      setResult(await api.post("/advisor/plan", body));
      try {
        localStorage.setItem(STORE, JSON.stringify({
          bike_id: form.bike_id, duration_min: form.duration_min, intensity: form.intensity, sensitivity: form.sensitivity,
          surface: form.surface, casing: form.casing, luggage_kg: form.luggage_kg, place, manual, manualWx,
        }));
      } catch { /* ohne Speicher weiter */ }
    } catch (err) {
      setError(err.message);
      setResult(null);
    } finally {
      setBusy(false);
    }
  }

  if (!defs && !error) return <p className="muted">Lade …</p>;

  return (
    <>
      <header className="page-head"><h1>Ratgeber</h1></header>
      <p className="muted">Sag BikeHelper, wann und wie lange du fahren willst. Du bekommst den passenden Reifendruck und eine Kleidungsempfehlung für das Wetter der Tour.</p>

      <form className="panel" onSubmit={submit}>
        <h2>Deine Tour</h2>
        <div className="form-grid">
          <label>
            Rad
            <select value={form.bike_id} onChange={(e) => pickBike(e.target.value)}>
              <option value="">Ohne Rad (Angaben von Hand)</option>
              {defs?.bikes.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
          <label>
            Start (Ortszeit)
            <input type="datetime-local" value={form.start} onChange={set("start")} required />
          </label>
          <label>
            Dauer
            <select value={form.duration_min} onChange={set("duration_min")}>
              {DURATIONS.map(([m, l]) => <option key={m} value={m}>{l}</option>)}
              {!DURATIONS.some(([m]) => m === Number(form.duration_min)) && <option value={form.duration_min}>{form.duration_min} Min.</option>}
            </select>
          </label>
          <label>
            Tempo
            <select value={form.intensity} onChange={set("intensity")}>
              <option value="easy">Locker, Grundlage oder Ausflug</option>
              <option value="normal">Normal</option>
              <option value="hard">Zügig oder hart (Intervalle, Rennen)</option>
            </select>
          </label>
          <label>
            Kälteempfinden
            <select value={form.sensitivity} onChange={set("sensitivity")}>
              <option value="cold">Ich friere schnell</option>
              <option value="normal">Normal</option>
              <option value="warm">Ich schwitze schnell</option>
            </select>
          </label>
          <label>
            Höhenmeter (optional)
            <input type="number" min="0" step="50" value={form.elevation_gain_m} onChange={set("elevation_gain_m")} placeholder="z. B. 800" />
          </label>
        </div>

        <h3 style={{ margin: "1.5rem 0 0.75rem" }}>Ort und Wetter</h3>
        {!manual ? (
          <>
            <p>
              {place ? <>Ort: <strong>{place.name}</strong> <span className="muted small">({place.lat}, {place.lng})</span></> : <span className="muted">Noch kein Ort gewählt.</span>}
            </p>
            <div className="inline-form" style={{ marginTop: 0 }}>
              <label className="grow">
                Ort suchen
                <input value={query} onChange={(e) => setQuery(e.target.value)} placeholder="z. B. Hamburg" />
              </label>
              <button type="button" className="btn" onClick={search} disabled={searching}>{searching ? "Suche …" : "Suchen"}</button>
              <button type="button" className="btn" onClick={useMyLocation}>Mein Standort</button>
            </div>
            {hits.length > 0 && (
              <ul className="gear-list">
                {hits.map((h) => (
                  <li key={`${h.lat},${h.lng}`}>
                    <span>{h.name}</span>
                    <button type="button" className="btn small" onClick={() => { setPlace({ lat: Math.round(h.lat * 100) / 100, lng: Math.round(h.lng * 100) / 100, name: h.name }); setHits([]); setQuery(""); }}>Wählen</button>
                  </li>
                ))}
              </ul>
            )}
            <p className="hint">Es werden nur der gerundete Ort und die Zeit an Open-Meteo gesendet. Die Vorhersage reicht 15 Tage voraus.</p>
          </>
        ) : (
          <div className="form-grid">
            <label>Temperatur (°C)<input type="number" step="0.5" value={manualWx.temp_c} onChange={(e) => setManualWx({ ...manualWx, temp_c: e.target.value })} required /></label>
            <label>Wind (km/h)<input type="number" min="0" value={manualWx.wind_kmh} onChange={(e) => setManualWx({ ...manualWx, wind_kmh: e.target.value })} /></label>
            <label>
              Regen
              <select value={manualWx.rain} onChange={(e) => setManualWx({ ...manualWx, rain: e.target.value })}>
                <option value="none">Trocken</option>
                <option value="light">Leichter Regen oder Schauer</option>
                <option value="heavy">Regen</option>
              </select>
            </label>
          </div>
        )}
        {defs?.weather_enabled && (
          <label className="check" style={{ marginTop: "0.75rem" }}>
            <input type="checkbox" checked={manual} onChange={(e) => setManual(e.target.checked)} />
            Wetter selbst eingeben, statt die Vorhersage zu nutzen
          </label>
        )}

        <h3 style={{ margin: "1.5rem 0 0.75rem" }}>Reifen und Gewicht</h3>
        <div className="form-grid">
          <label>
            Dein Gewicht (kg)
            <input type="number" min="30" max="250" step="0.5" value={form.rider_kg} onChange={set("rider_kg")} placeholder="z. B. 75" />
            <button type="button" className="link small" onClick={saveWeight} style={{ textAlign: "left" }}>Im Profil speichern</button>
          </label>
          <label>
            Rad (kg)
            <input type="number" min="3" max="40" step="0.1" value={form.bike_kg} onChange={set("bike_kg")} placeholder="Leer = typisch für den Radtyp" />
          </label>
          <label>
            Gepäck, Flaschen, Kleidung (kg)
            <input type="number" min="0" step="0.5" value={form.luggage_kg} onChange={set("luggage_kg")} />
          </label>
          <label>
            Reifenbreite (mm)
            <input type="number" min="18" max="80" value={form.tire_width_mm} onChange={set("tire_width_mm")} placeholder="z. B. 28" />
          </label>
          <label>
            Innenweite der Felge (mm)
            <input type="number" min="12" max="40" step="0.5" value={form.rim_inner_mm} onChange={set("rim_inner_mm")} placeholder="Leer = typisch" />
          </label>
          <label>
            Untergrund
            <select value={form.surface} onChange={set("surface")}>
              <option value="asphalt">Glatter Asphalt</option>
              <option value="rough">Rauer Asphalt, Pflaster</option>
              <option value="hardpack">Fester Schotter, Waldweg</option>
              <option value="gravel">Lockerer Schotter</option>
              <option value="chunky">Grober Schotter, Trail</option>
            </select>
          </label>
          <label>
            Reifenkarkasse
            <select value={form.casing} onChange={set("casing")}>
              <option value="supple">Dünn, geschmeidig (Rennreifen)</option>
              <option value="standard">Normal</option>
              <option value="stiff">Pannenschutz, steif</option>
            </select>
          </label>
          <label>
            Straße
            <select value={form.wetness} onChange={set("wetness")}>
              <option value="auto">Nach dem Wetter</option>
              <option value="dry">Trocken</option>
              <option value="damp">Feucht</option>
              <option value="wet">Nass</option>
            </select>
          </label>
          <div className="checks">
            <label className="check"><input type="checkbox" checked={form.tubeless} onChange={(e) => setForm({ ...form, tubeless: e.target.checked })} /> Tubeless</label>
            <label className="check"><input type="checkbox" checked={form.hookless} onChange={(e) => setForm({ ...form, hookless: e.target.checked })} /> Hookless-Felgen</label>
          </div>
        </div>
        {defs && defs.bikes.length === 0 && <p className="hint">Tipp: Lege in der <Link to="/">Garage</Link> ein Rad mit Reifenbreite an, dann füllt sich vieles von selbst.</p>}

        {error && <p className="error" role="alert">{error}</p>}
        {note && <p className="ok" role="status">{note}</p>}
        <div className="actions">
          <button className="btn primary" disabled={busy}>{busy ? "Berechne …" : "Empfehlung berechnen"}</button>
        </div>
      </form>

      {result && (
        <>
          <ClothingCard c={result.clothing} />
          <TiresCard t={result.tires} missing={result.tires_missing} />
          <WeatherCard w={result.weather} />
          <p className="muted small">
            Alle Werte sind Richtwerte. Reifendruck: Formel nach Frank Bertos 15-%-Regel mit Zuschlägen für Untergrund und Nässe.
            Kleidung: Mittel aus gängigen Temperaturtabellen. Die Quellen stehen in der README.
          </p>
        </>
      )}
    </>
  );
}
