"""Wetter zu einer Fahrt: Temperatur, Regen, Wind und Nässezeit aus stündlichen Wetterdaten.

Reiner Rechenkern ohne Datenbank und Netzwerk. Die Abfrage der Daten (Open-Meteo) steht in service.py.

Annahmen des Modells (bewusst einfach gehalten):
- Niederschlag ist bei Open-Meteo die Summe der *vorangegangenen* Stunde. Der Wert zur Zeit t gilt also für (t-1h, t].
- Eine Stunde gilt als nass, wenn mindestens WET_HOUR_MM Niederschlag fiel oder in den DAMP_LOOKBACK_H Stunden
  davor zusammen mindestens DAMP_MM (die Straße ist dann noch feucht).
- Die Fahrzeit wird als zusammenhängend ab dem Start angenommen (Start + Bewegungszeit).
- Entlang der Strecke wird die Fahrt in Abschnitte von etwa 12 km geteilt. Jeder Abschnitt bekommt das Wetter an seiner
  Position und zu seiner Zeit; die Zeit wird dabei gleichmäßig über die Strecke verteilt (konstantes Tempo angenommen).
- Wind: Open-Meteo liefert die Richtung, aus der der Wind kommt (0° = Nord). Der Gegenwind ist der Anteil des Windes
  in Fahrtrichtung, gemittelt über die Wegstücke des Abschnitts (positiv = Gegenwind, negativ = Rückenwind).
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import math
from bisect import bisect_left
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
    wdir: float | None = None
    code: int | None = None


Series = dict[datetime, Hour]


@dataclass
class WeatherSummary:
    temp_c: float | None
    precip_mm: float | None
    wind_kmh: float | None
    wet_minutes: float | None
    weather_code: int | None
    wind_dir: float | None = None      # Grad, aus der der Wind kommt
    headwind_kmh: float | None = None  # positiv = Gegenwind, negativ = Rückenwind


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
            wdir=_at(h.get("wind_direction_10m"), i),
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


def _wind_vec(series: Series, when: datetime) -> tuple[float, float] | None:
    """Wind als (Ost, Nord)-Anteil des Windes „von dort“ in km/h; None, wenn Richtung oder Tempo fehlen."""
    lo = floor_hour(when)
    w = (when - lo) / HOUR
    vecs = []
    for t in (lo, lo + HOUR):
        h = series.get(t)
        if h is None or h.wind is None or h.wdir is None:
            vecs.append(None)
            continue
        r = math.radians(h.wdir)
        vecs.append((h.wind * math.sin(r), h.wind * math.cos(r)))
    a, b = vecs
    if a is None and b is None:
        return None
    if a is None:
        return b
    if b is None:
        return a
    return (a[0] + (b[0] - a[0]) * w, a[1] + (b[1] - a[1]) * w)


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


def summarize(series: Series, start: datetime, duration_s: int | None, direction: tuple[float, float] | None = None) -> WeatherSummary | None:
    """Wetter während der Fahrt (oder eines Abschnitts). Gibt None zurück, wenn für den Zeitraum keine Daten vorliegen.

    direction: mittlere Fahrtrichtung als (Ost, Nord)-Anteil (Länge 0 bis 1); damit wird der Gegenwind berechnet."""
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

    vecs = [v for v in (_wind_vec(series, s) for s in samples) if v is not None]
    wind_dir = head = None
    if vecs:
        fx = sum(v[0] for v in vecs) / len(vecs)
        fy = sum(v[1] for v in vecs) / len(vecs)
        if math.hypot(fx, fy) >= 0.5:
            wind_dir = round(math.degrees(math.atan2(fx, fy)) % 360, 0)
        if direction is not None:
            head = round(fx * direction[0] + fy * direction[1], 1)

    if not (temps or winds or codes or have_precip):
        return None
    return WeatherSummary(
        temp_c=round(sum(temps) / len(temps), 1) if temps else None,
        precip_mm=round(precip, 2) if have_precip else None,
        wind_kmh=round(sum(winds) / len(winds), 1) if winds else None,
        wet_minutes=round(wet_min, 1) if have_precip else None,
        weather_code=max(codes) if codes else None,
        wind_dir=wind_dir,
        headwind_kmh=head,
    )


def combine(parts: list[tuple[WeatherSummary | None, float]]) -> WeatherSummary | None:
    """Fasst die Abschnitte einer Fahrt zusammen. parts: (Wetter, Dauer in Sekunden). Regen und Nässezeit addieren sich,
    Temperatur, Wind und Gegenwind werden nach Dauer gewichtet gemittelt, die Windrichtung als Vektor."""
    have = [(w, max(sec, 1.0)) for w, sec in parts if w is not None]
    if not have:
        return None

    def wavg(attr: str) -> float | None:
        vals = [(getattr(w, attr), sec) for w, sec in have if getattr(w, attr) is not None]
        total = sum(sec for _, sec in vals)
        return round(sum(v * sec for v, sec in vals) / total, 1) if total else None

    def wsum(attr: str) -> float | None:
        vals = [getattr(w, attr) for w, _ in have if getattr(w, attr) is not None]
        return round(sum(vals), 2) if vals else None

    fx = fy = 0.0
    for w, sec in have:
        if w.wind_dir is not None and w.wind_kmh is not None:
            r = math.radians(w.wind_dir)
            fx += w.wind_kmh * math.sin(r) * sec
            fy += w.wind_kmh * math.cos(r) * sec
    total = sum(sec for _, sec in have)
    wind_dir = round(math.degrees(math.atan2(fx, fy)) % 360, 0) if math.hypot(fx, fy) / total >= 0.5 else None
    codes = [w.weather_code for w, _ in have if w.weather_code is not None]
    return WeatherSummary(
        temp_c=wavg("temp_c"),
        precip_mm=wsum("precip_mm"),
        wind_kmh=wavg("wind_kmh"),
        wet_minutes=wsum("wet_minutes"),
        weather_code=max(codes) if codes else None,
        wind_dir=wind_dir,
        headwind_kmh=wavg("headwind_kmh"),
    )


# ---------- Abfragen bündeln ----------

@dataclass
class Item:
    """Eine Fahrt oder ein Abschnitt einer Fahrt, für den das Wetter an Position lat/lng zur Zeit start gebraucht wird."""
    activity_id: int
    lat: float
    lng: float
    start: datetime
    duration_s: int
    dir_x: float | None = None  # mittlere Fahrtrichtung im Abschnitt (Ost-Anteil, 0 bis 1)
    dir_y: float | None = None  # Nord-Anteil
    part: int = 0
    parts: int = 1

    @property
    def direction(self) -> tuple[float, float] | None:
        return None if self.dir_x is None or self.dir_y is None else (self.dir_x, self.dir_y)


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


# ---------- Strecke in Abschnitte teilen ----------

SEGMENT_KM = 12.0
MAX_SEGMENTS = 12
MIN_ROUTE_M = 1500.0


def route_items(activity_id: int, points: list[tuple[float, float]], start: datetime, duration_s: int) -> list[Item] | None:
    """Teilt eine Strecke in Abschnitte von etwa SEGMENT_KM. None, wenn die Strecke zu kurz oder unbrauchbar ist
    (dann bleibt es beim Wetter am Startpunkt)."""
    if len(points) < 2:
        return None
    steps = []  # (Ost m, Nord m, Länge m)
    cum = [0.0]
    for (la1, ln1), (la2, ln2) in zip(points, points[1:]):
        north = (la2 - la1) * 111_320
        east = (ln2 - ln1) * 111_320 * math.cos(math.radians((la1 + la2) / 2))
        steps.append((east, north, math.hypot(east, north)))
        cum.append(cum[-1] + steps[-1][2])
    total = cum[-1]
    if total < MIN_ROUTE_M:
        return None
    n = max(1, min(MAX_SEGMENTS, round(total / 1000 / SEGMENT_KM)))
    sums = [[0.0, 0.0, 0.0] for _ in range(n)]
    for j, (east, north, length) in enumerate(steps):
        if length <= 0:
            continue
        i = min(n - 1, int((cum[j] + length / 2) / total * n))
        sums[i][0] += east
        sums[i][1] += north
        sums[i][2] += length

    def point_at(dist: float) -> tuple[float, float]:
        k = min(max(bisect_left(cum, dist), 1), len(cum) - 1)
        seg = cum[k] - cum[k - 1]
        f = (dist - cum[k - 1]) / seg if seg > 0 else 0.0
        (la1, ln1), (la2, ln2) = points[k - 1], points[k]
        return la1 + (la2 - la1) * f, ln1 + (ln2 - ln1) * f

    duration = max(int(duration_s or 0), 60)
    out = []
    for i in range(n):
        lat, lng = point_at(total * (i + 0.5) / n)
        east, north, length = sums[i]
        out.append(Item(
            activity_id, lat, lng, start + timedelta(seconds=duration * i / n), max(int(duration / n), 60),
            dir_x=east / length if length > 0 else None, dir_y=north / length if length > 0 else None,
            part=i, parts=n,
        ))
    return out
