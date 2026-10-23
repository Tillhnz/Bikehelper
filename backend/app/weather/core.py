"""Wetter zu einer Fahrt: Temperatur, Regen, Wind und Nässezeit aus stündlichen Wetterdaten.

Reiner Rechenkern ohne Datenbank und Netzwerk. Die Abfrage der Daten (Open-Meteo) steht in service.py.

Annahmen des Modells (bewusst einfach gehalten):
- Niederschlag ist bei Open-Meteo die Summe der *vorangegangenen* Stunde. Der Wert zur Zeit t gilt also für (t-1h, t].
- Eine Stunde gilt als nass, wenn mindestens WET_HOUR_MM Niederschlag fiel oder in den DAMP_LOOKBACK_H Stunden
  davor zusammen mindestens DAMP_MM (die Straße ist dann noch feucht).
- Die Fahrzeit wird als zusammenhängend ab dem Start angenommen (Start + Bewegungszeit).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

WET_HOUR_MM = 0.1
DAMP_LOOKBACK_H = 2
DAMP_MM = 0.5
HOUR = timedelta(hours=1)

ARCHIVE_DELAY_DAYS = 7   # jüngere Fahrten stehen noch nicht im Archiv (ERA5 hinkt etwa 5 Tage hinterher)
MAX_WINDOW_DAYS = 90     # so viele Tage deckt eine Abfrage höchstens ab


@dataclass
class Hour:
    temp: float | None = None
    precip: float | None = None
    wind: float | None = None
    code: int | None = None


Series = dict[datetime, Hour]


@dataclass
class WeatherSummary:
    temp_c: float | None
    precip_mm: float | None
    wind_kmh: float | None
    wet_minutes: float | None
    weather_code: int | None


# ---------- Antwort der API einlesen ----------

def _at(values: list | None, i: int):
    if not values or i >= len(values):
        return None
    return values[i]


def parse_hourly(payload: dict) -> Series:
    """Wandelt die JSON-Antwort von Open-Meteo (Zeitzone GMT) in eine Zeitreihe um."""
    h = payload.get("hourly") or {}
    series: Series = {}
    for i, t in enumerate(h.get("time") or []):
        try:
            when = datetime.fromisoformat(t)
        except ValueError:
            continue
        code = _at(h.get("weather_code"), i)
        series[when] = Hour(
            temp=_at(h.get("temperature_2m"), i),
            precip=_at(h.get("precipitation"), i),
            wind=_at(h.get("wind_speed_10m"), i),
            code=int(code) if code is not None else None,
        )
    return series


# ---------- Auswertung einer Fahrt ----------

def floor_hour(dt: datetime) -> datetime:
    return dt.replace(minute=0, second=0, microsecond=0)


def ceil_hour(dt: datetime) -> datetime:
    f = floor_hour(dt)
    return f if f == dt else f + HOUR


def _interp(series: Series, when: datetime, attr: str) -> float | None:
    lo = floor_hour(when)
    a = getattr(series.get(lo), attr, None) if lo in series else None
    b = getattr(series.get(lo + HOUR), attr, None) if (lo + HOUR) in series else None
    if a is None and b is None:
        return None
    if a is None:
        return float(b)
    if b is None:
        return float(a)
    w = (when - lo) / HOUR
    return float(a) + (float(b) - float(a)) * w


def _is_wet(series: Series, t: datetime) -> bool:
    here = series[t].precip or 0.0
    if here >= WET_HOUR_MM:
        return True
    before = 0.0
    for k in range(1, DAMP_LOOKBACK_H + 1):
        prev = series.get(t - k * HOUR)
        if prev is not None and prev.precip:
            before += prev.precip
    return before >= DAMP_MM


def summarize(series: Series, start: datetime, duration_s: int | None) -> WeatherSummary | None:
    """Wetter während der Fahrt. Gibt None zurück, wenn für den Zeitraum keine Daten vorliegen."""
    end = start + timedelta(seconds=max(int(duration_s or 0), 60))

    precip = wet_min = 0.0
    have_precip = False
    t = floor_hour(start) + HOUR
    while t - HOUR < end:
        h = series.get(t)
        if h is not None and h.precip is not None:
            have_precip = True
            overlap = (min(end, t) - max(start, t - HOUR)).total_seconds()
            if overlap > 0:
                precip += h.precip * overlap / 3600
                if _is_wet(series, t):
                    wet_min += overlap / 60
        t += HOUR

    samples = [start, start + (end - start) / 2, end]
    temps = [v for v in (_interp(series, s, "temp") for s in samples) if v is not None]
    winds = [v for v in (_interp(series, s, "wind") for s in samples) if v is not None]

    codes = []
    t = floor_hour(start)
    last = ceil_hour(end)
    while t <= last:
        h = series.get(t)
        if h is not None and h.code is not None:
            codes.append(h.code)
        t += HOUR

    if not (temps or winds or codes or have_precip):
        return None
    return WeatherSummary(
        temp_c=round(sum(temps) / len(temps), 1) if temps else None,
        precip_mm=round(precip, 2) if have_precip else None,
        wind_kmh=round(sum(winds) / len(winds), 1) if winds else None,
        wet_minutes=round(wet_min, 1) if have_precip else None,
        weather_code=max(codes) if codes else None,
    )


# ---------- Abfragen bündeln ----------

@dataclass
class Item:
    activity_id: int
    lat: float
    lng: float
    start: datetime
    duration_s: int


@dataclass
class Window:
    lat: float
    lng: float
    start_date: date
    end_date: date
    recent: bool
    items: list[Item] = field(default_factory=list)


def plan_windows(items: list[Item], today: date) -> list[Window]:
    """Fasst Fahrten zu wenigen Abfragen zusammen: je Gitterzelle (0,1 Grad) und Zeitraum eine.

    Ein Tag vor der ersten Fahrt wird mitgeladen, damit sich feuchte Straßen nach Regen erkennen lassen.
    """
    cells: dict[tuple[float, float, bool], list[Item]] = defaultdict(list)
    for it in items:
        recent = (today - it.start.date()).days < ARCHIVE_DELAY_DAYS
        cells[(round(it.lat, 1), round(it.lng, 1), recent)].append(it)

    windows: list[Window] = []
    for (lat, lng, recent), lst in sorted(cells.items()):
        lst.sort(key=lambda i: i.start)
        chunk: list[Item] = []
        for it in lst:
            if chunk and (it.start.date() - chunk[0].start.date()).days > MAX_WINDOW_DAYS:
                windows.append(_window(lat, lng, recent, chunk))
                chunk = []
            chunk.append(it)
        if chunk:
            windows.append(_window(lat, lng, recent, chunk))
    return windows


def _window(lat: float, lng: float, recent: bool, chunk: list[Item]) -> Window:
    first = chunk[0].start.date() - timedelta(days=1)
    last = max((i.start + timedelta(seconds=max(i.duration_s, 60))).date() for i in chunk)
    return Window(lat=lat, lng=lng, start_date=first, end_date=last, recent=recent, items=list(chunk))


# ---------- Anzeige ----------

def describe_code(code: int | None) -> str | None:
    """WMO-Wettercode als kurzer deutscher Text."""
    if code is None:
        return None
    if code == 0:
        return "klar"
    if code in (1, 2, 3):
        return "bewölkt"
    if code in (45, 48):
        return "Nebel"
    if 51 <= code <= 57:
        return "Nieselregen"
    if 61 <= code <= 67:
        return "Regen"
    if 71 <= code <= 77:
        return "Schnee"
    if 80 <= code <= 82:
        return "Regenschauer"
    if code in (85, 86):
        return "Schneeschauer"
    if code >= 95:
        return "Gewitter"
    return None
