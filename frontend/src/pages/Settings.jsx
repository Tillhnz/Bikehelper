import { Link } from "react-router-dom";

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
