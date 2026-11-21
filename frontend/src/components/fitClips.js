// Zwischenspeicher für aufgenommene Videos. Alles bleibt in diesem Browser (IndexedDB),
// nichts davon geht an den Server. Zwei Speicher: kleine Angaben zum Nachschlagen, große Daten getrennt.
const DB_NAME = "bikehelper-fit";
const VERSION = 1;
const META = "clipMeta";
const DATA = "clipData";
export const MAX_PER_BIKE = 6;

function open() {
  return new Promise((resolve, reject) => {
    if (typeof indexedDB === "undefined") { reject(new Error("Dieser Browser kann keine Videos zwischenspeichern.")); return; }
    const req = indexedDB.open(DB_NAME, VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(META)) db.createObjectStore(META, { keyPath: "id", autoIncrement: true }).createIndex("bike", "bikeId");
      if (!db.objectStoreNames.contains(DATA)) db.createObjectStore(DATA);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error || new Error("Der Zwischenspeicher lässt sich nicht öffnen."));
  });
}

const done = (tx) => new Promise((res, rej) => { tx.oncomplete = () => res(); tx.onerror = () => rej(tx.error); tx.onabort = () => rej(tx.error); });
const get = (store, key) => new Promise((res, rej) => { const r = store.get(key); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });

/** Aufnahme ablegen. Gibt die neue Kennung zurück. */
export async function saveClip({ bikeId, view, blob, metrics, times, poses, label }) {
  const db = await open();
  const tx = db.transaction([META, DATA], "readwrite");
  const meta = { bikeId, view, at: new Date().toISOString(), metrics, label: label || "", bytes: blob?.size || 0, type: blob?.type || "" };
  const id = await new Promise((res, rej) => { const r = tx.objectStore(META).add(meta); r.onsuccess = () => res(r.result); r.onerror = () => rej(r.error); });
  tx.objectStore(DATA).put({ blob, times, poses }, id);
  await done(tx);
  await prune(bikeId);
  return id;
}

export async function listClips(bikeId) {
  const db = await open();
  const tx = db.transaction(META, "readonly");
  const rows = await new Promise((res, rej) => {
    const r = tx.objectStore(META).index("bike").getAll(bikeId);
    r.onsuccess = () => res(r.result || []); r.onerror = () => rej(r.error);
  });
  return rows.sort((a, b) => (a.at < b.at ? 1 : -1));
}

export async function loadClip(id) {
  const db = await open();
  const tx = db.transaction([META, DATA], "readonly");
  const meta = await get(tx.objectStore(META), id);
  const data = await get(tx.objectStore(DATA), id);
  return meta && data ? { ...meta, ...data } : null;
}

export async function deleteClip(id) {
  const db = await open();
  const tx = db.transaction([META, DATA], "readwrite");
  tx.objectStore(META).delete(id);
  tx.objectStore(DATA).delete(id);
  await done(tx);
}

/** Älteste Aufnahmen eines Rads wegräumen, damit der Speicher nicht vollläuft. */
export async function prune(bikeId, keep = MAX_PER_BIKE) {
  const rows = await listClips(bikeId);
  for (const row of rows.slice(keep)) await deleteClip(row.id);
}

/** Freier Platz, grob. Gibt null zurück, wenn der Browser nichts verrät. */
export async function space() {
  try {
    const e = await navigator.storage?.estimate?.();
    if (!e || !e.quota) return null;
    return { usedMb: Math.round(e.usage / 1e5) / 10, freeMb: Math.round((e.quota - e.usage) / 1e5) / 10 };
  } catch { return null; }
}
