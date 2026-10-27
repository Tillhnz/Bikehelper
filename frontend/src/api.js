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

/** Lädt eine Datei vom Server (mit Anmeldung) und startet den Download im Browser. */
export async function download(path, fallbackName) {
  const token = getToken();
  const res = await fetch(`/api${path}`, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
  if (!res.ok) throw new Error(`Fehler ${res.status}`);
  const m = /filename="([^"]+)"/.exec(res.headers.get("Content-Disposition") || "");
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = m ? m[1] : fallbackName;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 5000);
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
      const err = new Error(msg);
      err.status = xhr.status;
      reject(err);
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
  tires: "Reifen",
  tire_front: "Reifen vorn",
  tire_rear: "Reifen hinten",
  brake_pads: "Bremsbeläge",
  bar_tape: "Lenkerband",
  cables: "Brems- und Schaltzüge",
  sealant: "Dichtmilch",
  brake_fluid: "Bremsflüssigkeit",
  headset: "Steuersatz",
  bottom_bracket: "Tretlager",
  hubs: "Naben",
  pulleys: "Schaltröllchen",
  pedals: "Pedale",
  fasteners: "Schrauben und Gewinde",
  other: "Sonstiges",
};

export const CHAIN_LUBES = {
  oil: { name: "Öl", hint: "Klassisch: alle ca. 200 km schmieren. Gut bei Dauerregen und Streusalz." },
  wax: { name: "Wachs", hint: "Sauber und lange haltbar, der Verschleiß ist deutlich geringer. Ob heiß oder flüssig gewachst wurde, trägst du bei jeder Wartung der Kette ein." },
};

export const BIKE_TYPES = { road: "Rennrad", gravel: "Gravel", mtb: "Mountainbike", other: "Sonstiges" };

export const STATUS_LABEL = { ok: "In Ordnung", soon: "Bald fällig", due: "Fällig", unknown: "Einbaudatum fehlt" };

export const fmtKm = (km) =>
  new Intl.NumberFormat("de-DE", { maximumFractionDigits: 0 }).format(Math.round(km ?? 0));

export const fmtDate = (iso) =>
  iso ? new Date(iso + "T00:00:00").toLocaleDateString("de-DE") : "–";

export const today = () => new Date().toISOString().slice(0, 10);
// Aktuelle Ortszeit als HH:MM für Zeitfelder
export const nowTime = () => {
  const d = new Date();
  return `${String(d.getHours()).padStart(2, "0")}:${String(d.getMinutes()).padStart(2, "0")}`;
};
const toTime = (t) => (t ? (t.length === 5 ? `${t}:00` : t) : null);
export { toTime };

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

export const fmtNum = (v, digits = 1) =>
  v == null ? "–" : new Intl.NumberFormat("de-DE", { maximumFractionDigits: digits }).format(v);

export const WEATHER_TEXT = (code) => {
  if (code == null) return null;
  if (code === 0) return "klar";
  if (code <= 3) return "bewölkt";
  if (code === 45 || code === 48) return "Nebel";
  if (code >= 51 && code <= 57) return "Nieselregen";
  if (code >= 61 && code <= 67) return "Regen";
  if (code >= 71 && code <= 77) return "Schnee";
  if (code >= 80 && code <= 82) return "Regenschauer";
  if (code === 85 || code === 86) return "Schneeschauer";
  if (code >= 95) return "Gewitter";
  return null;
};

/** Nur http(s)-Links werden als Verweis verwendet (nie javascript: oder data:), auch wenn der Server sie schon prüft. */
export const safeUrl = (u) => {
  try {
    const p = new URL(u);
    return p.protocol === "http:" || p.protocol === "https:" ? p.href : null;
  } catch {
    return null;
  }
};

/** Woher eine Fahrt stammt (Feld `source`). Ältere oder unbekannte Werte erscheinen unverändert. */
export const SOURCE_LABEL = {
  wahoo: "Wahoo",
  intervals: "intervals.icu",
  upload: "Datei-Upload",
  strava_export: "Strava-Export",
  strava: "Strava",
};
export const sourceLabel = (s) => (s ? SOURCE_LABEL[s] ?? s : null);
