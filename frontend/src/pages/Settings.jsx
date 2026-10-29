import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, clearToken, download, fmtDateTime, setToken } from "../api.js";
import { Loading, confirmDialog, toast } from "../components/feedback.jsx";
import { getTheme, setTheme } from "../theme.js";

function ProfileSettings({ user, onChange }) {
  const [weight, setWeight] = useState(user.weight_kg ?? "");
  const [maxHr, setMaxHr] = useState(user.max_hr ?? "");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");

  async function save(e) {
    e.preventDefault();
    setMsg("");
    setError("");
    try {
      const r = await api.put("/settings/profile", { weight_kg: weight === "" ? null : Number(weight), max_hr: maxHr === "" ? null : Number(maxHr) });
      onChange?.({ ...user, weight_kg: r.weight_kg, max_hr: r.max_hr });
      setMsg("Gespeichert.");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <section className="panel">
      <h2>Profil</h2>
      <p className="muted">Deine Werte bleiben auf deinem Server.</p>
      <form className="inline-form" onSubmit={save}>
        <label>Körpergewicht (kg)<input type="number" min="30" max="250" step="0.5" value={weight} onChange={(e) => setWeight(e.target.value)} /></label>
        <label>Maximalpuls (bpm)<input type="number" min="120" max="230" step="1" value={maxHr} onChange={(e) => setMaxHr(e.target.value)} placeholder="automatisch" /></label>
        <button className="btn primary">Speichern</button>
      </form>
      <p className="muted small">Gewicht für Reifendruck und Watt pro Kilo, Maximalpuls für die Pulszonen. Ohne Maximalpuls nimmt BikeHelper den höchsten Wert deiner Fahrten.</p>
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
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

  if (!st) return <section className="panel"><h2>Erinnerungen</h2>{error ? <p className="error" role="alert">{error}</p> : <Loading />}</section>;

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
        {!st.smtp_available && <p className="hint">Der Administrator hat den E-Mail-Versand noch nicht eingerichtet.</p>}
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

function IntervalsSettings() {
  const [st, setSt] = useState(null);
  const [bikes, setBikes] = useState([]);
  const [key, setKey] = useState("");
  const [msg, setMsg] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => api.get("/settings/intervals").then(setSt).catch((e) => setError(e.message)), []);
  useEffect(() => {
    load();
    api.get("/bikes").then(setBikes).catch(() => {});
  }, [load]);
  useEffect(() => {  // Link aus dem Neuigkeiten-Hinweis: hierher scrollen
    if (st && window.location.hash === "#intervals") document.getElementById("intervals")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }, [st]);
  useEffect(() => {
    if (!st?.running) return undefined;
    const t = setInterval(load, 4000);
    return () => clearInterval(t);
  }, [st?.running, load]);

  async function run(fn, done) {
    setMsg("");
    setError("");
    setBusy(true);
    try {
      await fn();
      if (done) setMsg(done);
      await load();
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  }

  if (!st) return <section className="panel" id="intervals"><h2>intervals.icu</h2>{error ? <p className="error" role="alert">{error}</p> : <Loading />}</section>;
  if (!st.enabled) return null;

  return (
    <section className="panel" id="intervals">
      <h2>intervals.icu</h2>
      <p className="muted">
        Neue Fahrten werden alle 30 Minuten automatisch aus <a href="https://intervals.icu" target="_blank" rel="noopener noreferrer">intervals.icu</a> abgeholt.
        Dorthin synchronisieren Garmin Connect, Wahoo, Zwift, Polar, Suunto und weitere, so ist es auch der Weg für Garmin ohne Strava.
      </p>
      <details className="howto">
        <summary>So richtest du es ein</summary>
        <ol>
          <li>Bei intervals.icu anmelden und dort dein Garmin-, Wahoo- oder anderes Konto verbinden (Einstellungen → Verbindungen).</li>
          <li>Unter Einstellungen → Entwicklereinstellungen den persönlichen API-Schlüssel anzeigen oder erzeugen und kopieren.</li>
          <li>Hier einfügen und speichern. BikeHelper prüft den Schlüssel und startet den ersten Import.</li>
        </ol>
        <p className="muted small">
          Fahrten, die bei intervals.icu von Strava kommen, gibt intervals.icu nicht an andere Programme weiter; sie werden übersprungen. Dafür gibt es den Strava-Export.
          Der Schlüssel liegt wie die anderen Einstellungen in der Datenbank deines Servers und wird hier nie wieder angezeigt.
        </p>
      </details>
      <form className="inline-form" onSubmit={(e) => { e.preventDefault(); run(async () => { await api.put("/settings/intervals", { api_key: key.trim(), bike_id: st.bike_id }); setKey(""); }, "Verbunden. Der erste Import läuft."); }}>
        <label className="grow">API-Schlüssel
          <input type="password" value={key} onChange={(e) => setKey(e.target.value)} autoComplete="off" spellCheck={false}
            placeholder={st.connected ? `gespeichert (${st.key_hint}), zum Ersetzen neuen einfügen` : "Schlüssel von intervals.icu einfügen"} />
        </label>
        <button className="btn primary" disabled={!key.trim() || busy}>{st.connected ? "Ersetzen" : "Verbinden"}</button>
      </form>
      {st.connected && (
        <>
          <label className="block">
            Importierte Fahrten diesem Rad zuordnen
            <select value={st.bike_id ?? ""} onChange={(e) => run(() => api.put("/settings/intervals", { api_key: null, bike_id: e.target.value ? Number(e.target.value) : null }))}>
              <option value="">Nach dem Radnamen in intervals.icu, sonst später zuordnen</option>
              {bikes.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
            </select>
          </label>
          <div className="actions">
            <button className="btn primary" disabled={st.running} onClick={() => run(() => api.post("/intervals/sync", {}), "Import gestartet.")}>{st.running ? "Läuft …" : "Jetzt abholen"}</button>
            <button className="btn" disabled={st.running} onClick={() => run(() => api.post("/intervals/sync", { full: true }), "Neuer Abgleich gestartet.")}>Neu abgleichen</button>
            <button className="btn" onClick={() => run(() => api.del("/intervals/connection"), "Verbindung getrennt.")}>Trennen</button>
          </div>
          <p className="muted small">
            „Neu abgleichen“ prüft auch Fahrten noch einmal, die BikeHelper schon als vorhanden gemerkt hat, zum Beispiel nach dem Löschen einer Fahrt. Doppelte werden weiter erkannt.
          </p>
          <p className="muted small">
            {st.imported} Fahrten importiert{st.last_sync ? `, letzter Lauf ${fmtDateTime(st.last_sync)}` : ""}.{st.status ? ` ${st.status}.` : ""}
          </p>
        </>
      )}
      {msg && <p className="ok" role="status">{msg}</p>}
      {error && <p className="error" role="alert">{error}</p>}
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

function MechanicSettings({ user, onChange }) {
  const [st, setSt] = useState(null);
  const [error, setError] = useState("");
  const load = useCallback(() => api.get("/mechanic/state").then(setSt).catch((e) => setError(e.message)), []);
  useEffect(() => { load(); }, [load]);

  async function toggle(enabled) {
    try {
      await api.put("/mechanic/enabled", { enabled });
      onChange({ ...user, mechanic_enabled: enabled });
    } catch (e) {
      toast(e.message, "error");
    }
  }

  async function revoke(g) {
    const text = g.status === "active" ? `${g.email} den Zugriff auf deine Räder entziehen?` : `Anfrage von ${g.email} entfernen?`;
    if (!await confirmDialog(text)) return;
    try {
      await api.del(`/mechanic/grants/${g.id}`);
      await load();
    } catch (e) {
      toast(e.message, "error");
    }
  }

  return (
    <section className="panel">
      <h2>Mechanics-Modus</h2>
      <p className="muted">Mit dem Mechanics-Modus erscheint in der Garage der Bereich „Werkstatt“. Dort siehst und bearbeitest du die Räder von Partnern, die dir den Zugriff erlaubt haben.</p>
      <label className="check">
        <input type="checkbox" checked={!!user.mechanic_enabled} onChange={(e) => toggle(e.target.checked)} />
        Werkstatt in der Garage anzeigen
      </label>
      <h3>Wer auf meine Räder zugreifen darf</h3>
      {error && <p className="error" role="alert">{error}</p>}
      {!st ? <Loading /> : st.access_given.length === 0 ? <p className="muted">Niemand. Anfragen erscheinen auf deiner Startseite und werden erst nach deiner Bestätigung wirksam.</p> : (
        <ul className="log-list">
          {st.access_given.map((g) => (
            <li key={g.id}>
              <span><strong>{g.email}</strong> <span className="muted">{g.status === "active" ? "darf Räder, Teile, Wartung und Reifen bearbeiten" : "wartet auf deine Bestätigung"}</span></span>
              <button className="link small danger" onClick={() => revoke(g)}>{g.status === "active" ? "Zugriff entziehen" : "Entfernen"}</button>
            </li>
          ))}
        </ul>
      )}
      <p className="hint">Fahrten, Lager, Ziele, Orte und Einstellungen bleiben immer privat. Löschen kann nur du ein Rad.</p>
    </section>
  );
}

function TourSettings({ user, onChange }) {
  async function restart() {
    try {
      await api.post("/me/tour/restart", {});
      onChange({ ...user, tour: true });
    } catch (e) {
      toast(e.message, "error");
    }
  }
  return (
    <section className="panel">
      <h2>Rundgang</h2>
      <p className="muted">Eine kurze Führung durch BikeHelper: wo was zu finden ist und wie du am besten anfängst.</p>
      <button className="btn" onClick={restart}>Rundgang starten</button>
    </section>
  );
}

function ModeSettings({ user, onChange }) {
  const [busy, setBusy] = useState(false);
  const mode = user.ui_mode ?? "expert";
  async function pick(m) {
    if (m === mode) return;
    setBusy(true);
    try {
      const r = await api.put("/me/ui", { mode: m });
      onChange({ ...user, ui_mode: r.mode });
      toast(m === "expert" ? "Expertenmodus ist an." : "Einfacher Modus ist an.");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>Funktionsumfang</h2>
      <div className="seg" role="radiogroup" aria-label="Funktionsumfang">
        {[["simple", "Einfach"], ["expert", "Experte"]].map(([k, label]) => (
          <button key={k} type="button" role="radio" aria-checked={mode === k} className={`btn ${mode === k ? "primary" : ""}`} disabled={busy} onClick={() => pick(k)}>{label}</button>
        ))}
      </div>
      <p className="muted small">
        Einfach zeigt Garage, Wartung, Fahrten und die wichtigsten Statistiken. Experte blendet zusätzlich Belastung, Leistungsanalyse, Muster und Wetter,
        Vergleiche und das Gruppen-Duell ein sowie weitere Blöcke für die Startseite. Deine Daten und Einstellungen bleiben in beiden Modi gleich.
      </p>
      <p><Link to="/?customize=1" className="link">Startseite anpassen →</Link></p>
    </section>
  );
}

function AppearanceSettings() {
  const [mode, setMode] = useState(getTheme());
  function pick(m) { setMode(m); setTheme(m); }
  return (
    <section className="panel">
      <h2>Darstellung</h2>
      <div className="seg" role="radiogroup" aria-label="Farbschema">
        {[["auto", "Automatisch"], ["light", "Hell"], ["dark", "Dunkel"]].map(([k, label]) => (
          <button key={k} type="button" role="radio" aria-checked={mode === k} className={`btn ${mode === k ? "primary" : ""}`} onClick={() => pick(k)}>{label}</button>
        ))}
      </div>
      <p className="muted small">Automatisch folgt der Einstellung deines Geräts. Die Wahl gilt nur für diesen Browser.</p>
    </section>
  );
}

function DataSettings() {
  const [busy, setBusy] = useState(false);
  async function exportAll() {
    setBusy(true);
    try {
      await download("/me/export", "bikehelper-export.json");
      toast("Export heruntergeladen.");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel">
      <h2>Meine Daten</h2>
      <p className="muted">Lade alles herunter, was zu deinem Konto gehört: Räder, Teile, Wartungen, Reifen, Fahrten mit Strecke, Lager und Ziele. Passwörter und Zugangsschlüssel sind nicht enthalten.</p>
      <div className="actions"><button className="btn" onClick={exportAll} disabled={busy}>{busy ? "Bereite vor …" : "Alle Daten herunterladen"}</button></div>
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
      <ModeSettings user={user} onChange={onChange} />

      <AppearanceSettings />

      <MechanicSettings user={user} onChange={onChange} />
      <TourSettings user={user} onChange={onChange} />

      <NotifySettings />

      <InstallSettings />


      <IntervalsSettings />


      <DataSettings />

      <SecuritySettings user={user} />

      {user.role === "admin" && (
        <section className="panel">
          <h2>Administration</h2>
          <p className="muted">Server, E-Mail, Einladungen, Konten und Rollen stellst du im Admin-Bereich ein.</p>
          <div className="actions"><Link className="btn primary" to="/admin">Zur Administration</Link></div>
        </section>
      )}

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
