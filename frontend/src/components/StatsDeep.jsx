import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, fmtDate, fmtDuration, fmtKm, fmtNum } from "../api.js";
import { Bars, HBars } from "./charts.jsx";
import { Lines } from "./StatsExtra.jsx";
import { Kpi, Panel } from "./statsui.jsx";
import { EmptyState } from "./ui.jsx";
import { Loading } from "./feedback.jsx";

function useData(path, deps) {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    setD(null);
    setError("");
    api.get(path).then(setD).catch((e) => setError(e.message));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return [d, error];
}

const qs = (bikeId) => (bikeId ? `?bike_id=${bikeId}` : "");
const sign = (v, digits = 1) => (v == null ? "–" : `${v > 0 ? "+" : ""}${fmtNum(v, digits)}`);

/** Kleine Texte mit der wichtigsten Erkenntnis, damit man nicht jede Grafik deuten muss. */
function Insights({ items }) {
  const list = items.filter(Boolean);
  if (!list.length) return null;
  return (
    <ul className="insights">
      {list.map((t, i) => <li key={i}>{t}</li>)}
    </ul>
  );
}

function formText(f) {
  if (f > 10) return "sehr frisch";
  if (f > 0) return "frisch";
  if (f > -10) return "leicht ermüdet";
  if (f > -25) return "ermüdet";
  return "stark ermüdet";
}

// ---------- Leistung ----------

export function PowerView({ bikeId }) {
  const [d, error] = useData(`/stats/power${qs(bikeId)}`, [bikeId]);
  if (error) return <p className="error" role="alert">{error}</p>;
  if (!d) return <Loading />;
  if (!d.has_curve) {
    return (
      <EmptyState
        title="Noch keine Leistungsdaten"
        text={d.rides_with_power
          ? "Es gibt Fahrten mit Leistung, aber für die Leistungskurve fehlt noch ein längerer Verlauf. Wichtig sind Fahrten von mindestens 5 Minuten mit Wattwerten."
          : "Sobald Fahrten mit Wattwerten vorliegen (Leistungsmesser, per Datei oder intervals.icu importiert), erscheinen hier Leistungskurve, FTP und Zonen."}
      />
    );
  }
  const best20 = d.curve.find((c) => c.seconds === 1200);
  const form = d.form || [];
  const now = form[form.length - 1];
  const hist = d.ftp_history || [];
  return (
    <>
      <div className="kpis">
        <Kpi value={d.ftp ? fmtNum(d.ftp, 0) : "–"} unit="W" label={d.ftp_stale ? "FTP (Stand: ältere Fahrten)" : "FTP (geschätzt)"} />
        <Kpi value={d.ftp_wkg ? fmtNum(d.ftp_wkg, 2) : "–"} unit="W/kg" label={d.weight_kg ? `bei ${fmtNum(d.weight_kg, 1)} kg` : "Gewicht in den Einstellungen eintragen"} />
        <Kpi value={best20 ? fmtNum(best20.best, 0) : "–"} unit="W" label="Beste 20 Minuten" />
        <Kpi value={d.avg_power ? fmtNum(d.avg_power, 0) : "–"} unit="W" label={`Ø Leistung, ${d.rides_with_power} Fahrten`} />
      </div>
      <Insights items={[
        d.ftp && `FTP-Schätzung: ${d.ftp_basis}. Sie bezieht sich auf die Fahrten der letzten 90 Tage${d.ftp_stale ? " (dort gab es keine mit Leistung, daher gilt dein letzter bekannter Stand)" : ""}. Wer nie voll ausgefahren ist, liegt real höher.`,
        d.ftp_best && d.ftp && d.ftp_best > d.ftp * 1.03 && `Dein bester Stand lag bei ${fmtNum(d.ftp_best, 0)} W, das sind ${fmtNum(d.ftp_best - d.ftp, 0)} W mehr als jetzt.`,
        d.approx_note && "Ältere Fahrten ohne Sekundenverlauf sind aus dem Streckenprofil genähert (gilt ab 5 Minuten). Neu importierte Fahrten sind exakt.",
      ]} />
      <div className="grid-2">
        <Panel title="Leistungskurve" sub="Deine besten Durchschnittswerte über feste Zeiträume (alle Fahrten).">
          <Bars
            data={d.curve.map((c) => ({ label: c.label, value: c.best, sub: c.best_date ? fmtDate(c.best_date) : "" }))}
            unit="W" color="var(--signal)"
          />
          <div className="scroll-x">
            <table className="plain-table">
              <thead><tr><th>Dauer</th><th>Bestwert</th><th>W/kg</th><th>90 Tage</th><th>{new Date().getFullYear()}</th></tr></thead>
              <tbody>
                {d.curve.map((c) => (
                  <tr key={c.seconds}>
                    <td>{c.label}{c.approx ? " ≈" : ""}</td><td>{fmtNum(c.best, 0)} W</td>
                    <td>{c.wkg ? fmtNum(c.wkg, 2) : "–"}</td>
                    <td>{c.recent ? `${fmtNum(c.recent, 0)} W` : "–"}</td><td>{c.year ? `${fmtNum(c.year, 0)} W` : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
        <Panel title="FTP im Verlauf" sub="Monatlich geschätzt aus den jeweils letzten 90 Tagen.">
          {hist.length >= 2
            ? <Lines labels={hist.map((h) => `${h.month}-01`)} series={[{ name: "FTP", color: "var(--celeste)", values: hist.map((h) => h.ftp) }]} />
            : <p className="muted">Für einen Verlauf braucht es Fahrten aus mindestens zwei Monaten.</p>}
        </Panel>
      </div>
      {d.zones && (
        <div className="grid-2">
          <Panel title="Leistungsbereiche" sub="Aus deiner FTP abgeleitet (Zonen nach Coggan).">
            <div className="scroll-x">
              <table className="plain-table">
                <thead><tr><th>Zone</th><th>Watt</th></tr></thead>
                <tbody>
                  {d.zones.map((z) => (
                    <tr key={z.name}><td>{z.name}</td><td>{z.to == null ? `ab ${z.from}` : `${z.from}–${z.to}`} W</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel title="Stunden je Zone" sub="Jede Fahrt zählt in der Zone ihrer Durchschnittsleistung. Intervalle verschwinden darin, es ist ein grobes Bild.">
            <HBars rows={d.zone_hours.map((z) => ({ label: z.name, value: z.hours, text: `${fmtNum(z.hours, 1)} h` }))} />
          </Panel>
        </div>
      )}
      {now && (
        <Panel title="Form aus Leistung" sub="Fitness, Ermüdung und Form aus Fahrten mit Wattwerten (Trainingspunkte nach FTP, Schätzung über die Durchschnittsleistung).">
          <div className="kpis">
            <Kpi value={fmtNum(now.fitness, 0)} label="Fitness (42 Tage)" />
            <Kpi value={fmtNum(now.fatigue, 0)} label="Ermüdung (7 Tage)" />
            <Kpi value={`${now.form > 0 ? "+" : ""}${fmtNum(now.form, 0)}`} label={`Form: ${formText(now.form)}`} />
          </div>
          <Lines labels={form.map((p) => p.date)} series={[
            { name: "Fitness", color: "var(--celeste)", values: form.map((p) => p.fitness) },
            { name: "Ermüdung", color: "var(--amber)", values: form.map((p) => p.fatigue) },
          ]} />
        </Panel>
      )}
    </>
  );
}

// ---------- Muster und Wetter ----------

function SpeedBars({ rows, color }) {
  const withData = rows.filter((r) => r.value != null);
  if (!withData.length) return <p className="muted">Zu wenig Fahrten für einen Vergleich (je Gruppe mindestens 3).</p>;
  return (
    <Bars
      data={rows.map((r) => ({ label: r.label, value: r.value ?? 0, sub: `${r.rides} Fahrten${r.delta_pct != null ? `, ${sign(r.delta_pct)} %` : ""}` }))}
      unit="km/h" color={color} format={(v) => fmtNum(v, 1)}
    />
  );
}

export function PatternsView({ bikeId }) {
  const [c, e1] = useData(`/stats/conditions${qs(bikeId)}`, [bikeId]);
  const [p, e2] = useData(`/stats/patterns${qs(bikeId)}`, [bikeId]);
  if (e1 || e2) return <p className="error" role="alert">{e1 || e2}</p>;
  if (!c || !p) return <Loading />;
  if (!c.rides) return <EmptyState title="Keine Fahrten gefunden" text="Importiere Fahrten, dann zeigt BikeHelper hier, bei welchem Wetter und zu welcher Zeit du am besten fährst." />;
  const w = (x) => x.map((r) => ({ label: r.label, value: r.speed, rides: r.rides }));
  return (
    <>
      <div className="kpis">
        <Kpi value={fmtNum(c.base_speed, 1)} unit="km/h" label="Dein Durchschnittstempo" />
        <Kpi value={c.fastest_temp ?? "–"} label="Am schnellsten bei" />
        <Kpi value={p.fastest_weekday ?? "–"} label="Schnellster Wochentag" />
        <Kpi value={p.ride_days_per_week != null ? fmtNum(p.ride_days_per_week, 1) : "–"} label="Fahrtage pro aktiver Woche" />
      </div>
      <Insights items={[
        c.wet_dry && `Bei Regen fährst du ${fmtNum(Math.abs(c.wet_dry.delta_pct), 1)} % ${c.wet_dry.delta_pct < 0 ? "langsamer" : "schneller"} als bei trockenen Fahrten (${fmtNum(c.wet_dry.wet, 1)} gegen ${fmtNum(c.wet_dry.dry, 1)} km/h).`,
        c.wind_cost_pct != null && `Bei starkem Wind liegt dein Tempo ${fmtNum(Math.abs(c.wind_cost_pct), 1)} % ${c.wind_cost_pct < 0 ? "unter" : "über"} dem bei Windstille. Die Windrichtung ist nicht gespeichert, es ist also ein Mittel aus Gegen- und Rückenwind.`,
        c.most_rides_temp && `Die meisten Fahrten machst du bei ${c.most_rides_temp}.`,
        p.fastest_daypart && `Zu welcher Tageszeit du am schnellsten bist: ${p.fastest_daypart}.`,
        p.median_pause_days != null && `Typische Pause zwischen zwei Fahrtagen: ${p.median_pause_days} Tag${p.median_pause_days === 1 ? "" : "e"}, die längste war ${p.longest_pause_days} Tage.`,
      ]} />
      <div className="grid-2">
        <Panel title="Tempo nach Temperatur" sub={`Abweichung zum Durchschnitt in der Beschriftung. ${c.weather_rides} Fahrten mit Wetterdaten.`}>
          <SpeedBars rows={w(c.temp).map((r, i) => ({ ...r, delta_pct: c.temp[i].delta_pct }))} color="var(--amber)" />
        </Panel>
        <Panel title="Tempo nach Wind" sub="Mittlere Windgeschwindigkeit während der Fahrt.">
          <SpeedBars rows={w(c.wind).map((r, i) => ({ ...r, delta_pct: c.wind[i].delta_pct }))} color="var(--celeste)" />
        </Panel>
        {c.power_by_temp.some((r) => r.value != null) && (
          <Panel title="Leistung nach Temperatur" sub="Durchschnittliche Wattzahl der Fahrten.">
            <Bars data={c.power_by_temp.map((r) => ({ label: r.label, value: r.value ?? 0, sub: `${r.rides} Fahrten` }))} unit="W" color="var(--signal)" />
          </Panel>
        )}
        <Panel title="Tempo nach Wochentag">
          <SpeedBars rows={w(p.weekday)} color="var(--celeste)" />
        </Panel>
        <Panel title="Tempo nach Tageszeit">
          <SpeedBars rows={w(p.daypart)} color="var(--amber)" />
        </Panel>
        <Panel title="Tempo nach Jahreszeit">
          <SpeedBars rows={w(p.season)} color="var(--signal)" />
        </Panel>
        <Panel title="Wirkt sich Ruhe aus?" sub="Dein Tempo, abhängig von den Tagen ohne Fahrt davor.">
          <SpeedBars rows={w(p.rest)} color="var(--celeste)" />
        </Panel>
      </div>
    </>
  );
}

// ---------- Räder und Prognose ----------

const TERRAIN = { road: "Straße", gravel: "Gravel", mtb: "Gelände", ebike: "E-Bike" };

export function BikesView() {
  const [d, e1] = useData("/stats/bikes", []);
  const [f, e2] = useData("/stats/forecast", []);
  if (e1 || e2) return <p className="error" role="alert">{e1 || e2}</p>;
  if (!d || !f) return <Loading />;
  const bikes = d.bikes;
  const cell = (v, unit = "", digits = 0) => (v == null ? "–" : `${fmtNum(v, digits)}${unit}`);
  return (
    <>
      {bikes.length === 0 ? (
        <EmptyState title="Noch keine Fahrten" text="Sobald Fahrten einem Rad zugeordnet sind, siehst du sie hier nebeneinander." />
      ) : (
        <>
          <Panel title="Räder im Vergleich" sub="Alle Fahrten je Rad. Wechsel von Teilen zählen nur für Teile mit Ausbaudatum.">
            <div className="scroll-x">
              <table className="plain-table compare-table">
                <thead><tr><th />{bikes.map((b) => <th key={b.bike_id ?? "none"}>{b.name}</th>)}</tr></thead>
                <tbody>
                  <tr><th>Anteil der Kilometer</th>{bikes.map((b) => <td key={b.name}>{cell(b.share, " %")}</td>)}</tr>
                  <tr><th>Kilometer</th>{bikes.map((b) => <td key={b.name}>{fmtKm(b.km)}</td>)}</tr>
                  <tr><th>Fahrten</th>{bikes.map((b) => <td key={b.name}>{b.rides}</td>)}</tr>
                  <tr><th>Fahrzeit</th>{bikes.map((b) => <td key={b.name}>{cell(b.hours, " h", 0)}</td>)}</tr>
                  <tr><th>Ø Fahrtlänge</th>{bikes.map((b) => <td key={b.name}>{cell(b.avg_ride_km, " km")}</td>)}</tr>
                  <tr><th>Längste Fahrt</th>{bikes.map((b) => <td key={b.name}>{cell(b.longest_km, " km")}</td>)}</tr>
                  <tr><th>Ø Tempo</th>{bikes.map((b) => <td key={b.name}>{cell(b.speed, " km/h", 1)}</td>)}</tr>
                  <tr><th>Höhenmeter je 100 km</th>{bikes.map((b) => <td key={b.name}>{cell(b.elev_per_100, " m")}</td>)}</tr>
                  <tr><th>Anteil Fahrzeit bei Nässe</th>{bikes.map((b) => <td key={b.name}>{cell(b.wet_share, " %")}</td>)}</tr>
                  <tr><th>Ø Leistung</th>{bikes.map((b) => <td key={b.name}>{cell(b.power, " W")}</td>)}</tr>
                  <tr><th>Ersetzte Teile</th>{bikes.map((b) => <td key={b.name}>{b.replaced == null ? "–" : b.replaced}</td>)}</tr>
                  <tr><th>Ersetzte Teile je 1000 km</th>{bikes.map((b) => <td key={b.name}>{cell(b.replaced_per_1000, "", 1)}</td>)}</tr>
                  <tr><th>Untergrund</th>{bikes.map((b) => (
                    <td key={b.name}>{Object.keys(b.terrain).length ? Object.entries(b.terrain).map(([k, v]) => `${TERRAIN[k] ?? k} ${v} %`).join(", ") : "–"}</td>
                  ))}</tr>
                  <tr><th>Zeitraum</th>{bikes.map((b) => <td key={b.name}>{fmtDate(b.first)} – {fmtDate(b.last)}</td>)}</tr>
                </tbody>
              </table>
            </div>
          </Panel>
          <Panel title="Kilometer pro Rad">
            <HBars rows={bikes.map((b) => ({ label: b.name, value: b.km, text: `${fmtKm(b.km)} km` }))} />
          </Panel>
        </>
      )}
      <Panel title="Als Nächstes fällig" sub={`Voraussichtliche Termine bei deinem Tempo der letzten 8 Wochen. Es ist eine Schätzung, kein Termin.`}>
        {f.items.length === 0 ? <p className="muted">Keine Wartungsregeln mit Intervall gefunden.</p> : (
          <ul className="forecast">
            {f.items.map((it, i) => (
              <li key={i} className={it.status === "due" ? "due" : it.status === "soon" ? "soon" : ""}>
                <span><strong>{it.label}</strong><br /><span className="muted small">{it.component}, {it.bike}</span></span>
                <span className="forecast-when">
                  {it.days <= 0 ? "jetzt fällig" : it.days < 14 ? `in ${it.days} Tagen` : `um den ${fmtDate(it.eta)}`}
                  <br /><span className="muted small">{it.basis === "Kilometer" ? `noch ${fmtKm(it.km_left)} km bei ${fmtKm(it.pace)} km/Woche` : "nach Zeitintervall"}, {fmtNum(it.progress, 0)} % verbraucht</span>
                </span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </>
  );
}

// ---------- Stammrunden ----------

export function RoutesView() {
  const [d, error] = useData("/stats/routes", []);
  if (error) return <p className="error" role="alert">{error}</p>;
  if (!d) return <Loading />;
  if (!d.routes.length) {
    return <EmptyState title="Noch keine Stammrunden" text={`Eine Runde zählt, wenn du sie mindestens dreimal gefahren bist (gleicher Start, ähnliche Länge, fast derselbe Verlauf). Geprüft wurden ${d.checked} Fahrten.`} />;
  }
  return (
    <>
      <p className="muted">BikeHelper erkennt Runden, die du immer wieder fährst, und zeigt, wie sich deine Zeiten dort entwickeln. Die Auswertung läuft nur auf deinen eigenen Fahrten.</p>
      {d.routes.map((r) => (
        <Panel key={r.last_id} title={r.name} sub={`${r.rides} Fahrten, ca. ${fmtKm(r.km)} km. Zuletzt am ${fmtDate(r.last_date)}.`}>
          <div className="kpis">
            <Kpi value={fmtNum(r.avg_speed, 1)} unit="km/h" label="Ø Tempo" />
            <Kpi value={fmtNum(r.best_speed, 1)} unit="km/h" label={`Bestes Tempo (${fmtDate(r.best_date)})`}
              extra={<Link className="small" to={`/rides/${r.best_ride_id}`}>Fahrt ansehen</Link>} />
            <Kpi value={fmtDuration(r.quickest_s)} label="Schnellste Zeit" extra={<Link className="small" to={`/rides/${r.quickest_id}`}>Fahrt ansehen</Link>} />
            {r.trend_pct != null && <Kpi value={sign(r.trend_pct)} unit="%" label="Tempo: letzte 3 gegen erste 3" />}
          </div>
          {r.years.length > 1 && (
            <Bars data={r.years.map((y) => ({ label: String(y.year), value: y.speed, sub: `${y.rides} Fahrten` }))} unit="km/h" format={(v) => fmtNum(v, 1)} height={150} />
          )}
        </Panel>
      ))}
    </>
  );
}

// ---------- Einfluss einer Fahrt (Fahrtseite) ----------

function Change({ label, v, goodWhenUp = true }) {
  const up = v.delta > 0, flat = v.delta === 0;
  const good = flat ? null : up === goodWhenUp;
  return (
    <div className="kpi impact-kpi">
      <div className="kpi-value">{fmtNum(v.after, 1)}<small className={flat ? "" : good ? "impact-good" : "impact-neutral"}>{flat ? "±0" : sign(v.delta, 1)}</small></div>
      <div className="kpi-label">{label}</div>
      <div className="muted small">vorher {fmtNum(v.before, 1)}</div>
    </div>
  );
}

export function RideImpact({ id }) {
  const [d, setD] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setD(null);
    setFailed(false);
    api.get(`/stats/ride-impact/${id}`).then(setD).catch(() => setFailed(true));
  }, [id]);
  if (failed) return null;
  if (!d) return <section className="panel" style={{ marginTop: "1.25rem" }}><h2>Einfluss auf Fitness und FTP</h2><Loading rows={2} /></section>;
  const { load, ftp } = d;
  const formWord = load.form.after > 10 ? "sehr frisch" : load.form.after > 0 ? "frisch" : load.form.after > -10 ? "leicht ermüdet" : load.form.after > -25 ? "ermüdet" : "stark ermüdet";
  return (
    <section className="panel" style={{ marginTop: "1.25rem" }}>
      <h2>Einfluss auf Fitness und FTP</h2>
      <p>
        {load.level ? <>Für dich eine <strong>{load.level}e</strong> Fahrt: </> : null}
        {fmtNum(load.points, 0)} Belastungspunkte{load.typical ? <> (deine typische Fahrt: {fmtNum(load.typical, 0)})</> : null}.
        Danach giltst du als <strong>{formWord}</strong> (Form {load.form.after > 0 ? "+" : ""}{fmtNum(load.form.after, 0)}).
      </p>
      <div className="kpis">
        <Change label="Fitness (42 Tage)" v={load.fitness} />
        <Change label="Ermüdung (7 Tage)" v={load.fatigue} goodWhenUp={false} />
        <Change label="Form" v={load.form} />
      </div>
      {ftp.available ? (
        <>
          <h3 className="chart-title">FTP</h3>
          <p>
            {ftp.after == null ? "Noch keine FTP-Schätzung möglich." : ftp.delta == null
              ? <>Erste FTP-Schätzung: <strong>{ftp.after} W</strong>.</>
              : ftp.delta === 0 ? <>Die FTP-Schätzung bleibt bei <strong>{ftp.after} W</strong>.</>
                : <>Die FTP-Schätzung {ftp.delta > 0 ? "steigt" : "sinkt"} von {ftp.before} auf <strong>{ftp.after} W</strong> ({sign(ftp.delta, 0)} W).</>}
            {ftp.delta < 0 && " Das heißt nur, dass ältere Bestwerte aus dem 90-Tage-Fenster fallen."}
          </p>
          {ftp.records.length > 0 && (
            <ul className="insights">
              {ftp.records.map((r) => (
                <li key={r.seconds}>🏅 Neue Bestleistung über {r.label}: <strong>{fmtNum(r.watts, 0)} W</strong>{r.before ? ` (vorher ${fmtNum(r.before, 0)} W)` : " (erste Fahrt mit diesem Wert)"}{r.approx ? ", aus dem Profil genähert" : ""}</li>
              ))}
            </ul>
          )}
          {ftp.intensity_pct != null && (
            <p className="muted small">Die Durchschnittsleistung entsprach etwa {ftp.intensity_pct} % deiner FTP ({ftp.zone}), das sind rund {fmtNum(ftp.tss, 0)} Trainingspunkte nach FTP.</p>
          )}
        </>
      ) : (
        <p className="muted small">Ohne Leistungsdaten lässt sich der Einfluss auf die FTP nicht berechnen.</p>
      )}
      <p className="muted small">
        Stand direkt nach dieser Fahrt, spätere Fahrten sind nicht eingerechnet. Die Belastung ist aus Fahrzeit, Höhenmetern und Tempo geschätzt, kein Messwert.
        Mehr dazu in der <Link className="link" to="/stats?tab=power">Statistik unter „Leistung“</Link>.
      </p>
    </section>
  );
}

// ---------- Leistungsanalyse einer Fahrt (Fahrtseite) ----------

function ZoneBars({ zones, colors }) {
  const max = Math.max(1, ...zones.map((z) => z.seconds));
  return (
    <ul className="hbars zone-bars">
      {zones.map((z, i) => (
        <li key={z.name}>
          <span className="hbar-label">{z.name}<br /><span className="muted small">{z.to == null ? `ab ${z.from}` : `${z.from}–${z.to}`}</span></span>
          <span className="hbar-track"><span className="hbar-fill" style={{ width: `${(z.seconds / max) * 100}%`, background: colors[i % colors.length] }} /></span>
          <span className="hbar-val">{fmtDuration(z.seconds)}<br /><span className="muted small">{fmtNum(z.pct, 0)} %</span></span>
        </li>
      ))}
    </ul>
  );
}

const ZONE_COLORS = ["#7fb6ff", "#6fd3c3", "#8fd16a", "#f2b84b", "#ff9a52", "#ff6b6b", "#b48cf2"];
const HR_COLORS = ["#7fb6ff", "#6fd3c3", "#f2b84b", "#ff9a52", "#ff6b6b"];

export function RideAnalysis({ id }) {
  const [d, setD] = useState(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    setD(null);
    setFailed(false);
    api.get(`/stats/ride-analysis/${id}`).then(setD).catch(() => setFailed(true));
  }, [id]);
  if (failed || !d) return null;
  const { power: p, hr, cadence: cad } = d;
  if (!p && !hr && !cad) return null;
  return (
    <section className="panel" style={{ marginTop: "1.25rem" }}>
      <h2>Leistungsanalyse</h2>
      {!d.exact && (
        <p className="muted small">
          Diese Fahrt wurde importiert, bevor BikeHelper Sekundenwerte auswertete. Zonen und Spitzen sind aus dem Streckenprofil genähert und liegen eher zu niedrig.
          Lade dieselbe Datei oder denselben Strava-Export noch einmal hoch, dann werden sie exakt (die Fahrt wird dabei ergänzt, nicht doppelt angelegt).
        </p>
      )}
      {p && (
        <>
          <h3 className="chart-title">Leistung</h3>
          <div className="kpis">
            <Kpi value={fmtNum(p.avg, 0)} unit="W" label="Durchschnitt" />
            {p.np && <Kpi value={fmtNum(p.np, 0)} unit="W" label="Normalisiert (NP)" />}
            {p.max && <Kpi value={fmtNum(p.max, 0)} unit="W" label="Spitze" />}
            {p.wkg && <Kpi value={fmtNum(p.wkg, 2)} unit="W/kg" label="Ø pro Kilo" />}
            {p.kj && <Kpi value={fmtNum(p.kj, 0)} unit="kJ" label="Arbeit" />}
            {p.vi && <Kpi value={fmtNum(p.vi, 2)} label="Variabilität (NP ÷ Ø)" />}
            {p.if && <Kpi value={fmtNum(p.if, 2)} label="Intensität (IF)" />}
            {p.tss && <Kpi value={fmtNum(p.tss, 0)} label="Trainingspunkte (TSS)" />}
          </div>
          <Insights items={[
            p.vi && (p.vi < 1.05 ? "Sehr gleichmäßig gefahren (Variabilität unter 1,05)." : p.vi > 1.2 ? "Sehr unruhig gefahren, viele Antritte oder Wechsel (Variabilität über 1,2)." : null),
            p.if && (p.if >= 1 ? "Intensität über 1,0: Das war an oder über deiner FTP." : p.if < 0.6 ? "Intensität unter 0,6: lockere Ausfahrt oder Erholung." : null),
            !p.np && "Die normalisierte Leistung (NP) braucht den Sekundenverlauf und fehlt bei dieser Fahrt.",
          ]} />
          {p.zones ? (
            <>
              <h3 className="chart-title">Zeit in den Wattzonen <span className="muted small">(FTP {p.ftp} W)</span></h3>
              <ZoneBars zones={p.zones} colors={ZONE_COLORS} />
              <p className="muted small">{p.ftp_note}. Zonen nach Coggan.</p>
            </>
          ) : <p className="muted small">Für Wattzonen fehlt noch eine FTP-Schätzung. Sie entsteht aus Fahrten mit mindestens 20 Minuten Leistungsdaten.</p>}
          {p.peaks.length > 0 && (
            <>
              <h3 className="chart-title">Spitzenwerte dieser Fahrt</h3>
              <div className="scroll-x">
                <table className="plain-table">
                  <thead><tr><th>Dauer</th><th>Watt</th><th>W/kg</th><th>Dein Bestwert</th><th /></tr></thead>
                  <tbody>
                    {p.peaks.map((x) => (
                      <tr key={x.label}>
                        <td>{x.label}</td><td>{fmtNum(x.watts, 0)} W</td><td>{x.wkg ? fmtNum(x.wkg, 2) : "–"}</td>
                        <td>{fmtNum(x.best, 0)} W</td>
                        <td>{x.is_best ? "🏅 Bestwert" : `${fmtNum(x.pct_of_best, 0)} %`}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
      {hr && (
        <>
          <h3 className="chart-title">Puls</h3>
          <div className="kpis">
            <Kpi value={fmtNum(hr.avg, 0)} unit="bpm" label={hr.avg_pct ? `Durchschnitt (${hr.avg_pct} % vom Maximum)` : "Durchschnitt"} />
            {hr.max && <Kpi value={fmtNum(hr.max, 0)} unit="bpm" label="Höchster Puls" />}
            {hr.ef && <Kpi value={fmtNum(hr.ef, 2)} label="Effizienz (Watt je Herzschlag)" />}
            {hr.decoupling != null && <Kpi value={`${hr.decoupling > 0 ? "+" : ""}${fmtNum(hr.decoupling, 1)}`} unit="%" label="Entkopplung (Leistung zu Puls)" />}
          </div>
          {hr.decoupling != null && (
            <Insights items={[hr.decoupling > 5
              ? "Der Puls ist im Verhältnis zur Leistung in der zweiten Hälfte deutlich gestiegen (über 5 %). Das spricht für Ermüdung oder Hitze, bei langen Fahrten ist etwas Anstieg normal."
              : hr.decoupling < 3 ? "Kaum Entkopplung (unter 3 %): Grundlage hält die Fahrt locker durch." : null]} />
          )}
          {hr.zones ? (
            <>
              <h3 className="chart-title">Zeit in den Pulszonen <span className="muted small">(Maximalpuls {hr.max_used})</span></h3>
              <ZoneBars zones={hr.zones} colors={HR_COLORS} />
              <p className="muted small">Maximalpuls: {hr.max_note}. Zonen in Prozent davon. <Link className="link" to="/settings">Maximalpuls einstellen</Link></p>
            </>
          ) : <p className="muted small">Für Pulszonen fehlt der Maximalpuls. <Link className="link" to="/settings">In den Einstellungen eintragen</Link>.</p>}
        </>
      )}
      {cad && (
        <>
          <h3 className="chart-title">Trittfrequenz <span className="muted small">(Ø {fmtNum(cad.avg, 0)} U/min)</span></h3>
          <HBars color="#7fb6ff" rows={cad.buckets.map((b) => ({ label: b.label, value: b.seconds, text: `${fmtDuration(b.seconds)} · ${fmtNum(b.pct, 0)} %` }))} />
        </>
      )}
    </section>
  );
}
