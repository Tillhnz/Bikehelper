import { useState } from "react";
import { api } from "../api.js";

export default function Settings({ user, onChange }) {
  const [clientId, setClientId] = useState("");
  const [clientSecret, setClientSecret] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const callbackDomain = window.location.host;

  async function save(e) {
    e.preventDefault();
    setError("");
    setMessage("");
    try {
      onChange(await api.put("/settings/strava", { client_id: clientId, client_secret: clientSecret }));
      setClientSecret("");
      setMessage("Strava-Zugangsdaten gespeichert.");
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <>
      <header className="page-head"><h1>Einstellungen</h1></header>

      <section className="panel">
        <h2>Strava</h2>
        <p className="muted">
          Jeder Nutzer verbindet seine eigene Strava-API-App. So bleiben deine Zugangsdaten bei dir und
          es gibt keine gemeinsamen Limits.
        </p>
        <ol className="steps">
          <li>
            Öffne <a href="https://www.strava.com/settings/api" target="_blank" rel="noreferrer">strava.com/settings/api</a> und
            lege eine App an.
          </li>
          <li>
            Trage bei „Authorization Callback Domain“ diesen Wert ein: <code>{callbackDomain}</code>
          </li>
          <li>Kopiere Client-ID und Client-Secret hierher.</li>
        </ol>

        <form className="form-grid" onSubmit={save}>
          <label>
            Client-ID
            <input value={clientId} onChange={(e) => setClientId(e.target.value)} inputMode="numeric" required />
          </label>
          <label>
            Client-Secret
            <input type="password" value={clientSecret} onChange={(e) => setClientSecret(e.target.value)} autoComplete="off" required />
          </label>
          {error && <p className="error span-all" role="alert">{error}</p>}
          {message && <p className="ok span-all" role="status">{message}</p>}
          <div className="actions span-all">
            <button className="btn primary">Zugangsdaten speichern</button>
          </div>
        </form>

        <p className="small">
          Status:{" "}
          {user.strava_connected
            ? <span className="pill pill-ok">Mit Strava verbunden</span>
            : user.strava_configured
              ? <span className="pill pill-soon">Zugangsdaten gespeichert, Verbindung folgt</span>
              : <span className="pill pill-muted">Nicht eingerichtet</span>}
        </p>
        <p className="muted small">Die Verbindung mit Strava und der Import deiner Fahrten kommen im nächsten Schritt.</p>
      </section>
    </>
  );
}
