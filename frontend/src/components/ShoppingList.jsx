import { useEffect, useState } from "react";
import { CATEGORIES, api, safeUrl, today } from "../api.js";
import { toast } from "./feedback.jsx";

const REPLACE = /wechsel|tausch|erneuer|ersetz/i;

/** Einkaufsliste: was bald oder jetzt gewechselt werden muss, abgeglichen mit dem Lager. Zum Kopieren oder Drucken. */
export default function ShoppingList({ onClose }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    Promise.all([api.get("/maintenance/overview"), api.get("/inventory")])
      .then(([o, inv]) => setData({ items: o.items, stock: inv.items }))
      .catch((e) => setError(e.message));
  }, []);

  if (error) return <section className="panel"><p className="error" role="alert">{error}</p></section>;
  if (!data) return null;

  const buy = [], care = [];
  for (const i of data.items) {
    const stock = data.stock
      .filter((s) => s.category === i.category && (s.bike_id == null || s.bike_id === i.bike_id) && s.quantity > 0)
      .reduce((n, s) => n + s.quantity, 0);
    (REPLACE.test(i.rule) ? buy : care).push({ ...i, stock });
  }

  const lineBuy = (i) => `- ${CATEGORIES[i.category] ?? i.component}${i.bike ? ` für ${i.bike}` : ""} (${i.component}, ${i.status === "due" ? "fällig" : "bald fällig"})${i.stock ? `, ${i.stock}x auf Lager` : ""}${safeUrl(i.shop_url) ? ` – ${safeUrl(i.shop_url)}` : ""}`;
  const text = `Einkaufsliste ${new Date(today() + "T00:00:00").toLocaleDateString("de-DE")}\n\nTeile:\n${buy.filter((i) => !i.stock).map(lineBuy).join("\n") || "- nichts zu besorgen"}\n\n` +
    (buy.some((i) => i.stock) ? `Schon im Lager:\n${buy.filter((i) => i.stock).map(lineBuy).join("\n")}\n\n` : "") +
    (care.length ? `Pflege und Prüfung:\n${care.map((i) => `- ${i.rule}: ${i.component}${i.bike ? ` (${i.bike})` : ""}`).join("\n")}\n` : "");

  async function copy() {
    try { await navigator.clipboard.writeText(text); toast("Liste kopiert."); } catch { toast("Kopieren ist hier nicht möglich.", "error"); }
  }

  return (
    <section className="panel print-area">
      <h2>Einkaufsliste</h2>
      {data.items.length === 0 ? <p className="ok">Nichts steht an, es gibt nichts zu besorgen.</p> : (
        <>
          <h3>Teile besorgen</h3>
          {buy.filter((i) => !i.stock).length === 0 ? <p className="muted">Alles Nötige ist im Lager oder es steht kein Wechsel an.</p> : (
            <ul className="shop-list">{buy.filter((i) => !i.stock).map((i) => (
              <li key={`${i.component_id}-${i.rule}`}><span className="box" aria-hidden="true" /> <strong>{CATEGORIES[i.category] ?? i.component}</strong>{i.bike ? ` für ${i.bike}` : ""} <span className="muted small">({i.component}, {i.status === "due" ? "fällig" : "bald fällig"})</span>{safeUrl(i.shop_url) && <> <a className="no-print" href={safeUrl(i.shop_url)} target="_blank" rel="noopener noreferrer">Kaufen</a></>}</li>
            ))}</ul>
          )}
          {buy.some((i) => i.stock) && (
            <>
              <h3>Schon im Lager</h3>
              <ul className="shop-list">{buy.filter((i) => i.stock).map((i) => (
                <li key={`${i.component_id}-${i.rule}`}><strong>{CATEGORIES[i.category] ?? i.component}</strong>{i.bike ? ` für ${i.bike}` : ""} <span className="muted small">{i.stock}x vorhanden</span></li>
              ))}</ul>
            </>
          )}
          {care.length > 0 && (
            <>
              <h3>Pflege und Prüfung</h3>
              <ul className="shop-list">{care.map((i) => (
                <li key={`${i.component_id}-${i.rule}`}>{i.rule}: {i.component}{i.bike ? ` (${i.bike})` : ""}</li>
              ))}</ul>
            </>
          )}
        </>
      )}
      <div className="actions no-print">
        <button className="btn" onClick={copy}>Kopieren</button>
        <button className="btn" onClick={() => window.print()}>Drucken</button>
        <button className="btn" onClick={onClose}>Schließen</button>
      </div>
    </section>
  );
}
