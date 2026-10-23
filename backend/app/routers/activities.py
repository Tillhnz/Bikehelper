import json
import shutil
import tempfile

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session, defer

from ..database import get_db
from ..importers import service
from ..models import Activity, Bike, User
from ..schemas import ActivityDetail, ActivityOut, ActivityPage, ActivityUpdate, AssignIn, GearOut
from ..security import current_user
from ..weather import service as weather_service
from .garage import _own_bike

router = APIRouter(prefix="/api", tags=["activities"])

MAX_FILES_PER_UPLOAD = 500


def _out(a: Activity, has_track: bool) -> ActivityOut:
    return ActivityOut(
        id=a.id, name=a.name, sport_type=a.sport_type, start_date=a.start_date,
        distance_km=a.distance_km, moving_time_s=a.moving_time_s, elevation_m=a.elevation_m,
        bike_id=a.bike_id, gear_name=a.gear_name, source=a.source, has_track=has_track,
        temp_c=a.temp_c, precip_mm=a.precip_mm, wind_kmh=a.wind_kmh, wet_minutes=a.wet_minutes,
        weather_code=a.weather_code, weather_status=a.weather_status,
    )


def _own_activity(db: Session, user: User, activity_id: int) -> Activity:
    a = db.get(Activity, activity_id)
    if not a or a.user_id != user.id:
        raise HTTPException(404, "Fahrt nicht gefunden")
    return a


# ---------- Import ----------

@router.post("/activities/upload")
def upload_activities(
    files: list[UploadFile] = File(...),
    bike_id: int | None = Form(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """GPX-, TCX- und FIT-Dateien (auch als .gz) hochladen; optional direkt einem Rad zuordnen."""
    if len(files) > MAX_FILES_PER_UPLOAD:
        raise HTTPException(422, f"Maximal {MAX_FILES_PER_UPLOAD} Dateien pro Upload.")
    bike = _own_bike(db, user, bike_id) if bike_id is not None else None

    loaded: list[tuple[str, bytes]] = []
    too_big: list[str] = []
    for f in files:
        name = f.filename or "datei"
        data = f.file.read(service.MAX_UPLOAD_FILE_BYTES + 1)
        if len(data) > service.MAX_UPLOAD_FILE_BYTES:
            too_big.append(name)
        else:
            loaded.append((name, data))

    summary = service.import_files(db, user.id, loaded, bike)
    for name in too_big:
        summary.add_error(name, "Die Datei ist zu groß.")
    if summary.imported:
        weather_service.trigger(user.id)
    return summary.as_dict()


@router.post("/imports/strava-export", status_code=202)
def start_strava_import(
    file: UploadFile = File(...),
    create_bikes: bool = Form(default=True),
    user: User = Depends(current_user),
):
    """Strava-Export (ZIP) hochladen. Die Verarbeitung läuft im Hintergrund, der Fortschritt ist abrufbar."""
    if service.running_job(user.id):
        raise HTTPException(409, "Es läuft bereits ein Import. Bitte warte, bis er fertig ist.")
    head = file.file.read(4)
    file.file.seek(0)
    if head != b"PK\x03\x04":
        raise HTTPException(
            422, "Das ist kein ZIP-Archiv. Lade die ZIP-Datei hoch, die Strava dir per E-Mail schickt."
        )
    with tempfile.NamedTemporaryFile(delete=False, suffix=".zip") as tmp:
        shutil.copyfileobj(file.file, tmp, 1024 * 1024)
        path = tmp.name
    job = service.start_zip_import(user.id, path, create_bikes)
    return {"job_id": job.id}


@router.get("/imports/active")
def active_import(user: User = Depends(current_user)):
    """Läuft gerade ein Import? Damit die Oberfläche nach einem Neuladen den Fortschritt wieder anzeigen kann."""
    job = service.running_job(user.id)
    return {"job": job.as_dict() if job else None}


@router.get("/imports/{job_id}")
def import_status(job_id: str, user: User = Depends(current_user)):
    job = service.get_job(job_id, user.id)
    if not job:
        raise HTTPException(404, "Import nicht gefunden (nach einem Neustart des Servers gehen laufende Importe verloren)")
    return job.as_dict()


# ---------- Fahrten ansehen und zuordnen ----------

@router.get("/activities", response_model=ActivityPage)
def list_activities(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    unassigned: bool = False,
    bike_id: int | None = None,
    q: str | None = None,
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    cond = [Activity.user_id == user.id]
    if unassigned:
        cond.append(Activity.bike_id.is_(None))
    if bike_id is not None:
        cond.append(Activity.bike_id == bike_id)
    if q:
        cond.append(Activity.name.ilike(f"%{q.strip()}%"))
    total = db.scalar(select(func.count()).select_from(Activity).where(*cond)) or 0
    rows = db.execute(
        select(Activity, Activity.polyline.is_not(None).label("has_track"))
        .options(defer(Activity.polyline))
        .where(*cond)
        .order_by(Activity.start_date.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return ActivityPage(total=total, items=[_out(a, bool(t)) for a, t in rows])


@router.get("/activities/gear", response_model=list[GearOut])
def list_gear(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Fahrten gruppiert nach dem Radnamen aus dem Strava-Export."""
    rows = db.execute(
        select(Activity.gear_name, Activity.bike_id, Activity.distance_km).where(Activity.user_id == user.id)
    ).all()
    agg: dict[str | None, list] = {}
    for gear, bike_id, km in rows:
        e = agg.setdefault(gear, [0, 0, 0.0])
        e[0] += 1
        e[1] += 1 if bike_id is None else 0
        e[2] += km or 0.0
    out = [GearOut(gear_name=g, count=c, unassigned=u, km=round(km, 1)) for g, (c, u, km) in agg.items()]
    return sorted(out, key=lambda g: g.count, reverse=True)


@router.post("/activities/assign")
def assign_activities(data: AssignIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Ordnet mehrere Fahrten auf einmal einem Rad zu (nach Radname aus dem Export oder nach Auswahl)."""
    if data.bike_id is not None:
        _own_bike(db, user, data.bike_id)
    stmt = update(Activity).where(Activity.user_id == user.id)
    if data.activity_ids is not None:
        stmt = stmt.where(Activity.id.in_(data.activity_ids))
    elif data.gear_name is not None:
        stmt = stmt.where(Activity.gear_name == data.gear_name)
    else:
        raise HTTPException(422, "Bitte activity_ids oder gear_name angeben.")
    if data.only_unassigned:
        stmt = stmt.where(Activity.bike_id.is_(None))
    result = db.execute(stmt.values(bike_id=data.bike_id))
    db.commit()
    return {"updated": result.rowcount}


@router.put("/activities/{activity_id}", response_model=ActivityOut)
def update_activity(
    activity_id: int, data: ActivityUpdate, user: User = Depends(current_user), db: Session = Depends(get_db),
):
    a = _own_activity(db, user, activity_id)
    if "bike_id" in data.model_fields_set:
        if data.bike_id is not None:
            _own_bike(db, user, data.bike_id)
        a.bike_id = data.bike_id
    if data.name:
        a.name = data.name
    db.commit()
    return _out(a, bool(a.polyline))


@router.delete("/activities/{activity_id}", status_code=204)
def delete_activity(activity_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    db.delete(_own_activity(db, user, activity_id))
    db.commit()


@router.delete("/activities")
def delete_all_activities(
    confirm: bool = Query(default=False),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Löscht alle Fahrten des Nutzers (Räder, Komponenten und Wartungen bleiben erhalten)."""
    if not confirm:
        raise HTTPException(422, "Zum Löschen aller Fahrten muss confirm=true angegeben werden.")
    result = db.execute(delete(Activity).where(Activity.user_id == user.id))
    db.commit()
    return {"deleted": result.rowcount}


@router.get("/activities/{activity_id}", response_model=ActivityDetail)
def activity_detail(activity_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Einzelauswertung einer Fahrt mit Strecke und Verlaufsdaten."""
    a = _own_activity(db, user, activity_id)
    base = _out(a, bool(a.polyline)).model_dump()
    try:
        details = json.loads(a.details) if a.details else None
    except ValueError:
        details = None
    return ActivityDetail(
        **base,
        bike_name=(db.get(Bike, a.bike_id).name if a.bike_id and db.get(Bike, a.bike_id) else None),
        polyline=a.polyline,
        avg_speed=round(a.distance_km / a.moving_time_s * 3600, 1) if a.moving_time_s else None,
        details=details,
        start_lat=a.start_lat,
        start_lng=a.start_lng,
    )
