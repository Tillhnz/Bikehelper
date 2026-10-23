from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import Base, ensure_columns, engine
from .routers import activities, auth, garage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Für den Start genügen create_all und ensure_columns; später wechseln wir auf Alembic-Migrationen.
    Base.metadata.create_all(engine)
    ensure_columns()
    yield


app = FastAPI(title="BikeHelper", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(garage.router)
app.include_router(activities.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
