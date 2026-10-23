import { STATUS_LABEL } from "../api.js";

/** Kilometerzähler im Odometer-Stil: jede Ziffer in eigener Kachel. */
export function Odometer({ km, size = "lg" }) {
  const digits = String(Math.round(km ?? 0)).padStart(5, "0").split("");
  return (
    <div className={`odo odo-${size}`} aria-label={`${Math.round(km ?? 0)} Kilometer`} role="img">
      {digits.map((d, i) => (
        <span key={i} className="odo-digit">{d}</span>
      ))}
      <span className="odo-unit">km</span>
    </div>
  );
}

/** Verschleißanzeige wie ein Messlineal: 20 Striche, gefüllt nach Anteil des Intervalls. */
export function Gauge({ progress = 0, status = "ok" }) {
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
        <span key={i} className={i < filled ? "tick on" : "tick"} />
      ))}
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
