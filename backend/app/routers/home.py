from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import Activity, Bike, Goal, User
from ..security import current_user
from ..stats import extra as X
from ..stats.overview import get_tz, local
from . import garage
from .stats import _goal_targets, _load

router = APIRouter(prefix="/api", tags=["home"])

WEEKDAYS = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


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
        "maintenance": {"status": maintenance["status"], "items": maintenance["items"][:6], "total": len(maintenance["items"])},
        "bikes": bike_out,
        "recent": [{"id": a.id, "name": a.name, "date": local(a.start_date, tz).isoformat(), "km": round(a.distance_km, 1),
                    "elev_m": round(a.elevation_m or 0), "time_s": a.moving_time_s} for a in acts[:4]],
        "has_rides": bool(acts),
    }
