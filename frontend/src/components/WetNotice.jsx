import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

const KEY = "bikehelper-wet-dismissed";
const readDismissed = () => { try { return JSON.parse(localStorage.getItem(KEY) || "[]"); } catch { return []; } };
const writeDismissed = (ids) => { try { localStorage.setItem(KEY, JSON.stringify(ids.slice(-30))); } catch { /* privater Modus */ } };

const ADVICE = {
  oil: "Kette mit einem Lappen trocken wischen. Wirkt sie danach trocken oder schmutzig, neu schmieren.",
  wax: "Kette mit einem Lappen trocken wischen und abtrocknen lassen. Neu wachsen nur, wenn sie verschmutzt, rostig oder sehr nass geworden ist; Heißwachsen presst das Wasser auch aus den Gliedern.",
};

/** Hinweis nach einer nassen Fahrt. Verschwindet nach Ablauf (vom Server berechnet), mit „Verstanden“ oder sobald die Kette gepflegt ist. */
export default function WetNotice({ items }) {
  const [now, setNow] = useState(Date.now());
  const [dismissed, setDismissed] = useState(readDismissed);
  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(id);
  }, []);
  const visible = (items || []).filter((n) => now < new Date(n.expires_at).getTime() && !dismissed.includes(n.activity_id));
  if (visible.length === 0) return null;
  const hide = (id) => { const next = [...dismissed, id]; setDismissed(next); writeDismissed(next); };
  const clock = (iso) => new Date(iso).toLocaleTimeString("de-DE", { hour: "2-digit", minute: "2-digit" });
  return (
    <div className="wet-notices">
      {visible.map((n) => (
        <section key={n.activity_id} className="wet-notice" role="status">
          <svg viewBox="0 0 24 24" className="nav-icon wet-icon" aria-hidden="true" focusable="false"><path d="M12 3 C12 3 5 11 5 15 A7 7 0 0 0 19 15 C19 11 12 3 12 3 Z" /></svg>
          <div className="wet-body">
            <strong>Nasse Fahrt mit {n.bike_name}</strong>
            <p>{ADVICE[n.lube] || ADVICE.oil}</p>
            <p className="muted small">„{n.name}“ endete um {clock(n.ended_at)} Uhr, rund {n.wet_minutes} Minuten nass. Der Hinweis bleibt bis {clock(n.expires_at)} Uhr.</p>
            <div className="actions">
              <Link className="btn small" to={`/bikes/${n.bike_id}`}>Zum Rad</Link>
              <button className="btn small" onClick={() => hide(n.activity_id)}>Verstanden</button>
            </div>
          </div>
        </section>
      ))}
    </div>
  );
}
