import { useState } from "react";
import { api } from "../api.js";
import { toast } from "./feedback.jsx";

/** Meldung auf der Startseite: jemand möchte als Mechaniker auf die eigenen Räder zugreifen. */
export default function MechanicRequests({ items }) {
  const [gone, setGone] = useState([]);
  const [busy, setBusy] = useState(false);
  const visible = (items || []).filter((r) => !gone.includes(r.id));
  if (visible.length === 0) return null;

  async function decide(r, accept) {
    setBusy(true);
    try {
      await api.post(`/mechanic/requests/${r.id}/${accept ? "accept" : "decline"}`, {});
      setGone((g) => [...g, r.id]);
      toast(accept ? `${r.email} darf jetzt deine Räder bearbeiten.` : "Anfrage abgelehnt.");
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mech-requests" role="region" aria-label="Zugriffsanfragen">
      {visible.map((r) => (
        <div key={r.id} className="notice-card">
          <div>
            <strong>{r.email}</strong> möchte als Mechaniker auf deine Räder zugreifen.
            <p className="muted small">Erlaubt sind Ansehen und Bearbeiten von Rädern, Komponenten, Wartung und Reifen. Fahrten, Lager, Ziele und Einstellungen bleiben privat. Du kannst den Zugriff jederzeit in den Einstellungen entziehen.</p>
          </div>
          <div className="actions" style={{ marginTop: 0 }}>
            <button className="btn primary" disabled={busy} onClick={() => decide(r, true)}>Zulassen</button>
            <button className="btn" disabled={busy} onClick={() => decide(r, false)}>Ablehnen</button>
          </div>
        </div>
      ))}
    </div>
  );
}
