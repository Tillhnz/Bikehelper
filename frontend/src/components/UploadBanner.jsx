import { Link, useLocation } from "react-router-dom";
import { dismiss, isBusy, useUploads } from "../uploads.js";

function Row({ k, t, title }) {
  if (t.phase === "idle") return null;
  const busy = isBusy(t);
  const pct = t.phase === "uploading" ? Math.round(t.pct * 100) : t.job && t.job.total ? Math.round((t.job.processed / t.job.total) * 100) : 0;
  const n = t.result?.imported;
  return (
    <div className={`upload-banner ${t.phase === "error" ? "is-error" : t.phase === "done" ? "is-done" : ""}`} role="status">
      <div className="upload-banner-main">
        <strong>{title}</strong>
        {busy && (
          <span className="muted small">
            {t.phase === "uploading" ? `Wird hochgeladen · ${pct} %` : t.job?.total ? `Fahrt ${t.job.processed} von ${t.job.total}` : "Wird verarbeitet …"}
          </span>
        )}
        {t.phase === "done" && <span>Fertig: {n} {n === 1 ? "Fahrt" : "Fahrten"} importiert.</span>}
        {t.phase === "error" && <span className="error">{t.error}</span>}
      </div>
      {busy && <div className="progress banner-progress"><div className="progress-bar" style={{ width: `${pct}%` }} /></div>}
      {!busy && (
        <div className="actions" style={{ margin: 0 }}>
          <Link className="btn small" to="/rides" onClick={() => dismiss(k)}>Zu den Fahrten</Link>
          <button className="link small" onClick={() => dismiss(k)}>Schließen</button>
        </div>
      )}
    </div>
  );
}

/** Zeigt laufende und fertige Uploads auf jeder Seite, damit man sie nicht aus den Augen verliert. */
export default function UploadBanner() {
  const { strava, files } = useUploads();
  const { pathname } = useLocation();
  // Auf der Fahrten-Seite steht der Fortschritt ohnehin direkt im Formular
  if (pathname === "/rides") return null;
  return (
    <div className="upload-banners">
      <Row k="strava" t={strava} title="Strava-Export" />
      <Row k="files" t={files} title="Fahrtdateien" />
    </div>
  );
}
