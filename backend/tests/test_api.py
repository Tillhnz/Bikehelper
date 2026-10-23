import os
import tempfile
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["WEATHER_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Activity  # noqa: E402


def test_full_flow():
    with TestClient(app) as c:
        # Registrierung + Login
        r = c.post("/api/auth/register", json={"email": "A@Example.com", "password": "geheim1234"})
        assert r.status_code == 201
        assert c.post("/api/auth/login", json={"email": "a@example.com", "password": "falsch"}).status_code == 401
        token = c.post("/api/auth/login", json={"email": "a@example.com", "password": "geheim1234"}).json()["access_token"]
        h = {"Authorization": f"Bearer {token}"}

        assert c.get("/api/me").status_code == 401
        me = c.get("/api/me", headers=h).json()
        assert me["strava_configured"] is False

        # Strava-Einstellungen
        me = c.put("/api/settings/strava", headers=h, json={"client_id": "123", "client_secret": "abc"}).json()
        assert me["strava_configured"] is True and me["strava_connected"] is False

        # Rad + Komponente + Regel
        bike = c.post("/api/bikes", headers=h, json={"name": "Canyon Endurace", "type": "road", "start_km": 1000}).json()
        installed = date.today() - timedelta(days=60)
        comp = c.post("/api/components", headers=h, json={
            "bike_id": bike["id"], "category": "chain", "name": "KMC X11",
            "installed_at": installed.isoformat(),
        }).json()
        rule = c.post(f"/api/components/{comp['id']}/rules", headers=h,
                      json={"label": "Kette wechseln", "interval_km": 1000}).json()
        assert rule["status"] == "ok"

        # Fahrten seit Einbau: 850 km => "soon" (>= 80 %)
        with SessionLocal() as db:
            for i in range(5):
                db.add(Activity(user_id=me["id"], bike_id=bike["id"], name=f"Ride {i}",
                                start_date=datetime.now() - timedelta(days=10 + i), distance_km=170))
            db.commit()

        rules = c.get(f"/api/components/{comp['id']}/rules", headers=h).json()
        assert rules[0]["km_since"] == 850 and rules[0]["status"] == "soon"
        assert c.get(f"/api/bikes/{bike['id']}", headers=h).json()["total_km"] == 1850

        # weitere 200 km => fällig
        with SessionLocal() as db:
            db.add(Activity(user_id=me["id"], bike_id=bike["id"], name="Long",
                            start_date=datetime.now() - timedelta(days=2), distance_km=200))
            db.commit()
        overview = c.get("/api/maintenance/overview", headers=h).json()
        assert overview["status"] == "due" and overview["items"][0]["rule"] == "Kette wechseln"

        # Wartung eintragen => Zähler startet neu
        c.post(f"/api/components/{comp['id']}/logs", headers=h,
               json={"performed_at": date.today().isoformat(), "note": "gewechselt"})
        assert c.get("/api/maintenance/overview", headers=h).json()["items"] == []

        # Fremde Nutzer sehen nichts
        t2 = c.post("/api/auth/register", json={"email": "b@example.com", "password": "geheim1234"}).json()["access_token"]
        h2 = {"Authorization": f"Bearer {t2}"}
        assert c.get("/api/bikes", headers=h2).json() == []
        assert c.get(f"/api/bikes/{bike['id']}", headers=h2).status_code == 404
