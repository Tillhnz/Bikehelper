import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, clearToken, setToken } from "../api.js";
import { loadMapConfig, resetMapConfig } from "../geo.js";

const PROVIDER_TEXT = {
  carto: "Dunkle CARTO-Karte (mit Schlüssel)",
  osm: "Helle OpenStreetMap-Karte (ohne Schlüssel)",
  custom: "Eigene Kachel-URL des Servers",
};

function ProfileSettings({ user, onChange }) {
  const [weight, setWeight] = useState(user.weight_kg ?? "");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function save(e) {
    e.preventDefault();
    setMsg("");
    setError("");
    try {
      const r = await api.put("/settings/profile", { weight_kg: weight === "" ? null : Number(weight) });
      onChange?.({ ...user, weight_kg: r.weight_kg });
      setMsg("Gespeichert.");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="panel">
      <h2>Profil</h2>
      <p className="muted">Dein Gewicht nutzt der Ratgeber für den Reifendruck. Es bleibt auf deinem Server.</p>
      <form className="inline-form" onSubmit={save}>
        <label>Körpergewicht (kg)<input type="number" min="30" max="250" step="0.5" value={weight} onChange={(e) => setWeight(e.target.value)} /></label>
        <button className="btn primary">Speichern</button>
      </form>
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function MapSettings() {
  const [st, setSt] = useState(null);
  const [key, setKey] = useState("");
  const [cfg, setCfg] = useState(null);
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      setSt(await api.get("/settings/map"));
      resetMapConfig();
      setCfg(await loadMapConfig(api));
    } catch (err) {
      setError(err.message);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  async function save(value, doneText) {
    setBusy(true);
    setError("");
    setMsg("");
    try {
      setSt(await api.put("/settings/map", { carto_api_key: value }));
      setKey("");
      resetMapConfig();
      setCfg(await loadMapConfig(api));
      setMsg(doneText);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  // Vorschaukachel (Mitteleuropa), an ihr erkennt man, ob der Schlüssel gilt: bei falschem Schlüssel erscheint ein Wasserzeichen
  const preview = cfg ? cfg.url.replace("{s}", cfg.subdomains[0]).replace("{z}", "5").replace("{x}", "16").replace("{y}", "10").replace("{r}", "") : null;

  if (!st) return <section className="panel"><h2>Karten</h2>{error ? <p className="error" role="alert">{error}</p> : <p className="muted">Lade …</p>}</section>;

  return (
    <section className="panel">
      <h2>Karten</h2>
      <p>
        Aktiv: <strong>{PROVIDER_TEXT[st.provider] ?? st.provider}</strong>
        {st.has_user_key && <span className="muted"> · dein Schlüssel endet auf {st.key_hint}</span>}
        {!st.has_user_key && st.server_has_key && st.provider === "carto" && <span className="muted"> · Schlüssel des Servers</span>}
      </p>
      {st.server_custom_url ? (
        <p className="muted">Der Server nutzt eine eigene Kachel-URL aus der Konfiguration. Ein Schlüssel hier ändert daran nichts.</p>
      ) : (
        <>
          <p className="muted">
            Die dunkle Karte stammt von CARTO und braucht einen kostenlosen Schlüssel. Ohne ihn zeigt CARTO ein Wasserzeichen,
            BikeHelper nimmt dann stattdessen die helle OpenStreetMap-Karte. Den Schlüssel gibt es ohne Konto auf{" "}
            <a href="https://carto.com/basemaps/apikey/" target="_blank" rel="noreferrer">carto.com/basemaps/apikey</a>,
            er kommt per E-Mail und gilt für private Projekte bis 5 Millionen Kartenabrufe im Monat.
          </p>
          <form className="inline-form" onSubmit={(e) => { e.preventDefault(); save(key.trim(), "Schlüssel gespeichert."); }}>
            <label className="grow">
              CARTO-Schlüssel
              <input
                value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" spellCheck={false}
                placeholder={st.has_user_key ? "Neuen Schlüssel einfügen, um ihn zu ersetzen" : "Schlüssel aus der E-Mail einfügen"}
              />
            </label>
            <button className="btn primary" disabled={!key.trim() || busy}>Speichern</button>
            {st.has_user_key && (
              <button type="button" className="btn" disabled={busy} onClick={() => save("", "Schlüssel entfernt.")}>Entfernen</button>
            )}
          </form>
        </>
      )}
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
      {preview && (
        <div className="map-preview">
          <img src={preview} alt="Vorschau des Kartenhintergrunds" width="256" height="256" />
          <span className="muted small">
            Vorschau. Steht darin „API KEY REQUIRED“ oder ein Wasserzeichen, gilt der Schlüssel nicht.
          </span>
        </div>
      )}
    </section>
  );
}

function NotifySettings() {
  const [st, setSt] = useState(null);
  const [email, setEmail] = useState(false);
  const [topic, setTopic] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api.get("/settings/notifications").then((r) => { setSt(r); setEmail(r.email); setTopic(r.ntfy_topic); }).catch((e) => setError(e.message));
  }, []);

  async function run(fn, done) {
    setMsg(""); setError(""); setBusy(true);
    try { await fn(); setMsg(done); } catch (err) { setError(err.message); } finally { setBusy(false); }
  }

  const save = (e) => {
    e.preventDefault();
    return run(async () => setSt(await api.put("/settings/notifications", { email, ntfy_topic: topic })), "Gespeichert.");
  };
  const test = () => run(() => api.post("/settings/notifications/test"), "Testnachricht gesendet. Prüfe dein Postfach und dein Handy.");
  const randomTopic = () => {
    const a = new Uint8Array(9);
    crypto.getRandomValues(a);
    setTopic("bikehelper-" + Array.from(a, (b) => b.toString(36).padStart(2, "0")).join("").slice(0, 14));
  };

  if (!st) return <section className="panel"><h2>Erinnerungen</h2>{error ? <p className="error" role="alert">{error}</p> : <p className="muted">Lade …</p>}</section>;

  return (
    <section className="panel">
      <h2>Erinnerungen</h2>
      <p className="muted">
        BikeHelper meldet sich, sobald eine Wartung bald oder fällig ist. Jede Fälligkeit kommt nur einmal, tagsüber zwischen 8 und 21 Uhr.
      </p>
      <form className="notify-form" onSubmit={save}>
        <label className="check">
          <input type="checkbox" checked={email} disabled={!st.smtp_available} onChange={(e) => setEmail(e.target.checked)} />
          <span>Per E-Mail an dich senden</span>
        </label>
        {!st.smtp_available && <p className="hint">Dafür muss auf dem Server ein E-Mail-Versand eingerichtet sein (SMTP_HOST in der .env).</p>}
        <label>
          Push aufs Handy mit ntfy, Thema
          <span className="topic-row">
            <input value={topic} onChange={(e) => setTopic(e.target.value)} placeholder="z. B. bikehelper-k3j9x2" autoCapitalize="none" />
            <button type="button" className="btn small" onClick={randomTopic}>Zufälliges Thema</button>
          </span>
        </label>
        <p className="hint">
          Installiere die kostenlose App ntfy auf dem Handy und abonniere dort dasselbe Thema (Server {st.ntfy_server}).
          Wer das Thema kennt, kann mitlesen, nimm also ein zufälliges.
        </p>
        <div className="actions">
          <button className="btn primary" disabled={busy}>Speichern</button>
          <button type="button" className="btn" disabled={busy} onClick={test}>Testnachricht senden</button>
        </div>
      </form>
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

function InstallSettings() {
  const [prompt, setPrompt] = useState(null);
  const [installed, setInstalled] = useState(false);
  const standalone = typeof window !== "undefined" && (window.matchMedia?.("(display-mode: standalone)").matches || window.navigator.standalone);
  const ios = typeof navigator !== "undefined" && /iphone|ipad|ipod/i.test(navigator.userAgent);

  useEffect(() => {
    const onPrompt = (e) => { e.preventDefault(); setPrompt(e); };
    const onInstalled = () => setInstalled(true);
    window.addEventListener("beforeinstallprompt", onPrompt);
    window.addEventListener("appinstalled", onInstalled);
    return () => {
      window.removeEventListener("beforeinstallprompt", onPrompt);
      window.removeEventListener("appinstalled", onInstalled);
    };
  }, []);

  async function install() {
    prompt.prompt();
    await prompt.userChoice;
    setPrompt(null);
  }

  return (
    <section className="panel">
      <h2>Als App installieren</h2>
      {standalone || installed ? (
        <p className="ok">BikeHelper läuft schon als App.</p>
      ) : prompt ? (
        <>
          <p className="muted">BikeHelper bekommt ein eigenes Symbol und öffnet ohne Browserleiste.</p>
          <div className="actions"><button className="btn primary" onClick={install}>App installieren</button></div>
        </>
      ) : ios ? (
        <p className="muted">Tippe in Safari auf Teilen und dann auf „Zum Home-Bildschirm“.</p>
      ) : (
        <p className="muted">
          Öffne das Browsermenü und wähle „App installieren“ oder „Zum Startbildschirm hinzufügen“. Das geht nur über eine
          https-Adresse, also über deinen Reverse Proxy.
        </p>
      )}
    </section>
  );
}

function SecuritySettings({ user }) {
  const [pw, setPw] = useState({ current: "", next: "" });
  const [del, setDel] = useState({ open: false, password: "" });
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function run(fn, done) {
    setMsg("");
    setError("");
    try {
      await fn();
      if (done) setMsg(done);
    } catch (err) {
      setError(err.message);
    }
  }

  const changePassword = (e) => {
    e.preventDefault();
    return run(async () => {
      const r = await api.put("/auth/password", { current_password: pw.current, new_password: pw.next });
      setToken(r.access_token);
      setPw({ current: "", next: "" });
    }, "Passwort geändert. Auf allen anderen Geräten bist du jetzt abgemeldet.");
  };

  const logoutAll = () =>
    run(async () => {
      const r = await api.post("/auth/logout-all", {});
      setToken(r.access_token);
    }, "Alle anderen Geräte sind abgemeldet. Dieses Gerät bleibt angemeldet.");

  const deleteAccount = (e) => {
    e.preventDefault();
    return run(async () => {
      await api.post("/me/delete", { password: del.password });
      clearToken();
      window.location.assign("/");
    });
  };

  return (
    <section className="panel">
      <h2>Sicherheit</h2>
      <form className="inline-form" onSubmit={changePassword}>
        <label>Aktuelles Passwort<input type="password" autoComplete="current-password" value={pw.current} onChange={(e) => setPw({ ...pw, current: e.target.value })} required /></label>
        <label>Neues Passwort<input type="password" autoComplete="new-password" minLength={8} value={pw.next} onChange={(e) => setPw({ ...pw, next: e.target.value })} required /></label>
        <button className="btn primary">Passwort ändern</button>
      </form>
      <p className="muted small">Anmeldungen laufen nach 7 Tagen ab. Wenn du ein Gerät verloren hast, melde alle anderen ab:</p>
      <div className="actions">
        <button className="btn" onClick={logoutAll}>Überall abmelden</button>
      </div>
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}

      <h3>Konto löschen</h3>
      <p className="muted small">
        Entfernt {user.email} samt Rädern, Komponenten, Wartungen, Fahrten, Inventar und Zielen vom Server. Das lässt sich nicht rückgängig machen.
      </p>
      {!del.open ? (
        <div className="actions"><button className="btn danger" onClick={() => setDel({ open: true, password: "" })}>Konto löschen …</button></div>
      ) : (
        <form className="inline-form" onSubmit={deleteAccount}>
          <label>Passwort zur Bestätigung<input type="password" autoComplete="current-password" value={del.password} onChange={(e) => setDel({ ...del, password: e.target.value })} required /></label>
          <button className="btn danger">Konto endgültig löschen</button>
          <button type="button" className="btn" onClick={() => setDel({ open: false, password: "" })}>Abbrechen</button>
        </form>
      )}
    </section>
  );
}

function AdminSettings() {
  const [invites, setInvites] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => api.get("/admin/invites").then(setInvites).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  const run = async (fn) => {
    setError("");
    try { await fn(); await load(); } catch (err) { setError(err.message); }
  };

  return (
    <section className="panel">
      <h2>Einladungen</h2>
      <p className="muted small">
        Du bist Administrator. Wenn die offene Registrierung ausgeschaltet ist (ALLOW_REGISTRATION=false), können sich neue Nutzer nur mit einem Einladungscode anmelden. Jeder Code gilt einmal.
      </p>
      <div className="actions">
        <button className="btn primary" onClick={() => run(() => api.post("/admin/invites", {}))}>Neuen Code erzeugen</button>
      </div>
      {invites?.length > 0 && (
        <ul className="log-list">
          {invites.map((i) => (
            <li key={i.id}>
              <span><strong>{i.code}</strong> <span className="muted">{i.used_by_email ? `verwendet von ${i.used_by_email}` : "offen"}</span></span>
              <button className="link small danger" onClick={() => run(() => api.del(`/admin/invites/${i.id}`))}>Löschen</button>
            </li>
          ))}
        </ul>
      )}
      {error && <p className="error" role="alert">{error}</p>}
    </section>
  );
}

export default function Settings({ user, onChange }) {
  return (
    <>
      <header className="page-head"><h1>Einstellungen</h1></header>

      <section className="panel">
        <h2>Konto</h2>
        <p>
          Angemeldet als <strong>{user.email}</strong>
        </p>
      </section>

      <ProfileSettings user={user} onChange={onChange} />

      <NotifySettings />

      <InstallSettings />

      <MapSettings />

      <SecuritySettings user={user} />

      {user.is_admin && <AdminSettings />}

      <section className="panel">
        <h2>Strava</h2>
        <p className="muted">
          Eine direkte Strava-Anbindung ist derzeit nicht eingerichtet, weil Strava dafür ein Abo verlangt.
          Importiere stattdessen deinen kostenlosen Datenexport oder die Fahrtdateien deines Radcomputers.
        </p>
        <div className="actions">
          <Link className="btn primary" to="/rides">Zu den Fahrten</Link>
        </div>
      </section>
    </>
  );
}
