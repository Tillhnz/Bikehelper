export function Kpi({ value, unit, label, extra }) {
  return (
    <div className="kpi">
      <div className="kpi-value">{value}{unit && <small>{unit}</small>}</div>
      <div className="kpi-label">{label}</div>
      {extra}
    </div>
  );
}

export function Panel({ title, sub, children, className = "" }) {
  return (
    <section className={`panel ${className}`}>
      <h2>{title}</h2>
      {sub && <p className="muted small">{sub}</p>}
      {children}
    </section>
  );
}
