"""Verschleiß der Kette aus Messwerten (Kettenlehre) hochrechnen.

Reiner Rechenkern ohne Datenbank. Eine Messung gibt die Längung der Kette in Prozent an. Zwischen Messung und heute
wird der Verschleiß linear mit der bisherigen Rate fortgeschrieben (Längung je wirksamem Kilometer). Der Wert der
Messung ersetzt die reine Kilometerschätzung, denn er zeigt den tatsächlichen Zustand der Kette.
"""
from __future__ import annotations

from dataclasses import dataclass

DEFAULT_LIMIT_PCT = 0.5      # 11- und 12-fach; bei 10-fach und weniger 0,75 %
ALLOWED_LIMITS = (0.5, 0.75)
# Eine Kette hält selten mehr als das Dreifache des Intervalls; so bleibt die Rate auch bei Messwert 0 sinnvoll
RATE_FLOOR_FACTOR = 3.0


@dataclass(frozen=True)
class Projection:
    measured_pct: float
    projected_pct: float
    limit_pct: float
    ratio: float                 # projected / limit
    km_left: float | None        # wirksame Kilometer bis zum Grenzwert (None = Rate unbekannt)
    rate_pct_per_1000: float     # Längung je 1000 wirksame km


def project(
    measured_pct: float,
    eff_km_at_measure: float,
    eff_km_now: float,
    limit_pct: float | None = None,
    interval_km: float | None = None,
) -> Projection:
    limit = limit_pct or DEFAULT_LIMIT_PCT
    floor = limit / (interval_km * RATE_FLOOR_FACTOR) if interval_km else 0.0
    rate = measured_pct / eff_km_at_measure if eff_km_at_measure > 0 else 0.0
    rate = max(rate, floor)
    projected = measured_pct + rate * max(0.0, eff_km_now - eff_km_at_measure)
    km_left = max(0.0, (limit - projected) / rate) if rate > 0 else None
    return Projection(
        measured_pct=measured_pct,
        projected_pct=projected,
        limit_pct=limit,
        ratio=projected / limit if limit else 0.0,
        km_left=km_left,
        rate_pct_per_1000=rate * 1000.0,
    )
