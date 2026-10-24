"""Reifenkatalog: mitgelieferte Liste (data/tires.csv) plus eigene Einträge des Nutzers (CSV-Import).

Die mitgelieferte Liste enthält nur Herstellerangaben mit Quelle (Breite, Gewicht, Einsatzbereich). Rollwiderstandswerte
(Watt) sind optional und stammen aus den Quellen, die in `source_url` stehen, oder aus dem eigenen Import des Nutzers.
Spalten: brand, model, category, width_mm, tubeless, weight_g, watts, watts_note, source_url, casing
"""
from __future__ import annotations

import csv
import io
import re
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

CATEGORIES = ("road", "gravel", "mtb", "trekking", "city", "tt", "other")
TUBELESS = ("tubeless", "clincher", "tubular", "both")
CASINGS = ("supple", "standard", "stiff")
CATEGORY_LABEL = {
    "road": "Rennrad", "gravel": "Gravel/CX", "mtb": "Mountainbike", "trekking": "Trekking",
    "city": "Stadt/Alltag", "tt": "Zeitfahren/Triathlon", "other": "Sonstige",
}
MAX_IMPORT_BYTES = 2 * 1024 * 1024
MAX_IMPORT_ROWS = 5000
DATA_FILE = Path(__file__).parent / "data" / "tires.csv"
REQUIRED = ("brand", "model")


@dataclass
class TireEntry:
    key: str
    brand: str
    model: str
    category: str = "road"
    width_mm: float | None = None
    tubeless: str | None = None
    weight_g: float | None = None
    watts: float | None = None
    watts_note: str | None = None
    source_url: str | None = None
    casing: str | None = None
    own: bool = False

    @property
    def label(self) -> str:
        w = f" {self.width_mm:g}" if self.width_mm else ""
        return f"{self.brand} {self.model}{w}".strip()

    def to_dict(self) -> dict:
        d = asdict(self)
        d["label"] = self.label
        return d


def slug(*parts) -> str:
    return re.sub(r"[^a-z0-9]+", "-", " ".join(str(p) for p in parts if p not in (None, "")).lower()).strip("-")


def _num(v, lo: float, hi: float) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    try:
        x = float(str(v).strip().replace(",", "."))
    except ValueError:
        raise ValueError(f"„{v}“ ist keine Zahl")
    if not lo <= x <= hi:
        raise ValueError(f"{x:g} liegt außerhalb von {lo:g} bis {hi:g}")
    return x


def _url(v) -> str | None:
    v = (v or "").strip()
    if not v:
        return None
    if not re.match(r"^https?://", v, re.I) or len(v) > 255:
        raise ValueError("Quelle muss eine http(s)-Adresse sein")
    return v


def parse_row(row: dict, key_prefix: str, own: bool) -> TireEntry:
    row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
    brand, model = row.get("brand", ""), row.get("model", "")
    if not brand or not model:
        raise ValueError("Marke und Modell sind Pflicht")
    category = row.get("category", "").lower() or "road"
    if category not in CATEGORIES:
        raise ValueError(f"Kategorie „{category}“ unbekannt (erlaubt: {', '.join(CATEGORIES)})")
    tubeless = row.get("tubeless", "").lower() or None
    if tubeless and tubeless not in TUBELESS:
        raise ValueError(f"tubeless „{tubeless}“ unbekannt (erlaubt: {', '.join(TUBELESS)})")
    casing = row.get("casing", "").lower() or None
    if casing and casing not in CASINGS:
        raise ValueError(f"casing „{casing}“ unbekannt (erlaubt: {', '.join(CASINGS)})")
    width = _num(row.get("width_mm"), 18, 85)
    return TireEntry(
        key=f"{key_prefix}{slug(brand, model, f'{width:g}' if width else None)}", brand=brand[:120], model=model[:160], category=category,
        width_mm=width, tubeless=tubeless, weight_g=_num(row.get("weight_g"), 50, 3000),
        watts=_num(row.get("watts"), 0.5, 100), watts_note=(row.get("watts_note") or None) and row["watts_note"][:200],
        source_url=_url(row.get("source_url")), casing=casing, own=own,
    )


def parse_csv(text: str, key_prefix: str, own: bool) -> tuple[list[TireEntry], list[str]]:
    """Liest CSV-Text (Komma oder Semikolon). Gibt Einträge und Fehlermeldungen je Zeile zurück."""
    if len(text.encode("utf-8", "ignore")) > MAX_IMPORT_BYTES:
        raise ValueError("Die Datei ist zu groß (höchstens 2 MB).")
    text = text.lstrip("﻿")
    first = text.splitlines()[0] if text.strip() else ""
    delimiter = ";" if first.count(";") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    if not reader.fieldnames or not all(c in [f.strip().lower() for f in reader.fieldnames] for c in REQUIRED):
        raise ValueError("Die erste Zeile muss die Spalten brand und model enthalten.")
    entries, errors, seen = [], [], set()
    for n, row in enumerate(reader, start=2):
        if n - 1 > MAX_IMPORT_ROWS:
            errors.append(f"Mehr als {MAX_IMPORT_ROWS} Zeilen: der Rest wurde ignoriert")
            break
        if not any((v or "").strip() for v in row.values() if isinstance(v, str)):
            continue
        try:
            e = parse_row(row, key_prefix, own)
        except ValueError as err:
            errors.append(f"Zeile {n}: {err}")
            continue
        if e.key in seen:
            errors.append(f"Zeile {n}: {e.label} kommt doppelt vor")
            continue
        seen.add(e.key)
        entries.append(e)
    return entries, errors


@lru_cache(maxsize=1)
def bundled() -> tuple[TireEntry, ...]:
    if not DATA_FILE.exists():
        return ()
    entries, _ = parse_csv(DATA_FILE.read_text(encoding="utf-8"), "c:", False)
    return tuple(entries)


def search(entries: list[TireEntry], q: str = "", category: str | None = None, limit: int = 20) -> list[TireEntry]:
    """Alle Suchbegriffe müssen vorkommen (Marke, Modell, Breite). Treffer am Anfang der Marke zuerst."""
    words = [w for w in re.split(r"\s+", q.lower().strip()) if w]
    out = []
    for e in entries:
        if category and e.category != category:
            continue
        hay = e.label.lower()
        if all(w in hay for w in words):
            out.append(e)
    out.sort(key=lambda e: (not (words and e.label.lower().startswith(words[0])), e.brand.lower(), e.model.lower(), e.width_mm or 0))
    return out[:limit]
