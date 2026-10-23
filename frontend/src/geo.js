/** Google-Polyline (Präzision 5) -> [[lat, lng], ...] */
export function decodePolyline(str) {
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
    out.push([lat / 1e5, lng / 1e5]);
  }
  return out;
}

let mapConfigPromise = null;

/** Kartenhintergrund laut Server (einmal laden, danach aus dem Speicher). */
export function loadMapConfig(api) {
  if (!mapConfigPromise) {
    mapConfigPromise = api.get("/map-config").catch((e) => {
      mapConfigPromise = null;
      throw e;
    });
  }
  return mapConfigPromise;
}

export function tileOptions(cfg) {
  return { maxZoom: cfg.max_zoom, subdomains: cfg.subdomains, attribution: cfg.attribution };
}
