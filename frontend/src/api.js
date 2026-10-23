const TOKEN_KEY = "bikehelper_token";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (t) => localStorage.setItem(TOKEN_KEY, t);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

let onUnauthorized = () => {};
export const setUnauthorizedHandler = (fn) => (onUnauthorized = fn);

async function request(method, path, body) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;

  const res = await fetch(`/api${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && path !== "/auth/login") {
    clearToken();
    onUnauthorized();
  }
  if (!res.ok) {
    let msg = `Fehler ${res.status}`;
    try {
      const data = await res.json();
      if (typeof data.detail === "string") msg = data.detail;
      else if (Array.isArray(data.detail)) msg = data.detail.map((d) => d.msg).join(", ");
    } catch {
      /* keine JSON-Antwort */
    }
    throw new Error(msg);
  }
  return res.status === 204 ? null : res.json();
}

export const api = {
  get: (p) => request("GET", p),
  post: (p, b) => request("POST", p, b ?? {}),
  put: (p, b) => request("PUT", p, b ?? {}),
  del: (p) => request("DELETE", p),
};

// ---- Anzeige-Helfer ----

export const CATEGORIES = {
  chain: "Kette",
  cassette: "Kassette",
  chainring: "Kettenblatt",
  tire_front: "Reifen vorn",
  tire_rear: "Reifen hinten",
  brake_pads: "Bremsbeläge",
  bar_tape: "Lenkerband",
  cables: "Brems- und Schaltzüge",
  sealant: "Dichtmilch",
  other: "Sonstiges",
};

export const BIKE_TYPES = { road: "Rennrad", gravel: "Gravel", mtb: "Mountainbike", other: "Sonstiges" };

// Vorschläge für Wartungsregeln, die beim Anlegen einer Komponente mit erstellt werden können
export const DEFAULT_RULES = {
  chain: { label: "Kette wechseln", interval_km: 3000 },
  cassette: { label: "Kassette wechseln", interval_km: 9000 },
  chainring: { label: "Kettenblatt wechseln", interval_km: 20000 },
  tire_front: { label: "Reifen wechseln", interval_km: 5000 },
  tire_rear: { label: "Reifen wechseln", interval_km: 4000 },
  brake_pads: { label: "Bremsbeläge prüfen", interval_km: 4000, interval_months: 12 },
  bar_tape: { label: "Lenkerband erneuern", interval_months: 24 },
  cables: { label: "Züge erneuern", interval_months: 24 },
  sealant: { label: "Dichtmilch auffüllen", interval_months: 6 },
};

export const STATUS_LABEL = { ok: "In Ordnung", soon: "Bald fällig", due: "Fällig" };

export const fmtKm = (km) =>
  new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 }).format(Math.round(km ?? 0));

export const fmtDate = (iso) =>
  iso ? new Date(iso + "T00:00:00").toLocaleDateString("de-DE") : "–";

export const today = () => new Date().toISOString().slice(0, 10);
