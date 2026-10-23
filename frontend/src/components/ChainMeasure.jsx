import { useCallback, useEffect, useState } from "react";
import { api, fmtDate, fmtKm, fmtNum, today } from "../api.js";

/** Kleines Diagramm: gemessene Längung über die Kilometer der Kette, mit Grenzwert. */
function WearChart({ points, limit }) {
  const w = 300, h = 110, pad = { l: 34, r: 8, t: 8, b: 20 };
  const maxX = Math.max(1, ...points.map((p) => p.km));
  const maxY = Math.max(limit * 1.15, ...points.map((p) => p.wear_pct));
  const x = (v) => pad.l + (v / maxX) * (w - pad.l - pad.r);
  const y = (v) => h - pad.b - (v / maxY) * (h - pad.t - pad.b);
  const line = [{ km: 0, wear_pct: 0 }, ...points].map((p, i) => `${i ? "L" : "M"}${x(p.km).toFixed(1)} ${y(p.wear_pct).toFixed(1)}`).join(" ");
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="wear-chart" role="img" aria-label="Kettenlängung über die gefahrenen Kilometer">
      <line x1={pad.l} x2={w - pad.r} y1={y(limit)} y2={y(limit)} className="wear-limit" />
      <text x={pad.l - 4} y={y(limit) + 3} textAnchor="end" className="wear-axis">{fmtNum(limit, 2)} %</text>
      <line x1={pad.l} x2={w - pad.r} y1={y(0)} y2={y(0)} className="wear-base" />
      <text x={pad.l - 4} y={y(0) + 3} textAnchor="end" className="wear-axis">0</text>
      <text x={w - pad.r} y={h - 5} textAnchor="end" className="wear-axis">{fmtKm(maxX)} km</text>
      <path d={line} className="wear-line draw" pathLength="1" />
      {points.map((p) => <circle key={p.id} cx={x(p.km)} cy={y(p.wear_pct)} r="3.2" className={p.wear_pct >= limit ? "wear-dot over" : "wear-dot"} />)}
    </svg>
  );
}

export default function ChainMeasure({ comp, rule, disabled, onChanged }) {
  const [points, setPoints] = useState([]);
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ measured_at: today(), wear_pct: "", limit_pct: String(comp.wear_limit_pct ?? 0.5), note: "" });
  const [error, setError] = useState("");

  const load = useCallback(async () => setPoints(await api.get(`/components/${comp.id}/measurements`)), [comp.id]);
  useEffect(() => { load().catch(() => {}); }, [load, comp.km]);

  const limit = comp.wear_limit_pct ?? 0.5;
  const m = rule?.measure;

  async function submit(e) {
    e.preventDefault();
    setError("");
    try {
      const value = Number(String(form.wear_pct).replace(",", "."));
      if (!Number.isFinite(value) || value < 0) throw new Error("Bitte die gemessene Längung in Prozent eintragen, z. B. 0,3.");
      setPoints(await api.post(`/components/${comp.id}/measurements`, {
        measured_at: form.measured_at, wear_pct: value, limit_pct: Number(form.limit_pct), note: form.note || null,
      }));
      setForm({ ...form, wear_pct: "", note: "" });
      setOpen(false);
      onChanged();
    } catch (err) {
      setError(err.message);
    }
  }

  async function remove(p) {
    if (!window.confirm(`Messung vom ${fmtDate(p.measured_at)} löschen?`)) return;
    setPoints(await api.del(`/measurements/${p.id}`));
    onChanged();
  }

  return (
    <section className="chain-measure">
      <div className="chain-measure-head">
        <strong>Kettenlehre</strong>
        {!disabled && <button className="link small" onClick={() => setOpen(!open)}>Messwert eintragen</button>}
      </div>
      {m ? (
        <p className="small">
          Zuletzt {fmtNum(m.wear_pct, 2)} % gemessen ({fmtDate(m.measured_at)}), jetzt geschätzt {fmtNum(m.projected_pct, 2)} % von {fmtNum(m.limit_pct, 2)} %
          {m.km_left != null ? `, noch etwa ${fmtKm(m.km_left)} km bis zum Wechsel.` : "."}
        </p>
      ) : (
        <p className="muted small">Noch nicht gemessen. Mit einem Messwert rechnet BikeHelper mit dem echten Zustand der Kette statt nur mit Kilometern.</p>
      )}
      {points.length > 0 && <WearChart points={points} limit={limit} />}
      {points.length > 0 && (
        <ul className="log-list">
          {[...points].reverse().map((p) => (
            <li key={p.id}>
              <span><strong>{fmtDate(p.measured_at)}</strong> {fmtNum(p.wear_pct, 2)} % nach {fmtKm(p.km)} km{p.note ? ` – ${p.note}` : ""}</span>
              {!disabled && <button className="link small danger" onClick={() => remove(p)}>Löschen</button>}
            </li>
          ))}
        </ul>
      )}
      {open && (
        <form className="inline-form" onSubmit={submit}>
          <label>Datum<input type="date" value={form.measured_at} onChange={(e) => setForm({ ...form, measured_at: e.target.value })} required /></label>
          <label>Längung in %<input inputMode="decimal" value={form.wear_pct} onChange={(e) => setForm({ ...form, wear_pct: e.target.value })} placeholder="z. B. 0,3" required /></label>
          <label>Grenzwert der Lehre
            <select value={form.limit_pct} onChange={(e) => setForm({ ...form, limit_pct: e.target.value })}>
              <option value="0.5">0,5 % (10-fach und mehr)</option>
              <option value="0.75">0,75 % (9-fach und weniger)</option>
            </select>
          </label>
          <label className="grow">Notiz<input value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} /></label>
          <button className="btn primary">Messwert speichern</button>
          <button type="button" className="btn" onClick={() => setOpen(false)}>Abbrechen</button>
        </form>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}
