import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { BIKE_TYPES, WEATHER_TEXT, api, fmtNum } from "../api.js";
import BikeIllustration from "../components/BikeIllustration.jsx";
import { GroupIcon, Segmented, Slider, StopSlider, Switch } from "../components/controls.jsx";
import { CountUp, useTween } from "../components/motion.jsx";
import { Loading } from "../components/feedback.jsx";

const STORE = "bikehelper_advisor_v2";
const TYPICAL_WIDTH = { road: 28, gravel: 40, mtb: 58, other: 38 };

const SURFACES = [
  { value: "asphalt", label: "Glatter Asphalt", short: "Asphalt" },
  { value: "rough", label: "Rauer Asphalt, Pflaster", short: "Rau" },
  { value: "hardpack", label: "Fester Schotter, Waldweg", short: "Fest" },
  { value: "gravel", label: "Lockerer Schotter", short: "Locker" },
  { value: "chunky", label: "Grober Schotter, Trail", short: "Grob" },
];
// Standard je Radtyp: Untergrund und Durchschnittsgeschwindigkeit (das "normale" Tempo des Radtyps im Backend)
const SURFACE_DEFAULT = { road: "asphalt", gravel: "hardpack", mtb: "chunky", other: "asphalt" };
const SPEED_DEFAULT = { road: 27, gravel: 23, mtb: 19, other: 21 };
const speedHint = (speed, type) => {
  const d = speed - (SPEED_DEFAULT[type] ?? 25);
  if (d <= -3) return "Lockeres Tempo: Du erzeugst weniger Wärme, die Kleidung fällt wärmer aus.";
  if (d >= 3) return "Zügiges Tempo: Dir wird wärmer, die Kleidung fällt leichter aus.";
  return "Normales Tempo für dieses Rad.";
};
const SENSITIVITIES = [
  { value: "cold", label: "Ich friere schnell", short: "Friert schnell" },
  { value: "normal", label: "Normal" },
  { value: "warm", label: "Ich schwitze schnell", short: "Schwitzt schnell" },
];
const RAINS = [
  { value: "none", label: "Trocken" },
  { value: "light", label: "Leichter Regen", short: "Schauer" },
  { value: "heavy", label: "Regen" },
];

const pad = (n) => String(n).padStart(2, "0");
const isoDay = (offset) => {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};
const dayLabel = (offset) => {
  if (offset === 0) return "Heute";
  if (offset === 1) return "Morgen";
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return d.toLocaleDateString("de-DE", { weekday: "short", day: "numeric", month: "numeric" });
};
const fmtClock = (min) => `${pad(Math.floor(min / 60))}:${pad(min % 60)} Uhr`;
const nowMinutes = () => {
  const d = new Date();
  return Math.min(1435, Math.floor((d.getHours() * 60 + d.getMinutes()) / 5) * 5);
};
const fmtDur = (m) => {
  const h = Math.floor(m / 60);
  const r = m % 60;
  if (!h) return `${r} Min.`;
  return r ? `${h} Std. ${r} Min.` : `${h} Std.`;
};

function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(STORE) || "{}");
  } catch {
    return {};
  }
}

// ---------- Anzeigen ----------

const ARC = { cx: 60, cy: 60, r: 46, start: 135, sweep: 270 };
const polar = (deg) => [ARC.cx + ARC.r * Math.cos((deg * Math.PI) / 180), ARC.cy + ARC.r * Math.sin((deg * Math.PI) / 180)];
const ARC_PATH = (() => {
  const [x0, y0] = polar(ARC.start);
  const [x1, y1] = polar(ARC.start + ARC.sweep);
  return `M${x0} ${y0} A${ARC.r} ${ARC.r} 0 1 1 ${x1} ${y1}`;
})();
const BAR_MIN = 0.5;
const BAR_MAX = 8;

function Dial({ label, bar, psi }) {
  const frac = Math.min(1, Math.max(0, (bar - BAR_MIN) / (BAR_MAX - BAR_MIN)));
  const shown = useTween(bar);
  const [kx, ky] = polar(ARC.start);
  const ticks = Array.from({ length: 16 }, (_, i) => i);
  return (
    <div className="dial">
      <svg viewBox="0 0 120 112" role="img" aria-label={`${label}: ${fmtNum(bar)} bar`}>
        {ticks.map((i) => {
          const a = ARC.start + (ARC.sweep * i) / 15;
          const [ax, ay] = [ARC.cx + 54 * Math.cos((a * Math.PI) / 180), ARC.cy + 54 * Math.sin((a * Math.PI) / 180)];
          const [bx, by] = [ARC.cx + (i % 5 === 0 ? 50 : 52) * Math.cos((a * Math.PI) / 180), ARC.cy + (i % 5 === 0 ? 50 : 52) * Math.sin((a * Math.PI) / 180)];
          return <line key={i} x1={ax} y1={ay} x2={bx} y2={by} className="dial-tick" />;
        })}
        <path d={ARC_PATH} className="dial-track" />
        <path d={ARC_PATH} className="dial-fill" pathLength="1" style={{ strokeDashoffset: 1 - frac }} />
        <g className="dial-knob" style={{ transform: `rotate(${ARC.sweep * frac}deg)`, transformOrigin: `${ARC.cx}px ${ARC.cy}px` }}>
          <circle cx={kx} cy={ky} r="5.5" />
        </g>
      </svg>
      <div className="dial-read">
        <span className="dial-label">{label}</span>
        <span className="dial-num">{fmtNum(shown, 1)}<small>bar</small></span>
        <span className="muted small">{psi} psi</span>
      </div>
    </div>
  );
}

function TiresResult({ t, missing }) {
  if (!t) {
    return (
      <section className="panel result-card">
        <h2>Reifendruck</h2>
        <p className="muted">
          {missing.length ? `Dafür fehlt noch: ${missing.join(" und ")}. Stelle es links ein.` : "Stelle links Gewicht und Reifenbreite ein."}
        </p>
      </section>
    );
  }
  const wet = { dry: "trocken", damp: "feucht", wet: "nass" }[t.wetness];
  return (
    <section className="panel result-card">
      <h2>Reifendruck</h2>
      <div className="dials">
        <Dial label="Vorne" bar={t.front_bar} psi={t.front_psi} />
        <Dial label="Hinten" bar={t.rear_bar} psi={t.rear_psi} />
      </div>
      <p className="muted small">
        Gerechnet mit {fmtNum(t.system_kg)} kg Systemgewicht und {fmtNum(t.real_width_mm)} mm echter Reifenbreite, Straße {wet}. Ein Startwert:
        Passe ihn um 0,1 bis 0,2 bar an, bis es sich richtig anfühlt.
      </p>
      {t.notes.length > 0 && <ul className="steps">{t.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      {t.warnings.map((w) => <p key={w} className={/Hookless|niedrig|Mountain/.test(w) ? "error" : "muted small"}>{w}</p>)}
    </section>
  );
}

const SCALE_MIN = -4;
const SCALE_MAX = 30;

function ThermoScale({ temp }) {
  const pct = Math.min(100, Math.max(0, ((temp - SCALE_MIN) / (SCALE_MAX - SCALE_MIN)) * 100));
  return (
    <div className="thermo" role="img" aria-label={`Gefühlte Temperatur ${fmtNum(temp, 0)} Grad`}>
      <div className="thermo-bar" />
      <div className="thermo-marker" style={{ left: `${pct}%` }}>
        <span>{fmtNum(temp, 0)} °C</span>
      </div>
      <div className="thermo-ends"><span>kalt</span><span>warm</span></div>
    </div>
  );
}

function ClothingResult({ c }) {
  return (
    <section className="panel result-card">
      <h2>Das ziehst du an</h2>
      <p className="advice-headline" key={c.headline}>{c.headline}</p>
      <ThermoScale temp={c.effective_temp} />
      <p className="muted small">Es fühlt sich für diese Fahrt an wie {fmtNum(c.effective_temp, 0)} °C. Oben {c.top.toLowerCase()}, unten {c.legs.toLowerCase()}.</p>
      {c.warnings.map((w) => <p key={w} className="error" role="alert">{w}</p>)}
      <div className="advice-groups">
        {Object.entries(c.groups).map(([name, items], i) => (
          <div key={`${name}:${items.join("|")}`} className="advice-group" style={{ "--i": i }}>
            <h3><GroupIcon name={name} />{name}</h3>
            <ul>{items.map((it) => <li key={it}>{it}</li>)}</ul>
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

function WeatherStrip({ hours }) {
  const temps = hours.map((h) => h.temp).filter((v) => v != null);
  const lo = Math.min(...temps) - 3;
  const hi = Math.max(...temps) + 3;
  const maxRain = Math.max(0.5, ...hours.map((h) => h.precip || 0));
  return (
    <div className="scroll-x">
    <div className="wx-strip" role="img" aria-label="Wetter Stunde für Stunde">
      {hours.map((h, i) => (
        <div key={h.time} className="wx-col" style={{ "--i": i }} title={`${h.time}: ${fmtNum(h.temp, 0)} °C, ${fmtNum(h.precip)} mm, Wind ${fmtNum(h.wind, 0)} km/h`}>
          <span className="wx-temp">{fmtNum(h.temp, 0)}°</span>
          <span className="wx-track"><span className="wx-bar" style={{ height: `${Math.max(8, ((h.temp - lo) / (hi - lo)) * 100)}%` }} /></span>
          <span className="wx-rain"><span style={{ height: `${Math.min(100, ((h.precip || 0) / maxRain) * 100)}%` }} /></span>
          <span className="wx-wind">{fmtNum(h.wind, 0)}</span>
          <span className="wx-time">{h.time.slice(0, 2)}</span>
        </div>
      ))}
    </div>
    <p className="hint">Säulen zeigen die Temperatur, blaue Balken den Regen. Darunter stehen Wind in km/h und die Uhrzeit.</p>
    </div>
  );
}

function WeatherResult({ w }) {
  const text = WEATHER_TEXT(w.weather_code);
  return (
    <section className="panel result-card">
      <h2>Wetter während der Tour</h2>
      <p className="muted small">
        {w.source === "forecast" ? "Vorhersage von Open-Meteo, Ortszeit des Startorts." : "Deine Angaben, ohne Vorhersage."}
      </p>
      <div className="kpis" style={{ marginBottom: 0 }}>
        <div className="kpi">
          <div className="kpi-value"><CountUp value={w.temp_avg} /><small>°C</small></div>
          <div className="kpi-label">
            {w.temp_min != null && w.temp_max != null && Math.round(w.temp_min) !== Math.round(w.temp_max)
              ? `${fmtNum(w.temp_min, 0)} bis ${fmtNum(w.temp_max, 0)} °C` : "Ø Temperatur"}{text ? `, ${text}` : ""}
          </div>
        </div>
        <div className="kpi">
          <div className="kpi-value"><CountUp value={w.precip_mm} digits={1} /><small>mm</small></div>
          <div className="kpi-label">Regen{w.precip_prob != null ? `, bis ${Math.round(w.precip_prob)} % Wahrscheinlichkeit` : ""}</div>
        </div>
        <div className="kpi">
          <div className="kpi-value"><CountUp value={w.wind_kmh} /><small>km/h</small></div>
          <div className="kpi-label">Wind{w.gust_kmh != null ? `, Böen bis ${fmtNum(w.gust_kmh, 0)}` : ""}</div>
        </div>
        {w.dark_minutes > 0 && (
          <div className="kpi">
            <div className="kpi-value"><CountUp value={Math.round(w.dark_minutes)} /><small>min</small></div>
            <div className="kpi-label">in der Dunkelheit</div>
          </div>
        )}
      </div>
      {w.hours?.length > 0 && <WeatherStrip hours={w.hours} />}
    </section>
  );
}

// ---------- Rad wählen ----------

function PickCard({ type, title, sub, selected, onClick, tireMm }) {
  return (
    <button type="button" role="radio" aria-checked={selected} className={`pick ${selected ? "on" : ""}`} onClick={onClick}>
      <BikeIllustration type={type} tireMm={tireMm} className="pick-ill" />
      <span className="pick-title">{title}</span>
      {sub && <span className="pick-sub">{sub}</span>}
    </button>
  );
}

/** Angaben, die vom gewählten Rad aus der Garage kommen. */
const TYPICAL_BIKE_KG = { road: 8, gravel: 10, mtb: 13, other: 11 };

const CASING_NAME = { supple: "dünn, geschmeidig", standard: "normal", stiff: "Pannenschutz" };

function GarageFacts({ bike }) {
  const set = bike.tire_set;
  const width = set?.width_mm ?? bike.tire_width_mm;
  const rows = [
    {
      label: "Reifen",
      value: set ? `${set.name}${set.width_mm ? `, ${fmtNum(set.width_mm, 0)} mm` : ""}${bike.tubeless === false ? ", mit Schlauch" : ", tubeless"}` : width ? `${fmtNum(width, 0)} mm` : null,
      missing: "Kein Reifensatz montiert",
    },
    {
      label: "Karkasse",
      value: set?.casing ? CASING_NAME[set.casing] : null,
      missing: set ? "nicht eingetragen, gerechnet wird mit normal" : "kein Reifensatz montiert",
    },
    {
      label: "Gewicht des Rads",
      value: bike.bike_weight_kg ? `${fmtNum(bike.bike_weight_kg)} kg` : null,
      missing: `nicht eingetragen, gerechnet wird mit ${TYPICAL_BIKE_KG[bike.type] ?? 11} kg`,
    },
    {
      label: "Innenweite der Felge",
      value: bike.rim_inner_mm ? `${fmtNum(bike.rim_inner_mm)} mm${bike.hookless ? ", hookless" : ""}` : null,
      missing: "nicht eingetragen, gerechnet wird mit einem typischen Wert",
    },
  ];
  return (
    <div className="garage-facts">
      <div className="garage-facts-head">
        <span className="field-label">Aus der Garage</span>
        <Link className="link small" to={`/bikes/${bike.id}`}>Ändern</Link>
      </div>
      <dl>
        {rows.map((r) => (
          <div key={r.label} className={r.value ? "" : "missing"}>
            <dt>{r.label}</dt>
            <dd>{r.value ?? r.missing}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

// ---------- Seite ----------

export default function Advisor() {
  const saved = useMemo(loadSaved, []);
  const [defs, setDefs] = useState(null);
  const [form, setForm] = useState({
    bike_id: saved.bike_id ?? "",
    bike_type: saved.bike_type ?? "road",
    day: 0,
    minutes: nowMinutes(),
    duration_min: saved.duration_min ?? 120,
    speed: SPEED_DEFAULT[saved.bike_type ?? "road"],
    sensitivity: saved.sensitivity ?? "normal",
    elevation_gain_m: "",
    surface: SURFACE_DEFAULT[saved.bike_type ?? "road"],
    casing: saved.casing ?? "standard",
    wetness: "auto",
    rider_kg: saved.rider_kg ?? "",
    bike_kg: "",
    luggage_kg: saved.luggage_kg ?? 1.5,
    tire_width_mm: saved.tire_width_mm ?? TYPICAL_WIDTH[saved.bike_type ?? "road"],
    rim_inner_mm: "",
    tubeless: true,
    hookless: false,
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
  const reqId = useRef(0);

  const patch = (p) => setForm((f) => ({ ...f, ...p }));

  useEffect(() => {
    api.get("/advisor/defaults").then((d) => {
      setDefs(d);
      setForm((f) => ({ ...f, rider_kg: f.rider_kg === "" ? (d.weight_kg ?? "") : f.rider_kg }));
      if (!saved.place && d.last_location) setPlace({ ...d.last_location, name: "Ort deiner letzten Fahrt" });
      if (!d.weather_enabled) setManual(true);
    }).catch((e) => setError(e.message));
  }, [saved.place]);

  function applyBike(b) {
    patch({
      bike_id: b.id,
      bike_type: b.type,
      tire_width_mm: b.tire_set?.width_mm ?? b.tire_width_mm ?? TYPICAL_WIDTH[b.type] ?? 28,
      rim_inner_mm: b.rim_inner_mm ?? "",
      bike_kg: b.bike_weight_kg ?? "",
      tubeless: b.tubeless,
      hookless: b.hookless,
      casing: b.tire_set?.casing ?? "standard",
      surface: SURFACE_DEFAULT[b.type] ?? "asphalt",
      speed: SPEED_DEFAULT[b.type] ?? 25,
    });
  }

  function pickOther() {
    patch({ bike_id: "", bike_kg: "", rim_inner_mm: "", tubeless: true, hookless: false });
  }

  function pickType(type) {
    patch({
      bike_type: type,
      tire_width_mm: TYPICAL_WIDTH[type],
      surface: SURFACE_DEFAULT[type] ?? "asphalt",
      speed: SPEED_DEFAULT[type] ?? 25,
    });
  }

  // gespeichertes Rad nach dem Laden der Daten übernehmen
  const applied = useRef(false);
  useEffect(() => {
    if (!defs || applied.current) return;
    applied.current = true;
    const b = defs.bikes.find((x) => String(x.id) === String(form.bike_id));
    if (b) applyBike(b);
    else if (form.bike_id) patch({ bike_id: "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [defs]);

  const num = (v) => (v === "" || v == null ? null : Number(v));
  const garageBike = defs?.bikes?.find((x) => String(x.id) === String(form.bike_id));
  const garageCasing = garageBike?.tire_set?.casing ?? null;

  // Anfrage aus dem Formular; fehlt noch der Ort, gibt es keine
  const request = useMemo(() => {
    const date = isoDay(form.day);
    const body = {
      start: `${date}T${pad(Math.floor(form.minutes / 60))}:${pad(form.minutes % 60)}:00`,
      duration_min: Number(form.duration_min),
      avg_speed_kmh: Number(form.speed),
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
      casing: garageCasing ? null : form.casing, // aus der Garage, sonst die Auswahl hier
      surface: form.surface,
      wetness: form.wetness,
    };
    if (manual) {
      body.manual = { temp_c: Number(manualWx.temp_c), wind_kmh: Number(manualWx.wind_kmh) || 0, rain: manualWx.rain };
    } else if (place) {
      body.lat = place.lat;
      body.lng = place.lng;
    } else {
      return null;
    }
    return body;
  }, [form, manual, manualWx, place, garageCasing]);

  const requestKey = JSON.stringify(request);

  // Ergebnis live nachführen, kurz nachdem sich ein Regler beruhigt hat
  useEffect(() => {
    if (!defs || !request) {
      setResult(null);
      return undefined;
    }
    const id = ++reqId.current;
    setBusy(true);
    const timer = setTimeout(async () => {
      try {
        const r = await api.post("/advisor/plan", request);
        if (id !== reqId.current) return;
        setResult(r);
        setError("");
      } catch (err) {
        if (id !== reqId.current) return;
        setError(err.message);
        setResult(null);
      } finally {
        if (id === reqId.current) setBusy(false);
      }
    }, 450);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requestKey, defs]);

  useEffect(() => {
    try {
      localStorage.setItem(STORE, JSON.stringify({
        bike_id: form.bike_id, bike_type: form.bike_type, duration_min: form.duration_min,
        sensitivity: form.sensitivity, casing: form.casing, luggage_kg: form.luggage_kg,
        rider_kg: form.rider_kg, place, manual, manualWx,
      }));
    } catch { /* ohne Speicher weiter */ }
  }, [form, place, manual, manualWx]);

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

  if (!defs && !error) return <Loading />;

  const bikes = defs?.bikes ?? [];
  const showTypes = !form.bike_id;
  const bike = bikes.find((b) => String(b.id) === String(form.bike_id)) ?? null;
  const widthKnown = !!(bike && (bike.tire_set?.width_mm ?? bike.tire_width_mm));

  return (
    <>
      <header className="page-head"><h1>Ratgeber</h1></header>
      <p className="muted lead">Stelle deine Tour ein. Reifendruck und Kleidung passen sich sofort an.</p>

      <div className="advisor">
        <div className="advisor-controls">
          <section className="panel stage">
            <div className="pick-row" role="radiogroup" aria-label="Dein Rad">
              {bikes.map((b) => (
                <PickCard
                  key={b.id} type={b.type} title={b.name} sub={BIKE_TYPES[b.type]} tireMm={b.tire_width_mm}
                  selected={String(form.bike_id) === String(b.id)} onClick={() => applyBike(b)}
                />
              ))}
              {bikes.length > 0 && (
                <PickCard type={form.bike_id ? "other" : form.bike_type} title="Anderes Rad" sub="Radtyp wählen" selected={!form.bike_id} onClick={pickOther} />
              )}
            </div>
            {showTypes && (
              <div className="pick-row types" role="radiogroup" aria-label="Radtyp">
                {Object.entries(BIKE_TYPES).map(([k, v]) => (
                  <PickCard key={k} type={k} title={v} selected={form.bike_type === k} onClick={() => pickType(k)} />
                ))}
              </div>
            )}

            <div className="stage-controls">
              {!widthKnown && (
                <Slider
                  label="Reifenbreite" value={form.tire_width_mm} onChange={(v) => patch({ tire_width_mm: v })} min={23} max={65}
                  format={(v) => `${v} mm`} marks={["23", "35", "50", "65"]}
                  hint={bike ? "Für dieses Rad ist kein Reifensatz montiert. Trage ihn in der Garage ein, dann gilt seine Breite automatisch." : undefined}
                />
              )}
              {bike && <GarageFacts bike={bike} />}
              <StopSlider label="Untergrund" value={form.surface} onChange={(v) => patch({ surface: v })} options={SURFACES} />
            </div>
            {bikes.length === 0 && <p className="hint">Tipp: Lege in der <Link to="/garage">Garage</Link> ein Rad mit Reifenbreite an, dann füllt sich vieles von selbst.</p>}
          </section>

          <section className="panel">
            <h2>Die Tour</h2>
            <div className="field-label">Tag</div>
            <div className="chips" role="radiogroup" aria-label="Tag">
              {Array.from({ length: 7 }, (_, i) => (
                <button key={i} type="button" role="radio" aria-checked={form.day === i} className={`chip ${form.day === i ? "on" : ""}`} onClick={() => patch({ day: i })}>
                  {dayLabel(i)}
                </button>
              ))}
            </div>
            <div className="slider-stack">
              <div>
                <Slider label="Start" value={form.minutes} onChange={(v) => patch({ minutes: v })} min={0} max={1435} step={5} format={fmtClock} marks={["0 Uhr", "12 Uhr", "24 Uhr"]} />
                <button type="button" className="link small" onClick={() => patch({ day: 0, minutes: nowMinutes() })}>Auf jetzt setzen</button>
              </div>
              <Slider label="Dauer" value={form.duration_min} onChange={(v) => patch({ duration_min: v })} min={30} max={600} step={15} format={fmtDur} marks={["30 Min.", "5 Std.", "10 Std."]} />
              <Slider label="Durchschnittsgeschwindigkeit" value={form.speed} onChange={(v) => patch({ speed: v })} min={8} max={45} step={1} format={(v) => `${v} km/h`} hint={speedHint(form.speed, form.bike_type)} />
              <StopSlider label="Kälteempfinden" value={form.sensitivity} onChange={(v) => patch({ sensitivity: v })} options={SENSITIVITIES} />
              <Slider label="Höhenmeter" optional autoText="nicht angegeben" fallback={0} value={form.elevation_gain_m} onChange={(v) => patch({ elevation_gain_m: v })} min={0} max={3000} step={50} format={(v) => `${v} m`} />
            </div>
          </section>

          <section className="panel">
            <h2>Ort und Wetter</h2>
            {!manual ? (
              <>
                <p className="place">
                  {place ? <><strong>{place.name}</strong> <span className="muted small">({place.lat}, {place.lng})</span></> : <span className="muted">Noch kein Ort gewählt.</span>}
                </p>
                <form className="search-row" onSubmit={search}>
                  <input type="search" value={query} onChange={(e) => setQuery(e.target.value)} placeholder="Ort suchen, z. B. Hamburg" aria-label="Ort suchen" />
                  <button className="btn" disabled={searching}>{searching ? "Suche …" : "Suchen"}</button>
                  <button type="button" className="btn" onClick={useMyLocation}>Mein Standort</button>
                </form>
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
              <div className="slider-stack">
                <Slider label="Temperatur" value={Number(manualWx.temp_c)} onChange={(v) => setManualWx({ ...manualWx, temp_c: v })} min={-15} max={40} step={0.5} format={(v) => `${fmtNum(v)} °C`} />
                <Slider label="Wind" value={Number(manualWx.wind_kmh)} onChange={(v) => setManualWx({ ...manualWx, wind_kmh: v })} min={0} max={70} step={1} format={(v) => `${v} km/h`} />
                <StopSlider label="Regen" value={manualWx.rain} onChange={(v) => setManualWx({ ...manualWx, rain: v })} options={RAINS} />
              </div>
            )}
            {defs?.weather_enabled && (
              <div style={{ marginTop: "1rem" }}>
                <Switch checked={manual} onChange={setManual}>Wetter selbst einstellen, statt die Vorhersage zu nutzen</Switch>
              </div>
            )}
          </section>

          <section className="panel">
            <h2>Gewicht und Reifen</h2>
            <div className="slider-stack">
              <Slider label="Dein Gewicht" optional autoText="noch nicht angegeben" fallback={75} value={form.rider_kg} onChange={(v) => patch({ rider_kg: v })} min={40} max={140} step={0.5} format={(v) => `${fmtNum(v)} kg`} />
              {form.rider_kg !== "" && <button type="button" className="link small save-weight" onClick={saveWeight}>Im Profil speichern</button>}
              <Slider label="Gepäck, Flaschen, Kleidung" value={Number(form.luggage_kg)} onChange={(v) => patch({ luggage_kg: v })} min={0} max={12} step={0.5} format={(v) => `${fmtNum(v)} kg`} />
              {!bike && (
                <>
                  <Slider label="Gewicht des Rads" optional autoText="typisch für den Radtyp" fallback={form.bike_type === "mtb" ? 13 : 9} value={form.bike_kg} onChange={(v) => patch({ bike_kg: v })} min={6} max={22} step={0.1} format={(v) => `${fmtNum(v)} kg`} />
                  <Slider label="Innenweite der Felge" optional autoText="typisch für den Radtyp" fallback={form.bike_type === "road" ? 19 : 24} value={form.rim_inner_mm} onChange={(v) => patch({ rim_inner_mm: v })} min={15} max={32} step={0.5} format={(v) => `${fmtNum(v)} mm`} />
                </>
              )}
            </div>
            {!garageCasing && (
              <>
                <Segmented
                  label="Reifenkarkasse"
                  value={form.casing}
                  onChange={(v) => patch({ casing: v })}
                  options={[{ value: "supple", label: "Dünn, geschmeidig" }, { value: "standard", label: "Normal" }, { value: "stiff", label: "Pannenschutz" }]}
                />
                <p className="hint">
                  Die Karkasse ist das Gewebe unter dem Profil: dünne, geschmeidige brauchen etwas weniger Druck, Pannenschutz-Karkassen etwas mehr.
                  {bike ? " Trage sie am Reifensatz in der Garage ein, dann gilt sie hier automatisch." : ""}
                </p>
              </>
            )}
            <Segmented
              label="Straße"
              value={form.wetness}
              onChange={(v) => patch({ wetness: v })}
              options={[{ value: "auto", label: "Nach Wetter" }, { value: "dry", label: "Trocken" }, { value: "damp", label: "Feucht" }, { value: "wet", label: "Nass" }]}
            />
            {!bike && (
              <div className="switch-row">
                <Switch checked={form.tubeless} onChange={(v) => patch({ tubeless: v })}>Tubeless</Switch>
                <Switch checked={form.hookless} onChange={(v) => patch({ hookless: v })}>Hookless-Felgen</Switch>
              </div>
            )}
          </section>
        </div>

        <div className={`advisor-results ${busy ? "is-busy" : ""}`} aria-live="polite">
          {error && <p className="error" role="alert">{error}</p>}
          {note && <p className="ok" role="status">{note}</p>}
          {!request && !manual && (
            <section className="panel result-card">
              <h2>Wo fährst du?</h2>
              <p className="muted">Wähle einen Ort, damit BikeHelper das Wetter der Tour abfragen kann. Oder stelle das Wetter selbst ein.</p>
            </section>
          )}
          {result && (
            <>
              <TiresResult t={result.tires} missing={result.tires_missing} />
              <ClothingResult c={result.clothing} />
              <WeatherResult w={result.weather} />
              <p className="muted small">
                Alle Werte sind Richtwerte. Reifendruck: Formel nach Frank Bertos 15-%-Regel mit Zuschlägen für Untergrund und Nässe.
                Kleidung: Mittel aus gängigen Temperaturtabellen. Die Quellen stehen in der README.
              </p>
            </>
          )}
          {request && !result && !error && <p className="muted">Berechne …</p>}
        </div>
      </div>
    </>
  );
}
