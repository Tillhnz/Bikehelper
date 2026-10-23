import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import { loadMapConfig, resetMapConfig } from "../geo.js";

const PROVIDER_TEXT = {
  carto: "Dunkle CARTO-Karte (mit Schlüssel)",
  osm: "Helle OpenStreetMap-Karte (ohne Schlüssel)",
  custom: "Eigene Kachel-URL des Servers",
};

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

export default function Settings({ user }) {
  return (
    <>
      <header className="page-head"><h1>Einstellungen</h1></header>

      <section className="panel">
        <h2>Konto</h2>
        <p>
          Angemeldet als <strong>{user.email}</strong>
        </p>
      </section>

      <MapSettings />

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
