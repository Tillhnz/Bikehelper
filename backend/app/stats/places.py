"""Städte und Länder: Welche erkundeten Kacheln liegen in welchem Ort? Reiner Rechenkern ohne Datenbank und Netzwerk.

Orte kommen als GeoJSON-Fläche (Polygon oder MultiPolygon, Koordinaten [Länge, Breite]) von OpenStreetMap. Eine Kachel
gehört zu einem Ort, wenn ihr Mittelpunkt in der Fläche liegt. Länder werden über ihre Landfläche geschätzt.
"""
from __future__ import annotations

import math

from .tiles import ZOOM, Tile, tile_bounds, tile_of

Geometry = dict  # GeoJSON: {"type": "Polygon"|"MultiPolygon", "coordinates": [...]}

# Landfläche in km² und Breitengrad der Mitte, gerundet. Reicht für die Schätzung des Anteils; Länder ohne Eintrag
# zeigen nur die Zahl der Kacheln.
COUNTRIES: dict[str, tuple[float, float]] = {
    "de": (357_600, 51.1), "at": (83_900, 47.6), "ch": (41_300, 46.8), "li": (160, 47.1), "fr": (543_900, 46.6),
    "it": (301_300, 42.8), "es": (505_900, 40.2), "pt": (92_200, 39.6), "nl": (41_500, 52.2), "be": (30_700, 50.6),
    "lu": (2_590, 49.8), "dk": (42_900, 56.0), "pl": (312_700, 52.1), "cz": (78_900, 49.8), "sk": (49_000, 48.7),
    "hu": (93_000, 47.2), "si": (20_300, 46.1), "hr": (56_600, 45.1), "ba": (51_200, 44.2), "rs": (77_500, 44.0),
    "ro": (238_400, 45.9), "bg": (111_000, 42.7), "gr": (131_900, 39.1), "gb": (242_500, 54.0), "ie": (70_300, 53.2),
    "se": (450_300, 62.0), "no": (385_200, 64.5), "fi": (338_100, 64.0), "ee": (45_300, 58.7), "lv": (64_600, 56.9),
    "lt": (65_300, 55.3), "us": (9_833_500, 39.8), "ca": (9_984_700, 56.0), "au": (7_692_000, -25.7),
    "nz": (268_000, -41.5), "tr": (783_600, 39.0), "mt": (316, 35.9), "cy": (9_250, 35.0), "is": (103_000, 64.9),
    "mc": (2, 43.7), "ad": (468, 42.5),
}


def tile_area_km2(lat: float, zoom: int = ZOOM) -> float:
    side = 40_075.017 * math.cos(math.radians(lat)) / 2 ** zoom
    return side * side


def country_total_tiles(code: str) -> int | None:
    info = COUNTRIES.get((code or "").lower())
    if not info:
        return None
    area, lat = info
    return max(1, round(area / tile_area_km2(lat)))


def _ring_contains(ring: list, lng: float, lat: float) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _polygons(geom: Geometry) -> list[list]:
    if geom.get("type") == "Polygon":
        return [geom["coordinates"]]
    if geom.get("type") == "MultiPolygon":
        return list(geom["coordinates"])
    return []


def contains(geom: Geometry, lat: float, lng: float) -> bool:
    """Liegt der Punkt in der Fläche (äußerer Ring, abzüglich Löcher)?"""
    for poly in _polygons(geom):
        if poly and _ring_contains(poly[0], lng, lat) and not any(_ring_contains(h, lng, lat) for h in poly[1:]):
            return True
    return False


def bbox(geom: Geometry) -> tuple[float, float, float, float] | None:
    """(süd, west, nord, ost) in Grad."""
    pts = [p for poly in _polygons(geom) for ring in poly[:1] for p in ring]
    if not pts:
        return None
    return (min(p[1] for p in pts), min(p[0] for p in pts), max(p[1] for p in pts), max(p[0] for p in pts))


def tiles_in(geom: Geometry, box: tuple[float, float, float, float] | None = None) -> set[Tile]:
    """Alle Kacheln, deren Mittelpunkt in der Fläche liegt."""
    box = box or bbox(geom)
    if not box:
        return set()
    s, w, n, e = box
    x0, y1 = tile_of(s, w)
    x1, y0 = tile_of(n, e)
    out: set[Tile] = set()
    for x in range(min(x0, x1), max(x0, x1) + 1):
        for y in range(min(y0, y1), max(y0, y1) + 1):
            ts, tw, tn, te = tile_bounds(x, y)
            if contains(geom, (ts + tn) / 2, (tw + te) / 2):
                out.add((x, y))
    return out


def kind_and_name(address: dict, fallback: str = "") -> tuple[str, str]:
    """Art und Name des Ortes aus der Adresse eines Nominatim-Treffers."""
    for key, kind in (("city", "city"), ("town", "town"), ("municipality", "town"), ("village", "village"),
                      ("hamlet", "village"), ("county", "county")):
        if address.get(key):
            return kind, address[key]
    return "area", fallback


def percent(part: int, total: int | None) -> float | None:
    if not total:
        return None
    return round(min(100.0, part / total * 100), 1)
