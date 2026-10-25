import os
import tempfile
from datetime import date, datetime, timedelta

os.environ["DATABASE_URL"] = f"sqlite:///{tempfile.mkdtemp()}/test.db"
os.environ["WEATHER_ENABLED"] = "false"

from fastapi.testclient import TestClient  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Activity  # noqa: E402


def test_tire_lifetime_and_check_interval():
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "t@example.com", "password": "geheim1234"})
        h = {"Authorization": "Bearer " + c.post("/api/auth/login", json={"email": "t@example.com", "password": "geheim1234"}).json()["access_token"]}
        me = c.get("/api/me", headers=h).json()
        bike = c.post("/api/bikes", headers=h, json={"name": "R", "type": "road"}).json()
        start = date.today() - timedelta(days=30)
        ts = c.post(f"/api/bikes/{bike['id']}/tire-sets", headers=h,
                    json={"name": "Satz", "max_km": 1000, "check_km": 500, "mount_from": start.isoformat()}).json()
        assert ts["check_interval_km"] == 500 and ts["status"] == "ok" and ts["km_left"] == 1000
        with SessionLocal() as db:
            db.add(Activity(user_id=me["id"], bike_id=bike["id"], name="Tour", start_date=datetime.now() - timedelta(days=5), distance_km=450))
            db.commit()
        ts = c.get(f"/api/bikes/{bike['id']}/tire-sets", headers=h).json()[0]
        assert ts["check_status"] == "soon" and ts["life_status"] == "ok" and ts["km_left"] == 550
        items = c.get("/api/maintenance/overview", headers=h).json()["items"]
        assert [i["rule"] for i in items] == ["Reifen prüfen"] and items[0]["rule_id"] is None
        ts = c.post(f"/api/tire-sets/{ts['id']}/checked", headers=h).json()
        assert ts["check_status"] == "ok" and ts["km_since_check"] == 0 and ts["checked_on"] == date.today().isoformat()
        assert c.get("/api/maintenance/overview", headers=h).json()["items"] == []
        # Standard-Intervall bei leerem Feld
        ts2 = c.post(f"/api/bikes/{bike['id']}/tire-sets", headers=h, json={"name": "Zweiter"}).json()
        assert ts2["check_interval_km"] == 1000
