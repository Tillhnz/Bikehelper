import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { BIKE_TYPES, CATEGORIES, DEFAULT_RULES, api, fmtDate, fmtKm, today } from "../api.js";
import { EmptyState, Gauge, Odometer, StatusPill } from "../components/ui.jsx";

function ComponentForm({ bikeId, onCreated, onCancel }) {
  const [form, setForm] = useState({
    category: "chain", name: "", brand: "", installed_at: today(), start_km: 0, withRule: true,
  });
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const preset = DEFAULT_RULES[form.category];

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      const comp = await api.post("/components", {
        bike_id: bikeId,
        category: form.category,
        name: form.name,
        brand: form.brand || null,
        installed_at: form.installed_at || null,
        start_km: Number(form.start_km) || 0,
      });
      if (form.withRule && preset) await api.post(`/components/${comp.id}/rules`, preset);
      onCreated();
    } catch (err) {
      setError(err.message);
    }
  }

  const presetText = preset
    ? [preset.interval_km && `${fmtKm(preset.interval_km)} km`, preset.interval_months && `${preset.interval_months} Monate`]
        .filter(Boolean).join(" oder ")
    : "";

  return (
    <form className="panel form-grid" onSubmit={submit}>
      <h2 className="span-all">Neue Komponente</h2>
      <label>
        Kategorie
        <select value={form.category} onChange={set("category")}>
          {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <label>
        Bezeichnung
        <input value={form.name} onChange={set("name")} placeholder="z. B. KMC X11 oder Continental GP5000" required autoFocus />
      </label>
      <label>
        Marke
        <input value={form.brand} onChange={set("brand")} />
      </label>
      <label>
        Eingebaut am
        <input type="date" value={form.installed_at} onChange={set("installed_at")} />
      </label>
      <label>
        Kilometer vor dem Einbau
        <input type="number" min="0" step="1" value={form.start_km} onChange={set("start_km")} />
        <span className="hint">Nur bei gebrauchten Teilen, sonst 0.</span>
      </label>
      {preset && (
        <label className="check span-all">
          <input
            type="checkbox"
            checked={form.withRule}
            onChange={(e) => setForm({ ...form, withRule: e.target.checked })}
          />
          Wartungsregel anlegen: {preset.label} nach {presetText}
        </label>
      )}
      {error && <p className="error span-all" role="alert">{error}</p>}
      <div className="actions span-all">
        <button className="btn primary">Komponente speichern</button>
        <button type="button" className="btn" onClick={onCancel}>Abbrechen</button>
      </div>
    </form>
  );
}

function RuleRow({ rule, onDelete }) {
  const limits = [
    rule.interval_km && `${fmtKm(rule.km_since)} von ${fmtKm(rule.interval_km)} km`,
    rule.interval_months && `${rule.months_since.toLocaleString("de-DE")} von ${rule.interval_months} Monaten`,
  ].filter(Boolean).join(" · ");
  return (
    <li className="rule-row">
      <div className="rule-top">
        <strong>{rule.label}</strong>
        <StatusPill status={rule.status} />
      </div>
      <Gauge progress={rule.progress} status={rule.status} />
      <div className="rule-bottom">
        <span className="muted small">{limits}</span>
        <button className="link small" onClick={onDelete}>Regel löschen</button>
      </div>
    </li>
  );
}

function ComponentCard({ comp, onChanged }) {
  const [rules, setRules] = useState([]);
  const [logs, setLogs] = useState([]);
  const [panel, setPanel] = useState(null); // "log" | "rule" | null
  const [log, setLog] = useState({ performed_at: today(), note: "" });
  const [rule, setRule] = useState({ label: "", interval_km: "", interval_months: "" });
  const [error, setError] = useState("");

  const loadDetails = useCallback(async () => {
    const [r, l] = await Promise.all([
      api.get(`/components/${comp.id}/rules`),
      api.get(`/components/${comp.id}/logs`),
    ]);
    setRules(r);
    setLogs(l);
  }, [comp.id]);

  useEffect(() => { loadDetails().catch((e) => setError(e.message)); }, [loadDetails, comp.km]);

  async function refresh() {
    await loadDetails();
    onChanged();
  }

  async function addLog(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post(`/components/${comp.id}/logs`, { performed_at: log.performed_at, note: log.note || null });
      setPanel(null);
      setLog({ performed_at: today(), note: "" });
      await refresh();
    } catch (err) { setError(err.message); }
  }

  async function addRule(e) {
    e.preventDefault();
    setError("");
    try {
      await api.post(`/components/${comp.id}/rules`, {
        label: rule.label,
        interval_km: rule.interval_km ? Number(rule.interval_km) : null,
        interval_months: rule.interval_months ? Number(rule.interval_months) : null,
      });
      setPanel(null);
      setRule({ label: "", interval_km: "", interval_months: "" });
      await refresh();
    } catch (err) { setError(err.message); }
  }

  async function removeRule(id) {
    await api.del(`/rules/${id}`);
    await refresh();
  }

  async function retire() {
    const { id, km, status, ...rest } = comp;
    await api.put(`/components/${id}`, { ...rest, retired_at: today() });
    onChanged();
  }

  async function remove() {
    if (!window.confirm(`„${comp.name}“ wirklich löschen?`)) return;
    await api.del(`/components/${comp.id}`);
    onChanged();
  }

  const retired = !!comp.retired_at;

  return (
    <article className={`component ${retired ? "retired" : ""}`}>
      <header className="component-head">
        <div>
          <span className="muted small">{CATEGORIES[comp.category] ?? comp.category}</span>
          <h3>{comp.name}</h3>
        </div>
        <div className="component-km">
          <strong>{fmtKm(comp.km)}</strong> <span className="muted">km</span>
          {!retired && rules.length > 0 && <StatusPill status={comp.status} />}
          {retired && <span className="pill pill-muted">Ausgemustert</span>}
        </div>
      </header>
      <p className="muted small">
        {comp.brand ? `${comp.brand} · ` : ""}eingebaut am {fmtDate(comp.installed_at)}
        {retired ? `, ausgemustert am ${fmtDate(comp.retired_at)}` : ""}
      </p>

      {rules.length > 0 && (
        <ul className="rule-list">
          {rules.map((r) => <RuleRow key={r.id} rule={r} onDelete={() => removeRule(r.id)} />)}
        </ul>
      )}

      {logs.length > 0 && (
        <p className="muted small">
          Letzte Wartung: {fmtDate(logs[0].performed_at)}{logs[0].note ? ` – ${logs[0].note}` : ""}
        </p>
      )}

      {panel === "log" && (
        <form className="inline-form" onSubmit={addLog}>
          <label>Datum<input type="date" value={log.performed_at} onChange={(e) => setLog({ ...log, performed_at: e.target.value })} required /></label>
          <label className="grow">Notiz<input value={log.note} onChange={(e) => setLog({ ...log, note: e.target.value })} placeholder="z. B. gereinigt und geölt" /></label>
          <button className="btn primary">Wartung speichern</button>
          <button type="button" className="btn" onClick={() => setPanel(null)}>Abbrechen</button>
        </form>
      )}

      {panel === "rule" && (
        <form className="inline-form" onSubmit={addRule}>
          <label className="grow">Aufgabe<input value={rule.label} onChange={(e) => setRule({ ...rule, label: e.target.value })} placeholder="z. B. Kette wechseln" required /></label>
          <label>Alle … km<input type="number" min="1" value={rule.interval_km} onChange={(e) => setRule({ ...rule, interval_km: e.target.value })} /></label>
          <label>Oder alle … Monate<input type="number" min="1" value={rule.interval_months} onChange={(e) => setRule({ ...rule, interval_months: e.target.value })} /></label>
          <button className="btn primary">Regel speichern</button>
          <button type="button" className="btn" onClick={() => setPanel(null)}>Abbrechen</button>
        </form>
      )}

      {error && <p className="error" role="alert">{error}</p>}

      {!retired && (
        <div className="actions">
          <button className="btn small" onClick={() => setPanel("log")}>Wartung eintragen</button>
          <button className="btn small" onClick={() => setPanel("rule")}>Regel hinzufügen</button>
          <button className="btn small" onClick={retire}>Ausmustern</button>
          <button className="link small danger" onClick={remove}>Löschen</button>
        </div>
      )}
      {retired && (
        <div className="actions">
          <button className="link small danger" onClick={remove}>Löschen</button>
        </div>
      )}
    </article>
  );
}

export default function BikeDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [bike, setBike] = useState(null);
  const [components, setComponents] = useState([]);
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [b, c] = await Promise.all([api.get(`/bikes/${id}`), api.get(`/components?bike_id=${id}`)]);
      setBike(b);
      setComponents(c);
    } catch (err) {
      setError(err.message);
    }
  }, [id]);

  useEffect(() => { load(); }, [load]);

  async function toggleRetired() {
    const { id: _id, total_km, component_count, due_count, ...rest } = bike;
    await api.put(`/bikes/${bike.id}`, { ...rest, retired: !bike.retired });
    load();
  }

  async function removeBike() {
    if (!window.confirm(`„${bike.name}“ wirklich löschen? Die Komponenten bleiben ohne Rad erhalten.`)) return;
    await api.del(`/bikes/${bike.id}`);
    navigate("/");
  }

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!bike) return <p className="muted">Lade …</p>;

  const active = components.filter((c) => !c.retired_at);
  const retired = components.filter((c) => c.retired_at);

  return (
    <>
      <p><Link to="/" className="link">← Zurück zur Garage</Link></p>
      <header className="bike-hero">
        <div>
          <h1>{bike.name}</h1>
          <p className="muted">
            {BIKE_TYPES[bike.type] ?? bike.type}
            {bike.brand ? ` · ${bike.brand}` : ""}{bike.model ? ` ${bike.model}` : ""}
            {bike.retired ? " · ausgemustert" : ""}
          </p>
          <div className="actions">
            <button className="btn small" onClick={toggleRetired}>
              {bike.retired ? "Wieder aktivieren" : "Ausmustern"}
            </button>
            <button className="link small danger" onClick={removeBike}>Rad löschen</button>
          </div>
        </div>
        <Odometer km={bike.total_km} />
      </header>

      <header className="page-head">
        <h2>Komponenten</h2>
        {!adding && <button className="btn primary" onClick={() => setAdding(true)}>Komponente hinzufügen</button>}
      </header>

      {adding && (
        <ComponentForm bikeId={bike.id} onCreated={() => { setAdding(false); load(); }} onCancel={() => setAdding(false)} />
      )}

      {active.length === 0 && !adding ? (
        <EmptyState
          title="Noch keine Komponenten"
          text="Füge Kette, Kassette, Reifen und weitere Teile hinzu, damit BikeHelper den Verschleiß mitzählt."
        >
          <button className="btn primary" onClick={() => setAdding(true)}>Erste Komponente anlegen</button>
        </EmptyState>
      ) : (
        <div className="component-list">
          {active.map((c) => <ComponentCard key={c.id} comp={c} onChanged={load} />)}
        </div>
      )}

      {retired.length > 0 && (
        <>
          <h2 className="section-title">Ausgemusterte Komponenten</h2>
          <div className="component-list">
            {retired.map((c) => <ComponentCard key={c.id} comp={c} onChanged={load} />)}
          </div>
        </>
      )}
    </>
  );
}
