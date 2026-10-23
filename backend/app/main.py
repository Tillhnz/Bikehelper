from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from . import notify
from .database import Base, SessionLocal, ensure_columns, engine
from .routers import activities, advisor, auth, garage, home, mapconfig, notifications, stats as stats_router, tires, weather as weather_router
from .services import migrate_legacy_lube
from .weather import service as weather_service


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Für den Start genügen create_all und ensure_columns; später wechseln wir auf Alembic-Migrationen.
    Base.metadata.create_all(engine)
    ensure_columns()
    with SessionLocal() as db:
        migrate_legacy_lube(db)
    weather_service.start_background()
    notify.start_background()
    yield


app = FastAPI(title="BikeHelper", lifespan=lifespan)
app.add_middleware(GZipMiddleware, minimum_size=1024)
app.include_router(auth.router)
app.include_router(home.router)
app.include_router(garage.router)
app.include_router(tires.router)
app.include_router(activities.router)
app.include_router(weather_router.router)
app.include_router(stats_router.router)
app.include_router(mapconfig.router)
app.include_router(advisor.router)
app.include_router(notifications.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
