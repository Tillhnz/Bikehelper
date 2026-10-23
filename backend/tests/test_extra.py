from datetime import date, datetime, timezone

from app.stats.extra import build_extra, build_review, goals_progress, load_series, milestones, ride_load, _local_rows
from app.stats.overview import Row, get_tz

TZ = get_tz("UTC")


def row(i, d, km=50, h=8, elev=300, bike=1, **kw):
    return Row(i, f"Fahrt {i}", bike, datetime(d.year, d.month, d.day, h), km, int(km / 25 * 3600), elev, **kw)


def rows():
    out, i = [], 0
    for m in (1, 3, 5, 7):
        for dd in (3, 4, 10):
            i += 1
            out.append(row(i, date(2025, m, dd), 40 + i, tiles={(i, i)}))
    for m in (1, 2, 3, 4):
        for dd in (2, 9, 16):
            i += 1
            out.append(row(i, date(2026, m, dd), 60 + i, h=6, tiles={(i, i), (100, 100)}))
    return out


def test_load_grows_and_decays():
    lr = _local_rows(rows(), TZ)
    s = load_series(lr, date(2026, 6, 1), days=400)
    assert s[-1]["fitness"] < max(p["fitness"] for p in s)
    assert ride_load(rows()[0]) > 0
    assert all("form" in p for p in s)


def test_extra_shapes():
    e = build_extra(rows(), TZ, date(2026, 6, 1), {1: "Gravel"})
    assert e["month_matrix"]["years"] == [2025, 2026]
    assert len(e["weekly"] if "weekly" in e else e["load"]["weekly"]) == 26
    assert e["bike_years"]["bikes"][0]["name"] == "Gravel"
    assert sum(b["rides"] for b in e["speed_buckets"]) == 24
    assert e["breaks"]["since_last_ride"] == (date(2026, 6, 1) - date(2026, 4, 16)).days
    assert e["equivalents"]["earth_laps"] > 0
    assert build_extra([], TZ, date.today()) == {"empty": True}


def test_milestones_in_order():
    ms = milestones(_local_rows(rows(), TZ))
    assert ms and ms[0]["km"] == 500
    assert [m["date"] for m in ms] == sorted(m["date"] for m in ms)


def test_review_compares_with_previous_year():
    rv = build_review(rows(), TZ, 2026, date(2026, 6, 1), {1: "Gravel"})
    assert rv["totals"]["rides"] == 12 and rv["previous"]["rides"] == 12
    assert rv["delta"]["km"] > 0
    assert rv["new_tiles"] == 13  # 12 neue plus die gemeinsame (100,100); alte Kacheln (i,i) sind andere
    assert rv["early_rides"] == 12
    assert build_review(rows(), TZ, 2020, date(2026, 6, 1))["empty"] is True


def test_goals_progress():
    g = goals_progress(rows(), TZ, 2026, date(2026, 6, 1), {"km": 1000, "rides": 10})
    km = [x for x in g if x["metric"] == "km"][0]
    assert km["done"] > 0 and km["target"] == 1000 and km["percent"] == round(km["done"] / 10, 1)
    rides = [x for x in g if x["metric"] == "rides"][0]
    assert rides["reached_on"] is not None and rides["remaining"] == 0
