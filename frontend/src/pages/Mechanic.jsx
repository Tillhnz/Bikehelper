import { useCallback, useEffect, useState } from "react";
import { api } from "../api.js";
import { EmptyState } from "../components/ui.jsx";
import { Loading, confirmDialog, toast } from "../components/feedback.jsx";
import { BikeCard } from "./Garage.jsx";

/** Werkstatt (Mechanics-Modus): eigene Räder und die Räder von Partnern, die den Zugriff erlaubt haben. */
export default function Mechanic() {
  const [groups, setGroups] = useState(null);
  const [state, setState] = useState(null);
  const [email, setEmail] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    try {
      const [g, s] = await Promise.all([api.get("/mechanic/bikes"), api.get("/mechanic/state")]);
      setGroups(g);
      setState(s);
    } catch (e) {
      setError(e.message);
    }
  }, []);
  useEffect(() => { load(); }, [load]);

  async function send(e) {
    e.preventDefault();
    setBusy(true);
    try {
      const r = await api.post("/mechanic/requests", { email: email.trim() });
      toast(r.message);
      setEmail("");
      await load();
    } catch (err) {
      toast(err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function leave(p) {
    const text = p.status === "active" ? `Zugriff auf die Räder von ${p.email} wirklich zurückgeben?` : `Anfrage an ${p.email} zurückziehen?`;
    if (!await confirmDialog(text)) return;
    try {
      await api.del(`/mechanic/grants/${p.id}`);
      await load();
    } catch (err) {
      toast(err.message, "error");
    }
  }

  if (error) return <p className="error" role="alert">{error}</p>;
  if (!groups || !state) return <Loading />;

  return (
    <>
      <header className="page-head">
        <h1>Werkstatt</h1>
        <p className="muted">Deine Räder und die Räder deiner Partner an einem Ort. Bei Partnerrädern darfst du Teile, Wartung und Reifen eintragen und ändern.</p>
      </header>

      {groups.map((g) => (
        <section key={g.owner} className="panel">
          <h2>{g.own ? "Meine Räder" : `Räder von ${g.owner}`}</h2>
          {g.bikes.length === 0 ? <p className="muted">Keine aktiven Räder.</p> : (
            <div className="bike-grid">{g.bikes.map((b, i) => <BikeCard key={b.id} bike={b} index={i} />)}</div>
          )}
        </section>
      ))}
      {groups.length === 1 && state.partners.length === 0 && (
        <EmptyState title="Noch keine Partner" text="Frage den Zugriff mit der E-Mail-Adresse des Partner-Kontos an. Er bestätigt die Anfrage auf seiner Startseite." />
      )}

      <section className="panel">
        <h2>Zugriff anfragen</h2>
        <form className="inline-form" onSubmit={send}>
          <label className="grow">E-Mail-Adresse des Partner-Kontos
            <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} required placeholder="partner@example.com" />
          </label>
          <button className="btn primary" disabled={busy}>Anfrage senden</button>
        </form>
        {state.partners.length > 0 && (
          <ul className="log-list">
            {state.partners.map((p) => (
              <li key={p.id}>
                <span><strong>{p.email}</strong> <span className="muted">{p.status === "active" ? "Zugriff erteilt" : "wartet auf Bestätigung"}</span></span>
                <button className="link small danger" onClick={() => leave(p)}>{p.status === "active" ? "Zurückgeben" : "Zurückziehen"}</button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
