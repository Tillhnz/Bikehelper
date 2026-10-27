"""Radvorschläge für Fahrten ohne Rad, abgeleitet aus bereits zugeordneten Fahrten.

Die Vorschläge sind Schätzungen und werden nie automatisch übernommen. Hinweise in dieser Reihenfolge:
0. Es gibt nur ein Rad: Das wird vorgeschlagen.
1. Gleicher Radname (Strava-Export, intervals.icu): Gehören fast alle Fahrten mit diesem Namen zu einem Rad, ist das der Vorschlag.
2. Ähnliche Fahrten: gleicher Startort (etwa 400 m), ähnliche Länge (±35 %) und Tageszeit (±2,5 h).
3. Merkmale der Aufzeichnung, verglichen mit dem, was bei jedem Rad bisher typisch war (Naive-Bayes-Schätzung):
   Leistungs- und Trittfrequenzdaten vorhanden oder nicht, Datenquelle, Fahrtart (Gravel, Gelände, Straße, E-Bike, soweit die
   Datei oder der Export sie nennt) und Durchschnittstempo. Ein Untergrund steht in GPX/FIT nicht drin; die Fahrtart und das
   Tempo sind nur Anhaltspunkte dafür. Es wird nur vorgeschlagen, wenn ein Rad klar vorn liegt.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
from collections import Counter

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .database import SessionLocal
from .models import Activity, Bike

log = logging.getLogger("bikehelper.suggest")

GEAR_SHARE = 0.8
NEIGHBOR_MIN = 3
NEIGHBOR_SHARE = 0.75
RADIUS_M = 400
LENGTH_TOLERANCE = 0.35
TIME_TOLERANCE_MIN = 150
MODEL_MIN_RIDES = 8        # so viele zugeordnete Fahrten braucht ein Rad, damit es in die Schätzung eingeht
MODEL_CONFIDENCE = 0.9     # Mindestwahrscheinlichkeit für einen Vorschlag
MODEL_DAMPING = 0.5        # Merkmale sind nicht unabhängig; die Summe wird gedämpft, damit die Schätzung nicht übertreibt
MIN_SPEED_KMH_SIGMA = 2.0

SOURCE_TEXT = {"wahoo": "Wahoo", "intervals": "intervals.icu", "upload": "Datei-Upload", "strava_export": "Strava-Export"}
TERRAIN_TEXT = {"road": "Straße", "gravel": "Gravel", "mtb": "Gelände", "ebike": "E-Bike"}


def terrain_of(text: str | None) -> str | None:
    """Fahrtart aus dem Sporttyp (Strava „Gravel Ride“, FIT „cycling gravel_cycling“ …); None, wenn nichts Genaues drinsteht."""
    t = (text or "").lower().replace("_", " ").replace("-", " ")
    if not t:
        return None
    if "ebike" in t or "e bike" in t or "emountain" in t or "e mountain" in t:
        return "ebike"
    if "gravel" in t:
        return "gravel"
    if "mountain" in t or "mtb" in t:
        return "mtb"
    if "road" in t:
        return "road"
    return None


def features_from_details(details: dict | None) -> tuple[float, float]:
    """(Durchschnittsleistung, Durchschnittsfrequenz) aus den Auswertungsdaten; 0 = nicht aufgezeichnet."""
    d = details or {}
    return float(d.get("avg_power") or 0.0), float(d.get("avg_cadence") or 0.0)


def _minutes(dt) -> int:
    return dt.hour * 60 + dt.minute


def _close(a_lat: float, a_lng: float, b_lat: float, b_lng: float) -> bool:
    dy = (a_lat - b_lat) * 111_320
    dx = (a_lng - b_lng) * 111_320 * math.cos(math.radians(a_lat))
    return dx * dx + dy * dy <= RADIUS_M * RADIUS_M


def _speed(distance_km: float | None, moving_time_s: int | None) -> float | None:
    if not distance_km or not moving_time_s or distance_km < 1 or moving_time_s < 120:
        return None
    return distance_km / (moving_time_s / 3600)


def _cat_features(a) -> dict[str, str | None]:
    """Kategoriale Merkmale einer Fahrt (None = unbekannt, zählt nicht)."""
    return {
        "power": None if a.avg_power is None else ("ja" if a.avg_power > 0 else "nein"),
        "cadence": None if a.avg_cadence is None else ("ja" if a.avg_cadence > 0 else "nein"),
        "source": a.source or None,
        "terrain": a.terrain or None,  # "" (unbekannt) zählt nicht
    }


def _model_suggestion(assigned: list, bikes: dict[int, Bike], target) -> dict | None:
    by_bike: dict[int, list] = {}
    for r in assigned:
        by_bike.setdefault(r.bike_id, []).append(r)
    cands = {b: rows for b, rows in by_bike.items() if len(rows) >= MODEL_MIN_RIDES}
    if len(cands) < 2:
        return None
    total = sum(len(r) for r in cands.values())
    tf = _cat_features(target)
    ts = _speed(target.distance_km, target.moving_time_s)

    counters: dict[int, dict[str, Counter]] = {}
    speeds: dict[int, list[float]] = {}
    for b, rows in cands.items():
        counters[b] = {k: Counter() for k in tf}
        speeds[b] = []
        for r in rows:
            for k, v in _cat_features(r).items():
                if v is not None:
                    counters[b][k][v] += 1
            s = _speed(r.distance_km, r.moving_time_s)
            if s is not None:
                speeds[b].append(s)

    def logp(b: int, key: str, value: str) -> float:
        seen = {v for c in counters.values() for v in c[key]}
        k = len(seen | {value})
        c = counters[b][key]
        return math.log((c[value] + 1) / (sum(c.values()) + k))

    parts: dict[int, dict[str, float]] = {b: {} for b in cands}
    for b in cands:
        for key, value in tf.items():
            if value is not None:
                parts[b][key] = logp(b, key, value)
        sp = speeds[b]
        if ts is not None and len(sp) >= MODEL_MIN_RIDES:
            mu = sum(sp) / len(sp)
            sd = max(MIN_SPEED_KMH_SIGMA, math.sqrt(sum((x - mu) ** 2 for x in sp) / len(sp)))
            parts[b]["speed"] = -0.5 * ((ts - mu) / sd) ** 2 - math.log(sd)
    if not any(parts[b] for b in cands):
        return None

    score = {b: math.log(len(cands[b]) / total) + MODEL_DAMPING * sum(parts[b].values()) for b in cands}
    top = max(score.values())
    expo = {b: math.exp(s - top) for b, s in score.items()}
    z = sum(expo.values())
    ranked = sorted(cands, key=lambda b: -score[b])
    best, second = ranked[0], ranked[1]
    if expo[best] / z < MODEL_CONFIDENCE:
        return None

    # Begründung: die Merkmale, die das beste Rad am stärksten vom zweitbesten unterscheiden
    order = ["power", "cadence", "source", "terrain", "speed"]  # bei gleichem Gewicht zuerst die handfesten Merkmale nennen
    gains = sorted(((-round(parts[best].get(k, 0.0) - parts[second].get(k, 0.0), 3), order.index(k), k) for k in parts[best]))
    reasons = []
    for neg_gain, _, key in gains:
        if -neg_gain < 0.6 or len(reasons) >= 3:
            break
        reasons.append(_reason(key, tf.get(key), ts, best, second, cands, counters, speeds, bikes))
    if not reasons:
        return None
    return {"bike_id": best, "bike_name": bikes[best].name, "reason": "; ".join(reasons)}


def _share(counter: Counter, value: str) -> str:
    n = sum(counter.values())
    return f"{round(100 * counter[value] / n)} %" if n else "–"


def _reason(key, value, speed, best, second, cands, counters, speeds, bikes) -> str:
    other = bikes[second].name
    if key == "speed":
        mb = sum(speeds[best]) / len(speeds[best])
        mo = sum(speeds[second]) / len(speeds[second])
        return f"Tempo {speed:.0f} km/h passt zu Ø {mb:.0f} km/h dieses Rades (bei „{other}“ Ø {mo:.0f} km/h)"
    label = {"power": "Leistungsdaten", "cadence": "Trittfrequenzdaten", "source": "Datenquelle", "terrain": "Fahrtart"}[key]
    shown = SOURCE_TEXT.get(value, value) if key == "source" else TERRAIN_TEXT.get(value, value) if key == "terrain" else value
    if key in ("power", "cadence"):
        what = "vorhanden" if value == "ja" else "nicht vorhanden"
        return f"{label} {what}: {_share(counters[best][key], value)} der Fahrten dieses Rades, bei „{other}“ {_share(counters[second][key], value)}"
    return f"{label} {shown}: {_share(counters[best][key], value)} der Fahrten dieses Rades, bei „{other}“ {_share(counters[second][key], value)}"


def suggest_bikes(db: Session, user_id: int, targets: list[Activity]) -> dict[int, dict]:
    """Gibt je Fahrt-ID einen Vorschlag {bike_id, bike_name, reason} zurück; Fahrten ohne klaren Hinweis fehlen."""
    bikes = {b.id: b for b in db.scalars(select(Bike).where(Bike.user_id == user_id, Bike.retired.is_(False)))}
    if not bikes or not targets:
        return {}
    out: dict[int, dict] = {}
    if len(bikes) == 1:  # nur ein Rad: der naheliegende Vorschlag
        only = next(iter(bikes.values()))
        return {a.id: {"bike_id": only.id, "bike_name": only.name, "reason": "Du hast nur ein Rad"} for a in targets}

    cols = (Activity.bike_id, Activity.gear_name, Activity.start_lat, Activity.start_lng, Activity.distance_km, Activity.start_date,
            Activity.moving_time_s, Activity.avg_power, Activity.avg_cadence, Activity.source, Activity.terrain)
    assigned = [r for r in db.execute(select(*cols).where(Activity.user_id == user_id, Activity.bike_id.is_not(None))) if r.bike_id in bikes]
    if not assigned:
        return {}
    by_gear: dict[str, Counter] = {}
    for r in assigned:
        if r.gear_name:
            by_gear.setdefault(r.gear_name.strip().lower(), Counter())[r.bike_id] += 1
    located = [r for r in assigned if r.start_lat is not None and r.start_lng is not None and r.distance_km]

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
        if a.start_lat is not None and a.start_lng is not None and a.distance_km:
            near = Counter()
            for r in located:
                if abs(r.distance_km - a.distance_km) > LENGTH_TOLERANCE * a.distance_km:
                    continue
                gap = abs(_minutes(r.start_date) - _minutes(a.start_date))
                if min(gap, 1440 - gap) > TIME_TOLERANCE_MIN:
                    continue
                if _close(a.start_lat, a.start_lng, r.start_lat, r.start_lng):
                    near[r.bike_id] += 1
            total = sum(near.values())
            if total >= NEIGHBOR_MIN:
                bike_id, n = near.most_common(1)[0]
                if n / total >= NEIGHBOR_SHARE:
                    out[a.id] = {"bike_id": bike_id, "bike_name": bikes[bike_id].name,
                                 "reason": f"{n} von {total} ähnlichen Fahrten (gleicher Start, ähnliche Länge und Tageszeit) gehören zu diesem Rad"}
                    continue
        guess = _model_suggestion(assigned, bikes, a)
        if guess:
            out[a.id] = guess
    return out


# ---------- Merkmale für bestehende Fahrten nachtragen ----------

def backfill_features(limit: int = 200) -> int:
    """Trägt Leistungs-/Trittfrequenzwerte und Fahrtart für ältere Fahrten nach. Gibt die Zahl bearbeiteter Fahrten zurück."""
    with SessionLocal() as db:
        done = 0
        # Fahrtart: ein Update je vorhandenem Sporttyp
        for (sport,) in db.execute(select(Activity.sport_type).where(Activity.terrain.is_(None)).distinct()):
            db.execute(update(Activity).where(Activity.terrain.is_(None), Activity.sport_type == sport).values(terrain=terrain_of(sport) or ""))
        db.commit()
        rows = db.execute(select(Activity.id, Activity.details).where(Activity.avg_power.is_(None), Activity.details.is_not(None)).limit(limit)).all()
        for aid, raw in rows:
            try:
                power, cadence = features_from_details(json.loads(raw))
            except (ValueError, TypeError):
                power = cadence = 0.0
            db.execute(update(Activity).where(Activity.id == aid).values(avg_power=power, avg_cadence=cadence))
            done += 1
        db.commit()
        return done


def start_backfill() -> None:
    """Läuft einmal nach dem Start im Hintergrund, bis alle älteren Fahrten ausgewertet sind."""
    def work() -> None:
        time.sleep(30)
        try:
            while backfill_features() > 0:
                time.sleep(0.2)
        except Exception:
            log.exception("Merkmale für Radvorschläge konnten nicht nachgetragen werden")

    threading.Thread(target=work, daemon=True, name="suggest-backfill").start()
