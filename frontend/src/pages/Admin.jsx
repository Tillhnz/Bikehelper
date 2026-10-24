import { useCallback, useEffect, useState } from "react";
import { api, fmtDate } from "../api.js";

const ROLE_TEXT = { admin: "Administrator", user: "Nutzer" };

/** Ein Block mit Einstellungsfeldern, der gemeinsam gespeichert wird. */
function SettingsBlock({ title, intro, fields, defs, spec, onSaved, extra }) {
  const initial = () =>
    Object.fromEntries(spec.map((f) => [f.key, f.secret ? "" : defs[f.key]?.value ?? (f.type === "bool" ? false : "")]));
  const [form, setForm] = useState(initial);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => { setForm(initial()); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [defs]);

  async function save(e) {
    e.preventDefault();
    setBusy(true);
    setMsg("");
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
      setMsg("Gespeichert. Die Änderung gilt sofort.");
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
                <button type="button" className="link small" onClick={() => onSaved({ [f.key]: "" }).then(() => setMsg(`${f.label} gelöscht.`)).catch((er) => setError(er.message))}>
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
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Accounts({ me }) {
  const [users, setUsers] = useState([]);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const load = useCallback(() => api.get("/admin/users").then(setUsers).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const run = async (fn, done) => {
    setError("");
    setMsg("");
    try { await fn(); if (done) setMsg(done); await load(); } catch (err) { setError(err.message); }
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
                  onClick={() => { if (window.confirm(`Konto ${u.email} samt allen Daten löschen? Das lässt sich nicht rückgängig machen.`)) run(() => api.del(`/admin/users/${u.id}`), "Konto gelöscht."); }}
                >
                  Löschen
                </button>
              </span>
            )}
          </li>
        ))}
      </ul>
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function Invites() {
  const [invites, setInvites] = useState(null);
  const [error, setError] = useState("");
  const [msg, setMsg] = useState("");
  const load = useCallback(() => api.get("/admin/invites").then(setInvites).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);
  const run = async (fn, done) => {
    setError("");
    setMsg("");
    try { await fn(); if (done) setMsg(done); await load(); } catch (err) { setError(err.message); }
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
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

const ACCESS = [
  { key: "allow_registration", type: "bool", label: "Jeder darf sich selbst registrieren", hint: "Aus: nur mit Einladung. Das erste Konto ist immer erlaubt." },
  { key: "token_expire_days", type: "number", label: "Anmeldung gilt (Tage)", min: 1, max: 90 },
  { key: "trusted_proxies", type: "number", label: "Proxys vor dem Webserver", min: 0, max: 5, hint: "1 für den Nginx Proxy Manager, 0 ohne Proxy. Wichtig für die Login-Drosselung." },
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
];
const MAPS = [
  { key: "carto_api_key", type: "text", secret: true, label: "CARTO-Schlüssel (dunkle Karte)", hint: "Kostenlos bei carto.com/basemaps/apikey. Leer: helle OpenStreetMap-Karte." },
  { key: "map_tile_url", type: "text", label: "Eigene Kachel-URL", wide: true, placeholder: "https://…/{z}/{x}/{y}.png", hint: "Hat Vorrang vor CARTO." },
  { key: "map_tile_dark", type: "bool", label: "Eigene Kacheln sind dunkel" },
];

export default function Admin({ user }) {
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

      <Accounts me={user} />
      <Invites />
      {!defs ? <p className="muted">Lade …</p> : (
        <>
          {block({ title: "Zugang", intro: "Wer sich anmelden darf und wie lange Anmeldungen gelten.", spec: ACCESS })}
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
      )}
    </>
  );
}
