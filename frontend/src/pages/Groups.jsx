import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api, fmtDuration, fmtNum } from "../api.js";
import { copyText } from "../clipboard.js";
import { EmptyState } from "../components/ui.jsx";
import { Loading, confirmDialog, toast } from "../components/feedback.jsx";

const PENDING_KEY = "bikehelper.pendingGroupToken";
export const pendingGroupToken = {
  get: () => { try { return sessionStorage.getItem(PENDING_KEY); } catch { return null; } },
  set: (t) => { try { sessionStorage.setItem(PENDING_KEY, t); } catch { /* ohne Speicher: Link nach der Anmeldung erneut öffnen */ } },
  clear: () => { try { sessionStorage.removeItem(PENDING_KEY); } catch { /* egal */ } },
};

const PERIODS = [["week", "Woche"], ["month", "Monat"], ["year", "Jahr"], ["all", "Gesamt"]];
const METRICS = {
  km: { label: "Kilometer", cell: (v) => `${fmtNum(v, 1)} km` },
  elev_m: { label: "Höhenmeter", cell: (v) => `${fmtNum(v, 0)} m` },
  time_s: { label: "Fahrzeit", cell: (v) => fmtDuration(v) },
  rides: { label: "Fahrten", cell: (v) => String(v) },
  avg_speed: { label: "Ø Tempo", cell: (v) => `${fmtNum(v, 1)} km/h` },
  longest_km: { label: "Längste Fahrt", cell: (v) => `${fmtNum(v, 1)} km` },
  active_days: { label: "Aktive Tage", cell: (v) => String(v) },
};
const MEDAL = ["🥇", "🥈", "🥉"];

// ---------- Übersicht ----------

export default function Groups() {
  const [groups, setGroups] = useState(null);
  const [invites, setInvites] = useState([]);
  const [name, setName] = useState("");
  const [me, setMe] = useState("");
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const load = useCallback(() => {
    Promise.all([api.get("/groups"), api.get("/groups/invitations")]).then(([g, i]) => { setGroups(g); setInvites(i); }).catch((e) => setError(e.message));
  }, []);
  useEffect(() => { load(); }, [load]);

  async function create(e) {
    e.preventDefault();
    setError("");
    try {
      const r = await api.post("/groups", { name, display_name: me });
      navigate(`/groups/${r.id}`);
    } catch (err) { setError(err.message); }
  }

  return (
    <>
      <header className="page-head"><h1>Gruppen</h1></header>
      <p className="muted">
        In einer Gruppe vergleichst du dich mit Freunden: Bestenlisten für Woche, Monat und Jahr. Geteilt werden nur Kennzahlen wie Kilometer und
        Höhenmeter, keine Strecken, Karten, Räder oder Fahrtnamen. Du bestimmst deinen Anzeigenamen und kannst die Teilnahme jederzeit pausieren.
      </p>
      {error && <p className="error" role="alert">{error}</p>}
      {invites.length > 0 && (
        <section className="panel attention">
          <h2>Einladungen</h2>
          <ul className="plain">
            {invites.map((i) => (
              <li key={i.token}>Einladung in „{i.group}“ <Link className="btn small primary" to={`/groups/join/${i.token}`}>Ansehen</Link></li>
            ))}
          </ul>
        </section>
      )}
      {!groups ? <Loading /> : groups.length === 0 ? (
        <EmptyState title="Noch keine Gruppe" text="Gründe unten eine Gruppe und lade Freunde per E-Mail ein." />
      ) : (
        <div className="group-cards">
          {groups.map((g) => (
            <Link key={g.id} to={`/groups/${g.id}`} className="panel group-card">
              <h2>{g.name}</h2>
              <p className="muted small">{g.members} {g.members === 1 ? "Mitglied" : "Mitglieder"}{g.role === "admin" ? " · du bist Administrator" : ""}{g.share ? "" : " · du pausierst"}</p>
            </Link>
          ))}
        </div>
      )}
      <section className="panel">
        <h2>Neue Gruppe</h2>
        <form className="inline-form" onSubmit={create}>
          <label className="grow">Gruppenname<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required /></label>
          <label className="grow">Dein Anzeigename in der Gruppe<input value={me} onChange={(e) => setMe(e.target.value)} maxLength={60} required /></label>
          <button className="btn primary">Gruppe gründen</button>
        </form>
      </section>
    </>
  );
}

// ---------- Einladung annehmen ----------

export function GroupJoin() {
  const { token } = useParams();
  const navigate = useNavigate();
  const [info, setInfo] = useState(null);
  const [name, setName] = useState("");
  const [share, setShare] = useState(true);
  const [shared, setShared] = useState([]);
  const [error, setError] = useState("");

  useEffect(() => { pendingGroupToken.clear(); api.get(`/groups/join/${encodeURIComponent(token)}`).then(setInfo).catch((e) => setError(e.message)); }, [token]);

  async function join(e) {
    e.preventDefault();
    setError("");
    try {
      const r = await api.post("/groups/join", { token, display_name: name, share, shared });
      toast("Du bist jetzt in der Gruppe.");
      navigate(`/groups/${r.id}`);
    } catch (err) { setError(err.message); }
  }

  if (error && !info) return <><p className="error" role="alert">{error}</p><p><Link className="link" to="/groups">Zu den Gruppen</Link></p></>;
  if (!info) return <Loading />;
  return (
    <>
      <header className="page-head"><h1>Einladung in „{info.group}“</h1></header>
      <section className="panel">
        <p>In der Gruppe sehen die anderen nur deine Kennzahlen (Kilometer, Höhenmeter, Fahrzeit, Fahrten, Tempo) unter dem Namen, den du hier wählst. Keine Strecken, Karten, Räder oder deine E-Mail-Adresse. Du kannst jederzeit pausieren oder die Gruppe verlassen.</p>
        {error && <p className="error" role="alert">{error}</p>}
        <form className="inline-form" onSubmit={join}>
          <label className="grow">Dein Anzeigename<input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required autoFocus /></label>
          <label className="check"><input type="checkbox" checked={share} onChange={(e) => setShare(e.target.checked)} /><span>Meine Kennzahlen sofort teilen</span></label>
          {share && <ShareChoices categories={info.categories} value={shared} onChange={setShared} />}
          <button className="btn primary">{info.already_member ? "Schon Mitglied, weiter" : "Beitreten"}</button>
        </form>
      </section>
    </>
  );
}

// ---------- Gruppenansicht ----------

const COLORS = ["var(--celeste)", "#f2b84b", "#ff6b6b", "#8fd16a", "#b48cf2", "#4aa8ff", "#e58bc1", "#9aa7b2"];

/** Verlauf je Mitglied; die Punkte folgen dem gewählten Zeitraum (Tage, Monate oder Jahre), optional aufsummiert. */
function SeriesChart({ data, cumulative }) {
  const { labels, members } = data;
  if (!members.length || labels.length < 2) return <p className="muted small">Für „Gesamt“ braucht der Verlauf mindestens zwei Jahre.</p>;
  const lines = members.map((m) => ({ ...m, v: cumulative ? m.km.reduce((acc, x) => [...acc, (acc[acc.length - 1] || 0) + x], []) : m.km }));
  const W = 640, H = 210, padL = 44, padB = 24, padT = 10, padR = 12;
  const max = Math.max(1, ...lines.flatMap((m) => m.v));
  const sx = (i) => padL + (i / (labels.length - 1)) * (W - padL - padR);
  const sy = (v) => padT + (1 - v / max) * (H - padT - padB);
  const every = Math.ceil(labels.length / 10);
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={cumulative ? "Aufsummierte Kilometer je Mitglied" : "Kilometer je Mitglied im Zeitraum"}>
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={padL} x2={W - padR} y1={sy(max * f)} y2={sy(max * f)} className="chart-grid" />
            <text x={padL - 6} y={sy(max * f) + 4} textAnchor="end" className="chart-label">{fmtNum(max * f, 0)}</text>
          </g>
        ))}
        {labels.map((l, i) => (i % every === 0 ? <text key={l + i} x={sx(i)} y={H - 6} textAnchor="middle" className="chart-label">{l}</text> : null))}
        {lines.map((m, k) => (
          <path key={m.display_name} d={m.v.map((v, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join("")}
            fill="none" stroke={COLORS[k % COLORS.length]} strokeWidth={m.is_me ? 3 : 1.8} strokeLinejoin="round" />
        ))}
      </svg>
      <p className="small group-legend">
        {lines.map((m, k) => <span key={m.display_name}><i style={{ background: COLORS[k % COLORS.length] }} />{m.display_name}{m.is_me ? " (du)" : ""}</span>)}
      </p>
    </div>
  );
}

const dash = <span className="muted" title="Wird nicht geteilt oder hat keine Werte">–</span>;
const WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

/** Tabelle für einen freigegebenen Bereich: eine Zeile je Mitglied, der beste Wert je Spalte ist hervorgehoben. */
function ExtraTable({ title, note, rows, cat, cols }) {
  const has = rows.some((r) => r.extras[cat]);
  if (!has) return null;
  const vals = cols.map((c) => rows.map((r) => (r.extras[cat] ? c.get(r.extras[cat]) : null)));
  return (
    <>
      <h3>{title}</h3>
      {note && <p className="muted small">{note}</p>}
      <div className="table-wrap">
        <table className="group-table">
          <thead><tr><th>Mitglied</th>{cols.map((c) => <th key={c.label}>{c.label}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={r.user_id} className={r.is_me ? "me" : ""}>
                <td>{r.display_name}{r.is_me ? " (du)" : ""}</td>
                {cols.map((c, k) => {
                  const v = vals[k][i];
                  const best = c.best && v != null && v > 0 && v === Math.max(...vals[k].filter((x) => x != null));
                  return <td key={c.label} className={best ? "best" : ""}>{v == null || v === 0 && !c.zero ? dash : c.fmt(v)}</td>;
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  );
}

const km1 = (v) => `${fmtNum(v, 1)} km`;
const num0 = (v) => fmtNum(v, 0);

function Extras({ rows }) {
  return (
    <>
      <ExtraTable title="Fahrrhythmus: Kilometer je Wochentag" cat="rhythm" rows={rows}
        cols={WD.map((d, i) => ({ label: d, get: (x) => x.weekdays[i], fmt: num0, best: true }))} />
      <ExtraTable title="Fahrrhythmus: Fahrzeit je Tageszeit" cat="rhythm" rows={rows}
        cols={(rows.find((r) => r.extras.rhythm)?.extras.rhythm.dayparts || []).map((d, i) => ({ label: d.label, get: (x) => x.dayparts[i].hours, fmt: (v) => `${fmtNum(v, 1)} h`, best: true }))} />
      <ExtraTable title="Fahrrhythmus: Fahrten nach Länge" cat="rhythm" rows={rows}
        cols={(rows.find((r) => r.extras.rhythm)?.extras.rhythm.distances || []).map((d, i) => ({ label: d.label, get: (x) => x.distances[i].rides, fmt: String, best: true }))} />
      <ExtraTable title="Rekorde im Zeitraum" cat="records" rows={rows} cols={[
        { label: "Längste Fahrt", get: (x) => x.longest_km, fmt: km1, best: true },
        { label: "Meiste Höhenmeter (Fahrt)", get: (x) => x.most_climb_m, fmt: (v) => `${num0(v)} m`, best: true },
        { label: "Bester Tag", get: (x) => x.best_day_km, fmt: km1, best: true },
        { label: "Schnellster Schnitt", get: (x) => x.fastest_avg, fmt: (v) => `${fmtNum(v, 1)} km/h`, best: true },
        { label: "Serie in Tagen", get: (x) => x.day_streak, fmt: String, best: true },
        { label: "Serie in Wochen", get: (x) => x.week_streak, fmt: String, best: true },
      ]} />
      <ExtraTable title="Belastung und Form" note="Geschätzt aus Fahrzeit, Höhenmetern und Tempo, ohne Puls oder Leistung. Stand am Ende des Zeitraums (Fitness 42 Tage, Ermüdung 7 Tage)." cat="load" rows={rows} cols={[
        { label: "Belastung im Zeitraum", get: (x) => x.period_load, fmt: num0, best: true },
        { label: "Fitness", get: (x) => x.fitness, fmt: (v) => fmtNum(v, 1), best: true },
        { label: "Ermüdung", get: (x) => x.fatigue, fmt: (v) => fmtNum(v, 1) },
        { label: "Form", get: (x) => x.form, fmt: (v) => fmtNum(v, 1), zero: true },
      ]} />
      <ExtraTable title="Wetter" cat="weather" rows={rows} cols={[
        { label: "Ø Temperatur", get: (x) => x.avg_temp, fmt: (v) => `${fmtNum(v, 1)} °C`, zero: true },
        { label: "Kilometer bei Regen/nass", get: (x) => x.wet_km, fmt: km1, best: true },
        { label: "Anteil nass", get: (x) => x.wet_share, fmt: (v) => `${v} %` },
        { label: "Regenfahrten", get: (x) => x.rainy_rides, fmt: String, best: true },
        { label: "Kälteste Fahrt", get: (x) => x.coldest, fmt: (v) => `${fmtNum(v, 1)} °C`, zero: true },
        { label: "Wärmste Fahrt", get: (x) => x.hottest, fmt: (v) => `${fmtNum(v, 1)} °C`, zero: true },
      ]} />
    </>
  );
}

function Board({ groupId }) {
  const [period, setPeriod] = useState("week");
  const [offset, setOffset] = useState(0);
  const [metric, setMetric] = useState("km");
  const [cumulative, setCumulative] = useState(false);
  const [d, setD] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/groups/${groupId}/stats?period=${period}&offset=${offset}`).then((r) => { setD(r); setError(""); }).catch((e) => setError(e.message));
  }, [groupId, period, offset]);

  const rows = d ? [...d.rows].sort((a, b) => (b[metric] ?? -1) - (a[metric] ?? -1) || a.display_name.localeCompare(b.display_name)) : [];
  const best = (m) => Math.max(0, ...(d?.rows || []).map((r) => r[m] ?? 0));
  const change = (r) => {
    const before = r.prev?.[metric];
    if (before == null || !before || metric === "avg_speed" || metric === "longest_km" || metric === "active_days") return null;
    const pct = Math.round(((r[metric] - before) / before) * 100);
    return pct === 0 ? null : <span className={`delta ${pct > 0 ? "up" : "down"}`} title="Veränderung gegenüber dem Zeitraum davor">{pct > 0 ? "▲" : "▼"} {Math.abs(pct)} %</span>;
  };

  return (
    <section className="panel">
      <div className="log-head">
        <h2>Rangliste</h2>
        <div className="segmented" role="group" aria-label="Zeitraum">
          {PERIODS.map(([k, label]) => <button key={k} type="button" className={period === k ? "on" : ""} aria-pressed={period === k} onClick={() => { setPeriod(k); setOffset(0); }}>{label}</button>)}
        </div>
      </div>
      {d && (
        <p className="group-period">
          <button className="btn small" onClick={() => setOffset(offset - 1)} disabled={!d.can_prev} aria-label="Früherer Zeitraum">‹</button>
          <strong>{d.label}</strong>
          <button className="btn small" onClick={() => setOffset(offset + 1)} disabled={!d.can_next} aria-label="Späterer Zeitraum">›</button>
        </p>
      )}
      {error && <p className="error" role="alert">{error}</p>}
      {!d && !error && <Loading rows={3} />}
      {d && d.rows.length === 0 && <p className="muted">Niemand in dieser Gruppe teilt gerade Kennzahlen.</p>}
      {d && d.rows.length > 0 && (
        <div className="table-wrap">
          <table className="group-table">
            <thead>
              <tr>
                <th>#</th><th>Mitglied</th>
                {Object.entries(METRICS).map(([k, m]) => (
                  <th key={k} className={metric === k ? "sorted" : ""} aria-sort={metric === k ? "descending" : "none"}>
                    <button type="button" className="th-btn" onClick={() => setMetric(k)} title="Danach sortieren">{m.label}</button>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.user_id} className={r.is_me ? "me" : ""}>
                  <td>{r[metric] ? (MEDAL[r.rank[metric] - 1] || r.rank[metric]) : "–"}</td>
                  <td>{r.display_name}{r.is_me ? " (du)" : ""}</td>
                  {Object.entries(METRICS).map(([k, m]) => (
                    <td key={k} className={`${metric === k ? "sorted" : ""} ${r[k] && r[k] === best(k) ? "best" : ""}`}>
                      {r[k] ? m.cell(r[k]) : "–"}{k === metric && change(r)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {d?.not_sharing.length > 0 && <p className="muted small">Pausieren: {d.not_sharing.join(", ")}</p>}
      {d?.rows.length > 0 && (
        <>
          <div className="log-head">
            <h3>Kilometer im Verlauf: {d.label}</h3>
            <label className="check"><input type="checkbox" checked={cumulative} onChange={(e) => setCumulative(e.target.checked)} /><span>Aufsummiert</span></label>
          </div>
          <SeriesChart data={d.series} cumulative={cumulative} />
          <Extras rows={rows} />
          <p className="muted small">Mehr Bereiche erscheinen, sobald Mitglieder sie unter „Meine Teilnahme“ freigeben. Orte, Strecken, Räder und Wartung werden nie geteilt.</p>
        </>
      )}
    </section>
  );
}

/** Auswahl, was zusätzlich zu den Grundwerten geteilt wird. */
export function ShareChoices({ categories, value, onChange }) {
  const toggle = (k) => onChange(value.includes(k) ? value.filter((x) => x !== k) : [...value, k]);
  return (
    <fieldset className="share-choices">
      <legend>Was teilst du mit der Gruppe?</legend>
      <p className="muted small">Immer geteilt (sonst wäre keine Rangliste möglich): Kilometer, Höhenmeter, Fahrzeit, Fahrten, Ø Tempo, längste Fahrt, aktive Tage. Dazu kannst du freigeben:</p>
      {categories.map((c) => (
        <label key={c.key} className="check">
          <input type="checkbox" checked={value.includes(c.key)} onChange={() => toggle(c.key)} />
          <span><strong>{c.label}</strong> <span className="muted small">{c.text}</span></span>
        </label>
      ))}
      <p className="muted small">Nie geteilt: Strecken, Orte, Karten, Heatmap, Räder, Wartung, Fahrtnamen, Ziele und deine E-Mail-Adresse. Du kannst die Auswahl jederzeit ändern.</p>
    </fieldset>
  );
}

function Members({ g, reload }) {
  const [email, setEmail] = useState("");
  const [link, setLink] = useState(null);
  const [name, setName] = useState(g.display_name);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  const isAdmin = g.role === "admin";

  async function run(fn, done) {
    setError("");
    try { await fn(); if (done) toast(done); await reload(); } catch (e) { setError(e.message); }
  }

  async function invite(e) {
    e.preventDefault();
    setError("");
    try {
      const r = await api.post(`/groups/${g.id}/invites`, { email });
      setLink(r.mailed ? null : r.link);
      toast(r.mailed ? "Einladung per E-Mail verschickt." : "Einladung erstellt. Schicke den Link selbst.");
      setEmail("");
      await reload();
    } catch (err) { setError(err.message); }
  }

  return (
    <section className="panel">
      <h2>Mitglieder und Einstellungen</h2>
      {error && <p className="error" role="alert">{error}</p>}
      <ul className="plain group-members">
        {g.members.map((m) => (
          <li key={m.user_id}>
            <span>{m.display_name}{m.is_me ? " (du)" : ""} <span className="muted small">{m.role === "admin" ? "Administrator" : "Mitglied"}{m.share ? "" : " · pausiert"}{m.share && m.shared.length ? ` · teilt zusätzlich: ${m.shared.map((k) => g.categories.find((c) => c.key === k)?.label || k).join(", ")}` : ""}</span></span>
            {isAdmin && !m.is_me && (
              <span className="row-actions">
                <button className="link small" onClick={() => run(() => api.put(`/groups/${g.id}/members/${m.user_id}/role`, { role: m.role === "admin" ? "member" : "admin" }))}>{m.role === "admin" ? "Zum Mitglied machen" : "Zum Administrator machen"}</button>
                <button className="link small danger" onClick={async () => { if (await confirmDialog(`„${m.display_name}“ aus der Gruppe entfernen?`)) run(() => api.del(`/groups/${g.id}/members/${m.user_id}`), "Entfernt."); }}>Entfernen</button>
              </span>
            )}
          </li>
        ))}
      </ul>

      <h3>Meine Teilnahme</h3>
      <form className="inline-form" onSubmit={(e) => { e.preventDefault(); run(() => api.put(`/groups/${g.id}/me`, { display_name: name }), "Name geändert."); }}>
        <label className="grow">Anzeigename<input value={name} onChange={(e) => setName(e.target.value)} maxLength={60} required /></label>
        <button className="btn">Speichern</button>
      </form>
      <label className="check">
        <input type="checkbox" checked={g.share} onChange={(e) => run(() => api.put(`/groups/${g.id}/me`, { share: e.target.checked }))} />
        <span>Meine Kennzahlen in dieser Gruppe zeigen (aus: du erscheinst nicht in den Ranglisten)</span>
      </label>
      {g.share && <ShareChoices categories={g.categories} value={g.shared} onChange={(v) => run(() => api.put(`/groups/${g.id}/me`, { shared: v }))} />}
      <p>
        <button className="link danger" onClick={async () => { if (await confirmDialog(`Gruppe „${g.name}“ verlassen?`)) { try { await api.del(`/groups/${g.id}/me`); navigate("/groups"); } catch (e) { setError(e.message); } } }}>Gruppe verlassen</button>
      </p>

      {isAdmin && (
        <>
          <h3>Einladungslink</h3>
          <p className="muted small">Ein Link für alle, die du einladen willst, zum Beispiel in einer Messenger-Gruppe. Wer ihn öffnet, kann sich dort auch ein BikeHelper-Konto anlegen, falls er noch keines hat, und tritt danach bei. Der Link gilt 30 Tage. Ein neuer Link ersetzt den alten.</p>
          {g.invite_link ? (
            <p className="group-link">
              <code>{g.invite_link}</code>{" "}
              <button className="btn small" onClick={async () => toast((await copyText(g.invite_link)) ? "Link kopiert." : "Bitte den Link markieren und selbst kopieren.")}>Kopieren</button>{" "}
              <button className="link small" onClick={async () => { if (await confirmDialog("Neuen Link erzeugen? Der alte funktioniert dann nicht mehr.")) run(() => api.post(`/groups/${g.id}/invite-link`), "Neuer Link erstellt."); }}>Neuer Link</button>{" "}
              <button className="link small danger" onClick={() => run(() => api.del(`/groups/${g.id}/invite-link`), "Link abgeschaltet.")}>Abschalten</button>
            </p>
          ) : (
            <p><button className="btn" onClick={() => run(() => api.post(`/groups/${g.id}/invite-link`), "Link erstellt.")}>Einladungslink erstellen</button></p>
          )}
          <h3>Per E-Mail einladen</h3>
          <form className="inline-form" onSubmit={invite}>
            <label className="grow">E-Mail-Adresse<input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required /></label>
            <button className="btn primary">Einladen</button>
          </form>
          <p className="muted small">{g.mail_enabled ? "Die Einladung geht per E-Mail raus." : "Auf diesem Server ist kein E-Mail-Versand eingerichtet: Du bekommst einen Link zum Weitergeben."} Sie gilt 14 Tage und einmal. Hat die Person ein Konto mit dieser Adresse, sieht sie die Einladung auch unter Gruppen.</p>
          {link && (
            <p className="group-link"><code>{link}</code> <button className="btn small" onClick={async () => toast((await copyText(link)) ? "Link kopiert." : "Bitte den Link markieren und selbst kopieren.", "ok")}>Kopieren</button></p>
          )}
          {g.invites.length > 0 && (
            <ul className="plain">
              {g.invites.map((i) => (
                <li key={i.id}>{i.email} <span className="muted small">{i.expired ? "abgelaufen" : "offen"}</span> <button className="link small danger" onClick={() => run(() => api.del(`/groups/${g.id}/invites/${i.id}`))}>Zurückziehen</button></li>
              ))}
            </ul>
          )}
          <h3>Gruppe verwalten</h3>
          <GroupAdmin g={g} reload={reload} />
        </>
      )}
    </section>
  );
}

function GroupAdmin({ g, reload }) {
  const [name, setName] = useState(g.name);
  const [error, setError] = useState("");
  const navigate = useNavigate();
  async function rename(e) {
    e.preventDefault();
    try { await api.put(`/groups/${g.id}`, { name }); toast("Gruppe umbenannt."); await reload(); } catch (err) { setError(err.message); }
  }
  async function remove() {
    if (!await confirmDialog(`Gruppe „${g.name}“ für alle löschen? Die Daten der Mitglieder bleiben unberührt.`)) return;
    try { await api.del(`/groups/${g.id}`); navigate("/groups"); } catch (err) { setError(err.message); }
  }
  return (
    <>
      {error && <p className="error" role="alert">{error}</p>}
      <form className="inline-form" onSubmit={rename}>
        <label className="grow">Gruppenname<input value={name} onChange={(e) => setName(e.target.value)} maxLength={80} required /></label>
        <button className="btn">Umbenennen</button>
      </form>
      <p><button className="link danger" onClick={remove}>Gruppe löschen</button></p>
    </>
  );
}

export function GroupDetail() {
  const { id } = useParams();
  const [g, setG] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => api.get(`/groups/${id}`).then(setG).catch((e) => setError(e.message)), [id]);
  useEffect(() => { setG(null); load(); }, [load]);

  if (error) return <><p className="error" role="alert">{error}</p><p><Link className="link" to="/groups">Zu den Gruppen</Link></p></>;
  if (!g) return <Loading />;
  return (
    <>
      <p><Link to="/groups" className="link">← Alle Gruppen</Link></p>
      <header className="page-head"><h1>{g.name}</h1></header>
      <Board groupId={g.id} key={`${g.id}-${g.share}-${g.shared.join()}`} />
      <Members g={g} reload={load} />
    </>
  );
}
