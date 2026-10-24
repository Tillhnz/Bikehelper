import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { BIKE_TYPES, api, fmtDate, fmtDuration, fmtKm, fmtNum } from "../api.js";
import BikeIllustration from "../components/BikeIllustration.jsx";
import { Kpi, Panel } from "../components/statsui.jsx";
import { EmptyState, StatusPill } from "../components/ui.jsx";
import { GOAL_META } from "../components/StatsExtra.jsx";

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Gute Nacht" : h < 11 ? "Guten Morgen" : h < 18 ? "Guten Tag" : "Guten Abend";
}

/** Sieben Balken Montag bis Sonntag; heute ist hervorgehoben, kommende Tage sind blass. */
function WeekBars({ days }) {
  const max = Math.max(20, ...days.map((d) => d.km));
  return (
    <div className="week-bars" role="img" aria-label={`Kilometer pro Tag: ${days.map((d) => `${d.label} ${fmtNum(d.km, 0)}`).join(", ")}`}>
      {days.map((d, i) => (
        <div key={d.date} className={`week-day ${d.today ? "today" : ""} ${d.future ? "future" : ""}`}>
          <span className="week-km">{d.km > 0 ? fmtNum(d.km, 0) : ""}</span>
          <div className="week-track">
            <span className="week-fill" style={{ height: `${(d.km / max) * 100}%`, "--i": i }} />
          </div>
          <span className="week-label">{d.label}</span>
        </div>
      ))}
    </div>
  );
}

function compare(now, before) {
  const diff = now - before;
  if (!before && !now) return null;
  return (
    <span className={`delta ${diff >= 0 ? "up" : "down"}`}>
      {diff >= 0 ? "▲" : "▼"} {fmtKm(Math.abs(diff))} km zur gleichen Zeit der Vorwoche
    </span>
  );
}

export default function Home() {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => { api.get("/home").then(setD).catch((e) => setError(e.message)); }, []);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!d) return <p className="muted">Lade …</p>;

  const { week, year, maintenance: m, bikes, recent } = d;
  const t = week.totals;

  return (
    <>
      <header className="page-head">
        <h1>{greeting()}</h1>
        <p className="muted">{new Date(d.today + "T00:00:00").toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" })}</p>
      </header>

      {!d.has_rides && bikes.length === 0 ? (
        <EmptyState title="Willkommen bei BikeHelper" text="Lege zuerst dein Rad an und importiere dann deine Fahrten.">
          <div className="actions">
            <Link className="btn primary" to="/garage">Rad anlegen</Link>
            <Link className="btn" to="/rides">Fahrten importieren</Link>
          </div>
        </EmptyState>
      ) : (
        <>
          <div className="home-grid">
            <Panel title="Diese Woche" className="home-week">
              <div className="week-head">
                <div className="week-total"><strong>{fmtKm(t.km)}</strong> <span className="muted">km</span></div>
                {compare(t.km, week.last_week_same_point_km)}
              </div>
              <WeekBars days={week.days} />
              <div className="week-facts">
                <span>{t.rides} {t.rides === 1 ? "Fahrt" : "Fahrten"}</span>
                <span>{fmtDuration(t.time_s)}</span>
                <span>{fmtKm(t.elev_m)} m hoch</span>
                <span>Vorwoche gesamt {fmtKm(week.last_week_km)} km</span>
              </div>
            </Panel>

            <Panel title="Wartung" className="home-maint">
              {m.items.length === 0 ? (
                <p className="ok">Alles in Ordnung. Nichts ist bald fällig.</p>
              ) : (
                <ul className="maint-list">
                  {m.items.map((i) => (
                    <li key={`${i.component_id}-${i.rule}`}>
                      <div>
                        <Link to={`/bikes/${i.bike_id}`}>{i.rule}</Link>
                        <span className="muted small">{i.bike ? `${i.bike}: ` : ""}{i.component}</span>
                      </div>
                      <StatusPill status={i.status} />
                    </li>
                  ))}
                </ul>
              )}
              {m.total > m.items.length && <p className="muted small">und {m.total - m.items.length} weitere</p>}
              <p style={{ marginTop: "0.75rem" }}><Link to="/garage" className="link">Zur Garage →</Link></p>
            </Panel>
          </div>

          {bikes.length > 0 && (
            <section className="home-bikes" aria-label="Deine Räder">
              {bikes.map((b) => (
                <Link key={b.id} to={`/bikes/${b.id}`} className="home-bike">
                  <div className="home-bike-art"><BikeIllustration type={b.type} title={BIKE_TYPES[b.type] ?? "Rad"} /></div>
                  <div className="home-bike-info">
                    <strong>{b.name}</strong>
                    <span className="muted small">{fmtKm(b.total_km)} km gesamt · {fmtKm(b.week_km)} km diese Woche</span>
                    {b.tire_set && <span className="muted small">Mantel: {b.tire_set}</span>}
                    {b.due_count > 0 ? <span className="pill pill-due">{b.due_count} fällig</span> : <span className="pill pill-ok">in Ordnung</span>}
                  </div>
                </Link>
              ))}
            </section>
          )}

          <div className="home-grid">
            <Panel title={`Dein Ziel ${year.year}`} sub={year.goals?.length ? `Noch ${year.days_left} Tage bis Jahresende` : undefined}>
              {year.goals?.length ? (
                <ul className="goal-list">
                  {year.goals.map((g) => {
                    const m = GOAL_META[g.metric];
                    const perWeek = g.per_week_needed;
                    return (
                      <li key={g.metric}>
                        <div className="goal-num"><strong>{fmtKm(g.done)}</strong> <span className="muted">von {fmtKm(g.target)} {m.unit} · {m.label}</span></div>
                        <div className="goal-bar" role="progressbar" aria-valuenow={Math.round(g.percent)} aria-valuemin={0} aria-valuemax={100}>
                          <span style={{ width: `${Math.min(100, g.percent)}%` }} />
                          <i style={{ left: `${Math.min(100, (g.plan / g.target) * 100)}%` }} title="Plan bei gleichmäßigem Tempo" />
                        </div>
                        <p className="small">
                          {g.reached_on ? `Geschafft am ${fmtDate(g.reached_on)}.` : (
                            <>
                              Noch {fmtKm(g.remaining)} {m.unit}
                              {perWeek != null && <>, das sind <strong>{fmtKm(perWeek)} {m.unit} pro Woche</strong> ({fmtKm(perWeek / 7)} pro Tag)</>}.
                              {" "}{g.on_track ? "Im aktuellen Tempo schaffst du es." : `Im aktuellen Tempo erreichst du ${fmtKm(g.projected)} ${m.unit}.`}
                            </>
                          )}
                        </p>
                      </li>
                    );
                  })}
                  <li><Link to="/stats" className="link small">Ziele ändern</Link></li>
                </ul>
              ) : (
                <>
                  <div className="goal-num"><strong>{fmtKm(year.km)}</strong> <span className="muted">km in diesem Jahr</span></div>
                  <p className="small muted">Setze dir in der <Link to="/stats" className="link">Statistik</Link> ein Jahresziel. Hier siehst du dann, was du pro Woche fahren musst, um es zu erreichen.</p>
                </>
              )}
            </Panel>
            <Panel title="Letzte Fahrten">
              {recent.length === 0 ? <p className="muted">Noch keine Fahrten importiert.</p> : (
                <ol className="top-list">
                  {recent.map((r) => (
                    <li key={r.id}>
                      <Link to={`/rides/${r.id}`}>{r.name}</Link>
                      <span className="muted small">{fmtDate(r.date.slice(0, 10))} · {fmtDuration(r.time_s)} · {fmtKm(r.elev_m)} m</span>
                      <strong>{fmtNum(r.km)} km</strong>
                    </li>
                  ))}
                </ol>
              )}
            </Panel>
          </div>
        </>
      )}
    </>
  );
}
