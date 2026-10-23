import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, fmtDuration, fmtKm, fmtNum } from "../api.js";
import { Bars, HBars } from "./charts.jsx";
import { Kpi, Panel } from "./statsui.jsx";
import { EmptyState } from "./ui.jsx";

const MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

function useData(path, deps) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setD(null);
    setError("");
    api.get(path).then(setD).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return [d, error, setD];
}

/** Liniendiagramm mit mehreren Reihen über Datumswerte, Nulllinie bei negativen Werten. */
function Lines({ labels, series, height = 200, zeroLine = false }) {
  const W = 640, padL = 36, padR = 8, padT = 10, padB = 22;
  const all = series.flatMap((s) => s.values);
  const lo = Math.min(0, ...all), hi = Math.max(1, ...all);
  const x = (i) => padL + (i / Math.max(1, labels.length - 1)) * (W - padL - padR);
  const y = (v) => padT + (1 - (v - lo) / (hi - lo)) * (height - padT - padB);
  const ticks = [lo, (lo + hi) / 2, hi];
  const step = Math.max(1, Math.floor(labels.length / 6));
  return (
    <>
      <svg viewBox={`0 0 ${W} ${height}`} className="chart" role="img" aria-label="Liniendiagramm">
        {ticks.map((t) => (
          <g key={t}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} className="chart-grid" />
            <text x={padL - 4} y={y(t) + 3} textAnchor="end" className="chart-label">{fmtNum(t, 0)}</text>
          </g>
        ))}
        {zeroLine && lo < 0 && <line x1={padL} x2={W - padR} y1={y(0)} y2={y(0)} stroke="var(--mute)" strokeWidth="1" />}
        {labels.map((l, i) => i % step === 0 && (
          <text key={l} x={x(i)} y={height - 6} textAnchor="middle" className="chart-label">{fmtDate(l).replace(/\.\d{4}$/, ".")}</text>
        ))}
        {series.map((s) => (
          <path key={s.name} className="draw" pathLength="1" fill="none" stroke={s.color} strokeWidth="2" strokeLinejoin="round"
            d={s.values.map((v, i) => `${i ? "L" : "M"}${x(i).toFixed(1)} ${y(v).toFixed(1)}`).join(" ")} />
        ))}
      </svg>
      <div className="legend">
        {series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}
      </div>
    </>
  );
}

function formText(f) {
  if (f > 10) return "sehr frisch";
  if (f > 0) return "frisch";
  if (f > -10) return "leicht ermüdet";
  if (f > -25) return "ermüdet";
  return "stark ermüdet";
}

export function LoadView({ bikeId }) {
  const [d, error] = useData(`/stats/extra${bikeId ? `?bike_id=${bikeId}` : ""}`, [bikeId]);
  if (error) return <p className="error" role="alert">{error}</p>;
  if (!d) return <p className="muted">Lade …</p>;
  if (d.empty) return <EmptyState title="Keine Fahrten gefunden" text="Importiere Fahrten, dann erscheint hier deine Belastung." />;
  const { series, weekly, now, note } = d.load;
  const thisWeek = weekly[weekly.length - 1], lastWeek = weekly[weekly.length - 2];
  return (
    <>
      <div className="kpis">
        <Kpi value={fmtNum(now.fitness, 0)} label="Fitness (Mittel der letzten 6 Wochen)" />
        <Kpi value={fmtNum(now.fatigue, 0)} label="Ermüdung (letzte 7 Tage)" />
        <Kpi value={`${now.form > 0 ? "+" : ""}${fmtNum(now.form, 0)}`} label={`Form: ${formText(now.form)}`} />
        <Kpi value={fmtKm(thisWeek.km)} unit="km" label={`diese Woche (Vorwoche ${fmtKm(lastWeek.km)})`} />
      </div>
      <Panel title="Fitness und Ermüdung" sub={`Letzte ${series.length} Tage. ${note}`}>
        <Lines labels={series.map((p) => p.date)} series={[
          { name: "Fitness", color: "var(--celeste)", values: series.map((p) => p.fitness) },
          { name: "Ermüdung", color: "var(--amber)", values: series.map((p) => p.fatigue) },
        ]} />
      </Panel>
      <div className="grid-2">
        <Panel title="Form" sub="Fitness minus Ermüdung. Über 0 bist du erholt, deutlich darunter brauchst du Ruhe.">
          <Lines zeroLine height={170} labels={series.map((p) => p.date)} series={[{ name: "Form", color: "var(--signal)", values: series.map((p) => p.form) }]} />
        </Panel>
        <Panel title="Belastung pro Woche" sub="Punkte aus Fahrzeit, Höhenmetern und Tempo">
          <Bars data={weekly.map((w) => ({ label: fmtDate(w.week).slice(0, 5), value: w.load, sub: `${fmtKm(w.km)} km, ${w.rides} Fahrten` }))} unit="Punkte" labelEvery={4} color="var(--amber)" />
        </Panel>
        <Panel title="Kilometer pro Woche">
          <Bars data={weekly.map((w) => ({ label: fmtDate(w.week).slice(0, 5), value: w.km, sub: `${fmtDuration(w.time_s)}, ${fmtKm(w.elev_m)} m` }))} unit="km" labelEvery={4} />
        </Panel>
        <Panel title="Höhenmeter pro Woche">
          <Bars data={weekly.map((w) => ({ label: fmtDate(w.week).slice(0, 5), value: w.elev_m, sub: `${fmtKm(w.km)} km` }))} unit="m" labelEvery={4} color="var(--signal)" />
        </Panel>
      </div>
    </>
  );
}

function MatrixTable({ years, rows, labels, unit = "" }) {
  const max = Math.max(1, ...rows.flat());
  return (
    <div className="scroll-x">
      <table className="matrix">
        <thead><tr><th />{labels.map((l) => <th key={l}>{l}</th>)}<th>Summe</th></tr></thead>
        <tbody>
          {rows.map((r, i) => (
            <tr key={years[i]}>
              <th>{years[i]}</th>
              {r.map((v, j) => (
                <td key={j} style={{ "--a": v / max }} title={`${fmtKm(v)} ${unit}`}>{v ? fmtKm(v) : ""}</td>
              ))}
              <td className="sum">{fmtKm(r.reduce((a, b) => a + b, 0))}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function RideList({ items, unit, fmt = (v) => fmtNum(v) }) {
  return (
    <ol className="top-list">
      {items.map((r) => (
        <li key={r.id}>
          <Link to={`/rides/${r.id}`}>{r.name}</Link>
          <span className="muted small">{fmtDate(r.date)}</span>
          <strong>{fmt(r.value)} {unit}</strong>
        </li>
      ))}
    </ol>
  );
}

export function CompareView({ bikeId }) {
  const [d, error] = useData(`/stats/extra${bikeId ? `?bike_id=${bikeId}` : ""}`, [bikeId]);
  if (error) return <p className="error" role="alert">{error}</p>;
  if (!d) return <p className="muted">Lade …</p>;
  if (d.empty) return <EmptyState title="Keine Fahrten gefunden" text="Importiere Fahrten, dann erscheinen hier die Vergleiche." />;
  const { month_matrix: mm, bike_years: by, equivalents: eq, breaks: br } = d;
  return (
    <>
      <div className="kpis">
        <Kpi value={fmtNum(eq.earth_laps, 2)} unit="×" label="um die Erde (40.075 km)" />
        <Kpi value={fmtNum(eq.everests, 1)} unit="×" label="Mount Everest hoch" />
        <Kpi value={fmtNum(eq.moon_percent, 1)} unit="%" label="des Wegs zum Mond" />
        <Kpi value={fmtNum(eq.days_in_saddle, 1)} unit="Tage" label="reine Fahrzeit im Sattel" />
        <Kpi value={br.longest_week_streak} unit="Wochen" label="Serie mit Fahrt jede Woche" />
        <Kpi value={br.longest_days} unit="Tage" label={br.from ? `längste Pause (${fmtDate(br.from)} bis ${fmtDate(br.to)})` : "längste Pause"} />
      </div>

      <Panel title="Kilometer pro Monat und Jahr" sub="Je dunkler, desto mehr Kilometer.">
        <MatrixTable years={mm.years} rows={mm.km} labels={MONTHS} unit="km" />
      </Panel>

      <Panel title="Räder im Vergleich" sub="Kilometer pro Jahr">
        <div className="scroll-x">
          <table className="matrix plain">
            <thead><tr><th />{by.years.map((y) => <th key={y}>{y}</th>)}<th>Summe</th></tr></thead>
            <tbody>
              {by.bikes.map((b) => (
                <tr key={b.name}><th>{b.name}</th>{b.km.map((v, i) => <td key={i}>{v ? fmtKm(v) : "–"}</td>)}<td className="sum">{fmtKm(b.total)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>

      <div className="grid-2">
        <Panel title="Tempo" sub="Durchschnittsgeschwindigkeit je Fahrt (ab 5 km)">
          <HBars rows={d.speed_buckets.map((b) => ({ label: b.label, value: b.rides, text: `${b.rides} Fahrten` }))} />
        </Panel>
        <Panel title="Profil der Fahrten" sub="Höhenmeter je Kilometer">
          <HBars rows={d.climb_buckets.map((b) => ({ label: b.label, value: b.rides, text: `${b.rides} Fahrten` }))} color="var(--signal)" />
        </Panel>
        <Panel title="Tageszeit" sub="Fahrzeit in Stunden">
          <HBars rows={d.dayparts.map((b) => ({ label: b.label, value: b.hours, text: `${fmtNum(b.hours, 0)} h` }))} color="var(--amber)" />
        </Panel>
        <Panel title="Jahreszeiten" sub="Kilometer insgesamt">
          <Bars data={d.seasons.map((s) => ({ label: s.label, value: s.km }))} unit="km" />
        </Panel>
        <Panel title="Durchschnittstempo pro Monat" sub="Letzte 24 Monate mit Fahrten">
          <Bars data={d.speed_by_month.map((m) => ({ label: m.month.slice(2), value: m.avg_speed }))} unit="km/h" labelEvery={3} format={(v) => fmtNum(v, 1)} color="var(--amber)" />
        </Panel>
        <Panel title="Meilensteine" sub="Wann du welche Gesamtstrecke erreicht hast">
          {d.milestones.length === 0 ? <p className="muted">Noch keiner erreicht (erster bei 500 km).</p> : (
            <ul className="record-list">
              {[...d.milestones].reverse().map((m) => (
                <li key={m.km}><span>{fmtDate(m.date)}<br /><span className="muted small">{m.rides}. Fahrt</span></span><strong>{fmtKm(m.km)} km</strong></li>
              ))}
            </ul>
          )}
        </Panel>
        <Panel title="Längste Fahrten"><RideList items={d.top_rides} unit="km" /></Panel>
        <Panel title="Meiste Höhenmeter"><RideList items={d.top_climbs} unit="m" fmt={(v) => fmtKm(v)} /></Panel>
      </div>
    </>
  );
}

function Delta({ v }) {
  if (v == null) return null;
  return <span className={`delta ${v >= 0 ? "up" : "down"}`}>{v >= 0 ? "▲" : "▼"} {fmtNum(Math.abs(v), 0)} % zum Vorjahr</span>;
}

export function ReviewView({ bikeId, years }) {
  const [year, setYear] = useState(null);
  const y = year ?? (years.length ? years[years.length - 1] : null);
  const [d, error] = useData(y ? `/stats/review?year=${y}${bikeId ? `&bike_id=${bikeId}` : ""}` : "/stats/extra", [y, bikeId]);
  if (!y) return <EmptyState title="Keine Fahrten gefunden" text="Importiere Fahrten, dann entsteht hier dein Jahresrückblick." />;
  return (
    <>
      <div className="actions" style={{ marginTop: 0, marginBottom: "1rem" }}>
        {years.map((v) => <button key={v} className={`chip ${v === y ? "on" : ""}`} onClick={() => setYear(v)}>{v}</button>)}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {!d && !error && <p className="muted">Lade …</p>}
      {d?.empty && <EmptyState title={`Keine Fahrten ${y}`} />}
      {d && !d.empty && d.totals && <ReviewBody d={d} />}
    </>
  );
}

function ReviewBody({ d }) {
  const t = d.totals;
  const lr = (r) => r && `${r.name} · ${fmtDate(r.date)}`;
  return (
    <>
      <div className="kpis">
        <Kpi value={fmtKm(t.km)} unit="km" label="Strecke" extra={<Delta v={d.delta?.km} />} />
        <Kpi value={fmtKm(t.rides)} label="Fahrten" extra={<Delta v={d.delta?.rides} />} />
        <Kpi value={fmtKm(t.elev_m)} unit="m" label="Höhenmeter" extra={<Delta v={d.delta?.elev_m} />} />
        <Kpi value={fmtDuration(t.time_s)} label="Fahrzeit" />
        <Kpi value={fmtNum(t.avg_speed)} unit="km/h" label="Ø Geschwindigkeit" />
        <Kpi value={fmtKm(d.active_days)} label={`Fahrtage (${d.active_share} % des Jahres)`} />
      </div>
      <div className="grid-2">
        <Panel title="Kilometer pro Monat">
          <Bars data={d.months.map((m) => ({ label: MONTHS[m.month - 1], value: m.km }))} unit="km" />
        </Panel>
        <Panel title="Höhepunkte">
          <ul className="record-list">
            <li><span>Stärkster Monat</span><strong>{MONTHS[d.best_month.month - 1]}, {fmtKm(d.best_month.km)} km</strong></li>
            <li><span>Lieblingstag<br /><span className="muted small">{d.best_weekday.rides} Fahrten</span></span><strong>{d.best_weekday.label}, {fmtKm(d.best_weekday.km)} km</strong></li>
            <li><span>Meistgefahrenes Rad</span><strong>{d.favorite_bike.name}, {fmtKm(d.favorite_bike.km)} km</strong></li>
            <li><span>Längste Fahrt<br /><span className="muted small">{lr(d.longest_ride)}</span></span><strong>{fmtNum(d.longest_ride.value)} km</strong></li>
            <li><span>Meiste Höhenmeter<br /><span className="muted small">{lr(d.most_climbing)}</span></span><strong>{fmtKm(d.most_climbing.value)} m</strong></li>
            <li><span>Fahrten über 100 km</span><strong>{d.rides_100}</strong></li>
            <li><span>Fahrten über 150 km</span><strong>{d.rides_150}</strong></li>
            <li><span>Frühstarter<br /><span className="muted small">Start vor 7 Uhr</span></span><strong>{d.early_rides}</strong></li>
            <li><span>Winterfahrten<br /><span className="muted small">Dezember bis Februar</span></span><strong>{d.winter_rides}</strong></li>
            <li><span>Längste Serie</span><strong>{d.longest_streak_days} Tage</strong></li>
            <li><span>Längste Pause</span><strong>{d.longest_break_days} Tage</strong></li>
            {d.coldest && <li><span>Kälteste Fahrt<br /><span className="muted small">{lr(d.coldest)}</span></span><strong>{fmtNum(d.coldest.value)} °C</strong></li>}
            {d.hottest && <li><span>Wärmste Fahrt<br /><span className="muted small">{lr(d.hottest)}</span></span><strong>{fmtNum(d.hottest.value)} °C</strong></li>}
            <li><span>Kilometer bei Nässe</span><strong>{fmtKm(d.wet_km)} km</strong></li>
            <li><span>Erkundete Kacheln<br /><span className="muted small">{fmtKm(d.new_tiles)} davon neu in diesem Jahr</span></span><strong>{fmtKm(d.tiles)}</strong></li>
          </ul>
        </Panel>
        <Panel title="Die fünf längsten Fahrten"><RideList items={d.top_rides} unit="km" /></Panel>
        <Panel title="Zum Vergleich">
          <ul className="record-list">
            <li><span>Anteil an einer Erdumrundung</span><strong>{fmtNum(d.equivalents.earth_percent, 1)} %</strong></li>
            <li><span>Everest-Besteigungen</span><strong>{fmtNum(d.equivalents.everests, 1)} ×</strong></li>
            {d.previous && <li><span>Vorjahr<br /><span className="muted small">{d.previous.rides} Fahrten, {fmtKm(d.previous.elev_m)} m</span></span><strong>{fmtKm(d.previous.km)} km</strong></li>}
          </ul>
        </Panel>
      </div>
    </>
  );
}

const GOAL_META = {
  km: { label: "Kilometer", unit: "km", step: 100 },
  elev_m: { label: "Höhenmeter", unit: "m", step: 1000 },
  rides: { label: "Fahrten", unit: "Fahrten", step: 5 },
  time_h: { label: "Fahrzeit", unit: "h", step: 10 },
};

export function GoalsView() {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = useState(thisYear);
  const [d, error, setD] = useData(`/stats/goals?year=${year}`, [year]);
  const [form, setForm] = useState({});
  const [msg, setMsg] = useState("");
  const [err, setErr] = useState("");

  useEffect(() => { if (d) setForm(Object.fromEntries(Object.keys(GOAL_META).map((k) => [k, d.targets[k] ?? ""]))); }, [d]);

  async function save(e) {
    e.preventDefault();
    setMsg(""); setErr("");
    try {
      const targets = Object.fromEntries(Object.entries(form).map(([k, v]) => [k, v === "" ? null : Number(String(v).replace(",", "."))]));
      setD(await api.put("/stats/goals", { year, targets }));
      setMsg("Ziele gespeichert.");
    } catch (x) {
      setErr(x.message);
    }
  }

  return (
    <>
      <div className="actions" style={{ marginTop: 0, marginBottom: "1rem" }}>
        {[thisYear - 1, thisYear, thisYear + 1].map((v) => <button key={v} className={`chip ${v === year ? "on" : ""}`} onClick={() => setYear(v)}>{v}</button>)}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {d && (
        <>
          {d.progress.length === 0 && <p className="muted">Noch keine Ziele für {year}. Trage unten eines ein.</p>}
          <div className="goal-grid">
            {d.progress.map((g) => {
              const m = GOAL_META[g.metric];
              const pct = Math.min(100, g.percent), plan = Math.min(100, (g.plan / g.target) * 100);
              return (
                <section key={g.metric} className={`panel goal ${g.reached_on ? "is-done" : g.on_track ? "is-ok" : "is-late"}`}>
                  <h2>{m.label}</h2>
                  <div className="goal-num"><strong>{fmtKm(g.done)}</strong> <span className="muted">von {fmtKm(g.target)} {m.unit}</span></div>
                  <div className="goal-bar" role="progressbar" aria-valuenow={Math.round(g.percent)} aria-valuemin={0} aria-valuemax={100}>
                    <span style={{ width: `${pct}%` }} />
                    <i style={{ left: `${plan}%` }} title="Plan bei gleichmäßigem Tempo" />
                  </div>
                  <p className="small">
                    {g.reached_on ? `Geschafft am ${fmtDate(g.reached_on)}.` : (
                      <>
                        {fmtNum(g.percent, 0)} % · {g.ahead >= 0 ? `${fmtKm(g.ahead)} ${m.unit} vor dem Plan` : `${fmtKm(-g.ahead)} ${m.unit} hinter dem Plan`}.
                        {" "}Im aktuellen Tempo kommst du auf {fmtKm(g.projected)} {m.unit}.
                        {g.per_week_needed != null && ` Bis zum Ziel nötig: ${fmtKm(g.per_week_needed)} ${m.unit} pro Woche.`}
                      </>
                    )}
                  </p>
                </section>
              );
            })}
          </div>
          <Panel title={`Ziele für ${year}`} sub="Leer lassen, wenn du kein Ziel willst.">
            <form className="inline-form" onSubmit={save}>
              {Object.entries(GOAL_META).map(([k, m]) => (
                <label key={k}>{m.label} ({m.unit})
                  <input inputMode="decimal" value={form[k] ?? ""} onChange={(e) => setForm({ ...form, [k]: e.target.value })} placeholder={String(m.step * 10)} />
                </label>
              ))}
              <button className="btn primary">Ziele speichern</button>
            </form>
            {msg && <p className="ok" role="status">{msg}</p>}
            {err && <p className="error" role="alert">{err}</p>}
          </Panel>
        </>
      )}
    </>
  );
}
