import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api.js";
import QuickDone from "./QuickDone.jsx";
import { StatusPill } from "./ui.jsx";

/** Zeigt nach einer Fahrt, was am Rad bald oder jetzt fällig ist, und lässt es direkt abhaken. */
export default function AfterRide({ bikeId }) {
  const [items, setItems] = useState([]);
  const load = useCallback(() => {
    api.get("/maintenance/overview").then((r) => setItems(r.items.filter((i) => i.bike_id === bikeId))).catch(() => {});
  }, [bikeId]);
  useEffect(() => { if (bikeId) load(); }, [bikeId, load]);
  if (!bikeId || items.length === 0) return null;
  return (
    <section className="panel after-ride">
      <h2>Am Rad zu tun</h2>
      <ul className="maint-list">
        {items.map((i) => (
          <li key={`${i.component_id}-${i.rule}`}>
            <div>
              <Link to={`/bikes/${i.bike_id}`}>{i.rule}</Link>
              <span className="muted small">{i.component}</span>
            </div>
            <span className="maint-actions"><StatusPill status={i.status} /><QuickDone item={i} onDone={load} /></span>
          </li>
        ))}
      </ul>
    </section>
  );
}
