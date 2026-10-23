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

/** Upload mit Fortschrittsanzeige (fetch kann das nicht). */
export function upload(path, formData, onProgress) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `/api${path}`);
    const token = getToken();
    if (token) xhr.setRequestHeader("Authorization", `Bearer ${token}`);
    xhr.upload.onprogress = (e) => {
      if (e.lengthComputable && onProgress) onProgress(e.loaded / e.total);
    };
    xhr.onerror = () => reject(new Error("Verbindung fehlgeschlagen. Prüfe dein Netzwerk und versuche es erneut."));
    xhr.onload = () => {
      let data = null;
      try {
        data = JSON.parse(xhr.responseText);
      } catch {
        /* keine JSON-Antwort */
      }
      if (xhr.status === 401) {
        clearToken();
        onUnauthorized();
      }
      if (xhr.status >= 200 && xhr.status < 300) return resolve(data);
      let msg =
        xhr.status === 413
          ? "Die Datei ist für den Server zu groß. Prüfe das Upload-Limit des Reverse Proxys."
          : `Fehler ${xhr.status}`;
      if (data && typeof data.detail === "string") msg = data.detail;
      else if (data && Array.isArray(data.detail)) msg = data.detail.map((d) => d.msg).join(", ");
      reject(new Error(msg));
    };
    xhr.send(formData);
  });
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

// Der Server liefert Zeiten in UTC ohne Zeitzonenangabe
export const fmtDateTime = (iso) => {
  if (!iso) return "–";
  const d = new Date(/[zZ]|[+-]\d{2}:?\d{2}$/.test(iso) ? iso : iso + "Z");
  return d.toLocaleString("de-DE", { dateStyle: "medium", timeStyle: "short" });
};

export const fmtKm1 = (km) =>
  new Intl.NumberFormat("de-DE", { minimumFractionDigits: 1, maximumFractionDigits: 1 }).format(km ?? 0);

export const fmtDuration = (s) => {
  const h = Math.floor((s ?? 0) / 3600);
  const m = Math.floor(((s ?? 0) % 3600) / 60);
  return `${h}:${String(m).padStart(2, "0")} h`;
};
