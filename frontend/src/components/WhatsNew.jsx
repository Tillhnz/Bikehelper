import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

/** Einmaliger Hinweis nach der Anmeldung: Was ist neu? Wird pro Konto nur einmal gezeigt. */
export default function WhatsNew({ user, onClose }) {
  const navigate = useNavigate();
  const okRef = useRef(null);
  useEffect(() => { okRef.current?.focus(); }, []);
  if (user.whatsnew !== "intervals-2026-10") return null;

  async function close(goToSettings) {
    onClose();  // sofort schließen, das Speichern darf im Hintergrund laufen
    try { await api.post("/me/whatsnew/seen", {}); } catch { /* beim nächsten Start erneut */ }
    if (goToSettings) navigate("/settings#intervals");
  }

  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) close(false); }}>
      <div className="modal whatsnew" role="dialog" aria-modal="true" aria-labelledby="wn-title" onKeyDown={(e) => { if (e.key === "Escape") close(false); }}>
        <h3 id="wn-title">Neu: Fahrten aus intervals.icu</h3>
        <p>
          BikeHelper kann jetzt neue Fahrten automatisch aus <strong>intervals.icu</strong> abholen. Dorthin synchronisieren
          unter anderem Garmin Connect, Wahoo, Zwift, Polar und Suunto. So kommen auch Garmin-Fahrten ohne Strava in die App.
        </p>
        <p>
          <strong>Verbinde in intervals.icu nicht Strava, sondern direkt deinen Radcomputer</strong> (Wahoo, Garmin oder Hammerhead).
          Strava gibt Aktivitäten nicht über die Schnittstelle weiter, solche Fahrten kann BikeHelper deshalb nicht abholen.
        </p>
        <p className="muted small">Du brauchst nur deinen persönlichen API-Schlüssel von intervals.icu.</p>
        <div className="actions">
          <button className="btn" onClick={() => close(false)}>Später</button>
          <button ref={okRef} className="btn primary" onClick={() => close(true)}>Jetzt einrichten</button>
        </div>
      </div>
    </div>
  );
}
