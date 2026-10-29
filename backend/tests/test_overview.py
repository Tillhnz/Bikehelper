from datetime import date, datetime, timezone

from app.stats.overview import Row, build_overview, get_tz, streaks


def row(i, d, km=50, h=8, **kw):
    return Row(i, f"Fahrt {i}", kw.pop("bike_id", 1), datetime(d.year, d.month, d.day, h), km, int(km / 25 * 3600), km * 5, **kw)


def test_streaks():
    days = {date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22), date(2026, 10, 1)}
    assert streaks(days, date(2026, 10, 23)) == (3, 3)  # gestern zählt noch
    assert streaks(days, date(2026, 10, 30)) == (3, 0)
    assert streaks(set(), date(2026, 10, 30)) == (0, 0)


def test_empty():
    assert build_overview([], timezone.utc, date.today()) == {"empty": True}


def test_overview_totals_and_timezone():
    rows = [
        row(1, date(2026, 5, 1), 100),
        row(2, date(2026, 5, 2), 30, h=23),  # 23 Uhr UTC = 01 Uhr am Folgetag in Berlin (Sommerzeit)
        row(3, date(2026, 6, 1), 60, bike_id=None),
    ]
    o = build_overview(rows, get_tz("Europe/Berlin"), date(2026, 6, 2), {1: "Gravel"})
    assert o["totals"]["rides"] == 3 and o["totals"]["km"] == 190.0
    assert o["records"]["longest_ride"]["value"] == 100.0
    assert o["records"]["best_day_km"]["date"] == "2026-05-01"
    assert "2026-05-03" in o["daily"]
    assert [b["name"] for b in o["bikes"]] == ["Gravel", "Ohne Rad"]
    assert o["years"][0]["year"] == 2026 and o["years"][0]["km"] == 190.0


def test_weather_block():
    rows = [
        row(1, date(2026, 5, 1), 50, temp_c=12.0, precip_mm=2.0, wet_minutes=60, weather_status="ok"),
        row(2, date(2026, 5, 2), 50, temp_c=22.0, precip_mm=0.0, wet_minutes=0, weather_status="ok"),
        row(3, date(2026, 5, 3), 50),
    ]
    w = build_overview(rows, get_tz("UTC"), date(2026, 5, 4))["weather"]
    assert w["rides_with_weather"] == 2 and w["avg_temp"] == 17.0
    assert w["wet_km"] == 25.0 and w["wet_share"] == 25.0  # Fahrt 1: 60 min von 120 min nass
    assert w["rainy_rides"] == 1
    assert w["hottest"]["value"] == 22.0


def test_tiles_block_new_per_year():
    a = row(1, date(2025, 5, 1), tiles={(1, 1), (1, 2), (2, 1), (2, 2)})
    b = row(2, date(2026, 5, 1), tiles={(2, 2), (3, 3)})
    t = build_overview([a, b], get_tz("UTC"), date(2026, 6, 1))["tiles"]
    assert t["count"] == 5 and t["max_square"] == 2 and t["by_year_new"] == {2025: 4, 2026: 1}


def test_eddington_number():
    from app.stats.overview import eddington, eddington_block
    assert eddington([]) == 0
    assert eddington([100, 80, 60, 3, 2, 2, 1]) == 3
    assert eddington([5] * 5) == 5
    assert eddington([59.9] * 60) == 59  # 59,9 km zählt nicht als 60
    b = eddington_block({"2024-05-01": 70, "2024-05-02": 50, "2024-05-03": 10, "2025-06-01": 45, "2025-06-02": 40, "2025-06-03": 30})
    assert (b["value"], b["next"], b["missing_days"]) == (6, 7, 1)
    assert [h["value"] for h in b["history"]] == [3, 6] and [h["value"] for h in b["by_year"]] == [3, 3]
