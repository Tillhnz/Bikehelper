"""Reifendruck-Empfehlung aus Gewicht, Reifenbreite, Untergrund und Wetter.

Grundlage ist die Anpassung von Frank Bertos 15-%-Reifenabsenkung als Formel (bikelabstudio.com, Genauigkeit
etwa +-2 psi im geprüften Bereich für Straße und Gravel):

    P = 600 * L / W^2 + 0,75 * W - 25      (P in psi, L = Last pro Rad in lb, W = echte Reifenbreite in mm)

Der Hinterreifen wird direkt berechnet, der Vorderreifen ergibt sich als 93 % davon. Dazu kommen Zu- und Abschläge
für Untergrund (Werte der Rechner von BikeLab und SILCA), Schlauch, Karkasse und Nässe (Continental empfiehlt
rund 10 % weniger bei Regen). Das Ergebnis ist ein Startwert, den man nach Gefühl und Rollentest anpasst.
Reiner Rechenkern ohne Datenbank.
"""
from __future__ import annotations

from dataclasses import dataclass, field

PSI_PER_BAR = 14.5038
LB_PER_KG = 2.20462

# Anteil des Systemgewichts auf dem Hinterrad (Rennrad sportlicher, Gravel und MTB aufrechter)
REAR_SHARE = {"road": 0.60, "gravel": 0.55, "mtb": 0.55, "other": 0.60}
FRONT_OF_REAR = 0.93

# Untergrund: Abschlag auf den Druck. Asphalt-Werte BikeLab/SILCA, Gravel-Stufen nach SILCA.
SURFACES = {
    "asphalt": ("Glatter Asphalt", 0.0),
    "rough": ("Rauer Asphalt, Pflaster", -0.05),
    "hardpack": ("Fester Schotter, Waldweg", -0.09),
    "gravel": ("Lockerer Schotter", -0.175),
    "chunky": ("Grober Schotter, Trail", -0.33),
}
CASINGS = {"supple": ("Dünne, geschmeidige Karkasse", -0.05), "standard": ("Normale Karkasse", 0.0), "stiff": ("Pannenschutz, steife Karkasse", 0.05)}
WET_FACTOR = {"dry": 0.0, "damp": -0.05, "wet": -0.10}
TUBE_BONUS = 0.05          # Schlauch statt tubeless
HOOKLESS_MAX_PSI = 72.5    # 5,0 bar (ETRTO), bei Maulweite ab 30 mm 60 psi
HOOKLESS_WIDE_MAX_PSI = 60.0
RIM_DEFAULT = {"road": 19.0, "gravel": 24.0, "mtb": 29.0, "other": 19.0}
WIDTH_OFFSET = 0.3         # Reifen messen im Schnitt etwas breiter als aufgedruckt (bei 21 mm Maulweite ca. +1,5)
MIN_WARN_PSI = 25.0


@dataclass
class TireResult:
    front_bar: float
    rear_bar: float
    front_psi: int
    rear_psi: int
    real_width_mm: float
    system_kg: float
    notes: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def real_width(nominal_mm: float, rim_inner_mm: float | None, bike_type: str, measured_mm: float | None) -> float:
    """Echte Reifenbreite: gemessen, sonst geschätzt aus Aufdruck und Maulweite der Felge."""
    if measured_mm:
        return float(measured_mm)
    rim = rim_inner_mm or RIM_DEFAULT.get(bike_type, 19.0)
    return nominal_mm + WIDTH_OFFSET + 0.4 * (rim - 18.0)


def berto_rear_psi(load_lb: float, width_mm: float) -> float:
    return 600.0 * load_lb / width_mm**2 + 0.75 * width_mm - 25.0


def recommend(
    *,
    rider_kg: float,
    bike_kg: float,
    luggage_kg: float = 1.5,
    tire_width_mm: float,
    bike_type: str = "road",
    rim_inner_mm: float | None = None,
    measured_width_mm: float | None = None,
    surface: str = "asphalt",
    wetness: str = "dry",
    tubeless: bool = True,
    casing: str = "standard",
    hookless: bool = False,
) -> TireResult:
    if rider_kg <= 0 or tire_width_mm <= 0:
        raise ValueError("Gewicht und Reifenbreite müssen größer als 0 sein.")
    if surface not in SURFACES:
        raise ValueError(f"Unbekannter Untergrund: {surface}")
    if casing not in CASINGS:
        raise ValueError(f"Unbekannte Karkasse: {casing}")
    if wetness not in WET_FACTOR:
        raise ValueError(f"Unbekannte Nässe: {wetness}")

    notes: list[str] = []
    warnings: list[str] = []
    system = rider_kg + bike_kg + luggage_kg
    width = real_width(tire_width_mm, rim_inner_mm, bike_type, measured_width_mm)
    rear_load = system * LB_PER_KG * REAR_SHARE.get(bike_type, 0.60)

    rear = berto_rear_psi(rear_load, width)
    factor = 1.0 + SURFACES[surface][1] + CASINGS[casing][1] + WET_FACTOR[wetness]
    if not tubeless:
        factor += TUBE_BONUS
        notes.append("Mit Schlauch etwa 5 % mehr Druck als tubeless (Schutz vor Durchschlägen).")
    rear *= factor
    front = rear * FRONT_OF_REAR

    if surface != "asphalt":
        notes.append(f"Untergrund „{SURFACES[surface][0]}“: {SURFACES[surface][1] * 100:+.0f} %.".replace(".0 %", " %"))
    if wetness == "wet":
        notes.append("Nasse Straße: rund 10 % weniger Druck für mehr Haftung (Richtwert von Continental).")
    elif wetness == "damp":
        notes.append("Feuchte Straße: rund 5 % weniger Druck.")
    if casing != "standard":
        notes.append(f"{CASINGS[casing][0]}: {CASINGS[casing][1] * 100:+.0f} %.")

    if bike_type == "mtb" or width > 50:
        warnings.append("Für Mountainbike-Reifen ist das nur eine grobe Näherung. Hier zählen Reifenmodell und Gelände stark.")

    cap = None
    if hookless:
        cap = HOOKLESS_WIDE_MAX_PSI if (rim_inner_mm or 0) >= 30 else HOOKLESS_MAX_PSI
        if rear > cap or front > cap:
            warnings.append(
                f"Hookless-Felgen vertragen höchstens {cap / PSI_PER_BAR:.1f} bar. Der Druck wurde darauf begrenzt. "
                "Mit breiteren Reifen kommst du bei deinem Gewicht mit weniger Druck aus."
            )
            rear, front = min(rear, cap), min(front, cap)
    if rear < MIN_WARN_PSI:
        warnings.append("Sehr niedriger Druck: Achte auf Durchschläge und Felgenschäden und wähle zur Not einen breiteren Reifen.")
    warnings.append("Beachte immer den Maximaldruck, der auf Reifen und Felge steht, es gilt der niedrigere Wert.")

    rear = max(rear, 10.0)
    front = max(front, 10.0)
    return TireResult(
        front_bar=round(front / PSI_PER_BAR, 1),
        rear_bar=round(rear / PSI_PER_BAR, 1),
        front_psi=round(front),
        rear_psi=round(rear),
        real_width_mm=round(width, 1),
        system_kg=round(system, 1),
        notes=notes,
        warnings=warnings,
    )
