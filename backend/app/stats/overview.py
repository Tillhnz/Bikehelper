"""Statistiken über alle Fahrten. Reiner Rechenkern: bekommt einfache Datensätze, keine Datenbank."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from . import tiles as T

DISTANCE_BUCKETS = [(0, 25, "< 25 km"), (25, 50, "25–50"), (50, 75, "50–75"), (75, 100, "75–100"),
                    (100, 150, "100–150"), (150, 10_000, "> 150 km")]
TEMP_BUCKETS = [(-100, 5, "< 5 °C"), (5, 10, "5–10"), (10, 15, "10–15"), (15, 20, "15–20"),
                (20, 25, "20–25"), (25, 100, "> 25 °C")]
WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


@dataclass
class Row:
    id: int
    name: str
    bike_id: int | None
    start: datetime          # UTC, ohne Zeitzone
    km: float
    time_s: int
    elev_m: float
    temp_c: float | None = None
    precip_mm: float | None = None
    wet_minutes: float | None = None
    weather_status: str | None = None
    tiles: set | None = None
    wind_kmh: float | None = None
    headwind_kmh: float | None = None  # mittlerer Gegenwind entlang der Strecke (negativ = Rückenwind)
    avg_power: float | None = None
    terrain: str | None = None
    curve: dict | None = None  # beste Leistung je Dauer (Sekunden -> Watt), siehe stats/deep.py
    curve_approx: bool = False
    np: float | None = None  # normalisierte Leistung, wenn aus dem Sekundenverlauf bekannt


def get_tz(name: str):
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return timezone.utc


def local(dt: datetime, tz) -> datetime:
    return dt.replace(tzinfo=timezone.utc).astimezone(tz).replace(tzinfo=None)


def _r(v: float, n: int = 1) -> float:
    return round(v, n)


def streaks(days: set[date], today: date) -> tuple[int, int]:
    """(längste Serie, aktuelle Serie) aufeinanderfolgender Tage mit Fahrt."""
    if not days:
        return 0, 0
    ordered = sorted(days)
    best = run = 1
    for a, b in zip(ordered, ordered[1:]):
        run = run + 1 if (b - a).days == 1 else 1
        best = max(best, run)
    cur = 0
    d = today if today in days else today - timedelta(days=1)
    while d in days:
        cur += 1
        d -= timedelta(days=1)
    return best, cur


def _bucket(value: float, buckets) -> str | None:
    for lo, hi, label in buckets:
        if lo <= value < hi:
            return label
    return None


def build_overview(rows: list[Row], tz, today: date, bike_names: dict[int, str] | None = None) -> dict:
    bike_names = bike_names or {}
    if not rows:
        return {"empty": True}

    rows = sorted(rows, key=lambda r: r.start)
    loc = [(r, local(r.start, tz)) for r in rows]

    total_km = sum(r.km for r in rows)
    total_s = sum(r.time_s for r in rows)
    total_elev = sum(r.elev_m for r in rows)
    days = {d.date() for _, d in loc}
    longest, cur = streaks(days, today)

    by_year: dict[int, dict] = defaultdict(lambda: {"km": 0.0, "rides": 0, "elev_m": 0.0, "time_s": 0})
    by_month: dict[str, dict] = defaultdict(lambda: {"km": 0.0, "rides": 0})
    by_weekday = [{"label": w, "km": 0.0, "rides": 0} for w in WEEKDAYS]
    by_hour = [0] * 24
    dist_hist = {label: 0 for _, _, label in DISTANCE_BUCKETS}
    per_day: dict[str, float] = defaultdict(float)
    per_bike: dict[int | None, dict] = defaultdict(lambda: {"km": 0.0, "rides": 0, "time_s": 0, "elev_m": 0.0})
    cumulative: dict[int, list] = defaultdict(list)
    running: dict[int, float] = defaultdict(float)

    for r, d in loc:
        y = by_year[d.year]
        y["km"] += r.km; y["rides"] += 1; y["elev_m"] += r.elev_m; y["time_s"] += r.time_s
        m = by_month[d.strftime("%Y-%m")]
        m["km"] += r.km; m["rides"] += 1
        w = by_weekday[d.weekday()]
        w["km"] += r.km; w["rides"] += 1
        by_hour[d.hour] += 1
        b = _bucket(r.km, DISTANCE_BUCKETS)
        if b:
            dist_hist[b] += 1
        per_day[d.date().isoformat()] += r.km
        pb = per_bike[r.bike_id]
        pb["km"] += r.km; pb["rides"] += 1; pb["time_s"] += r.time_s; pb["elev_m"] += r.elev_m
        running[d.year] += r.km
        cumulative[d.year].append([d.timetuple().tm_yday, _r(running[d.year])])

    def pick(key, rs=loc):
        return max(rs, key=lambda t: key(t[0]))

    def rec(t, value):
        r, d = t
        return {"id": r.id, "name": r.name, "date": d.date().isoformat(), "value": value}

    longest_ride = pick(lambda r: r.km)
    most_climb = pick(lambda r: r.elev_m)
    day_best = max(per_day.items(), key=lambda kv: kv[1])
    fast = [t for t in loc if t[0].time_s > 600 and t[0].km >= 10]
    fastest = max(fast, key=lambda t: t[0].km / t[0].time_s) if fast else None

    records = {
        "longest_ride": rec(longest_ride, _r(longest_ride[0].km)),
        "most_climbing": rec(most_climb, round(most_climb[0].elev_m)),
        "longest_time": rec(pick(lambda r: r.time_s), pick(lambda r: r.time_s)[0].time_s),
        "best_day_km": {"date": day_best[0], "value": _r(day_best[1])},
        "fastest_avg": rec(fastest, _r(fastest[0].km / fastest[0].time_s * 3600)) if fastest else None,
    }

    # Kacheln
    all_tiles: set = set()
    per_year_tiles: dict[int, set] = defaultdict(set)
    for r, d in loc:
        if r.tiles:
            all_tiles |= r.tiles
            per_year_tiles[d.year] |= r.tiles
    size, at = T.max_square(all_tiles)
    tiles_block = {
        "count": len(all_tiles),
        "max_square": size,
        "max_square_at": list(at) if at else None,
        "max_cluster": T.max_cluster(all_tiles),
        "by_year_new": {},
    }
    seen: set = set()
    for y in sorted(per_year_tiles):
        tiles_block["by_year_new"][y] = len(per_year_tiles[y] - seen)
        seen |= per_year_tiles[y]

    # Wetter
    wx = [r for r in rows if r.weather_status in ("ok", "prelim") and r.temp_c is not None]
    temp_hist = {label: {"rides": 0, "km": 0.0} for _, _, label in TEMP_BUCKETS}
    for r in wx:
        b = _bucket(r.temp_c, TEMP_BUCKETS)
        if b:
            temp_hist[b]["rides"] += 1
            temp_hist[b]["km"] += r.km
    wet_rows = [r for r in rows if r.wet_minutes is not None and r.time_s > 0]
    wet_km = sum(r.km * min(1.0, r.wet_minutes * 60 / r.time_s) for r in wet_rows)
    wet_km_total_base = sum(r.km for r in wet_rows)
    rainy_rides = sum(1 for r in wet_rows if r.wet_minutes >= 5)
    coldest = min(wx, key=lambda r: r.temp_c) if wx else None
    hottest = max(wx, key=lambda r: r.temp_c) if wx else None
    weather = {
        "rides_with_weather": len(wx),
        "coverage": _r(len(wx) / len(rows) * 100),
        "avg_temp": _r(sum(r.temp_c for r in wx) / len(wx)) if wx else None,
        "wet_km": _r(wet_km),
        "wet_share": _r(wet_km / wet_km_total_base * 100) if wet_km_total_base else None,
        "rainy_rides": rainy_rides,
        "total_precip_mm": _r(sum(r.precip_mm or 0 for r in wx)),
        "by_temp": [{"label": k, **{"rides": v["rides"], "km": _r(v["km"])}} for k, v in temp_hist.items()],
        "coldest": rec((coldest, local(coldest.start, tz)), coldest.temp_c) if coldest else None,
        "hottest": rec((hottest, local(hottest.start, tz)), hottest.temp_c) if hottest else None,
    }

    return {
        "empty": False,
        "totals": {
            "rides": len(rows), "km": _r(total_km), "time_s": total_s, "elev_m": round(total_elev),
            "active_days": len(days), "avg_km": _r(total_km / len(rows)),
            "avg_speed": _r(total_km / total_s * 3600) if total_s else None,
            "first": loc[0][1].date().isoformat(), "last": loc[-1][1].date().isoformat(),
        },
        "years": [{"year": y, **{k: (_r(v) if isinstance(v, float) else v) for k, v in d.items()}}
                  for y, d in sorted(by_year.items())],
        "months": [{"month": k, "km": _r(v["km"]), "rides": v["rides"]} for k, v in sorted(by_month.items())],
        "weekdays": [{"label": w["label"], "km": _r(w["km"]), "rides": w["rides"]} for w in by_weekday],
        "hours": by_hour,
        "distance_buckets": [{"label": k, "rides": v} for k, v in dist_hist.items()],
        "daily": {k: _r(v, 2) for k, v in sorted(per_day.items())},
        "cumulative": {str(y): v for y, v in sorted(cumulative.items())},
        "bikes": [{"bike_id": k, "name": bike_names.get(k, "Ohne Rad") if k is not None else "Ohne Rad",
                   "km": _r(v["km"]), "rides": v["rides"], "time_s": v["time_s"], "elev_m": round(v["elev_m"])}
                  for k, v in sorted(per_bike.items(), key=lambda kv: -kv[1]["km"])],
        "records": records,
        "streaks": {"longest_days": longest, "current_days": cur},
        "tiles": tiles_block,
        "weather": weather,
    }
