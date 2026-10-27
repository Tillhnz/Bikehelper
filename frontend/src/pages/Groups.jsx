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
  const [error, setError] = useState("");

  useEffect(() => { pendingGroupToken.clear(); api.get(`/groups/join/${encodeURIComponent(token)}`).then(setInfo).catch((e) => setError(e.message)); }, [token]);

  async function join(e) {
    e.preventDefault();
    setError("");
    try {
      const r = await api.post("/groups/join", { token, display_name: name, share });
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
          <button className="btn primary">{info.already_member ? "Schon Mitglied, weiter" : "Beitreten"}</button>
        </form>
      </section>
    </>
  );
}

// ---------- Gruppenansicht ----------

function WeeklyLines({ data }) {
  const { weeks, series } = data;
  if (!series.length) return null;
  const W = 640, H = 200, padL = 40, padB = 22, padT = 10, padR = 10;
  const max = Math.max(1, ...series.flatMap((s) => s.km));
  const sx = (i) => padL + (i / (weeks.length - 1)) * (W - padL - padR);
  const sy = (v) => padT + (1 - v / max) * (H - padT - padB);
  const colors = ["var(--celeste)", "#f2b84b", "#ff6b6b", "#8fd16a", "#b48cf2", "#4aa8ff", "#e58bc1", "#9aa7b2"];
  return (
    <div>
      <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label="Kilometer pro Woche je Mitglied, letzte 12 Wochen">
        {[0, 0.5, 1].map((f) => (
          <g key={f}>
            <line x1={padL} x2={W - padR} y1={sy(max * f)} y2={sy(max * f)} className="chart-grid" />
            <text x={padL - 6} y={sy(max * f) + 4} textAnchor="end" className="chart-label">{fmtNum(max * f, 0)}</text>
          </g>
        ))}
        {weeks.map((w, i) => (i % 2 === 0 ? <text key={w} x={sx(i)} y={H - 6} textAnchor="middle" className="chart-label">{w.slice(8, 10)}.{w.slice(5, 7)}.</text> : null))}
        {series.map((s, k) => (
          <path key={s.display_name} d={s.km.map((v, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join("")}
            fill="none" stroke={colors[k % colors.length]} strokeWidth={s.is_me ? 3 : 1.8} strokeLinejoin="round" />
        ))}
      </svg>
      <p className="small group-legend">
        {series.map((s, k) => <span key={s.display_name}><i style={{ background: colors[k % colors.length] }} />{s.display_name}{s.is_me ? " (du)" : ""}</span>)}
      </p>
    </div>
  );
}

function Board({ groupId }) {
  const [period, setPeriod] = useState("week");
  const [offset, setOffset] = useState(0);
  const [metric, setMetric] = useState("km");
  const [d, setD] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/groups/${groupId}/stats?period=${period}&offset=${offset}`).then((r) => { setD(r); setError(""); }).catch((e) => setError(e.message));
  }, [groupId, period, offset]);

  const rows = d ? [...d.rows].sort((a, b) => (b[metric] ?? -1) - (a[metric] ?? -1) || a.display_name.localeCompare(b.display_name)) : [];
  const best = (m) => Math.max(0, ...(d?.rows || []).map((r) => r[m] ?? 0));

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
              {rows.map((r, i) => (
                <tr key={r.user_id} className={r.is_me ? "me" : ""}>
                  <td>{r[metric] ? (MEDAL[r.rank[metric] - 1] || r.rank[metric]) : "–"}</td>
                  <td>{r.display_name}{r.is_me ? " (du)" : ""}</td>
                  {Object.entries(METRICS).map(([k, m]) => (
                    <td key={k} className={`${metric === k ? "sorted" : ""} ${r[k] && r[k] === best(k) ? "best" : ""}`}>{r[k] ? m.cell(r[k]) : "–"}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {d?.not_sharing.length > 0 && <p className="muted small">Pausieren: {d.not_sharing.join(", ")}</p>}
      {d?.rows.length > 0 && <><h3>Kilometer pro Woche, letzte 12 Wochen</h3><WeeklyLines data={d.weekly} /></>}
    </section>
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
            <span>{m.display_name}{m.is_me ? " (du)" : ""} <span className="muted small">{m.role === "admin" ? "Administrator" : "Mitglied"}{m.share ? "" : " · pausiert"}</span></span>
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
      <p>
        <button className="link danger" onClick={async () => { if (await confirmDialog(`Gruppe „${g.name}“ verlassen?`)) { try { await api.del(`/groups/${g.id}/me`); navigate("/groups"); } catch (e) { setError(e.message); } } }}>Gruppe verlassen</button>
      </p>

      {isAdmin && (
        <>
          <h3>Einladen</h3>
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
      <Board groupId={g.id} key={`${g.id}-${g.share}`} />
      <Members g={g} reload={load} />
    </>
  );
}
