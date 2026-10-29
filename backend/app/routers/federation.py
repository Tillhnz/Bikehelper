"""Gruppen über mehrere BikeHelper-Server.

Zwei Seiten in einer Datei:
- /api/federation/...: die Schnittstelle des Gastgebers. Andere Server melden sich mit einem Schlüssel, den sie beim Beitritt bekommen.
- /api/groups/remote/...: was ein Nutzer dieses Servers tut, um einer Gruppe auf einem anderen Server beizutreten.

Übertragen werden nur Anzeigename, Freigabe und Tageswerte (Datum, Kilometer, Fahrten, Zeit, Höhenmeter, längste Fahrt).
Beschreibung des Ablaufs: siehe app/federation.py und README.
"""
from __future__ import annotations

import hashlib
import secrets
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import federation as fed
from ..config import settings
from ..database import get_db
from ..models import Group, GroupMember, RemoteDay, RemoteMember, RemoteMembership, User
from ..security import bearer, current_user
from . import groups as g

router = APIRouter(prefix="/api/federation", tags=["federation"])
guest = APIRouter(prefix="/api/groups/remote", tags=["federation"])

MAX_DAYS_PER_PUSH = 4000
FIRST_DAY = date(2000, 1, 1)


def _enabled() -> None:
    if not settings.federation_enabled:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gruppen mit anderen Servern sind auf diesem Server nicht eingeschaltet.")


def _hash(key: str) -> str:
    return hashlib.sha256(key.encode()).hexdigest()


def remote_member(creds: HTTPAuthorizationCredentials | None = Depends(bearer), db: Session = Depends(get_db)) -> RemoteMember:
    _enabled()
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Nicht angemeldet")
    rm = db.scalar(select(RemoteMember).where(RemoteMember.key_hash == _hash(creds.credentials)))
    if rm is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unbekannter Schlüssel")
    return rm


# ---------- Gastgeber ----------

class JoinIn(BaseModel):
    token: str = Field(min_length=8, max_length=100)
    display_name: str = Field(min_length=1, max_length=60)
    share: bool = True
    origin: str | None = Field(default=None, max_length=200)


class DayIn(BaseModel):
    day: date
    km: float = Field(ge=0, le=3000)
    rides: int = Field(ge=0, le=500)
    time_s: int = Field(ge=0, le=172_800)
    elev_m: float = Field(ge=0, le=50_000)
    longest_km: float = Field(ge=0, le=3000)


class PushIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    share: bool = True
    since: date | None = None  # ab diesem Tag werden die gespeicherten Tage ersetzt; ohne Datum alle
    days: list[DayIn] = Field(default_factory=list, max_length=MAX_DAYS_PER_PUSH)


class MeIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    share: bool | None = None


@router.get("/ping")
def ping():
    _enabled()
    return {"app": "bikehelper", "federation": 1}


@router.get("/invite/{token}")
def invite_preview(token: str, db: Session = Depends(get_db)):
    """Name der Gruppe zu einem gültigen Einladungsschlüssel, damit der Gast-Server dem Nutzer zeigen kann, wohin er beitritt."""
    _enabled()
    inv = g.find_invite(db, token)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Die Einladung ist ungültig oder abgelaufen")
    return {"group": db.get(Group, inv.group_id).name, "members": len(g._members(db, inv.group_id))}


@router.post("/join")
def join(data: JoinIn, db: Session = Depends(get_db)):
    _enabled()
    inv = g.find_invite(db, data.token)
    if inv is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Die Einladung ist ungültig oder abgelaufen")
    gid = inv.group_id
    if len(g._members(db, gid)) >= g.MAX_MEMBERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Die Gruppe ist voll")
    name = g._clean(data.display_name)
    g._unique_name(db, gid, name)
    key = secrets.token_urlsafe(32)
    origin = (data.origin or "").strip()[:200]
    rm = RemoteMember(group_id=gid, display_name=name, key_hash=_hash(key), share=data.share,
                      origin=origin if origin.startswith(("http://", "https://")) else None)
    db.add(rm)
    if not inv.multi:
        db.delete(inv)  # persönliche Einladungen gelten einmal, der Gruppenlink bleibt
    db.commit()
    return {"key": key, "group": db.get(Group, gid).name, "members": len(g._members(db, gid))}


@router.post("/push")
def push(data: PushIn, rm: RemoteMember = Depends(remote_member), db: Session = Depends(get_db)):
    if data.display_name is not None:
        name = g._clean(data.display_name)
        if name.lower() != rm.display_name.lower():
            g._unique_name(db, rm.group_id, name, except_remote=rm.id)
        rm.display_name = name
    rm.share = data.share
    if not data.share:
        db.execute(delete(RemoteDay).where(RemoteDay.member_id == rm.id))  # wer nicht teilt, hinterlässt keine Werte
    else:
        limit = date.today() + timedelta(days=2)
        q = delete(RemoteDay).where(RemoteDay.member_id == rm.id)
        if data.since is not None:
            q = q.where(RemoteDay.day >= data.since)
        db.execute(q)
        seen: dict[date, DayIn] = {}
        for d in data.days:
            if FIRST_DAY <= d.day <= limit and (data.since is None or d.day >= data.since):
                seen[d.day] = d
        for d in seen.values():
            db.add(RemoteDay(member_id=rm.id, day=d.day, km=d.km, rides=d.rides, time_s=d.time_s, elev_m=d.elev_m,
                             longest_km=min(d.longest_km, d.km)))
    rm.last_push_at = datetime.utcnow()
    db.commit()
    return {"group": db.get(Group, rm.group_id).name, "members": len(g._members(db, rm.group_id))}


@router.get("/info")
def info(rm: RemoteMember = Depends(remote_member), db: Session = Depends(get_db)):
    return g._info(db, rm.group_id, "member", rm.display_name, rm.share, [], -rm.id, is_local=False)


@router.get("/stats")
def stats(period: str = "week", offset: int = 0, rm: RemoteMember = Depends(remote_member), db: Session = Depends(get_db)):
    return g.compute_stats(db, rm.group_id, period, offset, -rm.id)


@router.get("/goal")
def goal(rm: RemoteMember = Depends(remote_member), db: Session = Depends(get_db)):
    return g.goal_state(db, rm.group_id)


@router.get("/duel")
def duel(a: int, b: int, rm: RemoteMember = Depends(remote_member), db: Session = Depends(get_db)):
    return g.compute_duel(db, rm.group_id, a, b, -rm.id)


@router.put("/me")
def update_me(data: MeIn, rm: RemoteMember = Depends(remote_member), db: Session = Depends(get_db)):
    if data.display_name is not None:
        name = g._clean(data.display_name)
        g._unique_name(db, rm.group_id, name, except_remote=rm.id)
        rm.display_name = name
    if data.share is not None:
        rm.share = data.share
        if not data.share:
            db.execute(delete(RemoteDay).where(RemoteDay.member_id == rm.id))
    db.commit()
    return {"ok": True}


@router.delete("/leave", status_code=204)
def leave(rm: RemoteMember = Depends(remote_member), db: Session = Depends(get_db)):
    db.execute(delete(RemoteDay).where(RemoteDay.member_id == rm.id))
    db.delete(rm)
    db.commit()


# ---------- Gast: einer Gruppe auf einem anderen Server beitreten ----------

class LinkIn(BaseModel):
    link: str = Field(min_length=10, max_length=600)


class GuestJoinIn(LinkIn):
    display_name: str = Field(min_length=1, max_length=60)
    share: bool = True


def _fed_error(e: fed.FederationError) -> HTTPException:
    return HTTPException(e.status_code if e.status_code in (404, 409, 422) else status.HTTP_502_BAD_GATEWAY, e.message)


@guest.get("/status")
def remote_status(user: User = Depends(current_user)):
    return {"enabled": settings.federation_enabled}


@guest.post("/preview")
def preview(data: LinkIn, user: User = Depends(current_user)):
    try:
        origin, token = fed.parse_link(data.link)
        out = fed.call(origin, "GET", f"/invite/{token}") or {}
    except fed.FederationError as e:
        raise _fed_error(e)
    return {"group": out.get("group"), "members": out.get("members"), "host": origin.split("://", 1)[-1]}


@guest.post("/join", status_code=201)
def join_remote(data: GuestJoinIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    name = g._clean(data.display_name)
    mine = (db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.user_id == user.id)) or 0) \
        + (db.scalar(select(func.count()).select_from(RemoteMembership).where(RemoteMembership.user_id == user.id)) or 0)
    if mine >= g.MAX_GROUPS_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mehr als {g.MAX_GROUPS_PER_USER} Gruppen sind nicht möglich")
    try:
        origin, token = fed.parse_link(data.link)
        out = fed.call(origin, "POST", "/join", json={"token": token, "display_name": name, "share": data.share,
                                                       "origin": settings.public_url}) or {}
    except fed.FederationError as e:
        raise _fed_error(e)
    key = out.get("key")
    if not isinstance(key, str) or len(key) < 20 or len(key) > 80:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Der andere Server hat unverständlich geantwortet.")
    group = str(out.get("group") or "Gruppe")[:80]
    if db.scalar(select(RemoteMembership.id).where(RemoteMembership.user_id == user.id, RemoteMembership.host_url == origin,
                                                   RemoteMembership.group_name == group)) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Du bist schon in dieser Gruppe auf diesem Server.")
    ms = RemoteMembership(user_id=user.id, host_url=origin, group_name=group, members=out.get("members") if isinstance(out.get("members"), int) else None,
                          display_name=name, share=data.share, member_key=key)
    db.add(ms)
    db.commit()
    fed.trigger(user.id)
    return {"id": fed.REMOTE_BASE + ms.id}


@guest.post("/sync")
def sync_now(user: User = Depends(current_user)):
    """Sendet die Tageswerte sofort an die Gastgeber (sonst alle paar Stunden und nach dem Beitritt)."""
    if not settings.federation_enabled:
        raise HTTPException(status.HTTP_409_CONFLICT, "Gruppen mit anderen Servern sind nicht eingeschaltet.")
    fed.sync_user(user.id)
    return {"ok": True}
