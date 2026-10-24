"""Datenbank-Ebene des Imports: Dateien speichern, Duplikate erkennen, Räder zuordnen."""
from __future__ import annotations

import os
import threading
import time
import uuid
import zipfile
import json
from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..models import Activity, Bike
from ..services import create_default_components
from .parsers import ParsedActivity, ParseError, is_cycling, parse_activity_file
from .strava_export import ExportEntry, clean_gear_name, gear_key, index_export

MAX_UPLOAD_FILE_BYTES = 50 * 1024 * 1024  # eine einzelne Fahrtdatei (typisch unter 10 MB)
MAX_ARCHIVE_TOTAL_BYTES = 40 * 1024**3  # entpackte Gesamtgröße eines Strava-Exports
MAX_ARCHIVE_ENTRIES = 200_000
COMMIT_EVERY = 100


@dataclass
class Summary:
    imported: int = 0
    duplicates: int = 0
    skipped_other_sport: int = 0
    skipped_no_file: int = 0
    assigned: int = 0
    updated: int = 0
    notes: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)
    created_bikes: list[str] = field(default_factory=list)
    unmatched_gear: dict[str, int] = field(default_factory=dict)

    def add_error(self, file: str, message: str) -> None:
        if len(self.errors) < 50:  # die Liste klein halten
            self.errors.append({"file": file, "message": message})

    def as_dict(self) -> dict:
        return {
            "imported": self.imported,
            "duplicates": self.duplicates,
            "skipped_other_sport": self.skipped_other_sport,
            "skipped_no_file": self.skipped_no_file,
            "assigned": self.assigned,
            "updated": self.updated,
            "notes": self.notes,
            "errors": self.errors,
            "created_bikes": self.created_bikes,
            "unmatched_gear": self.unmatched_gear,
        }


# ---------- Speichern einer einzelnen Fahrt ----------

def find_duplicate(db: Session, user_id: int, parsed: ParsedActivity, strava_id: int | None) -> Activity | None:
    if strava_id is not None:
        found = db.scalar(select(Activity).where(Activity.user_id == user_id, Activity.strava_id == strava_id))
        if found:
            return found
    lo, hi = parsed.start - timedelta(seconds=90), parsed.start + timedelta(seconds=90)
    candidates = db.scalars(
        select(Activity).where(Activity.user_id == user_id, Activity.start_date.between(lo, hi))
    )
    tolerance = max(0.3, 0.03 * parsed.distance_km)
    return next((a for a in candidates if abs(a.distance_km - parsed.distance_km) <= tolerance), None)


def is_duplicate(db: Session, user_id: int, parsed: ParsedActivity, strava_id: int | None) -> bool:
    return find_duplicate(db, user_id, parsed, strava_id) is not None


def backfill_existing(
    existing: Activity, strava_id: int | None, gear_name: str | None, bike: Bike | None,
    details: dict | None = None,
) -> bool:
    """Ergänzt bei einer schon vorhandenen Fahrt fehlende Angaben (Strava-ID, Radname, Rad).

    Bereits gesetzte Werte bleiben unberührt, damit manuelle Zuordnungen nicht überschrieben werden.
    """
    changed = False
    if gear_name and not existing.gear_name:
        existing.gear_name = gear_name[:160]
        changed = True
    if strava_id is not None and existing.strava_id is None:
        existing.strava_id = strava_id
        changed = True
    if bike is not None and existing.bike_id is None:
        existing.bike_id = bike.id
        changed = True
    if details and not existing.details:
        existing.details = json.dumps(details, separators=(",", ":"))
        changed = True
    return changed


def store_activity(
    db: Session,
    user_id: int,
    parsed: ParsedActivity,
    *,
    name: str | None,
    strava_id: int | None,
    gear_name: str | None,
    bike: Bike | None,
    sport_type: str | None,
    source: str,
    check_duplicate: bool = True,
) -> bool:
    """Legt die Fahrt an. Gibt False zurück, wenn sie schon vorhanden ist."""
    if check_duplicate and is_duplicate(db, user_id, parsed, strava_id):
        return False
    label = name or parsed.name or f"Fahrt vom {parsed.start:%d.%m.%Y}"
    activity = Activity(
        user_id=user_id,
        bike_id=bike.id if bike else None,
        strava_id=strava_id,
        name=label[:255],
        sport_type=(sport_type or ("Ride" if is_cycling(parsed.sport) else (parsed.sport or "Ride").title()))[:40],
        start_date=parsed.start,
        distance_km=parsed.distance_km,
        moving_time_s=parsed.moving_time_s,
        elevation_m=parsed.elevation_m,
        polyline=parsed.polyline,
        details=json.dumps(parsed.details, separators=(",", ":")) if parsed.details else None,
        start_lat=parsed.start_lat,
        start_lng=parsed.start_lng,
        gear_name=gear_name[:160] if gear_name else None,
        source=source,
    )
    try:
        with db.begin_nested():
            db.add(activity)
            db.flush()
    except IntegrityError:
        return False
    return True


# ---------- Direkter Upload einzelner Dateien ----------

def import_files(db: Session, user_id: int, files: list[tuple[str, bytes]], bike: Bike | None) -> Summary:
    summary = Summary()
    for filename, data in files:
        try:
            parsed = parse_activity_file(filename, data)
        except ParseError as e:
            summary.add_error(filename, str(e))
            continue
        if not is_cycling(parsed.sport):
            summary.skipped_other_sport += 1
            continue
        if store_activity(
            db, user_id, parsed, name=None, strava_id=None, gear_name=None, bike=bike,
            sport_type=None, source="upload",
        ):
            summary.imported += 1
            if bike:
                summary.assigned += 1
        else:
            summary.duplicates += 1
    db.commit()
    return summary


# ---------- Strava-Export (läuft im Hintergrund) ----------

@dataclass
class Job:
    id: str
    user_id: int
    status: str = "running"  # running | done | error
    total: int = 0
    processed: int = 0
    summary: Summary = field(default_factory=Summary)
    error: str | None = None
    finished_at: float | None = None

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "total": self.total,
            "processed": self.processed,
            "error": self.error,
            "summary": self.summary.as_dict(),
        }


_jobs: dict[str, Job] = {}
_lock = threading.Lock()


def _prune_jobs() -> None:
    cutoff = time.time() - 3600
    for jid in [j.id for j in _jobs.values() if j.finished_at and j.finished_at < cutoff]:
        _jobs.pop(jid, None)


def get_job(job_id: str, user_id: int) -> Job | None:
    with _lock:
        job = _jobs.get(job_id)
    return job if job and job.user_id == user_id else None


def running_job(user_id: int) -> Job | None:
    with _lock:
        return next((j for j in _jobs.values() if j.user_id == user_id and j.status == "running"), None)


def start_zip_import(user_id: int, zip_path: str, create_bikes: bool) -> Job:
    job = Job(id=uuid.uuid4().hex, user_id=user_id)
    with _lock:
        _prune_jobs()
        _jobs[job.id] = job
    threading.Thread(target=_run_zip_import, args=(job, zip_path, create_bikes), daemon=True).start()
    return job


def _resolve_bike(
    db: Session, user_id: int, entry: ExportEntry, bikes: dict[str, Bike], index_bikes: dict,
    create_bikes: bool, summary: Summary,
) -> Bike | None:
    gear = clean_gear_name(entry.gear)
    if not gear:
        return None
    key = gear_key(gear)
    bike = bikes.get(key)
    if bike is None and create_bikes:
        name, brand, model = index_bikes.get(key, (gear, None, None))
        bike = Bike(user_id=user_id, name=name[:120], type=_guess_bike_type(entry.type), brand=brand, model=model)
        db.add(bike)
        db.flush()
        create_default_components(db, user_id, bike)
        bikes[key] = bike
        summary.created_bikes.append(bike.name)
    if bike is None:
        summary.unmatched_gear[gear] = summary.unmatched_gear.get(gear, 0) + 1
    return bike


def _guess_bike_type(strava_type: str | None) -> str:
    t = (strava_type or "").lower()
    if "gravel" in t:
        return "gravel"
    if "mountain" in t:
        return "mtb"
    return "road"


def _run_zip_import(job: Job, zip_path: str, create_bikes: bool) -> None:
    summary = job.summary
    try:
        with SessionLocal() as db, zipfile.ZipFile(zip_path) as zf:
            if len(zf.infolist()) > MAX_ARCHIVE_ENTRIES:
                raise ParseError("Das Archiv enthält zu viele Dateien.")
            if sum(i.file_size for i in zf.infolist()) > MAX_ARCHIVE_TOTAL_BYTES:
                raise ParseError("Das Archiv ist entpackt zu groß.")
            index = index_export(zf)
            if not index.entries:
                raise ParseError(
                    "Im Archiv wurden keine Aktivitätsdateien gefunden. Erwartet wird der Ordner activities/ "
                    "mit .fit-, .gpx- oder .tcx-Dateien."
                )
            summary.skipped_no_file = index.rows_without_file
            if not index.used_csv:
                summary.notes.append(
                    "Die Datei activities.csv konnte nicht gelesen werden. Es wurden nur die Dateien im Ordner "
                    "activities/ importiert, ohne Zuordnung zu Rädern."
                )
            elif not index.gear_column:
                summary.notes.append(
                    "In activities.csv wurde keine Spalte mit dem Rad gefunden. Die Fahrten wurden ohne Radzuordnung importiert."
                )
            job.total = len(index.entries)
            bikes = {gear_key(b.name): b for b in db.scalars(select(Bike).where(Bike.user_id == job.user_id))}

            for entry in index.entries:
                job.processed += 1
                if entry.type and not is_cycling(entry.type):
                    summary.skipped_other_sport += 1
                    continue
                try:
                    if zf.getinfo(entry.path).file_size > MAX_UPLOAD_FILE_BYTES:
                        raise ParseError("Die Datei ist zu groß.")
                    parsed = parse_activity_file(entry.path, zf.read(entry.path))
                except ParseError as e:
                    summary.add_error(entry.path, str(e))
                    continue
                except Exception as e:  # einzelne kaputte Datei darf den Import nicht stoppen
                    summary.add_error(entry.path, f"Unerwarteter Fehler: {e}")
                    continue
                if not entry.type and not is_cycling(parsed.sport):
                    summary.skipped_other_sport += 1
                    continue

                existing = find_duplicate(db, job.user_id, parsed, entry.strava_id)
                if existing is not None:
                    # Schon vorhanden: nur fehlendes Rad und Radname nachtragen
                    bike = None
                    if existing.bike_id is None:
                        bike = _resolve_bike(db, job.user_id, entry, bikes, index.bikes, create_bikes, summary)
                    if backfill_existing(existing, entry.strava_id, entry.gear, bike, parsed.details):
                        summary.updated += 1
                        if bike is not None:
                            summary.assigned += 1
                    summary.duplicates += 1
                else:
                    bike = _resolve_bike(db, job.user_id, entry, bikes, index.bikes, create_bikes, summary)
                    stored = store_activity(
                        db, job.user_id, parsed, name=entry.name, strava_id=entry.strava_id,
                        gear_name=entry.gear, bike=bike, sport_type=entry.type, source="strava_export",
                        check_duplicate=False,
                    )
                    if stored:
                        summary.imported += 1
                        if bike:
                            summary.assigned += 1
                    else:
                        summary.duplicates += 1
                if job.processed % COMMIT_EVERY == 0:
                    db.commit()
            db.commit()
        job.status = "done"
    except zipfile.BadZipFile:
        job.status, job.error = "error", "Die Datei ist kein gültiges ZIP-Archiv."
    except ParseError as e:
        job.status, job.error = "error", str(e)
    except Exception as e:
        job.status, job.error = "error", f"Der Import ist fehlgeschlagen: {e}"
    finally:
        job.finished_at = time.time()
        try:
            os.unlink(zip_path)
        except OSError:
            pass
        if job.status == "done":
            from ..weather import service as weather_service

            weather_service.trigger(job.user_id)
