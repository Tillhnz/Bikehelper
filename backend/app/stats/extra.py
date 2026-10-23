"""Weitere Statistiken: Belastung, Jahresrückblick, Jahresziele, Meilensteine. Reiner Rechenkern ohne Datenbank."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta

from .overview import Row, WEEKDAYS, _bucket, _r, local, streaks

EARTH_KM = 40_075.0
EVEREST_M = 8_849.0
MOON_KM = 384_400.0
SPEED_BUCKETS = [(0, 18, "< 18 km/h"), (18, 21, "18–21"), (21, 24, "21–24"), (24, 27, "24–27"), (27, 30, "27–30"), (30, 200, "> 30 km/h")]
CLIMB_BUCKETS = [(0, 5, "flach (<5)"), (5, 10, "leicht (5–10)"), (10, 15, "wellig (10–15)"), (15, 20, "hügelig (15–20)"), (20, 1000, "bergig (>20)")]
DAYPARTS = [(5, 10, "Morgens 5–10"), (10, 15, "Mittags 10–15"), (15, 19, "Nachm. 15–19"), (19, 24, "Abends 19–24"), (0, 5, "Nachts 0–5")]
SEASONS = {12: "Winter", 1: "Winter", 2: "Winter", 3: "Frühling", 4: "Frühling", 5: "Frühling",
           6: "Sommer", 7: "Sommer", 8: "Sommer", 9: "Herbst", 10: "Herbst", 11: "Herbst"}
MILESTONES = [500, 1000, 2500, 5000, 7500, 10_000, 15_000, 20_000, 25_000, 30_000, 40_075, 50_000, 75_000, 100_000]
CTL_DAYS, ATL_DAYS = 42, 7
LOAD_DAYS = 180


def ride_load(r: Row) -> float:
    """Geschätzte Belastung in Punkten, ohne Puls oder Leistung: Fahrzeit, Höhenmeter und Tempo über Grundtempo."""
    h = r.time_s / 3600
    speed = r.km / h if h > 0 else 0
    return h * 40 + (r.elev_m or 0) / 25 + h * max(0.0, speed - 18) * 1.5


def _local_rows(rows: list[Row], tz) -> list[tuple[datetime, Row]]:
    return sorted(((local(r.start, tz), r) for r in rows), key=lambda x: x[0])


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def load_series(local_rows, today: date, days: int = LOAD_DAYS) -> list[dict]:
    """Fitness (42 Tage), Ermüdung (7 Tage) und Form pro Tag, gleitende Mittel der täglichen Belastung."""
    if not local_rows:
        return []
    daily: dict[date, float] = defaultdict(float)
    for dt, r in local_rows:
        daily[dt.date()] += ride_load(r)
    d = min(daily)
    ctl = atl = 0.0
    out = []
    kc, ka = math.exp(-1 / CTL_DAYS), math.exp(-1 / ATL_DAYS)
    while d <= today:
        x = daily.get(d, 0.0)
        ctl = ctl * kc + x * (1 - kc)
        atl = atl * ka + x * (1 - ka)
        out.append({"date": d.isoformat(), "load": _r(x), "fitness": _r(ctl), "fatigue": _r(atl), "form": _r(ctl - atl)})
        d += timedelta(days=1)
    return out[-days:]


def weekly(local_rows, today: date, weeks: int = 26) -> list[dict]:
    first = _week_start(today) - timedelta(weeks=weeks - 1)
    agg = {first + timedelta(weeks=i): {"km": 0.0, "time_s": 0, "elev_m": 0.0, "rides": 0, "load": 0.0} for i in range(weeks)}
    for dt, r in local_rows:
        w = _week_start(dt.date())
        if w in agg:
            a = agg[w]
            a["km"] += r.km; a["time_s"] += r.time_s; a["elev_m"] += r.elev_m or 0; a["rides"] += 1; a["load"] += ride_load(r)
    return [{"week": w.isoformat(), "km": _r(a["km"]), "time_s": a["time_s"], "elev_m": _r(a["elev_m"], 0),
             "rides": a["rides"], "load": _r(a["load"], 0)} for w, a in agg.items()]


def longest_week_streak(days: set[date]) -> int:
    weeks = sorted({_week_start(d) for d in days})
    best = run = 1 if weeks else 0
    for a, b in zip(weeks, weeks[1:]):
        run = run + 1 if (b - a).days == 7 else 1
        best = max(best, run)
    return best


def milestones(local_rows) -> list[dict]:
    total = 0.0
    todo = list(MILESTONES)
    out = []
    for i, (dt, r) in enumerate(local_rows, 1):
        total += r.km
        while todo and total >= todo[0]:
            out.append({"km": todo.pop(0), "date": dt.date().isoformat(), "rides": i})
    return out


def _ride(dt: datetime, r: Row, value: float) -> dict:
    return {"id": r.id, "name": r.name, "date": dt.date().isoformat(), "value": _r(value)}


def build_extra(rows: list[Row], tz, today: date, bike_names: dict[int, str] | None = None) -> dict:
    bike_names = bike_names or {}
    lr = _local_rows(rows, tz)
    if not lr:
        return {"empty": True}
    days = {dt.date() for dt, _ in lr}

    month_km: dict[int, list[float]] = defaultdict(lambda: [0.0] * 12)
    bike_year: dict[str, dict[int, float]] = defaultdict(lambda: defaultdict(float))
    speed_b, climb_b, daypart_b, season_b = defaultdict(int), defaultdict(int), defaultdict(float), defaultdict(float)
    speed_month: dict[str, list[float]] = defaultdict(lambda: [0.0, 0.0])
    sport_total = 0.0
    for dt, r in lr:
        month_km[dt.year][dt.month - 1] += r.km
        bike_year[bike_names.get(r.bike_id, "ohne Rad")][dt.year] += r.km
        if r.time_s > 0 and r.km >= 5:
            speed_b[_bucket(r.km / (r.time_s / 3600), SPEED_BUCKETS)] += 1
            m = speed_month[dt.strftime("%Y-%m")]
            m[0] += r.km; m[1] += r.time_s
        if r.km >= 5 and r.elev_m is not None:
            climb_b[_bucket(r.elev_m / r.km, CLIMB_BUCKETS)] += 1
        for lo, hi, label in DAYPARTS:
            if lo <= dt.hour < hi:
                daypart_b[label] += r.time_s / 3600
                break
        season_b[SEASONS[dt.month]] += r.km
        sport_total += r.km

    years = sorted(month_km)
    total_km = sum(r.km for _, r in lr)
    total_elev = sum(r.elev_m or 0 for _, r in lr)
    ordered_days = sorted(days)
    gaps = [((b - a).days - 1, a, b) for a, b in zip(ordered_days, ordered_days[1:])]
    gap = max(gaps, default=None)
    loads = load_series(lr, today)
    week_load = weekly(lr, today)

    return {
        "load": {
            "series": loads,
            "weekly": week_load,
            "now": loads[-1] if loads else None,
            "note": "Geschätzt aus Fahrzeit, Höhenmetern und Tempo, ohne Puls oder Leistung.",
        },
        "month_matrix": {"years": years, "km": [[_r(v, 0) for v in month_km[y]] for y in years]},
        "bike_years": {
            "years": years,
            "bikes": [{"name": n, "km": [_r(by.get(y, 0.0), 0) for y in years], "total": _r(sum(by.values()), 0)}
                      for n, by in sorted(bike_year.items(), key=lambda kv: -sum(kv[1].values()))],
        },
        "speed_buckets": [{"label": b[2], "rides": speed_b.get(b[2], 0)} for b in SPEED_BUCKETS],
        "climb_buckets": [{"label": b[2], "rides": climb_b.get(b[2], 0)} for b in CLIMB_BUCKETS],
        "dayparts": [{"label": d[2], "hours": _r(daypart_b.get(d[2], 0.0))} for d in DAYPARTS],
        "seasons": [{"label": s, "km": _r(season_b.get(s, 0.0), 0)} for s in ("Frühling", "Sommer", "Herbst", "Winter")],
        "speed_by_month": [{"month": k, "avg_speed": _r(v[0] / (v[1] / 3600))} for k, v in sorted(speed_month.items())[-24:] if v[1] > 0],
        "milestones": milestones(lr),
        "top_rides": [_ride(dt, r, r.km) for dt, r in sorted(lr, key=lambda x: -x[1].km)[:10]],
        "top_climbs": [_ride(dt, r, r.elev_m or 0) for dt, r in sorted(lr, key=lambda x: -(x[1].elev_m or 0))[:10]],
        "breaks": {
            "longest_days": gap[0] if gap else 0,
            "from": gap[1].isoformat() if gap else None,
            "to": gap[2].isoformat() if gap else None,
            "since_last_ride": (today - ordered_days[-1]).days,
            "longest_week_streak": longest_week_streak(days),
            "longest_day_streak": streaks(days, today)[0],
        },
        "equivalents": {
            "earth_laps": _r(total_km / EARTH_KM, 2),
            "everests": _r(total_elev / EVEREST_M, 1),
            "moon_percent": _r(total_km / MOON_KM * 100, 1),
            "days_in_saddle": _r(sum(r.time_s for _, r in lr) / 86400, 1),
        },
        "totals": {"km": _r(total_km, 0), "elev_m": _r(total_elev, 0), "rides": len(lr)},
    }


def _sum(rs: list[Row]) -> dict:
    km = sum(r.km for r in rs)
    t = sum(r.time_s for r in rs)
    return {"km": _r(km), "rides": len(rs), "elev_m": _r(sum(r.elev_m or 0 for r in rs), 0), "time_s": t,
            "avg_speed": _r(km / (t / 3600)) if t else 0.0}


def _delta(now: float, before: float) -> float | None:
    return _r((now - before) / before * 100) if before else None


def build_review(rows: list[Row], tz, year: int, today: date, bike_names: dict[int, str] | None = None) -> dict:
    """Jahresrückblick: Kennzahlen des Jahres, Vergleich zum Vorjahr und einige Besonderheiten."""
    bike_names = bike_names or {}
    lr = _local_rows(rows, tz)
    mine = [(dt, r) for dt, r in lr if dt.year == year]
    if not mine:
        return {"empty": True, "year": year}
    prev = [r for dt, r in lr if dt.year == year - 1]
    cur_rows = [r for _, r in mine]
    cur, before = _sum(cur_rows), _sum(prev)

    by_month = [0.0] * 12
    by_wd = [0.0] * 7
    by_wd_n = [0] * 7
    by_bike: dict[str, float] = defaultdict(float)
    for dt, r in mine:
        by_month[dt.month - 1] += r.km
        by_wd[dt.weekday()] += r.km
        by_wd_n[dt.weekday()] += 1
        by_bike[bike_names.get(r.bike_id, "ohne Rad")] += r.km
    best_month = max(range(12), key=lambda i: by_month[i])
    best_wd = max(range(7), key=lambda i: by_wd[i])
    days = {dt.date() for dt, _ in mine}
    ordered = sorted(days)
    gaps = [(b - a).days - 1 for a, b in zip(ordered, ordered[1:])]

    seen_before: set = set()
    for dt, r in lr:
        if dt.year < year and r.tiles:
            seen_before |= r.tiles
    seen_now: set = set()
    for _, r in mine:
        if r.tiles:
            seen_now |= r.tiles

    rated = [(dt, r) for dt, r in mine if r.temp_c is not None]
    wet_km = sum(r.km * min(1.0, (r.wet_minutes or 0) * 60 / r.time_s) for _, r in mine if r.time_s and r.wet_minutes)
    elapsed = ((min(today, date(year, 12, 31)) - date(year, 1, 1)).days + 1)
    return {
        "year": year,
        "totals": cur,
        "previous": before if prev else None,
        "delta": {"km": _delta(cur["km"], before["km"]), "elev_m": _delta(cur["elev_m"], before["elev_m"]),
                  "rides": _delta(cur["rides"], before["rides"])} if prev else None,
        "months": [{"month": i + 1, "km": _r(v, 0)} for i, v in enumerate(by_month)],
        "best_month": {"month": best_month + 1, "km": _r(by_month[best_month], 0)},
        "best_weekday": {"label": WEEKDAYS[best_wd], "km": _r(by_wd[best_wd], 0), "rides": by_wd_n[best_wd]},
        "favorite_bike": (lambda kv: {"name": kv[0], "km": _r(kv[1], 0)})(max(by_bike.items(), key=lambda kv: kv[1])),
        "active_days": len(days),
        "active_share": _r(len(days) / elapsed * 100, 0) if elapsed else 0,
        "longest_break_days": max(gaps, default=0),
        "longest_streak_days": streaks(days, today)[0],
        "rides_100": sum(1 for r in cur_rows if r.km >= 100),
        "rides_150": sum(1 for r in cur_rows if r.km >= 150),
        "early_rides": sum(1 for dt, _ in mine if dt.hour < 7),
        "winter_rides": sum(1 for dt, _ in mine if dt.month in (12, 1, 2)),
        "longest_ride": max((_ride(dt, r, r.km) for dt, r in mine), key=lambda x: x["value"]),
        "most_climbing": max((_ride(dt, r, r.elev_m or 0) for dt, r in mine), key=lambda x: x["value"]),
        "coldest": min((_ride(dt, r, r.temp_c) for dt, r in rated), key=lambda x: x["value"], default=None),
        "hottest": max((_ride(dt, r, r.temp_c) for dt, r in rated), key=lambda x: x["value"], default=None),
        "wet_km": _r(wet_km, 0),
        "new_tiles": len(seen_now - seen_before),
        "tiles": len(seen_now),
        "top_rides": [_ride(dt, r, r.km) for dt, r in sorted(mine, key=lambda x: -x[1].km)[:5]],
        "equivalents": {"earth_percent": _r(cur["km"] / EARTH_KM * 100, 1), "everests": _r(cur["elev_m"] / EVEREST_M, 1)},
    }


GOAL_METRICS = ("km", "elev_m", "rides", "time_h")


def goals_progress(rows: list[Row], tz, year: int, today: date, targets: dict[str, float]) -> list[dict]:
    """Fortschritt je Ziel mit Vergleich zum gleichmäßigen Plan und Hochrechnung bis Jahresende."""
    mine = [(dt, r) for dt, r in _local_rows(rows, tz) if dt.year == year]
    start, end = date(year, 1, 1), date(year, 12, 31)
    total_days = (end - start).days + 1
    elapsed = max(1, min((today - start).days + 1, total_days)) if today >= start else 0
    left_days = max(0, (end - today).days) if today <= end else 0
    done_all = {
        "km": sum(r.km for _, r in mine),
        "elev_m": sum(r.elev_m or 0 for _, r in mine),
        "rides": float(len(mine)),
        "time_h": sum(r.time_s for _, r in mine) / 3600,
    }
    out = []
    for metric in GOAL_METRICS:
        target = targets.get(metric)
        if not target:
            continue
        done = done_all[metric]
        plan = target * elapsed / total_days
        projected = done / elapsed * total_days if elapsed else 0.0
        remaining = max(0.0, target - done)
        reached = None
        if done >= target:
            acc = 0.0
            for dt, r in mine:
                acc += {"km": r.km, "elev_m": r.elev_m or 0, "rides": 1.0, "time_h": r.time_s / 3600}[metric]
                if acc >= target:
                    reached = dt.date().isoformat()
                    break
        out.append({
            "metric": metric, "target": target, "done": _r(done), "percent": _r(done / target * 100),
            "plan": _r(plan), "ahead": _r(done - plan), "projected": _r(projected),
            "remaining": _r(remaining), "per_week_needed": _r(remaining / (left_days / 7)) if left_days else None,
            "reached_on": reached,
            "on_track": projected >= target,
        })
    return out
