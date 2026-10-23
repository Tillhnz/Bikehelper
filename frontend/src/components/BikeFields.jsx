import { CHAIN_LUBES } from "../api.js";

/** Felder für Kettenschmierung und Reifen (gemeinsam für „Neues Rad“ und „Rad bearbeiten“). */
export default function BikeFields({ form, setForm }) {
  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const check = (k) => (e) => setForm({ ...form, [k]: e.target.checked });
  const lube = CHAIN_LUBES[form.chain_lube === "wax" ? "wax" : "oil"];
  return (
    <>
      <label className="span-all">
        Kettenschmierung
        <select value={form.chain_lube === "wax" ? "wax" : "oil"} onChange={set("chain_lube")}>
          {Object.entries(CHAIN_LUBES).map(([k, v]) => <option key={k} value={k}>{v.name}</option>)}
        </select>
        <span className="hint">{lube.hint}</span>
      </label>
      <p className="hint span-all">
        Reifenbreite und Tubeless übernimmt das Rad vom montierten Reifensatz. Du legst die Sätze auf der Seite des Rades unter „Reifen“ an.
      </p>
      <label>
        Innenweite der Felge (mm)
        <input type="number" min="12" max="40" step="0.5" value={form.rim_inner_mm ?? ""} onChange={set("rim_inner_mm")} placeholder="z. B. 21" />
        <span className="hint">Leer lassen, wenn unbekannt.</span>
      </label>
      <label>
        Gewicht des Rades (kg)
        <input type="number" min="3" max="40" step="0.1" value={form.bike_weight_kg ?? ""} onChange={set("bike_weight_kg")} placeholder="z. B. 8,5" />
      </label>
      <div className="checks">
        <label className="check">
          <input type="checkbox" checked={!!form.hookless} onChange={check("hookless")} /> Hookless-Felgen
        </label>
      </div>
    </>
  );
}

/** Leere Eingaben als null senden, Zahlen als Zahlen. */
export function bikePayload(form) {
  const num = (v) => (v === "" || v == null ? null : Number(v));
  return {
    ...form,
    brand: form.brand || null,
    model: form.model || null,
    start_km: Number(form.start_km) || 0,
    chain_lube: form.chain_lube === "wax" || form.chain_lube === "hot_wax" || form.chain_lube === "drip_wax" ? "wax" : "oil",
    tire_width_mm: num(form.tire_width_mm),
    rim_inner_mm: num(form.rim_inner_mm),
    bike_weight_kg: num(form.bike_weight_kg),
    tubeless: form.tubeless ?? true,
    hookless: !!form.hookless,
  };
}
