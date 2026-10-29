import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { BIKE_TYPES, api, fmtDate, fmtDuration, fmtKm, fmtNum } from "../api.js";
import BikeIllustration from "../components/BikeIllustration.jsx";
import { Kpi, Panel } from "../components/statsui.jsx";
import { EmptyState, StatusPill } from "../components/ui.jsx";
import { GOAL_META } from "../components/StatsExtra.jsx";
import QuickDone from "../components/QuickDone.jsx";
import WetNotice from "../components/WetNotice.jsx";
import MechanicRequests from "../components/MechanicRequests.jsx";
import { Loading } from "../components/feedback.jsx";

function greeting() {
  const h = new Date().getHours();
  return h < 5 ? "Gute Nacht" : h < 11 ? "Guten Morgen" : h < 18 ? "Guten Tag" : "Guten Abend";
}

/** Sieben Balken Montag bis Sonntag; heute ist hervorgehoben, kommende Tage sind blass. */
function WeekBars({ days }) {
  const max = Math.max(20, ...days.map((d) => d.km));
  return (
    <div className="week-bars" aria-label={`Kilometer pro Tag: ${days.map((d) => `${d.label} ${fmtNum(d.km, 0)}`).join(", ")}`}>
      {days.map((d, i) => {
        const inner = (
          <>
            <span className="week-km">{d.km > 0 ? fmtNum(d.km, 0) : ""}</span>
            <div className="week-track">
              <span className="week-fill" style={{ height: `${(d.km / max) * 100}%`, "--i": i }} />
            </div>
            <span className="week-label">{d.label}</span>
          </>
        );
        const cls = `week-day ${d.today ? "today" : ""} ${d.future ? "future" : ""}`;
        // Ein Tipp auf einen Tag mit Fahrten öffnet genau diese Fahrten
        return d.rides > 0
          ? <Link key={d.date} to={`/rides?day=${d.date}`} className={`${cls} has-rides`} aria-label={`${d.label}: ${fmtNum(d.km, 0)} km, Fahrten ansehen`}>{inner}</Link>
          : <div key={d.date} className={cls}>{inner}</div>;
      })}
    </div>
  );
}

function compare(now, before, current = true) {
  const diff = now - before;
  if (!before && !now) return null;
  return (
    <span className={`delta ${diff >= 0 ? "up" : "down"}`}>
      {diff >= 0 ? "▲" : "▼"} {fmtKm(Math.abs(diff))} km {current ? "zur gleichen Zeit der Vorwoche" : "zur Woche davor"}
    </span>
  );
}

const MONTHS = ["Jan.", "Feb.", "März", "Apr.", "Mai", "Juni", "Juli", "Aug.", "Sep.", "Okt.", "Nov.", "Dez."];

/** Titel der Woche: "Diese Woche", "Letzte Woche" oder Kalenderwoche mit Datum. */
function weekTitle(w) {
  if (w.offset === 0) return "Diese Woche";
  if (w.offset === -1) return "Letzte Woche";
  const mon = new Date(`${w.monday}T00:00:00`);
  const sun = new Date(mon.getTime() + 6 * 864e5);
  const th = new Date(mon.getTime() + 3 * 864e5); // Donnerstag bestimmt die ISO-Woche
  const kw = Math.ceil(((th - new Date(th.getFullYear(), 0, 1)) / 864e5 + 1) / 7);
  const range = mon.getMonth() === sun.getMonth()
    ? `${mon.getDate()}.–${sun.getDate()}. ${MONTHS[sun.getMonth()]}`
    : `${mon.getDate()}. ${MONTHS[mon.getMonth()]} – ${sun.getDate()}. ${MONTHS[sun.getMonth()]}`;
  return `KW ${kw}, ${range}${mon.getFullYear() !== new Date().getFullYear() ? ` ${mon.getFullYear()}` : ""}`;
}

const DATA_BLOCKS = ["eddington", "streaks", "records", "form"];

/** Auswahl und Reihenfolge der Blöcke auf der Startseite. */
function HomeEditor({ lay, onSave, onClose }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const byId = Object.fromEntries(lay.catalog.map((c) => [c.id, c]));
  const on = lay.layout;
  const off = lay.catalog.filter((c) => !on.includes(c.id));

  async function save(body) {
    setBusy(true); setError("");
    try { await onSave(body); } catch (e) { setError(e.message); } finally { setBusy(false); }
  }
  const move = (i, dir) => {
    const next = [...on];
    const j = i + dir;
    if (j < 0 || j >= next.length) return;
    [next[i], next[j]] = [next[j], next[i]];
    save({ layout: next });
  };
  // Im einfachen Modus ausgeblendete Expertenblöcke bleiben in der gespeicherten Anordnung erhalten (sie liegen nicht in `on`)
  return (
    <section className="panel home-editor" aria-label="Startseite anpassen">
      <h2>Startseite anpassen</h2>
      <p className="muted small">Wähle, welche Blöcke du auf der Startseite sehen willst, und bring sie in die passende Reihenfolge. Das gilt nur für dein Konto.</p>
      {error && <p className="error" role="alert">{error}</p>}
      <h3>Auf deiner Startseite</h3>
      {on.length === 0 ? <p className="muted">Keine Blöcke. Füge unten welche hinzu.</p> : (
        <ol className="plain home-editor-list">
          {on.map((id, i) => (
            <li key={id}>
              <span><strong>{byId[id]?.title ?? id}</strong><br /><span className="muted small">{byId[id]?.text}</span></span>
              <span className="row-actions">
                <button className="btn small" onClick={() => move(i, -1)} disabled={busy || i === 0} aria-label={`${byId[id]?.title} nach oben`}>▲</button>
                <button className="btn small" onClick={() => move(i, 1)} disabled={busy || i === on.length - 1} aria-label={`${byId[id]?.title} nach unten`}>▼</button>
                <button className="link small danger" onClick={() => save({ layout: on.filter((x) => x !== id) })} disabled={busy}>Entfernen</button>
              </span>
            </li>
          ))}
        </ol>
      )}
      {off.length > 0 && (
        <>
          <h3>Weitere Blöcke</h3>
          <ul className="plain home-editor-list">
            {off.map((c) => (
              <li key={c.id}>
                <span><strong>{c.title}</strong><br /><span className="muted small">{c.text}{!c.available ? " (nur im Expertenmodus, einstellbar unter Einstellungen)" : ""}</span></span>
                <button className="btn small" onClick={() => save({ layout: [...on, c.id] })} disabled={busy || !c.available}>Hinzufügen</button>
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="actions">
        <button className="btn primary" onClick={onClose}>Fertig</button>
        {lay.custom && <button className="btn" onClick={() => save({ reset: true })} disabled={busy}>Standard wiederherstellen</button>}
      </div>
    </section>
  );
}

function AnalysisPanel({ id, data }) {
  const titles = { eddington: "Eddington-Zahl", streaks: "Serie", records: "Rekorde", form: "Form und Fitness" };
  if (!data) return <Panel title={titles[id]}><Loading rows={2} /></Panel>;
  if (id === "eddington") {
    return (
      <Panel title="Eddington-Zahl">
        <div className="goal-num"><strong>{data.value}</strong></div>
        <p className="small muted">An {data.value} Tagen bist du mindestens {data.value} km gefahren. Für {data.next} fehlen {data.missing_days} {data.missing_days === 1 ? "Tag" : "Tage"} mit mindestens {data.next} km.</p>
        <p><Link to="/stats" className="link small">Zur Statistik →</Link></p>
      </Panel>
    );
  }
  if (id === "streaks") {
    return (
      <Panel title="Serie">
        <div className="goal-num"><strong>{data.current}</strong> <span className="muted">{data.current === 1 ? "Tag" : "Tage"} in Folge</span></div>
        <p className="small muted">Deine längste Serie war {data.longest} {data.longest === 1 ? "Tag" : "Tage"}.</p>
      </Panel>
    );
  }
  if (id === "records") {
    return (
      <Panel title="Rekorde">
        <ul className="record-list">
          {data.longest && <li><span>Längste Fahrt<br /><Link className="small" to={`/rides/${data.longest.id}`}>ansehen</Link></span><strong>{fmtNum(data.longest.km)} km</strong></li>}
          {data.best_day && <li><span>Bester Tag<br /><span className="muted small">{fmtDate(data.best_day.date)}</span></span><strong>{fmtNum(data.best_day.km)} km</strong></li>}
          {data.climb && <li><span>Meiste Höhenmeter<br /><Link className="small" to={`/rides/${data.climb.id}`}>ansehen</Link></span><strong>{fmtKm(data.climb.m)} m</strong></li>}
        </ul>
        {!data.longest && <p className="muted">Noch keine Fahrten.</p>}
      </Panel>
    );
  }
  return (
    <Panel title="Form und Fitness" sub="Geschätzt aus Fahrzeit, Höhenmetern und Tempo, ohne Puls oder Leistung.">
      {data.form == null ? <p className="muted">Noch keine Fahrten.</p> : (
        <>
          <div className="goal-num"><strong>{fmtNum(data.form, 0)}</strong> <span className="muted">Form, {data.state}</span></div>
          <p className="small muted">Fitness {fmtNum(data.fitness, 0)}, Ermüdung {fmtNum(data.fatigue, 0)}. Positiv heißt ausgeruht, stark negativ heißt müde.</p>
        </>
      )}
      <p><Link to="/stats?tab=load" className="link small">Zur Belastung →</Link></p>
    </Panel>
  );
}

export default function Home() {
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  const [offset, setOffset] = useState(0);
  const [past, setPast] = useState(null); // Daten einer früheren Woche
  const [weekError, setWeekError] = useState("");
  const [lay, setLay] = useState(null);
  const [extra, setExtra] = useState({});
  const [params] = useSearchParams();
  const [editing, setEditing] = useState(params.get("customize") === "1");

  const reload = () => api.get("/home").then(setD).catch((e) => setError(e.message));
  useEffect(() => { reload(); }, []);
  useEffect(() => {
    api.get("/home/layout").then(setLay).catch(() => setLay({ mode: "expert", layout: ["week", "maintenance", "bikes", "goal", "recent"], custom: false, catalog: [] }));
  }, []);
  const dataKey = lay ? lay.layout.filter((i) => DATA_BLOCKS.includes(i)).join(",") : "";
  useEffect(() => {
    if (!dataKey) { setExtra({}); return undefined; }
    let live = true;
    api.get(`/home/blocks?ids=${dataKey}`).then((r) => { if (live) setExtra(r); }).catch(() => { if (live) setExtra({}); });
    return () => { live = false; };
  }, [dataKey]);

  useEffect(() => {
    if (offset === 0) { setPast(null); return undefined; }
    let live = true;
    setWeekError("");
    api.get(`/home/week?offset=${offset}`).then((r) => { if (live) setPast(r); }).catch((e) => { if (live) setWeekError(e.message); });
    return () => { live = false; };
  }, [offset]);

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!d || !lay) return <Loading />;

  const { week, year, maintenance: m, bikes, recent } = d;
  const shown = offset === 0 || !past ? week : past;
  const t = shown.totals;
  const isCurrent = offset === 0;

  const blocks = {
    week: (
            <Panel title={weekTitle(shown)} className="home-week">
              <div className="week-nav">
                <button className="btn small" onClick={() => setOffset(offset - 1)} disabled={!shown.has_earlier || (offset !== 0 && !past)} aria-label="Eine Woche zurück">‹ Zurück</button>
                {!isCurrent && <button className="link small" onClick={() => setOffset(0)}>Zu dieser Woche</button>}
                <button className="btn small" onClick={() => setOffset(offset + 1)} disabled={isCurrent} aria-label="Eine Woche vor">Weiter ›</button>
              </div>
              {weekError && <p className="error" role="alert">{weekError}</p>}
              <div className="week-head">
                <div className="week-total"><strong>{fmtKm(t.km)}</strong> <span className="muted">km</span></div>
                {compare(t.km, shown.last_week_same_point_km, isCurrent)}
              </div>
              <WeekBars key={shown.monday ?? "now"} days={shown.days} />
              <div className="week-facts">
                <span>{t.rides} {t.rides === 1 ? "Fahrt" : "Fahrten"}</span>
                <span>{fmtDuration(t.time_s)}</span>
                <span>{fmtKm(t.elev_m)} m hoch</span>
                <span>{isCurrent ? "Vorwoche" : "Woche davor"} gesamt {fmtKm(shown.last_week_km)} km</span>
              </div>
            </Panel>
    ),
    maintenance: (
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
                      <span className="maint-actions">
                        <StatusPill status={i.status} />
                        <QuickDone item={i} onDone={reload} />
                      </span>
                    </li>
                  ))}
                </ul>
              )}
              {m.total > m.items.length && <p className="muted small">und {m.total - m.items.length} weitere</p>}
              <p style={{ marginTop: "0.75rem" }}><Link to="/garage" className="link">Zur Garage →</Link></p>
            </Panel>
    ),
    bikes: bikes.length > 0 ? (
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
    ) : null,
    goal: (
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
                        {g.metric === "km" && !g.reached_on && g.per_week_needed != null && isCurrent && (
                          <p className="goal-hint small">
                            {t.km >= g.per_week_needed
                              ? `Diese Woche hast du dein Pensum von ${fmtKm(g.per_week_needed)} km schon erreicht.`
                              : `Diese Woche noch ${fmtKm(g.per_week_needed - t.km)} km, dann bist du auf Kurs.`}
                          </p>
                        )}
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
    ),
    recent: (
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
    ),
  };
  const wide = new Set(lay.catalog.filter((c) => c.wide).map((c) => c.id));

  return (
    <>
      <header className="page-head">
        <h1>{greeting()}</h1>
        <p className="muted">{new Date(d.today + "T00:00:00").toLocaleDateString("de-DE", { weekday: "long", day: "numeric", month: "long" })}</p>
        {!(!d.has_rides && bikes.length === 0) && (
          <button className="btn small" onClick={() => setEditing((v) => !v)} aria-expanded={editing}>{editing ? "Fertig" : "Startseite anpassen"}</button>
        )}
      </header>

      <MechanicRequests items={d.mechanic_requests} />

      {!d.has_rides && bikes.length === 0 ? (
        <EmptyState title="Willkommen bei BikeHelper" text="Lege zuerst dein Rad an und importiere dann deine Fahrten.">
          <div className="actions">
            <Link className="btn primary" to="/garage">Rad anlegen</Link>
            <Link className="btn" to="/rides">Fahrten importieren</Link>
          </div>
        </EmptyState>
      ) : (
        <>
          <WetNotice items={d.wet_notices} />
          {editing && <HomeEditor lay={lay} onSave={async (body) => setLay(await api.put("/me/ui", body))} onClose={() => setEditing(false)} />}
          {lay.layout.length === 0 && !editing && (
            <p className="muted">Deine Startseite ist leer. <button className="link" onClick={() => setEditing(true)}>Blöcke hinzufügen</button></p>
          )}
          <div className="home-blocks">
            {lay.layout.map((id) => {
              const node = blocks[id] ?? (DATA_BLOCKS.includes(id) ? <AnalysisPanel id={id} data={extra[id]} /> : null);
              return node ? <div key={id} className={`home-cell ${wide.has(id) ? "home-wide" : ""}`}>{node}</div> : null;
            })}
          </div>
        </>
      )}
    </>
  );
}
