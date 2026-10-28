import json
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..importers import polyline
from .. import services
from ..models import Activity, Bike, Component, Goal, User
from ..security import current_user
from ..stats import tiles as T
from ..stats import extra as X
from ..stats import deep as D
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


def _load(db: Session, user: User, bike_id: int | None, year: int | None, with_tiles: bool = True, with_power: bool = False):
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
            wind_kmh=a.wind_kmh, avg_power=a.avg_power, terrain=a.terrain,
        )))
        if with_power and a.avg_power and a.avg_power > 0 and a.details:
            try:
                rows[-1][1].curve, rows[-1][1].curve_approx = D.ride_curve(json.loads(a.details))
            except ValueError:
                pass
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
    """Alle Strecken (vereinfachte Polylines) plus erkundete Kacheln für die Karte.

    Für den Zeitverlauf gibt es zu jeder Strecke Tag (Tage seit 1970, Ortszeit) und Kilometer und zu jeder Kachel den
    Tag der ersten Fahrt hindurch.
    """
    tz, rows = _load(db, user, bike_id, year)
    epoch = date(1970, 1, 1)
    tiles: dict = {}
    lines, days, kms = [], [], []
    for a, r in rows:
        day = (local(a.start_date, tz).date() - epoch).days
        if a.polyline:
            lines.append(a.polyline)
            days.append(day)
            kms.append(round(a.distance_km, 1))
        for t in r.tiles or ():
            if t not in tiles or day < tiles[t]:
                tiles[t] = day
    size, at = T.max_square(set(tiles))
    square = None
    if at:
        s, w, _, _ = T.tile_bounds(at[0] + size - 1, at[1] + size - 1)
        _, _, n, e = T.tile_bounds(at[0], at[1])
        square = {"size": size, "bounds": [[s, w], [n, e]]}
    return {
        "lines": lines, "days": days, "km": kms,
        "tiles": [[x, y, tiles[(x, y)]] for x, y in sorted(tiles)], "zoom": T.ZOOM, "max_square": square,
    }


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


# ---------- Tiefere Auswertungen ----------

@router.get("/stats/power")
def stats_power(
    bike_id: int | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    """Leistungskurve, geschätzte FTP und Zonen, Verlauf und Form aus Fahrten mit Leistungsdaten."""
    tz, rows = _load(db, user, bike_id, None, with_tiles=False, with_power=True)
    return D.build_power([r for _, r in rows], tz, _today(tz), user.weight_kg)


@router.get("/stats/conditions")
def stats_conditions(
    bike_id: int | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    tz, rows = _load(db, user, bike_id, None, with_tiles=False)
    return D.build_conditions([r for _, r in rows])


@router.get("/stats/patterns")
def stats_patterns(
    bike_id: int | None = Query(default=None),
    user: User = Depends(current_user),
    db: Session = Depends(get_db),
):
    tz, rows = _load(db, user, bike_id, None, with_tiles=False)
    return D.build_patterns([r for _, r in rows], tz, _today(tz))


@router.get("/stats/bikes")
def stats_bikes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Räder nebeneinander: Tempo, Länge, Höhenmeter, Nässe, Leistung, ersetzte Teile je 1000 km."""
    tz, rows = _load(db, user, None, None, with_tiles=False)
    replaced: dict[int, int] = {}
    for c in db.scalars(select(Component).where(Component.user_id == user.id, Component.retired_at.is_not(None))):
        if c.bike_id:
            replaced[c.bike_id] = replaced.get(c.bike_id, 0) + 1
    return D.build_bike_compare([r for _, r in rows], _bike_names(db, user), replaced)


_ROUTE_CACHE: dict[int, tuple[tuple, dict]] = {}


@router.get("/stats/routes")
def stats_routes(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Stammrunden: oft gefahrene Strecken mit Zeiten und Entwicklung. Rechnet nur auf deinen eigenen Fahrten."""
    tz, rows = _load(db, user, None, None, with_tiles=False)
    rows = [r for _, r in rows]
    stamp = (len(rows), max((r.id for r in rows), default=0))
    hit = _ROUTE_CACHE.get(user.id)
    if hit and hit[0] == stamp:
        return hit[1]
    polys = {a.id: a.polyline for a in db.scalars(select(Activity).where(Activity.user_id == user.id, Activity.polyline.is_not(None)))}
    paths = {}
    for r in rows:
        enc = polys.get(r.id)
        if not enc:
            continue
        try:
            pts = polyline.decode(enc)
        except Exception:
            continue
        if len(pts) >= 5:
            paths[r.id] = [(float(la), float(ln)) for la, ln in pts]
    out = D.build_routes(rows, paths, tz)
    _ROUTE_CACHE[user.id] = (stamp, out)
    return out


@router.get("/stats/forecast")
def stats_forecast(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Wann Wartungen voraussichtlich fällig werden, gerechnet mit deinem Kilometertempo der letzten 8 Wochen."""
    tz, rows = _load(db, user, None, None, with_tiles=False)
    rows = [r for _, r in rows]
    today = _today(tz)
    items = []
    for bike in db.scalars(select(Bike).where(Bike.user_id == user.id, Bike.retired.is_(False))):
        pace = D.weekly_pace(rows, today, bike.id)
        for comp in db.scalars(select(Component).where(Component.bike_id == bike.id, Component.retired_at.is_(None))):
            for rule in comp.rules:
                st = services.rule_state(db, comp, rule, today)
                it = D.forecast_item(rule.label, comp.name, bike.name, {**st, "interval_months": rule.interval_months}, pace, today)
                if it:
                    items.append(it)
    items.sort(key=lambda x: x["days"])
    return {"items": items[:30], "today": today.isoformat()}


@router.get("/stats/ride-impact/{activity_id}")
def stats_ride_impact(activity_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Einfluss einer Fahrt auf Fitness, Ermüdung, Form und FTP (Stand nach dieser Fahrt)."""
    tz, rows = _load(db, user, None, None, with_tiles=False, with_power=True)
    out = D.ride_impact([r for _, r in rows], activity_id, tz)
    if out is None:
        raise HTTPException(404, "Fahrt nicht gefunden")
    return out
