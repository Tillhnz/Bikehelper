"""Radvorschläge für Fahrten ohne Rad, abgeleitet aus bereits zugeordneten Fahrten.

Zwei Hinweise, in dieser Reihenfolge:
1. Gleicher Radname (Strava-Export, intervals.icu): Wurden Fahrten mit diesem Namen fast immer demselben Rad zugeordnet, ist das der Vorschlag.
2. Ähnliche Fahrten: gleicher Startort (etwa 400 m), ähnliche Länge (±35 %) und ähnliche Tageszeit (±2,5 h). Gehören mindestens 3 solche
   Fahrten und mindestens 75 % davon zu einem Rad, ist das der Vorschlag.
Das ist eine Schätzung und wird nie automatisch übernommen.
"""
from __future__ import annotations

import math
from collections import Counter

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Activity, Bike

GEAR_SHARE = 0.8
NEIGHBOR_MIN = 3
NEIGHBOR_SHARE = 0.75
RADIUS_M = 400
LENGTH_TOLERANCE = 0.35
TIME_TOLERANCE_MIN = 150


def _minutes(dt) -> int:
    return dt.hour * 60 + dt.minute


def _close(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> bool:
    dy = (a_lat - b_lat) * 111_320
    dx = (a_lng - b_lng) * 111_320 * math.cos(math.radians(a_lat))
    return dx * dx + dy * dy <= RADIUS_M * RADIUS_M


def suggest_bikes(db: Session, user_id: int, targets: list[Activity]) -> dict[int, dict]:
    """Gibt je Fahrt-ID einen Vorschlag {bike_id, bike_name, reason} zurück; Fahrten ohne klaren Hinweis fehlen."""
    bikes = {b.id: b for b in db.scalars(select(Bike).where(Bike.user_id == user_id, Bike.retired.is_(False)))}
    if not bikes or not targets:
        return {}
    cols = (Activity.bike_id, Activity.gear_name, Activity.start_lat, Activity.start_lng, Activity.distance_km, Activity.start_date)
    assigned = [r for r in db.execute(select(*cols).where(Activity.user_id == user_id, Activity.bike_id.is_not(None))) if r[0] in bikes]
    if not assigned:
        return {}
    by_gear: dict[str, Counter] = {}
    for bike_id, gear, *_ in assigned:
        if gear:
            by_gear.setdefault(gear.strip().lower(), Counter())[bike_id] += 1
    located = [r for r in assigned if r[2] is not None and r[3] is not None and r[4]]

    out: dict[int, dict] = {}
    for a in targets:
        gear = (a.gear_name or "").strip().lower()
        counts = by_gear.get(gear) if gear else None
        if counts:
            bike_id, n = counts.most_common(1)[0]
            total = sum(counts.values())
            if n / total >= GEAR_SHARE:
                out[a.id] = {"bike_id": bike_id, "bike_name": bikes[bike_id].name,
                             "reason": f"{n} von {total} Fahrten mit dem Radnamen „{a.gear_name}“ gehören zu diesem Rad"}
                continue
        if a.start_lat is None or a.start_lng is None or not a.distance_km:
            continue
        near = Counter()
        for bike_id, _g, lat, lng, dist, start in located:
            if abs(dist - a.distance_km) > LENGTH_TOLERANCE * a.distance_km:
                continue
            gap = abs(_minutes(start) - _minutes(a.start_date))
            if min(gap, 1440 - gap) > TIME_TOLERANCE_MIN:
                continue
            if _close(a.start_lat, a.start_lng, lat, lng):
                near[bike_id] += 1
        total = sum(near.values())
        if total >= NEIGHBOR_MIN:
            bike_id, n = near.most_common(1)[0]
            if n / total >= NEIGHBOR_SHARE:
                out[a.id] = {"bike_id": bike_id, "bike_name": bikes[bike_id].name,
                             "reason": f"{n} von {total} ähnlichen Fahrten (gleicher Start, ähnliche Länge und Tageszeit) gehören zu diesem Rad"}
    return out
