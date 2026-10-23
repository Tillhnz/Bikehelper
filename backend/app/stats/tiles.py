"""Kachel-Erkundung wie bei Statshunters: Die Welt wird in Web-Mercator-Kacheln (Zoomstufe 14, ca. 1,5 x 1,5 km
bei uns) zerlegt. Jede Kachel, durch die eine Fahrt führt, gilt als erkundet.

Reiner Rechenkern ohne Datenbank. Die Strecken sind auf ca. 600 Punkte vereinfacht, deshalb werden lange
Teilstücke vor dem Zuordnen zu Kacheln in kleine Schritte zerlegt.
"""
from __future__ import annotations

import math

ZOOM = 14
MAX_LAT = 85.0511
_N = 2 ** ZOOM
STEP_M = 150.0  # so dicht wird auf Teilstücken abgetastet (Kacheln sind deutlich größer)

Tile = tuple[int, int]


def tile_of(lat: float, lng: float, zoom: int = ZOOM) -> Tile:
    n = 2 ** zoom
    lat = max(-MAX_LAT, min(MAX_LAT, lat))
    x = int((lng + 180.0) / 360.0 * n)
    r = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(r)) / math.pi) / 2.0 * n)
    return (min(max(x, 0), n - 1), min(max(y, 0), n - 1))


def tile_bounds(x: int, y: int, zoom: int = ZOOM) -> tuple[float, float, float, float]:
    """(süd, west, nord, ost) in Grad."""
    n = 2 ** zoom

    def lat(yy: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * yy / n))))

    return (lat(y + 1), x / n * 360 - 180, lat(y), (x + 1) / n * 360 - 180)


def _dist_m(a: tuple[float, float], b: tuple[float, float]) -> float:
    dlat = (b[0] - a[0]) * 111_320
    dlng = (b[1] - a[1]) * 111_320 * math.cos(math.radians((a[0] + b[0]) / 2))
    return math.hypot(dlat, dlng)


def tiles_for_points(points: list[tuple[float, float]]) -> set[Tile]:
    out: set[Tile] = set()
    prev = None
    for p in points:
        if prev is not None:
            d = _dist_m(prev, p)
            if d > STEP_M:
                steps = int(d // STEP_M)
                for i in range(1, steps + 1):
                    f = i / (steps + 1)
                    out.add(tile_of(prev[0] + (p[0] - prev[0]) * f, prev[1] + (p[1] - prev[1]) * f))
        out.add(tile_of(*p))
        prev = p
    return out


def encode(tiles: set[Tile]) -> str:
    return ";".join(f"{x},{y}" for x, y in sorted(tiles))


def decode(s: str | None) -> set[Tile]:
    if not s:
        return set()
    out = set()
    for part in s.split(";"):
        a, _, b = part.partition(",")
        out.add((int(a), int(b)))
    return out


def max_square(tiles: set[Tile]) -> tuple[int, Tile | None]:
    """Größtes vollständig erkundetes Quadrat: (Seitenlänge, linke obere Kachel)."""
    best, best_at = 0, None
    dp: dict[Tile, int] = {}
    for x, y in sorted(tiles):  # nach x, dann y: links und oben sind schon berechnet
        v = 1 + min(dp.get((x - 1, y), 0), dp.get((x, y - 1), 0), dp.get((x - 1, y - 1), 0))
        dp[(x, y)] = v
        if v > best:
            best, best_at = v, (x - v + 1, y - v + 1)
    return best, best_at


def max_cluster(tiles: set[Tile]) -> int:
    """Größte zusammenhängende Gruppe erkundeter Kacheln (auch diagonal verbunden)."""
    seen: set[Tile] = set()
    best = 0
    for start in tiles:
        if start in seen:
            continue
        seen.add(start)
        stack, size = [start], 0
        while stack:
            x, y = stack.pop()
            size += 1
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    nb = (x + dx, y + dy)
                    if nb in tiles and nb not in seen:
                        seen.add(nb)
                        stack.append(nb)
        best = max(best, size)
    return best
