"""Tiefere Auswertungen: Leistung und FTP, Bedingungen, Muster, Radvergleich, Stammstrecken, Prognose.

Reiner Rechenkern ohne Datenbank (außer der Prognose, die fertige Wartungszustände bekommt).
"""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from statistics import median

from .overview import Row, WEEKDAYS, _bucket, _r, local
from .extra import DAYPARTS, SEASONS

CURVE_SECONDS = [5, 30, 60, 300, 1200, 3600]
CURVE_LABELS = {5: "5 s", 30: "30 s", 60: "1 min", 300: "5 min", 1200: "20 min", 3600: "60 min"}
FTP_WINDOW_DAYS = 90
# Leistungsbereiche nach Coggan, Anteile der FTP
ZONES = [(0, 0.55, "Z1 Erholung"), (0.55, 0.75, "Z2 Grundlage"), (0.75, 0.90, "Z3 Tempo"), (0.90, 1.05, "Z4 Schwelle"),
         (1.05, 1.20, "Z5 VO2max"), (1.20, 1.50, "Z6 Anaerob"), (1.50, 9.99, "Z7 Sprint")]
WIND_BUCKETS = [(0, 10, "< 10 km/h"), (10, 20, "10–20"), (20, 30, "20–30"), (30, 200, "> 30 km/h")]
TEMP_BUCKETS = [(-100, 5, "< 5 °C"), (5, 10, "5–10"), (10, 15, "10–15"), (15, 20, "15–20"), (20, 25, "20–25"), (25, 100, "> 25 °C")]
MIN_BUCKET_RIDES = 3  # darunter ist ein Durchschnitt zu zufällig


def _speed(r: Row) -> float | None:
    if r.km < 5 or r.time_s < 900:
        return None
    return r.km / (r.time_s / 3600)


def curve_from_profile(details: dict | None) -> dict | None:
    """Näherung der Leistungskurve (>= 5 min) für Fahrten, die vor dieser Funktion importiert wurden.

    Aus dem verdichteten Verlauf (rund 300 Abschnitte mit Leistung und Tempo) lässt sich die Dauer je Abschnitt
    schätzen. Für Zeiträume ab 5 Minuten ist das brauchbar, für Sprints nicht.
    """
    prof = (details or {}).get("profile") or {}
    d, s, p = prof.get("d"), prof.get("s"), prof.get("p")
    if not d or not s or not p:
        return None
    segs = []  # (Sekunden, Watt)
    prev = 0.0
    for dist, spd, pw in zip(d, s, p):
        step = (dist - prev) * 1000
        prev = dist
        if pw is None or not spd or spd <= 1 or step <= 0:
            segs.append((step / 4.0 if step > 0 else 0.0, 0.0))  # Stillstand: grobe Pausendauer, 0 W
            continue
        segs.append((step / (spd / 3.6), float(pw)))
    out = {}
    for dur in (300, 1200, 3600):
        best = 0.0
        lo = 0
        t = e = 0.0
        found = False
        for hi in range(len(segs)):
            t += segs[hi][0]
            e += segs[hi][0] * segs[hi][1]
            while lo < hi and t - segs[lo][0] >= dur:
                t -= segs[lo][0]
                e -= segs[lo][0] * segs[lo][1]
                lo += 1
            if t >= dur:
                found = True
                best = max(best, e / t)
        if found:
            out[str(dur)] = round(best)
    return out or None


def ride_curve(details: dict | None) -> tuple[dict | None, bool]:
    """(Kurve, ungefähr?) einer Fahrt."""
    if not details:
        return None, False
    pc = details.get("pc")
    if pc:
        return pc, False
    return curve_from_profile(details), True


def estimate_ftp(curve: dict) -> tuple[float | None, str | None]:
    """FTP aus einer Bestwerte-Kurve: 95 % der besten 20 Minuten, mindestens die beste Stunde."""
    p20, p60 = curve.get(1200), curve.get(3600)
    cands = []
    if p20:
        cands.append((0.95 * p20, "95 % der besten 20 Minuten"))
    if p60:
        cands.append((float(p60), "beste 60 Minuten"))
    if not cands:
        return None, None
    return max(cands, key=lambda x: x[0])


def _best_curve(items: list[tuple[date, dict, bool]]) -> dict[int, dict]:
    best: dict[int, dict] = {}
    for day, curve, approx in items:
        for k, w in curve.items():
            k = int(k)
            if k not in best or w > best[k]["watts"]:
                best[k] = {"watts": w, "date": day.isoformat(), "approx": approx}
    return best


def build_power(rows: list[Row], tz, today: date, weight_kg: float | None) -> dict:
    """Leistungskurve, FTP-Schätzung und Verlauf, Zonen sowie eine leistungsbasierte Form-Kurve."""
    items = []  # (lokaler Tag, Kurve, ungefähr, Row)
    for r in rows:
        if not r.curve:
            continue
        curve = {int(k): v for k, v in r.curve.items()}
        approx = r.curve_approx
        items.append((local(r.start, tz).date(), curve, approx, r))
    powered = [r for r in rows if r.avg_power and r.avg_power > 0]
    out: dict = {
        "rides_with_power": len(powered), "weight_kg": weight_kg,
        "avg_power": _r(sum(r.avg_power for r in powered) / len(powered), 0) if powered else None,
    }
    if not items:
        return {**out, "has_curve": False}
    flat = [(d, c, a) for d, c, a, _ in items]
    recent_from = today - timedelta(days=FTP_WINDOW_DAYS)
    year_from = date(today.year, 1, 1)
    all_best = _best_curve(flat)
    recent = _best_curve([x for x in flat if x[0] >= recent_from])
    this_year = _best_curve([x for x in flat if x[0] >= year_from])
    curve_rows = []
    for k in CURVE_SECONDS:
        if k in all_best:
            curve_rows.append({
                "seconds": k, "label": CURVE_LABELS[k], "best": all_best[k]["watts"], "best_date": all_best[k]["date"],
                "recent": recent.get(k, {}).get("watts"), "year": this_year.get(k, {}).get("watts"),
                "approx": all_best[k]["approx"],
                "wkg": _r(all_best[k]["watts"] / weight_kg, 2) if weight_kg else None,
            })
    ftp, basis = estimate_ftp({k: v["watts"] for k, v in recent.items()})
    ftp_all, basis_all = estimate_ftp({k: v["watts"] for k, v in all_best.items()})
    stale = False
    if not ftp and ftp_all:  # keine Fahrt mit Leistung in den letzten 90 Tagen: letzter bekannter Wert, als veraltet gekennzeichnet
        ftp, basis, stale = ftp_all, basis_all, True
    # FTP-Verlauf: je Monat die Schätzung aus den Fahrten der 90 Tage bis Monatsende
    months = sorted({(d.year, d.month) for d, *_ in flat})
    history = []
    for y, m in months[-24:]:
        end = date(y + (m == 12), (m % 12) + 1, 1) - timedelta(days=1)
        win = [x for x in flat if end - timedelta(days=FTP_WINDOW_DAYS) < x[0] <= end]
        est, _ = estimate_ftp({k: v["watts"] for k, v in _best_curve(win).items()}) if win else (None, None)
        if est:
            history.append({"month": f"{y}-{m:02d}", "ftp": round(est)})
    out.update({
        "has_curve": True, "curve": curve_rows,
        "ftp": round(ftp) if ftp else None, "ftp_basis": basis, "ftp_stale": stale,
        "ftp_best": round(ftp_all) if ftp_all else None,
        "ftp_wkg": _r(ftp / weight_kg, 2) if ftp and weight_kg else None,
        "ftp_history": history,
        "approx_note": any(c["approx"] for c in curve_rows),
    })
    if ftp:
        out["zones"] = [
            {"name": n, "from": round(lo * ftp), "to": None if hi > 5 else round(hi * ftp)} for lo, hi, n in ZONES
        ]
        # Zeit in den Zonen aus der Durchschnittsleistung je Fahrt (grob, ohne Sekundenverlauf)
        zt = defaultdict(float)
        for r in powered:
            ratio = r.avg_power / ftp
            for lo, hi, n in ZONES:
                if lo <= ratio < hi:
                    zt[n] += r.time_s / 3600
                    break
        out["zone_hours"] = [{"name": n, "hours": _r(zt.get(n, 0.0))} for _, _, n in ZONES]
        out["form"] = power_form(rows, tz, today, ftp)
    return out


def ride_tss(r: Row, ftp: float) -> float:
    """Belastungspunkte einer Fahrt nach Coggan (TSS), genähert über die Durchschnittsleistung.

    Die normalisierte Leistung fehlt in den gespeicherten Daten. Der Faktor 1,06 gleicht die typische Unruhe einer
    Ausfahrt aus; echte Intervalleinheiten werden dadurch unterschätzt.
    """
    if not r.avg_power or r.avg_power <= 0 or ftp <= 0:
        return 0.0
    intensity = min(1.4, r.avg_power * 1.06 / ftp)
    return r.time_s / 3600 * intensity * intensity * 100


def power_form(rows: list[Row], tz, today: date, ftp: float, days: int = 120) -> list[dict]:
    """Fitness, Ermüdung und Form aus Fahrten mit Leistungsdaten (42 und 7 Tage)."""
    daily: dict[date, float] = defaultdict(float)
    for r in rows:
        t = ride_tss(r, ftp)
        if t:
            daily[local(r.start, tz).date()] += t
    if not daily:
        return []
    d = min(daily)
    ctl = atl = 0.0
    kc, ka = math.exp(-1 / 42), math.exp(-1 / 7)
    out = []
    while d <= today:
        x = daily.get(d, 0.0)
        ctl = ctl * kc + x * (1 - kc)
        atl = atl * ka + x * (1 - ka)
        out.append({"date": d.isoformat(), "tss": _r(x), "fitness": _r(ctl), "fatigue": _r(atl), "form": _r(ctl - atl)})
        d += timedelta(days=1)
    return out[-days:]


# ---------- Bedingungen ----------

def _avg_by(rows: list[Row], key, buckets, value) -> list[dict]:
    groups = defaultdict(list)
    for r in rows:
        k = key(r)
        v = value(r)
        if k is None or v is None:
            continue
        label = _bucket(k, buckets)
        if label:
            groups[label].append(v)
    out = []
    for _, _, label in buckets:
        vs = groups.get(label, [])
        out.append({"label": label, "rides": len(vs), "value": _r(sum(vs) / len(vs)) if len(vs) >= MIN_BUCKET_RIDES else None})
    return out


def build_conditions(rows: list[Row]) -> dict:
    """Tempo und Leistung bei Temperatur, Wind und Nässe, jeweils im Vergleich zum eigenen Durchschnitt."""
    ok = [r for r in rows if _speed(r) is not None]
    if not ok:
        return {"rides": 0}
    base = sum(_speed(r) for r in ok) / len(ok)
    wx = [r for r in ok if r.temp_c is not None]
    temp = _avg_by(wx, lambda r: r.temp_c, TEMP_BUCKETS, _speed)
    wind = _avg_by([r for r in ok if r.wind_kmh is not None], lambda r: r.wind_kmh, WIND_BUCKETS, _speed)
    pw_rows = [r for r in wx if r.avg_power and r.avg_power > 0]
    power = _avg_by(pw_rows, lambda r: r.temp_c, TEMP_BUCKETS, lambda r: r.avg_power)
    for rowset in (temp, wind):
        for b in rowset:
            b["delta_pct"] = _r((b["value"] / base - 1) * 100) if b["value"] else None
    wet = [r for r in ok if r.wet_minutes is not None and r.time_s > 0 and r.wet_minutes / (r.time_s / 60) >= 0.3]
    dry = [r for r in ok if r.wet_minutes is not None and r.time_s > 0 and r.wet_minutes / (r.time_s / 60) < 0.05]
    wet_dry = None
    if len(wet) >= MIN_BUCKET_RIDES and len(dry) >= MIN_BUCKET_RIDES:
        sw = sum(_speed(r) for r in wet) / len(wet)
        sd = sum(_speed(r) for r in dry) / len(dry)
        wet_dry = {"wet": _r(sw), "dry": _r(sd), "wet_rides": len(wet), "dry_rides": len(dry), "delta_pct": _r((sw / sd - 1) * 100)}
    best_t = max((b for b in temp if b["value"]), key=lambda b: b["value"], default=None)
    most_t = max(temp, key=lambda b: b["rides"], default=None)
    strong = [b for b in wind if b["value"]]
    return {
        "rides": len(ok), "weather_rides": len(wx), "base_speed": _r(base),
        "temp": temp, "wind": wind, "power_by_temp": power, "wet_dry": wet_dry,
        "fastest_temp": best_t["label"] if best_t else None,
        "most_rides_temp": most_t["label"] if most_t and most_t["rides"] else None,
        "wind_cost_pct": _r((strong[-1]["value"] / strong[0]["value"] - 1) * 100) if len(strong) >= 2 else None,
    }


# ---------- Muster ----------

def build_patterns(rows: list[Row], tz, today: date) -> dict:
    ok = sorted(((local(r.start, tz), r) for r in rows), key=lambda x: x[0])
    if not ok:
        return {"rides": 0}
    sp = [(dt, r, _speed(r)) for dt, r in ok if _speed(r) is not None]
    base = sum(s for *_, s in sp) / len(sp) if sp else None

    def group(keyf, labels):
        g = defaultdict(list)
        for dt, r, s in sp:
            g[keyf(dt)].append(s)
        return [{"label": lab, "rides": len(g.get(k, [])),
                 "speed": _r(sum(g[k]) / len(g[k])) if len(g.get(k, [])) >= MIN_BUCKET_RIDES else None}
                for k, lab in labels]

    weekday = group(lambda dt: dt.weekday(), list(enumerate(WEEKDAYS)))
    part_of = lambda dt: next((lab for lo, hi, lab in DAYPARTS if lo <= dt.hour < hi), None)
    daypart = group(part_of, [(lab, lab) for *_, lab in DAYPARTS])
    seasons = group(lambda dt: SEASONS[dt.month], [(s, s) for s in ("Frühling", "Sommer", "Herbst", "Winter")])
    # Tempo nach Ruhetagen
    days = sorted({dt.date() for dt, _ in ok})
    gaps = [(b - a).days - 1 for a, b in zip(days, days[1:])]
    last_ride_day: dict[date, date] = {}
    prev = None
    for d in days:
        last_ride_day[d] = prev
        prev = d
    rest = defaultdict(list)
    for dt, r, s in sp:
        p = last_ride_day.get(dt.date())
        k = None if p is None else min(3, (dt.date() - p).days - 1)
        if k is not None:
            rest[k].append(s)
    rest_rows = [{"label": lab, "rides": len(rest.get(k, [])),
                  "speed": _r(sum(rest[k]) / len(rest[k])) if len(rest.get(k, [])) >= MIN_BUCKET_RIDES else None}
                 for k, lab in ((0, "Tag danach"), (1, "1 Ruhetag"), (2, "2 Ruhetage"), (3, "3+ Ruhetage"))]
    weeks = defaultdict(int)
    for d in days:
        weeks[d - timedelta(days=d.weekday())] += 1
    best_wd = max((w for w in weekday if w["speed"]), key=lambda w: w["speed"], default=None)
    best_dp = max((w for w in daypart if w["speed"]), key=lambda w: w["speed"], default=None)
    return {
        "rides": len(ok), "base_speed": _r(base) if base else None,
        "weekday": weekday, "daypart": daypart, "season": seasons, "rest": rest_rows,
        "median_pause_days": median(gaps) if gaps else None,
        "longest_pause_days": max(gaps) if gaps else None,
        "ride_days_per_week": _r(sum(weeks.values()) / len(weeks)) if weeks else None,
        "fastest_weekday": best_wd["label"] if best_wd else None,
        "fastest_daypart": best_dp["label"] if best_dp else None,
    }


# ---------- Radvergleich ----------

def build_bike_compare(rows: list[Row], bike_names: dict[int, str], replaced: dict[int, int] | None = None) -> dict:
    replaced = replaced or {}
    groups: dict[int | None, list[Row]] = defaultdict(list)
    for r in rows:
        groups[r.bike_id].append(r)
    total_km = sum(r.km for r in rows) or 1.0
    out = []
    for bid, rs in groups.items():
        km = sum(r.km for r in rs)
        h = sum(r.time_s for r in rs) / 3600
        sp = [_speed(r) for r in rs if _speed(r)]
        wet_min = sum(r.wet_minutes or 0 for r in rs)
        pw = [r.avg_power for r in rs if r.avg_power and r.avg_power > 0]
        terr = defaultdict(float)
        for r in rs:
            if r.terrain:
                terr[r.terrain] += r.km
        out.append({
            "bike_id": bid, "name": bike_names.get(bid, "Ohne Rad") if bid else "Ohne Rad",
            "rides": len(rs), "km": _r(km), "hours": _r(h), "share": _r(km / total_km * 100),
            "avg_ride_km": _r(km / len(rs)), "longest_km": _r(max(r.km for r in rs)),
            "speed": _r(sum(sp) / len(sp)) if sp else None,
            "elev_per_100": _r(sum(r.elev_m or 0 for r in rs) / km * 100, 0) if km > 0 else None,
            "wet_share": _r(wet_min / (h * 60) * 100) if h > 0 else None,
            "power": _r(sum(pw) / len(pw), 0) if pw else None,
            "replaced": replaced.get(bid, 0) if bid else None,
            "replaced_per_1000": _r(replaced.get(bid, 0) / km * 1000) if bid and km >= 300 else None,
            "terrain": {k: _r(v / km * 100, 0) for k, v in terr.items()} if km > 0 else {},
            "first": min(r.start for r in rs).date().isoformat(), "last": max(r.start for r in rs).date().isoformat(),
        })
    out.sort(key=lambda x: -x["km"])
    return {"bikes": out}


# ---------- Stammstrecken ----------

CELL_M = 150.0


def _cells(points: list[tuple[float, float]]) -> set[tuple[int, int]]:
    """Gitterzellen (150 m), die der Streckenzug berührt, mit Zwischenpunkten alle ~75 m."""
    out = set()
    if not points:
        return out
    lat0 = points[0][0]
    ky = 111_320.0
    kx = 111_320.0 * math.cos(math.radians(lat0))

    def cell(la, ln):
        return int(la * ky // CELL_M), int(ln * kx // CELL_M)

    prev = points[0]
    out.add(cell(*prev))
    for pt in points[1:]:
        dist = math.hypot((pt[0] - prev[0]) * ky, (pt[1] - prev[1]) * kx)
        steps = max(1, int(dist // 75))
        for i in range(1, steps + 1):
            f = i / steps
            out.add(cell(prev[0] + (pt[0] - prev[0]) * f, prev[1] + (pt[1] - prev[1]) * f))
        prev = pt
    return out


def _near(cells: set) -> set:
    out = set()
    for x, y in cells:
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                out.add((x + dx, y + dy))
    return out


def build_routes(rows: list[Row], paths: dict[int, list[tuple[float, float]]], tz, min_rides: int = 3, limit: int = 12) -> dict:
    """Findet Stammrunden: Fahrten mit gleichem Start, ähnlicher Länge und weitgehend gleichem Verlauf.

    paths: Fahrt-ID -> Streckenzug. Zwei Fahrten gehören zusammen, wenn mindestens 80 % der Zellen der kürzeren
    Strecke in der Nähe der anderen liegen und die Länge um höchstens 15 % abweicht.
    """
    cand = [r for r in rows if r.id in paths and r.km >= 5 and r.time_s >= 900]
    cand.sort(key=lambda r: r.start)
    data = {r.id: (_cells(paths[r.id]), paths[r.id][0]) for r in cand}
    clusters: list[list[Row]] = []
    for r in reversed(cand):  # neueste zuerst, damit aktuelle Runden die Gruppe bestimmen
        cells, start = data[r.id]
        placed = False
        for cl in clusters:
            ref = cl[0]
            rc, rs = data[ref.id]
            if abs(rs[0] - start[0]) * 111_320 > 400 or abs(rs[1] - start[1]) * 111_320 * math.cos(math.radians(start[0])) > 400:
                continue
            if abs(ref.km - r.km) / max(ref.km, r.km) > 0.15:
                continue
            small, big = (cells, rc) if len(cells) <= len(rc) else (rc, cells)
            near = _near(big)
            if len(small) and sum(1 for c in small if c in near) / len(small) >= 0.8:
                cl.append(r)
                placed = True
                break
        if not placed:
            clusters.append([r])
    out = []
    for cl in clusters:
        if len(cl) < min_rides:
            continue
        cl.sort(key=lambda r: r.start)
        sp = [(r, r.km / (r.time_s / 3600)) for r in cl]
        best = max(sp, key=lambda x: x[1])
        quickest = min(cl, key=lambda r: r.time_s)
        by_year = defaultdict(list)
        for r, s in sp:
            by_year[local(r.start, tz).year].append(s)
        recent = sp[-3:]
        early = sp[:3]
        out.append({
            "name": cl[-1].name, "rides": len(cl), "km": _r(sum(r.km for r in cl) / len(cl)),
            "avg_speed": _r(sum(s for _, s in sp) / len(sp)),
            "best_speed": _r(best[1]), "best_ride_id": best[0].id, "best_date": local(best[0].start, tz).date().isoformat(),
            "quickest_s": quickest.time_s, "quickest_id": quickest.id,
            "last_id": cl[-1].id, "last_date": local(cl[-1].start, tz).date().isoformat(),
            "trend_pct": _r((sum(s for _, s in recent) / len(recent)) / (sum(s for _, s in early) / len(early)) * 100 - 100)
            if len(cl) >= 6 else None,
            "years": [{"year": y, "speed": _r(sum(v) / len(v)), "rides": len(v)} for y, v in sorted(by_year.items())],
            "ride_ids": [r.id for r in cl][-30:],
        })
    out.sort(key=lambda x: -x["rides"])
    return {"routes": out[:limit], "checked": len(cand)}


# ---------- Prognose ----------

def weekly_pace(rows: list[Row], today: date, bike_id: int | None, weeks: int = 8) -> float:
    """Kilometer pro Woche der letzten Wochen für ein Rad (oder alle)."""
    since = datetime.combine(today - timedelta(weeks=weeks), datetime.min.time())
    km = sum(r.km for r in rows if r.start >= since and (bike_id is None or r.bike_id == bike_id))
    return km / weeks


def forecast_item(label: str, comp: str, bike: str, state: dict, pace_km_week: float, today: date) -> dict | None:
    """Wann ein Wartungsintervall voraussichtlich erreicht wird: je nach Tempo der letzten Wochen und Zeitintervall."""
    if state.get("status") in ("unknown",) or state.get("progress") is None:
        return None
    candidates = []
    interval_km = state.get("interval_km_eff")
    progress = state["progress"]
    eff_left = None
    if interval_km and state.get("effective_km") is not None:
        eff_left = max(0.0, interval_km - state["effective_km"])
        if state.get("measure") and state["measure"].get("km_left") is not None:
            eff_left = float(state["measure"]["km_left"])
        if pace_km_week > 1:
            candidates.append((today + timedelta(days=round(eff_left / pace_km_week * 7)), "Kilometer", round(eff_left)))
    interval_months = state.get("interval_months")
    if interval_months:
        left_m = max(0.0, interval_months - state.get("months_since", 0))
        candidates.append((today + timedelta(days=round(left_m * 30.4)), "Zeit", None))
    if not candidates:
        return None
    eta, basis, km_left = min(candidates, key=lambda c: c[0])
    return {
        "label": label, "component": comp, "bike": bike, "eta": eta.isoformat(), "days": (eta - today).days,
        "basis": basis, "km_left": km_left, "progress": _r(progress * 100, 0), "status": state.get("status"),
        "pace": _r(pace_km_week, 0),
    }


# ---------- Einfluss einer einzelnen Fahrt ----------

def _ftp_at(items: list[tuple[date, dict, bool]], end: date) -> float | None:
    """FTP-Schätzung am Tag `end` aus den Fahrten der 90 Tage davor."""
    win = [x for x in items if end - timedelta(days=FTP_WINDOW_DAYS) < x[0] <= end]
    if not win:
        return None
    return estimate_ftp({k: v["watts"] for k, v in _best_curve(win).items()})[0]


def _zone_of(ratio: float) -> str | None:
    for lo, hi, name in ZONES:
        if lo <= ratio < hi:
            return name
    return None


def ride_impact(rows: list[Row], ride_id: int, tz) -> dict | None:
    """Was eine Fahrt für Fitness, Ermüdung, Form und FTP bedeutet hat, jeweils im Stand nach dieser Fahrt.

    Vergleich wird mit und ohne die Fahrt gerechnet; spätere Fahrten bleiben außen vor.
    """
    from .extra import load_series, ride_load

    ride = next((r for r in rows if r.id == ride_id), None)
    if ride is None:
        return None
    day = local(ride.start, tz).date()
    upto = [r for r in rows if local(r.start, tz).date() <= day]
    others = [r for r in upto if r.id != ride_id]

    def state(rs):
        series = load_series(sorted(((local(r.start, tz), r) for r in rs), key=lambda x: x[0]), day, days=1)
        last = series[-1] if series and series[-1]["date"] == day.isoformat() else None
        return last or {"fitness": 0.0, "fatigue": 0.0, "form": 0.0}

    before, after = state(others), state(upto)
    delta = lambda k: _r(after[k] - before[k], 1)  # noqa: E731
    points = ride_load(ride)
    recent = sorted(ride_load(r) for r in others[-40:] if r.start < ride.start)
    typical = median(recent) if len(recent) >= 5 else None
    rel = points / typical if typical else None
    if rel is None:
        level = None
    elif rel < 0.6:
        level = "sehr locker"
    elif rel < 0.9:
        level = "locker"
    elif rel < 1.2:
        level = "normal"
    elif rel < 1.6:
        level = "fordernd"
    else:
        level = "sehr hart"
    out: dict = {
        "date": day.isoformat(),
        "load": {
            "points": _r(points), "typical": _r(typical) if typical else None, "level": level,
            "fitness": {"before": _r(before["fitness"]), "after": _r(after["fitness"]), "delta": delta("fitness")},
            "fatigue": {"before": _r(before["fatigue"]), "after": _r(after["fatigue"]), "delta": delta("fatigue")},
            "form": {"before": _r(before["form"]), "after": _r(after["form"]), "delta": delta("form")},
        },
    }

    # FTP und Bestwerte: nur mit Leistungskurve
    def items(rs):
        return [(local(r.start, tz).date(), {int(k): v for k, v in r.curve.items()}, r.curve_approx) for r in rs if r.curve]

    ftp: dict = {"available": bool(ride.curve)}
    if ride.curve:
        prior = items(others)
        ftp_before, ftp_after = _ftp_at(prior, day), _ftp_at(items(upto), day)
        records = []
        prior_best = _best_curve(prior)
        for k, w in sorted((int(k), v) for k, v in ride.curve.items()):
            if k in CURVE_LABELS and (k not in prior_best or w > prior_best[k]["watts"]):
                records.append({"seconds": k, "label": CURVE_LABELS[k], "watts": w,
                                "before": prior_best[k]["watts"] if k in prior_best else None, "approx": ride.curve_approx})
        ftp.update({
            "before": round(ftp_before) if ftp_before else None, "after": round(ftp_after) if ftp_after else None,
            "delta": round(ftp_after) - round(ftp_before) if ftp_before and ftp_after else None,
            "records": records, "approx": ride.curve_approx,
        })
        if ftp_after and ride.avg_power:
            ratio = ride.avg_power * 1.06 / ftp_after
            ftp.update({"intensity_pct": round(ratio * 100), "zone": _zone_of(ratio),
                        "tss": _r(ride_tss(ride, ftp_after), 0)})
    out["ftp"] = ftp
    return out
