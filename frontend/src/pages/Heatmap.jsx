import { useEffect, useMemo, useRef, useState } from "react";
import L from "leaflet";
import "leaflet/dist/leaflet.css";
import { api, fmtDate, fmtKm } from "../api.js";
import { EmptyState } from "../components/ui.jsx";
import { loadMapConfig, tileOptions } from "../geo.js";

/** Google-Polyline (Präzision 5) -> Float64Array mit normalisierten Mercator-Koordinaten (x, y in 0..1). */
function decodeToMercator(str) {
  const out = [];
  let i = 0, lat = 0, lng = 0;
  while (i < str.length) {
    for (let axis = 0; axis < 2; axis++) {
      let shift = 0, result = 0, b;
      do {
        b = str.charCodeAt(i++) - 63;
        result |= (b & 0x1f) << shift;
        shift += 5;
      } while (b >= 0x20);
      const delta = result & 1 ? ~(result >> 1) : result >> 1;
      if (axis === 0) lat += delta;
      else lng += delta;
    }
    const la = Math.max(-85.0511, Math.min(85.0511, lat / 1e5));
    const x = (lng / 1e5 + 180) / 360;
    const s = Math.sin((la * Math.PI) / 180);
    const y = 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI);
    out.push(x, y);
  }
  return Float64Array.from(out);
}

function bboxOf(line) {
  let x0 = 1, y0 = 1, x1 = 0, y1 = 0;
  for (let i = 0; i < line.length; i += 2) {
    if (line[i] < x0) x0 = line[i];
    if (line[i] > x1) x1 = line[i];
    if (line[i + 1] < y0) y0 = line[i + 1];
    if (line[i + 1] > y1) y1 = line[i + 1];
  }
  return [x0, y0, x1, y1];
}

export default function Heatmap({ embedded = false }) {
  const [filters, setFilters] = useState({ year: "", bike_id: "" });
  const [options, setOptions] = useState({ years: [], bikes: [] });
  const [data, setData] = useState(null);
  const [showTiles, setShowTiles] = useState(true);
  const [timeOn, setTimeOn] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeed] = useState(1);        // 0,5 = ruhig, 1 = normal, 2 = schnell
  const [cutoff, setCutoff] = useState(0);      // Tage seit 1970, nur Fahrten bis zu diesem Tag
  const [error, setError] = useState("");
  const [cfg, setCfg] = useState(null);
  const boxRef = useRef(null);
  const state = useRef({}); // Karte, Canvas, Daten für den Zeichner

  // Filteroptionen einmalig aus der Statistik holen
  useEffect(() => {
    api.get("/stats/overview")
      .then((o) => setOptions({ years: o.years_available ?? [], bikes: o.bikes_available ?? [] }))
      .catch(() => {});
  }, []);

  useEffect(() => {
    const qs = new URLSearchParams();
    if (filters.year) qs.set("year", filters.year);
    if (filters.bike_id) qs.set("bike_id", filters.bike_id);
    setData(null);
    api.get(`/stats/heatmap?${qs}`).then(setData).catch((e) => setError(e.message));
  }, [filters]);

  useEffect(() => {
    loadMapConfig(api).then(setCfg).catch((e) => setError(e.message));
  }, []);

  // Karte aufbauen, sobald der Kartenhintergrund bekannt ist
  useEffect(() => {
    if (!cfg) return undefined;
    const map = L.map(boxRef.current, { zoomAnimation: false, zoomControl: true, preferCanvas: true }).setView([51.2, 10.4], 6);
    L.tileLayer(cfg.url, tileOptions(cfg)).addTo(map);
    const canvas = document.createElement("canvas");
    canvas.className = "heat";
    map.getContainer().appendChild(canvas);
    const st = state.current;
    st.map = map;
    st.canvas = canvas;
    st.lines = [];
    st.tiles = [];
    st.zoomTile = 14;
    st.square = null;
    st.showTiles = true;
    st.dark = cfg.dark;

    let raf = 0;
    const draw = () => {
      raf = 0;
      const size = map.getSize();
      const dpr = window.devicePixelRatio || 1;
      if (canvas.width !== size.x * dpr || canvas.height !== size.y * dpr) {
        canvas.width = size.x * dpr;
        canvas.height = size.y * dpr;
        canvas.style.width = `${size.x}px`;
        canvas.style.height = `${size.y}px`;
      }
      const ctx = canvas.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, size.x, size.y);
      const z = map.getZoom();
      const world = 256 * 2 ** z;
      const min = map.getPixelBounds().min;
      const ox = min.x, oy = min.y;

      if (st.showTiles && st.tiles.length) {
        const n = 2 ** st.zoomTile;
        const w = (1 / n) * world;
        ctx.fillStyle = st.dark ? "rgba(111, 211, 195, 0.13)" : "rgba(20, 150, 130, 0.14)";
        ctx.strokeStyle = st.dark ? "rgba(111, 211, 195, 0.28)" : "rgba(20, 150, 130, 0.45)";
        ctx.lineWidth = 1;
        for (const [tx, ty, td] of st.tiles) {
          if (st.timeOn && td > st.cutoff) continue;
          const x = (tx / n) * world - ox, y = (ty / n) * world - oy;
          if (x > size.x || y > size.y || x + w < 0 || y + w < 0) continue;
          ctx.fillRect(x, y, w, w);
          if (w > 6) ctx.strokeRect(x + 0.5, y + 0.5, w - 1, w - 1);
        }
      }

      // Strecken: additiv gemischt, damit oft gefahrene Wege heller leuchten
      // Dunkle Karte: additiv gemischt (leuchtet). Helle Karte: normales Überlagern, dichter wird dunkler.
      // Im Zeitverlauf leuchten Fahrten der letzten drei Wochen vor dem gewählten Tag hell auf.
      const baseWidth = Math.max(1.2, Math.min(3, (z - 5) * 0.35));
      const stride = z < 8 ? 4 : z < 10 ? 2 : 1;
      const vx0 = (ox) / world, vy0 = oy / world, vx1 = (ox + size.x) / world, vy1 = (oy + size.y) / world;
      ctx.lineJoin = "round";
      ctx.lineCap = "round";
      for (const pass of st.timeOn ? [0, 1] : [0]) {
        ctx.globalCompositeOperation = st.dark ? "lighter" : "source-over";
        if (pass === 0) {
          ctx.strokeStyle = st.dark ? "rgba(255, 112, 40, 0.22)" : "rgba(214, 48, 20, 0.30)";
          ctx.lineWidth = baseWidth;
        } else {
          ctx.strokeStyle = st.dark ? "rgba(255, 226, 140, 0.75)" : "rgba(0, 90, 200, 0.75)";
          ctx.lineWidth = baseWidth + 1;
        }
        for (const l of st.lines) {
          if (st.timeOn) {
            if (l.day > st.cutoff) continue;
            if ((st.cutoff - l.day <= 21) !== (pass === 1)) continue;
          }
          const [bx0, by0, bx1, by1] = l.box;
          if (bx1 < vx0 || bx0 > vx1 || by1 < vy0 || by0 > vy1) continue;
          const p = l.pts;
          ctx.beginPath();
          ctx.moveTo(p[0] * world - ox, p[1] * world - oy);
          for (let i = 2; i < p.length; i += 2 * stride) ctx.lineTo(p[i] * world - ox, p[i + 1] * world - oy);
          ctx.stroke();
        }
      }
      ctx.globalCompositeOperation = "source-over";

      if (st.square && st.showTiles && !st.timeOn) {
        const [[s, w], [nn, e]] = st.square.bounds;
        const px = (lng, lat) => {
          const sn = Math.sin((lat * Math.PI) / 180);
          return [((lng + 180) / 360) * world - ox, (0.5 - Math.log((1 + sn) / (1 - sn)) / (4 * Math.PI)) * world - oy];
        };
        const [x0, y0] = px(w, nn), [x1, y1] = px(e, s);
        ctx.strokeStyle = "#f2b84b";
        ctx.lineWidth = 2;
        ctx.strokeRect(x0, y0, x1 - x0, y1 - y0);
      }
    };
    st.schedule = () => { if (!raf) raf = requestAnimationFrame(draw); };
    map.on("move zoom resize viewreset", st.schedule);
    st.schedule();
    return () => {
      if (raf) cancelAnimationFrame(raf);
      map.remove();
      state.current = {};
    };
  }, [cfg]);

  // Daten in den Zeichner übernehmen
  useEffect(() => {
    const st = state.current;
    if (!st.map || !data) return;
    st.lines = data.lines.map((s, i) => {
      const pts = decodeToMercator(s);
      return { pts, box: bboxOf(pts), day: data.days?.[i] ?? 0, km: data.km?.[i] ?? 0 };
    }).filter((l) => l.pts.length >= 4);
    st.tiles = data.tiles;
    st.zoomTile = data.zoom;
    st.square = data.max_square;
    st.fit = (everything) => {
      if (!st.lines.length) return;
      let use = st.lines;
      if (!everything && st.lines.length >= 8) {
        // Heimatgebiet: Ausreißer wie eine Urlaubsfahrt ausklammern (Mittelpunkte zwischen 8. und 92. Prozent)
        const cx = st.lines.map((l) => (l.box[0] + l.box[2]) / 2).sort((u, v) => u - v);
        const cy = st.lines.map((l) => (l.box[1] + l.box[3]) / 2).sort((u, v) => u - v);
        const q = (arr, f) => arr[Math.min(arr.length - 1, Math.floor(arr.length * f))];
        const [lx, hx, ly, hy] = [q(cx, 0.08), q(cx, 0.92), q(cy, 0.08), q(cy, 0.92)];
        use = st.lines.filter((l) => {
          const mx = (l.box[0] + l.box[2]) / 2, my = (l.box[1] + l.box[3]) / 2;
          return mx >= lx && mx <= hx && my >= ly && my <= hy;
        });
      }
      let x0 = 1, y0 = 1, x1 = 0, y1 = 0;
      for (const l of use) {
        x0 = Math.min(x0, l.box[0]); y0 = Math.min(y0, l.box[1]);
        x1 = Math.max(x1, l.box[2]); y1 = Math.max(y1, l.box[3]);
      }
      const toLL = (x, y) => [(Math.atan(Math.sinh(Math.PI * (1 - 2 * y))) * 180) / Math.PI, x * 360 - 180];
      st.map.fitBounds([toLL(x0, y1), toLL(x1, y0)], { padding: [30, 30], maxZoom: 13, animate: false });
    };
    st.fit(false);
    st.schedule();
  }, [data, cfg]);

  useEffect(() => {
    state.current.showTiles = showTiles;
    state.current.schedule?.();
  }, [showTiles]);

  // Zeitraum der Daten und Kennzahlen bis zum gewählten Tag
  const span = useMemo(() => {
    if (!data?.days?.length) return null;
    return { min: Math.min(...data.days), max: Math.max(...data.days) };
  }, [data]);
  const upTo = useMemo(() => {
    if (!data?.days || !timeOn) return null;
    let rides = 0, km = 0;
    data.days.forEach((d, i) => { if (d <= cutoff) { rides += 1; km += data.km[i] ?? 0; } });
    const tiles = data.tiles.reduce((n, t) => n + (t[2] <= cutoff ? 1 : 0), 0);
    return { rides, km, tiles };
  }, [data, timeOn, cutoff]);

  useEffect(() => {
    const st = state.current;
    st.timeOn = timeOn;
    st.cutoff = cutoff;
    st.schedule?.();
  }, [timeOn, cutoff, data, cfg]);

  // Neue Daten (anderer Filter): Zeitverlauf von vorn
  useEffect(() => { if (span) setCutoff(timeOn ? span.min : span.max); setPlaying(false); }, [span]); // eslint-disable-line react-hooks/exhaustive-deps

  // Abspielen: etwa 25 Sekunden für den ganzen Zeitraum bei normaler Geschwindigkeit
  useEffect(() => {
    if (!playing || !span) return undefined;
    let raf = 0, last = performance.now(), pos = cutoff >= span.max ? span.min : cutoff;
    const perSecond = Math.max(1, (span.max - span.min) / 25) * speed;
    const tick = (now) => {
      pos += ((now - last) / 1000) * perSecond;
      last = now;
      if (pos >= span.max) { setCutoff(span.max); setPlaying(false); return; }
      setCutoff(Math.floor(pos));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [playing, speed, span]); // eslint-disable-line react-hooks/exhaustive-deps

  function toggleTime() {
    if (!span) return;
    if (!timeOn) { setTimeOn(true); setCutoff(span.min); setPlaying(true); }
    else { setTimeOn(false); setPlaying(false); setCutoff(span.max); }
  }

  const set = (k) => (e) => setFilters({ ...filters, [k]: e.target.value });
  const empty = data && data.lines.length === 0;

  return (
    <>
      <header className="page-head">
        {embedded ? <h2>Heatmap</h2> : <h1>Heatmap</h1>}
        <div className="filter-bar">
          <select value={filters.year} onChange={set("year")} aria-label="Jahr">
            <option value="">Alle Jahre</option>
            {options.years.map((y) => <option key={y} value={y}>{y}</option>)}
          </select>
          <select value={filters.bike_id} onChange={set("bike_id")} aria-label="Rad">
            <option value="">Alle Räder</option>
            {options.bikes.map((b) => <option key={b.id} value={b.id}>{b.name}</option>)}
          </select>
          <button className={`chip ${timeOn ? "on" : ""}`} onClick={toggleTime} aria-pressed={timeOn} disabled={!span}>Zeitverlauf</button>
          <button className={`chip ${showTiles ? "on" : ""}`} onClick={() => setShowTiles(!showTiles)} aria-pressed={showTiles}>
            Erkundete Kacheln
          </button>
          <button className="chip" onClick={() => state.current.fit?.(true)}>Alles anzeigen</button>
        </div>
      </header>
      {error && <p className="error" role="alert">{error}</p>}
      {empty && (
        <EmptyState title="Noch keine Strecken" text="Importiere Fahrten mit GPS-Daten, dann erscheinen sie hier." />
      )}
      {timeOn && span && (
        <div className="time-bar" role="group" aria-label="Zeitverlauf">
          <button className="btn small primary" onClick={() => { if (cutoff >= span.max) setCutoff(span.min); setPlaying(!playing); }}>
            {playing ? "Pause" : cutoff >= span.max ? "Nochmal" : "Abspielen"}
          </button>
          <input
            type="range" min={span.min} max={span.max} step={1} value={Math.min(Math.max(cutoff, span.min), span.max)}
            style={{ "--pct": `${((cutoff - span.min) / Math.max(1, span.max - span.min)) * 100}%` }}
            onChange={(e) => { setPlaying(false); setCutoff(Number(e.target.value)); }}
            aria-label="Datum" aria-valuetext={fmtDate(new Date(cutoff * 86400000).toISOString().slice(0, 10))}
          />
          <select value={speed} onChange={(e) => setSpeed(Number(e.target.value))} aria-label="Geschwindigkeit">
            <option value={0.5}>langsam</option>
            <option value={1}>normal</option>
            <option value={2}>schnell</option>
            <option value={4}>sehr schnell</option>
          </select>
          <div className="time-read">
            <strong>{fmtDate(new Date(cutoff * 86400000).toISOString().slice(0, 10))}</strong>
            {upTo && <span className="muted small">{fmtKm(upTo.rides)} Fahrten · {fmtKm(upTo.km)} km · {fmtKm(upTo.tiles)} Kacheln</span>}
          </div>
        </div>
      )}
      <div className="map-wrap" style={empty ? { display: "none" } : undefined}>
        <div ref={boxRef} style={{ height: "100%" }} />
        {!data && !error && <div className="map-badge">Lade Strecken …</div>}
        {data && !empty && !timeOn && (
          <div className="map-badge">
            {fmtKm(data.lines.length)} Fahrten · {fmtKm(data.tiles.length)} Kacheln
            {data.max_square && showTiles ? ` · größtes Quadrat ${data.max_square.size} × ${data.max_square.size}` : ""}
          </div>
        )}
      </div>
    </>
  );
}
