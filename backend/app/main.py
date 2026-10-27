import logging
import traceback
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.middleware.gzip import GZipMiddleware

from . import audit, notify, suggest
from .database import Base, SessionLocal, ensure_columns, engine
from .routers import account as account_router, activities, admin as admin_router, advisor, auth, garage, home, mechanic as mechanic_router, inventory, mapconfig, notifications, places as places_router, stats as stats_router, tire_catalog as tire_catalog_router, tires, intervals as intervals_router, groups as groups_router, version as version_router, weather as weather_router
from . import server_settings
from .services import migrate_legacy_lube
from .geo import service as geo_service
from .intervals import service as intervals_service
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
    audit.event("System", "server.start", "BikeHelper gestartet")
    weather_service.start_background()
    notify.start_background()
    geo_service.start_background()
    intervals_service.start_background()
    suggest.start_backfill()
    yield


app = FastAPI(title="BikeHelper", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)

# Grobe Bereiche für das Ereignisprotokoll. Es wird nie ein Name, eine Zahl oder eine ID gespeichert.
_AREAS = (
    ("/api/bikes", "Garage"), ("/api/components", "Wartung"), ("/api/rules", "Wartung"), ("/api/logs", "Wartung"),
    ("/api/measurements", "Wartung"), ("/api/tire-sets", "Reifen"), ("/api/tire-mounts", "Reifen"),
    ("/api/tire-catalog", "Reifenkatalog"), ("/api/inventory", "Lager"), ("/api/activities", "Fahrten"),
    ("/api/imports", "Fahrten"), ("/api/stats/goals", "Ziele"), ("/api/settings", "Einstellungen"),
    ("/api/notifications", "Erinnerungen"), ("/api/intervals", "intervals.icu"), ("/api/places", "Orte"), ("/api/advisor", "Ratgeber"),
    ("/api/mechanic", "Mechanics"), ("/api/groups", "Gruppen"),
)
_SPECIAL = {
    "/api/auth/password": ("password", "Passwort geändert"), "/api/auth/logout-all": ("logout.all", "Überall abgemeldet"),
    "/api/me/delete": ("account.delete", "Konto selbst gelöscht"), "/api/me/export": ("export", "Datenexport"),
}
_VERB = {"POST": "neu oder ausgeführt", "PUT": "geändert", "PATCH": "geändert", "DELETE": "gelöscht"}


@app.exception_handler(StarletteHTTPException)
async def keep_http_detail(request, exc):
    """Merkt sich die Meldung, damit das Ereignisprotokoll sie bei Fehlern ab 500 vollständig zeigen kann."""
    request.state.http_detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
    return await http_exception_handler(request, exc)


@app.middleware("http")
async def event_log(request, call_next):
    """Schreibt Aktionen und Serverfehler ins Ereignisprotokoll. Nur Bereich und Art, keine Inhalte."""
    path = request.url.path
    crash = None
    try:
        response = await call_next(request)
    except Exception as exc:  # nicht abgefangener Fehler: ins Protokoll und als normale 500-Antwort ausliefern
        logging.getLogger("bikehelper").exception("Unbehandelter Fehler bei %s %s", request.method, path)
        crash = exc
        response = JSONResponse({"detail": "Interner Serverfehler"}, status_code=500)
    if not path.startswith("/api/") or path.startswith(("/api/admin", "/api/health")):
        return response
    try:
        actor = getattr(request.state, "actor", None)
        route = request.scope.get("route")
        template = getattr(route, "path", path)
        if response.status_code >= 500:
            if crash is not None:
                tb = traceback.extract_tb(crash.__traceback__)
                where = f"{tb[-1].filename.split('/app/')[-1]}:{tb[-1].lineno} in {tb[-1].name}" if tb else "?"
                text = f"Fehlercode {response.status_code}: {type(crash).__name__}: {crash}\nStelle: {where}"
            else:
                text = f"Fehlercode {response.status_code}: {getattr(request.state, 'http_detail', None) or 'keine Meldung'}"
            audit.event(actor or "System", "error", f"{request.method} {template} -> {response.status_code}", text)
        elif actor and request.method in _VERB and response.status_code < 400:
            if path in _SPECIAL:
                action, text = _SPECIAL[path]
                audit.event(actor, action, text if action != "export" else "")
            else:
                area = next((label for prefix, label in _AREAS if path.startswith(prefix)), None)
                if area:
                    audit.event(actor, "act", f"{area}: {_VERB[request.method]}")
    except Exception:
        logging.getLogger("bikehelper").exception("Ereignisprotokoll")
    return response


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
app.include_router(account_router.router)
app.include_router(home.router)
app.include_router(garage.router)
app.include_router(mechanic_router.router)
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
app.include_router(intervals_router.router)
app.include_router(groups_router.router)
app.include_router(version_router.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
