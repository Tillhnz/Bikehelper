import { useState } from "react";
import { api, today } from "../api.js";
import { toast } from "./feedback.jsx";

/** Knopf „Erledigt“: trägt eine Wartung mit heutigem Datum ein. Prüfungen brauchen ein Ergebnis und gehen deshalb zum Rad. */
export default function QuickDone({ item, onDone }) {
  const [busy, setBusy] = useState(false);
  if (!item.rule_id || item.is_inspection) return null;
  async function done() {
    setBusy(true);
    try {
      await api.post(`/rules/${item.rule_id}/done`, { performed_at: today() });
      toast(`${item.rule} ist eingetragen.`);
      onDone?.();
    } catch (e) {
      toast(e.message, "error");
    } finally {
      setBusy(false);
    }
  }
  return (
    <button className="btn small" onClick={done} disabled={busy} aria-label={`${item.rule} heute als erledigt eintragen`}>
      {busy ? "…" : "Erledigt"}
    </button>
  );
}
