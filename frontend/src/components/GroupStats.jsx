import { useEffect, useState } from "react";
import { api, fmtDuration, fmtNum } from "../api.js";
import { Kpi, Panel } from "./statsui.jsx";

export const COLORS = ["var(--celeste)", "#f2b84b", "#ff6b6b", "#8fd16a", "#b48cf2", "#4aa8ff", "#e58bc1", "#9aa7b2", "#5fd0c0", "#d9a066"];
const MEDAL = ["🥇", "🥈", "🥉"];
const WD = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"];

export const METRICS = {
  km: { label: "Kilometer", short: "km", cell: (v) => `${fmtNum(v, 1)} km` },
  elev_m: { label: "Höhenmeter", short: "Hm", cell: (v) => `${fmtNum(v, 0)} m` },
  time_s: { label: "Fahrzeit", short: "Zeit", cell: (v) => fmtDuration(v) },
  rides: { label: "Fahrten", short: "Fahrten", cell: (v) => String(v) },
  avg_speed: { label: "Ø Tempo", short: "Tempo", cell: (v) => `${fmtNum(v, 1)} km/h` },
  longest_km: { label: "Längste Fahrt", short: "Längste", cell: (v) => `${fmtNum(v, 1)} km` },
  active_days: { label: "Aktive Tage", short: "Tage", cell: (v) => String(v) },
  rides_per_week: { label: "Fahrten pro Woche", short: "pro Woche", cell: (v) => fmtNum(v, 1) },
  improve_pct: { label: "Verbesserung", short: "Steigerung", cell: (v) => `${v > 0 ? "+" : ""}${fmtNum(v, 0)} %` },
};

/** Jedes Mitglied behält in allen Diagrammen seine Farbe (nach Konto-Nummer, nicht nach Rang). */
function colorMap(rows) {
  const ids = [...rows].sort((a, b) => a.user_id - b.user_id).map((r) => r.user_id);
  return (r) => COLORS[ids.indexOf(r.user_id) % COLORS.length];
}

const Dot = ({ color }) => <i className="gs-dot" style={{ background: color }} />;
const nameOf = (r) => `${r.display_name}${r.is_me ? " (du)" : ""}`;
const dash = <span className="muted" title="Wird nicht geteilt oder hat keine Werte">–</span>;

// ---------- Bausteine ----------

/** Siegerpodest für die Top 3 einer Kennzahl. */
function Podium({ rows, metric, color }) {
  const top = [...rows].filter((r) => r[metric] > 0).sort((a, b) => b[metric] - a[metric]).slice(0, 3);
  if (!top.length) return <p className="muted">Noch keine Werte in diesem Zeitraum.</p>;
  const order = [top[1], top[0], top[2]].filter(Boolean);
  const height = { 0: 120, 1: 88, 2: 64 };
  return (
    <div className="podium" role="img" aria-label={`Podest ${METRICS[metric].label}`}>
      {order.map((r) => {
        const rank = top.indexOf(r);
        return (
          <div key={r.user_id} className="podium-col">
            <div className="podium-name">{nameOf(r)}</div>
            <div className="podium-val">{METRICS[metric].cell(r[metric])}</div>
            <div className="podium-step" style={{ height: height[rank], background: color(r), "--i": rank }}><span>{MEDAL[rank]}</span></div>
          </div>
        );
      })}
    </div>
  );
}

/** Waagerechte Balken, ein Balken je Mitglied in seiner Farbe. get liefert den Wert (null = nicht geteilt). */
function MemberBars({ rows, color, get, fmt, sort = true, note }) {
  const items = rows.map((r) => ({ r, v: get(r) }));
  if (sort) items.sort((a, b) => (b.v ?? -Infinity) - (a.v ?? -Infinity));
  const vals = items.map((i) => i.v).filter((v) => v != null);
  const max = Math.max(1, ...vals.map(Math.abs));
  return (
    <>
      <ul className="hbars member-bars">
        {items.map(({ r, v }, i) => (
          <li key={r.user_id} style={{ "--i": i }}>
            <span className="hbar-label"><Dot color={color(r)} />{nameOf(r)}</span>
            <span className="hbar-track">{v != null && <span className="hbar-fill" style={{ width: `${(Math.abs(v) / max) * 100}%`, background: color(r), opacity: v < 0 ? 0.55 : 1 }} />}</span>
            <span className="hbar-val">{v == null ? dash : fmt(v)}</span>
          </li>
        ))}
      </ul>
      {note && <p className="muted small">{note}</p>}
    </>
  );
}

/** Gruppierte Säulen: je Beschriftung eine Säule pro Mitglied. */
function GroupedBars({ labels, series, unit = "", height = 210 }) {
  const [hover, setHover] = useState(null);
  const W = 640, padB = 26, padT = 18, padL = 8;
  const max = Math.max(1, ...series.flatMap((s) => s.values.map((v) => v || 0)));
  const gw = (W - padL) / labels.length;
  const h = height - padB - padT;
  const bw = Math.min(26, (gw * 0.8) / Math.max(1, series.length));
  return (
    <svg viewBox={`0 0 ${W} ${height}`} className="chart" role="img" aria-label="Säulendiagramm im Vergleich">
      {[0.5, 1].map((f) => <line key={f} x1="0" x2={W} y1={padT + h * (1 - f)} y2={padT + h * (1 - f)} className="chart-grid" />)}
      {labels.map((l, i) => {
        const x0 = padL + i * gw + (gw - bw * series.length) / 2;
        return (
          <g key={l} onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
            <rect x={padL + i * gw} y="0" width={gw} height={height} fill="transparent" />
            {series.map((s, k) => {
              const bh = ((s.values[i] || 0) / max) * h;
              return <rect key={s.name} className="bar-grow" style={{ "--i": i }} x={x0 + k * bw} y={padT + h - bh} width={bw - 1.5} height={Math.max(bh, s.values[i] > 0 ? 1 : 0)} rx="2" fill={s.color} opacity={hover === null || hover === i ? 1 : 0.4} />;
            })}
            <text x={padL + i * gw + gw / 2} y={height - 8} textAnchor="middle" className="chart-label">{l}</text>
          </g>
        );
      })}
      {hover !== null && (
        <text x={Math.min(Math.max(padL + hover * gw + gw / 2, 120), W - 120)} y="11" textAnchor="middle" className="chart-tip">
          {labels[hover]}: {series.filter((s) => s.values[hover]).map((s) => `${s.name} ${fmtNum(s.values[hover], 0)}${unit}`).join(" · ") || "keine Werte"}
        </text>
      )}
    </svg>
  );
}

const Legend = ({ rows, color }) => (
  <p className="small group-legend">{rows.map((r) => <span key={r.user_id}><i style={{ background: color(r) }} />{nameOf(r)}</span>)}</p>
);

/** Verlauf je Mitglied; die Punkte folgen dem gewählten Zeitraum, optional aufsummiert. */
function SeriesChart({ data, cumulative, color, rows }) {
  const { labels, members } = data;
  const byName = Object.fromEntries(rows.map((r) => [r.display_name, r]));
  if (!members.length || labels.length < 2) return <p className="muted small">Für „Gesamt“ braucht der Verlauf mindestens zwei Jahre.</p>;
  const lines = members.map((m) => ({ ...m, row: byName[m.display_name], v: cumulative ? m.km.reduce((acc, x) => [...acc, (acc[acc.length - 1] || 0) + x], []) : m.km }));
  const W = 640, H = 230, padL = 44, padB = 24, padT = 14, padR = 56;
  const max = Math.max(1, ...lines.flatMap((m) => m.v));
  const sx = (i) => padL + (i / (labels.length - 1)) * (W - padL - padR);
  const sy = (v) => padT + (1 - v / max) * (H - padT - padB);
  const every = Math.ceil(labels.length / 10);
  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="chart" role="img" aria-label={cumulative ? "Aufsummierte Kilometer je Mitglied" : "Kilometer je Mitglied im Zeitraum"}>
      {[0, 0.5, 1].map((f) => (
        <g key={f}>
          <line x1={padL} x2={W - padR} y1={sy(max * f)} y2={sy(max * f)} className="chart-grid" />
          <text x={padL - 6} y={sy(max * f) + 4} textAnchor="end" className="chart-label">{fmtNum(max * f, 0)}</text>
        </g>
      ))}
      {labels.map((l, i) => (i % every === 0 ? <text key={l + i} x={sx(i)} y={H - 6} textAnchor="middle" className="chart-label">{l}</text> : null))}
      {lines.map((m, k) => {
        const c = m.row ? color(m.row) : COLORS[k % COLORS.length];
        const d = m.v.map((v, i) => `${i ? "L" : "M"}${sx(i).toFixed(1)},${sy(v).toFixed(1)}`).join("");
        const last = m.v[m.v.length - 1];
        return (
          <g key={m.display_name}>
            <path d={d} fill="none" stroke={c} strokeWidth={m.is_me ? 3.2 : 2} strokeLinejoin="round" strokeLinecap="round" className="line-draw" pathLength="1" style={{ "--i": k }} />
            <circle cx={sx(m.v.length - 1)} cy={sy(last)} r="3.5" fill={c} />
            <text x={sx(m.v.length - 1) + 7} y={sy(last) + 4} className="chart-label" fill={c}>{fmtNum(last, 0)}</text>
          </g>
        );
      })}
    </svg>
  );
}

/** Netzdiagramm: jede Kennzahl relativ zum Besten der Gruppe (100 %). Zeigt Profile wie Kletterer oder Vielfahrer. */
function Radar({ rows, color }) {
  const axes = ["km", "elev_m", "avg_speed", "rides", "longest_km", "active_days"];
  const maxes = Object.fromEntries(axes.map((a) => [a, Math.max(0, ...rows.map((r) => r[a] || 0))]));
  const [focus, setFocus] = useState(null);
  const R = 105, cx = 170, cy = 140;
  const pt = (i, f) => {
    const ang = -Math.PI / 2 + (i * 2 * Math.PI) / axes.length;
    return [cx + Math.cos(ang) * R * f, cy + Math.sin(ang) * R * f];
  };
  return (
    <div>
      <svg viewBox="0 0 340 285" className="chart radar" role="img" aria-label="Profil der Mitglieder im Vergleich zum Besten der Gruppe">
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <polygon key={f} points={axes.map((_, i) => pt(i, f).join(",")).join(" ")} fill="none" className="chart-grid" />
        ))}
        {axes.map((a, i) => {
          const [x, y] = pt(i, 1);
          const [lx, ly] = pt(i, 1.2);
          return (
            <g key={a}>
              <line x1={cx} y1={cy} x2={x} y2={y} className="chart-grid" />
              <text x={lx} y={ly + 4} textAnchor="middle" className="chart-label">{METRICS[a].short}</text>
            </g>
          );
        })}
        {rows.map((r) => {
          const pts = axes.map((a, i) => pt(i, maxes[a] ? (r[a] || 0) / maxes[a] : 0).join(",")).join(" ");
          const on = focus === null || focus === r.user_id;
          return <polygon key={r.user_id} points={pts} fill={color(r)} fillOpacity={on ? 0.16 : 0.03} stroke={color(r)} strokeWidth={r.is_me ? 3 : 1.8} strokeOpacity={on ? 1 : 0.25} />;
        })}
      </svg>
      <p className="small group-legend">
        {rows.map((r) => (
          <button key={r.user_id} type="button" className={`legend-btn ${focus === r.user_id ? "on" : ""}`} onClick={() => setFocus(focus === r.user_id ? null : r.user_id)} aria-pressed={focus === r.user_id}>
            <i style={{ background: color(r) }} />{nameOf(r)}
          </button>
        ))}
      </p>
    </div>
  );
}

/** Ringdiagramm: Anteil jedes Mitglieds an den Gruppenkilometern. */
function Donut({ rows, color }) {
  const total = rows.reduce((s, r) => s + r.km, 0);
  if (!total) return <p className="muted">Noch keine Kilometer in diesem Zeitraum.</p>;
  const R = 56, C = 2 * Math.PI * R;
  let acc = 0;
  return (
    <div className="donut-wrap">
      <svg viewBox="0 0 160 160" className="donut" role="img" aria-label="Anteil an den Gruppenkilometern">
        <circle cx="80" cy="80" r={R} fill="none" stroke="var(--ink)" strokeWidth="22" />
        {rows.filter((r) => r.km > 0).map((r) => {
          const len = (r.km / total) * C;
          const el = <circle key={r.user_id} cx="80" cy="80" r={R} fill="none" stroke={color(r)} strokeWidth="22" strokeDasharray={`${Math.max(0, len - 1.5)} ${C}`} strokeDashoffset={-acc} transform="rotate(-90 80 80)" />;
          acc += len;
          return el;
        })}
        <text x="80" y="78" textAnchor="middle" className="donut-num">{fmtNum(total, 0)}</text>
        <text x="80" y="95" textAnchor="middle" className="chart-label">km zusammen</text>
      </svg>
      <ul className="donut-list">
        {[...rows].sort((a, b) => b.km - a.km).filter((r) => r.km > 0).map((r) => (
          <li key={r.user_id}><Dot color={color(r)} />{nameOf(r)} <strong>{Math.round((r.km / total) * 100)} %</strong></li>
        ))}
      </ul>
    </div>
  );
}

/** Gestapelte Anteile je Mitglied, zum Beispiel Fahrzeit nach Tageszeit. */
function StackedRows({ rows, color, parts, get }) {
  const shades = ["#4aa8ff", "#f2b84b", "#ff9f6b", "#b48cf2", "#6b7a8c"];
  return (
    <>
      <ul className="stacked">
        {rows.map((r) => {
          const vals = get(r);
          const sum = vals ? vals.reduce((s, v) => s + v, 0) : 0;
          return (
            <li key={r.user_id}>
              <span className="hbar-label"><Dot color={color(r)} />{nameOf(r)}</span>
              <span className="stack-track">
                {vals && sum > 0 ? vals.map((v, i) => v > 0 && <span key={parts[i]} style={{ width: `${(v / sum) * 100}%`, background: shades[i % shades.length] }} title={`${parts[i]}: ${fmtNum(v, 1)} h (${Math.round((v / sum) * 100)} %)`} />) : null}
              </span>
              <span className="hbar-val">{vals && sum > 0 ? `${fmtNum(sum, 0)} h` : dash}</span>
            </li>
          );
        })}
      </ul>
      <p className="small group-legend">{parts.map((p, i) => <span key={p}><i style={{ background: shades[i % shades.length] }} />{p}</span>)}</p>
    </>
  );
}

/** Rekordkarte: Sieger groß, alle anderen als Balken darunter. */
function RecordCard({ title, rows, color, get, fmt }) {
  const items = rows.map((r) => ({ r, v: get(r) })).filter((i) => i.v);
  if (!items.length) return null;
  items.sort((a, b) => b.v - a.v);
  const win = items[0];
  return (
    <div className="record-card">
      <div className="muted small">{title}</div>
      <div className="record-win"><span>{fmt(win.v)}</span></div>
      <div className="record-who"><Dot color={color(win.r)} />🏆 {nameOf(win.r)}</div>
      <ul className="hbars compact">
        {items.slice(1, 4).map(({ r, v }) => (
          <li key={r.user_id}><span className="hbar-label">{nameOf(r)}</span><span className="hbar-track"><span className="hbar-fill" style={{ width: `${(v / win.v) * 100}%`, background: color(r) }} /></span><span className="hbar-val">{fmt(v)}</span></li>
        ))}
      </ul>
    </div>
  );
}


// ---------- Duell ----------

function Duel({ groupId, rows, color }) {
  const [a, setA] = useState("");
  const [b, setB] = useState("");
  const [d, setD] = useState(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!a || !b || a === b) { setD(null); return; }
    setError("");
    api.get(`/groups/${groupId}/duel?a=${a}&b=${b}`).then(setD).catch((e) => { setD(null); setError(e.message); });
  }, [groupId, a, b]);
  const byId = (id) => rows.find((r) => String(r.user_id) === String(id));
  const ra = byId(a), rb = byId(b);
  const cmp = (x, y, higherWins = true) => (x == null || y == null || x === y ? [false, false] : higherWins ? [x > y, y > x] : [x < y, y < x]);
  const lines = d ? [
    ["Kilometer", d.a.totals.km, d.b.totals.km, (v) => `${fmtNum(v, 1)} km`],
    ["Höhenmeter", d.a.totals.elev_m, d.b.totals.elev_m, (v) => `${fmtNum(v, 0)} m`],
    ["Fahrten", d.a.totals.rides, d.b.totals.rides, String],
    ["Fahrzeit", d.a.totals.time_s, d.b.totals.time_s, fmtDuration],
    ["Ø Tempo", d.a.totals.avg_speed, d.b.totals.avg_speed, (v) => `${fmtNum(v, 1)} km/h`],
  ] : [];
  return (
    <Panel title="Duell" sub="Zwei Mitglieder über die letzten 12 Wochen. Es zählen nur Kennzahlen, die ohnehin in der Gruppe stehen.">
      <div className="duel-pick">
        <select value={a} onChange={(e) => setA(e.target.value)} aria-label="Erstes Mitglied">
          <option value="">Mitglied wählen</option>
          {rows.map((r) => <option key={r.user_id} value={r.user_id}>{nameOf(r)}</option>)}
        </select>
        <span className="muted">gegen</span>
        <select value={b} onChange={(e) => setB(e.target.value)} aria-label="Zweites Mitglied">
          <option value="">Mitglied wählen</option>
          {rows.map((r) => <option key={r.user_id} value={r.user_id}>{nameOf(r)}</option>)}
        </select>
      </div>
      {error && <p className="error" role="alert">{error}</p>}
      {!d && !error && <p className="muted">Wähle zwei Mitglieder.</p>}
      {d && ra && rb && (
        <>
          <p className="duel-score">
            <span><Dot color={color(ra)} />{d.a.display_name}</span>
            <strong>{d.weeks_won.a} : {d.weeks_won.b}</strong>
            <span><Dot color={color(rb)} />{d.b.display_name}</span>
          </p>
          <p className="muted small" style={{ textAlign: "center" }}>Wochen gewonnen nach Kilometern{d.weeks_won.draw ? ` (${d.weeks_won.draw} unentschieden)` : ""}</p>
          <GroupedBars
            labels={d.weeks.map((w) => w.slice(8, 10) + "." + w.slice(5, 7))} unit=" km"
            series={[{ name: d.a.display_name, color: color(ra), values: d.a.km_by_week }, { name: d.b.display_name, color: color(rb), values: d.b.km_by_week }]}
          />
          <ul className="duel-lines">
            {lines.map(([label, x, y, fmt]) => {
              const [wa, wb] = cmp(x, y);
              return (
                <li key={label}>
                  <span className={wa ? "win" : ""}>{x == null ? "–" : fmt(x)}</span>
                  <span className="muted small">{label}</span>
                  <span className={wb ? "win" : ""}>{y == null ? "–" : fmt(y)}</span>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </Panel>
  );
}

// ---------- Hauptansicht ----------

const TAB_LIST = [["overview", "Übersicht"], ["streaks", "Serien & Meilensteine"], ["duel", "Duell"], ["course", "Verlauf"], ["rhythm", "Rhythmus"], ["records", "Rekorde"], ["load", "Belastung"], ["weather", "Wetter"], ["table", "Alle Zahlen"]];

export default function GroupStats({ d, groupId }) {
  const [tab, setTab] = useState("overview");
  const [metric, setMetric] = useState("km");
  const [cumulative, setCumulative] = useState(false);
  const rows = d.rows;
  const color = colorMap(rows);
  const has = (cat) => rows.some((r) => r.extras[cat]);
  const tabs = TAB_LIST.filter(([k]) => !["rhythm", "records", "load", "weather"].includes(k) || has(k));
  const active = tabs.some(([k]) => k === tab) ? tab : "overview";
  const sum = (m) => rows.reduce((s, r) => s + (r[m] || 0), 0);
  const secs = sum("time_s");
  const groupSpeed = secs >= 600 && sum("km") > 0 ? sum("km") / (secs / 3600) : null;
  const ex = (cat, key) => (r) => (r.extras[cat] ? r.extras[cat][key] : null);
  const change = (r) => {
    const before = r.prev?.[metric];
    if (!before || !["km", "elev_m", "time_s", "rides"].includes(metric)) return null;
    const pct = Math.round(((r[metric] - before) / before) * 100);
    return pct === 0 ? null : <span className={`delta ${pct > 0 ? "up" : "down"}`} title="Veränderung gegenüber dem Zeitraum davor">{pct > 0 ? "▲" : "▼"} {Math.abs(pct)} %</span>;
  };
  const sorted = [...rows].sort((a, b) => (b[metric] ?? -1) - (a[metric] ?? -1) || a.display_name.localeCompare(b.display_name));
  const best = (m) => Math.max(0, ...rows.map((r) => r[m] ?? 0));
  const picker = (
    <div className="actions metric-chips" role="group" aria-label="Kennzahl">
      {Object.entries(METRICS).map(([k, m]) => <button key={k} type="button" className={`chip ${metric === k ? "on" : ""}`} aria-pressed={metric === k} onClick={() => setMetric(k)}>{m.label}</button>)}
    </div>
  );
  const rhythm = rows.find((r) => r.extras.rhythm)?.extras.rhythm;
  const withR = rows.filter((r) => r.extras.rhythm);

  return (
    <>
      <nav className="stat-tabs" aria-label="Gruppenstatistik">
        {tabs.map(([k, l]) => <button key={k} className={active === k ? "on" : ""} aria-pressed={active === k} onClick={() => setTab(k)}>{l}</button>)}
      </nav>

      {active === "overview" && (
        <>
          <div className="kpis">
            <Kpi value={fmtNum(sum("km"), 0)} unit="km" label="Gruppe gesamt" />
            <Kpi value={fmtNum(sum("rides"), 0)} label="Fahrten" />
            <Kpi value={fmtNum(sum("elev_m"), 0)} unit="m" label="Höhenmeter" />
            <Kpi value={fmtDuration(secs)} label="Fahrzeit" />
            <Kpi value={groupSpeed ? fmtNum(groupSpeed, 1) : "–"} unit={groupSpeed ? "km/h" : ""} label="Ø Tempo" />
            <Kpi value={String(rows.filter((r) => r.rides > 0).length)} unit={`/ ${rows.length}`} label="Aktive Mitglieder" />
          </div>
          {picker}
          <div className="grid-2 gs-top">
            <Panel title={`Podest: ${METRICS[metric].label}`}><Podium rows={rows} metric={metric} color={color} /></Panel>
            <Panel title="Rangliste">
              <ol className="rank-list">
                {sorted.map((r, i) => (
                  <li key={r.user_id} className={r.is_me ? "me" : ""}>
                    <span className="rank-pos">{r.rank[metric] ? (MEDAL[r.rank[metric] - 1] || r.rank[metric]) : "–"}</span>
                    <Dot color={color(r)} /><span className="rank-name">{nameOf(r)}</span>
                    <span className="rank-val">{r[metric] ? METRICS[metric].cell(r[metric]) : dash}{change(r)}</span>
                  </li>
                ))}
              </ol>
            </Panel>
          </div>
          <div className="grid-2">
            <Panel title="Profil im Vergleich" sub="Jede Achse zeigt den Wert im Verhältnis zum Besten der Gruppe. Tippe auf einen Namen, um ihn hervorzuheben."><Radar rows={rows} color={color} /></Panel>
            <Panel title="Anteil an den Gruppenkilometern"><Donut rows={rows} color={color} /></Panel>
          </div>
        </>
      )}

      {active === "streaks" && (
        <>
          <div className="grid-2">
            <Panel title="Meilensteine" sub="Gesamtkilometer, die in diesem Zeitraum überschritten wurden.">
              {rows.some((r) => r.milestone)
                ? <ul className="milestone-list">{rows.filter((r) => r.milestone).sort((a, b) => b.milestone - a.milestone).map((r) => (
                  <li key={r.user_id}><Dot color={color(r)} /><strong>{nameOf(r)}</strong> hat die {fmtNum(r.milestone, 0)}-km-Marke geknackt 🎉</li>
                ))}</ul>
                : <p className="muted">In diesem Zeitraum wurde keine Marke überschritten (500, 1000, 2500, 5000, 10 000 km und weiter). Bei „Gesamt“ entfällt die Anzeige.</p>}
            </Panel>
            <Panel title="Größte Steigerung" sub="Kilometer im Vergleich zum Zeitraum davor. Wer sich verbessert, gewinnt, auch mit weniger Kilometern.">
              <MemberBars rows={rows} color={color} get={(r) => r.improve_pct} fmt={(v) => `${v > 0 ? "+" : ""}${fmtNum(v, 0)} %`} note="Ab 5 km im Zeitraum davor aussagekräftig." />
            </Panel>
          </div>
          <div className="grid-2">
            <Panel title="Fahrten pro Woche" sub="Regelmäßigkeit statt Kilometer: wer fährt am häufigsten?">
              <MemberBars rows={rows} color={color} get={(r) => r.rides_per_week} fmt={(v) => fmtNum(v, 1)} />
            </Panel>
            {has("records") && (
              <Panel title="Aktuelle Wochenserie" sub="Wochen in Folge mit mindestens einer Fahrt. Nur Mitglieder, die Rekorde teilen.">
                <MemberBars rows={rows} color={color} get={ex("records", "week_streak_now")} fmt={(v) => `${v} ${v === 1 ? "Woche" : "Wochen"}`} />
              </Panel>
            )}
          </div>
        </>
      )}

      {active === "duel" && <Duel groupId={groupId} rows={rows} color={color} />}

      {active === "course" && (
        <Panel title={`Kilometer im Verlauf: ${d.label}`}>
          <label className="check"><input type="checkbox" checked={cumulative} onChange={(e) => setCumulative(e.target.checked)} /><span>Aufsummiert: wer liegt wann vorn?</span></label>
          <SeriesChart data={d.series} cumulative={cumulative} color={color} rows={rows} />
          <Legend rows={rows} color={color} />
        </Panel>
      )}

      {active === "rhythm" && rhythm && (
        <>
          <Panel title="Kilometer je Wochentag" sub="Wer fährt wann? Nur Mitglieder, die den Fahrrhythmus teilen.">
            <GroupedBars labels={WD} unit=" km" series={withR.map((r) => ({ name: r.display_name, color: color(r), values: r.extras.rhythm.weekdays }))} />
            <Legend rows={withR} color={color} />
          </Panel>
          <div className="grid-2">
            <Panel title="Fahrzeit nach Tageszeit"><StackedRows rows={withR} color={color} parts={rhythm.dayparts.map((x) => x.label)} get={(r) => r.extras.rhythm.dayparts.map((x) => x.hours)} /></Panel>
            <Panel title="Fahrten nach Länge">
              <GroupedBars labels={rhythm.distances.map((x) => x.label)} series={withR.map((r) => ({ name: r.display_name, color: color(r), values: r.extras.rhythm.distances.map((x) => x.rides) }))} />
              <Legend rows={withR} color={color} />
            </Panel>
          </div>
        </>
      )}

      {active === "records" && (
        <div className="record-grid">
          <RecordCard title="Längste Fahrt" rows={rows} color={color} get={ex("records", "longest_km")} fmt={(v) => `${fmtNum(v, 1)} km`} />
          <RecordCard title="Meiste Höhenmeter (eine Fahrt)" rows={rows} color={color} get={ex("records", "most_climb_m")} fmt={(v) => `${fmtNum(v, 0)} m`} />
          <RecordCard title="Eddington-Zahl (Tage mit mindestens so vielen km)" rows={rows} color={color} get={ex("records", "eddington")} fmt={(v) => `${v}`} />
          <RecordCard title="Bester Tag" rows={rows} color={color} get={ex("records", "best_day_km")} fmt={(v) => `${fmtNum(v, 1)} km`} />
          <RecordCard title="Schnellster Schnitt" rows={rows} color={color} get={ex("records", "fastest_avg")} fmt={(v) => `${fmtNum(v, 1)} km/h`} />
          <RecordCard title="Längste Serie (Tage)" rows={rows} color={color} get={ex("records", "day_streak")} fmt={(v) => `${v} Tage`} />
          <RecordCard title="Längste Serie (Wochen)" rows={rows} color={color} get={ex("records", "week_streak")} fmt={(v) => `${v} Wochen`} />
        </div>
      )}

      {active === "load" && (
        <>
          <div className="grid-2">
            <Panel title="Belastung im Zeitraum" sub="Geschätzt aus Fahrzeit, Höhenmetern und Tempo, ohne Puls oder Leistung."><MemberBars rows={rows} color={color} get={ex("load", "period_load")} fmt={(v) => fmtNum(v, 0)} /></Panel>
            <Panel title="Fitness" sub="Gleitender Schnitt der Belastung über 42 Tage, Stand am Ende des Zeitraums."><MemberBars rows={rows} color={color} get={ex("load", "fitness")} fmt={(v) => fmtNum(v, 1)} /></Panel>
          </div>
          <div className="grid-2">
            <Panel title="Ermüdung" sub="Dasselbe über 7 Tage: wer ist gerade ausgepowert?"><MemberBars rows={rows} color={color} get={ex("load", "fatigue")} fmt={(v) => fmtNum(v, 1)} /></Panel>
            <Panel title="Form" sub="Fitness minus Ermüdung. Positiv heißt frisch, negativ heißt müde."><MemberBars rows={rows} color={color} get={ex("load", "form")} fmt={(v) => `${v > 0 ? "+" : ""}${fmtNum(v, 1)}`} /></Panel>
          </div>
        </>
      )}

      {active === "weather" && (
        <>
          <div className="grid-2">
            <Panel title="Kilometer bei Regen oder nasser Straße" sub="Wer ist der Hartgesottenste?"><MemberBars rows={rows} color={color} get={ex("weather", "wet_km")} fmt={(v) => `${fmtNum(v, 1)} km`} /></Panel>
            <Panel title="Anteil nasser Fahrten"><MemberBars rows={rows} color={color} get={ex("weather", "wet_share")} fmt={(v) => `${v} %`} /></Panel>
          </div>
          <div className="grid-2">
            <Panel title="Durchschnittstemperatur"><MemberBars rows={rows} color={color} get={ex("weather", "avg_temp")} fmt={(v) => `${fmtNum(v, 1)} °C`} /></Panel>
            <Panel title="Regenfahrten"><MemberBars rows={rows} color={color} get={ex("weather", "rainy_rides")} fmt={String} /></Panel>
          </div>
          <div className="record-grid">
            <RecordCard title="Kälteste Fahrt (je kälter, desto weiter oben)" rows={rows.map((r) => ({ ...r, _c: r.extras.weather?.coldest }))} color={color} get={(r) => (r._c != null ? 40 - r._c : null)} fmt={(v) => `${fmtNum(40 - v, 1)} °C`} />
            <RecordCard title="Wärmste Fahrt" rows={rows} color={color} get={ex("weather", "hottest")} fmt={(v) => `${fmtNum(v, 1)} °C`} />
          </div>
        </>
      )}

      {active === "table" && (
        <Panel title="Alle Zahlen" sub="Tippe auf eine Spaltenüberschrift, um danach zu sortieren.">
          <div className="table-wrap">
            <table className="group-table">
              <thead>
                <tr>
                  <th>#</th><th>Mitglied</th>
                  {Object.entries(METRICS).map(([k, m]) => (
                    <th key={k} className={metric === k ? "sorted" : ""} aria-sort={metric === k ? "descending" : "none"}>
                      <button type="button" className="th-btn" onClick={() => setMetric(k)}>{m.label}</button>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {sorted.map((r) => (
                  <tr key={r.user_id} className={r.is_me ? "me" : ""}>
                    <td>{r.rank[metric] ? (MEDAL[r.rank[metric] - 1] || r.rank[metric]) : "–"}</td>
                    <td><Dot color={color(r)} />{nameOf(r)}</td>
                    {Object.entries(METRICS).map(([k, m]) => (
                      <td key={k} className={`${metric === k ? "sorted" : ""} ${r[k] && r[k] === best(k) ? "best" : ""}`}>{r[k] != null && r[k] !== 0 ? m.cell(r[k]) : "–"}{k === metric && change(r)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Panel>
      )}
    </>
  );
}
