import { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, fmtDate, fmtDateTime } from "../api.js";
import { Loading, confirmDialog, toast } from "../components/feedback.jsx";

const ROLE_TEXT = { admin: "Administrator", user: "Nutzer" };

/** Ein Block mit Einstellungsfeldern, der gemeinsam gespeichert wird. */
function SettingsBlock({ title, intro, fields, defs, spec, onSaved, extra }) {
  const initial = () =>
    Object.fromEntries(spec.map((f) => [f.key, f.secret ? "" : defs[f.key]?.value ?? (f.type === "bool" ? false : "")]));
  const [form, setForm] = useState(initial);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { setForm(initial()); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [defs]);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setError("");
    try {
      const values = {};
      for (const f of spec) {
        if (f.secret) {
          if (form[f.key] !== "") values[f.key] = form[f.key]; // leer = bisherigen Wert behalten
        } else {
          values[f.key] = form[f.key];
        }
      }
      await onSaved(values);
      toast("Gespeichert. Die Änderung gilt sofort.");
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <h2>{title}</h2>
      {intro && <p className="muted small">{intro}</p>}
      <form className="form-grid" onSubmit={save}>
        {spec.map((f) => {
          const def = defs[f.key];
          if (f.type === "bool") {
            return (
              <label key={f.key} className="check span-all">
                <input type="checkbox" checked={!!form[f.key]} onChange={(e) => setForm({ ...form, [f.key]: e.target.checked })} />
                <span>{f.label}{f.hint && <span className="hint block">{f.hint}</span>}</span>
              </label>
            );
          }
          return (
            <label key={f.key} className={f.wide ? "span-all" : ""}>
              {f.label}
              <input
                type={f.secret ? "password" : f.type === "number" ? "number" : "text"}
                value={form[f.key] ?? ""}
                placeholder={f.secret ? (def?.set ? "gespeichert, leer lassen zum Behalten" : "") : f.placeholder}
                onChange={(e) => setForm({ ...form, [f.key]: e.target.value })}
                autoComplete="off"
                min={f.min}
                max={f.max}
              />
              {f.hint && <span className="hint">{f.hint}</span>}
              {f.secret && def?.set && (
                <button type="button" className="link small" onClick={() => onSaved({ [f.key]: "" }).then(() => toast(`${f.label} gelöscht.`)).catch((er) => setError(er.message))}>
                  gespeicherten Wert löschen
                </button>
              )}
            </label>
          );
        })}
        <div className="actions span-all">
          <button className="btn primary" disabled={busy}>Speichern</button>
          {extra}
        </div>
      </form>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Accounts({ me }) {
  const [users, setUsers] = useState([]);
  const [error, setError] = useState("");
  const load = useCallback(() => api.get("/admin/users").then(setUsers).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const run = async (fn, done) => {
    setError("");
    try { await fn(); if (done) toast(done); await load(); } catch (err) { setError(err.message); }
  };

  return (
    <section className="panel">
      <h2>Konten und Rollen ({users.length})</h2>
      <p className="muted small">
        Als Administrator siehst du hier nur E-Mail-Adresse, Rolle und Status. Räder, Fahrten, Orte und andere persönliche Daten bleiben für dich unsichtbar.
        Administratoren verwalten Konten, Einladungen und Servereinstellungen. Nutzer verwalten nur ihre eigenen Daten.
      </p>
      <ul className="log-list">
        {users.map((u) => (
          <li key={u.id}>
            <span>
              <strong>{u.email}</strong>{" "}
              <span className={`pill ${u.role === "admin" ? "pill-ok" : "pill-muted"}`}>{ROLE_TEXT[u.role]}</span>
              {!u.active && <> <span className="pill pill-due">Gesperrt</span></>}
              <span className="muted small"> seit {u.created_at ? fmtDate(u.created_at.slice(0, 10)) : "?"}{u.is_me ? ", das bist du" : ""}</span>
            </span>
            {!u.is_me && (
              <span className="rule-actions">
                <button
                  className="link small"
                  onClick={() => run(() => api.put(`/admin/users/${u.id}`, { role: u.role === "admin" ? "user" : "admin" }), "Rolle geändert.")}
                >
                  {u.role === "admin" ? "Zum Nutzer machen" : "Zum Administrator machen"}
                </button>
                <button className="link small" onClick={() => run(() => api.put(`/admin/users/${u.id}`, { active: !u.active }), u.active ? "Konto gesperrt." : "Konto entsperrt.")}>
                  {u.active ? "Sperren" : "Entsperren"}
                </button>
                <button
                  className="link small danger"
                  onClick={async () => { if (await confirmDialog(`Konto ${u.email} samt allen Daten löschen? Das lässt sich nicht rückgängig machen.`)) run(() => api.del(`/admin/users/${u.id}`), "Konto gelöscht."); }}
                >
                  Löschen
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Invites() {
  const [invites, setInvites] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => api.get("/admin/invites").then(setInvites).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const run = async (fn, done) => {
    setError("");
    try { await fn(); if (done) toast(done); await load(); } catch (err) { setError(err.message); }
  };
  const link = (code) => `${window.location.origin}/login?invite=${code}`;

  return (
    <section className="panel">
      <h2>Einladungen</h2>
      <p className="muted small">
        Ist die offene Registrierung aus, kommen neue Nutzer nur mit einem Einladungscode hinein. Jeder Code gilt einmal.
        Schick der Person den Link: Er öffnet direkt die Registrierung mit eingetragenem Code.
      </p>
      <div className="actions">
        <button className="btn primary" onClick={() => run(() => api.post("/admin/invites", {}))}>Neue Einladung erzeugen</button>
      </div>
      {invites?.length > 0 && (
        <ul className="log-list">
          {invites.map((i) => (
            <li key={i.id}>
              <span><strong>{i.code}</strong> <span className="muted">{i.used_by_email ? `verwendet von ${i.used_by_email}` : "offen"}</span></span>
              <span className="rule-actions">
                {!i.used_by_email && (
                  <button className="link small" onClick={() => run(() => navigator.clipboard.writeText(link(i.code)), "Einladungslink kopiert.")}>Link kopieren</button>
                )}
                <button className="link small danger" onClick={() => run(() => api.del(`/admin/invites/${i.id}`))}>Löschen</button>
              </span>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Updates() {
  const [st, setSt] = useState(null);
  const [error, setError] = useState("");
  const [checking, setChecking] = useState(false);
  const [watching, setWatching] = useState(false);

  const load = useCallback(async (check = false) => {
    try {
      const r = await api.get(`/admin/update${check ? "?check=true" : ""}`);
      setSt(r);
      setError("");
      return r;
    } catch (e) {
      setError(e.message);
      return null;
    }
  }, []);

  useEffect(() => { load(false); }, [load]);

  // Während des Updates fragen wir regelmäßig nach. Das Backend startet dabei kurz neu, Fehler sind dann normal.
  useEffect(() => {
    if (!watching) return undefined;
    const id = setInterval(async () => {
      try {
        const r = await api.get("/admin/update");
        setSt(r);
        setError("");
        if (r.job.state === "done") { setWatching(false); setTimeout(() => window.location.reload(), 1500); }
        if (r.job.state === "failed") setWatching(false);
      } catch {
        setError("");
      }
    }, 3000);
    return () => clearInterval(id);
  }, [watching]);

  async function check() {
    setChecking(true);
    await load(true);
    setChecking(false);
  }

  async function start() {
    if (!(await confirmDialog("Die Seite ist dabei ein bis zwei Minuten kurz nicht erreichbar. Deine Daten bleiben erhalten.", { title: "BikeHelper jetzt aktualisieren?", confirmLabel: "Aktualisieren", danger: false }))) return;
    try {
      await api.post("/admin/update", {});
      setError("");
      setWatching(true);
      setSt((s) => ({ ...s, job: { ...(s?.job || {}), state: "running", log: "", error: null } }));
    } catch (e) {
      setError(e.message);
    }
  }

  const v = st?.version;
  const job = st?.job;
  const busy = watching || job?.state === "running" || job?.state === "restarting";
  return (
    <section className="panel">
      <h2>Updates</h2>
      {v && <p>Installierte Version: <strong>{v.commit}</strong> <span className="muted small">vom {fmtDate(v.date)}, {v.subject}</span></p>}
      {st?.dirty && <p className="error">Im Projektordner gibt es lokale Änderungen. Das Update bricht dann ab.</p>}
      {st?.check_error && <p className="error" role="alert">{st.check_error}</p>}
      {st?.behind === 0 && <p className="ok">BikeHelper ist auf dem neuesten Stand.</p>}
      {st?.behind > 0 && (
        <>
          <p><strong>{st.behind} {st.behind === 1 ? "neue Änderung" : "neue Änderungen"}</strong> verfügbar:</p>
          <ul className="log-list">{st.changes.map((c) => <li key={c}><span>{c}</span></li>)}</ul>
        </>
      )}
      {busy && <p role="status">{job?.state === "restarting" ? "Starte neu … die Seite lädt gleich von selbst." : "Update läuft … das dauert einige Minuten."}</p>}
      {job?.state === "failed" && <p className="error" role="alert">{job.error}</p>}
      {job?.state === "failed" && job.log && <details><summary className="small">Protokoll</summary><pre className="small" style={{ whiteSpace: "pre-wrap", overflow: "auto", maxHeight: 240 }}>{job.log}</pre></details>}
      {error && <p className="error" role="alert">{error}</p>}
      <div className="actions">
        <button className="btn" onClick={check} disabled={busy || checking}>{checking ? "Prüfe …" : "Nach Updates suchen"}</button>
        <button className="btn primary" onClick={start} disabled={busy || st?.behind === 0 || !st}>Jetzt aktualisieren</button>
      </div>
      <p className="muted small">Das Update sichert zuerst die Datenbank, holt die neue Version von GitHub und baut sie neu. Springt die neue Version nicht an, geht BikeHelper automatisch zur vorherigen zurück. Der Update-Dienst darf dafür Docker auf dem Server steuern, ist aber nur über diesen Bereich erreichbar.</p>
    </section>
  );
}

const ACCESS = [
  { key: "allow_registration", type: "bool", label: "Jeder darf sich selbst registrieren", hint: "Aus: nur mit Einladung. Das erste Konto ist immer erlaubt." },
  { key: "token_expire_days", type: "number", label: "Anmeldung gilt (Tage)", min: 1, max: 90 },
  { key: "trusted_proxies", type: "number", label: "Proxys vor dem Webserver", min: 0, max: 5, hint: "1 für den Nginx Proxy Manager, 0 ohne Proxy. Wichtig für die Login-Drosselung." },
];
const EMBED = [
  { key: "frame_ancestors", type: "text", wide: true, label: "Diese Seiten dürfen BikeHelper einbetten", placeholder: "https://ha.example.de http://192.168.1.20:8123",
    hint: "Zum Beispiel Home Assistant (Webseiten-Karte oder Seitenleiste). Trage jede Adresse ein, unter der du die Seite öffnest, mit Leerzeichen getrennt. Leer: Einbetten ist verboten (Schutz vor Klick-Tricks fremder Seiten)." },
];
const GENERAL = [
  { key: "public_url", type: "text", label: "Öffentliche Adresse", wide: true, placeholder: "https://bike.example.de", hint: "Wird für Links in Mails und für die Wahoo-Anmeldung genutzt." },
  { key: "timezone", type: "text", label: "Zeitzone", placeholder: "Europe/Berlin", hint: "Für Statistiken, Wochentage und Erinnerungszeiten." },
];
const EMAIL = [
  { key: "smtp_host", type: "text", label: "SMTP-Server", placeholder: "smtp.gmail.com" },
  { key: "smtp_port", type: "number", label: "Port", min: 1, max: 65535, hint: "587 (STARTTLS) oder 465 (verschlüsselt von Anfang an)." },
  { key: "smtp_user", type: "text", label: "Benutzername", hint: "Meist deine E-Mail-Adresse." },
  { key: "smtp_password", type: "text", secret: true, label: "Passwort", hint: "Bei Gmail ein App-Passwort, nicht das Login-Passwort." },
  { key: "smtp_from", type: "text", label: "Absenderadresse", hint: "Leer: der Benutzername." },
  { key: "smtp_starttls", type: "bool", label: "Verbindung mit STARTTLS verschlüsseln (Port 587)" },
];
const NOTIFY = [
  { key: "reminders_enabled", type: "bool", label: "Wartungserinnerungen senden" },
  { key: "ntfy_server", type: "text", label: "ntfy-Server für Push-Nachrichten", wide: true, placeholder: "https://ntfy.sh" },
];
const FEATURES = [
  { key: "weather_enabled", type: "bool", label: "Wetter pro Fahrt holen", hint: "Sendet gerundete Startkoordinaten an Open-Meteo." },
  { key: "geo_enabled", type: "bool", label: "Orte und Länder zuordnen", hint: "Sendet Kachelmittelpunkte an OpenStreetMap (Nominatim)." },
  { key: "wahoo_enabled", type: "bool", label: "Wahoo-Import anbieten" },
  { key: "intervals_enabled", type: "bool", label: "intervals.icu-Import anbieten" },
];
const MAPS = [
  { key: "carto_api_key", type: "text", secret: true, label: "CARTO-Schlüssel (dunkle Karte)", hint: "Kostenlos bei carto.com/basemaps/apikey. Leer: helle OpenStreetMap-Karte." },
  { key: "map_tile_url", type: "text", label: "Eigene Kachel-URL", wide: true, placeholder: "https://…/{z}/{x}/{y}.png", hint: "Hat Vorrang vor CARTO." },
  { key: "map_tile_dark", type: "bool", label: "Eigene Kacheln sind dunkel" },
];

function Health() {
  const [h, setH] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => { api.get("/admin/health").then(setH).catch((e) => setError(e.message)); }, []);
  if (error) return <section className="panel"><h2>Zustand</h2><p className="error" role="alert">{error}</p></section>;
  if (!h) return <Loading rows={1} />;
  const up = h.uptime_s;
  return (
    <section className="panel">
      <h2>Zustand</h2>
      <ul className="log-list">
        {h.checks.map((c) => (
          <li key={c.key}>
            <span>{c.label}</span>
            <span><span className={`pill ${c.ok ? "pill-ok" : "pill-due"}`}>{c.ok ? "In Ordnung" : "Prüfen"}</span> <span className="muted small">{c.text}</span></span>
          </li>
        ))}
        <li><span>Konten</span><span className="muted small">{h.users}</span></li>
        {h.db_bytes != null && <li><span>Größe der Datenbank</span><span className="muted small">{(h.db_bytes / 1e6).toFixed(1)} MB</span></li>}
        <li><span>Läuft seit</span><span className="muted small">{up >= 86400 ? `${Math.floor(up / 86400)} Tagen` : up >= 3600 ? `${Math.floor(up / 3600)} Stunden` : `${Math.max(1, Math.floor(up / 60))} Minuten`}</span></li>
      </ul>
    </section>
  );
}

function Backups() {
  const [items, setItems] = useState(null);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => api.get("/admin/backups").then((r) => { setItems(r.items); setError(""); }).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  async function create() {
    setBusy(true);
    try {
      const r = await api.post("/admin/backups", {});
      toast(`Gesichert: ${r.name}`);
      await load();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>Sicherungen</h2>
      <p className="muted small">
        Eine Sicherung enthält die Daten aller Konten. Sie liegt deshalb nur im Ordner <code>backups</code> auf dem Server und lässt sich hier nicht herunterladen.
        Vor jedem Update entsteht automatisch eine. Die letzten 14 bleiben erhalten. Zurückspielen: <code>./install.sh restore backups/DATEI</code>.
      </p>
      <div className="actions"><button className="btn" onClick={create} disabled={busy}>{busy ? "Sichere …" : "Jetzt sichern"}</button></div>
      {error && <p className="error" role="alert">{error}</p>}
      {items?.length === 0 && <p className="muted small">Noch keine Sicherung.</p>}
      {items?.length > 0 && (
        <ul className="log-list">
          {items.slice(0, 8).map((b) => (
            <li key={b.name}><span>{fmtDateTime(b.at)}</span><span className="muted small">{(b.bytes / 1e6).toFixed(1)} MB, {b.name}</span></li>
          ))}
        </ul>
      )}
    </section>
  );
}

const ACTION_TEXT = {
  login: "Angemeldet", "login.fail": "Anmeldung fehlgeschlagen", "login.blocked": "Anmeldung abgelehnt",
  act: "Aktion", error: "Serverfehler", "server.start": "Server gestartet",
  password: "Passwort geändert", "logout.all": "Überall abgemeldet", "account.delete": "Konto selbst gelöscht", export: "Datenexport",
  "invite.create": "Einladung erstellt", "invite.delete": "Einladung gelöscht", "user.role": "Rolle geändert",
  "user.lock": "Konto gesperrt", "user.unlock": "Konto entsperrt", "user.delete": "Konto gelöscht",
  "user.register": "Konto angelegt", "settings.save": "Einstellungen gespeichert", "update.start": "Update gestartet",
  "backup.create": "Sicherung erstellt", "password.reset": "Passwort zurückgesetzt",
};

// Gruppen für den Filter: Anmeldungen, Aktionen der Nutzer, Verwaltung durch Admins, Fehler und Systemereignisse
function kindOf(action) {
  if (action.startsWith("login")) return "login";
  if (action === "error") return "error";
  if (action === "server.start") return "system";
  if (["act", "password", "logout.all", "account.delete", "export"].includes(action)) return "action";
  return "admin";
}
const KIND_TEXT = { login: "Anmeldungen", action: "Aktionen", admin: "Verwaltung", error: "Fehler", system: "System" };
const KIND_PILL = { login: "pill-ok", action: "pill-muted", admin: "pill-soon", error: "pill-due", system: "pill-muted" };

function timeText(iso) {
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + "Z");
  const sameDay = d.toDateString() === new Date().toDateString();
  return sameDay ? d.toLocaleTimeString("de-DE") : d.toLocaleString("de-DE", { dateStyle: "short", timeStyle: "medium" });
}

function AuditLog() {
  const [rows, setRows] = useState(null);
  const [error, setError] = useState("");
  const [live, setLive] = useState(true);
  const [filter, setFilter] = useState("all");
  const [fresh, setFresh] = useState(new Set());
  const top = useRef(0);

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const after = top.current;
        const r = await api.get(`/admin/audit?limit=${after ? 100 : 300}&after=${after}`);
        if (stop) return;
        setError("");
        if (r.length) {
          top.current = Math.max(top.current, ...r.map((x) => x.id));
          setRows((prev) => [...r, ...(prev || [])].slice(0, 500));
          if (after) {
            setFresh(new Set(r.map((x) => x.id)));
            setTimeout(() => setFresh(new Set()), 2500);
          }
        } else if (!after) {
          setRows([]);
        }
      } catch (e) {
        if (!stop) setError(e.message);
      }
    }
    tick();
    const id = live ? setInterval(tick, 4000) : null;
    return () => { stop = true; if (id) clearInterval(id); };
  }, [live]);

  const shown = rows?.filter((r) => filter === "all" || kindOf(r.action) === filter);

  return (
    <section className="panel">
      <div className="log-head">
        <h2>Ereignisprotokoll</h2>
        <label className="check live-switch">
          <input type="checkbox" checked={live} onChange={(e) => setLive(e.target.checked)} />
          <span>{live ? <><span className="live-dot" aria-hidden="true" /> Live</> : "Live aus"}</span>
        </label>
      </div>
      <p className="muted small">
        Wer sich wann angemeldet hat, was grob getan wurde und was auf dem Server passiert. Aus Datenschutzgründen steht hier nur, <em>in welchem Bereich</em> etwas passiert ist
        (zum Beispiel „Lager: gelöscht“), nie ein Name, eine Zahl, ein Passwort oder eine IP-Adresse. Einträge bleiben 30 Tage.
      </p>
      <div className="seg" role="group" aria-label="Filter">
        {[["all", "Alle"], ...Object.entries(KIND_TEXT)].map(([k, label]) => (
          <button key={k} type="button" className={`btn small ${filter === k ? "primary" : ""}`} aria-pressed={filter === k} onClick={() => setFilter(k)}>{label}</button>
        ))}
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {!rows && !error && <Loading rows={2} />}
      {shown?.length === 0 && <p className="muted small">Keine Einträge in dieser Ansicht.</p>}
      {shown?.length > 0 && (
        <ul className="event-list" aria-live={live ? "polite" : "off"}>
          {shown.map((r) => {
            const kind = kindOf(r.action);
            return (
              <li key={r.id} className={fresh.has(r.id) ? "fresh" : ""}>
                <span className="muted small ev-time">{timeText(r.at)}</span>
                <span className={`pill ${KIND_PILL[kind]}`}>{ACTION_TEXT[r.action] || r.action}</span>
                <span className="ev-who">{r.actor}</span>
                {r.detail && <span className="muted small">{r.detail}</span>}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}

const TABS = [["overview", "Übersicht"], ["accounts", "Konten"], ["server", "Server"], ["log", "Live-Protokoll"]];

export default function Admin({ user }) {
  const [params, setParams] = useSearchParams();
  const tab = TABS.some(([k]) => k === params.get("tab")) ? params.get("tab") : "overview";
  const [data, setData] = useState(null);
  const [error, setError] = useState("");
  const [testMsg, setTestMsg] = useState("");
  const [testErr, setTestErr] = useState("");

  const load = useCallback(() => api.get("/admin/settings").then(setData).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const save = async (values) => {
    const r = await api.put("/admin/settings", { values });
    setData(r);
  };

  async function testEmail() {
    setTestMsg("");
    setTestErr("");
    try {
      const r = await api.post("/admin/settings/test-email", {});
      setTestMsg(`Testmail an ${r.to} gesendet.`);
    } catch (err) {
      setTestErr(err.message);
    }
  }

  if (user.role !== "admin") return <p className="error">Dieser Bereich ist nur für Administratoren.</p>;

  const defs = data?.fields;
  const block = (props) => <SettingsBlock {...props} defs={defs} onSaved={save} />;

  return (
    <>
      <header className="page-head"><h1>Administration</h1></header>
      <p className="muted lead">Alles, was früher in Dateien auf dem Server stand, stellst du hier ein. Persönliche Daten anderer Nutzer sind für dich nicht einsehbar.</p>
      {error && <p className="error" role="alert">{error}</p>}

      <div className="tabs" role="tablist" aria-label="Bereiche der Administration">
        {TABS.map(([k, label]) => (
          <button key={k} role="tab" aria-selected={tab === k} className={`tab ${tab === k ? "on" : ""}`} onClick={() => setParams(k === "overview" ? {} : { tab: k })}>{label}</button>
        ))}
      </div>
      {tab === "overview" && <><Health /><Updates /><Backups /></>}
      {tab === "accounts" && <><Accounts me={user} /><Invites /></>}
      {tab === "log" && <AuditLog />}
      {tab === "server" && (!defs ? <Loading /> : (
        <>
          {block({ title: "Zugang", intro: "Wer sich anmelden darf und wie lange Anmeldungen gelten.", spec: ACCESS })}
          {block({ title: "In andere Seiten einbetten", intro: <>So zeigst du BikeHelper zum Beispiel in Home Assistant an: Dort eine <strong>Webseiten-Karte</strong> oder unter Einstellungen → Dashboards einen <strong>Webseiten-Eintrag</strong> mit der Adresse <code>{window.location.origin}</code> anlegen und die Adresse von Home Assistant hier eintragen. Die Änderung wirkt sofort. Im eingebetteten Fenster meldest du dich beim ersten Mal einmal an.</>, spec: EMBED })}
          {block({ title: "Adresse und Zeit", spec: GENERAL })}
          {block({
            title: "E-Mail-Versand",
            intro: data.smtp_ready
              ? "E-Mail ist eingerichtet. Die Testmail geht an deine eigene Adresse."
              : "Noch nicht eingerichtet: Ohne Server und Absender können Nutzer keine Erinnerungen per E-Mail erhalten.",
            spec: EMAIL,
            extra: (
              <>
                <button type="button" className="btn" onClick={testEmail}>Testmail an mich senden</button>
                <span className="hint">Speichere zuerst, die Testmail nutzt die gespeicherten Werte.</span>
                {testMsg && <span className="ok" role="status">{testMsg}</span>}
                {testErr && <span className="error" role="alert">{testErr}</span>}
              </>
            ),
          })}
          {block({ title: "Erinnerungen und Push", spec: NOTIFY })}
          {block({ title: "Funktionen", intro: "Diese Dienste verbinden sich mit externen Anbietern. Schalte aus, was du nicht nutzen willst.", spec: FEATURES })}
          {block({ title: "Karten", spec: MAPS })}
        </>
      ))}
    </>
  );
}
