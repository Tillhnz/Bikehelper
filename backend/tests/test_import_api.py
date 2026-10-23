"""API-Test für den Import (braucht die installierten Abhängigkeiten, siehe requirements.txt)."""
import io
import os
import tempfile
import time
import zipfile
from datetime import datetime, timedelta

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from test_importers import CSV_HEADER, make_gpx  # noqa: E402

DAY = timedelta(days=1)
BASE = datetime(2026, 10, 23, 7, 15, 0)


def _auth(c):
    r = c.post("/api/auth/register", json={"email": "import@example.com", "password": "geheim1234"})
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def _upload(c, h, name, data, bike_id=None):
    return c.post(
        "/api/activities/upload", headers=h,
        files=[("files", (name, data, "application/octet-stream"))],
        data={"bike_id": str(bike_id)} if bike_id else {},
    ).json()


def _wait(c, h, job_id, seconds=15):
    for _ in range(seconds * 10):
        job = c.get(f"/api/imports/{job_id}", headers=h).json()
        if job["status"] != "running":
            return job
        time.sleep(0.1)
    raise AssertionError("Import wurde nicht fertig")


def test_upload_assign_and_strava_zip():
    with TestClient(app) as c:
        h = _auth(c)
        bike = c.post("/api/bikes", headers=h, json={"name": "Canyon Endurace"}).json()

        # Datei-Upload mit Zuordnung, danach derselbe Upload als Duplikat
        r = _upload(c, h, "a.gpx", make_gpx(), bike["id"])
        assert r["imported"] == 1 and r["assigned"] == 1
        assert _upload(c, h, "a.gpx", make_gpx(), bike["id"])["duplicates"] == 1
        assert c.get(f"/api/bikes/{bike['id']}", headers=h).json()["total_km"] == 8.0

        # Fehlerhafte Datei wird gemeldet, ohne den Rest zu stoppen
        bad = _upload(c, h, "route.gpx", make_gpx(with_time=False))
        assert bad["imported"] == 0 and "Zeitstempel" in bad["errors"][0]["message"]

        # Fahrt ohne Rad, danach gesammelt zuordnen
        assert _upload(c, h, "b.gpx", make_gpx(start=BASE + DAY))["assigned"] == 0
        page = c.get("/api/activities?unassigned=true", headers=h).json()
        assert page["total"] == 1
        res = c.post("/api/activities/assign", headers=h,
                     json={"bike_id": bike["id"], "activity_ids": [page["items"][0]["id"]]}).json()
        assert res["updated"] == 1

        # Strava-Export: ein bekanntes Rad, ein neues Rad, eine Laufaktivität
        csv_text = "\n".join([
            CSV_HEADER,
            '9001,"x",Tour,Ride,,0,0,,,false,,Canyon Endurace,activities/9001.gpx,0,0',
            '9002,"x",Gravel,Gravel Ride,,0,0,,,false,,Neues+Gravel,activities/9002.gpx,0,0',
            '9003,"x",Laufen,Run,,0,0,,,false,,,activities/9003.gpx,0,0',
        ])
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as zf:
            zf.writestr("activities.csv", csv_text)
            zf.writestr("activities/9001.gpx", make_gpx(start=BASE + 2 * DAY))
            zf.writestr("activities/9002.gpx", make_gpx(start=BASE + 3 * DAY))
            zf.writestr("activities/9003.gpx", make_gpx(start=BASE + 4 * DAY, sport="running"))
        r = c.post("/api/imports/strava-export", headers=h,
                   files={"file": ("export.zip", buf.getvalue(), "application/zip")}, data={"create_bikes": "true"})
        assert r.status_code == 202
        job = _wait(c, h, r.json()["job_id"])
        assert job["status"] == "done", job
        s = job["summary"]
        assert s["imported"] == 2 and s["skipped_other_sport"] == 1
        assert s["created_bikes"] == ["Neues Gravel"] and s["assigned"] == 2

        bikes = {b["name"]: b for b in c.get("/api/bikes", headers=h).json()}
        assert set(bikes) == {"Canyon Endurace", "Neues Gravel"}
        assert bikes["Neues Gravel"]["type"] == "gravel"
        assert c.get("/api/activities", headers=h).json()["total"] == 4

        # Kein ZIP -> verständliche Fehlermeldung
        bad = c.post("/api/imports/strava-export", headers=h, files={"file": ("x.zip", b"kein zip", "application/zip")})
        assert bad.status_code == 422

        # Fremde Nutzer sehen weder Fahrten noch Importe
        t2 = c.post("/api/auth/register", json={"email": "other@example.com", "password": "geheim1234"}).json()["access_token"]
        h2 = {"Authorization": f"Bearer {t2}"}
        assert c.get("/api/activities", headers=h2).json()["total"] == 0
        assert c.get(f"/api/imports/{r.json()['job_id']}", headers=h2).status_code == 404
