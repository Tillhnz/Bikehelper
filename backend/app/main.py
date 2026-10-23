from contextlib import asynccontextmanager

from fastapi import FastAPI

from .database import Base, engine
from .routers import auth, garage


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Für den Start genügt create_all; später wechseln wir auf Alembic-Migrationen.
    Base.metadata.create_all(engine)
    yield


app = FastAPI(title="BikeHelper", lifespan=lifespan)
app.include_router(auth.router)
app.include_router(garage.router)


@app.get("/api/health")
def health():
    return {"status": "ok"}
