"""Gruppen: Mitglieder vergleichen ihre Kennzahlen in Ranglisten (Woche, Monat, Jahr, gesamt).

Geteilt werden nur Summen je Zeitraum (Kilometer, Höhenmeter, Zeit, Fahrten, Tempo, längste Fahrt, aktive Tage). Nie Strecken, Karten,
Räder, Wartung, Fahrtnamen oder die E-Mail-Adresse; in der Gruppe erscheint nur der gewählte Anzeigename. Wer nicht teilt, zählt nicht mit.
"""
from __future__ import annotations

import logging
import secrets
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import notify
from ..config import settings
from ..database import get_db
from ..models import Activity, Group, GroupInvite, GroupMember, User
from ..security import current_user
from ..stats.overview import get_tz, local

log = logging.getLogger("bikehelper.groups")
router = APIRouter(prefix="/api/groups", tags=["groups"])

MAX_GROUPS_PER_USER = 10
MAX_MEMBERS = 50
MAX_PENDING_INVITES = 30
INVITE_DAYS = 14
LINK_DAYS = 30
PERIODS = ("week", "month", "year", "all")
METRICS = ("km", "elev_m", "time_s", "rides", "avg_speed", "longest_km", "active_days")


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=60)


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class JoinIn(BaseModel):
    token: str
    display_name: str = Field(min_length=1, max_length=60)
    share: bool = True


class MeIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    share: bool | None = None


class RoleIn(BaseModel):
    role: str


def _member(db: Session, group_id: int, user: User) -> GroupMember:
    m = db.get(GroupMember, (group_id, user.id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gruppe nicht gefunden")
    return m


def _admin(db: Session, group_id: int, user: User) -> GroupMember:
    m = _member(db, group_id, user)
    if m.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Das dürfen nur Gruppenadministratoren")
    return m


def _clean(name: str) -> str:
    n = " ".join(name.split())
    if not n:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Der Name darf nicht leer sein")
    return n


def _unique_name(db: Session, group_id: int, name: str, except_user: int | None = None) -> None:
    q = select(GroupMember.user_id).where(GroupMember.group_id == group_id, func.lower(GroupMember.display_name) == name.lower())
    if except_user is not None:
        q = q.where(GroupMember.user_id != except_user)
    if db.scalar(q) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Diesen Anzeigenamen gibt es in der Gruppe schon")


def _admin_count(db: Session, group_id: int) -> int:
    return db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group_id, GroupMember.role == "admin")) or 0


def _fresh(inv: GroupInvite) -> bool:
    days = LINK_DAYS if inv.multi else INVITE_DAYS
    return inv.created_at is not None and inv.created_at > datetime.utcnow() - timedelta(days=days)


def find_invite(db: Session, token: str | None) -> GroupInvite | None:
    """Gültige Gruppeneinladung zu diesem Schlüssel (auch zum Anlegen eines Kontos nutzbar), sonst None."""
    if not token:
        return None
    inv = db.scalar(select(GroupInvite).where(GroupInvite.token == token.strip()))
    return inv if inv is not None and _fresh(inv) else None


def leave_all(db: Session, user_id: int) -> None:
    """Beim Löschen eines Kontos: aus allen Gruppen entfernen; ohne Admin rückt das dienstälteste Mitglied nach, leere Gruppen verschwinden."""
    gids = db.scalars(select(GroupMember.group_id).where(GroupMember.user_id == user_id)).all()
    db.execute(delete(GroupMember).where(GroupMember.user_id == user_id))
    db.flush()
    for gid in gids:
        rest = db.scalars(select(GroupMember).where(GroupMember.group_id == gid).order_by(GroupMember.joined_at, GroupMember.user_id)).all()
        if not rest:
            db.execute(delete(GroupInvite).where(GroupInvite.group_id == gid))
            db.execute(delete(Group).where(Group.id == gid))
        elif not any(m.role == "admin" for m in rest):
            rest[0].role = "admin"
    db.execute(delete(GroupInvite).where(GroupInvite.invited_by == user_id))


# ---------- Gruppen ----------

@router.get("")
def my_groups(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.execute(
        select(Group, GroupMember).join(GroupMember, GroupMember.group_id == Group.id)
        .where(GroupMember.user_id == user.id).order_by(Group.name)
    ).all()
    counts = dict(db.execute(select(GroupMember.group_id, func.count()).group_by(GroupMember.group_id)).all())
    return [{"id": g.id, "name": g.name, "role": m.role, "members": counts.get(g.id, 0), "share": m.share} for g, m in rows]


@router.get("/invitations")
def my_invitations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Offene Einladungen an die E-Mail-Adresse dieses Kontos (auch ohne Mailversand sichtbar)."""
    rows = db.execute(
        select(GroupInvite, Group).join(Group, Group.id == GroupInvite.group_id)
        .where(func.lower(GroupInvite.email) == user.email.lower()).order_by(GroupInvite.id.desc())
    ).all()
    return [{"token": i.token, "group": g.name} for i, g in rows if _fresh(i)]


@router.post("", status_code=201)
def create_group(data: GroupIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.user_id == user.id)) >= MAX_GROUPS_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mehr als {MAX_GROUPS_PER_USER} Gruppen sind nicht möglich")
    g = Group(name=_clean(data.name))
    db.add(g)
    db.flush()
    db.add(GroupMember(group_id=g.id, user_id=user.id, role="admin", display_name=_clean(data.display_name), share=True))
    db.commit()
    return {"id": g.id}


@router.get("/join/{token}")
def preview_invite(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = db.scalar(select(GroupInvite).where(GroupInvite.token == token))
    if inv is None or not _fresh(inv):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Die Einladung ist ungültig oder abgelaufen")
    g = db.get(Group, inv.group_id)
    return {"group": g.name, "already_member": db.get(GroupMember, (g.id, user.id)) is not None}


@router.post("/join")
def join(data: JoinIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = db.scalar(select(GroupInvite).where(GroupInvite.token == data.token))
    if inv is None or not _fresh(inv):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Die Einladung ist ungültig oder abgelaufen")
    gid = inv.group_id
    if db.get(GroupMember, (gid, user.id)) is not None:
        if not inv.multi:
            db.delete(inv)
        db.commit()
        return {"id": gid}
    if db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == gid)) >= MAX_MEMBERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Die Gruppe ist voll")
    if db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.user_id == user.id)) >= MAX_GROUPS_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mehr als {MAX_GROUPS_PER_USER} Gruppen sind nicht möglich")
    name = _clean(data.display_name)
    _unique_name(db, gid, name)
    db.add(GroupMember(group_id=gid, user_id=user.id, role="member", display_name=name, share=data.share))
    if not inv.multi:
        db.delete(inv)  # persönliche Einladungen sind einmal gültig, der Gruppenlink bleibt
    db.commit()
    return {"id": gid}


@router.get("/{group_id}")
def group_info(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    me = _member(db, group_id, user)
    g = db.get(Group, group_id)
    members = db.scalars(select(GroupMember).where(GroupMember.group_id == group_id).order_by(GroupMember.display_name)).all()
    out = {
        "id": g.id, "name": g.name, "role": me.role, "display_name": me.display_name, "share": me.share,
        "members": [{"user_id": m.user_id, "display_name": m.display_name, "role": m.role, "share": m.share, "is_me": m.user_id == user.id} for m in members],
        "invites": [],
        "mail_enabled": notify.smtp_configured(),
    }
    if me.role == "admin":
        invs = db.scalars(select(GroupInvite).where(GroupInvite.group_id == group_id).order_by(GroupInvite.id.desc())).all()
        out["invites"] = [{"id": i.id, "email": i.email, "expired": not _fresh(i)} for i in invs if not i.multi]
        shared = next((i for i in invs if i.multi and _fresh(i)), None)
        out["invite_link"] = f"{settings.public_url.rstrip('/')}/groups/join/{shared.token}" if shared else None
    return out


@router.put("/{group_id}")
def rename(group_id: int, data: RenameIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _admin(db, group_id, user)
    db.get(Group, group_id).name = _clean(data.name)
    db.commit()
    return {"ok": True}


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _admin(db, group_id, user)
    db.execute(delete(GroupInvite).where(GroupInvite.group_id == group_id))
    db.execute(delete(GroupMember).where(GroupMember.group_id == group_id))
    db.execute(delete(Group).where(Group.id == group_id))
    db.commit()


# ---------- Einladungen ----------

@router.post("/{group_id}/invites", status_code=201)
def invite(group_id: int, data: InviteIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    me = _admin(db, group_id, user)
    email = data.email.strip().lower()
    if "@" not in email or " " in email:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bitte eine gültige E-Mail-Adresse angeben")
    if db.scalar(select(func.count()).select_from(GroupInvite).where(GroupInvite.group_id == group_id)) >= MAX_PENDING_INVITES:
        raise HTTPException(status.HTTP_409_CONFLICT, "Zu viele offene Einladungen. Lösche alte Einladungen.")
    g = db.get(Group, group_id)
    inv = GroupInvite(group_id=group_id, email=email, token=secrets.token_urlsafe(24), invited_by=user.id)
    db.add(inv)
    db.commit()
    link = f"{settings.public_url.rstrip('/')}/groups/join/{inv.token}"
    mailed = False
    if notify.smtp_configured():
        try:
            notify.send_email(email, f"Einladung zur BikeHelper-Gruppe „{g.name}“",
                              f"{me.display_name} lädt dich in die Gruppe „{g.name}“ ein. In der Gruppe werden nur Kennzahlen "
                              f"(Kilometer, Höhenmeter, Zeit) verglichen, keine Strecken. Einladung annehmen (14 Tage gültig):\n{link}")
            mailed = True
        except Exception:
            log.exception("Gruppeneinladung konnte nicht per Mail verschickt werden")
    return {"id": inv.id, "link": link, "mailed": mailed}


@router.post("/{group_id}/invite-link")
def create_invite_link(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Einladungslink für mehrere Personen (30 Tage). Ein neuer Link ersetzt den alten; auch Personen ohne Konto können sich darüber registrieren."""
    _admin(db, group_id, user)
    db.execute(delete(GroupInvite).where(GroupInvite.group_id == group_id, GroupInvite.multi.is_(True)))
    inv = GroupInvite(group_id=group_id, email="", token=secrets.token_urlsafe(24), invited_by=user.id, multi=True)
    db.add(inv)
    db.commit()
    return {"link": f"{settings.public_url.rstrip('/')}/groups/join/{inv.token}"}


@router.delete("/{group_id}/invite-link", status_code=204)
def delete_invite_link(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _admin(db, group_id, user)
    db.execute(delete(GroupInvite).where(GroupInvite.group_id == group_id, GroupInvite.multi.is_(True)))
    db.commit()


@router.get("/invite-info/{token}")
def invite_info(token: str, db: Session = Depends(get_db)):
    """Ohne Anmeldung: Name der Gruppe zu einem gültigen Einladungsschlüssel, damit die Anmeldeseite sagen kann, wohin es geht."""
    inv = find_invite(db, token)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Die Einladung ist ungültig oder abgelaufen")
    return {"group": db.get(Group, inv.group_id).name}


@router.delete("/{group_id}/invites/{invite_id}", status_code=204)
def delete_invite(group_id: int, invite_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _admin(db, group_id, user)
    db.execute(delete(GroupInvite).where(GroupInvite.id == invite_id, GroupInvite.group_id == group_id))
    db.commit()


# ---------- Mitglieder ----------

@router.put("/{group_id}/me")
def update_me(group_id: int, data: MeIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _member(db, group_id, user)
    if data.display_name is not None:
        name = _clean(data.display_name)
        _unique_name(db, group_id, name, except_user=user.id)
        m.display_name = name
    if data.share is not None:
        m.share = data.share
    db.commit()
    return {"ok": True}


@router.delete("/{group_id}/me", status_code=204)
def leave(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    m = _member(db, group_id, user)
    others = db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id != user.id))
    if m.role == "admin" and _admin_count(db, group_id) <= 1 and others:
        raise HTTPException(status.HTTP_409_CONFLICT, "Du bist der einzige Gruppenadministrator. Ernenne zuerst jemand anderen oder lösche die Gruppe.")
    db.delete(m)
    db.flush()
    if not others:
        db.execute(delete(GroupInvite).where(GroupInvite.group_id == group_id))
        db.execute(delete(Group).where(Group.id == group_id))
    db.commit()


@router.put("/{group_id}/members/{member_id}/role")
def set_role(group_id: int, member_id: int, data: RoleIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _admin(db, group_id, user)
    if data.role not in ("admin", "member"):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannte Rolle")
    m = db.get(GroupMember, (group_id, member_id))
    if m is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mitglied nicht gefunden")
    if m.role == "admin" and data.role == "member" and _admin_count(db, group_id) <= 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Es muss mindestens einen Gruppenadministrator geben")
    m.role = data.role
    db.commit()
    return {"ok": True}


@router.delete("/{group_id}/members/{member_id}", status_code=204)
def remove_member(group_id: int, member_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _admin(db, group_id, user)
    if member_id == user.id:
        raise HTTPException(status.HTTP_409_CONFLICT, "Zum Verlassen der Gruppe nutze „Gruppe verlassen“")
    db.execute(delete(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == member_id))
    db.commit()


# ---------- Ranglisten ----------

def _bounds(period: str, offset: int, today: date) -> tuple[date | None, date | None, str]:
    """Zeitraum als lokale Daten [von, bis) und Beschriftung; offset 0 = aktuell, -1 = davor …"""
    if period == "week":
        start = today - timedelta(days=today.weekday()) + timedelta(weeks=offset)
        return start, start + timedelta(days=7), f"Woche ab {start:%d.%m.%Y}"
    if period == "month":
        idx = today.year * 12 + today.month - 1 + offset
        y, m = divmod(idx, 12)
        start = date(y, m + 1, 1)
        end = date(y + (m + 1) // 12, (m + 1) % 12 + 1, 1)
        names = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]
        return start, end, f"{names[m]} {y}"
    if period == "year":
        y = today.year + offset
        return date(y, 1, 1), date(y + 1, 1, 1), str(y)
    return None, None, "Gesamt"


def _empty() -> dict:
    return {"km": 0.0, "elev_m": 0.0, "time_s": 0, "rides": 0, "avg_speed": None, "longest_km": 0.0, "active_days": 0}


@router.get("/{group_id}/stats")
def group_stats(group_id: int, period: str = "week", offset: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _member(db, group_id, user)
    if period not in PERIODS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannter Zeitraum")
    offset = min(0, max(-520, offset))
    tz = get_tz(settings.timezone)
    today = local(datetime.now(timezone.utc).replace(tzinfo=None), tz).date()
    lo, hi, label = _bounds(period, offset if period != "all" else 0, today)
    members = db.scalars(select(GroupMember).where(GroupMember.group_id == group_id)).all()
    sharing = {m.user_id: m for m in members if m.share}
    totals = {uid: _empty() for uid in sharing}
    days: dict[int, set[date]] = {uid: set() for uid in sharing}
    weekly: dict[int, dict[date, float]] = {uid: {} for uid in sharing}
    week0 = today - timedelta(days=today.weekday())
    first_week = week0 - timedelta(weeks=11)
    if sharing:
        # nur die nötigen Spalten, keine Strecken oder Namen
        q = select(Activity.user_id, Activity.start_date, Activity.distance_km, Activity.moving_time_s, Activity.elevation_m).where(Activity.user_id.in_(sharing))
        for uid, start, km, secs, elev in db.execute(q):
            d = local(start, tz).date()
            km, secs, elev = km or 0.0, secs or 0, elev or 0.0
            if d >= first_week:
                w = d - timedelta(days=d.weekday())
                weekly[uid][w] = weekly[uid].get(w, 0.0) + km
            if (lo and d < lo) or (hi and d >= hi):
                continue
            t = totals[uid]
            t["km"] += km
            t["elev_m"] += elev
            t["time_s"] += secs
            t["rides"] += 1
            t["longest_km"] = max(t["longest_km"], km)
            days[uid].add(d)
    for uid, t in totals.items():
        t["active_days"] = len(days[uid])
        t["avg_speed"] = round(t["km"] / (t["time_s"] / 3600), 1) if t["time_s"] >= 600 and t["km"] > 0 else None
        t["km"], t["elev_m"], t["longest_km"] = round(t["km"], 1), round(t["elev_m"]), round(t["longest_km"], 1)
    rows = [{"user_id": uid, "display_name": sharing[uid].display_name, "is_me": uid == user.id, **t} for uid, t in totals.items()]
    ranks: dict[str, list[int]] = {}
    for metric in METRICS:  # Rang je Kennzahl, 1 = bester; gleiche Werte teilen sich den Rang; leere Werte zählen nicht
        vals = sorted({r[metric] for r in rows if r[metric]}, reverse=True)
        for r in rows:
            r.setdefault("rank", {})[metric] = vals.index(r[metric]) + 1 if r[metric] else None
        ranks[metric] = vals
    rows.sort(key=lambda r: (-(r["km"] or 0), r["display_name"].lower()))
    weeks = [first_week + timedelta(weeks=i) for i in range(12)]
    return {
        "period": period, "offset": offset, "label": label,
        "can_next": period != "all" and offset < 0, "can_prev": period != "all",
        "rows": rows,
        "not_sharing": sorted(m.display_name for m in members if not m.share),
        "weekly": {"weeks": [w.isoformat() for w in weeks],
                   "series": [{"display_name": sharing[uid].display_name, "is_me": uid == user.id, "km": [round(weekly[uid].get(w, 0.0), 1) for w in weeks]} for uid in sharing]},
    }
