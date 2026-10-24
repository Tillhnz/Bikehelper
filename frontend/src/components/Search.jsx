import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

const GROUPS = [["rides", "Fahrten"], ["bikes", "Räder"], ["components", "Teile am Rad"], ["inventory", "Lager"]];

/** Globale Suche über Fahrten, Räder, Teile und Lager. Öffnet mit dem Knopf oder der Taste „/“. */
export default function Search() {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [res, setRes] = useState(null);
  const [error, setError] = useState("");
  const input = useRef(null);
  const navigate = useNavigate();

  useEffect(() => {
    function onKey(e) {
      const typing = /^(INPUT|TEXTAREA|SELECT)$/.test(document.activeElement?.tagName) || document.activeElement?.isContentEditable;
      if (e.key === "/" && !typing && !e.ctrlKey && !e.metaKey) { e.preventDefault(); setOpen(true); }
      if (e.key === "Escape") setOpen(false);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => { if (open) setTimeout(() => input.current?.focus(), 0); else { setQ(""); setRes(null); setError(""); } }, [open]);

  useEffect(() => {
    if (q.trim().length < 2) { setRes(null); return undefined; }
    let live = true;
    const t = setTimeout(() => {
      api.get(`/search?q=${encodeURIComponent(q.trim())}`).then((r) => { if (live) { setRes(r); setError(""); } }).catch((e) => { if (live) setError(e.message); });
    }, 250);
    return () => { live = false; clearTimeout(t); };
  }, [q]);

  function go(to) { setOpen(false); navigate(to); }
  const total = res ? GROUPS.reduce((n, [k]) => n + res[k].length, 0) : 0;

  return (
    <>
      <button className="search-btn" onClick={() => setOpen(true)} aria-label="Suche öffnen" title="Suche (Taste /)">
        <svg viewBox="0 0 24 24" className="nav-icon" aria-hidden="true" focusable="false"><path d="M10.5 18 A7.5 7.5 0 1 0 10.5 3 A7.5 7.5 0 0 0 10.5 18 M16 16 L21 21" /></svg>
        <span className="search-label">Suche</span>
      </button>
      {open && (
        <div className="modal-back search-back" onMouseDown={(e) => { if (e.target === e.currentTarget) setOpen(false); }}>
          <div className="modal search-modal" role="dialog" aria-modal="true" aria-label="Suche">
            <input ref={input} type="search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Fahrten, Räder, Teile, Lager durchsuchen" aria-label="Suchbegriff" autoComplete="off" />
            {error && <p className="error" role="alert">{error}</p>}
            {q.trim().length >= 2 && res && total === 0 && <p className="muted">Nichts gefunden.</p>}
            {res && GROUPS.map(([k, label]) => res[k].length > 0 && (
              <div key={k} className="search-group">
                <h3>{label}</h3>
                <ul>
                  {res[k].map((r) => (
                    <li key={`${k}-${r.id}`}><button className="search-hit" onClick={() => go(r.to)}><strong>{r.title}</strong> <span className="muted small">{r.sub}</span></button></li>
                  ))}
                </ul>
              </div>
            ))}
            {q.trim().length < 2 && <p className="muted small">Mindestens zwei Zeichen eingeben. Mit Esc schließt du die Suche.</p>}
          </div>
        </div>
      )}
    </>
  );
}
