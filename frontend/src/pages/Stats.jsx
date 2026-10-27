import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Heatmap from "./Heatmap.jsx";
import { api, fmtDate, fmtDuration, fmtKm, fmtNum } from "../api.js";
import { Bars, CalendarHeat, CumulativeLines, HBars } from "../components/charts.jsx";
import { EmptyState } from "../components/ui.jsx";
import { Kpi, Panel } from "../components/statsui.jsx";
import { CompareView, GoalsView, LoadView, PlacesView, ReviewView } from "../components/StatsExtra.jsx";
import { Loading } from "../components/feedback.jsx";

const TABS = [["overview", "Übersicht"], ["load", "Belastung"], ["review", "Jahresrückblick"], ["goals", "Ziele"], ["compare", "Vergleiche"], ["places", "Orte"], ["heatmap", "Heatmap"]];
const MONTH_NAMES = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"];

export default function Stats() {
  const [filters, setFilters] = useState({ year: "", bike_id: "" });
  const [options, setOptions] = useState({ years: [], bikes: [] });
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [calYear, setCalYear] = useState(null);
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([k]) => k === params.get("tab")) ? params.get("tab") : "overview";
  const setTab = (k) => setParams(k === "overview" ? {} : { tab: k }, { replace: true });

  useEffect(() => {
    const qs = new URLSearchParams();
    if (filters.year) qs.set("year", filters.year);
    if (filters.bike_id) qs.set("bike_id", filters.bike_id);
    api.get(`/stats/overview?${qs}`)
      .then((o) => {
        setD(o);
        if (!filters.year && !filters.bike_id) setOptions({ years: o.years_available ?? [], bikes: o.bikes_available ?? [] });
        if (!o.empty) {
          const ys = o.years.map((y) => y.year);
          setCalYear((c) => (c && ys.includes(c) ? c : ys[ys.length - 1]));
        }
      })
      .catch((e) => setError(e.message));
  }, [filters]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!d) return <Loading />;

  const set = (k) => (e) => setFilters({ ...filters, [k]: e.target.value });
  const header = (
    <header className="page-head">
      <h1>Statistik</h1>
      <div className="filter-bar">
        {tab === "overview" && (
          <select value={filters.year} onChange={set("year")} aria-label="Jahr">
            <option value="">Alle Jahre</option>
            {options.years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
        )}
        <select value={filters.bike_id} onChange={set("bike_id")} aria-label="Rad">
          <option value="">Alle Räder</option>
          {options.bikes.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
        </select>
      </div>
    </header>
  );
  const tabs = (
    <nav className="stat-tabs" aria-label="Statistikbereiche">
      {TABS.map(([k, l]) => (
        <button key={k} className={tab === k ? "on" : ""} aria-pressed={tab === k} onClick={() => setTab(k)}>{l}</button>
      ))}
    </nav>
  );
  const years = options.years.length ? options.years : (d.years ? d.years.map((y) => y.year) : []);
  if (tab === "load") return <>{header}{tabs}<LoadView bikeId={filters.bike_id} /></>;
  if (tab === "review") return <>{header}{tabs}<ReviewView bikeId={filters.bike_id} years={years} /></>;
  if (tab === "goals") return <>{header}{tabs}<GoalsView /></>;
  if (tab === "places") return <>{header}{tabs}<PlacesView /></>;
  if (tab === "heatmap") return <>{header}{tabs}<Heatmap embedded /></>;
  if (tab === "compare") return <>{header}{tabs}<CompareView bikeId={filters.bike_id} /></>;

  if (d.empty) {
    return (
      <>
        {header}
        {tabs}
        <EmptyState title="Keine Fahrten gefunden" text="Importiere Fahrten oder ändere den Filter.">
          <Link className="btn primary" to="/rides">Fahrten importieren</Link>
        </EmptyState>
      </>
    );
  }

  const t = d.totals, r = d.records, w = d.weather, tl = d.tiles;
  const rideLink = (rec) => rec && `${rec.name} · ${fmtDate(rec.date)}`;
  const singleYear = !!filters.year;

  return (
    <>
      {header}
      {tabs}

      <div className="kpis">
        <Kpi value={fmtKm(t.km)} unit="km" label="Gesamtstrecke" />
        <Kpi value={fmtKm(t.rides)} label="Fahrten" />
        <Kpi value={fmtKm(t.elev_m)} unit="m" label="Höhenmeter" />
        <Kpi value={fmtDuration(t.time_s)} label="Fahrzeit" />
        <Kpi value={fmtNum(t.avg_speed)} unit="km/h" label="Ø Geschwindigkeit" />
        <Kpi value={fmtNum(t.avg_km)} unit="km" label="Ø pro Fahrt" />
      </div>

      <div className="grid-2">
        <Panel title={singleYear ? "Kilometer pro Monat" : "Kilometer pro Jahr"}>
          {singleYear ? (
            <Bars
              data={Array.from({ length: 12 }, (_, i) => {
                const m = d.months.find((x) => x.month === `${filters.year}-${String(i + 1).padStart(2, "0")}`);
                return { label: MONTH_NAMES[i], value: m?.km ?? 0, sub: m ? `${m.rides} Fahrten` : "" };
              })}
              unit="km"
            />
          ) : (
            <Bars data={d.years.map((y) => ({ label: String(y.year), value: y.km, sub: `${y.rides} Fahrten, ${fmtKm(y.elev_m)} m` }))} unit="km" />
          )}
        </Panel>
        <Panel title="Verlauf im Jahr" sub="Kumulierte Kilometer, ein Jahr pro Linie">
          <CumulativeLines cumulative={d.cumulative} />
        </Panel>
      </div>

      <Panel title="Fahrtage" className="scroll-x">
        <div className="actions" style={{ marginTop: 0, marginBottom: "0.75rem" }}>
          {d.years.map((y) => (
            <button key={y.year} className={`chip ${calYear === y.year ? "on" : ""}`} onClick={() => setCalYear(y.year)}>{y.year}</button>
          ))}
          <span className="muted small">{fmtKm(t.active_days)} Tage mit Fahrt</span>
        </div>
        {calYear && <CalendarHeat year={calYear} daily={d.daily} />}
      </Panel>

      <div className="grid-2">
        <Panel title="Erkundete Kacheln" sub="Wie bei Statshunters: Jede 1,5 × 1,5 km große Kachel, durch die du gefahren bist.">
          <div className="tile-hero">
            <Kpi value={fmtKm(tl.count)} label="Kacheln erkundet" />
            <Kpi value={`${tl.max_square} × ${tl.max_square}`} label="Größtes Quadrat" />
            <Kpi value={fmtKm(tl.max_cluster)} label="Größtes Gebiet" />
          </div>
          {!singleYear && Object.keys(tl.by_year_new).length > 1 && (
            <>
              <h3 style={{ margin: "1.25rem 0 0.5rem" }}>Neue Kacheln pro Jahr</h3>
              <Bars data={Object.entries(tl.by_year_new).map(([y, n]) => ({ label: y, value: n }))} />
            </>
          )}
          <p style={{ marginTop: "1rem" }}><Link to="/stats?tab=heatmap" className="link">Auf der Karte ansehen →</Link></p>
        </Panel>
        <Panel title="Rekorde">
          <ul className="record-list">
            <li><span>Längste Fahrt<br /><span className="muted small">{rideLink(r.longest_ride)}</span></span><strong>{fmtNum(r.longest_ride.value)} km</strong></li>
            <li><span>Meiste Höhenmeter<br /><span className="muted small">{rideLink(r.most_climbing)}</span></span><strong>{fmtKm(r.most_climbing.value)} m</strong></li>
            <li><span>Längste Fahrzeit<br /><span className="muted small">{rideLink(r.longest_time)}</span></span><strong>{fmtDuration(r.longest_time.value)}</strong></li>
            <li><span>Bester Tag<br /><span className="muted small">{fmtDate(r.best_day_km.date)}</span></span><strong>{fmtNum(r.best_day_km.value)} km</strong></li>
            {r.fastest_avg && <li><span>Schnellster Schnitt (ab 10 km)<br /><span className="muted small">{rideLink(r.fastest_avg)}</span></span><strong>{fmtNum(r.fastest_avg.value)} km/h</strong></li>}
            <li><span>Längste Serie<br /><span className="muted small">Tage in Folge mit Fahrt</span></span><strong>{d.streaks.longest_days} Tage</strong></li>
            <li><span>Aktuelle Serie</span><strong>{d.streaks.current_days} Tage</strong></li>
          </ul>
        </Panel>
      </div>

      <div className="grid-2" style={{ marginTop: "1.25rem" }}>
        <Panel title="Wochentage">
          <Bars data={d.weekdays.map((x) => ({ label: x.label, value: x.km, sub: `${x.rides} Fahrten` }))} unit="km" />
        </Panel>
        <Panel title="Startzeit">
          <Bars
            data={d.hours.map((n, h) => ({ label: String(h), value: n }))}
            unit="Fahrten" labelEvery={3}
          />
        </Panel>
        <Panel title="Fahrtlängen">
          <HBars rows={d.distance_buckets.map((b) => ({ label: b.label, value: b.rides, text: `${b.rides} Fahrten` }))} />
        </Panel>
        <Panel title="Deine Räder">
          <HBars
            rows={d.bikes.map((b) => ({ label: b.name, value: b.km, text: `${fmtKm(b.km)} km` }))}
            color="var(--amber)"
          />
        </Panel>
      </div>

      <h2 className="section-title">Wetter</h2>
      {w.rides_with_weather === 0 ? (
        <Panel title="Noch keine Wetterdaten" sub="Die Wetterdaten werden nach dem Import automatisch von Open-Meteo geholt. Du kannst den Abruf unter Fahrten auch von Hand starten." />
      ) : (
        <>
          <div className="kpis">
            <Kpi value={fmtNum(w.avg_temp)} unit="°C" label="Ø Temperatur" />
            <Kpi value={fmtKm(w.wet_km)} unit="km" label={`bei Nässe (${fmtNum(w.wet_share, 0)} %)`} />
            <Kpi value={fmtKm(w.rainy_rides)} label="Fahrten mit Regen" />
            <Kpi value={fmtKm(w.total_precip_mm)} unit="mm" label="Regen während der Fahrten" />
          </div>
          <div className="grid-2">
            <Panel title="Kilometer nach Temperatur">
              <Bars data={w.by_temp.map((b) => ({ label: b.label, value: b.km, sub: `${b.rides} Fahrten` }))} unit="km" />
            </Panel>
            <Panel title="Extreme">
              <ul className="record-list">
                {w.coldest && <li><span>Kälteste Fahrt<br /><span className="muted small">{rideLink(w.coldest)}</span></span><strong>{fmtNum(w.coldest.value)} °C</strong></li>}
                {w.hottest && <li><span>Wärmste Fahrt<br /><span className="muted small">{rideLink(w.hottest)}</span></span><strong>{fmtNum(w.hottest.value)} °C</strong></li>}
              </ul>
              <p className="muted small" style={{ marginTop: "1rem" }}>
                Wetterdaten für {fmtNum(w.coverage, 0)} % der Fahrten. Nässe-Kilometer fließen in die Wartungsintervalle ein.
              </p>
            </Panel>
          </div>
        </>
      )}
    </>
  );
}
