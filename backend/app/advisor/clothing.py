"""Kleidungsempfehlung aus Wetter, Fahrtdauer und Intensität.

Vorgehen: Aus Temperatur, Wind, Regen, Fahrtdauer, Intensität und persönlichem Kälteempfinden wird eine
"Kleidungstemperatur" berechnet. Sie wählt eine Stufe (kurz-kurz bis lang-lang mit Winterausstattung). Dazu kommen
Zusätze für Regen, Wind, Sonne, Dunkelheit und Mitnehmen. Die Stufen orientieren sich an den Tabellen von Roadman,
Löffler und Down The Road (siehe README); die Stufengrenzen sind ein Mittel aus diesen Quellen, die Zu- und Abschläge
sind eigene, begründete Annahmen und gehören zum persönlichen Geschmack.

Reiner Rechenkern ohne Datenbank und Netzwerk.
"""
from __future__ import annotations

from dataclasses import dataclass, field

SPEED_KMH = {"easy": 22.0, "normal": 27.0, "hard": 32.0}
SPEED_BY_TYPE = {"road": 0.0, "gravel": -4.0, "mtb": -8.0, "other": -6.0}
INTENSITY_ADJ = {"easy": -2.0, "normal": 0.0, "hard": 3.0}      # hart: eine Schicht weniger (ca. 3 °C)
SENSITIVITY_ADJ = {"cold": -2.0, "normal": 0.0, "warm": 2.0}
RAIN_HEAVY_ADJ = -3.5   # "nasse Kälte" fühlt sich etwa eine Stufe kälter an
RAIN_LIGHT_ADJ = -1.5


def wind_chill_loss(temp_c: float, speed_kmh: float) -> float:
    """Wie viel kälter es sich durch Fahrtwind anfühlt (Formel von Environment Canada, gedämpft über 10 °C)."""
    if temp_c >= 20 or speed_kmh < 5:
        return 0.0
    t = min(temp_c, 10.0)
    v16 = speed_kmh**0.16
    wc = 13.12 + 0.6215 * t - 11.37 * v16 + 0.3965 * t * v16
    loss = max(0.0, t - wc)
    if temp_c > 10:
        loss *= (20.0 - temp_c) / 10.0
    return loss


@dataclass
class ClothingAdvice:
    headline: str
    top: str
    legs: str
    effective_temp: float
    groups: dict[str, list[str]] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _add(groups: dict[str, list[str]], key: str, *items: str) -> None:
    lst = groups.setdefault(key, [])
    for i in items:
        if i not in lst:
            lst.append(i)


def advise(
    *,
    temp_avg: float,
    temp_start: float | None = None,
    temp_min: float | None = None,
    temp_max: float | None = None,
    wind_kmh: float = 0.0,
    gust_kmh: float | None = None,
    precip_mm: float = 0.0,
    precip_prob: float | None = None,
    wet_minutes: float = 0.0,
    uv: float | None = None,
    duration_min: float = 90.0,
    intensity: str = "normal",
    speed_kmh: float | None = None,
    sensitivity: str = "normal",
    bike_type: str = "road",
    elevation_gain_m: float | None = None,
    dark_minutes: float = 0.0,
) -> ClothingAdvice:
    if intensity not in SPEED_KMH or sensitivity not in SENSITIVITY_ADJ:
        raise ValueError("Unbekannte Intensität oder Kälteempfindlichkeit.")
    start = temp_avg if temp_start is None else temp_start
    tmin = min(start, temp_avg) if temp_min is None else temp_min
    tmax = max(start, temp_avg) if temp_max is None else temp_max

    reasons: list[str] = []
    ref = (start + temp_avg) / 2
    normal_speed = SPEED_KMH["normal"] + SPEED_BY_TYPE.get(bike_type, 0.0)
    intensity_adj = INTENSITY_ADJ[intensity]
    if speed_kmh is not None:
        # Durchschnittsgeschwindigkeit statt Stufe: Abweichung vom normalen Tempo dieses Radtyps, 0,6 °C je km/h
        delta = speed_kmh - normal_speed
        intensity_adj = max(INTENSITY_ADJ["easy"], min(INTENSITY_ADJ["hard"], 0.6 * delta))
        intensity = "easy" if delta <= -3 else "hard" if delta >= 3 else "normal"
    speed = max(10.0, speed_kmh if speed_kmh is not None else SPEED_KMH[intensity] + SPEED_BY_TYPE.get(bike_type, 0.0))
    # Die Stufen der Quellen gelten schon für normalen Fahrtwind. Zusätzlich zählt nur, was der echte Wind dazu beiträgt
    # (im Schnitt die Hälfte des Windes als Gegen- oder Seitenwind).
    loss = wind_chill_loss(ref, speed + 0.5 * wind_kmh) - wind_chill_loss(ref, speed)
    te = ref - loss
    if loss >= 1:
        reasons.append(f"Der Wind lässt es sich etwa {loss:.0f} °C kälter anfühlen.")

    prob = precip_prob if precip_prob is not None else 0.0
    heavy_rain = wet_minutes >= 10 or precip_mm >= 0.5 or prob >= 60
    light_rain = not heavy_rain and (precip_mm >= 0.1 or prob >= 40 or wet_minutes > 0)
    if heavy_rain:
        te += RAIN_HEAVY_ADJ
        reasons.append("Regen: Nasse Kälte zieht mehr Wärme ab, deshalb eine Stufe wärmer anziehen.")
    elif light_rain:
        te += RAIN_LIGHT_ADJ
        reasons.append("Leichter Regen möglich: etwas wärmer anziehen.")

    te += intensity_adj + SENSITIVITY_ADJ[sensitivity]
    if intensity == "hard":
        reasons.append("Bei hoher Intensität wird dir warm: eine Schicht weniger.")
    elif intensity == "easy":
        reasons.append("Bei lockerem Tempo erzeugst du weniger Wärme: eine Schicht mehr.")
    if sensitivity == "cold":
        reasons.append("Du frierst schnell: eine Stufe wärmer.")
    elif sensitivity == "warm":
        reasons.append("Du schwitzt schnell: eine Stufe leichter.")
    if duration_min < 60:
        te -= 1.5
        reasons.append("Kurze Fahrt: Der Körper wird nicht richtig warm, daher etwas wärmer starten.")
    elif duration_min >= 240:
        te -= 1.0
        reasons.append("Lange Fahrt: Gegen Ende lässt die Wärmeproduktion nach, daher etwas mehr Reserve.")
    te = round(te, 1)

    g: dict[str, list[str]] = {}
    warnings: list[str] = []

    # --- Stufen ---
    if te >= 24:
        top, legs, headline = "Kurzes, helles Trikot", "Kurze Radhose", "Kurz / kurz"
        _add(g, "Oberkörper", "Kurzes, helles Trikot", "Optional: dünnes Netz-Unterhemd")
        _add(g, "Beine", "Kurze Radhose")
    elif te >= 20:
        top, legs, headline = "Kurzes Trikot", "Kurze Radhose", "Kurz / kurz"
        _add(g, "Oberkörper", "Kurzes Trikot")
        _add(g, "Beine", "Kurze Radhose")
    elif te >= 16:
        top, legs, headline = "Kurzes Trikot mit Armlingen", "Kurze Radhose", "Kurz mit Armlingen / kurz"
        _add(g, "Oberkörper", "Kurzes Trikot", "Armlinge (kannst du später in die Tasche stecken)", "Optional: dünnes Unterhemd")
        _add(g, "Beine", "Kurze Radhose", "Optional bei Wind oder kühlem Start: Knielinge")
    elif te >= 12:
        top, legs, headline = "Langarm-Trikot oder Kurzarm mit Armlingen", "Beinlinge oder lange Hose", "Lang / Beinlinge"
        _add(g, "Oberkörper", "Langarm-Trikot (oder Kurzarm mit Armlingen)", "Dünnes Unterhemd", "Weste oder dünne Windjacke")
        _add(g, "Beine", "Radhose mit Beinlingen (oder dünne lange Hose)")
        _add(g, "Hände", "Dünne Handschuhe mit langen Fingern")
        _add(g, "Füße", "Dünne Socken, Zehenwärmer bei kühlen Füßen")
    elif te >= 8:
        top, legs, headline = "Langarm-Thermotrikot mit Unterhemd", "Lange Radhose", "Lang / lang"
        _add(g, "Oberkörper", "Langarm-Thermotrikot", "Funktionsunterhemd (Merino oder Kunstfaser)", "Weste oder leichte Winddichte Jacke")
        _add(g, "Beine", "Lange Radhose mit Wärmefutter")
        _add(g, "Hände", "Winddichte Handschuhe mit langen Fingern")
        _add(g, "Füße", "Überschuhe", "Wärmere Socken")
        _add(g, "Kopf & Hals", "Dünnes Stirnband oder Mütze unter dem Helm")
    elif te >= 4:
        top, legs, headline = "Thermotrikot mit winddichter Jacke", "Lange Thermo-Radhose", "Lang / lang, winterfest"
        _add(g, "Oberkörper", "Langarm-Thermotrikot", "Warmes Unterhemd", "Winddichte, wärmende Jacke")
        _add(g, "Beine", "Lange Thermo-Radhose")
        _add(g, "Hände", "Gefütterte, winddichte Winterhandschuhe")
        _add(g, "Füße", "Dicke Überschuhe", "Warme Socken")
        _add(g, "Kopf & Hals", "Helmmütze oder Stirnband über den Ohren", "Halstuch oder Schlauchtuch")
    elif te >= 0:
        top, legs, headline = "Winterjacke über Thermotrikot", "Dicke Thermo-Radhose", "Lang / lang, Winterausrüstung"
        _add(g, "Oberkörper", "Dickes Thermotrikot oder Softshell", "Winddichte Winterjacke", "Warmes Unterhemd")
        _add(g, "Beine", "Dickste lange Thermo-Radhose")
        _add(g, "Hände", "Dicke Winterhandschuhe (Lobster-Handschuhe)")
        _add(g, "Füße", "Neopren-Überschuhe", "Dicke Socken")
        _add(g, "Kopf & Hals", "Dünne Helmmütze", "Halstuch bis über das Kinn")
    else:
        top, legs, headline = "Winterjacke über Thermotrikot", "Dicke Thermo-Radhose", "Lang / lang, Winterausrüstung"
        _add(g, "Oberkörper", "Dickes Thermotrikot oder Softshell", "Winddichte Winterjacke", "Warmes Unterhemd")
        _add(g, "Beine", "Dickste lange Thermo-Radhose")
        _add(g, "Hände", "Dicke Winterhandschuhe, bei Bedarf Lenkerstulpen")
        _add(g, "Füße", "Neopren-Überschuhe", "Dicke Socken", "Wärmepads für die Zehen")
        _add(g, "Kopf & Hals", "Dünne Helmmütze", "Sturmhaube oder Halstuch über dem Gesicht")
        _add(g, "Mitnehmen", "Rettungsdecke")
        warnings.append("Unter 0 °C kühlen Hände und Füße schnell aus. Plane die Fahrt kürzer und in Reichweite von Wärme.")

    # --- Regen ---
    if heavy_rain or light_rain:
        if te >= 20:
            _add(g, "Regen & Wind", "Dünne, verpackbare Regenjacke in die Tasche" if light_rain else "Dünne Regenjacke")
        elif te >= 12:
            _add(g, "Regen & Wind", "Wasserdichte Regenjacke", "Überschuhe")
        else:
            _add(g, "Regen & Wind", "Wasserdichte Regenjacke", "Wasserdichte Handschuhe oder Neoprenhandschuhe", "Überschuhe")
        _add(g, "Kopf & Hals", "Kappe mit Schirm unter dem Helm hält Regen aus den Augen")
        _add(g, "Regen & Wind", "Schutzbleche, wenn vorhanden", "Radbrille mit klaren Gläsern")
        if te >= 16:
            _add(g, "Regen & Wind", "Wechselsocken im Beutel (Trockenhalten der Füße zählt)")
    # --- Wind ---
    if (wind_kmh >= 25 or (gust_kmh or 0) >= 40) and te < 22:
        _add(g, "Regen & Wind", "Winddichte Weste oder Jacke")
        reasons.append(f"Starker Wind (bis {max(wind_kmh, gust_kmh or 0):.0f} km/h): ein winddichtes Teil lohnt sich.")
    # --- Sonne ---
    if te >= 22 or (uv or 0) >= 6:
        _add(g, "Sonne", "Sonnencreme", "Sonnenbrille")
    if te >= 26 or tmax >= 28:
        _add(g, "Sonne", "Helle Kappe unter dem Helm", "Mindestens zwei Flaschen, bei Hitze mit Elektrolyten")
    # --- Temperaturschwankung, Höhenmeter ---
    if tmax - start >= 5:
        _add(g, "Mitnehmen", "Armlinge oder Weste zum Ausziehen (Taschen im Trikot)")
        reasons.append(f"Es wird während der Fahrt bis zu {tmax - start:.0f} °C wärmer: Zwiebelprinzip nutzen.")
    if start - tmin >= 4:
        reasons.append(f"Es kühlt während der Fahrt um bis zu {start - tmin:.0f} °C ab: Reserve einpacken.")
        _add(g, "Mitnehmen", "Weste oder dünne Jacke als Reserve")
    if elevation_gain_m and elevation_gain_m >= 500 and te < 18:
        _add(g, "Mitnehmen", "Weste oder Windjacke für die Abfahrt (rund 6 bis 8 °C kälter je 1000 m Höhe)")
    # --- Dauer ---
    if duration_min >= 180:
        _add(g, "Mitnehmen", "Dünne Regen- oder Windjacke als Notfall-Schicht")
        if te < 14:
            _add(g, "Mitnehmen", "Zweites Paar Handschuhe")
        _add(g, "Mitnehmen", "Verpflegung, bei kühlem Wetter mehr als im Sommer")
        reasons.append("Lange Fahrt: Das Wetter kann umschlagen, eine Notfall-Schicht gehört in die Tasche.")
    # --- Dunkelheit ---
    if dark_minutes >= 5:
        _add(g, "Sichtbarkeit", "Licht vorn und hinten", "Reflektierende Kleidung oder Weste")
        reasons.append(f"Etwa {dark_minutes:.0f} Minuten der Fahrt liegen in der Dunkelheit.")
    # --- Glätte ---
    if tmin <= 3 and (heavy_rain or light_rain or precip_mm > 0):
        warnings.append("Glatteisgefahr bei Temperaturen um den Gefrierpunkt mit Niederschlag. Überlege, die Fahrt zu verschieben.")
    elif tmin <= 1:
        warnings.append("Frostgefahr: Brücken, Schatten und Waldwege können glatt sein.")

    order = ["Oberkörper", "Beine", "Hände", "Füße", "Kopf & Hals", "Regen & Wind", "Sonne", "Mitnehmen", "Sichtbarkeit"]
    groups = {k: g[k] for k in order if k in g}
    return ClothingAdvice(
        headline=headline, top=top, legs=legs, effective_temp=te, groups=groups, reasons=reasons, warnings=warnings,
    )
