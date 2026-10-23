import { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { CATEGORIES, api, fmtDate, fmtNum, today } from "../api.js";
import { Kpi } from "../components/statsui.jsx";
import { EmptyState } from "../components/ui.jsx";

const EMPTY = { category: "chain", name: "", brand: "", spec: "", quantity: 1, min_quantity: "", price_eur: "", purchased_at: "", location: "", notes: "", bike_id: "" };

const toPayload = (f) => ({
  category: f.category, name: f.name.trim(), brand: f.brand || null, spec: f.spec || null,
  quantity: Number(f.quantity) || 0,
  min_quantity: f.min_quantity === "" ? null : Number(f.min_quantity),
  price_eur: f.price_eur === "" ? null : Number(String(f.price_eur).replace(",", ".")),
  purchased_at: f.purchased_at || null, location: f.location || null, notes: f.notes || null,
  bike_id: f.bike_id === "" ? null : Number(f.bike_id),
});

const fromItem = (i) => ({ ...EMPTY, ...Object.fromEntries(Object.entries(i).map(([k, v]) => [k, v ?? ""])) });
const euro = (v) => `${fmtNum(v, 2)} €`;

function ItemForm({ initial, bikes, onSave, onCancel, title }) {
  const [f, setF] = useState(initial);
  const [error, setError] = useState("");
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });
  async function submit(e) {
    e.preventDefault();
    setError("");
    try { await onSave(toPayload(f)); } catch (err) { setError(err.message); }
  }
  return (
    <form className="panel form-grid" onSubmit={submit}>
      <h2 className="span-all">{title}</h2>
      <label>Art
        <select value={f.category} onChange={set("category")}>
          {Object.entries(CATEGORIES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
        </select>
      </label>
      <label>Name<input value={f.name} onChange={set("name")} placeholder="z. B. Schwalbe G-One RS" required autoFocus /></label>
      <label>Marke<input value={f.brand} onChange={set("brand")} /></label>
      <label>Größe oder Typ<input value={f.spec} onChange={set("spec")} placeholder="z. B. 40 mm, 12-fach, 11-34" /></label>
      <label>Anzahl<input type="number" min="0" value={f.quantity} onChange={set("quantity")} /></label>
      <label>Warnen unter<input type="number" min="0" value={f.min_quantity} onChange={set("min_quantity")} placeholder="optional" /></label>
      <label>Preis je Stück (€)<input inputMode="decimal" value={f.price_eur} onChange={set("price_eur")} /></label>
      <label>Gekauft am<input type="date" value={f.purchased_at} onChange={set("purchased_at")} /></label>
      <label>Lagerort<input value={f.location} onChange={set("location")} placeholder="z. B. Keller, Regal 2" /></label>
      <label>Passt zu
        <select value={f.bike_id} onChange={set("bike_id")}>
          <option value="">Keinem bestimmten Rad</option>
          {bikes.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
      </label>
      <label className="span-all">Notiz<input value={f.notes} onChange={set("notes")} /></label>
      {error && <p className="error span-all" role="alert">{error}</p>}
      <div className="actions span-all">
        <button className="btn primary">Speichern</button>
        <button type="button" className="btn" onClick={onCancel}>Abbrechen</button>
      </div>
    </form>
  );
}

function InstallForm({ item, bikes, onDone, onCancel }) {
  const [bike, setBike] = useState(item.bike_id ?? bikes[0]?.id ?? "");
  const [date, setDate] = useState(today());
  const [error, setError] = useState("");
  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      const r = await api.post(`/inventory/${item.id}/install`, { bike_id: Number(bike), installed_at: date, with_rules: true });
      onDone(r);
    } catch (err) { setError(err.message); }
  }
  return (
    <form className="inline-form" onSubmit={submit}>
      <label>Einbauen an
        <select value={bike} onChange={(e) => setBike(e.target.value)} required>
          {bikes.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
      </label>
      <label>Datum<input type="date" value={date} onChange={(e) => setDate(e.target.value)} required /></label>
      <button className="btn primary">Einbauen</button>
      <button type="button" className="btn" onClick={onCancel}>Abbrechen</button>
      <p className="hint span-all">Ein vorhandenes Teil derselben Art am Rad wird ausgemustert. Das neue Teil bekommt die Wartungsregeln und zählt ab 0 km.</p>
      {error && <p className="error" role="alert">{error}</p>}
    </form>
  );
}

export default function Inventory() {
  const [data, setData] = useState(null);
  const [bikes, setBikes] = useState([]);
  const [error, setError] = useState("");
  const [mode, setMode] = useState(null); // {type: "new"} | {type: "edit"|"install", id}
  const [cat, setCat] = useState("");
  const [msg, setMsg] = useState("");

  const load = useCallback(async () => {
    const [inv, b] = await Promise.all([api.get("/inventory"), api.get("/bikes")]);
    setData(inv);
    setBikes(b.filter((x) => !x.retired));
  }, []);
  useEffect(() => { load().catch((e) => setError(e.message)); }, [load]);

  const items = useMemo(() => (data?.items ?? []).filter((i) => !cat || i.category === cat), [data, cat]);
  if (error) return <p className="error" role="alert">{error}</p>;
  if (!data) return <p className="muted">Lade …</p>;

  const t = data.totals;
  const bikeName = (id) => bikes.find((b) => b.id === id)?.name;
  const usedCats = [...new Set(data.items.map((i) => i.category))];

  async function save(payload, id) {
    if (id) await api.put(`/inventory/${id}`, payload); else await api.post("/inventory", payload);
    setMode(null);
    await load();
  }
  async function step(i, d) {
    const { id, low, ...rest } = i;
    await api.put(`/inventory/${id}`, { ...rest, quantity: Math.max(0, i.quantity + d) });
    await load();
  }
  async function remove(i) {
    if (!window.confirm(`„${i.name}“ aus dem Inventar löschen?`)) return;
    await api.del(`/inventory/${i.id}`);
    await load();
  }

  return (
    <>
      <header className="page-head">
        <h1>Inventar</h1>
        <div className="actions" style={{ margin: 0 }}>
          <Link className="btn" to="/garage">Zur Garage</Link>
          {mode?.type !== "new" && <button className="btn primary" onClick={() => setMode({ type: "new" })}>Teil hinzufügen</button>}
        </div>
      </header>

      {mode?.type === "new" && <ItemForm title="Neues Teil" initial={EMPTY} bikes={bikes} onSave={(p) => save(p)} onCancel={() => setMode(null)} />}
      {msg && <p className="ok" role="status">{msg}</p>}

      {data.items.length === 0 ? (
        <EmptyState title="Dein Lager ist leer" text="Trage Ersatzteile ein, die du zu Hause hast, etwa Ketten, Reifen oder Beläge. Beim Einbau legt BikeHelper das Teil mit Wartungsregeln am Rad an." />
      ) : (
        <>
          <div className="kpis">
            <Kpi value={t.items} label="Positionen" />
            <Kpi value={t.pieces} label="Teile im Lager" />
            <Kpi value={euro(t.value_eur)} label="Wert des Lagers" />
            {t.low > 0 && <Kpi value={t.low} label="mit niedrigem Bestand" />}
          </div>
          <div className="actions" style={{ marginTop: 0 }}>
            <button className={`chip ${cat === "" ? "on" : ""}`} onClick={() => setCat("")}>Alle</button>
            {usedCats.map((c) => <button key={c} className={`chip ${cat === c ? "on" : ""}`} onClick={() => setCat(c)}>{CATEGORIES[c] ?? c}</button>)}
          </div>
          <ul className="inv-list">
            {items.map((i) => (
              <li key={i.id} className={`panel inv-item ${i.quantity === 0 ? "gone" : ""}`}>
                {mode?.id === i.id && mode.type === "edit" ? (
                  <ItemForm title="Teil bearbeiten" initial={fromItem(i)} bikes={bikes} onSave={(p) => save(p, i.id)} onCancel={() => setMode(null)} />
                ) : (
                  <>
                    <div className="inv-main">
                      <span className="muted small">{CATEGORIES[i.category] ?? i.category}</span>
                      <strong>{i.name}</strong>
                      <span className="muted small">
                        {[i.brand, i.spec, i.location && `Lager: ${i.location}`, i.bike_id && `für ${bikeName(i.bike_id) ?? "Rad"}`,
                          i.price_eur != null && euro(i.price_eur), i.purchased_at && `gekauft ${fmtDate(i.purchased_at)}`].filter(Boolean).join(" · ")}
                      </span>
                      {i.notes && <span className="small">{i.notes}</span>}
                    </div>
                    <div className="inv-qty" aria-label="Anzahl">
                      <button className="qty-btn" onClick={() => step(i, -1)} disabled={i.quantity === 0} aria-label="Eines weniger">−</button>
                      <span className={i.low ? "low" : ""}>{i.quantity}</span>
                      <button className="qty-btn" onClick={() => step(i, 1)} aria-label="Eines mehr">+</button>
                      {i.low && <span className="pill pill-soon">knapp</span>}
                    </div>
                    <div className="inv-actions">
                      {i.quantity > 0 && bikes.length > 0 && <button className="btn small primary" onClick={() => setMode({ type: "install", id: i.id })}>Einbauen</button>}
                      <button className="link small" onClick={() => setMode({ type: "edit", id: i.id })}>Bearbeiten</button>
                      <button className="link small danger" onClick={() => remove(i)}>Löschen</button>
                    </div>
                    {mode?.id === i.id && mode.type === "install" && (
                      <div className="inv-install">
                        <InstallForm item={i} bikes={bikes} onCancel={() => setMode(null)} onDone={async (r) => {
                          setMode(null);
                          setMsg(r.replaced ? `Eingebaut. „${r.replaced}“ wurde ausgemustert.` : "Eingebaut.");
                          await load();
                        }} />
                      </div>
                    )}
                  </>
                )}
              </li>
            ))}
          </ul>
        </>
      )}
    </>
  );
}
