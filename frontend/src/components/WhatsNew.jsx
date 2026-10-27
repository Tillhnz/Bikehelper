import { useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import { api, fmtDate } from "../api.js";

/** Einmaliger Hinweis nach einem Update: zeigt beim ersten Anmelden danach, was sich seit der letzten gesehenen Version geändert hat. */
export default function WhatsNew({ user, onClose }) {
  const navigate = useNavigate();
  const okRef = useRef(null);
  const entries = Array.isArray(user.whatsnew) ? user.whatsnew : [];
  useEffect(() => { if (entries.length) okRef.current?.focus(); }, [entries.length]);
  if (!entries.length) return null;

  async function close(to) {
    onClose();  // sofort schließen, das Speichern darf im Hintergrund laufen
    try { await api.post("/me/whatsnew/seen", {}); } catch { /* beim nächsten Start erneut */ }
    if (to) navigate(to);
  }

  const action = entries.find((e) => e.action)?.action;
  return (
    <div className="modal-back" onMouseDown={(e) => { if (e.target === e.currentTarget) close(); }}>
      <div className="modal whatsnew" role="dialog" aria-modal="true" aria-labelledby="wn-title" onKeyDown={(e) => { if (e.key === "Escape") close(); }}>
        <h3 id="wn-title">BikeHelper wurde aktualisiert</h3>
        <div className="wn-scroll">
          {entries.map((e) => (
            <section key={e.id} className="wn-entry">
              <h4>{e.title} <span className="muted small">Version {e.id}{e.date ? `, ${fmtDate(e.date)}` : ""}</span></h4>
              <ul>{e.changes.map((c) => <li key={c}>{c}</li>)}</ul>
            </section>
          ))}
        </div>
        <div className="actions">
          {action ? (
            <>
              <button className="btn" onClick={() => close()}>Später</button>
              <button ref={okRef} className="btn primary" onClick={() => close(action.to)}>{action.label}</button>
            </>
          ) : (
            <button ref={okRef} className="btn primary" onClick={() => close()}>Verstanden</button>
          )}
        </div>
      </div>
    </div>
  );
}
