import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api.js";

const STEPS = [
  { title: "Willkommen bei BikeHelper", to: "/", text: "BikeHelper merkt sich, wie viele Kilometer jedes deiner Räder und jedes Teil daran gefahren sind, und sagt dir, wann Wartung ansteht. Dieser Rundgang zeigt dir in etwa zwei Minuten, wo was ist. Du kannst jederzeit überspringen und ihn später in den Einstellungen wiederholen." },
  { title: "Garage: deine Räder", to: "/garage", nav: "/garage", text: "Hier legst du deine Räder an, mit Typ, Marke, Kaufdatum und Kilometerstand. Beim Anlegen kann BikeHelper gleich die üblichen Komponenten wie Kette, Kassette und Bremsbeläge mit passenden Wartungsregeln mitanlegen. Eine Kachel öffnet das Rad." },
  { title: "Komponenten und Wartung", to: "/garage", nav: "/garage", text: "In jedem Rad siehst du die Komponenten mit ihrem Zustand, trägst Wartungen und Sichtprüfungen ein und bekommst Hinweise, was fällig ist. Wichtig: Gib bei Teilen das Einbaudatum an, denn ohne Datum kann BikeHelper keine Kilometer rechnen. Auch Reifensätze mit Restkilometern findest du dort." },
  { title: "Fahrten importieren", to: "/rides", nav: "/rides", text: "Die Kilometer kommen aus deinen Fahrten. Du kannst deinen Strava-Export importieren (kein Abo nötig), GPX-, FIT- und TCX-Dateien hochladen oder intervals.icu in den Einstellungen verbinden (dort hängt dein Radcomputer von Wahoo, Garmin oder Hammerhead dran), dann kommen neue Fahrten von selbst. Fahrten ohne Rad ordnest du hier zu, BikeHelper macht dir Vorschläge." },
  { title: "Start: das steht an", to: "/", nav: "/", text: "Die Startseite zeigt, was als Nächstes ansteht, deine Woche, Jahresziele und Hinweise, etwa zur Kettenpflege nach einer nassen Fahrt. Wartung, die fällig wird, erscheint hier zuerst." },
  { title: "Ratgeber", to: "/advisor", nav: "/advisor", text: "Der Ratgeber rechnet dir den Reifendruck für Gewicht, Reifen und Untergrund aus, schlägt Kleidung fürs Wetter vor und zeigt das Wetter während deiner Tour." },
  { title: "Statistik und Heatmap", to: "/stats", nav: "/stats", text: "Die Statistik zeigt Übersicht, Belastung, Jahresrückblick, Ziele, Vergleiche und besuchte Orte. Im Tab „Heatmap“ siehst du alle gefahrenen Strecken auf der Karte, mit erkundeten Kacheln und einem Zeitverlauf." },
  { title: "Gruppen", to: "/groups", nav: "/groups", text: "Mit Freunden kannst du eine Gruppe gründen und dich in Ranglisten für Woche, Monat und Jahr vergleichen. Geteilt werden nur Kennzahlen, keine Strecken. Eingeladen wird per E-Mail oder Link." },
  { title: "Einstellungen", to: "/settings", nav: "/settings", text: "Hier richtest du Erinnerungen per E-Mail oder ntfy ein, verbindest intervals.icu, aktivierst den Mechanics-Modus für eine Werkstatt mit Zugriff auf Partnerräder, wählst Hell oder Dunkel und exportierst deine Daten. Den Rundgang startest du hier auch wieder." },
  { title: "So fängst du am besten an", to: "/", last: true, text: "Diese drei Schritte reichen für den Anfang:", todo: [
    ["1. Rad anlegen", "/garage"], ["2. Fahrten importieren", "/rides"], ["3. Erinnerungen einrichten", "/settings"],
  ] },
];

/** Geführter Rundgang für neue Konten: springt von Seite zu Seite, hebt den passenden Menüpunkt hervor. */
export default function Tour({ onClose }) {
  const navigate = useNavigate();
  const [i, setI] = useState(0);
  const nextRef = useRef(null);
  const step = STEPS[i];

  // Der erste Schritt bleibt auf der aktuellen Seite (zum Beispiel einer Gruppeneinladung); danach springt der Rundgang mit
  useEffect(() => { if (i > 0) navigate(step.to); }, [i]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (!step.nav) return undefined;
    const el = document.querySelector(`.sidebar nav a[href="${step.nav}"]`);
    el?.classList.add("tour-hl");
    el?.scrollIntoView?.({ block: "nearest" });
    return () => el?.classList.remove("tour-hl");
  }, [step.nav]);

  useEffect(() => { nextRef.current?.focus(); }, [i]);

  async function finish(to) {
    onClose();
    try { await api.post("/me/tour/done", {}); } catch { /* beim nächsten Start erneut */ }
    if (to) navigate(to);
  }

  return (
    <div className="tour-card" role="dialog" aria-labelledby="tour-title" aria-live="polite" onKeyDown={(e) => { if (e.key === "Escape") finish(); }}>
      <p className="muted small tour-count">Schritt {i + 1} von {STEPS.length}</p>
      <h3 id="tour-title">{step.title}</h3>
      <p>{step.text}</p>
      {step.todo && (
        <ul className="tour-todo">
          {step.todo.map(([label, to]) => <li key={to}><button className="link" onClick={() => finish(to)}>{label}</button></li>)}
        </ul>
      )}
      <div className="tour-dots" aria-hidden="true">{STEPS.map((s, k) => <i key={s.title} className={k === i ? "on" : ""} />)}</div>
      <div className="actions">
        {step.last ? null : <button className="link" onClick={() => finish()}>Überspringen</button>}
        {i > 0 && <button className="btn" onClick={() => setI(i - 1)}>Zurück</button>}
        {step.last
          ? <button ref={nextRef} className="btn primary" onClick={() => finish()}>Rundgang beenden</button>
          : <button ref={nextRef} className="btn primary" onClick={() => setI(i + 1)}>Weiter</button>}
      </div>
    </div>
  );
}
