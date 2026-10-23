/**
 * Uploads und Importe leben hier, außerhalb der Seiten. So laufen sie weiter, wenn man auf eine andere Seite
 * der App wechselt, und der Fortschritt bleibt überall sichtbar. Der Server-Import läuft ohnehin im Hintergrund;
 * nach einem Neuladen der Seite wird er über /imports/active wieder aufgenommen.
 */
import { useSyncExternalStore } from "react";
import { api, upload } from "./api.js";

const idle = () => ({ phase: "idle", pct: 0, job: null, result: null, error: "", label: "" });

let state = { strava: idle(), files: idle(), doneCount: 0 };
const listeners = new Set();
const baseTitle = typeof document !== "undefined" ? document.title : "BikeHelper";

function emit() {
  listeners.forEach((l) => l());
  updateTitle();
}

function set(key, patch) {
  state = { ...state, [key]: { ...state[key], ...patch } };
  emit();
}

export const subscribe = (l) => {
  listeners.add(l);
  return () => listeners.delete(l);
};
export const getState = () => state;
export const useUploads = () => useSyncExternalStore(subscribe, getState);

export const isBusy = (t) => t.phase === "uploading" || t.phase === "processing";

function updateTitle() {
  if (typeof document === "undefined") return;
  const s = state.strava, f = state.files;
  if (s.phase === "uploading") document.title = `⬆ ${Math.round(s.pct * 100)} % · ${baseTitle}`;
  else if (s.phase === "processing") document.title = `⏳ Import läuft · ${baseTitle}`;
  else if (f.phase === "uploading") document.title = `⬆ ${Math.round(f.pct * 100)} % · ${baseTitle}`;
  else document.title = baseTitle;
}

// ---------- Benachrichtigungen ----------

export function askNotificationPermission() {
  try {
    if ("Notification" in window && Notification.permission === "default") Notification.requestPermission();
  } catch { /* nicht unterstützt */ }
}

function notify(title, body) {
  if (typeof document !== "undefined") document.title = `✓ ${title} · ${baseTitle}`;
  try {
    if ("Notification" in window && Notification.permission === "granted" && document.hidden) {
      const n = new Notification(title, { body });
      n.onclick = () => { window.focus(); n.close(); };
    }
  } catch { /* nicht unterstützt */ }
}

if (typeof document !== "undefined") {
  // Sobald man zurückkommt, wieder den normalen Titel zeigen (außer es läuft noch etwas)
  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) updateTitle();
  });
  // Beim Schließen oder Neuladen mitten im Hochladen warnen (der Upload ginge verloren)
  window.addEventListener("beforeunload", (e) => {
    if (state.strava.phase === "uploading" || state.files.phase === "uploading") {
      e.preventDefault();
      e.returnValue = "";
    }
  });
}

// ---------- Strava-Export ----------

let pollTimer = null;

function pollJob(jobId) {
  clearTimeout(pollTimer);
  const tick = async () => {
    try {
      const j = await api.get(`/imports/${jobId}`);
      if (j.status === "running") {
        set("strava", { phase: "processing", job: j });
        pollTimer = setTimeout(tick, 1500);
      } else if (j.status === "done") {
        state = { ...state, doneCount: state.doneCount + 1 };
        set("strava", { phase: "done", job: j, result: j.summary });
        const n = j.summary.imported;
        notify("Import abgeschlossen", `${n} ${n === 1 ? "Fahrt" : "Fahrten"} importiert.`);
      } else {
        state = { ...state, doneCount: state.doneCount + 1 };
        set("strava", { phase: "error", job: j, error: j.error || "Der Import ist fehlgeschlagen." });
        notify("Import fehlgeschlagen", j.error || "");
      }
    } catch (err) {
      // Kurze Verbindungsprobleme (zum Beispiel Tab im Ruhezustand) überbrücken, statt abzubrechen
      if (/Fehler 404/.test(err.message) || /nicht gefunden/.test(err.message)) {
        set("strava", { phase: "error", error: err.message });
      } else {
        pollTimer = setTimeout(tick, 4000);
      }
    }
  };
  pollTimer = setTimeout(tick, 300);
}

export async function startStravaImport(file, createBikes) {
  if (isBusy(state.strava)) return;
  askNotificationPermission();
  // Läuft auf dem Server schon ein Import (zum Beispiel von einem früheren Versuch), nicht erneut hochladen
  if (await resumeActive()) return;
  set("strava", { ...idle(), phase: "uploading", label: file.name });
  try {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("create_bikes", createBikes ? "true" : "false");
    const { job_id } = await upload("/imports/strava-export", fd, (p) => set("strava", { pct: p }));
    set("strava", { phase: "processing", pct: 1 });
    pollJob(job_id);
  } catch (err) {
    // Zeitüberschreitung des Proxys (502/504) oder "läuft schon" (409): Die Datei kann trotzdem angekommen sein
    if ([409, 502, 504, 524].includes(err.status) && (await resumeActive())) return;
    const hint = [502, 504, 524].includes(err.status)
      ? " Wahrscheinlich bricht der Reverse Proxy große Uploads ab, siehe README (Abschnitt Reverse Proxy)."
      : "";
    set("strava", { phase: "error", error: err.message + hint });
    notify("Upload fehlgeschlagen", err.message);
  }
}

/** Nach einem Neuladen: läuft auf dem Server noch ein Import, Fortschritt wieder anzeigen. */
export async function resumeActive() {
  if (state.strava.phase === "processing") return true;
  try {
    const { job } = await api.get("/imports/active");
    if (job) {
      set("strava", { ...idle(), phase: "processing", job, label: "Import" });
      pollJob(job.id);
      return true;
    }
  } catch { /* nicht schlimm */ }
  return false;
}

// ---------- Einzelne Dateien ----------

export async function startFileImport(files, bikeId) {
  if (isBusy(state.files)) return;
  askNotificationPermission();
  set("files", { ...idle(), phase: "uploading", label: files.length === 1 ? files[0].name : `${files.length} Dateien` });
  try {
    const fd = new FormData();
    files.forEach((f) => fd.append("files", f));
    if (bikeId) fd.append("bike_id", bikeId);
    const result = await upload("/activities/upload", fd, (p) => set("files", { pct: p }));
    state = { ...state, doneCount: state.doneCount + 1 };
    set("files", { phase: "done", result });
    notify("Upload abgeschlossen", `${result.imported} ${result.imported === 1 ? "Fahrt" : "Fahrten"} importiert.`);
  } catch (err) {
    set("files", { phase: "error", error: err.message });
    notify("Upload fehlgeschlagen", err.message);
  }
}

export function dismiss(key) {
  set(key, idle());
}

/** Beim Abmelden alles zurücksetzen. */
export function resetUploads() {
  clearTimeout(pollTimer);
  state = { strava: idle(), files: idle(), doneCount: 0 };
  emit();
}
