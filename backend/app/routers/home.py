from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import home_blocks
from ..config import settings
from ..database import get_db
from ..models import Activity, Bike, Component, Goal, MaintenanceLog, User
from ..security import current_user
from ..stats import extra as X
from ..stats.overview import Row, get_tz, local
from . import garage, mechanic
from .stats import _goal_targets, _load

router = APIRouter(prefix="/api", tags=["home"])

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


WET_NOTICE_HOURS = 4   # so lange steht der Hinweis nach dem Ende einer nassen Fahrt
WET_MIN_MINUTES = 5    # ab so vielen Minuten Regen oder nasser Straße gilt eine Fahrt als nass


def build_wet_notices(rides: list[dict], now: datetime, care: dict[int, list[datetime]]) -> list[dict]:
    """Hinweise zur Kettenpflege nach nassen Fahrten. rides: neueste zuerst, mit start (UTC), moving_time_s, wet_minutes, bike_id.
    care: je Rad die Zeitpunkte (UTC) bereits eingetragener Kettenpflege. Je Rad zählt nur die jüngste nasse Fahrt.
    Reiner Rechenkern ohne Datenbank."""
    out, seen = [], set()
    for r in rides:
        bike_id = r["bike_id"]
        if not bike_id or bike_id in seen or (r["wet_minutes"] or 0) < WET_MIN_MINUTES:
            continue
        seen.add(bike_id)
        ended = r["start"] + timedelta(seconds=r["moving_time_s"] or 0)
        expires = ended + timedelta(hours=WET_NOTICE_HOURS)
        if now >= expires or any(t >= ended for t in care.get(bike_id, [])):
            continue
        out.append({**{k: r[k] for k in ("activity_id", "name", "bike_id", "bike_name", "lube")},
                    "wet_minutes": round(r["wet_minutes"]), "ended_at": ended.isoformat() + "Z", "expires_at": expires.isoformat() + "Z"})
    return out


def build_home_week(rows: list[tuple[datetime, float, int, float]], today, weeks: int = 8, offset: int = 0) -> dict:
    """Wochenübersicht aus (lokaler Start, km, Fahrzeit, Höhenmeter). Reiner Rechenkern ohne Datenbank."""
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)  # offset: 0 = diese, -1 = Vorwoche
    ref = min(today, monday + timedelta(days=6))  # "gleiche Zeit der Vorwoche" bis zu diesem Tag
    first = monday - timedelta(weeks=weeks - 1)
    days = {monday + timedelta(days=i): {"km": 0.0, "rides": 0} for i in range(7)}
    totals = {"km": 0.0, "time_s": 0, "elev_m": 0.0, "rides": 0}
    per_week = {first + timedelta(weeks=i): 0.0 for i in range(weeks)}
    same_point_last_week = 0.0
    last_monday = monday - timedelta(weeks=1)
    for dt, km, t, elev in rows:
        d = dt.date()
        w = d - timedelta(days=d.weekday())
        if w in per_week:
            per_week[w] += km
        if w == monday:
            days[d]["km"] += km
            days[d]["rides"] += 1
            totals["km"] += km; totals["time_s"] += t; totals["elev_m"] += elev; totals["rides"] += 1
        elif w == last_monday and d <= ref - timedelta(weeks=1):
            same_point_last_week += km
    return {
        "days": [{"date": d.isoformat(), "label": WEEKDAYS[i], "km": round(v["km"], 1), "rides": v["rides"],
                  "today": d == today, "future": d > today} for i, (d, v) in enumerate(days.items())],
        "totals": {k: round(v, 1) for k, v in totals.items()},
        "last_week_same_point_km": round(same_point_last_week, 1),
        "last_week_km": round(per_week[last_monday], 1),
        "weeks": [{"week": w.isoformat(), "km": round(v, 1)} for w, v in per_week.items()],
        "monday": monday.isoformat(),
        "offset": offset,
    }


@router.get("/home/week")
def home_week(offset: int = Query(0, ge=-1040, le=0), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Wochenansicht der Startseite für eine frühere Woche (offset 0 = diese, -1 = Vorwoche, …)."""
    tz = get_tz(settings.timezone)
    today = local(datetime.now(timezone.utc).replace(tzinfo=None), tz).date()
    monday = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
    lo = datetime.combine(monday - timedelta(weeks=1, days=1), datetime.min.time())
    hi = datetime.combine(monday + timedelta(days=8), datetime.min.time())
    acts = db.scalars(select(Activity).where(Activity.user_id == user.id, Activity.start_date >= lo, Activity.start_date < hi)).all()
    rows = [(local(a.start_date, tz), a.distance_km, a.moving_time_s, a.elevation_m or 0.0) for a in acts]
    out = build_home_week(rows, today, weeks=2, offset=offset)
    earliest = db.scalar(select(func.min(Activity.start_date)).where(Activity.user_id == user.id))
    out["has_earlier"] = bool(earliest and local(earliest, tz).date() < monday)
    return out


def _wet_notices(db: Session, user: User, acts, bikes: dict, tz) -> list[dict]:
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    horizon = now - timedelta(hours=WET_NOTICE_HOURS + 24)  # nur frische Fahrten kommen in Frage
    recent = [a for a in acts if a.start_date >= horizon and a.bike_id in bikes and (a.wet_minutes or 0) >= WET_MIN_MINUTES]
    if not recent:
        return []
    care: dict[int, list[datetime]] = {}
    rows = db.execute(
        select(Component.bike_id, MaintenanceLog.performed_at, MaintenanceLog.performed_time)
        .join(MaintenanceLog, MaintenanceLog.component_id == Component.id)
        .where(Component.user_id == user.id, Component.category == "chain", Component.bike_id.in_({a.bike_id for a in recent}),
               MaintenanceLog.performed_at >= (horizon - timedelta(days=1)).date(),
               MaintenanceLog.result.is_(None) | MaintenanceLog.rule_id.is_not(None))  # eine Sichtprüfung ist keine Kettenpflege
    ).all()
    for bike_id, day, at in rows:  # eingetragene Zeiten sind Ortszeit; ohne Uhrzeit zählt das Tagesende
        local_dt = datetime.combine(day, at or time(23, 59))
        care.setdefault(bike_id, []).append(local_dt.replace(tzinfo=tz).astimezone(timezone.utc).replace(tzinfo=None))
    rides = [{"activity_id": a.id, "name": a.name, "bike_id": a.bike_id, "bike_name": bikes[a.bike_id].name,
              "lube": bikes[a.bike_id].chain_lube or "oil", "start": a.start_date, "moving_time_s": a.moving_time_s,
              "wet_minutes": a.wet_minutes} for a in sorted(recent, key=lambda x: x.start_date, reverse=True)]
    return build_wet_notices(rides, now, care)


def _mode(user: User) -> str:
    return user.ui_mode if user.ui_mode in ("simple", "expert") else "expert"


@router.get("/home/layout")
def home_layout(user: User = Depends(current_user)):
    """Welche Blöcke die Startseite zeigt (in dieser Reihenfolge) und welche es gibt."""
    mode = _mode(user)
    saved = home_blocks.parse_layout(user.home_layout)
    layout = home_blocks.DEFAULT_LAYOUT if saved is None else saved
    avail = {c["id"]: c["available"] for c in home_blocks.catalog(mode)}
    return {"mode": mode, "layout": [i for i in layout if avail.get(i)], "custom": saved is not None, "catalog": home_blocks.catalog(mode)}


class UiIn(BaseModel):
    mode: str | None = None
    layout: list[str] | None = None
    reset: bool = False  # True = zurück zur Standardanordnung


@router.put("/me/ui")
def set_ui(data: UiIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if data.mode is not None:
        if data.mode not in ("simple", "expert"):
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannter Modus")
        user.ui_mode = data.mode
    if data.reset:
        user.home_layout = None
    elif data.layout is not None:
        try:
            user.home_layout = home_blocks.clean_layout(data.layout)
        except ValueError as e:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    db.commit()
    return home_layout(user)


@router.get("/home/blocks")
def home_block_data(ids: str = Query(default="", max_length=200), user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Daten der Analyse-Blöcke (Eddington-Zahl, Serie, Rekorde, Form), nur für die angefragten."""
    want = [i for i in ids.split(",") if i in home_blocks.CATALOG]
    if _mode(user) != "expert":
        want = [i for i in want if not home_blocks.CATALOG[i][3]]
    if not home_blocks.needs_data(want):
        return {}
    tz = get_tz(settings.timezone)
    today = local(datetime.now(timezone.utc).replace(tzinfo=None), tz).date()
    rows = [Row(id=i, name="", bike_id=None, start=s, km=km or 0.0, time_s=t or 0, elev_m=e or 0.0)
            for i, s, km, t, e in db.execute(select(Activity.id, Activity.start_date, Activity.distance_km, Activity.moving_time_s,
                                                    Activity.elevation_m).where(Activity.user_id == user.id))]
    return home_blocks.compute(want, rows, tz, today)


@router.get("/home")
def home(user: User = Depends(current_user), db: Session = Depends(get_db)):
    tz = get_tz(settings.timezone)
    today = local(datetime.now(timezone.utc).replace(tzinfo=None), tz).date()
    since = datetime.combine(today - timedelta(weeks=9), datetime.min.time())
    year_start = datetime(today.year - 1, 12, 30)
    acts = db.scalars(select(Activity).where(Activity.user_id == user.id, Activity.start_date >= min(since, year_start))
                      .order_by(Activity.start_date.desc())).all()
    rows = [(local(a.start_date, tz), a.distance_km, a.moving_time_s, a.elevation_m or 0.0) for a in acts]
    week = build_home_week(rows, today)
    earliest = db.scalar(select(func.min(Activity.start_date)).where(Activity.user_id == user.id))
    week["has_earlier"] = bool(earliest and local(earliest, tz).date() < today - timedelta(days=today.weekday()))
    year_km = sum(r[1] for r in rows if r[0].year == today.year)

    goal = db.scalar(select(Goal).where(Goal.user_id == user.id, Goal.year == today.year, Goal.metric == "km"))
    targets = _goal_targets(db, user, today.year)
    goals = []
    if targets:
        _, year_rows = _load(db, user, None, today.year, with_tiles=False)
        goals = X.goals_progress([r for _, r in year_rows], tz, today.year, today, targets)
    bikes = db.scalars(select(Bike).where(Bike.user_id == user.id, Bike.retired.is_(False)).order_by(Bike.id)).all()
    wet_notices = _wet_notices(db, user, acts, {b.id: b for b in bikes}, tz)
    bike_week: dict[int, float] = {}
    monday = today - timedelta(days=today.weekday())
    for (dt, km, _, _), a in zip(rows, acts):
        if dt.date() >= monday and a.bike_id:
            bike_week[a.bike_id] = bike_week.get(a.bike_id, 0.0) + km
    bike_out = []
    for b in bikes:
        o = garage._bike_out(db, b)
        bike_out.append({"id": b.id, "name": b.name, "type": b.type, "total_km": o.total_km, "week_km": round(bike_week.get(b.id, 0.0), 1),
                         "due_count": o.due_count, "unknown_count": o.unknown_count, "tire_set": o.tire_set.name if o.tire_set else None})
    maintenance = garage.maintenance_overview(user, db)
    return {
        "today": today.isoformat(),
        "week": week,
        "year": {"year": today.year, "km": round(year_km, 1), "goal_km": goal.target if goal else None,
                 "days_left": (date(today.year, 12, 31) - today).days, "goals": goals},
        "maintenance": {"status": maintenance["status"], "items": maintenance["items"][:5], "total": len(maintenance["items"])},
        "bikes": bike_out,
        "wet_notices": wet_notices,
        "recent": [{"id": a.id, "name": a.name, "date": local(a.start_date, tz).isoformat(), "km": round(a.distance_km, 1),
                    "elev_m": round(a.elevation_m or 0), "time_s": a.moving_time_s} for a in acts[:4]],
        "has_rides": bool(acts),
        "mechanic_requests": mechanic.pending_for(db, user),
    }
