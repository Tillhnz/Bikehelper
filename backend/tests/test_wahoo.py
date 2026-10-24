"""Wahoo-Import mit nachgestellter Wahoo-API (httpx.MockTransport); die FIT-Datei wird durch GPX ersetzt."""
import os
import tempfile
import time

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("WEATHER_ENABLED", "false")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.database import SessionLocal  # noqa: E402
from app.importers.parsers import parse_activity_file  # noqa: E402
from app.main import app  # noqa: E402
from app.models import Activity, User, WahooSeen  # noqa: E402
from app.wahoo import service  # noqa: E402
from test_importers import make_gpx  # noqa: E402


def _fake_wahoo(calls, rate_limit_after=None):
    gpx = make_gpx()

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        calls.append(path)
        if request.url.host == "cdn.example.com":
            return httpx.Response(200, content=gpx)
        if rate_limit_after is not None and sum(1 for p in calls if p.startswith("/v1/workouts/")) > rate_limit_after:
            return httpx.Response(429, json={})
        if path == "/oauth/token":
            return httpx.Response(200, json={"access_token": "A2", "refresh_token": "R2", "expires_in": 7200})
        if path == "/v1/workouts":
            items = [{"id": i, "name": f"Fahrt {i}", "starts": f"2026-10-0{i}T07:00:00Z"} for i in (1, 2, 3)]
            return httpx.Response(200, json={"workouts": items, "total": 3, "page": 1, "per_page": 100})
        if path.startswith("/v1/workouts/"):
            wid = int(path.rsplit("/", 1)[1])
            file = None if wid == 3 else {"url": "https://cdn.example.com/x.fit"}
            return httpx.Response(200, json={"id": wid, "name": f"Fahrt {wid}", "workout_summary": {"file": file}})
        return httpx.Response(404)

    return httpx.Client(transport=httpx.MockTransport(handler))


def _connected_user(c, email):
    r = c.post("/api/auth/register", json={"email": email, "password": "geheim1234"})
    h = {"Authorization": f"Bearer {r.json()['access_token']}"}
    with SessionLocal() as db:
        u = db.scalar(select(User).where(User.email == email))
        u.wahoo_client_id, u.wahoo_client_secret = "cid", "secret"
        u.wahoo_access_token, u.wahoo_refresh_token = "A1", "R1"
        u.wahoo_expires_at = int(time.time()) - 10  # abgelaufen: Refresh nötig
        db.commit()
        return h, u.id


def test_sync_imports_new_rides_once_and_remembers_workouts(monkeypatch):
    # Statt FIT eine GPX-Datei parsen
    monkeypatch.setattr(service, "parse_activity_file", lambda name, data: parse_activity_file("x.gpx", data))
    with TestClient(app) as c:
        h, uid = _connected_user(c, "wahoo1@example.com")
        calls = []
        with SessionLocal() as db:
            user = db.get(User, uid)
            res = service.sync_user(db, user, http=_fake_wahoo(calls))
            # Beide Fahrten haben dieselbe Testdatei: die erste wird importiert, die zweite ist ein Duplikat
            assert (res.imported, res.duplicates, res.skipped, res.remaining) == (1, 1, 1, 0)
            assert user.wahoo_access_token == "A2" and user.wahoo_refresh_token == "R2"  # einmaliger Refresh-Token ersetzt
            seen = {s.workout_id: s.status for s in db.scalars(select(WahooSeen).where(WahooSeen.user_id == uid))}
            assert seen[3] == "skipped" and set(seen) == {1, 2, 3}
            assert db.scalars(select(Activity).where(Activity.user_id == uid, Activity.source == "wahoo")).all()

        # Zweiter Lauf: nur die Liste, keine Detailabrufe mehr
        calls2 = []
        with SessionLocal() as db:
            res2 = service.sync_user(db, db.get(User, uid), http=_fake_wahoo(calls2))
            assert res2.imported == 0 and not [p for p in calls2 if p.startswith("/v1/workouts/")]

        st = c.get("/api/settings/wahoo", headers=h).json()
        assert st["connected"] and st["imported"] >= 1 and st["last_sync"]


def test_rate_limit_stops_the_run_and_resumes_later(monkeypatch):
    monkeypatch.setattr(service, "parse_activity_file", lambda name, data: parse_activity_file("x.gpx", data))
    with TestClient(app) as c:
        _, uid = _connected_user(c, "wahoo2@example.com")
        with SessionLocal() as db:
            res = service.sync_user(db, db.get(User, uid), http=_fake_wahoo([], rate_limit_after=1))
            assert res.remaining >= 1 and "Limit" in res.note
            assert db.scalars(select(WahooSeen).where(WahooSeen.user_id == uid)).all()  # Fortschritt bleibt erhalten


def test_state_is_signed_and_settings_never_expose_the_secret():
    with TestClient(app) as c:
        h, uid = _connected_user(c, "wahoo3@example.com")
        assert service.read_state(service.make_state(uid)) == uid
        assert service.read_state("kaputt") is None
        st = c.get("/api/settings/wahoo", headers=h).json()
        assert "secret" not in str(st) and st["configured"]
        url = c.get("/api/wahoo/connect", headers=h).json()["url"]
        assert "client_id=cid" in url and "offline_data" in url and "secret" not in url
        assert c.get("/api/wahoo/callback?code=x&state=falsch").status_code == 400
        assert c.delete("/api/wahoo/connection", headers=h).status_code == 204
        assert not c.get("/api/settings/wahoo", headers=h).json()["connected"]
