"""Tests für den Wetter-Rechenkern (nur Standardbibliothek)."""
from datetime import date, datetime

from app.weather.core import (
    Hour, Item, describe_code, parse_hourly, plan_windows, summarize,
)

DAY = datetime(2026, 10, 23)


def make_series():
    """24 Stunden: Temperatur steigt, zwischen 08 und 09 Uhr fallen 1,2 mm Regen (Wert hängt am Label 09:00)."""
    s = {}
    for h in range(24):
        s[DAY.replace(hour=h)] = Hour(
            temp=10 + h * 0.5,
            precip=1.2 if h == 9 else 0.0,
            wind=15.0,
            code=61 if h == 9 else 3,
        )
    return s


def test_ride_in_rain_counts_rain_and_damp_road():
    r = summarize(make_series(), DAY.replace(hour=8, minute=30), 3600)
    assert r.precip_mm == 0.6  # nur die halbe Regenstunde liegt in der Fahrt
    assert r.wet_minutes == 60  # zweite Hälfte: Straße noch nass
    assert r.temp_c == 14.5
    assert r.wind_kmh == 15.0
    assert r.weather_code == 61


def test_dry_ride():
    r = summarize(make_series(), DAY.replace(hour=12), 3600)
    assert r.precip_mm == 0 and r.wet_minutes == 0
    assert r.weather_code == 3


def test_road_dries_after_two_hours():
    r = summarize(make_series(), DAY.replace(hour=10, minute=30), 3600)
    assert r.wet_minutes == 30  # bis 11 Uhr noch nass, danach trocken


def test_no_data_gives_none():
    assert summarize({}, DAY.replace(hour=8), 3600) is None


def test_missing_precipitation_leaves_wetness_unknown():
    s = {DAY.replace(hour=h): Hour(temp=12.0, precip=None, wind=10.0, code=1) for h in range(24)}
    r = summarize(s, DAY.replace(hour=8), 1800)
    assert r.wet_minutes is None and r.precip_mm is None and r.temp_c == 12.0


def test_parse_hourly():
    payload = {"hourly": {
        "time": ["2026-10-23T00:00", "2026-10-23T01:00"],
        "temperature_2m": [10.0, 9.5],
        "precipitation": [0.0, None],
        "wind_speed_10m": [12.0, 13.0],
        "weather_code": [3, 61],
    }}
    s = parse_hourly(payload)
    assert s[datetime(2026, 10, 23, 1)].temp == 9.5
    assert s[datetime(2026, 10, 23, 1)].precip is None
    assert s[datetime(2026, 10, 23, 1)].code == 61
    assert parse_hourly({}) == {}


def test_windows_group_by_place_and_period():
    today = date(2026, 10, 23)
    def item(i, lat, lng, d, h=8):
        return Item(i, lat, lng, datetime(d.year, d.month, d.day, h), 3600)

    items = [
        item(1, 53.52, 10.01, date(2026, 1, 10)),
        item(2, 53.53, 10.02, date(2026, 2, 1)),     # gleiche Zelle (0,1 Grad), im selben Zeitraum
        item(3, 53.52, 10.01, date(2026, 6, 1)),     # später als 90 Tage: neue Abfrage
        item(4, 53.52, 10.01, date(2026, 10, 21)),   # zu jung fürs Archiv
        item(5, 48.14, 11.58, date(2026, 1, 10)),    # andere Zelle
    ]
    windows = plan_windows(items, today)
    assert len(windows) == 4
    first = next(w for w in windows if 1 in [i.activity_id for i in w.items])
    assert [i.activity_id for i in first.items] == [1, 2]
    assert first.start_date == date(2026, 1, 9)  # ein Tag Vorlauf
    assert first.end_date == date(2026, 2, 1)
    assert not first.recent
    assert next(w for w in windows if w.recent).items[0].activity_id == 4


def test_ride_crossing_midnight_extends_window():
    w = plan_windows([Item(1, 53.55, 10.0, datetime(2026, 5, 1, 23, 0), 7200)], date(2026, 10, 23))[0]
    assert w.end_date == date(2026, 5, 2)


def test_describe_code():
    assert describe_code(0) == "klar"
    assert describe_code(63) == "Regen"
    assert describe_code(95) == "Gewitter"
    assert describe_code(None) is None
