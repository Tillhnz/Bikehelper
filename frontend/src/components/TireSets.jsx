import { useCallback, useEffect, useState } from "react";
import { api, fmtDate, fmtKm, fmtNum, today } from "../api.js";
import { Gauge } from "./ui.jsx";
import { CountUp } from "./motion.jsx";

const EMPTY = { name: "", brand: "", width_mm: "", tubeless: true, start_km: 0, max_km: "", notes: "", mountNow: true, mount_from: today() };

const num = (v) => (v === "" || v == null ? null : Number(v));

function setPayload(f) {
  return {
    name: f.name.trim(),
    brand: f.brand || null,
    width_mm: num(f.width_mm),
    tubeless: f.tubeless,
    start_km: Number(f.start_km) || 0,
    max_km: num(f.max_km),
    notes: f.notes || null,
    retired: !!f.retired,
  };
}

function SetForm({ initial, adding, onSubmit, onCancel }) {
  const [f, setF] = useState(initial);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  return (
    <form
      className="panel form-grid tire-form"
      onSubmit={(e) => { e.preventDefault(); onSubmit(f); }}
    >
      <h3 className="span-all">{adding ? "Neuer Reifensatz" : "Reifensatz bearbeiten"}</h3>
      <label>
        Bezeichnung
        <input value={f.name} onChange={set("name")} placeholder="z. B. Continental GP5000 S TR" required autoFocus />
      </label>
      <label>
        Marke
        <input value={f.brand ?? ""} onChange={set("brand")} />
      </label>
      <label>
        Breite (Aufdruck, mm)
        <input type="number" min="18" max="85" step="1" value={f.width_mm ?? ""} onChange={set("width_mm")} placeholder="z. B. 28" />
      </label>
      <label>
        Kilometer vor der App
        <input type="number" min="0" step="1" value={f.start_km} onChange={set("start_km")} />
        <span className="hint">Nur bei gebrauchten Reifen, sonst 0.</span>
      </label>
      <label>
        Erwartete Lebensdauer (km, optional)
        <input type="number" min="1" step="100" value={f.max_km ?? ""} onChange={set("max_km")} placeholder="z. B. 5000" />
        <span className="hint">Damit zeigt eine Anzeige, wie viel verbraucht ist.</span>
      </label>
      <label>
        Notiz
        <input value={f.notes ?? ""} onChange={set("notes")} />
      </label>
      <label className="check span-all">
        <input type="checkbox" checked={!!f.tubeless} onChange={(e) => setF({ ...f, tubeless: e.target.checked })} />
        Tubeless
      </label>
      {adding && (
        <div className="span-all mount-now">
          <label className="check">
            <input type="checkbox" checked={f.mountNow} onChange={(e) => setF({ ...f, mountNow: e.target.checked })} />
            Gleich montieren, ab
          </label>
          <input type="date" value={f.mount_from} onChange={set("mount_from")} disabled={!f.mountNow} aria-label="Montiert ab" />
        </div>
      )}
      <div className="actions span-all">
        <button className="btn primary">{adding ? "Reifensatz speichern" : "Speichern"}</button>
        <button type="button" className="btn" onClick={onCancel}>Abbrechen</button>
      </div>
    </form>
  );
}

function MountRow({ m, onSave, onDelete }) {
  const [edit, setEdit] = useState(false);
  const [r, setR] = useState({ from_date: m.from_date, to_date: m.to_date ?? "" });
  if (!edit) {
    return (
      <li>
        <span>
          {fmtDate(m.from_date)} bis {m.to_date ? fmtDate(m.to_date) : "heute"}{" "}
          <span className="muted">{fmtKm(m.km)} km</span>
        </span>
        <span className="rule-actions">
          <button className="link small" onClick={() => setEdit(true)}>Ändern</button>
          <button className="link small danger" onClick={onDelete}>Löschen</button>
        </span>
      </li>
    );
  }
  return (
    <li>
      <form
        className="inline-form"
        style={{ width: "100%", margin: 0 }}
        onSubmit={async (e) => { e.preventDefault(); if (await onSave({ from_date: r.from_date, to_date: r.to_date || null })) setEdit(false); }}
      >
        <label>Von<input type="date" value={r.from_date} onChange={(e) => setR({ ...r, from_date: e.target.value })} required /></label>
        <label>Bis<input type="date" value={r.to_date} onChange={(e) => setR({ ...r, to_date: e.target.value })} /></label>
        <button className="btn primary small">Speichern</button>
        <button type="button" className="btn small" onClick={() => setEdit(false)}>Abbrechen</button>
        <p className="hint span-all" style={{ flexBasis: "100%" }}>„Bis“ leer lassen, wenn der Satz noch montiert ist.</p>
      </form>
    </li>
  );
}

function SetCard({ ts, run, onEdit, hasMounted }) {
  const [panel, setPanel] = useState(null); // "mount" | "past" | null
  const [day, setDay] = useState(today());
  const [past, setPast] = useState({ from_date: today(), to_date: today() });
  const status = ts.progress == null ? "ok" : ts.progress >= 1 ? "due" : ts.progress >= 0.8 ? "soon" : "ok";

  return (
    <article className={`tire-set ${ts.mounted ? "mounted" : ""} ${ts.retired ? "retired" : ""}`}>
      <header className="component-head">
        <div>
          <span className="muted small">
            {[ts.brand, ts.width_mm ? `${fmtNum(ts.width_mm, 0)} mm` : null, ts.tubeless === false ? "mit Schlauch" : ts.tubeless ? "tubeless" : null]
              .filter(Boolean).join(" · ") || "Reifensatz"}
          </span>
          <h3>{ts.name}</h3>
        </div>
        <div className="component-km">
          <strong><CountUp value={ts.km} /></strong> <span className="muted">km</span>
          {ts.mounted && <span className="pill pill-ok">Montiert seit {fmtDate(ts.mounted_since)}</span>}
          {ts.retired && <span className="pill pill-muted">Ausgemustert</span>}
        </div>
      </header>

      {ts.max_km && (
        <>
          <Gauge progress={ts.progress} status={status} />
          <p className="muted small">{fmtKm(ts.km)} von {fmtKm(ts.max_km)} km erwartet</p>
        </>
      )}
      {ts.notes && <p className="muted small">{ts.notes}</p>}

      {panel === "mount" && (
        <form
          className="inline-form"
          onSubmit={async (e) => { e.preventDefault(); if (await run(`/tire-sets/${ts.id}/mount`, { day })) setPanel(null); }}
        >
          <label>Montiert ab<input type="date" value={day} onChange={(e) => setDay(e.target.value)} required /></label>
          <button className="btn primary">Montieren</button>
          <button type="button" className="btn" onClick={() => setPanel(null)}>Abbrechen</button>
          <p className="hint" style={{ flexBasis: "100%" }}>
            Alle Fahrten des Rades ab diesem Tag zählen auf diesen Satz, bis du einen anderen montierst.
            {hasMounted ? " Der bisherige Satz endet am Vortag." : ""}
          </p>
        </form>
      )}

      {panel === "past" && (
        <form
          className="inline-form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await run(`/tire-sets/${ts.id}/mounts`, { from_date: past.from_date, to_date: past.to_date || null })) setPanel(null);
          }}
        >
          <label>Von<input type="date" value={past.from_date} onChange={(e) => setPast({ ...past, from_date: e.target.value })} required /></label>
          <label>Bis<input type="date" value={past.to_date} onChange={(e) => setPast({ ...past, to_date: e.target.value })} /></label>
          <button className="btn primary">Zeitraum eintragen</button>
          <button type="button" className="btn" onClick={() => setPanel(null)}>Abbrechen</button>
        </form>
      )}

      <div className="actions">
        {!ts.retired && !ts.mounted && <button className="btn small primary" onClick={() => setPanel("mount")}>Montieren</button>}
        {ts.mounted && <button className="btn small" onClick={() => run(`/tire-sets/${ts.id}/unmount`, { day: today() })}>Abmontieren</button>}
        <button className="btn small" onClick={() => setPanel("past")}>Zeitraum nachtragen</button>
        <button className="btn small" onClick={() => onEdit(ts)}>Bearbeiten</button>
        <button className="btn small" onClick={() => onEdit(ts, { retired: !ts.retired })}>{ts.retired ? "Wieder aktivieren" : "Ausmustern"}</button>
        <button className="link small danger" onClick={() => onEdit(ts, null, true)}>Löschen</button>
      </div>

      {ts.mounts.length > 0 && (
        <details className="howto log-history">
          <summary>Verlauf auf dem Rad ({ts.mounts.length})</summary>
          <ul className="log-list">
            {ts.mounts.map((m) => (
              <MountRow
                key={m.id}
                m={m}
                onSave={(body) => run(`/tire-mounts/${m.id}`, body, "put")}
                onDelete={() => { if (window.confirm("Diesen Zeitraum löschen? Die Kilometer zählen dann nicht mehr auf diesen Satz.")) run(`/tire-mounts/${m.id}`, null, "del"); }}
              />
            ))}
          </ul>
        </details>
      )}
    </article>
  );
}

/** Reifensätze eines Rades: welcher Satz montiert ist und wie viele Kilometer jeder hat. */
export default function TireSets({ bike, onChanged }) {
  const [sets, setSets] = useState(null);
  const [form, setForm] = useState(null); // {mode: "add" | "edit", ts?}
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      setSets(await api.get(`/bikes/${bike.id}/tire-sets`));
    } catch (e) {
      setError(e.message);
    }
  }, [bike.id]);

  useEffect(() => { load(); }, [load]);

  /** Führt eine Änderung aus und lädt danach Sätze und Rad neu. Gibt true bei Erfolg zurück. */
  async function run(path, body, method = "post") {
    setError("");
    try {
      await api[method](path, body ?? undefined);
      await load();
      onChanged();
      return true;
    } catch (e) {
      setError(e.message);
      return false;
    }
  }

  async function onEdit(ts, patch, remove) {
    if (remove) {
      if (!window.confirm(`„${ts.name}“ wirklich löschen? Der Verlauf geht verloren.`)) return;
      await run(`/tire-sets/${ts.id}`, null, "del");
      return;
    }
    if (patch) {
      await run(`/tire-sets/${ts.id}`, setPayload({ ...ts, ...patch }), "put");
      return;
    }
    setForm({ mode: "edit", ts });
  }

  async function submit(f) {
    if (form.mode === "add") {
      const ok = await run(`/bikes/${bike.id}/tire-sets`, { ...setPayload(f), mount_from: f.mountNow ? f.mount_from : null });
      if (ok) setForm(null);
    } else {
      const ok = await run(`/tire-sets/${form.ts.id}`, { ...setPayload(f), retired: form.ts.retired }, "put");
      if (ok) setForm(null);
    }
  }

  if (!sets) return error ? <p className="error" role="alert">{error}</p> : null;

  const active = sets.filter((s) => !s.retired);
  const retired = sets.filter((s) => s.retired);
  const hasMounted = active.some((s) => s.mounted);

  return (
    <section className="tire-sets-section">
      <header className="page-head">
        <h2>Reifen</h2>
        {!form && <button className="btn primary" onClick={() => setForm({ mode: "add" })}>Reifensatz hinzufügen</button>}
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      {form && (
        <SetForm
          adding={form.mode === "add"}
          initial={form.mode === "add" ? { ...EMPTY, width_mm: bike.tire_width_mm ?? "", tubeless: bike.tubeless ?? true } : { ...form.ts, mountNow: false }}
          onSubmit={submit}
          onCancel={() => setForm(null)}
        />
      )}

      {sets.length === 0 && !form ? (
        <div className="empty">
          <h3>Noch kein Reifensatz</h3>
          <p className="muted">
            Lege jeden Satz Reifen an und wähle, welcher gerade montiert ist. BikeHelper zählt die Kilometer jedes Satzes
            und rechnet alle Fahrten des Rades automatisch auf den montierten Satz, bis du hier einen anderen montierst.
          </p>
        </div>
      ) : (
        <div className="component-list">
          {active.map((ts) => <SetCard key={ts.id} ts={ts} run={run} onEdit={onEdit} hasMounted={hasMounted} />)}
        </div>
      )}

      {retired.length > 0 && (
        <details className="howto" style={{ marginTop: "1rem" }}>
          <summary>Ausgemusterte Sätze ({retired.length})</summary>
          <div className="component-list" style={{ marginTop: "0.75rem" }}>
            {retired.map((ts) => <SetCard key={ts.id} ts={ts} run={run} onEdit={onEdit} hasMounted={hasMounted} />)}
          </div>
        </details>
      )}
    </section>
  );
}
