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
                 "Nach einer Nassfahrt die Kette zuerst abwischen und trocknen lassen, damit sie nicht rostet. Nachwachsen lohnt, wenn sie verschmutzt, rostig oder sehr nass geworden ist (Heißwachsen presst das Wasser auch aus den Gliedern). "
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
    "pulleys": ComponentTemplate("pulleys", "Schaltröllchen", (
        RuleTemplate(
            "Schaltröllchen prüfen und wechseln", interval_km=5000, wet_factor=1.5,
            hint="Richtwert: etwa alle 5.000 bis 7.000 km über einen Wechsel nachdenken, bei Schotter und Matsch früher. "
                 "Tauschen bei spitzen oder runden Zähnen, seitlichem Spiel, rauem Lauf, Klicken oder ungenauem Schalten.",
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
    "pedals": ComponentTemplate("pedals", "Pedale", (
        RuleTemplate(
            "Pedalgewinde fetten, Lager prüfen", interval_months=12,
            hint="Beim Einbau und einmal im Jahr: Gewinde reinigen und dünn mit Montagefett oder Anti-Seize-Paste einreiben, "
                 "dann mit dem Drehmoment des Herstellers festziehen (meist etwa 30 bis 40 Nm). Rechts Rechtsgewinde, links Linksgewinde. "
                 "Das verhindert Knarzen und festgerostete Pedalen.",
        ),
    )),
    "fasteners": ComponentTemplate("fasteners", "Schrauben und Gewinde", (
        RuleTemplate(
            "Gewinde fetten, Schrauben nachziehen", interval_months=12,
            hint="Einmal im Jahr bei der Inspektion: Schrauben von Vorbau, Lenker, Sattelstütze, Kurbel, Kassettenverschlussring und Steckachsen "
                 "lösen, Gewinde dünn fetten und mit dem Drehmoment des Herstellers anziehen (steht meist auf dem Bauteil). "
                 "An Carbon-Bauteilen statt Fett die Carbon-Montagepaste nehmen. Nie Bremsscheiben oder Beläge einfetten.",
        ),
    )),
}

BIKE_TEMPLATES: dict[str, tuple[str, ...]] = {
    "road": (
        "chain", "cassette", "chainring", "pulleys", "brake_pads", "brake_fluid",
        "cables", "bar_tape", "headset", "bottom_bracket", "hubs", "pedals", "fasteners",
    ),
    "gravel": (
        "chain", "cassette", "chainring", "pulleys", "brake_pads", "brake_fluid",
        "cables", "bar_tape", "sealant", "headset", "bottom_bracket", "hubs", "pedals", "fasteners",
    ),
    "mtb": (
        "chain", "cassette", "chainring", "pulleys", "brake_pads", "brake_fluid",
        "cables", "sealant", "headset", "bottom_bracket", "hubs", "pedals", "fasteners",
    ),
    "other": ("chain", "cassette", "pulleys", "brake_pads", "cables", "pedals"),
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
        "checks": {k: asdict(v) for k, v in CHECKS.items()},
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
    "Pedalgewinde fetten, Lager prüfen": (
        Guide("Pedale aus- und einbauen", _PT + "pedal-installation-and-removal", PT),
    ),
    "Schaltröllchen prüfen und wechseln": (
        Guide("Schaltwerk zerlegen und warten (mit Schaltröllchen)", _PT + "rear-derailleur-overhaul", PT, True),
    ),
    "Gewinde fetten, Schrauben nachziehen": (
        Guide("Drehmomente und Gewinde richtig vorbereiten", _PT + "torque-specifications-and-concepts", PT),
    ),
    "Nabenlager warten": (
        Guide("Nabe warten und einstellen (Konuslager)", _PT.replace("en-us", "en-int") + "hub-overhaul-and-adjustment", PT, True),
        Guide("Freilaufkörper warten", _PT.replace("en-us", "en-int") + "freehub-service", PT),
    ),
}


def guides_for(label: str) -> list[dict]:
    return [asdict(g) for g in GUIDES.get(label, ())]


# Prüfregel -> Verschleißregel, die sich nach dem Prüfergebnis richtet
INSPECTIONS = {"Belagstärke prüfen": "Bremsbeläge wechseln"}
WEAR_TO_INSPECTION = {v: k for k, v in INSPECTIONS.items()}
INSPECTION_RESULTS = ("good", "watch", "replace")


# ---------- Sichtprüfung je Komponente ----------
# Kurz gehalten und bewusst vorsichtig: Was man ohne Spezialwerkzeug sehen, fühlen und hören kann, woran man ein gutes oder
# ein schlechtes Teil erkennt und was dann zu tun ist. Grenzwerte stehen in den Regeln; im Zweifel zählt die Angabe des Herstellers.
@dataclass(frozen=True)
class Check:
    tools: str                 # was man braucht
    how: tuple[str, ...]       # Schritte der Prüfung
    good: tuple[str, ...]      # so sieht ein gutes Teil aus
    bad: tuple[str, ...]       # Warnzeichen
    act: str                   # was dann zu tun ist


CHECKS: dict[str, Check] = {
    "chain": Check(
        tools="Lappen, Kettenlehre (am besten), gute Beleuchtung",
        how=(
            "Kette mit einem Lappen abwischen, damit du Metall und Glieder siehst.",
            "Kettenlehre einhängen und ablesen: Sie zeigt, ob die Längung unter dem Grenzwert liegt (0,5 % bei 11- und 12-fach, 0,75 % bei 10-fach und weniger).",
            "Ohne Lehre: Kette vorn am Kettenblatt ein Stück vom Zahn abheben. Lässt sie sich deutlich abziehen, sodass ein Zahn sichtbar wird, ist sie gelängt.",
            "Kurbel langsam rückwärts drehen und Glied für Glied ansehen. Achte auf steife Glieder, die an einer Stelle abknicken, und auf Laschen, die seitlich verdreht sind.",
        ),
        good=(
            "Lehre bleibt unter dem Grenzwert.",
            "Alle Glieder laufen leicht und gleichmäßig durch die Umlenkrollen.",
            "Metall glänzt oder ist bei Wachs matt hellgrau, ohne Rost.",
            "Läuft leise und schaltet sauber.",
        ),
        bad=(
            "Lehre zeigt Grenzwert oder mehr.",
            "Rost, steife Glieder, verdrehte oder verbogene Laschen.",
            "Risse in einer Lasche oder ein herausstehender Nietkopf.",
            "Schwarze, schmierige Paste, Knacken oder Springen unter Last.",
        ),
        act="Bei Grenzwert die Kette zeitnah wechseln, bevor sie Kassette und Kettenblätter mit abnutzt. Bei Rissen oder gebrochenem Glied nicht weiterfahren.",
    ),
    "cassette": Check(
        tools="Taschenlampe, saubere Kassette",
        how=(
            "Kassette und Ritzel mit Lappen oder Bürste reinigen.",
            "Zähne von der Seite ansehen und mit dem Profil neuer Ritzel vergleichen, falls du eines zur Hand hast.",
            "Kurbel drehen und prüfen, ob die Kette unter Last (kräftig antreten) springt.",
            "Mit der Hand am Ritzelpaket rütteln: Es darf nichts wackeln und der Verschlussring muss fest sitzen.",
        ),
        good=(
            "Zähne sind symmetrisch und trapezförmig.",
            "Die Kette liegt ruhig auf und springt nicht.",
            "Schaltvorgänge laufen ohne Schleifen und Rattern.",
        ),
        bad=(
            "Zähne sind spitz oder hakenförmig wie Haifischflossen.",
            "Eine neue Kette springt unter Last.",
            "Rost, abgebrochene Zähne oder ein wackelndes Ritzelpaket.",
        ),
        act="Die Kassette zusammen mit einer neuen Kette wechseln, wenn die Zähne verschlissen sind. Einzelne Ritzel zu tauschen lohnt kaum.",
    ),
    "chainring": Check(
        tools="Taschenlampe, Inbusschlüssel passend zu den Schrauben",
        how=(
            "Kettenblätter reinigen und die Zähne von der Seite ansehen.",
            "Kurbel langsam drehen und den Abstand zu Umwerfer oder Kettenstrebe beobachten: Er soll nicht pendeln.",
            "Die Befestigungsschrauben auf festen Sitz prüfen, ohne sie mit Gewalt zu belasten (Drehmoment nach Herstellerangabe).",
        ),
        good=(
            "Zähne sind gleichmäßig und beidseitig symmetrisch.",
            "Das Blatt läuft ohne Schlag.",
            "Alle Schrauben sitzen fest.",
        ),
        bad=(
            "Zähne sind spitz, hakenförmig oder abgebrochen.",
            "Das Blatt schlägt seitlich oder ist verbogen.",
            "Lockere Schrauben, Risse an Zähnen oder Armen.",
        ),
        act="Verschlissene oder verbogene Blätter wechseln, am besten mit neuer Kette. Rissige Teile nicht weiterfahren.",
    ),
    "tires": Check(
        tools="Taschenlampe, Pumpe mit Manometer, Fingernagel oder kleine Nadel",
        how=(
            "Reifen auf den vorgeschriebenen Druck bringen und das Rad langsam drehen.",
            "Die Lauffläche Streifen für Streifen absuchen: Profil, Mitte und Schultern. Der Hinterreifen verschleißt in der Mitte zuerst.",
            "Flanken ansehen und mit dem Daumen biegen: Risse, poröser Gummi, Beulen.",
            "Eingedrungene Steinchen oder Glas mit Fingernagel oder Nadel entfernen und prüfen, wie tief der Schnitt geht.",
            "Auf der Flanke das Herstelldatum (DOT-Nummer) suchen, falls vorhanden.",
        ),
        good=(
            "Die Lauffläche ist gleichmäßig gerundet, das Profil oder die Verschleißmarken sind noch sichtbar.",
            "Flanken sind geschmeidig, ohne Risse.",
            "Nur kleine, oberflächliche Schnitte im Gummi.",
            "Der Reifen hält den Druck.",
        ),
        bad=(
            "Die Mitte ist flach geschliffen, Verschleißmarken sind weg.",
            "Die Gewebelage (Karkasse) schimmert durch oder Fäden sind sichtbar.",
            "Tiefe Schnitte, Beulen, Blasen oder Risse in der Flanke.",
            "Der Gummi ist spröde, hart und rissig, besonders bei alten Reifen.",
            "Mehrere Platten in kurzer Zeit.",
        ),
        act="Bei sichtbarer Karkasse, Beulen oder tiefen Schnitten sofort wechseln. Alte, rissige Reifen auch bei gutem Profil erneuern. Hinterreifen häufiger prüfen als den vorderen.",
    ),
    "brake_pads": Check(
        tools="Taschenlampe, bei Scheibenbremsen ein Schieber oder Lineal, saubere Hände",
        how=(
            "Scheibenbremse: Von oben oder unten mit Taschenlampe in den Sattel sehen. Du siehst zwei Beläge links und rechts der Scheibe. Miss das Belagmaterial ohne die metallische Trägerplatte.",
            "Felgenbremse: Belag von vorn ansehen und die Rillen oder Verschleißmarke im Gummi suchen.",
            "Die Scheibe ansehen: Sie soll glatt sein. Die Mindestdicke steht meist auf der Scheibe (häufig 1,5 mm).",
            "Rad drehen und achten, ob etwas schleift. Beim Bremsen auf Quietschen, Rubbeln oder Nachlassen achten.",
        ),
        good=(
            "Belag ist dicker als etwa 1,5 mm und beide Seiten sind ähnlich abgenutzt.",
            "Beläge sind matt und trocken.",
            "Scheibe ist glatt, gerade und über der Mindestdicke.",
            "Die Bremse greift gleichmäßig und leise.",
        ),
        bad=(
            "Belag ist dünner als 1 bis 1,5 mm oder die Trägerplatte ist zu sehen.",
            "Glasierte, glänzende Oberfläche oder Ölflecken (Verschmutzung).",
            "Metallisches Schleifen, Pulsieren oder starkes Quietschen.",
            "Verzogene, tief eingelaufene oder zu dünne Scheibe, bei Felgenbremsen eine abgefahrene Verschleißmarke.",
        ),
        act="Beläge je Bremse paarweise wechseln und danach einbremsen. Verölte Beläge und Scheiben reinigen oder tauschen. Bei metallischem Schleifen sofort nicht mehr fahren, sonst wird die Scheibe zerstört.",
    ),
    "brake_fluid": Check(
        tools="Lappen, Taschenlampe",
        how=(
            "Den Bremshebel mehrmals ziehen: Spüre den Druckpunkt. Er soll fest und klar sein.",
            "Hebel bei gedrückter Stellung 10 Sekunden halten: Er darf nicht langsam nachgeben.",
            "Leitung, Anschlüsse am Hebel und am Sattel, den Ausgleichsbehälter und die Kolben auf feuchte Stellen absuchen.",
            "Die Leitung entlang ansehen: Knicke, Scheuerstellen, Risse. Bei DOT-Bremsen die Farbe im Behälter prüfen, falls einsehbar.",
        ),
        good=(
            "Fester Druckpunkt, der Hebel geht nicht bis zum Lenker.",
            "Leitung und Anschlüsse sind trocken.",
            "Die Bremskraft bleibt auch bei langen Abfahrten gleich.",
        ),
        bad=(
            "Der Hebel fühlt sich schwammig an oder lässt sich bis zum Lenker ziehen.",
            "Der Druckpunkt wandert oder wird nach einer Abfahrt weich.",
            "Feuchte oder ölige Stellen an Anschlüssen oder am Sattel.",
            "Geknickte, scheuernde oder gerissene Leitung, dunkle Bremsflüssigkeit bei DOT.",
        ),
        act="Bei schwammigem Hebel entlüften, spätestens nach dem empfohlenen Intervall die Flüssigkeit wechseln. Bei Leckage nicht weiterfahren und zur Werkstatt. DOT-Flüssigkeit greift Lack an.",
    ),
    "cables": Check(
        tools="Lappen, Taschenlampe",
        how=(
            "Die Züge von Hebel bis Bremse oder Schaltwerk mit den Augen und Fingern abfahren.",
            "Hüllenenden ansehen: Sitzen die Endkappen, sind die Hüllen ausgefranst, geknickt oder verrostet?",
            "Zug an den Klemmschrauben und dort, wo er sichtbar aus der Hülle kommt, auf Rost und gespreizte Drähte prüfen.",
            "Hebel betätigen und loslassen: Er soll zügig zurückfedern. Bei der Schaltung prüfen, ob sie sauber und ohne Verzögerung schaltet.",
        ),
        good=(
            "Züge glänzen, sind sauber und haben keine abstehenden Drähte.",
            "Hüllen sind glatt, ohne Knicke, Endkappen sitzen.",
            "Hebel gehen leicht und federn schnell zurück.",
            "Die Schaltung ist präzise.",
        ),
        bad=(
            "Rost, ausgefranste oder gespreizte Drähte.",
            "Geknickte, gerissene oder aufgeplatzte Hüllen, fehlende Endkappen.",
            "Hebel gehen schwer oder federn träge zurück.",
            "Die Schaltung ist ungenau, obwohl sie eingestellt ist.",
        ),
        act="Zug und Hülle gemeinsam erneuern, sobald sie rostig, ausgefranst oder zäh sind. Ein gerissener Bremszug ist ein Sicherheitsrisiko: lieber früher wechseln.",
    ),
    "pedals": Check(
        tools="Pedalschlüssel oder Inbus (je nach Pedal), Lappen, Montagefett oder Anti-Seize-Paste",
        how=(
            "Pedale an Kurbel und Pedalachse anfassen und seitlich wackeln: Es darf kein Spiel zwischen Pedale und Kurbel geben.",
            "Pedalkörper um die Achse drehen: leichtgängig, ohne Rauheit, Klemmen oder spürbares Spiel.",
            "Beim Fahren auf Knarzen oder Knacken achten, das im Takt der Kurbel kommt.",
            "Beim Ausbau (einmal im Jahr oder beim Wechsel): Gewinde und Kurbelauge reinigen, Gewinde dünn fetten, wieder einschrauben. Rechte Pedale hat Rechtsgewinde (im Uhrzeigersinn festziehen), die linke Linksgewinde (gegen den Uhrzeigersinn, von der jeweiligen Seite gesehen).",
        ),
        good=(
            "Kein Spiel an der Kurbel, die Achse läuft leicht und leise.",
            "Gewinde sauber, leicht gefettet, ohne Rost oder Aluminiumabrieb.",
        ),
        bad=(
            "Spiel zwischen Pedale und Kurbel oder lose Pedalachse.",
            "Raues oder schwergängiges Lager, Knarzen im Takt der Kurbel.",
            "Festgerostetes oder verschmiertes Gewinde, das sich nur mit Gewalt lösen lässt.",
        ),
        act="Gewinde fetten und mit dem Hersteller-Drehmoment festziehen. Ein beschädigtes Kurbelgewinde nicht weiterfahren, sondern in der Werkstatt prüfen lassen. Lose Pedale sofort nachziehen.",
    ),
    "fasteners": Check(
        tools="Drehmomentschlüssel mit Inbus-Bits, Montagefett, bei Carbon Carbon-Montagepaste, Lappen",
        how=(
            "Die Anzugsdrehmomente stehen meist auf dem Bauteil oder in der Anleitung des Herstellers; sie vorher nachschlagen.",
            "Schrauben nacheinander lösen (jeweils nur eine Verbindung, damit nichts verrutscht), Gewinde und Auflage reinigen.",
            "Gewinde dünn fetten (an Carbon die Montagepaste) und mit dem Drehmomentschlüssel kreuzweise festziehen.",
            "Nach einer kurzen Fahrt den Sitz von Vorbau, Lenker, Sattelstütze und Kurbel noch einmal prüfen.",
        ),
        good=(
            "Schrauben lassen sich leicht lösen, Gewinde sind sauber und leicht gefettet.",
            "Nichts knarzt, wackelt oder hat sich verstellt.",
        ),
        bad=(
            "Festgerostete oder festgefressene Schrauben, Aluminium-Abrieb am Gewinde.",
            "Knarzen von Vorbau, Sattelstütze oder Kurbel.",
            "Schraubenköpfe mit ausgeleiertem Inbus.",
        ),
        act="Gewinde fetten und mit dem Drehmomentschlüssel nach Herstellerangabe anziehen. Zu fest ist so gefährlich wie zu lose, besonders an Carbon. Beschädigte Schrauben ersetzen.",
    ),
    "pulleys": Check(
        tools="Lappen, Taschenlampe, Entfetter oder Bürste zum Reinigen",
        how=(
            "Schaltwerk und beide Röllchen reinigen, damit du die Zähne siehst.",
            "Die Zähne mit denen der Kassette vergleichen: Sie sollen ein ähnlich gleichmäßiges Profil haben.",
            "Jedes Röllchen mit den Fingern seitlich bewegen: Es soll kaum Spiel haben.",
            "Das Röllchen von Hand drehen: gleichmäßig, leichtgängig, ohne Rauheit oder Klemmen.",
            "Beim Pedalieren und Schalten auf Klicken, Rattern oder Pfeifen hören.",
        ),
        good=(
            "Zähne sind gleichmäßig, nicht spitz oder rund geschliffen.",
            "Kaum seitliches Spiel, das Röllchen dreht leicht und leise.",
            "Die Kette läuft ruhig durch den Käfig.",
        ),
        bad=(
            "Spitze, runde oder verformte Zähne.",
            "Deutliches seitliches Spiel oder Wackeln.",
            "Rauer, schwergängiger oder klemmender Lauf.",
            "Klicken, Rattern oder ungenaues Schalten, obwohl Zug und Kette in Ordnung sind.",
        ),
        act="Beide Röllchen als Paar erneuern, passend zur Gangzahl. Die Laufrichtung beachten und vor dem Einbau die Käfigschrauben mit dem Hersteller-Drehmoment anziehen. Abgenutzte Röllchen verschleißen Kette und Kassette schneller.",
    ),
    "bar_tape": Check(
        tools="Gute Beleuchtung",
        how=(
            "Das Band auf der ganzen Länge ansehen, besonders an den Bremsgriffen und in den Unterlenker-Kurven.",
            "Enden und Klebestellen prüfen: Hält das Isolierband, sind Lenkerstopfen gesetzt?",
            "Mit dem Daumen drücken: Das Polster soll noch nachgeben und nicht hart oder klebrig sein.",
            "Bei Carbon-Lenkern an freiliegenden Stellen auf Risse achten.",
        ),
        good=(
            "Das Band liegt glatt, gleichmäßig und ohne Lücken.",
            "Die Enden sind verklebt und beide Lenkerstopfen sitzen.",
            "Das Material ist griffig und dämpft.",
        ),
        bad=(
            "Durchgescheuerte oder aufgerissene Stellen, besonders an den Griffen.",
            "Lösende Wicklung, offene Enden, fehlende Stopfen.",
            "Hart, speckig oder klebrig.",
            "Risse oder Beschädigungen am Lenker unter dem Band.",
        ),
        act="Band erneuern, wenn es verschlissen ist oder sich löst. Fehlende Lenkerstopfen sofort ersetzen, ein offenes Lenkerende ist bei Stürzen gefährlich.",
    ),
    "sealant": Check(
        tools="Ventilkernwerkzeug, kleiner Messbecher oder Spritze, Lappen",
        how=(
            "Das Rad schütteln oder drehen und lauschen: Du solltest die Flüssigkeit schwappen hören.",
            "Ventil nach oben stellen, den Ventilkern herausdrehen und den Inhalt mit einem Zahnstocher oder einem Dichtmilch-Prüfstab ansehen.",
            "Bei Zweifel eine Reifenseite abdrücken und die Dichtmilch am Reifen und an der Felge ansehen.",
            "Auf Luftverlust über Nacht, Spritzer an der Flanke und nasse Stellen am Ventil achten.",
        ),
        good=(
            "Die Dichtmilch ist flüssig und milchig, mit wenig Klümpchen.",
            "Das Schwappen ist deutlich hörbar.",
            "Der Reifen verliert über Nacht nur wenig Druck.",
        ),
        bad=(
            "Kaum oder kein Schwappen: Die Milch ist eingetrocknet.",
            "Klumpen, Krümel oder eine gummiartige Haut im Reifen.",
            "Wiederholter Luftverlust, Spritzer an den Flanken.",
            "Nasse oder verklebte Ventile.",
        ),
        act="Nachfüllen, wenn die Menge abnimmt, und komplett erneuern, wenn sie verklumpt ist. Dabei Ventil, Ventilkern und Felgenband mitprüfen. Menge je Reifen nach Herstellerangabe.",
    ),
    "headset": Check(
        tools="Lappen",
        how=(
            "Vorderbremse ziehen und das Rad am Lenker mehrmals vor und zurück schieben. Lege dabei einen Finger an den Spalt zwischen Steuerrohr und oberer Kappe: Du spürst kein Klacken oder Ruckeln.",
            "Vorderrad anheben und den Lenker langsam nach links und rechts drehen. Es soll gleichmäßig, leicht und leise laufen.",
            "Auf Rasten (eine Mittelstellung, in die der Lenker fällt) und Knarzen achten.",
            "Dichtung und Kappe ansehen: Wasserspuren, Rost, Risse.",
        ),
        good=(
            "Kein Spiel, kein Klacken beim Bremsen.",
            "Der Lenker dreht sich gleichmäßig und leise.",
            "Die Dichtungen sitzen und sind trocken.",
        ),
        bad=(
            "Klacken oder Spiel beim Vor- und Zurückschieben mit gezogener Bremse.",
            "Rasten in der Mittelstellung, Rauheit oder Knirschen.",
            "Knarzen beim Lenken oder Treten im Wiegetritt.",
            "Rost oder Wasser am Steuersatz.",
        ),
        act="Bei Spiel die Vorspannung nachstellen und Vorbau anziehen. Bei Rauheit oder Rasten Lager reinigen und fetten oder erneuern. Fahre nicht mit lockerem Steuersatz.",
    ),
    "bottom_bracket": Check(
        tools="Lappen, gute Beleuchtung",
        how=(
            "Beide Kurbeln seitlich greifen und abwechselnd hin und her bewegen: Es darf kein Spiel zu spüren sein.",
            "Die Kette vom Blatt nehmen, die Kurbel kräftig anwerfen und auslaufen lassen: Sie soll lange und gleichmäßig drehen.",
            "Beim Treten auf Knacken und Knarzen hören, besonders im Antritt und am Berg.",
            "Am Gehäuse nach Wasser, Rost und Entwässerungslöchern sehen.",
        ),
        good=(
            "Kein Spiel in der Kurbel.",
            "Gleichmäßiger, leiser Lauf mit langem Auslaufen.",
            "Das Gehäuse ist sauber und trocken.",
        ),
        bad=(
            "Spürbares Spiel, die Kurbel wackelt seitlich.",
            "Rauheit, Knirschen oder Rattern beim Drehen.",
            "Knacken im Antritt, das nicht von den Pedalen kommt.",
            "Wasser, Rost oder braune Brühe am Gehäuse.",
        ),
        act="Lose Lager nach Herstellerangabe nachziehen. Bei Rauheit oder Spiel das Innenlager wechseln. Knacken zuerst bei Pedalen und Kurbelschrauben suchen, bevor das Lager getauscht wird.",
    ),
    "hubs": Check(
        tools="Lappen, ein Rad oder eine Aufhängung zum freien Drehen",
        how=(
            "Rad anheben und anwerfen: Es soll lange und gleichmäßig auslaufen.",
            "Beim Drehen die Achse zwischen zwei Fingern halten und auf Rauheit oder Rasten spüren.",
            "Das Rad am Reifen seitlich bewegen: Spiel in der Nabe fühlt sich wie ein leichtes Klacken an.",
            "Den Freilauf in Fahrtrichtung drehen und hören: Er soll gleichmäßig surren oder klicken und sicher greifen.",
            "Dichtungen an den Naben ansehen: Wasser oder Rost.",
        ),
        good=(
            "Lange, gleichmäßige Drehung und leises Laufgeräusch.",
            "Kein Spiel in der Achse.",
            "Der Freilauf greift sofort und rutscht nicht durch.",
        ),
        bad=(
            "Schleifen, Knirschen oder Rauheit beim Drehen.",
            "Rasten, die man zwischen den Fingern spürt.",
            "Seitliches Spiel in der Nabe.",
            "Freilauf rutscht durch oder klemmt, Rost oder Wasser an den Dichtungen.",
        ),
        act="Bei Spiel die Lager nachstellen, bei Rauheit reinigen, fetten oder erneuern. Rutscht der Freilauf durch, nicht mehr belasten und warten lassen.",
    ),
}
