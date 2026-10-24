"""Zugriff auf Räder anderer Konten (Mechanics-Modus). Nur aktive, vom Besitzer bestätigte Freigaben zählen."""
from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import MechanicGrant, User


def can_use(db: Session, user: User, owner_id: int) -> bool:
    """True für das eigene Konto oder wenn `owner_id` dem Nutzer eine aktive Freigabe erteilt hat."""
    if owner_id == user.id:
        return True
    return db.scalar(select(MechanicGrant.id).where(
        MechanicGrant.owner_id == owner_id, MechanicGrant.mechanic_id == user.id, MechanicGrant.status == "active"
    )) is not None
