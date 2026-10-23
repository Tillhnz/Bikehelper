from datetime import date, datetime

from app.advisor.forecast import check_start, parse_forecast, ride_weather

DAY = "2026-10-24"


def payload():
    times = [f"{DAY}T{h:02d}:00" for h in range(24)]
    return {
        "hourly": {
            "time": times,
            "temperature_2m": [5 + h * 0.5 for h in range(24)],            # 5 °C um 0 Uhr, 16,5 °C um 23 Uhr
            "precipitation": [0.0] * 9 + [1.5] + [0.0] * 14,               # Regen in der Stunde bis 9 Uhr
            "precipitation_probability": [10] * 8 + [80, 80] + [10] * 14,
            "wind_speed_10m": [12.0] * 24,
            "wind_gusts_10m": [20.0] * 10 + [38.0] + [20.0] * 13,
            "weather_code": [3] * 24,
            "uv_index": [0, 0, 0, 0, 0, 0, 0, 0, 1, 2, 3, 4, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, 0, 0],
        },
        "daily": {"time": [DAY], "sunrise": [f"{DAY}T07:45"], "sunset": [f"{DAY}T18:05"]},
    }


def test_ride_weather_window():
    fc = parse_forecast(payload())
    w = ride_weather(fc, datetime(2026, 10, 24, 8, 30), 120)
    assert w.temp_start == 9.2 and w.temp_max > w.temp_start and w.temp_min == w.temp_start
    assert w.precip_mm is not None and w.precip_mm > 0.5
    assert w.wet_minutes and w.wet_minutes > 30
    assert w.precip_prob == 80
    assert w.gust_kmh == 38.0
    assert w.dark_minutes == 0
    assert [h["time"] for h in w.hours][0] == "08:00"


def test_dry_afternoon_ride():
    fc = parse_forecast(payload())
    w = ride_weather(fc, datetime(2026, 10, 24, 13, 0), 90)
    assert w.precip_mm == 0 and w.wet_minutes == 0 and w.uv == 3


def test_darkness_before_sunrise_and_after_sunset():
    fc = parse_forecast(payload())
    morning = ride_weather(fc, datetime(2026, 10, 24, 7, 0), 60)
    assert morning.dark_minutes == 45
    evening = ride_weather(fc, datetime(2026, 10, 24, 17, 30), 120)
    assert evening.dark_minutes == 85


def test_no_data_and_range_checks():
    fc = parse_forecast(payload())
    assert ride_weather(fc, datetime(2026, 11, 20, 8, 0), 60) is None
    now = datetime(2026, 10, 24, 12, 0)
    assert check_start(datetime(2026, 10, 24, 8, 0), now) is None
    assert "Vergangenheit" in check_start(datetime(2026, 10, 20, 8, 0), now)
    assert "15 Tage" in check_start(datetime(2026, 11, 20, 8, 0), now)
    assert parse_forecast({}).series == {}
