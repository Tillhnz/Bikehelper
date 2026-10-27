"""intervals.icu-Import mit nachgestellter API (httpx.MockTransport); die FIT-Datei wird durch GPX ersetzt."""
import os
import tempfile

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.mkdtemp()}/test.db")
os.environ.setdefault("WEATHER_ENABLED", "false")

import httpx  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import changelog  # noqa: E402
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
        w = c.get("/api/me", headers=h).json()["whatsnew"]
        assert [e["id"] for e in w][0] == changelog.latest_id() and all(e["changes"] and e["title"] for e in w)
        assert c.post("/api/me/whatsnew/seen", headers=h).status_code == 204
        assert c.get("/api/me", headers=h).json()["whatsnew"] is None


def test_version_endpoint_reports_installed_version():
    with TestClient(app) as c:
        h, _ = _user(c, "icu10@example.com")
        r = c.get("/api/version", headers=h).json()
        assert r["version"] == changelog.latest_id() and r["update_available"] in (None, True, False)
        assert c.get("/api/version").status_code == 401


def test_changelog_shows_only_newer_entries():
    items = changelog.entries()
    ids = [e["id"] for e in items]
    assert len(ids) == len(set(ids)) and ids == sorted(ids, reverse=True)  # eindeutig, neueste zuerst
    assert all(e["title"] and e["date"] and e["changes"] for e in items)
    assert changelog.unseen(ids[0]) == [] and [e["id"] for e in changelog.unseen(ids[1])] == [ids[0]]
    assert [e["id"] for e in changelog.unseen("intervals-2026-10")] == ids[: ids.index("2026-10-27.1")]  # alte Kennung
    assert len(changelog.unseen("unbekannt")) == min(5, len(ids))


def test_tour_for_new_accounts_only_until_done():
    with TestClient(app) as c:
        h, uid = _user(c, "icu11@example.com")
        assert c.get("/api/me", headers=h).json()["tour"] is True  # neues Konto
        assert c.post("/api/me/tour/done", headers=h).status_code == 204
        assert c.get("/api/me", headers=h).json()["tour"] is False
        assert c.post("/api/me/tour/restart", headers=h).status_code == 204
        assert c.get("/api/me", headers=h).json()["tour"] is True
        with SessionLocal() as db:  # Bestandskonto von vor dem Update: kein Rundgang
            u = db.get(User, uid)
            u.tour_pending = None
            db.commit()
        assert c.get("/api/me", headers=h).json()["tour"] is False


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


def test_bike_suggestions_from_gear_name_and_similar_rides():
    from datetime import datetime, timedelta
    with TestClient(app) as c:
        h, uid = _user(c, "icu7@example.com")
        with SessionLocal() as db:
            bike = db.scalars(select(Bike).where(Bike.user_id == uid)).one()
            other = Bike(user_id=uid, name="Gravel", type="gravel")
            db.add(other)
            db.flush()
            t0 = datetime(2026, 5, 1, 7, 30)
            for i in range(4):  # Pendeln mit dem Canyon: gleicher Start, ~20 km, morgens
                db.add(Activity(user_id=uid, bike_id=bike.id, name=f"P{i}", start_date=t0 + timedelta(days=i), distance_km=20 + i,
                                start_lat=50.1, start_lng=8.6, gear_name="Canyon Endurace"))
            db.add(Activity(user_id=uid, bike_id=other.id, name="G", start_date=t0, distance_km=80, start_lat=50.5, start_lng=9.0))
            a_gear = Activity(user_id=uid, name="Neu 1", start_date=datetime(2026, 6, 1, 18, 0), distance_km=5, gear_name="Canyon Endurace")
            a_near = Activity(user_id=uid, name="Neu 2", start_date=datetime(2026, 6, 2, 7, 45), distance_km=21, start_lat=50.1004, start_lng=8.6004)
            a_far = Activity(user_id=uid, name="Neu 3", start_date=datetime(2026, 6, 3, 7, 45), distance_km=21, start_lat=48.0, start_lng=11.0)
            db.add_all([a_gear, a_near, a_far])
            db.commit()
            ids = (a_gear.id, a_near.id, a_far.id, bike.id)
        s = c.get("/api/activities/suggestions", headers=h).json()
        assert s[str(ids[0])]["bike_id"] == ids[3] and "Radnamen" in s[str(ids[0])]["reason"]
        assert s[str(ids[1])]["bike_id"] == ids[3] and "ähnlichen" in s[str(ids[1])]["reason"]
        assert str(ids[2]) not in s  # anderer Startort: kein Vorschlag
        one = c.get(f"/api/activities/suggestions?activity_id={ids[1]}", headers=h).json()
        assert list(one) == [str(ids[1])] and one[str(ids[1])]["bike_id"] == ids[3]  # Vorschlag für die Einzelansicht


def test_bike_suggestions_from_power_source_terrain_and_speed():
    from datetime import datetime, timedelta
    with TestClient(app) as c:
        h, uid = _user(c, "icu9@example.com")
        with SessionLocal() as db:
            road = db.scalars(select(Bike).where(Bike.user_id == uid)).one()
            gravel = Bike(user_id=uid, name="Gravel", type="gravel")
            db.add(gravel)
            db.flush()
            t0 = datetime(2026, 4, 1, 12, 0)
            for i in range(10):  # Rennrad: immer mit Leistungsmesser, schnell, Wahoo
                db.add(Activity(user_id=uid, bike_id=road.id, name=f"R{i}", start_date=t0 + timedelta(days=i), distance_km=60 + i,
                                moving_time_s=int((60 + i) / 29 * 3600), avg_power=210 + i, avg_cadence=88, source="wahoo", terrain="road"))
            for i in range(10):  # Gravel: ohne Leistung, langsamer, Fahrtart Gravel
                db.add(Activity(user_id=uid, bike_id=gravel.id, name=f"G{i}", start_date=t0 + timedelta(days=i), distance_km=40 + i,
                                moving_time_s=int((40 + i) / 20 * 3600), avg_power=0, avg_cadence=0, source="intervals", terrain="gravel"))
            fast = Activity(user_id=uid, name="Neu schnell", start_date=datetime(2026, 6, 1, 9, 0), distance_km=70,
                            moving_time_s=int(70 / 29.5 * 3600), avg_power=215, avg_cadence=90, source="wahoo", terrain="road")
            unclear = Activity(user_id=uid, name="Neu unklar", start_date=datetime(2026, 6, 2, 9, 0), distance_km=50,
                               moving_time_s=int(50 / 25 * 3600), avg_power=None, avg_cadence=None, source="upload", terrain="")
            db.add_all([fast, unclear])
            db.commit()
            ids = (fast.id, unclear.id, road.id)
        s = c.get("/api/activities/suggestions", headers=h).json()
        assert s[str(ids[0])]["bike_id"] == ids[2] and "Leistungsdaten" in s[str(ids[0])]["reason"]
        assert str(ids[1]) not in s  # keine unterscheidenden Merkmale: kein Vorschlag


def test_terrain_of_and_features():
    from app.suggest import features_from_details, terrain_of
    assert terrain_of("Gravel Ride") == "gravel" and terrain_of("cycling gravel_cycling") == "gravel"
    assert terrain_of("MountainBikeRide") == "mtb" and terrain_of("EBikeRide") == "ebike" and terrain_of("Ride") is None
    assert features_from_details({"avg_power": 180.4, "avg_cadence": 85}) == (180.4, 85.0) and features_from_details(None) == (0.0, 0.0)


def test_import_triggers_weather_for_new_rides(monkeypatch):
    monkeypatch.setattr(service, "parse_activity_file", lambda name, data: parse_activity_file("x.gpx", data))
    from app.weather import service as weather_service
    calls = []
    monkeypatch.setattr(weather_service, "trigger", lambda uid=None: calls.append(uid))
    with TestClient(app) as c:
        _, uid = _user(c, "icu8@example.com")
        with SessionLocal() as db:
            service.sync_user(db, db.get(User, uid), http=_fake([]))
    assert calls == [uid]
