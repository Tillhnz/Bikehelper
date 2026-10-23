from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import User
from ..schemas import LoginIn, RegisterIn, StravaSettingsIn, TokenOut, UserOut
from ..security import create_token, current_user, hash_password, verify_password

router = APIRouter(prefix="/api", tags=["auth"])


def _user_out(u: User) -> UserOut:
    return UserOut(
        id=u.id,
        email=u.email,
        strava_configured=bool(u.strava_client_id and u.strava_client_secret),
        strava_connected=bool(u.strava_refresh_token),
        weight_kg=u.weight_kg,
    )


@router.get("/config")
def public_config():
    return {"allow_registration": settings.allow_registration}


@router.post("/auth/register", response_model=TokenOut, status_code=201)
def register(data: RegisterIn, db: Session = Depends(get_db)):
    first_user = db.scalar(select(User.id).limit(1)) is None
    if not settings.allow_registration and not first_user:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registrierung ist deaktiviert")
    email = data.email.lower()
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "E-Mail bereits vergeben")
    user = User(email=email, password_hash=hash_password(data.password))
    db.add(user)
    db.commit()
    return TokenOut(access_token=create_token(user.id))


@router.post("/auth/login", response_model=TokenOut)
def login(data: LoginIn, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == data.email.lower()))
    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "E-Mail oder Passwort falsch")
    return TokenOut(access_token=create_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return _user_out(user)


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
    return _user_out(user)
