import { useEffect, useState } from "react";
import { api } from "../api.js";

let cache = null; // Katalog einmal pro Sitzung laden
function loadChecks() {
  if (!cache) cache = api.get("/catalog").then((c) => c.checks || {}).catch(() => { cache = null; return {}; });
  return cache;
}

/** Aufklappbare Anleitung zur Sichtprüfung: wie man prüft, was gut und was schlecht ist und was dann zu tun ist. */
export default function CheckGuide({ category }) {
  const [checks, setChecks] = useState(null);
  useEffect(() => { loadChecks().then(setChecks); }, []);
  const key = category.startsWith("tire") ? "tires" : category;
  const c = checks?.[key];
  if (!c) return null;
  return (
    <details className="howto check-guide">
      <summary>Sichtprüfung: so geht es</summary>
      <p className="muted small"><strong>Du brauchst:</strong> {c.tools}</p>
      <h4>So prüfst du</h4>
      <ol>{c.how.map((t) => <li key={t}>{t}</li>)}</ol>
      <div className="check-cols">
        <div className="check-good">
          <h4>Gut</h4>
          <ul>{c.good.map((t) => <li key={t}>{t}</li>)}</ul>
        </div>
        <div className="check-bad">
          <h4>Schlecht</h4>
          <ul>{c.bad.map((t) => <li key={t}>{t}</li>)}</ul>
        </div>
      </div>
      <p className="check-act"><strong>Dann:</strong> {c.act}</p>
    </details>
  );
}
