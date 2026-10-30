import { useEffect, useState } from "react";
import { STATUS_LABEL } from "../api.js";

function Digit({ value, order }) {
  // Startet auf 0 und rollt nach dem ersten Zeichnen auf die Zielziffer
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const id = requestAnimationFrame(() => setShown(value));
    return () => cancelAnimationFrame(id);
  }, [value]);
  return (
    <span className="odo-digit" aria-hidden="true">
      <span className="odo-strip" style={{ "--d": shown, "--n": order }}>
        {Array.from({ length: 10 }, (_, n) => <span key={n}>{n}</span>)}
      </span>
    </span>
  );
}

/** Kilometerzähler im Odometer-Stil: jede Ziffer rollt wie ein mechanisches Zählwerk. */
export function Odometer({ km, size = "lg" }) {
  const digits = String(Math.round(km ?? 0)).padStart(5, "0").split("");
  return (
    <div className={`odo odo-${size}`} aria-label={`${Math.round(km ?? 0)} Kilometer`} role="img">
      {digits.map((d, i) => (
        <Digit key={i} value={Number(d)} order={i} />
      ))}
      <span className="odo-unit">km</span>
    </div>
  );
}

/** Verschleißanzeige wie ein Messlineal: 20 Striche, gefüllt nach Anteil des Intervalls. */
export function Gauge({ progress = 0, status = "ok", mark = null, markDue = false }) {
  const ticks = 20;
  const filled = Math.min(ticks, Math.round(Math.min(progress, 1) * ticks));
  return (
    <div
      className={`gauge gauge-${status}`}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(progress * 100)}
      aria-label="Verbrauchtes Wartungsintervall"
    >
      {Array.from({ length: ticks }, (_, i) => (
        <span key={i} className={i < filled ? "tick on" : "tick"} style={{ "--i": i }} />
      ))}
      {mark != null && <i className={`gauge-mark ${markDue ? "due" : ""}`} style={{ left: `${Math.min(1, Math.max(0, mark)) * 100}%` }} title="Nächste Sichtprüfung" />}
    </div>
  );
}

export function StatusPill({ status }) {
  return <span className={`pill pill-${status}`}>{STATUS_LABEL[status]}</span>;
}

export function EmptyState({ title, text, children }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {text && <p className="muted">{text}</p>}
      {children}
    </div>
  );
}
