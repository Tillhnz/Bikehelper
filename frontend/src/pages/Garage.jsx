import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BIKE_TYPES, api } from "../api.js";
import { EmptyState, Odometer, StatusPill } from "../components/ui.jsx";

function BikeForm({ onCreated, onCancel }) {
  const [form, setForm] = useState({ name: "", type: "road", brand: "", model: "", start_km: 0, with_defaults: true });
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post("/bikes", {
        ...form,
        brand: form.brand || null,
        model: form.model || null,
        start_km: Number(form.start_km) || 0,
      });
      onCreated();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="panel form-grid" onSubmit={submit}>
      <h2 className="span-all">Neues Rad</h2>
      <label>
        Name
        <input value={form.name} onChange={set("name")} placeholder="z. B. Canyon Endurace" required autoFocus />
      </label>
      <label>
        Art
        <select value={form.type} onChange={set("type")}>
          {Object.entries(BIKE_TYPES).map(([k, v]) => (
            <option key={k} value={k}>{v}</option>
          ))}
        </select>
      </label>
      <label>
        Marke
        <input value={form.brand} onChange={set("brand")} />
      </label>
      <label>
        Modell
        <input value={form.model} onChange={set("model")} />
      </label>
      <label>
        Kilometer vor der App
        <input type="number" min="0" step="1" value={form.start_km} onChange={set("start_km")} />
        <span className="hint">Bisher gefahrene Kilometer, die nicht in Strava stehen.</span>
      </label>
      <label className="check span-all">
        <input
          type="checkbox"
          checked={form.with_defaults}
          onChange={(e) => setForm({ ...form, with_defaults: e.target.checked })}
        />
        Standardkomponenten mit Wartungsintervallen anlegen (Kette, Reifen, Bremsen …)
      </label>
      {error && <p className="error span-all" role="alert">{error}</p>}
      <div className="actions span-all">
        <button className="btn primary">Rad speichern</button>
        <button type="button" className="btn" onClick={onCancel}>Abbrechen</button>
      </div>
    </form>
  );
}

export default function Garage() {
  const [bikes, setBikes] = useState(null);
  const [overview, setOverview] = useState({ items: [] });
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [b, o] = await Promise.all([api.get("/bikes"), api.get("/maintenance/overview")]);
      setBikes(b);
      setOverview(o);
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!bikes) return <p className="muted">Lade …</p>;

  const active = bikes.filter((b) => !b.retired);
  const retired = bikes.filter((b) => b.retired);

  return (
    <>
      <header className="page-head">
        <h1>Garage</h1>
        {!adding && <button className="btn primary" onClick={() => setAdding(true)}>Rad hinzufügen</button>}
      </header>

      {adding && (
        <BikeForm onCreated={() => { setAdding(false); load(); }} onCancel={() => setAdding(false)} />
      )}

      {overview.items.length > 0 && (
        <section className="panel attention">
          <h2>Das steht an</h2>
          <ul className="attention-list">
            {overview.items.map((i) => (
              <li key={`${i.component_id}-${i.rule}`}>
                <Link to={`/bikes/${i.bike_id}`}>
                  <span className="attention-main">
                    <strong>{i.rule}</strong>
                    <span className="muted"> – {i.component}{i.bike ? `, ${i.bike}` : ""}</span>
                  </span>
                  <span className="attention-meta">
                    {Math.round(i.progress * 100)} % verbraucht
                    <StatusPill status={i.status} />
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      )}

      {active.length === 0 && !adding ? (
        <EmptyState
          title="Deine Garage ist noch leer"
          text="Lege dein erstes Rad an oder importiere deinen Strava-Export, dabei werden die Räder automatisch angelegt."
        >
          <div className="actions" style={{ justifyContent: "center" }}>
            <button className="btn primary" onClick={() => setAdding(true)}>Erstes Rad anlegen</button>
            <Link className="btn" to="/rides">Fahrten importieren</Link>
          </div>
        </EmptyState>
      ) : (
        <div className="bike-grid">
          {active.map((b) => <BikeCard key={b.id} bike={b} />)}
        </div>
      )}

      {retired.length > 0 && (
        <>
          <h2 className="section-title">Ausgemustert</h2>
          <div className="bike-grid">
            {retired.map((b) => <BikeCard key={b.id} bike={b} />)}
          </div>
        </>
      )}
    </>
  );
}

function BikeCard({ bike }) {
  return (
    <Link to={`/bikes/${bike.id}`} className={`bike-card ${bike.retired ? "retired" : ""}`}>
      <div className="bike-card-head">
        <h3>{bike.name}</h3>
        <span className="muted small">
          {BIKE_TYPES[bike.type] ?? bike.type}
          {bike.brand ? ` · ${bike.brand}` : ""}
        </span>
      </div>
      <Odometer km={bike.total_km} />
      <div className="bike-card-foot">
        <span className="muted small">{bike.component_count} Komponenten</span>
        {bike.unknown_count > 0 && <span className="pill pill-unknown">{bike.unknown_count} ohne Einbaudatum</span>}
        {bike.due_count > 0 ? (
          <span className="pill pill-due">{bike.due_count} fällig</span>
        ) : (
          <span className="pill pill-ok">Alles in Ordnung</span>
        )}
      </div>
    </Link>
  );
}
