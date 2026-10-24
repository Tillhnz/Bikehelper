"""Standardkatalog: Komponenten und Wartungsintervalle für neue Räder.

Die Werte sind Richtwerte aus Herstellerangaben, Werkstatt-Ratgebern und Tests (Quellen siehe README).
Der Nässefaktor gibt an, wie viel schneller ein Teil verschleißt, wenn man im Regen oder auf nasser
Straße fährt: Ein Kilometer bei Nässe zählt dann wie `wet_factor` Kilometer. Belastbare Messwerte gibt es
nur für die Kette (Labortest eines Herstellers: nass etwa 1,5-fach, extrem nass etwa 2,3-fach). Die übrigen
Faktoren sind begründete Schätzwerte und pro Regel änderbar.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RuleTemplate:
    label: str
    interval_km: float | None = None
    interval_months: int | None = None
    wet_factor: float = 1.0
    hint: str = ""


@dataclass(frozen=True)
class ComponentTemplate:
    category: str
    name: str
    rules: tuple[RuleTemplate, ...]


WEAR_HINT = (
    "Mit einer Kettenlehre messen: bei 0,5 % Längung (11- und 12-fach) bzw. 0,75 % (10-fach und weniger) wechseln. "
    "Ein rechtzeitiger Wechsel schont Kassette und Kettenblätter."
)

# Kettenschmierung: Öl oder Wachs. Welche Art Wachs (Heißwachs im Tauchbad oder flüssiges Tropfwachs), legt man erst bei
# der Wartung fest; davon hängt das Intervall ab. Die Werte stammen aus Herstellerangaben und Tests (Quellen siehe README)
# und streuen stark: Heißwachs 300 bis 600 km, Tropfwachs 200 bis 400 km. Nach Regen immer früher. Zur Lebensdauer gibt es
# nur Herstellerangaben (bis zu dreimal so lang wie geölt, unabhängige Messungen fehlen), deshalb rechnen wir vorsichtig.
WAX_LUBE_LABEL = "Kette wachsen"
CHAIN_WEAR_LABEL = "Kette wechseln"
WAX_VARIANTS: dict[str, dict] = {
    "hot_wax": {
        "name": "Heißwachs (Tauchbad)", "interval_km": 500,
        "hint": "Je nach Wachs 300 bis 600 km. Zeit zum Nachwachsen: Die Kette wird dunkel statt weiß oder hellgrau, "
                "oder sie klingt trocken und knackt.",
    },
    "drip_wax": {
        "name": "Flüssigwachs (Tropfwachs)", "interval_km": 250,
        "hint": "Etwa 200 bis 400 km, sobald die Kette lauter wird. Empfindlicher gegen Regen als Heißwachs.",
    },
}
CHAIN_LUBES: dict[str, dict] = {
    "oil": {
        "name": "Öl",
        "lube": RuleTemplate(
            "Kette reinigen und schmieren", interval_km=200, wet_factor=2.0,
            hint="Etwa alle 200 km, nach Regenfahrten früher. Abwischen und neu schmieren, bevor sie trocken oder schmutzig läuft. "
                 "Bei viel Nässe und Streusalz ist Öl besser als Wachs.",
        ),
        "wear": RuleTemplate("Kette wechseln", interval_km=3000, wet_factor=2.0, hint=WEAR_HINT),
    },
    "wax": {
        "name": "Wachs",
        "lube": RuleTemplate(
            WAX_LUBE_LABEL, interval_km=500, wet_factor=2.5,
            hint="Beim Eintragen wählst du, ob heiß oder flüssig gewachst wurde: Heißwachs 300 bis 600 km, Flüssigwachs 200 bis 400 km. "
                 "Nach jeder Nassfahrt früher nachwachsen und die Kette trocknen, damit sie nicht rostet. "
                 "Bei dauerhaft nassem Wetter oder Salz ist Öl besser.",
        ),
        "wear": RuleTemplate(
            "Kette wechseln", interval_km=5000, wet_factor=2.0,
            hint=WEAR_HINT + " Gewachste Ketten halten laut Herstellern deutlich länger (bis dreimal so lang wie geölte). "
                 "Unabhängige Messungen fehlen, deshalb ist hier nur gut das Anderthalbfache angesetzt. Heißwachs hält tendenziell "
                 "länger als Flüssigwachs. Bei Nässe läuft die Kette schneller trocken, daher zählt Nässe weiter doppelt.",
        ),
    },
}
CHAIN_LUBE_KEYS = tuple(CHAIN_LUBES)
# Auch frühere Bezeichnungen erkennen, damit bestehende Regeln beim Umstellen gefunden werden
LUBE_LABELS = {v["lube"].label for v in CHAIN_LUBES.values()} | {
    "Kette neu wachsen (Heißwachs)", "Kette nachwachsen (Tropfwachs)",
}
LEGACY_LUBES = {"hot_wax": "hot_wax", "drip_wax": "drip_wax"}


def chain_rules(lube: str | None) -> tuple[RuleTemplate, RuleTemplate]:
    key = "wax" if lube in ("wax", "hot_wax", "drip_wax") else "oil"
    spec = CHAIN_LUBES[key]
    return (spec["lube"], spec["wear"])


def wax_interval_km(label: str, variant: str | None, default: float | None) -> float | None:
    """Intervall der Wachsregel je nach zuletzt eingetragener Wachsart."""
    if label == WAX_LUBE_LABEL and variant in WAX_VARIANTS:
        return WAX_VARIANTS[variant]["interval_km"]
    return default


CATALOG: dict[str, ComponentTemplate] = {
    "chain": ComponentTemplate("chain", "Kette", (
        RuleTemplate(
            "Kette reinigen und schmieren", interval_km=200, wet_factor=2.0,
            hint="Etwa alle 200 km, nach Regenfahrten früher. Abwischen und neu schmieren, bevor sie trocken oder schmutzig läuft.",
        ),
        RuleTemplate(
            "Kette wechseln", interval_km=3000, wet_factor=2.0,
            hint="Mit einer Kettenlehre messen: bei 0,5 % Längung (11- und 12-fach) bzw. 0,75 % (10-fach und weniger) wechseln. "
                 "Ein rechtzeitiger Wechsel schont Kassette und Kettenblätter. Mit Wachs hält eine Kette deutlich länger.",
        ),
    )),
    "cassette": ComponentTemplate("cassette", "Kassette", (
        RuleTemplate(
            "Kassette wechseln", interval_km=9000, wet_factor=1.5,
            hint="Faustregel: etwa drei Ketten pro Kassette. Wenn eine neue Kette springt, ist die Kassette fällig.",
        ),
    )),
    "chainring": ComponentTemplate("chainring", "Kettenblätter", (
        RuleTemplate(
            "Kettenblätter wechseln", interval_km=20000, wet_factor=1.5,
            hint="Bei rechtzeitigem Kettenwechsel halten sie mehrere Ketten lang. Ersetzen, wenn die Zähne spitz oder hakenförmig werden.",
        ),
    )),
    "tire_front": ComponentTemplate("tire_front", "Reifen vorn", (
        RuleTemplate(
            "Reifen vorn wechseln", interval_km=6000,
            hint="Stark vom Modell und Untergrund abhängig. Wechseln bei flachem Profil, sichtbarer Karkasse, Schnitten oder Rissen in der Flanke. Spätestens nach 10 Jahren.",
        ),
    )),
    "tire_rear": ComponentTemplate("tire_rear", "Reifen hinten", (
        RuleTemplate(
            "Reifen hinten wechseln", interval_km=4000,
            hint="Der Hinterreifen verschleißt zuerst. Wechseln bei flachem Profil, sichtbarer Karkasse, Schnitten oder Rissen in der Flanke.",
        ),
    )),
    "brake_pads": ComponentTemplate("brake_pads", "Bremsbeläge", (
        RuleTemplate(
            "Belagstärke prüfen", interval_km=500, wet_factor=2.0,
            hint="Alle 200 bis 500 km kontrollieren. Wechseln, wenn der Belag dünner als 1 bis 1,5 mm ist.",
        ),
        RuleTemplate(
            "Bremsbeläge wechseln", interval_km=1500, wet_factor=2.0,
            hint="Richtwert bei Scheibenbremsen: organische Beläge 500 bis 1.000 km, halbmetallische 700 bis 1.500 km, gesinterte 1.000 bis 2.000 km. "
                 "Bei Nässe verschleißen vor allem organische Beläge schneller.",
        ),
    )),
    "brake_fluid": ComponentTemplate("brake_fluid", "Bremsflüssigkeit", (
        RuleTemplate(
            "Bremse entlüften, Flüssigkeit wechseln", interval_months=12,
            hint="Nur für hydraulische Bremsen, sonst Komponente löschen. SRAM und TRP empfehlen jährlich; Shimano sagt, Rennradfahrer können oft mehrere Jahre warten. "
                 "DOT-Flüssigkeit spätestens alle 2 Jahre. Früher bei schwammigem Hebel.",
        ),
    )),
    "cables": ComponentTemplate("cables", "Brems- und Schaltzüge", (
        RuleTemplate(
            "Züge und Hüllen prüfen oder erneuern", interval_km=5000, interval_months=12, wet_factor=1.3,
            hint="Zugwechsel etwa jährlich, nach 6 Monaten auf Rost und Ausfransen prüfen. Hüllen halten etwa 10.000 km, bei zähem Lauf früher.",
        ),
    )),
    "bar_tape": ComponentTemplate("bar_tape", "Lenkerband", (
        RuleTemplate(
            "Lenkerband erneuern", interval_months=12,
            hint="Üblicherweise bei der Jahresinspektion. Früher, wenn es sich ablöst oder durchgescheuert ist.",
        ),
    )),
    "sealant": ComponentTemplate("sealant", "Dichtmilch", (
        RuleTemplate(
            "Dichtmilch nachfüllen", interval_months=4,
            hint="Je nach Marke, Klima und Fahrhäufigkeit alle 3 bis 6 Monate (Stan's: 2 bis 6 Monate) auffüllen. Dabei Ventil und Felgenband prüfen.",
        ),
        RuleTemplate(
            "Dichtmilch komplett erneuern", interval_months=15,
            hint="Etwa alle 12 bis 18 Monate den Reifen abnehmen, Reste entfernen und neue Dichtmilch einfüllen.",
        ),
    )),
    "headset": ComponentTemplate("headset", "Steuersatz", (
        RuleTemplate(
            "Steuersatz warten", interval_km=5000, interval_months=12, wet_factor=1.5,
            hint="Etwa jährlich prüfen und fetten. Bei viel Regen oder über 100 km pro Woche die Intervalle halbieren. Schutzbleche helfen.",
        ),
    )),
    "bottom_bracket": ComponentTemplate("bottom_bracket", "Innenlager", (
        RuleTemplate(
            "Innenlager prüfen und warten", interval_km=5000, interval_months=12, wet_factor=1.5,
            hint="Etwa jährlich auf Spiel und Rauheit prüfen. Nach vielen Regenfahrten fallen Innenlager öfter aus.",
        ),
    )),
    "hubs": ComponentTemplate("hubs", "Naben", (
        RuleTemplate(
            "Nabenlager warten", interval_km=5000, interval_months=12, wet_factor=1.5,
            hint="Etwa jährlich prüfen und bei Bedarf fetten oder tauschen, besonders bei Konuslagern und Freilauf.",
        ),
    )),
}

BIKE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "road": (
        "chain", "cassette", "chainring", "brake_pads", "brake_fluid",
        "cables", "bar_tape", "headset", "bottom_bracket", "hubs",
    ),
    "gravel": (
        "chain", "cassette", "chainring", "brake_pads", "brake_fluid",
        "cables", "bar_tape", "sealant", "headset", "bottom_bracket", "hubs",
    ),
    "mtb": (
        "chain", "cassette", "chainring", "brake_pads", "brake_fluid",
        "cables", "sealant", "headset", "bottom_bracket", "hubs",
    ),
    "other": ("chain", "cassette", "brake_pads", "cables"),
}


def categories_for(bike_type: str) -> tuple[str, ...]:
    return BIKE_TEMPLATES.get(bike_type, BIKE_TEMPLATES["other"])


# Reifen verwaltet die Reifensatz-Verwaltung (Kilometer je Mantelsatz). Ältere Reifen-Komponenten bleiben erhalten,
# zählen aber nicht mehr zur Wartung und werden nicht mehr neu angelegt.
LEGACY_CATEGORIES = ("tire_front", "tire_rear")


def catalog_payload() -> dict:
    """Für die Oberfläche: Katalog je Kategorie und die Vorlagen je Radtyp."""
    return {
        "components": {k: asdict(v) for k, v in CATALOG.items() if k not in LEGACY_CATEGORIES},
        "chain_lubes": {k: {"name": v["name"], "lube": asdict(v["lube"]), "wear": asdict(v["wear"])} for k, v in CHAIN_LUBES.items()},
        "wax_variants": WAX_VARIANTS,
        "bike_templates": {k: list(v) for k, v in BIKE_TEMPLATES.items()},
    }


# ---------- Anleitungen und Videos ----------
# Ausgewählt und einzeln geprüft (Stand Oktober 2026). Hauptquelle sind die Reparaturanleitungen von Park Tool, einem
# großen Werkzeughersteller; sie sind auf Englisch, mit Bildern und teils mit Video. Für Wachs die Anleitungen von Silca.
# `video` ist nur gesetzt, wenn auf der Seite ein Video eingebettet war. Zugeordnet wird über den Namen der Wartungsregel.
@dataclass(frozen=True)
class Guide:
    title: str
    url: str
    source: str
    video: bool = False
    lang: str = "en"


PT = "Park Tool"
_PT = "https://www.parktool.com/en-us/blog/repair-help/"
SILCA = "https://silca.cc/"

_G_CLEAN = (
    Guide("Kette reinigen und schmieren", _PT.replace("en-us", "en-int") + "chain-cleaning-with-a-park-tool-chain-scrubber", PT, True),
    Guide("Welches Schmiermittel wofür? (Öl, Wachs, Fett)", _PT.replace("en-us", "en-int") + "the-park-tool-guide-to-bicycle-lubricants-and-compounds", PT),
)
_G_WAX = (
    Guide("Kette reinigen und wachsen (Video)", SILCA + "pages/how-to-apply-chain-lube", "Silca", True),
    Guide("Gewachste Kette in jedem Wetter pflegen", SILCA + "blogs/silca/how-to-maintain-a-waxed-chain", "Silca"),
    Guide("Kette entfetten: Wachs vorbereiten", SILCA + "pages/ultimate-chain-stripper-and-wax-prep", "Silca"),
)
_G_CHAIN = (
    Guide("Wann die Kette gewechselt werden muss", _PT + "when-to-replace-a-chain-on-a-bicycle", PT, True),
    Guide("Kette wechseln (Kettenschaltung)", _PT + "chain-replacement-derailleur-bikes", PT),
    Guide("Kettenlänge bestimmen", _PT + "chain-length-sizing", PT),
)
_G_PADS = (
    Guide("Scheibenbremsbeläge aus- und einbauen", _PT.replace("en-us", "en-int") + "disc-brake-pad-removal-installation", PT, True),
    Guide("Hydraulische Scheibenbremse ausrichten", _PT + "hydraulic-disc-brake-alignment", PT),
    Guide("Bremsbeläge bei Felgenbremsen wechseln", _PT + "brake-pad-replacement-rim-brakes", PT),
)
_G_TUBELESS = (
    Guide("Tubeless-Reifen montieren und reparieren", _PT + "tubeless-tire-mounting-and-repair", PT, True),
    Guide("Auf Tubeless umrüsten", _PT + "tubeless-tire-conversion", PT),
)

GUIDES: dict[str, tuple[Guide, ...]] = {
    "Kette reinigen und schmieren": _G_CLEAN,
    WAX_LUBE_LABEL: _G_WAX,
    "Kette neu wachsen (Heißwachs)": _G_WAX,
    "Kette nachwachsen (Tropfwachs)": _G_WAX,
    "Kette wechseln": _G_CHAIN,
    "Kassette wechseln": (
        Guide("Kassette aus- und einbauen", _PT + "cassette-removal-and-installation", PT),
        Guide("Antrieb: Geräusche finden", _PT + "troubleshooting-a-noisy-drivetrain", PT),
    ),
    "Kettenblätter wechseln": (
        Guide("Kurbel aus- und einbauen (dreiteilig)", _PT + "crank-removal-and-installation-three-piece", PT),
        Guide("Wahl des Werkzeugs für den Kettenblatt-Verschlussring", _PT + "chainring-lockring-tool-selection", PT),
    ),
    "Reifen vorn wechseln": (
        Guide("Reifen und Schlauch aus- und einbauen", _PT + "tire-and-tube-removal-and-installation", PT, True),
    ) + _G_TUBELESS[:1],
    "Reifen hinten wechseln": (
        Guide("Reifen und Schlauch aus- und einbauen", _PT + "tire-and-tube-removal-and-installation", PT, True),
    ) + _G_TUBELESS[:1],
    "Belagstärke prüfen": _G_PADS[:2],
    "Bremsbeläge wechseln": _G_PADS,
    "Bremse entlüften, Flüssigkeit wechseln": (
        Guide("Shimano-Bremsen entlüften (Mineralöl)", _PT + "shimano-hydraulic-brake-service-and-adjustment", PT),
        Guide("SRAM-Bremsen entlüften (DOT)", _PT + "brake-bleeding-for-sram-hydraulic-brakes-using-the-bkd-1", PT, True),
    ),
    "Züge und Hüllen prüfen oder erneuern": (
        Guide("Schaltzug wechseln (Rennlenker)", _PT + "shift-cable-replacement-drop-bars", PT, True),
        Guide("Bremszug und -hülle einbauen (Rennlenker)", _PT.replace("en-us", "en-int") + "brake-housing-cable-installation-drop-bars", PT),
        Guide("Zughüllen richtig ablängen", _PT + "cutting-and-sizing-cable-housing", PT),
    ),
    "Lenkerband erneuern": (
        Guide("Lenkerband wickeln (Rennlenker)", _PT + "handlebar-tape-installation-drop-bars", PT, True),
    ),
    "Dichtmilch nachfüllen": _G_TUBELESS,
    "Dichtmilch komplett erneuern": _G_TUBELESS,
    "Steuersatz warten": (
        Guide("Gewindeloser Steuersatz: warten und fetten", _PT.replace("en-us", "en-int") + "threadless-headset-service", PT, True),
        Guide("Gewindeloser Steuersatz: einstellen", _PT.replace("en-us", "en-int") + "how-to-adjust-a-threadless-headset", PT),
    ),
    "Innenlager prüfen und warten": (
        Guide("Pressfit-Innenlager aus- und einbauen", _PT + "bottom-bracket-removal-installation-press-fit", PT, True),
        Guide("Innenlager zum Einschrauben aus- und einbauen", _PT + "bottom-bracket-removal-installation-thread-together", PT),
        Guide("Innenlager mit Konuslager warten", _PT + "bottom-bracket-service-adjustable-cup-and-cone", PT),
    ),
    "Nabenlager warten": (
        Guide("Nabe warten und einstellen (Konuslager)", _PT.replace("en-us", "en-int") + "hub-overhaul-and-adjustment", PT, True),
        Guide("Freilaufkörper warten", _PT.replace("en-us", "en-int") + "freehub-service", PT),
    ),
}


def guides_for(label: str) -> list[dict]:
    return [asdict(g) for g in GUIDES.get(label, ())]
