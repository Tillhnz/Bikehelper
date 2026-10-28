import { useCallback, useEffect, useRef, useState } from "react";
import { api, fmtDate, fmtKm, fmtNum, safeUrl, today } from "../api.js";
import { Gauge, StatusPill } from "./ui.jsx";
import { CountUp } from "./motion.jsx";
import { confirmDialog, toast } from "./feedback.jsx";
import CheckGuide from "./CheckGuide.jsx";

const EMPTY = { name: "", brand: "", width_mm: "", tubeless: true, category: "", weight_g: "", watts: "", watts_note: "", source_url: "", shop_url: "", model_key: "", casing: "", start_km: 0, max_km: "", check_km: "", notes: "", mountNow: true, mount_from: today() };

const num = (v) => (v === "" || v == null ? null : Number(v));

function setPayload(f) {
  return {
    name: f.name.trim(),
    brand: f.brand || null,
    width_mm: num(f.width_mm),
    tubeless: f.tubeless,
    start_km: Number(f.start_km) || 0,
    max_km: num(f.max_km),
    check_km: num(f.check_km),
    notes: f.notes || null,
    retired: !!f.retired,
    model_key: f.model_key || null,
    category: f.category || null,
    weight_g: num(f.weight_g),
    watts: num(f.watts),
    watts_note: f.watts_note || null,
    source_url: f.source_url || null,
    shop_url: f.shop_url?.trim() || null,
    casing: f.casing || null,
  };
}

const CASING_TEXT = { supple: "dünn, geschmeidig", standard: "normal", stiff: "Pannenschutz" };
const TUBELESS_TEXT = { tubeless: "tubeless", clincher: "Drahtreifen", tubular: "Schlauchreifen", both: "tubeless oder Schlauch" };

/** Suchfeld für den Reifenkatalog: tippen, Treffer anklicken, Felder werden gefüllt. Eigene Reifen bleiben frei eintragbar. */
function CatalogPicker({ onPick, category }) {
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [open, setOpen] = useState(false);
  const timer = useRef(null);
  const box = useRef(null);

  // Liste schließen: Klick oder Fokus außerhalb, Escape
  useEffect(() => {
    if (!open) return undefined;
    const away = (e) => { if (box.current && !box.current.contains(e.target)) setOpen(false); };
    const esc = (e) => { if (e.key === "Escape") setOpen(false); };
    document.addEventListener("pointerdown", away);
    document.addEventListener("focusin", away);
    document.addEventListener("keydown", esc);
    return () => {
      document.removeEventListener("pointerdown", away);
      document.removeEventListener("focusin", away);
      document.removeEventListener("keydown", esc);
    };
  }, [open]);

  useEffect(() => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => {
      const params = new URLSearchParams({ q, limit: "300" });
      if (category) params.set("category", category);
      api.get(`/tire-catalog?${params}`).then(setRes).catch(() => setRes(null));
    }, 200);
    return () => clearTimeout(timer.current);
  }, [q, category]);

  const total = res ? res.bundled + res.own : 0;
  const groups = [];
  for (const it of res?.items ?? []) {
    const id = `${it.brand}|${it.model}|${it.category}|${it.own}`;
    let g = groups.find((x) => x.id === id);
    if (!g) groups.push((g = { id, brand: it.brand, model: it.model, category: it.category, tubeless: it.tubeless, own: it.own, items: [] }));
    g.items.push(it);
  }
  return (
    <div className="span-all catalog-picker" ref={box}>
      <label>
        Reifen aus dem Katalog suchen
        <input
          value={q}
          onChange={(e) => { setQ(e.target.value); setOpen(true); }}
          onFocus={() => setOpen(true)}
          placeholder={total ? `z. B. Continental 28 (${total} Größen im Katalog)` : "Katalog ist noch leer, trage den Reifen unten selbst ein"}
          role="combobox"
          aria-expanded={open}
          aria-controls="catalog-results"
          autoComplete="off"
        />
      </label>
      {open && groups.length > 0 && (
        <ul className="catalog-results" id="catalog-results" role="listbox">
          {groups.map((g) => (
            <li key={g.id} role="presentation" className="catalog-group">
              <div className="catalog-model">
                <strong>{g.brand} {g.model}</strong>
                <span className="muted small">
                  {[res.categories[g.category], g.tubeless && TUBELESS_TEXT[g.tubeless], g.own && "eigener Eintrag"].filter(Boolean).join(" · ")}
                </span>
              </div>
              <div className="catalog-sizes">
                {g.items.map((it) => (
                  <button key={it.key} type="button" role="option" aria-selected="false" onClick={() => { onPick(it); setOpen(false); setQ(""); }}>
                    {it.width_mm ? `${fmtNum(it.width_mm, 0)} mm` : "Größe offen"}
                    {(it.weight_g || it.watts) && (
                      <span className="muted small">{[it.weight_g && `${fmtNum(it.weight_g, 0)} g`, it.watts && `${fmtNum(it.watts)} W`].filter(Boolean).join(" · ")}</span>
                    )}
                  </button>
                ))}
              </div>
            </li>
          ))}
        </ul>
      )}
      {open && q.trim() && res && groups.length === 0 && (
        <p className="hint">Keine Treffer. Trage den Reifen unten selbst ein oder suche ihn <a href={`https://duckduckgo.com/?q=${encodeURIComponent(`${q} Reifen Rollwiderstand`)}`} target="_blank" rel="noopener noreferrer">im Netz</a>.</p>
      )}
      <p className="hint">Nicht dabei? Einfach unten Bezeichnung und Breite selbst eintragen. Der Katalog ist nur eine Hilfe.</p>
    </div>
  );
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
      {adding && (
        <CatalogPicker
          onPick={(it) => setF({
            ...f, name: `${it.model}`, brand: it.brand, width_mm: it.width_mm ?? f.width_mm,
            tubeless: it.tubeless ? it.tubeless !== "clincher" : f.tubeless, category: it.category ?? "",
            weight_g: it.weight_g ?? "", watts: it.watts ?? "", watts_note: it.watts_note ?? "",
            source_url: it.source_url ?? "", model_key: it.key, casing: it.casing ?? f.casing,
          })}
        />
      )}
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
        <span className="hint">Damit siehst du, wie viele Kilometer noch übrig sind.</span>
      </label>
      <label>
        Sichtprüfung alle … km
        <input type="number" min="1" step="100" value={f.check_km ?? ""} onChange={set("check_km")} placeholder="1000" />
        <span className="hint">Leer lassen für 1.000 km. Prüfe Profil, Flanken, Schnitte und Fremdkörper.</span>
      </label>
      <label>
        Notiz
        <input value={f.notes ?? ""} onChange={set("notes")} />
      </label>
      <label>
        Karkasse
        <select value={f.casing ?? ""} onChange={set("casing")}>
          <option value="">Normal / nicht angegeben</option>
          <option value="supple">Dünn, geschmeidig (Rennreifen, hohe Fadenzahl)</option>
          <option value="stiff">Pannenschutz, steif (Touren-, Alltagsreifen)</option>
        </select>
        <span className="hint">Die Karkasse ist das Gewebe unter dem Profil. Der Ratgeber nutzt sie für den Reifendruck: dünne Karkassen etwas weniger, Pannenschutz etwas mehr.</span>
      </label>
      <label>
        Gewicht je Reifen (g)
        <input type="number" min="50" max="3000" step="1" value={f.weight_g ?? ""} onChange={set("weight_g")} />
      </label>
      <label>
        Rollwiderstand je Reifen (Watt)
        <input type="number" min="0.5" max="100" step="0.1" value={f.watts ?? ""} onChange={set("watts")} placeholder="z. B. 9,5" />
        <span className="hint">Prüfstandswert bei etwa 29 km/h und 42,5 kg Last, siehe Quelle. Dein Gesamtgewicht und höheres Tempo erhöhen ihn.</span>
      </label>
      <label>
        Quelle des Werts (Link)
        <input type="url" value={f.source_url ?? ""} onChange={set("source_url")} placeholder="https://" />
      </label>
      <label>
        Einkaufslink
        <input type="url" value={f.shop_url ?? ""} onChange={set("shop_url")} placeholder="https://" maxLength={500} />
        <span className="hint">Hier kaufst du diesen Reifen nach.</span>
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
  const [err, setErr] = useState("");
  function startEdit() {  // immer mit den aktuell gespeicherten Werten beginnen, nicht mit denen vom letzten Mal
    setR({ from_date: m.from_date, to_date: m.to_date ?? "" });
    setErr("");
    setEdit(true);
  }
  if (!edit) {
    return (
      <li>
        <span>
          {fmtDate(m.from_date)} bis {m.to_date ? fmtDate(m.to_date) : "heute"}{" "}
          <span className="muted">{fmtKm(m.km)} km</span>
        </span>
        <span className="rule-actions">
          <button className="link small" onClick={startEdit}>Ändern</button>
          <button className="link small danger" onClick={() => onDelete(setErr)}>Löschen</button>
        </span>
        {err && <p className="error span-all" role="alert" style={{ flexBasis: "100%" }}>{err}</p>}
      </li>
    );
  }
  return (
    <li>
      <form
        className="inline-form"
        style={{ width: "100%", margin: 0 }}
        onSubmit={async (e) => { e.preventDefault(); if (await onSave({ from_date: r.from_date, to_date: r.to_date || null }, setErr)) setEdit(false); }}
      >
        <label>Von<input type="date" value={r.from_date} onChange={(e) => setR({ ...r, from_date: e.target.value })} required /></label>
        <label>Bis<input type="date" value={r.to_date} onChange={(e) => setR({ ...r, to_date: e.target.value })} /></label>
        <button className="btn primary small">Speichern</button>
        <button type="button" className="btn small" onClick={() => setEdit(false)}>Abbrechen</button>
        <p className="hint span-all" style={{ flexBasis: "100%" }}>„Bis“ leer lassen, wenn der Satz noch montiert ist.</p>
        {err && <p className="error span-all" role="alert" style={{ flexBasis: "100%" }}>{err}</p>}
      </form>
    </li>
  );
}

function SetCard({ ts, run, onEdit, hasMounted, bestWatts, expandSignal }) {
  const [open, setOpen] = useState(false);
  useEffect(() => { if (expandSignal) setOpen(expandSignal.open); }, [expandSignal]);
  const [panel, setPanel] = useState(null); // "mount" | "past" | null
  const [day, setDay] = useState(today());
  const [past, setPast] = useState({ from_date: today(), to_date: today() });
  const [formErr, setFormErr] = useState("");
  const [history, setHistory] = useState(false);
  const openPanel = (name) => { setFormErr(""); setPanel(name); };
  const status = ts.life_status;

  return (
    <article className={`tire-set ${ts.mounted ? "mounted" : ""} ${ts.retired ? "retired" : ""}`}>
      <button type="button" className="component-toggle" aria-expanded={open} onClick={() => setOpen((v) => !v)}>
        <span className="chevron" aria-hidden="true" />
        <span className="component-title">
          <span className="muted small">
            {[ts.brand, ts.width_mm ? `${fmtNum(ts.width_mm, 0)} mm` : null, ts.tubeless === false ? "mit Schlauch" : ts.tubeless ? "tubeless" : null]
              .filter(Boolean).join(" · ") || "Reifensatz"}
          </span>
          <h3>{ts.name}</h3>
        </span>
        <span className="component-km">
          <strong>{fmtKm(ts.km)}</strong> <span className="muted">km</span>
          {ts.mounted && <span className="pill pill-ok">Montiert seit {fmtDate(ts.mounted_since)}</span>}
          {ts.retired && <span className="pill pill-muted">Ausgemustert</span>}
          {!ts.retired && ts.status !== "ok" && <StatusPill status={ts.status} />}
        </span>
      </button>
      {open && <div className="component-body">

      {ts.max_km ? (
        <>
          <Gauge progress={ts.progress} status={status} />
          <p className="muted small">
            {fmtKm(ts.km)} von {fmtKm(ts.max_km)} km gefahren,{" "}
            {ts.km_left > 0 ? <>noch etwa <strong>{fmtKm(ts.km_left)} km</strong> bis zum erwarteten Wechsel</> : <strong>erwartete Lebensdauer erreicht</strong>}
          </p>
        </>
      ) : (
        <p className="muted small">{fmtKm(ts.km)} km gefahren. Trage bei „Bearbeiten“ eine erwartete Lebensdauer ein, dann siehst du die Restkilometer.</p>
      )}
      {!ts.retired && (
        <>
          <Gauge progress={ts.check_progress} status={ts.check_status} />
          <p className="muted small">
            Sichtprüfung alle {fmtKm(ts.check_interval_km)} km: seit {ts.checked_on ? `der letzten Prüfung am ${fmtDate(ts.checked_on)}` : "dem Einbau"} {fmtKm(ts.km_since_check)} km
            {ts.check_status === "due" ? <strong> – jetzt prüfen</strong> : ts.check_status === "soon" ? " – bald prüfen" : ""}
          </p>
        </>
      )}
      {(ts.weight_g || ts.watts || ts.casing || ts.brand || ts.shop_url) && (
        <p className="tire-facts small">
          {ts.casing && <span>Karkasse: {CASING_TEXT[ts.casing]}</span>}
          {ts.weight_g && <span>{fmtNum(ts.weight_g, 0)} g je Reifen</span>}
          {ts.watts && (
            <span>
              {fmtNum(ts.watts)} W Rollwiderstand je Reifen
              {bestWatts != null && ts.watts > bestWatts + 0.05 && (
                <span className="muted"> (+{fmtNum(ts.watts - bestWatts)} W gegenüber dem besten deiner Sätze, am Rad etwa +{fmtNum((ts.watts - bestWatts) * 2)} W)</span>
              )}
              {bestWatts != null && ts.watts <= bestWatts + 0.05 && <span className="muted"> (bester deiner Sätze)</span>}
            </span>
          )}
          {safeUrl(ts.shop_url) && <a href={safeUrl(ts.shop_url)} target="_blank" rel="noopener noreferrer">Nachkaufen</a>}
          {ts.source_url && <a href={ts.source_url} target="_blank" rel="noopener noreferrer">Quelle</a>}
          {!ts.watts && <a href={`https://duckduckgo.com/?q=${encodeURIComponent(`${ts.brand ?? ""} ${ts.name} Rollwiderstand Watt`)}`} target="_blank" rel="noopener noreferrer">Rollwiderstand nachschlagen</a>}
        </p>
      )}
      {ts.notes && <p className="muted small">{ts.notes}</p>}

      {panel === "mount" && (
        <form
          className="inline-form"
          onSubmit={async (e) => { e.preventDefault(); if (await run(`/tire-sets/${ts.id}/mount`, { day }, "post", setFormErr)) setPanel(null); }}
        >
          <label>Montiert ab<input type="date" value={day} onChange={(e) => setDay(e.target.value)} required /></label>
          <button className="btn primary">Montieren</button>
          <button type="button" className="btn" onClick={() => setPanel(null)}>Abbrechen</button>
          <p className="hint" style={{ flexBasis: "100%" }}>
            Alle Fahrten des Rades ab diesem Tag zählen auf diesen Satz, bis du einen anderen montierst.
            {hasMounted ? " Der bisherige Satz endet am Vortag." : ""}
          </p>
          {formErr && <p className="error" role="alert" style={{ flexBasis: "100%" }}>{formErr}</p>}
        </form>
      )}

      {panel === "past" && (
        <form
          className="inline-form"
          onSubmit={async (e) => {
            e.preventDefault();
            if (await run(`/tire-sets/${ts.id}/mounts`, { from_date: past.from_date, to_date: past.to_date || null }, "post", setFormErr)) { setPanel(null); setHistory(true); toast("Zeitraum eingetragen."); setPast({ from_date: today(), to_date: today() }); }
          }}
        >
          <label>Von<input type="date" value={past.from_date} onChange={(e) => setPast({ ...past, from_date: e.target.value })} required /></label>
          <label>Bis<input type="date" value={past.to_date} onChange={(e) => setPast({ ...past, to_date: e.target.value })} /></label>
          <button className="btn primary">Zeitraum eintragen</button>
          <button type="button" className="btn" onClick={() => setPanel(null)}>Abbrechen</button>
          <p className="hint" style={{ flexBasis: "100%" }}>
            Alle Fahrten dieses Rades in dem Zeitraum zählen auf diesen Satz (beide Tage mit). „Bis“ leer lassen, wenn der Satz noch montiert ist.
            Zeiträume verschiedener Sätze dürfen sich nicht überschneiden.
          </p>
          {formErr && <p className="error" role="alert" style={{ flexBasis: "100%" }}>{formErr}</p>}
        </form>
      )}

      <div className="actions">
        {!ts.retired && !ts.mounted && <button className="btn small primary" onClick={() => openPanel("mount")}>Montieren</button>}
        {ts.mounted && <button className="btn small" onClick={() => run(`/tire-sets/${ts.id}/unmount`, { day: today() })}>Abmontieren</button>}
        {!ts.retired && <button className={`btn small ${ts.check_status !== "ok" ? "primary" : ""}`} onClick={() => run(`/tire-sets/${ts.id}/checked`, {})}>Geprüft</button>}
        <button className="btn small" onClick={() => openPanel("past")}>Zeitraum nachtragen</button>
        <button className="btn small" onClick={() => onEdit(ts)}>Bearbeiten</button>
        <button className="btn small" onClick={() => onEdit(ts, { retired: !ts.retired })}>{ts.retired ? "Wieder aktivieren" : "Ausmustern"}</button>
        <button className="link small danger" onClick={() => onEdit(ts, null, true)}>Löschen</button>
      </div>

      {ts.mounts.length > 0 && (
        <details className="howto log-history" open={history} onToggle={(e) => setHistory(e.currentTarget.open)}>
          <summary>Verlauf auf dem Rad ({ts.mounts.length})</summary>
          <ul className="log-list">
            {ts.mounts.map((m) => (
              <MountRow
                key={m.id}
                m={m}
                onSave={(body, sink) => run(`/tire-mounts/${m.id}`, body, "put", sink)}
                onDelete={async (sink) => { if (await confirmDialog("Diesen Zeitraum löschen? Die Kilometer zählen dann nicht mehr auf diesen Satz.")) run(`/tire-mounts/${m.id}`, null, "del", sink); }}
              />
            ))}
          </ul>
        </details>
      )}
      </div>}
    </article>
  );
}

function CatalogManager() {
  const [info, setInfo] = useState(null);
  const [csv, setCsv] = useState("");
  const [url, setUrl] = useState("");
  const [replace, setReplace] = useState(false);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const load = useCallback(() => api.get("/tire-catalog?limit=1").then(setInfo).catch(() => {}), []);
  useEffect(() => { load(); }, [load]);

  async function readFile(e) {
    const file = e.target.files?.[0];
    if (file) setCsv(await file.text());
  }

  async function send(e) {
    e.preventDefault();
    setMsg("");
    setError("");
    try {
      const r = csv.trim()
        ? await api.post("/tire-catalog/import", { csv, replace })
        : await api.post("/tire-catalog/import-url", { url: url.trim(), replace });
      setMsg(`${r.added} neu, ${r.updated} aktualisiert${r.error_count ? `, ${r.error_count} Zeilen mit Fehlern: ${r.errors.slice(0, 3).join("; ")}` : ""}.`);
      setCsv("");
      setUrl("");
      load();
    } catch (err) {
      setError(err.message);
    }
  }

  const template = "brand,model,category,width_mm,tubeless,weight_g,watts,watts_note,source_url,casing\nContinental,Beispiel-Reifen,road,28,tubeless,300,9.5,Prüfstand 29 km/h,https://example.org/test,supple\n";
  return (
    <details className="howto catalog-manager">
      <summary>Reifenkatalog erweitern ({info ? `${info.bundled} mitgeliefert, ${info.own} eigene` : "…"})</summary>
      <p className="muted small">
        Die mitgelieferte Liste enthält Herstellerangaben mit Quelle (Gewichte laut Händlerseite, ungefähr ±5 bis 10 %). Messwerte (Watt) kannst du als CSV selbst einlesen,
        etwa aus eigenen Notizen oder Tests, die du nutzen darfst. Spalten: brand, model, category (road, gravel, mtb, trekking, city, tt, other),
        width_mm, tubeless (tubeless, clincher, tubular, both), weight_g, watts, watts_note, source_url, casing (supple, standard, stiff). Brand und model sind Pflicht.
      </p>
      <form onSubmit={send} className="form-grid">
        <label className="span-all">CSV-Datei<input type="file" accept=".csv,text/csv,text/plain" onChange={readFile} /></label>
        <label className="span-all">oder hier einfügen<textarea rows="5" value={csv} onChange={(e) => setCsv(e.target.value)} placeholder={template} /></label>
        <label className="check span-all"><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />Bisherige eigene Einträge vorher löschen</label>
        <label className="span-all">
          oder von einer Adresse laden (https, gleiche Spalten)
          <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://raw.githubusercontent.com/…/reifen.csv" />
        </label>
        <div className="actions span-all">
          <button className="btn primary" disabled={!csv.trim() && !url.trim()}>Importieren</button>
          <a className="btn" download="reifen-vorlage.csv" href={`data:text/csv;charset=utf-8,${encodeURIComponent(template)}`}>Vorlage laden</a>
        </div>
      </form>
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </details>
  );
}

/** Reifensätze eines Rades: welcher Satz montiert ist und wie viele Kilometer jeder hat. */
export default function TireSets({ bike, onChanged, expandSignal }) {
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
  async function run(path, body, method = "post", sink) {
    setError("");
    sink?.("");
    try {
      await api[method](path, body ?? undefined);
      await load();
      onChanged();
      return true;
    } catch (e) {
      (sink || setError)(e.message);  // Fehler dort zeigen, wo der Nutzer gerade arbeitet (Formular), sonst oben
      return false;
    }
  }

  async function onEdit(ts, patch, remove) {
    if (remove) {
      if (!await confirmDialog(`„${ts.name}“ wirklich löschen? Der Verlauf geht verloren.`)) return;
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
  const wattValues = sets.filter((s) => s.watts).map((s) => s.watts);
  const bestWatts = wattValues.length > 1 ? Math.min(...wattValues) : null;

  return (
    <section className="tire-sets-section">
      <header className="page-head">
        <h2>Reifen</h2>
        {!form && <button className="btn primary" onClick={() => setForm({ mode: "add" })}>Reifensatz hinzufügen</button>}
      </header>
      {error && <p className="error" role="alert">{error}</p>}

      <CheckGuide category="tires" />

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
          {active.map((ts) => <SetCard key={ts.id} ts={ts} run={run} onEdit={onEdit} hasMounted={hasMounted} bestWatts={bestWatts} expandSignal={expandSignal} />)}
        </div>
      )}

      <CatalogManager />

      {retired.length > 0 && (
        <details className="howto" style={{ marginTop: "1rem" }}>
          <summary>Ausgemusterte Sätze ({retired.length})</summary>
          <div className="component-list" style={{ marginTop: "0.75rem" }}>
            {retired.map((ts) => <SetCard key={ts.id} ts={ts} run={run} onEdit={onEdit} hasMounted={hasMounted} expandSignal={expandSignal} />)}
          </div>
        </details>
      )}
    </section>
  );
}
