"""Orte zu erkundeten Kacheln zuordnen. Fragt Städte und Gemeinden bei OpenStreetMap (Nominatim) ab.

Nominatim erlaubt höchstens eine Anfrage pro Sekunde und verlangt eine eindeutige Kennung. Gesendet werden nur die
Mittelpunkte einzelner Kacheln (ca. 1,5 km genau), keine Konto- oder Fahrtdaten. Jeder Ort wird nur einmal geholt
und gespeichert; ein Lauf fragt höchstens `max_requests` Orte ab und macht beim nächsten Mal weiter.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from collections import Counter
from datetime import datetime
from typing import Callable

import httpx
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import SessionLocal
from ..models import Activity, GeoMiss, GeoState, Place, PlaceVisit, User
from ..stats import places as P
from ..stats import tiles as T

log = logging.getLogger("bikehelper.geo")

PAUSE_S = 1.1
MAX_BOX_TILES = 40_000     # größere Flächen (ganze Landkreise oder Länder) werden nicht zugeordnet
SCHEDULE_INTERVAL_S = 6 * 3600
BACKGROUND_REQUESTS = 120

Reverse = Callable[[float, float], dict | None]

_lock = threading.Lock()
_running: dict[int, dict] = {}
_cache: dict[int, tuple[dict, set]] = {}   # place_id -> (Geometrie, Kacheln innerhalb)


_pace_lock = threading.Lock()
_last_call = [0.0]


def _pace_nominatim() -> None:
    """Nominatim erlaubt eine Anfrage pro Sekunde für die ganze Installation, auch wenn mehrere Nutzer gleichzeitig laufen."""
    with _pace_lock:
        wait = PAUSE_S - (time.monotonic() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.monotonic()


def make_reverse() -> Reverse:
    client = httpx.Client(
        timeout=30,
        headers={"User-Agent": f"BikeHelper/1.0 (self-hosted; {settings.public_url})", "Accept-Language": "de"},
    )

    def reverse(lat: float, lng: float) -> dict | None:
        _pace_nominatim()
        r = client.get(
            settings.nominatim_url.rstrip("/") + "/reverse",
            params={"lat": f"{lat:.5f}", "lon": f"{lng:.5f}", "format": "jsonv2", "zoom": 10, "addressdetails": 1,
                    "polygon_geojson": 1, "polygon_threshold": 0.0003, "accept-language": "de"},
        )
        if r.status_code == 429:
            raise RuntimeError("Nominatim bremst (zu viele Anfragen). Der Lauf wird später fortgesetzt.")
        r.raise_for_status()
        data = r.json()
        return None if "error" in data else data

    return reverse


def _store_place(db: Session, data: dict) -> Place | None:
    """Legt aus einer Nominatim-Antwort einen Ort an (oder findet den vorhandenen)."""
    geom = data.get("geojson") or {}
    if geom.get("type") not in ("Polygon", "MultiPolygon") or not data.get("osm_id"):
        return None
    key = f"{str(data.get('osm_type', 'x'))[:1].upper()}{data['osm_id']}"
    existing = db.scalar(select(Place).where(Place.osm_key == key))
    if existing:
        return existing
    box = P.bbox(geom)
    if not box:
        return None
    x0, y1 = T.tile_of(box[0], box[1])
    x1, y0 = T.tile_of(box[2], box[3])
    if (abs(x1 - x0) + 1) * (abs(y1 - y0) + 1) > MAX_BOX_TILES:
        return None
    addr = data.get("address") or {}
    kind, name = P.kind_and_name(addr, data.get("name") or "")
    if not name:
        return None
    tiles = P.tiles_in(geom, box)
    place = Place(
        osm_key=key, name=name[:200], kind=kind, state=(addr.get("state") or None),
        country_code=(addr.get("country_code") or "").lower() or None, country=addr.get("country"),
        geometry=json.dumps(geom, separators=(",", ":")), total_tiles=len(tiles),
    )
    db.add(place)
    db.flush()
    _cache[place.id] = (geom, tiles)
    return place


def _tiles_of(place: Place) -> set:
    hit = _cache.get(place.id)
    if hit:
        return hit[1]
    geom = json.loads(place.geometry)
    tiles = P.tiles_in(geom)
    _cache[place.id] = (geom, tiles)
    return tiles


def user_tiles(db: Session, user_id: int) -> tuple[set, Counter]:
    """(alle erkundeten Kacheln, Zahl der Fahrtstarts je Kachel)."""
    explored: set = set()
    starts: Counter = Counter()
    for tiles, lat, lng in db.execute(
        select(Activity.tiles, Activity.start_lat, Activity.start_lng).where(Activity.user_id == user_id)
    ):
        explored |= T.decode(tiles)
        if lat is not None and lng is not None:
            starts[T.tile_of(lat, lng)] += 1
    return explored, starts


def resolve_user(db: Session, user_id: int, reverse: Reverse, max_requests: int = 300, pause: float = PAUSE_S,
                 progress: dict | None = None) -> dict:
    """Ordnet die erkundeten Kacheln eines Nutzers Orten zu und speichert das Ergebnis."""
    from ..routers.stats import _ensure_tiles  # Kacheln fehlender Fahrten zuerst berechnen

    _ensure_tiles(db, user_id)
    explored, starts = user_tiles(db, user_id)
    misses = {(m.x, m.y) for m in db.scalars(select(GeoMiss))}
    places = db.scalars(select(Place)).all()
    by_id = {p.id: p for p in places}
    covered: dict[int, set] = {}
    assigned: set = set()
    for p in places:
        hit = explored & _tiles_of(p)
        if hit:
            covered[p.id] = hit
            assigned |= hit

    error = None
    done = 0
    pending = sorted(explored - assigned - misses)
    while pending and done < max_requests:
        tile = pending.pop(0)
        if tile in assigned:
            continue
        s, w, n, e = T.tile_bounds(*tile)
        try:
            data = reverse((s + n) / 2, (w + e) / 2)
        except Exception as exc:  # noqa: BLE001
            error = str(exc)[:290]
            log.warning("Ortssuche abgebrochen: %s", exc)
            break
        done += 1
        if progress is not None:
            progress["requests"] = progress.get("requests", 0) + 1
        place = _store_place(db, data) if data else None
        if place is None:
            db.merge(GeoMiss(x=tile[0], y=tile[1]))
        else:
            hit = explored & _tiles_of(place)
            if tile not in hit:
                db.merge(GeoMiss(x=tile[0], y=tile[1]))   # Fläche passt nicht zur Kachel, nicht erneut fragen
            by_id[place.id] = place
            if hit:
                covered[place.id] = hit
            assigned |= hit
            pending = [t for t in pending if t not in assigned]
        db.commit()
        if pause:
            time.sleep(pause)

    db.execute(delete(PlaceVisit).where(PlaceVisit.user_id == user_id))
    for pid, hit in covered.items():
        rides = sum(n for t, n in starts.items() if t in hit)
        db.add(PlaceVisit(user_id=user_id, place_id=pid, tiles=len(hit), rides=rides))
    unresolved = len(explored - assigned - {(m.x, m.y) for m in db.scalars(select(GeoMiss))})
    state = db.get(GeoState, user_id) or GeoState(user_id=user_id)
    state.unresolved, state.explored, state.updated_at, state.error = unresolved, len(explored), datetime.utcnow(), error
    db.add(state)
    db.commit()
    return {"requests": done, "unresolved": unresolved, "error": error}


def status(user_id: int) -> dict:
    with _lock:
        return dict(_running.get(user_id, {"running": False}))


def start(user_id: int, max_requests: int = 400) -> bool:
    """Startet die Zuordnung im Hintergrund. False, wenn sie für diesen Nutzer schon läuft."""
    with _lock:
        if _running.get(user_id, {}).get("running"):
            return False
        _running[user_id] = {"running": True, "requests": 0, "started": datetime.utcnow().isoformat()}
        progress = _running[user_id]

    def work() -> None:
        try:
            with SessionLocal() as db:
                resolve_user(db, user_id, make_reverse(), max_requests, progress=progress)
        except Exception:
            log.exception("Ortszuordnung fehlgeschlagen")
        finally:
            with _lock:
                _running[user_id] = {"running": False}

    threading.Thread(target=work, daemon=True, name=f"geo-{user_id}").start()
    return True


def start_background() -> None:
    if not settings.geo_enabled:
        return

    def loop() -> None:
        time.sleep(300)
        while True:
            try:
                with SessionLocal() as db:
                    ids = db.scalars(select(User.id)).all()
                for uid in ids:
                    with SessionLocal() as db:
                        resolve_user(db, uid, make_reverse(), BACKGROUND_REQUESTS)
            except Exception:
                log.exception("Geplante Ortszuordnung fehlgeschlagen")
            time.sleep(SCHEDULE_INTERVAL_S)

    threading.Thread(target=loop, daemon=True, name="geo-scheduler").start()
