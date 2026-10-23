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

_COLUMNS = {
    "id": ("activity id",),
    "name": ("activity name",),
    "type": ("activity type",),
    "gear": ("activity gear",),
    "filename": ("filename",),
}


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


def read_activities_csv(text: str, zip_names: set[str]) -> tuple[list[ExportEntry], int] | None:
    """Gibt (Einträge, Zeilen ohne Datei) zurück oder None, wenn die CSV nicht lesbar ist."""
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return None
    header = rows[0]
    idx = {k: _find_index(header, v) for k, v in _COLUMNS.items()}
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
    return entries, without_file


def read_bikes_csv(text: str) -> dict[str, tuple[str, str | None, str | None]]:
    rows = list(csv.reader(io.StringIO(text)))
    if len(rows) < 2:
        return {}
    header = rows[0]
    i_name = _find_index(header, ("bike name",))
    i_brand = _find_index(header, ("bike brand",))
    i_model = _find_index(header, ("bike model",))
    if i_name is None:
        return {}
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
        parsed = read_activities_csv(_decode(zf.read(csv_member)), activity_names)
    if parsed is not None:
        entries, without_file = parsed
        return ExportIndex(entries, without_file, True, bikes)

    # Rückfall: alle Aktivitätsdateien im Ordner activities/ lesen, ohne Zusatzinfos
    entries = [
        ExportEntry(path=n, strava_id=_id_from_filename(n))
        for n in sorted(names)
        if _is_supported(n) and "activities/" in n.lower()
    ]
    return ExportIndex(entries, 0, False, bikes)
