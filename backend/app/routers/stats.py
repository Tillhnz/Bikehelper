from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..importers import polyline
from ..models import Activity, Bike, Goal, User
from ..security import current_user
from ..stats import tiles as T
from ..stats import extra as X
from ..stats.overview import Row, build_overview, get_tz, local

router = APIRouter(prefix="/api", tags=["stats"])


def _ensure_tiles(db: Session, user_id: int) -> None:
    """Berechnet Kacheln für Fahrten, bei denen sie noch fehlen (einmalig je Fahrt)."""
    todo = db.scalars(select(Activity).where(Activity.user_id == user_id, Activity.tiles.is_(None))).all()
    for i, a in enumerate(todo, 1):
        try:
            pts = polyline.decode(a.polyline) if a.polyline else []
        except Exception:
            pts = []
        a.tiles = T.encode(T.tiles_for_points(pts))
        if i % 200 == 0:
            db.commit()
    if todo:
        db.commit()


def _load(db: Session, user: User, bike_id: int | None, year: int | None, with_tiles: bool = True):
    _ensure_tiles(db, user.id)
    tz = get_tz(settings.timezone)
    q = select(Activity).where(Activity.user_id == user.id)
    if bike_id is not None:
        q = q.where(Activity.bike_id == bike_id)
    rows = []
    for a in db.scalars(q):
        if year is not None and local(a.start_date, tz).year != year:
            continue
        rows.append((a, Row(
            id=a.id, name=a.name, bike_id=a.bike_id, start=a.start_date, km=a.distance_km,
            time_s=a.moving_time_s, elev_m=a.elevation_m, temp_c=a.temp_c, precip_mm=a.precip_mm,
            wet_minutes=a.wet_minutes, weather_status=a.weather_status,
            tiles=T.decode(a.tiles) if with_tiles else None,
        )))
    return tz, rows


@router.get("/stats/overview")
def stats_overview(
    bike_id: int | None = Query(default=None),
    year: int | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    tz, rows = _load(db, user, bike_id, year)
    names = {b.id: b.name for b in db.scalars(select(Bike).where(Bike.user_id == user.id))}
    today = local(datetime.now(timezone.utc).replace(tzinfo=None), tz).date()
    data = build_overview([r for _, r in rows], tz, today, names)
    data["bikes_available"] = [{"id": k, "name": v} for k, v in names.items()]
    data["years_available"] = sorted({local(a.start_date, tz).year for a, _ in rows}) if year is None else None
    return data


@router.get("/stats/heatmap")
def heatmap(
    bike_id: int | None = Query(default=None),
    year: int | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Alle Strecken (vereinfachte Polylines) plus erkundete Kacheln für die Karte."""
    _, rows = _load(db, user, bike_id, year)
    tiles: set = set()
    lines = []
    for a, r in rows:
        if a.polyline:
            lines.append(a.polyline)
        tiles |= r.tiles or set()
    size, at = T.max_square(tiles)
    square = None
    if at:
        s, w, _, _ = T.tile_bounds(at[0] + size - 1, at[1] + size - 1)
        _, _, n, e = T.tile_bounds(at[0], at[1])
        square = {"size": size, "bounds": [[s, w], [n, e]]}
    return {"lines": lines, "tiles": [list(t) for t in sorted(tiles)], "zoom": T.ZOOM, "max_square": square}


def _today(tz):
    return local(datetime.now(timezone.utc).replace(tzinfo=None), tz).date()


def _bike_names(db: Session, user: User) -> dict[int, str]:
    return {b.id: b.name for b in db.scalars(select(Bike).where(Bike.user_id == user.id))}


@router.get("/stats/extra")
def stats_extra(
    bike_id: int | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Belastung, Vergleiche, Meilensteine und weitere Auswertungen über alle Jahre."""
    tz, rows = _load(db, user, bike_id, None, with_tiles=False)
    return X.build_extra([r for _, r in rows], tz, _today(tz), _bike_names(db, user))


@router.get("/stats/review")
def stats_review(
    year: int = Query(),
    bike_id: int | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    tz, rows = _load(db, user, bike_id, None)
    data = X.build_review([r for _, r in rows], tz, year, _today(tz), _bike_names(db, user))
    data["years_available"] = sorted({local(a.start_date, tz).year for a, _ in rows})
    return data


class GoalsIn(BaseModel):
    year: int
    targets: dict[str, float | None]  # Metrik -> Zielwert; None oder 0 löscht das Ziel


def _goal_targets(db: Session, user: User, year: int) -> dict[str, float]:
    return {g.metric: g.target for g in db.scalars(select(Goal).where(Goal.user_id == user.id, Goal.year == year))}


@router.get("/stats/goals")
def get_goals(year: int = Query(), user: User = Depends(current_user), db: Session = Depends(get_db)):
    tz, rows = _load(db, user, None, None, with_tiles=False)
    targets = _goal_targets(db, user, year)
    return {"year": year, "targets": targets,
            "progress": X.goals_progress([r for _, r in rows], tz, year, _today(tz), targets)}


@router.put("/stats/goals")
def save_goals(data: GoalsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    for metric, value in data.targets.items():
        if metric not in X.GOAL_METRICS:
            raise HTTPException(422, f"Unbekanntes Ziel: {metric}")
        if value is not None and value < 0:
            raise HTTPException(422, "Ziele müssen positiv sein.")
        g = db.scalar(select(Goal).where(Goal.user_id == user.id, Goal.year == data.year, Goal.metric == metric))
        if not value:
            if g:
                db.delete(g)
        elif g:
            g.target = value
        else:
            db.add(Goal(user_id=user.id, year=data.year, metric=metric, target=value))
    db.commit()
    return get_goals(data.year, user, db)
