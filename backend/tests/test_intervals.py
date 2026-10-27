"""intervals.icu-Import mit nachgestellter API (httpx.MockTransport); die FIT-Datei wird durch GPX ersetzt."""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("WEATHER_ENABLED", "false")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.importers.parsers import parse_activity_file  # noqa: E402
from app.intervals import service  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Activity, Bike, IntervalsSeen, User  # noqa: E402
from test_importers import make_gpx  # noqa: E402


def _fake(calls, status_for_list=200):
    gpx = make_gpx()

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.url.path, request.headers.get("authorization", "")[:6]))
        path = request.url.path
        if path == "/api/v1/athlete/0":
            return httpx.Response(200, json={"name": "Tester"})
        if path == "/api/v1/athlete/0/activities":
            if status_for_list != 200:
                return httpx.Response(status_for_list)
            if request.url.params["oldest"][:4] != "2015":  # nur das erste Jahr liefert Daten
                return httpx.Response(200, json=[])
            return httpx.Response(200, json=[
                {"id": "i1", "start_date_local": "2015-10-01T07:00:00", "type": "Ride", "name": "Morgenrunde", "file_type": "fit",
                 "source": "GARMIN_CONNECT", "gear": {"name": "Canyon"}},
                {"id": "i2", "start_date_local": "2015-10-02T07:00:00", "type": "Ride", "file_type": "fit", "source": "GARMIN_CONNECT"},
                {"id": "i3", "start_date_local": "2015-10-03T07:00:00", "type": "Ride", "source": "STRAVA",
                 "_note": "STRAVA activities are not available via the API"},
                {"id": "i4", "start_date_local": "2015-10-04T07:00:00", "type": "Run", "file_type": "fit"},
            ])
        if path.startswith("/api/v1/activity/") and path.endswith("/file"):
            return httpx.Response(200, content=gpx)
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="https://intervals.icu")


def _user(c, email):
    r = c.post("/api/auth/register", json={"email": email, "password": "geheim1234"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == email))
        db.add(Bike(user_id=u.id, name="Canyon", type="road"))
        u.icu_api_key = "abcdef123456"
        db.commit()
        return h, u.id


def test_sync_imports_once_skips_strava_and_other_sports(monkeypatch):
    monkeypatch.setattr(service, "parse_activity_file", lambda name, data: parse_activity_file("x.gpx", data))
    with TestClient(app) as c:
        h, uid = _user(c, "icu1@example.com")
        calls = []
        with SessionLocal() as db:
            res = service.sync_user(db, db.get(User, uid), http=_fake(calls))
            # i1 importiert, i2 hat dieselbe Datei (Duplikat), i3 Strava und i4 Laufen werden übersprungen
            assert (res.imported, res.duplicates, res.skipped, res.remaining) == (1, 1, 2, 0)
            assert (res.found, res.strava, res.other_sport) == (4, 1, 1) and "von Strava" in res.text()
            act = db.scalars(select(Activity).where(Activity.user_id == uid, Activity.source == "intervals")).one()
            assert act.gear_name == "Canyon" and act.bike_id is not None  # Rad über den Namen aus intervals.icu gefunden
            seen = {s.activity_id: s.status for s in db.scalars(select(IntervalsSeen).where(IntervalsSeen.user_id == uid))}
            assert seen == {"i1": "imported", "i2": "duplicate", "i3": "skipped", "i4": "skipped"}
            assert db.get(User, uid).icu_synced_until is not None
        assert all(a == "Basic " for _, a in calls)

        calls2 = []
        with SessionLocal() as db:
            res2 = service.sync_user(db, db.get(User, uid), http=_fake(calls2))
            assert res2.imported == 0 and not [p for p, _ in calls2 if p.endswith("/file")]
        st = c.get("/api/settings/intervals", headers=h).json()
        assert st["connected"] and st["imported"] == 1 and "abcdef" not in str(st) and st["key_hint"] == "…3456"


def test_bad_key_gives_clear_error():
    with TestClient(app) as c:
        _, uid = _user(c, "icu2@example.com")
        with SessionLocal() as db:
            try:
                service.sync_user(db, db.get(User, uid), http=_fake([], status_for_list=401))
                raise AssertionError("erwartet: IntervalsError")
            except service.IntervalsError as e:
                assert "API-Schlüssel" in str(e)
            assert "API-Schlüssel" in db.get(User, uid).icu_status


def test_settings_reject_malformed_key_and_disconnect():
    with TestClient(app) as c:
        h, _ = _user(c, "icu3@example.com")
        assert c.put("/api/settings/intervals", headers=h, json={"api_key": "bad key!"}).status_code == 422
        assert c.delete("/api/intervals/connection", headers=h).status_code == 204
        assert c.get("/api/settings/intervals", headers=h).json()["connected"] is False


def test_whatsnew_popup_shows_once_for_existing_accounts_only():
    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"email": "icu4@example.com", "password": "geheim1234"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        assert c.get("/api/me", headers=h).json()["whatsnew"] is None  # neues Konto: kein Hinweis nötig
        with SessionLocal() as db:  # Bestandskonto von vor dem Update
            u = db.scalar(select(User).where(User.email == "icu4@example.com"))
            u.whatsnew_seen = None
            db.commit()
        assert c.get("/api/me", headers=h).json()["whatsnew"] == "intervals-2026-10"
        assert c.post("/api/me/whatsnew/seen", headers=h).status_code == 204
        assert c.get("/api/me", headers=h).json()["whatsnew"] is None


def test_full_resync_restores_a_ride_deleted_in_bikehelper(monkeypatch):
    monkeypatch.setattr(service, "parse_activity_file", lambda name, data: parse_activity_file("x.gpx", data))
    monkeypatch.setattr(service, "run_in_background", lambda uid: True)  # der Test ruft den Abgleich selbst auf
    with TestClient(app) as c:
        h, uid = _user(c, "icu5@example.com")
        with SessionLocal() as db:
            # Fahrt war per Datei da, intervals.icu hat sie als Duplikat gemerkt, danach wurde sie gelöscht
            service.sync_user(db, db.get(User, uid), http=_fake([]))
            db.query(Activity).filter(Activity.user_id == uid).delete()
            db.commit()
            assert service.sync_user(db, db.get(User, uid), http=_fake([])).imported == 0  # bleibt ohne neuen Abgleich weg
        assert c.post("/api/intervals/sync", headers=h, json={"full": True}).status_code == 202
        with SessionLocal() as db:
            assert service.sync_user(db, db.get(User, uid), http=_fake([])).imported == 1


def test_filter_activities_by_source():
    with TestClient(app) as c:
        h, uid = _user(c, "icu6@example.com")
        with SessionLocal() as db:
            from datetime import datetime
            for i, src in enumerate(("wahoo", "wahoo", "intervals", None)):
                db.add(Activity(user_id=uid, name=f"R{i}", start_date=datetime(2026, 1, 1 + i), distance_km=10, source=src))
            db.commit()
        assert c.get("/api/activities?source=wahoo", headers=h).json()["total"] == 2
        assert c.get("/api/activities?source=unknown", headers=h).json()["total"] == 1
        assert {s["source"]: s["count"] for s in c.get("/api/activities/sources", headers=h).json()} == {"wahoo": 2, "intervals": 1, "unknown": 1}
