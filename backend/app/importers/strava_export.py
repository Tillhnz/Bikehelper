"""Lesen des Strava-Datenexports (ZIP mit activities.csv, activities/ und bikes.csv).

Die Spaltennamen der CSV hängen von der Sprache des Strava-Kontos ab. Dieses Modul kommt deshalb
mit dem Nötigsten aus (ID, Name, Typ, Ausrüstung, Dateiname) und fällt bei unbekannten Spalten darauf
zurück, einfach alle Dateien im Ordner activities/ zu lesen. Alle Kennzahlen stammen aus den
Aktivitätsdateien selbst, nicht aus der CSV.
"""
from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass

SUPPORTED_SUFFIXES = (".fit", ".gpx", ".tcx", ".fit.gz", ".gpx.gz", ".tcx.gz")

# Bekannte Spaltennamen (Englisch, Deutsch, Französisch, Spanisch). Was hier nicht steht, wird über den
# Inhalt der Spalte erkannt (siehe _detect_columns), damit der Import nicht von der Kontosprache abhängt.
_COLUMNS = {
    "id": ("activity id", "aktivitäts-id", "aktivitäts id", "aktivitaets-id", "id de l'activité", "id de la actividad"),
    "name": ("activity name", "aktivitätsname", "name der aktivität", "nom de l'activité", "nombre de la actividad"),
    "type": ("activity type", "aktivitätsart", "aktivitätstyp", "art der aktivität", "type d'activité", "tipo de actividad"),
    "gear": (
        "activity gear", "ausrüstung der aktivität", "aktivitätsausrüstung", "ausrüstung", "equipement de l'activité",
        "équipement de l'activité", "matériel de l'activité", "equipo de la actividad", "equipo",
    ),
    "filename": ("filename", "dateiname", "nom du fichier", "nombre del archivo", "nome file"),
}
_GEAR_WORDS = ("gear", "ausrüst", "ausruest", "equip", "matériel", "materiel", "material", "bike", "fahrrad", "vélo", "velo")


def _looks_like_file(value: str) -> bool:
    v = value.strip().lower()
    return bool(v) and (v.endswith(SUPPORTED_SUFFIXES) or v.startswith("activities/"))


def _detect_columns(header: list[str], rows: list[list[str]], bike_keys: frozenset[str]) -> dict[str, int | None]:
    """Findet die Spalten zuerst über bekannte Namen, dann über ihren Inhalt."""
    idx = {k: _find_index(header, v) for k, v in _COLUMNS.items()}
    used = {v for v in idx.values() if v is not None}
    sample = rows[:2000]

    def column(i: int) -> list[str]:
        return [r[i].strip() for r in sample if i < len(r) and r[i].strip()]

    if idx["filename"] is None:  # Spalte, in der fast nur Pfade zu Aktivitätsdateien stehen
        best, best_n = None, 0
        for i in range(len(header)):
            if i in used:
                continue
            n = sum(1 for v in column(i) if _looks_like_file(v))
            if n > best_n:
                best, best_n = i, n
        idx["filename"] = best
        if best is not None:
            used.add(best)

    if idx["id"] is None:  # erste Spalte aus reinen Zahlen
        for i in range(len(header)):
            vals = column(i)
            if i not in used and vals and all(v.isdigit() for v in vals) and min(len(v) for v in vals) >= 6:
                idx["id"] = i
                used.add(i)
                break

    if idx["gear"] is None:
        best, best_score = None, 0.0
        for i, h in enumerate(header):
            if i in used:
                continue
            vals = column(i)
            if not vals:
                continue
            hit = sum(1 for v in vals if gear_key(v) in bike_keys) / len(vals) if bike_keys else 0.0
            score = hit + (0.5 if any(w in h.casefold() for w in _GEAR_WORDS) else 0.0)
            if score > best_score:
                best, best_score = i, score
        idx["gear"] = best if best_score >= 0.5 else None
        if idx["gear"] is not None:
            used.add(idx["gear"])

    for key, words in (("name", ("name", "nom", "nombre", "titel")), ("type", ("type", "typ", "art", "tipo"))):
        if idx[key] is None:
            for i, h in enumerate(header):
                tokens = h.casefold().replace("-", " ").split()
                if i not in used and any(w in tokens for w in words):
                    idx[key] = i
                    used.add(i)
                    break
    return idx


@dataclass
class ExportEntry:
    path: str                 # Pfad der Datei im ZIP
    strava_id: int | None
    name: str | None = None
    type: str | None = None
    gear: str | None = None


@dataclass
class ExportIndex:
    entries: list[ExportEntry]
    rows_without_file: int    # Aktivitäten ohne GPS-Datei (z. B. manuell eingetragen)
    used_csv: bool
    bikes: dict[str, tuple[str, str | None, str | None]]  # gear_key -> (Name, Marke, Modell)
    gear_column: bool = False  # wurde in der CSV eine Spalte mit dem Rad gefunden?


def clean_gear_name(value: str | None) -> str:
    s = (value or "").strip()
    # Manche Exporte kodieren Leerzeichen in Namen als "+".
    if "+" in s and " " not in s:
        s = s.replace("+", " ")
    return s.strip()


def gear_key(value: str | None) -> str:
    return clean_gear_name(value).casefold()


def _decode(raw: bytes) -> str:
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1")


def _id_from_filename(path: str) -> int | None:
    m = re.match(r"^(\d+)\.", path.rsplit("/", 1)[-1])
    return int(m.group(1)) if m else None


def _is_supported(path: str) -> bool:
    return path.lower().endswith(SUPPORTED_SUFFIXES)


def _find_index(names: list[str], wanted: tuple[str, ...]) -> int | None:
    for i, n in enumerate(names):
        if n.strip().casefold() in wanted:
            return i
    return None


def read_activities_csv(
    text: str, zip_names: set[str], bike_keys: frozenset[str] = frozenset()
) -> tuple[list[ExportEntry], int, bool] | None:
    """Gibt (Einträge, Zeilen ohne Datei, Radspalte gefunden) zurück oder None, wenn die CSV nicht lesbar ist."""
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return None
    header = rows[0]
    idx = _detect_columns(header, rows[1:], bike_keys)
    if idx["filename"] is None:
        return None

    by_basename = {n.rsplit("/", 1)[-1]: n for n in zip_names}

    def cell(row: list[str], key: str) -> str | None:
        i = idx[key]
        return row[i].strip() if i is not None and i < len(row) and row[i].strip() else None

    entries: list[ExportEntry] = []
    without_file = 0
    for row in rows[1:]:
        if not row or not any(c.strip() for c in row):
            continue
        filename = cell(row, "filename")
        if not filename:
            without_file += 1
            continue
        path = filename if filename in zip_names else by_basename.get(filename.rsplit("/", 1)[-1])
        if path is None or not _is_supported(path):
            without_file += 1
            continue
        raw_id = cell(row, "id")
        sid = int(raw_id) if raw_id and raw_id.isdigit() else _id_from_filename(path)
        entries.append(ExportEntry(
            path=path, strava_id=sid, name=cell(row, "name"), type=cell(row, "type"),
            gear=clean_gear_name(cell(row, "gear")) or None,
        ))
    return entries, without_file, idx["gear"] is not None


def read_bikes_csv(text: str) -> dict[str, tuple[str, str | None, str | None]]:
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return {}
    header = rows[0]
    def find(words: tuple[str, ...]) -> int | None:
        for i, h in enumerate(header):
            if any(w in h.casefold() for w in words):
                return i
        return None

    i_name = find(("name", "nom", "nombre"))
    i_brand = find(("brand", "marke", "marque", "marca"))
    i_model = find(("model", "modell", "modèle", "modelo"))
    if i_name is None:
        i_name = 0  # in bikes.csv steht der Name in der ersten Spalte
    out = {}
    for row in rows[1:]:
        if i_name >= len(row) or not row[i_name].strip():
            continue
        name = clean_gear_name(row[i_name])
        brand = clean_gear_name(row[i_brand]) if i_brand is not None and i_brand < len(row) else ""
        model = clean_gear_name(row[i_model]) if i_model is not None and i_model < len(row) else ""
        out[gear_key(name)] = (name, brand or None, model or None)
    return out


def _find_member(names: set[str], filename: str) -> str | None:
    for n in names:
        if n.lower() == filename or n.lower().endswith("/" + filename):
            return n
    return None


def index_export(zf: zipfile.ZipFile) -> ExportIndex:
    names = {i.filename for i in zf.infolist() if not i.is_dir()}

    bikes: dict[str, tuple[str, str | None, str | None]] = {}
    bikes_member = _find_member(names, "bikes.csv")
    if bikes_member:
        bikes = read_bikes_csv(_decode(zf.read(bikes_member)))

    parsed = None
    csv_member = _find_member(names, "activities.csv")
    if csv_member:
        activity_names = {n for n in names if _is_supported(n)}
        parsed = read_activities_csv(_decode(zf.read(csv_member)), activity_names, frozenset(bikes))
    if parsed is not None:
        entries, without_file, has_gear = parsed
        return ExportIndex(entries, without_file, True, bikes, has_gear)

    # Rückfall: alle Aktivitätsdateien im Ordner activities/ lesen, ohne Zusatzinfos
    entries = [
        ExportEntry(path=n, strava_id=_id_from_filename(n))
        for n in sorted(names)
        if _is_supported(n) and "activities/" in n.lower()
    ]
    return ExportIndex(entries, 0, False, bikes)
