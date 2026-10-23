"""Wettervorhersage für eine geplante Fahrt (Open-Meteo) und Auswertung des Fahrtzeitraums.

Die Zeiten der Antwort sind Ortszeit (timezone=auto). Auswertung und Eingabe der Startzeit sind daher ebenfalls
Ortszeit des Ortes, ohne Zeitzone. Der Rechenkern (parse, ride_weather) kennt kein Netzwerk; fetch_forecast und
geocode holen die Daten.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import TYPE_CHECKING

from ..weather import core

if TYPE_CHECKING:  # httpx wird nur für die Abrufe gebraucht, der Rechenkern kommt ohne aus
    import httpx

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
GEOCODE_URL = "https://geocoding-api.open-meteo.com/v1/search"
HOURLY = "temperature_2m,precipitation,precipitation_probability,wind_speed_10m,wind_gusts_10m,weather_code,uv_index"
MAX_FORECAST_DAYS = 15
HOUR = timedelta(hours=1)


@dataclass
class Forecast:
    series: core.Series
    extra: dict[datetime, dict] = field(default_factory=dict)  # pop, gust, uv je Stunde
    sun: dict[date, tuple[datetime, datetime]] = field(default_factory=dict)  # Sonnenaufgang, -untergang


@dataclass
class RideWeather:
    temp_start: float | None
    temp_avg: float | None
    temp_min: float | None
    temp_max: float | None
    wind_kmh: float | None
    gust_kmh: float | None
    precip_mm: float | None
    precip_prob: float | None
    wet_minutes: float | None
    uv: float | None
    weather_code: int | None
    dark_minutes: float
    hours: list[dict]


def _at(values, i):
    return values[i] if values and i < len(values) else None


def parse_forecast(payload: dict) -> Forecast:
    h = payload.get("hourly") or {}
    series: core.Series = {}
    extra: dict[datetime, dict] = {}
    for i, t in enumerate(h.get("time") or []):
        try:
            when = datetime.fromisoformat(t)
        except ValueError:
            continue
        code = _at(h.get("weather_code"), i)
        series[when] = core.Hour(
            temp=_at(h.get("temperature_2m"), i), precip=_at(h.get("precipitation"), i),
            wind=_at(h.get("wind_speed_10m"), i), code=int(code) if code is not None else None,
        )
        extra[when] = {
            "pop": _at(h.get("precipitation_probability"), i),
            "gust": _at(h.get("wind_gusts_10m"), i),
            "uv": _at(h.get("uv_index"), i),
        }
    sun: dict[date, tuple[datetime, datetime]] = {}
    d = payload.get("daily") or {}
    for i, day in enumerate(d.get("time") or []):
        try:
            sun[date.fromisoformat(day)] = (
                datetime.fromisoformat(d["sunrise"][i]), datetime.fromisoformat(d["sunset"][i]),
            )
        except (KeyError, IndexError, ValueError, TypeError):
            continue
    return Forecast(series, extra, sun)


def _overlap_min(a0: datetime, a1: datetime, b0: datetime, b1: datetime) -> float:
    return max(0.0, (min(a1, b1) - max(a0, b0)).total_seconds() / 60)


def ride_weather(fc: Forecast, start: datetime, duration_min: float) -> RideWeather | None:
    """Wetter während der Fahrt (Ortszeit). None, wenn für den Zeitraum keine Daten vorliegen."""
    end = start + timedelta(minutes=max(duration_min, 5))
    summary = core.summarize(fc.series, start, int((end - start).total_seconds()))
    if summary is None:
        return None

    lo = core.floor_hour(start)
    hi = core.ceil_hour(end)
    points = [start, end]
    t = lo + HOUR
    while t < end:
        if t > start:
            points.append(t)
        t += HOUR
    temps = [v for v in (core._interp(fc.series, p, "temp") for p in sorted(points)) if v is not None]

    pops, gusts, uvs, strip = [], [], [], []
    t = lo
    while t <= hi:
        ex = fc.extra.get(t, {})
        row = fc.series.get(t)
        if row is not None:
            if ex.get("pop") is not None:
                pops.append(ex["pop"])
            if ex.get("gust") is not None:
                gusts.append(ex["gust"])
            if ex.get("uv") is not None:
                uvs.append(ex["uv"])
            strip.append({
                "time": t.strftime("%H:%M"), "temp": row.temp, "precip": row.precip,
                "pop": ex.get("pop"), "wind": row.wind, "gust": ex.get("gust"), "code": row.code,
            })
        t += HOUR

    dark = 0.0
    for day in {start.date(), end.date()}:
        if day in fc.sun:
            rise, sset = fc.sun[day]
            midnight = datetime.combine(day, datetime.min.time())
            dark += _overlap_min(start, end, midnight, rise) + _overlap_min(start, end, sset, midnight + timedelta(days=1))

    return RideWeather(
        temp_start=round(temps[0], 1) if temps else None,
        temp_avg=summary.temp_c,
        temp_min=round(min(temps), 1) if temps else None,
        temp_max=round(max(temps), 1) if temps else None,
        wind_kmh=summary.wind_kmh,
        gust_kmh=max(gusts) if gusts else None,
        precip_mm=summary.precip_mm,
        precip_prob=max(pops) if pops else None,
        wet_minutes=summary.wet_minutes,
        uv=max(uvs) if uvs else None,
        weather_code=summary.weather_code,
        dark_minutes=round(dark),
        hours=strip,
    )


def check_start(start: datetime, now: datetime) -> str | None:
    """Fehlertext, wenn die Vorhersage für diesen Start nicht verfügbar ist."""
    if start.date() < now.date() - timedelta(days=1):
        return "Der Start liegt in der Vergangenheit."
    if start.date() > now.date() + timedelta(days=MAX_FORECAST_DAYS):
        return f"Die Vorhersage reicht nur {MAX_FORECAST_DAYS} Tage voraus."
    return None


def fetch_forecast(client: "httpx.Client", lat: float, lng: float, start: datetime, end: datetime) -> Forecast:
    r = client.get(FORECAST_URL, params={
        "latitude": round(lat, 2), "longitude": round(lng, 2), "hourly": HOURLY, "daily": "sunrise,sunset",
        "timezone": "auto", "wind_speed_unit": "kmh",
        "start_date": (start.date() - timedelta(days=1)).isoformat(), "end_date": end.date().isoformat(),
    })
    r.raise_for_status()
    return parse_forecast(r.json())


def geocode(client: "httpx.Client", query: str, count: int = 5) -> list[dict]:
    r = client.get(GEOCODE_URL, params={"name": query, "count": count, "language": "de", "format": "json"})
    r.raise_for_status()
    out = []
    for it in r.json().get("results") or []:
        label = ", ".join(x for x in (it.get("name"), it.get("admin1"), it.get("country")) if x)
        out.append({"name": label, "lat": it["latitude"], "lng": it["longitude"]})
    return out
