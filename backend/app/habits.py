"""Gewohnheiten aus den Fahrten ableiten: Arbeitswege erkennen, Standzeit im Freien bewerten, Tags anlernen.

Arbeitswege: Am selben Tag mit demselben Rad morgens hin, später zurück (Ziel der ersten Fahrt = Start der zweiten, Start der ersten =
Ziel der zweiten). Erst wenn sich dasselbe Paar von Orten an mindestens COMMUTE_MIN_DAYS Tagen zeigt, gilt es als Muster.
Dazwischen steht das Rad. Steht es am Arbeitsplatz im Freien (Einstellung), zählt die Zeit dazwischen als zusätzliche Nässe-Belastung:
Regenstunden am Arbeitsplatz (Open-Meteo) plus eine kleine Grundlast für Feuchtigkeit und Schmutz.

Tags: Fahrten lassen sich von Hand taggen. Hast du ein Tag bei mindestens TAG_MIN_EXAMPLES ähnlichen Fahrten gesetzt (gleicher Start und Ziel,
ähnliche Länge, Tageszeit und Werktag/Wochenende), vergibt der Server es bei weiteren ähnlichen Fahrten selbst. Entfernst du ein
automatisches Tag, merkt er sich das und vergibt es dort nicht wieder.
"""
from __future__ import annotations

import logging
import math
import threading
from datetime import datetime, timedelta, timezone

import httpx
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .config import settings
from .database import SessionLocal
from .importers import polyline as polyline_codec
from .models import Activity, ActivityTag, User
from .stats.overview import get_tz, local
from .weather import core as weather_core
from .weather import service as weather_service

log = logging.getLogger("bikehelper.habits")

NO_END = 999.0                 # end_lat: keine Strecke vorhanden
PLACE_RADIUS_M = 400
HOME_RADIUS_M = 600
COMMUTE_TAG = "Pendeln"
COMMUTE_MIN_DAYS = 3           # so viele Tage mit demselben Hin- und Rückweg, bis es als Muster gilt
MIN_STAND_H = 3.0              # kürzere Pausen sind keine Standzeit (Einkauf, Kaffee)
MAX_STAND_H = 14.0
MIN_LEG_KM = 1.0
STAND_WET_KM_PER_WET_H = 6.0   # eine Regenstunde im Stand belastet etwa so wie 6 km Fahrt im Regen (kein Fahrtwind, kein Spritzwasser)
STAND_BASE_KM_PER_H = 0.25     # Grundlast durch Feuchtigkeit/Taupunkt/Schmutz, je Stunde im Freien
STAND_CAP_KM = 40.0
TAG_MIN_EXAMPLES = 3
TAG_SHARE = 0.8
TAG_LENGTH_TOLERANCE = 0.35
TAG_TIME_TOLERANCE_MIN = 150
MAX_TAG_LEN = 30
MAX_RIDES = 4000


def _near(a_lat: float, a_lng: float, b_lat: float, b_lng: float, radius: float = PLACE_RADIUS_M) -> bool:
    dy = (a_lat - b_lat) * 111_320
    dx = (a_lng - b_lng) * 111_320 * math.cos(math.radians(a_lat))
    return dx * dx + dy * dy <= radius * radius


def clean_tag(text: str | None) -> str:
    return " ".join((text or "").replace(",", " ").split())[:MAX_TAG_LEN]


# ---------- Zielpunkte nachtragen ----------

def fill_end_points(db: Session, user_id: int, limit: int = 300) -> int:
    rows = db.execute(
        select(Activity.id, Activity.polyline)
        .where(Activity.user_id == user_id, Activity.end_lat.is_(None), Activity.polyline.is_not(None)).limit(limit)
    ).all()
    for aid, enc in rows:
        lat = lng = NO_END
        try:
            pts = polyline_codec.decode(enc)
            if pts:
                lat, lng = pts[-1]
        except (IndexError, ValueError):
            pass
        db.execute(update(Activity).where(Activity.id == aid).values(end_lat=lat, end_lng=lng))
    # Fahrten ohne Strecke: kein Zielpunkt
    db.execute(update(Activity).where(Activity.user_id == user_id, Activity.end_lat.is_(None), Activity.polyline.is_(None))
               .values(end_lat=NO_END, end_lng=NO_END))
    db.commit()
    return len(rows)


# ---------- Arbeitswege ----------

class Ride:
    __slots__ = ("id", "bike_id", "start", "end", "slat", "slng", "elat", "elng", "km", "local_start")

    def __init__(self, id, bike_id, start, moving_s, slat, slng, elat, elng, km, tz):
        self.id, self.bike_id, self.start = id, bike_id, start
        self.end = start + timedelta(seconds=moving_s or 0)
        self.slat, self.slng, self.elat, self.elng, self.km = slat, slng, elat, elng, km or 0.0
        self.local_start = local(start, tz)


def _load_rides(db: Session, user_id: int, tz) -> list[Ride]:
    q = (select(Activity.id, Activity.bike_id, Activity.start_date, Activity.moving_time_s, Activity.start_lat, Activity.start_lng,
                Activity.end_lat, Activity.end_lng, Activity.distance_km)
         .where(Activity.user_id == user_id, Activity.start_lat.is_not(None), Activity.start_lng.is_not(None),
                Activity.end_lat.is_not(None), Activity.end_lat != NO_END)
         .order_by(Activity.start_date.desc()).limit(MAX_RIDES))
    return [Ride(*r, tz) for r in db.execute(q)]


def commute_pairs(rides: list[Ride]) -> tuple[list[tuple[Ride, Ride]], list[tuple[float, float, float, float]]]:
    """Gibt (Paare Hinweg/Rückweg, Orte als (Heim-lat, Heim-lng, Arbeits-lat, Arbeits-lng)) zurück; nur bestätigte Muster."""
    by_day: dict[tuple, list[Ride]] = {}
    for r in rides:
        by_day.setdefault((r.local_start.date(), r.bike_id), []).append(r)
    found: list[tuple[Ride, Ride]] = []
    for day_rides in by_day.values():
        day_rides.sort(key=lambda r: r.start)
        for a, b in zip(day_rides, day_rides[1:]):
            gap_h = (b.start - a.end).total_seconds() / 3600
            if not MIN_STAND_H <= gap_h <= MAX_STAND_H or a.local_start.hour >= 12:
                continue
            if a.km < MIN_LEG_KM or b.km < MIN_LEG_KM or not 0.5 <= a.km / b.km <= 2.0:
                continue
            if _near(a.slat, a.slng, a.elat, a.elng, HOME_RADIUS_M):  # Rundfahrt, kein Weg zu einem anderen Ort
                continue
            if _near(a.elat, a.elng, b.slat, b.slng) and _near(b.elat, b.elng, a.slat, a.slng, HOME_RADIUS_M):
                found.append((a, b))
    # gleiche Orte an mehreren Tagen = Muster
    places: list[dict] = []
    for a, b in found:
        for p in places:
            if _near(a.slat, a.slng, p["h"][0], p["h"][1], HOME_RADIUS_M) and _near(a.elat, a.elng, p["w"][0], p["w"][1]):
                p["pairs"].append((a, b))
                break
        else:
            places.append({"h": (a.slat, a.slng), "w": (a.elat, a.elng), "pairs": [(a, b)]})
    confirmed = [p for p in places if len({a.local_start.date() for a, _ in p["pairs"]}) >= COMMUTE_MIN_DAYS]
    return [pair for p in confirmed for pair in p["pairs"]], [(p["h"][0], p["h"][1], p["w"][0], p["w"][1]) for p in confirmed]


# ---------- Standzeit im Freien ----------

def stand_credit(hours: float, wet_hours: float | None) -> float:
    """Nasse Kilometer für eine Standzeit im Freien; ohne Wetterdaten nur die Grundlast."""
    wet = (wet_hours or 0.0) * STAND_WET_KM_PER_WET_H
    return round(min(STAND_CAP_KM, wet + hours * STAND_BASE_KM_PER_H), 2)


def _stand_weather(items: list[weather_core.Item], fetch) -> dict[int, float | None]:
    """Regenstunden je Fahrt-ID (None = nicht abrufbar). Fehler und Limits überspringen die Fahrt, sie wird später erneut versucht."""
    out: dict[int, float | None] = {}
    if not items:
        return out
    if not settings.weather_enabled:
        return {it.activity_id: -1.0 for it in items}  # -1 = kein Wetter vorgesehen
    today = datetime.now(timezone.utc).date()
    with httpx.Client(headers={"User-Agent": "BikeHelper (self-hosted)"}, timeout=30) as client:
        for w in weather_core.plan_windows(items, today):
            try:
                series = fetch(client, w)
            except weather_service.RateLimited:
                break
            except Exception as e:
                log.warning("Wetterabruf für Standzeit fehlgeschlagen: %s", e)
                continue
            for it in w.items:
                s = weather_core.summarize(series, it.start, it.duration_s) if series else None
                out[it.activity_id] = None if s is None else (s.wet_minutes or 0.0) / 60
    return out


def apply_stands(db: Session, user: User, pairs: list[tuple[Ride, Ride]], fetch=weather_service.fetch_window) -> int:
    """Bewertet die Standzeit zwischen Hin- und Rückweg (nur bei Einstellung „im Freien“). Gibt die Zahl neu bewerteter Fahrten zurück."""
    if user.work_storage != "outdoor":
        return 0
    open_ids = set(db.scalars(select(Activity.id).where(Activity.user_id == user.id, Activity.stand_status.is_(None))))
    todo = [(a, b) for a, b in pairs if a.id in open_ids and a.bike_id is not None]
    items = [weather_core.Item(a.id, a.elat, a.elng, a.end, int((b.start - a.end).total_seconds())) for a, b in todo]
    weather = _stand_weather(items, fetch)
    done = 0
    for a, b in todo:
        if a.id not in weather:
            continue  # später erneut
        hours = round((b.start - a.end).total_seconds() / 3600, 2)
        wet_h = weather[a.id]
        has_weather = wet_h is not None and wet_h >= 0
        db.execute(update(Activity).where(Activity.id == a.id).values(
            stand_h=hours, stand_wet_km=stand_credit(hours, wet_h if has_weather else None), stand_status="ok" if has_weather else "none"))
        done += 1
    db.commit()
    return done


def clear_stands(db: Session, user_id: int) -> None:
    db.execute(update(Activity).where(Activity.user_id == user_id, Activity.stand_status.is_not(None))
               .values(stand_h=None, stand_wet_km=None, stand_status=None))
    db.commit()


# ---------- Tags ----------

def _set_auto_tag(db: Session, user_id: int, activity_id: int, tag: str, reason: str) -> bool:
    if db.get(ActivityTag, (activity_id, tag)) is not None:
        return False
    db.add(ActivityTag(activity_id=activity_id, tag=tag, user_id=user_id, state="auto", reason=reason[:300]))
    return True


def tag_commutes(db: Session, user_id: int, rides: list[Ride], pairs: list[tuple[Ride, Ride]], places: list[tuple]) -> int:
    n = 0
    ids = {r.id for pair in pairs for r in pair}
    for r in rides:  # auch einzelne Wege zwischen den bekannten Orten (z. B. Rückweg mit der Bahn)
        if r.id in ids:
            continue
        for hl, hg, wl, wg in places:
            fwd = _near(r.slat, r.slng, hl, hg, HOME_RADIUS_M) and _near(r.elat, r.elng, wl, wg)
            back = _near(r.slat, r.slng, wl, wg) and _near(r.elat, r.elng, hl, hg, HOME_RADIUS_M)
            if fwd or back:
                ids.add(r.id)
                break
    for rid in ids:
        if _set_auto_tag(db, user_id, rid, COMMUTE_TAG, "Gleicher Hin- und Rückweg an mehreren Tagen (Arbeitsweg)"):
            n += 1
    db.commit()
    return n


def _similar(a: Ride, b: Ride) -> bool:
    if not _near(a.slat, a.slng, b.slat, b.slng) or not _near(a.elat, a.elng, b.elat, b.elng):
        return False
    if a.km and b.km and abs(a.km - b.km) > TAG_LENGTH_TOLERANCE * max(a.km, b.km):
        return False
    gap = abs((a.local_start.hour * 60 + a.local_start.minute) - (b.local_start.hour * 60 + b.local_start.minute))
    if min(gap, 1440 - gap) > TAG_TIME_TOLERANCE_MIN:
        return False
    return (a.local_start.weekday() >= 5) == (b.local_start.weekday() >= 5)


def learn_tags(db: Session, user_id: int, rides: list[Ride]) -> int:
    """Vergibt Tags, die du bei ähnlichen Fahrten gesetzt hast, auch bei weiteren ähnlichen Fahrten."""
    rows = db.execute(select(ActivityTag.activity_id, ActivityTag.tag, ActivityTag.state).where(ActivityTag.user_id == user_id)).all()
    by_id = {r.id: r for r in rides}
    have: dict[str, set[int]] = {}
    pos: dict[str, list[Ride]] = {}
    neg: dict[str, list[Ride]] = {}
    for aid, tag, state in rows:
        have.setdefault(tag, set()).add(aid)
        r = by_id.get(aid)
        if r is None:
            continue
        if state == "manual":
            pos.setdefault(tag, []).append(r)
        elif state == "rejected":
            neg.setdefault(tag, []).append(r)
    n = 0
    for tag, examples in pos.items():
        if len(examples) < TAG_MIN_EXAMPLES:
            continue
        for r in rides:
            if r.id in have[tag]:
                continue
            p = sum(1 for e in examples if _similar(r, e))
            if p < TAG_MIN_EXAMPLES:
                continue
            q = sum(1 for e in neg.get(tag, []) if _similar(r, e))
            if p / (p + q) >= TAG_SHARE:
                if _set_auto_tag(db, user_id, r.id, tag, f"{p} ähnliche Fahrten (gleicher Start und Ziel, ähnliche Länge und Tageszeit) hast du so getaggt"):
                    n += 1
    db.commit()
    return n


# ---------- Ablauf ----------

_lock = threading.Lock()  # nie zwei Läufe gleichzeitig (sonst vergeben beide dieselben Tags)


def run_for_user(db: Session, user: User, fetch=weather_service.fetch_window) -> dict:
    with _lock:
        return _run_for_user(db, user, fetch)


def _run_for_user(db: Session, user: User, fetch) -> dict:
    while fill_end_points(db, user.id) >= 300:
        pass
    tz = get_tz(settings.timezone)
    rides = _load_rides(db, user.id, tz)
    pairs, places = commute_pairs(rides)
    tagged = tag_commutes(db, user.id, rides, pairs, places) if pairs else 0
    stands = apply_stands(db, user, pairs, fetch)
    learned = learn_tags(db, user.id, rides) if rides else 0
    return {"commute_pairs": len(pairs), "commute_tags": tagged, "stands": stands, "learned": learned}


def run(user_id: int) -> None:
    try:
        with SessionLocal() as db:
            user = db.get(User, user_id)
            if user is not None:
                run_for_user(db, user)
    except Exception:
        log.exception("Gewohnheiten konnten nicht ausgewertet werden")


def trigger(user_id: int) -> None:
    threading.Thread(target=run, args=(user_id,), daemon=True, name="habits").start()


def run_all() -> None:
    with SessionLocal() as db:
        ids = db.scalars(select(Activity.user_id).distinct()).all()
    for uid in ids:
        run(uid)

