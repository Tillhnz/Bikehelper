"""Gruppen: Mitglieder vergleichen ihre Kennzahlen in Ranglisten (Woche, Monat, Jahr, gesamt).

Geteilt werden nur Summen je Zeitraum (Kilometer, Höhenmeter, Zeit, Fahrten, Tempo, längste Fahrt, aktive Tage). Nie Strecken, Karten,
Räder, Wartung, Fahrtnamen oder die E-Mail-Adresse; in der Gruppe erscheint nur der gewählte Anzeigename. Wer nicht teilt, zählt nicht mit.
"""
from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import federation as fed
from .. import notify
from ..config import settings
from ..database import get_db
from ..models import Activity, Group, GroupGoal, GroupInvite, GroupMember, RemoteDay, RemoteMember, RemoteMembership, User
from ..security import current_user
from ..stats.extra import DAYPARTS, MILESTONES, load_series, longest_week_streak, ride_load
from ..stats.overview import DISTANCE_BUCKETS, Row, _bucket, get_tz, local, streaks

log = logging.getLogger("bikehelper.groups")
router = APIRouter(prefix="/api/groups", tags=["groups"])

# Bereiche, die ein Mitglied zusätzlich zu den Grundwerten (Kilometer, Höhenmeter, Zeit, Fahrten, Tempo) freigeben kann.
# Es sind nur Summen und Verteilungen. Nie geteilt werden Strecken, Orte, Karten, Räder, Wartung, Fahrtnamen oder Ziele.
CATEGORIES = {
    "rhythm": ("Fahrrhythmus", "Wochentage, Tageszeiten und Streckenlängen als Verteilung"),
    "records": ("Rekorde", "längste Fahrt, meiste Höhenmeter, bester Tag, schnellster Schnitt und Serien, ohne Datum und Namen"),
    "load": ("Belastung und Form", "geschätzt aus Fahrzeit, Höhenmetern und Tempo"),
    "weather": ("Wetter", "Kilometer bei Regen, Durchschnittstemperatur, kälteste und wärmste Fahrt, ohne Orte"),
}
MAX_GROUPS_PER_USER = 10
MAX_MEMBERS = 50
MAX_PENDING_INVITES = 30
INVITE_DAYS = 14
LINK_DAYS = 30
PERIODS = ("week", "month", "year", "all")
METRICS = ("km", "elev_m", "time_s", "rides", "avg_speed", "longest_km", "active_days", "rides_per_week", "improve_pct")


class GroupIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    display_name: str = Field(min_length=1, max_length=60)
    shared: list[str] = []


class RenameIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=255)


class JoinIn(BaseModel):
    token: str
    display_name: str = Field(min_length=1, max_length=60)
    share: bool = True
    shared: list[str] = []


class MeIn(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=60)
    share: bool | None = None
    shared: list[str] | None = None


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


def _cats(values: list[str]) -> str:
    bad = [v for v in values if v not in CATEGORIES]
    if bad:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannter Bereich zum Teilen")
    return ",".join(c for c in CATEGORIES if c in values)  # feste Reihenfolge, keine Doppelten


def _shared(m: GroupMember) -> list[str]:
    return [c for c in (m.shared or "").split(",") if c in CATEGORIES]


@dataclass
class _Mem:
    """Mitglied einer Gruppe, lokal (uid = Nutzer-ID) oder von einem anderen Server (uid = negative ID des externen Mitglieds)."""
    uid: int
    display_name: str
    share: bool
    shared: str | None
    remote: bool = False
    role: str = "member"
    origin: str | None = None


def _members(db: Session, group_id: int) -> list[_Mem]:
    out = [_Mem(m.user_id, m.display_name, m.share, m.shared, False, m.role)
           for m in db.scalars(select(GroupMember).where(GroupMember.group_id == group_id))]
    out += [_Mem(-r.id, r.display_name, r.share, None, True, "member", r.origin)
            for r in db.scalars(select(RemoteMember).where(RemoteMember.group_id == group_id))]
    return out


def _drop_remote(db: Session, group_id: int) -> None:
    ids = db.scalars(select(RemoteMember.id).where(RemoteMember.group_id == group_id)).all()
    if ids:
        db.execute(delete(RemoteDay).where(RemoteDay.member_id.in_(ids)))
        db.execute(delete(RemoteMember).where(RemoteMember.group_id == group_id))


def _remote(db: Session, user: User, group_id: int, method: str, path: str, *, params: dict | None = None, json: dict | None = None):
    """Gruppe auf einem anderen Server: Anfrage an den Gastgeber weiterreichen."""
    ms = fed.membership(db, user.id, group_id)
    if ms is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gruppe nicht gefunden")
    try:
        return fed.call(ms.host_url, method, path, key=ms.member_key, params=params, json=json)
    except fed.FederationError as e:
        if e.status_code in (401, 404):
            ms.last_error = "Der Gastgeber kennt dich nicht mehr. Du wurdest entfernt oder die Gruppe gibt es nicht mehr."
            db.commit()
            raise HTTPException(status.HTTP_502_BAD_GATEWAY, ms.last_error)
        raise HTTPException(e.status_code if e.status_code in (409, 422) else status.HTTP_502_BAD_GATEWAY, e.message)


def _clean(name: str) -> str:
    n = " ".join(name.split())
    if not n:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Der Name darf nicht leer sein")
    return n


def _unique_name(db: Session, group_id: int, name: str, except_user: int | None = None, except_remote: int | None = None) -> None:
    q = select(GroupMember.user_id).where(GroupMember.group_id == group_id, func.lower(GroupMember.display_name) == name.lower())
    if except_user is not None:
        q = q.where(GroupMember.user_id != except_user)
    q2 = select(RemoteMember.id).where(RemoteMember.group_id == group_id, func.lower(RemoteMember.display_name) == name.lower())
    if except_remote is not None:
        q2 = q2.where(RemoteMember.id != except_remote)
    if db.scalar(q) is not None or db.scalar(q2) is not None:
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
    fed.leave_all(db, user_id)
    gids = db.scalars(select(GroupMember.group_id).where(GroupMember.user_id == user_id)).all()
    db.execute(delete(GroupMember).where(GroupMember.user_id == user_id))
    db.flush()
    for gid in gids:
        rest = db.scalars(select(GroupMember).where(GroupMember.group_id == gid).order_by(GroupMember.joined_at, GroupMember.user_id)).all()
        if not rest:
            _drop_remote(db, gid)
            db.execute(delete(GroupInvite).where(GroupInvite.group_id == gid))
            db.execute(delete(GroupGoal).where(GroupGoal.group_id == gid))
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
    for gid, n in db.execute(select(RemoteMember.group_id, func.count()).group_by(RemoteMember.group_id)).all():
        counts[gid] = counts.get(gid, 0) + n
    out = [{"id": g.id, "name": g.name, "role": m.role, "members": counts.get(g.id, 0), "share": m.share, "remote": False} for g, m in rows]
    for ms in db.scalars(select(RemoteMembership).where(RemoteMembership.user_id == user.id).order_by(RemoteMembership.group_name)):
        out.append({"id": fed.REMOTE_BASE + ms.id, "name": ms.group_name, "role": "member", "members": ms.members or 0, "share": ms.share,
                    "remote": True, "host": fed.host_label(ms), "error": ms.last_error})
    return out


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
    db.add(GroupMember(group_id=g.id, user_id=user.id, role="admin", display_name=_clean(data.display_name), share=True, shared=_cats(data.shared)))
    db.commit()
    return {"id": g.id}


@router.get("/join/{token}")
def preview_invite(token: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    inv = db.scalar(select(GroupInvite).where(GroupInvite.token == token))
    if inv is None or not _fresh(inv):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Die Einladung ist ungültig oder abgelaufen")
    g = db.get(Group, inv.group_id)
    return {"group": g.name, "already_member": db.get(GroupMember, (g.id, user.id)) is not None,
            "categories": [{"key": k, "label": v[0], "text": v[1]} for k, v in CATEGORIES.items()]}


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
    if len(_members(db, gid)) >= MAX_MEMBERS:
        raise HTTPException(status.HTTP_409_CONFLICT, "Die Gruppe ist voll")
    if db.scalar(select(func.count()).select_from(GroupMember).where(GroupMember.user_id == user.id)) >= MAX_GROUPS_PER_USER:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Mehr als {MAX_GROUPS_PER_USER} Gruppen sind nicht möglich")
    name = _clean(data.display_name)
    cats = _cats(data.shared)
    _unique_name(db, gid, name)
    db.add(GroupMember(group_id=gid, user_id=user.id, role="member", display_name=name, share=data.share, shared=cats))
    if not inv.multi:
        db.delete(inv)  # persönliche Einladungen sind einmal gültig, der Gruppenlink bleibt
    db.commit()
    return {"id": gid}


@router.get("/{group_id}")
def group_info(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if fed.is_remote_id(group_id):
        info = _remote(db, user, group_id, "GET", "/info")
        ms = fed.membership(db, user.id, group_id)
        return {**info, "id": group_id, "remote": True, "host": fed.host_label(ms), "last_sync_at": ms.last_sync_at.isoformat() + "Z" if ms.last_sync_at else None,
                "error": ms.last_error, "display_name": ms.display_name, "share": ms.share}
    me = _member(db, group_id, user)
    return _info(db, group_id, me.role, me.display_name, me.share, _shared(me), user.id, is_local=True)


def _info(db: Session, group_id: int, role: str, display_name: str, share: bool, shared: list[str], me_uid: int, *, is_local: bool) -> dict:
    """Gruppenübersicht. Für Mitglieder von anderen Servern (is_local False) ohne Einladungen und Mailfunktion."""
    g = db.get(Group, group_id)
    members = sorted(_members(db, group_id), key=lambda m: m.display_name.lower())
    out = {
        "id": g.id, "name": g.name, "role": role, "display_name": display_name, "share": share, "shared": shared,
        "categories": [{"key": k, "label": v[0], "text": v[1]} for k, v in CATEGORIES.items()] if is_local else [],
        "members": [{"user_id": m.uid, "display_name": m.display_name, "role": m.role, "share": m.share, "shared": [] if m.remote else _shared(m),
                     "is_me": m.uid == me_uid, "remote": m.remote} for m in members],
        "invites": [],
        "mail_enabled": notify.smtp_configured() if is_local else False,
    }
    if not is_local or role != "admin":
        return out
    invs = db.scalars(select(GroupInvite).where(GroupInvite.group_id == group_id).order_by(GroupInvite.id.desc())).all()
    out["invites"] = [{"id": i.id, "email": i.email, "expired": not _fresh(i)} for i in invs if not i.multi]
    link = next((i for i in invs if i.multi and _fresh(i)), None)
    out["invite_link"] = f"{settings.public_url.rstrip('/')}/groups/join/{link.token}" if link else None
    out["federation"] = settings.federation_enabled
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
    _drop_remote(db, group_id)
    db.execute(delete(GroupInvite).where(GroupInvite.group_id == group_id))
    db.execute(delete(GroupMember).where(GroupMember.group_id == group_id))
    db.execute(delete(GroupGoal).where(GroupGoal.group_id == group_id))
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
    if fed.is_remote_id(group_id):
        return _update_remote_me(db, user, group_id, data)
    m = _member(db, group_id, user)
    if data.display_name is not None:
        name = _clean(data.display_name)
        _unique_name(db, group_id, name, except_user=user.id)
        m.display_name = name
    if data.share is not None:
        m.share = data.share
    if data.shared is not None:
        m.shared = _cats(data.shared)
    db.commit()
    return {"ok": True}


def _update_remote_me(db: Session, user: User, group_id: int, data: MeIn) -> dict:
    ms = fed.membership(db, user.id, group_id)
    if ms is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Gruppe nicht gefunden")
    body: dict = {}
    if data.display_name is not None:
        body["display_name"] = _clean(data.display_name)
    if data.share is not None:
        body["share"] = data.share
    if body:
        _remote(db, user, group_id, "PUT", "/me", json=body)  # der Gastgeber prüft den Namen (eindeutig in der Gruppe)
        ms.display_name = body.get("display_name", ms.display_name)
        ms.share = body.get("share", ms.share)
        db.commit()
        fed.trigger(user.id)
    return {"ok": True}


@router.delete("/{group_id}/me", status_code=204)
def leave(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if fed.is_remote_id(group_id):
        ms = fed.membership(db, user.id, group_id)
        if ms is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Gruppe nicht gefunden")
        try:
            fed.call(ms.host_url, "DELETE", "/leave", key=ms.member_key)
        except fed.FederationError as e:
            log.info("Austritt beim Gastgeber nicht bestätigt: %s", e.message)  # lokal wird trotzdem ausgetreten
        db.delete(ms)
        db.commit()
        return
    m = _member(db, group_id, user)
    others = len(_members(db, group_id)) - 1
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
    if member_id < 0:
        raise HTTPException(status.HTTP_409_CONFLICT, "Mitglieder von anderen Servern können nicht Administrator werden")
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
    if member_id < 0:
        rm = db.get(RemoteMember, -member_id)
        if rm is not None and rm.group_id == group_id:
            db.execute(delete(RemoteDay).where(RemoteDay.member_id == rm.id))
            db.delete(rm)
        db.commit()
        return
    db.execute(delete(GroupMember).where(GroupMember.group_id == group_id, GroupMember.user_id == member_id))
    db.commit()


# ---------- Ranglisten ----------

MONTHS = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
MONTH_NAMES = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August", "September", "Oktober", "November", "Dezember"]


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
        return start, end, f"{MONTH_NAMES[m]} {y}"
    if period == "year":
        y = today.year + offset
        return date(y, 1, 1), date(y + 1, 1, 1), str(y)
    return None, None, "Gesamt"


def _totals(rs: list[Row]) -> dict:
    km = sum(r.km for r in rs)
    secs = sum(r.time_s for r in rs)
    days = {r.day for r in rs}
    return {
        "km": round(km, 1), "elev_m": round(sum(r.elev_m or 0 for r in rs)), "time_s": secs, "rides": len(rs),
        "avg_speed": round(km / (secs / 3600), 1) if secs >= 600 and km > 0 else None,
        "longest_km": round(max((r.km for r in rs), default=0.0), 1), "active_days": len(days),
    }


class _R(Row):
    """Row mit lokalem Tag und lokaler Uhrzeit (day, hour, start_local), damit nicht überall neu umgerechnet wird."""


def current_week_streak(days: set[date], today: date) -> int:
    """Wochen in Folge mit mindestens einer Fahrt, bis zur aktuellen Woche. Hat die aktuelle Woche noch keine Fahrt, zählt die Serie bis letzte Woche."""
    weeks = {d - timedelta(days=d.weekday()) for d in days}
    w = today - timedelta(days=today.weekday())
    if w not in weeks:
        w -= timedelta(weeks=1)
    n = 0
    while w in weeks:
        n += 1
        w -= timedelta(weeks=1)
    return n


def rides_per_week(rides: int, first: date | None, last: date) -> float | None:
    """Fahrten je Woche über die bisher vergangene Zeit des Zeitraums (mindestens eine Woche gerechnet)."""
    if first is None or rides == 0:
        return None
    weeks = max(1.0, ((last - first).days + 1) / 7)
    return round(rides / weeks, 1)


def improvement_pct(now_km: float, before_km: float) -> float | None:
    """Veränderung der Kilometer gegenüber dem Zeitraum davor in Prozent; erst ab 5 km davor aussagekräftig."""
    if before_km < 5:
        return None
    return round((now_km / before_km - 1) * 100, 1)


def crossed_milestone(before_km: float, after_km: float) -> int | None:
    """Höchste Kilometermarke, die zwischen zwei Ständen überschritten wurde."""
    hit = [m for m in MILESTONES if before_km < m <= after_km]
    return hit[-1] if hit else None


def _extras(cats: list[str], period_rows: list, all_rows: list, end: date, tz) -> dict:
    """Nur die Bereiche, die das Mitglied freigegeben hat. Summen und Verteilungen, keine einzelnen Fahrten."""
    out: dict = {}
    if "rhythm" in cats:
        wd = [0.0] * 7
        dp = {label: 0.0 for _, _, label in DAYPARTS}
        dist = {label: 0 for _, _, label in DISTANCE_BUCKETS}
        for r in period_rows:
            wd[r.day.weekday()] += r.km
            for lo, hi, label in DAYPARTS:
                if lo <= r.hour < hi:
                    dp[label] += r.time_s / 3600
                    break
            b = _bucket(r.km, DISTANCE_BUCKETS)
            if b:
                dist[b] += 1
        out["rhythm"] = {"weekdays": [round(v, 1) for v in wd], "dayparts": [{"label": k, "hours": round(v, 1)} for k, v in dp.items()],
                         "distances": [{"label": k, "rides": v} for k, v in dist.items()]}
    if "records" in cats:
        days = {r.day for r in period_rows}
        per_day: dict[date, float] = {}
        for r in period_rows:
            per_day[r.day] = per_day.get(r.day, 0.0) + r.km
        fast = [r for r in period_rows if r.time_s > 600 and r.km >= 10]
        out["records"] = {
            "longest_km": round(max((r.km for r in period_rows), default=0.0), 1),
            "most_climb_m": round(max((r.elev_m or 0 for r in period_rows), default=0)),
            "best_day_km": round(max(per_day.values(), default=0.0), 1),
            "fastest_avg": round(max((r.km / (r.time_s / 3600) for r in fast), default=0.0), 1) or None,
            "day_streak": streaks(days, end)[0],
            "week_streak": longest_week_streak(days),
            "week_streak_now": current_week_streak({r.day for r in all_rows if r.day <= end}, end),
        }
    if "load" in cats:
        series = load_series([(r.start_local, r) for r in all_rows if r.day <= end], end)
        now = series[-1] if series else None
        out["load"] = {
            "fitness": now["fitness"] if now else None, "fatigue": now["fatigue"] if now else None, "form": now["form"] if now else None,
            "period_load": round(sum(ride_load(r) for r in period_rows)),
        }
    if "weather" in cats:
        wx = [r for r in period_rows if r.weather_status in ("ok", "prelim") and r.temp_c is not None]
        wet = [r for r in period_rows if r.wet_minutes is not None and r.time_s > 0]
        wet_km = sum(r.km * min(1.0, r.wet_minutes * 60 / r.time_s) for r in wet)
        base = sum(r.km for r in wet)
        out["weather"] = {
            "avg_temp": round(sum(r.temp_c for r in wx) / len(wx), 1) if wx else None,
            "wet_km": round(wet_km, 1), "wet_share": round(wet_km / base * 100) if base else None,
            "rainy_rides": sum(1 for r in wet if r.wet_minutes >= 5),
            "coldest": min((r.temp_c for r in wx), default=None), "hottest": max((r.temp_c for r in wx), default=None),
        }
    return out


def _rows_from_days(days) -> list[_R]:
    """Tageswerte eines externen Mitglieds als einzelne Fahrten, damit die bestehende Auswertung unverändert rechnet. Die Summen
    (Kilometer, Zeit, Höhenmeter, Fahrten) und die längste Fahrt stimmen; die Uhrzeit ist mittags angenommen."""
    out: list[_R] = []
    for d in days:
        n = max(1, d.rides or 1)
        total = max(0.0, d.km or 0.0)
        longest = min(total, max(d.longest_km or 0.0, total / n)) if n > 1 else total
        kms = [longest] + [(total - longest) / (n - 1)] * (n - 1) if n > 1 else [total]
        t_left, e_left = int(d.time_s or 0), float(d.elev_m or 0.0)
        for i, km in enumerate(kms):
            frac = km / total if total > 0 else 1.0 / n
            last = i == n - 1
            secs = t_left if last else min(t_left, round((d.time_s or 0) * frac))
            elev = e_left if last else min(e_left, (d.elev_m or 0.0) * frac)
            t_left -= secs
            e_left -= elev
            start = datetime.combine(d.day, time(12))
            r = _R(id=0, name="", bike_id=None, start=start, km=km, time_s=secs, elev_m=elev)
            r.day, r.hour, r.start_local = d.day, 12, start
            out.append(r)
    return out


def _load_rows(db: Session, sharing: dict[int, _Mem], tz) -> dict[int, list[_R]]:
    rows_by_user: dict[int, list[_R]] = {uid: [] for uid in sharing}
    local_ids = [uid for uid in sharing if uid > 0]
    if local_ids:
        q = select(Activity.user_id, Activity.start_date, Activity.distance_km, Activity.moving_time_s, Activity.elevation_m,
                   Activity.temp_c, Activity.precip_mm, Activity.wet_minutes, Activity.weather_status).where(Activity.user_id.in_(local_ids))
        for uid, start, km, secs, elev, temp, precip, wetm, wstat in db.execute(q):
            ldt = local(start, tz)
            r = _R(id=0, name="", bike_id=None, start=start, km=km or 0.0, time_s=secs or 0, elev_m=elev or 0.0,
                   temp_c=temp, precip_mm=precip, wet_minutes=wetm, weather_status=wstat)
            r.day, r.hour, r.start_local = ldt.date(), ldt.hour, ldt
            rows_by_user[uid].append(r)
    remote_ids = [-uid for uid in sharing if uid < 0]
    if remote_ids:
        by_member: dict[int, list[RemoteDay]] = {}
        for d in db.scalars(select(RemoteDay).where(RemoteDay.member_id.in_(remote_ids))):
            by_member.setdefault(d.member_id, []).append(d)
        for mid, days in by_member.items():
            rows_by_user[-mid] = _rows_from_days(days)
    return rows_by_user


@router.get("/{group_id}/stats")
def group_stats(group_id: int, period: str = "week", offset: int = 0, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if fed.is_remote_id(group_id):
        return _remote(db, user, group_id, "GET", "/stats", params={"period": period, "offset": offset})
    _member(db, group_id, user)
    return compute_stats(db, group_id, period, offset, user.id)


def compute_stats(db: Session, group_id: int, period: str, offset: int, me_uid: int) -> dict:
    """Rangliste und Verlauf einer Gruppe. me_uid markiert die Zeile des Betrachters (Nutzer-ID, bei externen Mitgliedern negativ)."""
    if period not in PERIODS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannter Zeitraum")
    offset = min(0, max(-520, offset))
    tz = get_tz(settings.timezone)
    today = local(datetime.now(timezone.utc).replace(tzinfo=None), tz).date()
    lo, hi, label = _bounds(period, offset, today)
    plo, phi, _ = _bounds(period, offset - 1, today) if period != "all" else (None, None, "")
    members = _members(db, group_id)
    sharing = {m.uid: m for m in members if m.share}

    # Beschriftung und Zuordnung der Verlaufspunkte (Tage, Monate oder Jahre, je nach Zeitraum)
    if period == "week":
        labels = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
    elif period == "month":
        labels = [str(i + 1) for i in range((hi - lo).days)]
    elif period == "year":
        labels = MONTHS
    else:
        labels = []

    def slot(d: date) -> int | None:
        if period == "week":
            return (d - lo).days
        if period == "month":
            return (d - lo).days
        if period == "year":
            return d.month - 1
        return d.year

    rows_by_user = _load_rows(db, sharing, tz)

    def within(rs, a, b):
        return [r for r in rs if (a is None or r.day >= a) and (b is None or r.day < b)]

    result, series_raw, all_years = [], {}, set()
    for uid, m in sharing.items():
        rs = rows_by_user[uid]
        cur = within(rs, lo, hi)
        row = {"user_id": uid, "display_name": m.display_name, "is_me": uid == me_uid, **_totals(cur), "shared": [] if m.remote else _shared(m), "remote": m.remote}
        if period != "all":
            row["prev"] = {k: v for k, v in _totals(within(rs, plo, phi)).items() if k in ("km", "elev_m", "time_s", "rides")}
        end_day = min(today, (hi - timedelta(days=1)) if hi else today)
        row["extras"] = {} if m.remote else _extras(_shared(m), cur, rs, end_day, tz)  # Zusatzbereiche gibt es für externe Mitglieder noch nicht
        first_day = lo if lo else min((r.day for r in cur), default=None)
        row["rides_per_week"] = rides_per_week(len(cur), first_day, end_day)
        if period != "all":
            row["improve_pct"] = improvement_pct(row["km"], row["prev"]["km"])
            before = sum(r.km for r in rs if r.day < lo)
            row["milestone"] = crossed_milestone(before, before + row["km"])
        else:
            row["improve_pct"] = None
            row["milestone"] = None
        result.append(row)
        pts: dict[int, float] = {}
        for r in cur:
            k = slot(r.day)
            pts[k] = pts.get(k, 0.0) + r.km
        series_raw[uid] = pts
        all_years |= set(pts) if period == "all" else set()

    if period == "all":
        first = min(all_years, default=today.year)
        years = list(range(max(first, today.year - 11), today.year + 1))
        labels = [str(y) for y in years]
        slots = years
    else:
        slots = list(range(len(labels)))

    for r in result:  # Rang je Kennzahl, 1 = bester; gleiche Werte teilen sich den Rang; leere Werte zählen nicht
        r["rank"] = {}
    for metric in METRICS:
        vals = sorted({r[metric] for r in result if r[metric] and (metric != "improve_pct" or r[metric] > 0)}, reverse=True)
        for r in result:
            r["rank"][metric] = vals.index(r[metric]) + 1 if r[metric] in vals else None
    result.sort(key=lambda r: (-(r["km"] or 0), r["display_name"].lower()))
    return {
        "period": period, "offset": offset, "label": label,
        "can_next": period != "all" and offset < 0, "can_prev": period != "all",
        "rows": result,
        "categories": [{"key": k, "label": v[0], "text": v[1]} for k, v in CATEGORIES.items()],
        "not_sharing": sorted(m.display_name for m in members if not m.share),
        "has_remote": any(m.remote for m in members),
        "series": {"labels": labels,
                   "members": [{"display_name": r["display_name"], "is_me": r["is_me"],
                                "km": [round(series_raw[r["user_id"]].get(k, 0.0), 1) for k in slots]} for r in result]},
    }


# ---------- Gemeinsames Ziel ----------

GOAL_METRICS = {"km": "Kilometer", "elev_m": "Höhenmeter", "rides": "Fahrten"}


class GoalIn(BaseModel):
    metric: str
    target: float = Field(gt=0, le=10_000_000)
    start: date
    end: date
    title: str | None = Field(default=None, max_length=80)


def goal_progress(goal: GroupGoal, daily: dict[str, dict[date, float]], names: dict[int, str], today: date) -> dict:
    """Stand des Gruppenziels aus Tageswerten je Mitglied (user_id als Schlüssel in `daily`, Namen in `names`)."""
    total_days = (goal.end - goal.start).days + 1
    upto = min(today, goal.end)
    elapsed = max(0, (upto - goal.start).days + 1)
    per_member = {uid: sum(v for d, v in days.items() if goal.start <= d <= upto) for uid, days in daily.items()}
    done = sum(per_member.values())
    series, acc = [], 0.0
    for i in range(elapsed):
        d = goal.start + timedelta(days=i)
        acc += sum(days.get(d, 0.0) for days in daily.values())
        series.append(round(acc, 1))
    projected = done / elapsed * total_days if elapsed else 0.0
    return {
        "metric": goal.metric, "metric_label": GOAL_METRICS.get(goal.metric, goal.metric), "target": goal.target,
        "title": goal.title, "start": goal.start.isoformat(), "end": goal.end.isoformat(),
        "done": round(done, 1), "percent": round(min(999.0, done / goal.target * 100), 1),
        "days_total": total_days, "days_elapsed": elapsed, "days_left": max(0, (goal.end - today).days),
        "series": series, "expected_per_day": round(goal.target / total_days, 2),
        "projected": round(projected), "on_track": projected >= goal.target or done >= goal.target,
        "finished": done >= goal.target, "over": today > goal.end,
        "members": sorted(
            ({"display_name": names[uid], "value": round(v, 1)} for uid, v in per_member.items() if uid in names),
            key=lambda x: -x["value"],
        ),
    }


def _goal_daily(db: Session, goal: GroupGoal, sharing: dict[int, _Mem], tz) -> dict[int, dict[date, float]]:
    daily: dict[int, dict[date, float]] = {uid: {} for uid in sharing}
    if not sharing:
        return daily
    local_ids = [uid for uid in sharing if uid > 0]
    if local_ids:
        lo = datetime.combine(goal.start - timedelta(days=1), datetime.min.time())
        hi = datetime.combine(goal.end + timedelta(days=2), datetime.min.time())
        q = select(Activity.user_id, Activity.start_date, Activity.distance_km, Activity.elevation_m).where(
            Activity.user_id.in_(local_ids), Activity.start_date >= lo, Activity.start_date < hi)
        for uid, start, km, elev in db.execute(q):
            d = local(start, tz).date()
            value = {"km": km or 0.0, "elev_m": elev or 0.0, "rides": 1.0}[goal.metric]
            daily[uid][d] = daily[uid].get(d, 0.0) + value
    remote_ids = [-uid for uid in sharing if uid < 0]
    if remote_ids:
        q2 = select(RemoteDay).where(RemoteDay.member_id.in_(remote_ids), RemoteDay.day >= goal.start, RemoteDay.day <= goal.end)
        for rd in db.scalars(q2):
            value = {"km": rd.km or 0.0, "elev_m": rd.elev_m or 0.0, "rides": float(rd.rides or 0)}[goal.metric]
            daily[-rd.member_id][rd.day] = value
    return daily


@router.get("/{group_id}/goal")
def get_goal(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if fed.is_remote_id(group_id):
        return _remote(db, user, group_id, "GET", "/goal")
    _member(db, group_id, user)
    return goal_state(db, group_id)


def goal_state(db: Session, group_id: int) -> dict:
    goal = db.scalar(select(GroupGoal).where(GroupGoal.group_id == group_id))
    if goal is None:
        return {"goal": None}
    tz = get_tz(settings.timezone)
    today = local(datetime.now(timezone.utc).replace(tzinfo=None), tz).date()
    members = [m for m in _members(db, group_id) if m.share]
    sharing = {m.uid: m for m in members}
    names = {m.uid: m.display_name for m in members}
    return {"goal": goal_progress(goal, _goal_daily(db, goal, sharing, tz), names, today)}


@router.put("/{group_id}/goal")
def set_goal(group_id: int, data: GoalIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _admin(db, group_id, user)
    if data.metric not in GOAL_METRICS:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Unbekannte Kennzahl für das Ziel")
    if data.end < data.start or (data.end - data.start).days > 800:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Das Ende muss nach dem Start liegen, höchstens 800 Tage.")
    goal = db.scalar(select(GroupGoal).where(GroupGoal.group_id == group_id))
    title = (data.title or "").strip() or None
    if goal is None:
        db.add(GroupGoal(group_id=group_id, metric=data.metric, target=data.target, start=data.start, end=data.end, title=title))
    else:
        goal.metric, goal.target, goal.start, goal.end, goal.title = data.metric, data.target, data.start, data.end, title
    db.commit()
    return get_goal(group_id, user, db)


@router.delete("/{group_id}/goal", status_code=204)
def delete_goal(group_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    _admin(db, group_id, user)
    db.execute(delete(GroupGoal).where(GroupGoal.group_id == group_id))
    db.commit()


# ---------- Duell ----------

@router.get("/{group_id}/duel")
def duel(group_id: int, a: int, b: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Zwei Mitglieder im direkten Vergleich über die letzten 12 Wochen. Nur wer teilt, kann verglichen werden."""
    if fed.is_remote_id(group_id):
        return _remote(db, user, group_id, "GET", "/duel", params={"a": a, "b": b})
    _member(db, group_id, user)
    return compute_duel(db, group_id, a, b, user.id)


def compute_duel(db: Session, group_id: int, a: int, b: int, me_uid: int) -> dict:
    if a == b:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Bitte zwei verschiedene Mitglieder wählen.")
    members = {m.uid: m for m in _members(db, group_id) if m.uid in (a, b)}
    if a not in members or b not in members:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Mitglied nicht gefunden")
    if not (members[a].share and members[b].share):
        raise HTTPException(status.HTTP_409_CONFLICT, "Eines der Mitglieder teilt seine Kennzahlen gerade nicht.")
    tz = get_tz(settings.timezone)
    today = local(datetime.now(timezone.utc).replace(tzinfo=None), tz).date()
    first = today - timedelta(days=today.weekday()) - timedelta(weeks=11)
    since = datetime.combine(first - timedelta(days=1), datetime.min.time())
    weeks = [first + timedelta(weeks=i) for i in range(12)]
    acc = {uid: {w: {"km": 0.0, "elev_m": 0.0, "rides": 0, "time_s": 0} for w in weeks} for uid in (a, b)}

    def add(uid: int, d: date, km: float, elev: float, rides: int, secs: int) -> None:
        w = d - timedelta(days=d.weekday())
        if w in acc[uid]:
            x = acc[uid][w]
            x["km"] += km or 0.0
            x["elev_m"] += elev or 0.0
            x["rides"] += rides
            x["time_s"] += secs or 0

    local_ids = [uid for uid in (a, b) if uid > 0]
    if local_ids:
        q = select(Activity.user_id, Activity.start_date, Activity.distance_km, Activity.elevation_m, Activity.moving_time_s).where(
            Activity.user_id.in_(local_ids), Activity.start_date >= since)
        for uid, start, km, elev, secs in db.execute(q):
            add(uid, local(start, tz).date(), km, elev, 1, secs)
    remote_ids = [-uid for uid in (a, b) if uid < 0]
    if remote_ids:
        for rd in db.scalars(select(RemoteDay).where(RemoteDay.member_id.in_(remote_ids), RemoteDay.day >= first)):
            add(-rd.member_id, rd.day, rd.km, rd.elev_m, rd.rides or 0, rd.time_s)
    out = {}
    for uid in (a, b):
        tot = {k: sum(acc[uid][w][k] for w in weeks) for k in ("km", "elev_m", "rides", "time_s")}
        out[uid] = {"display_name": members[uid].display_name, "is_me": uid == me_uid,
                    "km_by_week": [round(acc[uid][w]["km"], 1) for w in weeks],
                    "totals": {"km": round(tot["km"], 1), "elev_m": round(tot["elev_m"]), "rides": int(tot["rides"]), "time_s": int(tot["time_s"]),
                               "avg_speed": round(tot["km"] / (tot["time_s"] / 3600), 1) if tot["time_s"] >= 600 else None}}
    won_a = sum(1 for w in weeks if acc[a][w]["km"] > acc[b][w]["km"])
    won_b = sum(1 for w in weeks if acc[b][w]["km"] > acc[a][w]["km"])
    return {"weeks": [w.isoformat() for w in weeks], "a": out[a], "b": out[b], "weeks_won": {"a": won_a, "b": won_b, "draw": 12 - won_a - won_b}}
