import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { BIKE_TYPES, CATEGORIES, CHAIN_LUBES, api, fmtDate, fmtKm, fmtNum, nowTime, toTime, today } from "../api.js";
import BikeFields, { bikePayload } from "../components/BikeFields.jsx";
import ChainMeasure from "../components/ChainMeasure.jsx";
import BikeIllustration from "../components/BikeIllustration.jsx";
import TireSets from "../components/TireSets.jsx";
import { EmptyState, Gauge, Odometer, StatusPill } from "../components/ui.jsx";

function ruleIntervalText(r) {
  return [r.interval_km && `${fmtKm(r.interval_km)} km`, r.interval_months && `${r.interval_months} Monate`]
    .filter(Boolean).join(" oder ");
}

function ComponentForm({ bikeId, catalog, onCreated, onCancel }) {
  const [form, setForm] = useState({
    category: "chain", name: "", brand: "", installed_at: "", start_km: 0, withRules: true,
  });
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const template = catalog?.components?.[form.category];

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
      if (form.withRules && template) {
        for (const r of template.rules) {
          await api.post(`/components/${comp.id}/rules`, {
            label: r.label, interval_km: r.interval_km, interval_months: r.interval_months,
            wet_factor: r.wet_factor, hint: r.hint || null,
          });
        }
      }
      onCreated();
    } catch (err) {
      setError(err.message);
    }
  }

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
        <span className="hint">Leer lassen, dann gilt das Kaufdatum des Rades.</span>
      </label>
      <label>
        Kilometer vor dem Einbau
        <input type="number" min="0" step="1" value={form.start_km} onChange={set("start_km")} />
        <span className="hint">Nur bei gebrauchten Teilen, sonst 0.</span>
      </label>
      {template && (
        <label className="check span-all">
          <input
            type="checkbox"
            checked={form.withRules}
            onChange={(e) => setForm({ ...form, withRules: e.target.checked })}
          />
          Standard-Wartungsregeln anlegen: {template.rules.map((r) => `${r.label} (${ruleIntervalText(r)})`).join("; ")}
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

function RuleRow({ rule, onDelete, onDone, disabled }) {
  const [open, setOpen] = useState(false);
  const [done, setDone] = useState({ performed_at: today(), time: nowTime(), note: "", variant: rule.variant || "hot_wax", result: "good" });
  const [hintOpen, setHintOpen] = useState(false);
  const [guideOpen, setGuideOpen] = useState(false);
  const unknown = rule.status === "unknown";
  const wet = rule.wet_factor > 1;

  const variantName = rule.variants?.find((v) => v.key === rule.variant)?.name;
  const limits = [
    variantName && `zuletzt ${variantName}`,
    rule.interval_km && `${fmtKm(rule.km_since)} von ${fmtKm(rule.interval_km)} km`,
    rule.interval_months && `${fmtNum(rule.months_since)} von ${rule.interval_months} Monaten`,
  ].filter(Boolean).join(" · ");

  const a = rule.assessment;
  const RESULTS = { good: "gut", watch: "Beobachtung", replace: "wechseln" };
  const assessLine = a && (rule.is_inspection
    ? `Letzte Prüfung am ${fmtDate(a.date)}: ${RESULTS[a.result]}${a.result === "watch" ? ", früher erneut prüfen" : ""}.`
    : `Nach der Prüfung am ${fmtDate(a.date)} (${RESULTS[a.result]}): ${a.result === "replace" ? "jetzt wechseln" : `noch etwa ${fmtKm(a.km_left)} km`}, angepasstes Intervall ${fmtKm(a.interval_km)} km.`);

  async function submit(e) {
    e.preventDefault();
    await onDone(done);
    setOpen(false);
    setDone({ performed_at: today(), time: nowTime(), note: "", variant: done.variant, result: "good" });
  }

  return (
    <li className="rule-row">
      <div className="rule-top">
        <strong>{rule.label}</strong>
        <StatusPill status={rule.status} />
      </div>
      {!unknown && <Gauge progress={rule.progress} status={rule.status} />}
      <div className="rule-bottom">
        <span className="muted small">
          {unknown ? "Trage unten ein Einbaudatum ein oder hake die Aufgabe als erledigt ab." : limits}
        </span>
        <span className="rule-actions">
          {rule.hint && (
            <button className="link small" onClick={() => setHintOpen(!hintOpen)}>
              {hintOpen ? "Hinweis ausblenden" : "Hinweis"}
            </button>
          )}
          {rule.guides?.length > 0 && (
            <button className="link small" onClick={() => setGuideOpen(!guideOpen)} aria-expanded={guideOpen}>
              {guideOpen ? "Anleitungen ausblenden" : "Anleitung"}
            </button>
          )}
          {!disabled && <button className="link small" onClick={() => setOpen(!open)}>Erledigt</button>}
          <button className="link small" onClick={onDelete}>Regel löschen</button>
        </span>
      </div>
      {wet && !unknown && rule.interval_km && (
        <p className="muted small wet-line">
          Nässe zählt ×{fmtNum(rule.wet_factor)}: {fmtKm(rule.wet_km)} km bei Nässe, damit zählen {fmtKm(rule.effective_km)} km
          statt {fmtKm(rule.km_since)} km.
        </p>
      )}
      {assessLine && <p className="muted small wet-line">{assessLine}</p>}
      {hintOpen && rule.hint && <p className="hint-box small">{rule.hint}</p>}
      {guideOpen && (
        <ul className="guide-list">
          {rule.guides.map((g) => (
            <li key={g.url}>
              <a href={g.url} target="_blank" rel="noopener noreferrer">{g.title}</a>
              <span className="muted small">
                {g.source}{g.lang === "en" ? ", Englisch" : ""}{g.video ? " · mit Video" : ""}
              </span>
            </li>
          ))}
          <li className="muted small">Die Links führen zu fremden Seiten. Bei Bremsen und Steuersatz im Zweifel eine Werkstatt fragen.</li>
        </ul>
      )}
      {open && (
        <form className="inline-form" onSubmit={submit}>
          <label>Datum<input type="date" value={done.performed_at} onChange={(e) => setDone({ ...done, performed_at: e.target.value })} required /></label>
          <label>Uhrzeit<input type="time" value={done.time} onChange={(e) => setDone({ ...done, time: e.target.value })} /></label>
          {rule.variants && (
            <label>
              Wachsart
              <select value={done.variant} onChange={(e) => setDone({ ...done, variant: e.target.value })}>
                {rule.variants.map((v) => <option key={v.key} value={v.key}>{v.name}, alle {fmtKm(v.interval_km)} km</option>)}
              </select>
            </label>
          )}
          {rule.is_inspection && (
            <label>
              Ergebnis
              <select value={done.result} onChange={(e) => setDone({ ...done, result: e.target.value })}>
                <option value="good">Gut, noch lange nutzbar</option>
                <option value="watch">Beobachtung, bald wechseln</option>
                <option value="replace">Wechseln, jetzt</option>
              </select>
            </label>
          )}
          <label className="grow">Notiz<input value={done.note} onChange={(e) => setDone({ ...done, note: e.target.value })} /></label>
          <button className="btn primary">Als erledigt eintragen</button>
          <button type="button" className="btn" onClick={() => setOpen(false)}>Abbrechen</button>
          <p className="hint" style={{ flexBasis: "100%" }}>Mit Uhrzeit zählen nur Fahrten, die danach begonnen haben. Ohne Uhrzeit zählt der ganze Tag.</p>
        </form>
      )}
    </li>
  );
}

function ComponentCard({ comp, onChanged }) {
  const [rules, setRules] = useState([]);
  const [logs, setLogs] = useState([]);
  const [panel, setPanel] = useState(null); // "log" | "rule" | "replace" | "date" | null
  const [log, setLog] = useState({ performed_at: today(), time: nowTime(), note: "" });
  const [rule, setRule] = useState({ label: "", interval_km: "", interval_months: "", wet_factor: 1 });
  const [repl, setRepl] = useState({ performed_at: today(), name: comp.name, brand: comp.brand ?? "" });
  const [installed, setInstalled] = useState(comp.installed_at || today());
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

  async function guarded(fn) {
    setError("");
    try {
      await fn();
    } catch (err) {
      setError(err.message);
    }
  }

  const addLog = (e) => {
    e.preventDefault();
    return guarded(async () => {
      await api.post(`/components/${comp.id}/logs`, { performed_at: log.performed_at, performed_time: toTime(log.time), note: log.note || null });
      setPanel(null);
      setLog({ performed_at: today(), time: nowTime(), note: "" });
      await refresh();
    });
  };

  const addRule = (e) => {
    e.preventDefault();
    return guarded(async () => {
      await api.post(`/components/${comp.id}/rules`, {
        label: rule.label,
        interval_km: rule.interval_km ? Number(rule.interval_km) : null,
        interval_months: rule.interval_months ? Number(rule.interval_months) : null,
        wet_factor: Number(rule.wet_factor) || 1,
      });
      setPanel(null);
      setRule({ label: "", interval_km: "", interval_months: "", wet_factor: 1 });
      await refresh();
    });
  };

  const ruleDone = (r, data) =>
    guarded(async () => {
      await api.post(`/rules/${r.id}/done`, {
        performed_at: data.performed_at, performed_time: toTime(data.time), note: data.note || null,
        variant: r.variants ? data.variant : null,
        result: r.is_inspection ? data.result : null,
      });
      await refresh();
    });

  const removeRule = (id) =>
    guarded(async () => {
      await api.del(`/rules/${id}`);
      await refresh();
    });

  const replace = (e) => {
    e.preventDefault();
    return guarded(async () => {
      await api.post(`/components/${comp.id}/replace`, {
        performed_at: repl.performed_at, name: repl.name || null, brand: repl.brand || null,
      });
      setPanel(null);
      onChanged();
    });
  };

  const saveInstallDate = (e) => {
    e.preventDefault();
    return guarded(async () => {
      const { id, km, status, ...rest } = comp;
      await api.put(`/components/${id}`, { ...rest, installed_at: installed || null });
      setPanel(null);
      onChanged();
    });
  };

  const clearInstallDate = () =>
    guarded(async () => {
      const { id, km, status, ...rest } = comp;
      await api.put(`/components/${id}`, { ...rest, installed_at: null });
      setInstalled(today());
      setPanel(null);
      onChanged();
    });

  const unretire = () =>
    guarded(async () => {
      const { id, km, status, ...rest } = comp;
      await api.put(`/components/${id}`, { ...rest, retired_at: null });
      onChanged();
    });

  const removeLog = (l) =>
    guarded(async () => {
      if (!window.confirm(`Wartung vom ${fmtDate(l.performed_at)} wirklich löschen?`)) return;
      await api.del(`/logs/${l.id}`);
      await refresh();
    });

  const retire = () =>
    guarded(async () => {
      const { id, km, status, ...rest } = comp;
      await api.put(`/components/${id}`, { ...rest, retired_at: today() });
      onChanged();
    });

  const remove = () =>
    guarded(async () => {
      if (!window.confirm(`„${comp.name}“ wirklich löschen?`)) return;
      await api.del(`/components/${comp.id}`);
      onChanged();
    });

  const retired = !!comp.retired_at;
  const noDate = !comp.installed_effective;

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
        {comp.brand ? `${comp.brand} · ` : ""}
        {noDate ? "Einbaudatum unbekannt" : comp.installed_inherited ? `seit dem Kauf des Rades am ${fmtDate(comp.installed_effective)}` : `eingebaut am ${fmtDate(comp.installed_at)}`}
        {retired ? `, ausgemustert am ${fmtDate(comp.retired_at)}` : ""}
      </p>

      {rules.length > 0 && (
        <ul className="rule-list">
          {rules.map((r) => (
            <RuleRow
              key={r.id}
              rule={r}
              disabled={retired}
              onDelete={() => removeRule(r.id)}
              onDone={(d) => ruleDone(r, d)}
            />
          ))}
        </ul>
      )}

      {comp.category === "chain" && (
        <ChainMeasure comp={comp} rule={rules.find((r) => r.measure !== undefined && r.measure !== null) ?? rules.find((r) => r.label === "Kette wechseln")} disabled={retired} onChanged={refresh} />
      )}

      {logs.length > 0 && (
        <details className="howto log-history">
          <summary>
            Wartungsverlauf ({logs.length}), zuletzt {fmtDate(logs[0].performed_at)}
          </summary>
          <ul className="log-list">
            {logs.map((l) => {
              const r = rules.find((x) => x.id === l.rule_id);
              const variant = r?.variants?.find((v) => v.key === l.variant)?.name;
              return (
                <li key={l.id}>
                  <span>
                    <strong>{fmtDate(l.performed_at)}{l.performed_time ? `, ${l.performed_time.slice(0, 5)} Uhr` : ""}</strong>{" "}
                    <span className="muted">{r ? r.label : l.rule_id ? "Regel gelöscht" : "ganze Komponente"}</span>
                    {variant ? `, ${variant}` : ""}{l.result ? `, Ergebnis: ${{ good: "gut", watch: "Beobachtung", replace: "wechseln" }[l.result]}` : ""}{l.note ? ` – ${l.note}` : ""}
                  </span>
                  <button className="link small danger" onClick={() => removeLog(l)}>Löschen</button>
                </li>
              );
            })}
          </ul>
        </details>
      )}

      {panel === "date" && (
        <form className="inline-form" onSubmit={saveInstallDate}>
          <label>Eingebaut am<input type="date" value={installed} onChange={(e) => setInstalled(e.target.value)} /></label>
          <button className="btn primary">Datum speichern</button>
          {comp.installed_at && <button type="button" className="btn" onClick={clearInstallDate}>Datum entfernen</button>}
          <button type="button" className="btn" onClick={() => setPanel(null)}>Abbrechen</button>
          <p className="hint span-all">Ohne eigenes Einbaudatum gilt das Kaufdatum des Rades, und ohne beides zählt BikeHelper erst ab der nächsten eingetragenen Wartung.</p>
        </form>
      )}

      {panel === "log" && (
        <form className="inline-form" onSubmit={addLog}>
          <label>Datum<input type="date" value={log.performed_at} onChange={(e) => setLog({ ...log, performed_at: e.target.value })} required /></label>
          <label>Uhrzeit<input type="time" value={log.time} onChange={(e) => setLog({ ...log, time: e.target.value })} /></label>
          <label className="grow">Notiz<input value={log.note} onChange={(e) => setLog({ ...log, note: e.target.value })} placeholder="z. B. gereinigt und geölt" /></label>
          <button className="btn primary">Wartung speichern</button>
          <button type="button" className="btn" onClick={() => setPanel(null)}>Abbrechen</button>
        </form>
      )}

      {panel === "replace" && (
        <form className="inline-form" onSubmit={replace}>
          <label>Gewechselt am<input type="date" value={repl.performed_at} onChange={(e) => setRepl({ ...repl, performed_at: e.target.value })} required /></label>
          <label className="grow">Neues Teil<input value={repl.name} onChange={(e) => setRepl({ ...repl, name: e.target.value })} /></label>
          <label>Marke<input value={repl.brand} onChange={(e) => setRepl({ ...repl, brand: e.target.value })} /></label>
          <button className="btn primary">Teil wechseln</button>
          <button type="button" className="btn" onClick={() => setPanel(null)}>Abbrechen</button>
          <p className="hint span-all">Das alte Teil wird ausgemustert, das neue übernimmt alle Wartungsregeln und zählt ab 0 km.</p>
        </form>
      )}

      {panel === "rule" && (
        <form className="inline-form" onSubmit={addRule}>
          <label className="grow">Aufgabe<input value={rule.label} onChange={(e) => setRule({ ...rule, label: e.target.value })} placeholder="z. B. Kette wechseln" required /></label>
          <label>Alle … km<input type="number" min="1" value={rule.interval_km} onChange={(e) => setRule({ ...rule, interval_km: e.target.value })} /></label>
          <label>Oder alle … Monate<input type="number" min="1" value={rule.interval_months} onChange={(e) => setRule({ ...rule, interval_months: e.target.value })} /></label>
          <label>Nässefaktor<input type="number" min="1" max="5" step="0.1" value={rule.wet_factor} onChange={(e) => setRule({ ...rule, wet_factor: e.target.value })} /></label>
          <button className="btn primary">Regel speichern</button>
          <button type="button" className="btn" onClick={() => setPanel(null)}>Abbrechen</button>
        </form>
      )}

      {error && <p className="error" role="alert">{error}</p>}

      {!retired && (
        <div className="actions">
          <button className={`btn small ${noDate ? "primary" : ""}`} onClick={() => setPanel("date")}>
            {noDate ? "Einbaudatum eintragen" : "Einbaudatum ändern"}
          </button>
          <button className="btn small" onClick={() => setPanel("replace")}>Teil gewechselt</button>
          <button className="btn small" onClick={() => setPanel("log")}>Wartung eintragen</button>
          <button className="btn small" onClick={() => setPanel("rule")}>Regel hinzufügen</button>
          <button className="btn small" onClick={retire}>Ausmustern</button>
          <button className="link small danger" onClick={remove}>Löschen</button>
        </div>
      )}
      {retired && (
        <div className="actions">
          <button className="btn small" onClick={unretire}>Wieder einbauen</button>
          <button className="link small danger" onClick={remove}>Löschen</button>
        </div>
      )}
    </article>
  );
}

function BikeEdit({ bike, onSaved, onCancel }) {
  const [form, setForm] = useState({ ...bike });
  const [error, setError] = useState("");
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      const { id, total_km, component_count, due_count, unknown_count, tire_set, ...rest } = bikePayload(form);
      await api.put(`/bikes/${bike.id}`, rest);
      onSaved();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <form className="panel form-grid" onSubmit={submit}>
      <h2 className="span-all">Rad bearbeiten</h2>
      <label>Name<input value={form.name} onChange={set("name")} required /></label>
      <label>
        Art
        <select value={form.type} onChange={set("type")}>
          {Object.entries(BIKE_TYPES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <label>Marke<input value={form.brand ?? ""} onChange={set("brand")} /></label>
      <label>Modell<input value={form.model ?? ""} onChange={set("model")} /></label>
      <BikeFields form={form} setForm={setForm} />
      {form.chain_lube !== (bike.chain_lube || "oil") && (
        <p className="hint span-all">
          Beim Speichern werden die Regeln der Kette (Schmieren und Wechseln) auf die neue Schmierung umgestellt.
          Bereits eingetragene Wartungen bleiben erhalten.
        </p>
      )}
      {error && <p className="error span-all" role="alert">{error}</p>}
      <div className="actions span-all">
        <button className="btn primary">Speichern</button>
        <button type="button" className="btn" onClick={onCancel}>Abbrechen</button>
      </div>
    </form>
  );
}

export default function BikeDetail() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [bike, setBike] = useState(null);
  const [components, setComponents] = useState([]);
  const [adding, setAdding] = useState(false);
  const [catalog, setCatalog] = useState(null);
  const [editing, setEditing] = useState(false);
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
  useEffect(() => { api.get("/catalog").then(setCatalog).catch(() => {}); }, []);

  async function addStandard() {
    setError("");
    try {
      await api.post(`/bikes/${bike.id}/standard-components`, {});
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  async function toggleRetired() {
    const { id: _id, total_km, component_count, due_count, unknown_count, tire_set, ...rest } = bike;
    await api.put(`/bikes/${bike.id}`, { ...rest, retired: !bike.retired });
    load();
  }

  async function removeBike() {
    if (!window.confirm(`„${bike.name}“ wirklich löschen? Die Komponenten bleiben ohne Rad erhalten.`)) return;
    await api.del(`/bikes/${bike.id}`);
    navigate("/garage");
  }

  if (error && !bike) return <p className="error" role="alert">{error}</p>;
  if (!bike) return <p className="muted">Lade …</p>;

  const legacy = components.filter((c) => c.category === "tire_front" || c.category === "tire_rear");
  const tracked = components.filter((c) => !legacy.includes(c));
  const active = tracked.filter((c) => !c.retired_at);
  const retired = tracked.filter((c) => c.retired_at);

  return (
    <>
      <p><Link to="/garage" className="link">← Zurück zur Garage</Link></p>
      <header className="bike-hero">
        <div>
          <h1>{bike.name}</h1>
          <p className="muted">
            {BIKE_TYPES[bike.type] ?? bike.type}
            {bike.brand ? ` · ${bike.brand}` : ""}{bike.model ? ` ${bike.model}` : ""}
            {bike.purchased_at ? ` · gekauft am ${fmtDate(bike.purchased_at)}` : ""}
            {bike.retired ? " · ausgemustert" : ""}
          </p>
          <p className="muted small">
            Kette: {CHAIN_LUBES[bike.chain_lube || "oil"].name}
            {bike.tire_set ? ` · Reifen ${bike.tire_set.name}` : bike.tire_width_mm ? ` · Reifen ${bike.tire_width_mm} mm` : ""}
            {bike.tubeless === false ? " mit Schlauch" : bike.tire_width_mm ? ", tubeless" : ""}
          </p>
          <div className="actions">
            <button className="btn small" onClick={() => setEditing(true)}>Bearbeiten</button>
            <button className="btn small" onClick={toggleRetired}>
              {bike.retired ? "Wieder aktivieren" : "Ausmustern"}
            </button>
            <button className="link small danger" onClick={removeBike}>Rad löschen</button>
          </div>
        </div>
        <div className="bike-hero-art">
          <BikeIllustration type={bike.type} tireMm={bike.tire_width_mm} ride title={BIKE_TYPES[bike.type] ?? "Rad"} />
          <Odometer km={bike.total_km} />
        </div>
      </header>

      {editing && (
        <BikeEdit bike={bike} onCancel={() => setEditing(false)} onSaved={() => { setEditing(false); load(); }} />
      )}

      <TireSets bike={bike} onChanged={load} />

      <header className="page-head">
        <h2>Komponenten</h2>
        {!adding && (
          <div className="actions" style={{ marginTop: 0 }}>
            <button className="btn" onClick={addStandard}>Standardkomponenten ergänzen</button>
            <button className="btn primary" onClick={() => setAdding(true)}>Komponente hinzufügen</button>
          </div>
        )}
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      {adding && (
        <ComponentForm bikeId={bike.id} catalog={catalog} onCreated={() => { setAdding(false); load(); }} onCancel={() => setAdding(false)} />
      )}

      {active.length === 0 && !adding ? (
        <EmptyState
          title="Noch keine Komponenten"
          text="Füge Kette, Kassette, Bremsen und weitere Teile hinzu, damit BikeHelper den Verschleiß mitzählt. Reifen verwaltest du unter „Reifen“."
        >
          <div className="actions" style={{ justifyContent: "center" }}>
            <button className="btn primary" onClick={addStandard}>Standardkomponenten anlegen</button>
            <button className="btn" onClick={() => setAdding(true)}>Eigene Komponente anlegen</button>
          </div>
        </EmptyState>
      ) : (
        <div className="component-list">
          {active.map((c) => <ComponentCard key={c.id} comp={c} onChanged={load} />)}
        </div>
      )}

      {legacy.length > 0 && (
        <details className="howto legacy-tires">
          <summary>Frühere Reifen-Einträge ({legacy.length})</summary>
          <p className="muted small">
            Reifen laufen jetzt über die Reifensätze weiter oben. Diese Einträge zählen nicht mehr zur Wartung und lösen keine
            Meldungen aus. Du kannst sie löschen, sobald du die Reifensätze angelegt hast.
          </p>
          <div className="component-list">
            {legacy.map((c) => <ComponentCard key={c.id} comp={c} onChanged={load} />)}
          </div>
        </details>
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
