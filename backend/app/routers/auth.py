from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from .. import audit, notify
from ..config import settings
from ..database import get_db
from .. import ratelimit
from ..models import (
    IntervalsSeen, MechanicGrant,
    Activity, Bike, Component, Goal, GeoState, InventoryItem, Invite, PasswordReset, PlaceVisit, RuleNotice, TireSet, User, UserTire, WahooSeen,
)
from ..schemas import LoginIn, PasswordChangeIn, PasswordConfirmIn, RegisterIn, StravaSettingsIn, TokenOut, UserOut
from ..security import create_token, current_user, hash_password, is_admin, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


# Hinweis „Neu“, der einmal pro Konto nach der Anmeldung erscheint. Zum nächsten Hinweis die Kennung ändern.
CURRENT_WHATSNEW = "intervals-2026-10"


def _user_out(u: User, admin: bool = False) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        strava_configured=bool(u.strava_client_id and u.strava_client_secret),
        strava_connected=bool(u.strava_refresh_token),
        weight_kg=u.weight_kg,
        is_admin=admin,
        role="admin" if admin else "user",
        mechanic_enabled=bool(u.mechanic_enabled),
        whatsnew=CURRENT_WHATSNEW if u.whatsnew_seen != CURRENT_WHATSNEW else None,
    )


# Für Anmeldungen mit unbekannter E-Mail wird trotzdem ein Hash geprüft, damit die Antwortzeit nichts verrät
_DUMMY_HASH = hash_password("dummy-password-for-timing")


@router.get("/frame-policy", include_in_schema=False)
def frame_policy():
    """Fragt der Webserver bei jedem Seitenaufruf ab: Wer darf BikeHelper einbetten? Leer = niemand."""
    value = settings.frame_ancestors.strip()
    return Response(status_code=204, headers={"X-BH-Frame-Ancestors": "'self' " + value} if value else {})


@router.get("/config")
def public_config():
    return {"allow_registration": settings.allow_registration, "invites": True, "password_reset": notify.smtp_configured()}


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, request: Request, db: Session = Depends(get_db)):
    ratelimit.check_register(ratelimit.client_ip(request))
    first_user = db.scalar(select(User.id).limit(1)) is None
    invite = None
    if not first_user and not settings.allow_registration:
        code = (data.invite or "").strip().upper()
        invite = db.scalar(select(Invite).where(Invite.code == code, Invite.used_at.is_(None))) if code else None
        if invite is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Registrierung nur mit gültigem Einladungscode")
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "E-Mail bereits vergeben")
    user = User(email=email, password_hash=hash_password(data.password), token_version=0,
                role="admin" if first_user else "user", active=True,
                whatsnew_seen=CURRENT_WHATSNEW)  # neue Konten brauchen den Hinweis nicht
    db.add(user)
    if invite is not None:
        invite.used_by_email, invite.used_at = email, datetime.utcnow()
    db.commit()
    if invite is not None:
        audit.record(db, email, "user.register", f"Einladung {invite.code}")
    return TokenOut(access_token=create_token(user))


@router.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, request: Request, db: Session = Depends(get_db)):
    email, ip = data.email.lower(), ratelimit.client_ip(request)
    ratelimit.check_login(email, ip)
    user = db.scalar(select(User).where(User.email == email))
    ok = verify_password(data.password, user.password_hash if user else _DUMMY_HASH)
    if not user or not ok:
        ratelimit.record_failure(email, ip)
        audit.event(email, "login.fail", "E-Mail oder Passwort falsch" if user else "unbekanntes Konto")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-Mail oder Passwort falsch")
    ratelimit.record_success(email)
    if user.active is False:
        audit.event(email, "login.blocked", "Konto gesperrt")
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Dieses Konto ist gesperrt. Bitte wende dich an den Administrator.")
    audit.event(email, "login")
    return TokenOut(access_token=create_token(user))


def _check_password(user: User, password: str, request: Request) -> None:
    """Prüft das Passwort für heikle Aktionen; zählt Fehlversuche mit. 403 statt 401, damit die App nicht abmeldet."""
    ip = ratelimit.client_ip(request)
    ratelimit.check_login(user.email, ip)
    if not verify_password(password, user.password_hash):
        ratelimit.record_failure(user.email, ip)
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Passwort falsch")


@router.put("/auth/password", response_model=TokenOut)
def change_password(data: PasswordChangeIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Ändert das Passwort und meldet alle anderen Geräte ab; das aktuelle bekommt einen neuen Token."""
    _check_password(user, data.current_password, request)
    user.password_hash = hash_password(data.new_password)
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return TokenOut(access_token=create_token(user))


@router.post("/auth/logout-all", response_model=TokenOut)
def logout_all(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Macht alle bisherigen Tokens ungültig (alle Geräte). Das aufrufende Gerät bekommt einen neuen Token."""
    user.token_version = (user.token_version or 0) + 1
    db.commit()
    return TokenOut(access_token=create_token(user))


def _admin_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(User).where(User.role == "admin")) or 0


def delete_user_data(db: Session, user: User) -> None:
    """Entfernt ein Konto samt allen Daten (Räder, Komponenten, Fahrten, Inventar, Ziele …)."""
    uid = user.id
    comps = db.scalars(select(Component).where(Component.user_id == uid)).all()
    rule_ids = [r.id for c in comps for r in c.rules]
    if rule_ids:
        db.execute(delete(RuleNotice).where(RuleNotice.rule_id.in_(rule_ids)))
    for obj in [*comps, *db.scalars(select(TireSet).where(TireSet.user_id == uid)).all()]:
        db.delete(obj)  # Regeln, Wartungseinträge, Messungen, Montagen laufen über die Kaskade mit
    db.flush()
    db.execute(delete(PasswordReset).where(PasswordReset.user_id == uid))
    db.execute(delete(MechanicGrant).where((MechanicGrant.owner_id == uid) | (MechanicGrant.mechanic_id == uid)))
    for model in (Activity, Goal, InventoryItem, PlaceVisit, GeoState, WahooSeen, IntervalsSeen, UserTire, Bike):
        db.execute(delete(model).where(model.user_id == uid))
    db.delete(user)
    db.commit()


@router.post("/me/delete", status_code=204)
def delete_account(data: PasswordConfirmIn, request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Löscht das Konto samt allen Daten. Nicht rückgängig zu machen."""
    _check_password(user, data.password, request)
    if is_admin(db, user) and _admin_count(db) <= 1 and db.scalar(select(func.count()).select_from(User)) > 1:
        raise HTTPException(status.HTTP_409_CONFLICT, "Du bist der letzte Administrator. Ernenne zuerst jemand anderen zum Administrator.")
    delete_user_data(db, user)


@router.post("/me/whatsnew/seen", status_code=204)
def whatsnew_seen(user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.whatsnew_seen = CURRENT_WHATSNEW
    db.commit()


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return _user_out(user, is_admin(db, user))


@router.put("/settings/strava", response_model=UserOut)
def save_strava_settings(data: StravaSettingsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    user.strava_client_id = data.client_id.strip()
    user.strava_client_secret = data.client_secret.strip()
    # Neue App-Zugangsdaten => bestehende Verbindung ungültig
    user.strava_access_token = None
    user.strava_refresh_token = None
    user.strava_expires_at = None
    user.strava_athlete_id = None
    db.commit()
    return _user_out(user, is_admin(db, user))
