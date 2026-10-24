import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from . import notify
from .database import Base, SessionLocal, ensure_columns, engine
from .routers import activities, admin as admin_router, advisor, auth, garage, home, inventory, mapconfig, notifications, places as places_router, stats as stats_router, tire_catalog as tire_catalog_router, tires, wahoo as wahoo_router, weather as weather_router
from . import server_settings
from .services import migrate_legacy_lube
from .geo import service as geo_service
from .wahoo import service as wahoo_service
from .weather import service as weather_service


def bootstrap_roles(db) -> None:
    """Älteren Konten eine Rolle geben: das älteste Konto wird Administrator, alle anderen Nutzer."""
    from sqlalchemy import select
    from .models import User
    users = db.scalars(select(User).order_by(User.id)).all()
    if not users:
        return
    for u in users:
        if u.role not in ("admin", "user"):
            u.role = "user"
        if u.active is None:
            u.active = True
    if not any(u.role == "admin" for u in users):
        users[0].role = "admin"
    db.commit()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Für den Start genügen create_all und ensure_columns; später wechseln wir auf Alembic-Migrationen.
    from .config import settings
    if settings.secret_key in ("dev-secret-change-me", "bitte-aendern") or len(settings.secret_key) < 16:
        logging.getLogger("bikehelper").warning("SECRET_KEY ist unsicher. Setze einen langen Zufallswert (openssl rand -hex 32).")
    Base.metadata.create_all(engine)
    ensure_columns()
    with SessionLocal() as db:
        migrate_legacy_lube(db)
        bootstrap_roles(db)
        server_settings.apply_overrides(db)
    weather_service.start_background()
    notify.start_background()
    geo_service.start_background()
    wahoo_service.start_background()
    yield


app = FastAPI(title="BikeHelper", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)


@app.middleware("http")
async def security_headers(request, call_next):
    """API-Antworten enthalten persönliche Daten: nicht zwischenspeichern, Inhaltstyp nicht erraten lassen."""
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("Cache-Control", "no-store")
    response.headers.setdefault("Referrer-Policy", "no-referrer")
    return response


app.include_router(auth.router)
app.include_router(admin_router.router)
app.include_router(home.router)
app.include_router(garage.router)
app.include_router(tires.router)
app.include_router(tire_catalog_router.router)
app.include_router(inventory.router)
app.include_router(activities.router)
app.include_router(weather_router.router)
app.include_router(stats_router.router)
app.include_router(mapconfig.router)
app.include_router(advisor.router)
app.include_router(notifications.router)
app.include_router(places_router.router)
app.include_router(wahoo_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
