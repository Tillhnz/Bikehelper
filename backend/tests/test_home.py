from datetime import date, datetime

from app.routers.home import build_home_week


def test_week_overview():
    today = date(2026, 10, 22)  # Donnerstag
    rows = [
        (datetime(2026, 10, 19, 8), 40.0, 5000, 300.0),   # Montag dieser Woche
        (datetime(2026, 10, 22, 8), 60.0, 7000, 500.0),   # heute
        (datetime(2026, 10, 12, 8), 30.0, 3000, 100.0),   # Montag der Vorwoche
        (datetime(2026, 10, 17, 8), 90.0, 9000, 100.0),   # Samstag der Vorwoche, nach dem Vergleichspunkt
    ]
    w = build_home_week(rows, today)
    assert w["totals"]["km"] == 100.0 and w["totals"]["rides"] == 2
    assert [d["km"] for d in w["days"]][:4] == [40.0, 0.0, 0.0, 60.0]
    assert w["days"][3]["today"] and w["days"][4]["future"]
    assert w["last_week_same_point_km"] == 30.0 and w["last_week_km"] == 120.0
    assert len(w["weeks"]) == 8


def test_past_week_view():
    today = date(2026, 10, 22)
    rows = [
        (datetime(2026, 10, 14, 8), 50.0, 4000, 200.0),   # Mittwoch der Vorwoche
        (datetime(2026, 10, 17, 8), 20.0, 2000, 50.0),    # Samstag der Vorwoche
        (datetime(2026, 10, 8, 8), 70.0, 6000, 0.0),      # Donnerstag davor
    ]
    w = build_home_week(rows, today, weeks=2, offset=-1)
    assert w["monday"] == "2026-10-12" and w["offset"] == -1
    assert w["totals"]["km"] == 70.0 and w["totals"]["rides"] == 2
    assert not any(d["today"] or d["future"] for d in w["days"])
    assert w["last_week_km"] == 70.0 and w["last_week_same_point_km"] == 70.0  # ganze Vorwoche, da die Woche vorbei ist


def test_wet_notice_window_and_chain_care():
    from datetime import timedelta
    from app.routers.home import build_wet_notices
    start = datetime(2026, 10, 24, 8, 0)
    ride = {"activity_id": 1, "name": "Nass", "bike_id": 7, "bike_name": "Hobel", "lube": "wax", "start": start,
            "moving_time_s": 3600, "wet_minutes": 40}  # endet 09:00
    dry = {**ride, "activity_id": 2, "bike_id": 8, "wet_minutes": 2}
    other = {**ride, "activity_id": 3, "start": start - timedelta(days=1)}  # älter, gleiches Rad: zählt nicht doppelt
    out = build_wet_notices([ride, dry, other], datetime(2026, 10, 24, 10, 0), {})
    assert [n["activity_id"] for n in out] == [1] and out[0]["expires_at"] == "2026-10-24T13:00:00Z" and out[0]["lube"] == "wax"
    assert build_wet_notices([ride], datetime(2026, 10, 24, 12, 59), {}) != []          # kurz vor Ablauf
    assert build_wet_notices([ride], datetime(2026, 10, 24, 13, 0), {}) == []           # nach 4 Stunden weg
    assert build_wet_notices([ride], datetime(2026, 10, 24, 10, 0), {7: [datetime(2026, 10, 24, 9, 30)]}) == []  # Kette schon gepflegt
    assert build_wet_notices([ride], datetime(2026, 10, 24, 10, 0), {7: [datetime(2026, 10, 24, 8, 30)]}) != []  # Pflege vor der Fahrt zählt nicht


def test_home_layout_and_analysis_blocks():
    from datetime import datetime, timedelta
    from fastapi.testclient import TestClient
    from app.database import SessionLocal
    from app.main import app
    from app.models import Activity

    with TestClient(app) as c:
        r = c.post("/api/auth/register", json={"email": "layout@example.com", "password": "geheim1234"})
        h = {"Authorization": f"Bearer {r.json()['access_token']}"}
        me = c.get("/api/me", headers=h).json()
        assert me["ui_mode"] == "simple" and me["home_layout"] is None  # neue Konten starten einfach
        lay = c.get("/api/home/layout", headers=h).json()
        assert lay["layout"] == ["week", "maintenance", "bikes", "goal", "recent"] and lay["custom"] is False
        assert next(b for b in lay["catalog"] if b["id"] == "form")["available"] is False  # nur für Experten

        # Anordnung speichern; der Expertenblock bleibt gespeichert, wird im einfachen Modus aber nicht angezeigt
        out = c.put("/api/me/ui", headers=h, json={"layout": ["recent", "form", "eddington"]}).json()
        assert out["layout"] == ["recent", "eddington"] and out["custom"] is True
        assert c.put("/api/me/ui", headers=h, json={"layout": ["week", "week"]}).status_code == 422
        assert c.put("/api/me/ui", headers=h, json={"layout": ["gibtesnicht"]}).status_code == 422
        assert c.put("/api/me/ui", headers=h, json={"mode": "chaos"}).status_code == 422
        assert c.put("/api/me/ui", headers=h, json={"mode": "expert"}).json()["layout"] == ["recent", "form", "eddington"]

        uid = c.get("/api/me", headers=h).json()["id"]
        with SessionLocal() as db:
            for i in range(4):
                db.add(Activity(user_id=uid, name="x", start_date=datetime.utcnow() - timedelta(days=i), distance_km=10.0 * (i + 1),
                                moving_time_s=3600, elevation_m=100))
            db.commit()
        data = c.get("/api/home/blocks?ids=eddington,streaks,records,form,week", headers=h).json()
        assert set(data) == {"eddington", "streaks", "records", "form"}
        assert data["eddington"]["value"] == 4 and data["streaks"]["current"] == 4 and data["records"]["longest"]["km"] == 40.0
        assert data["form"]["fitness"] is not None

        assert c.put("/api/me/ui", headers=h, json={"reset": True}).json()["custom"] is False
        # Einfacher Modus: Form wird nicht geliefert
        c.put("/api/me/ui", headers=h, json={"mode": "simple"})
        assert "form" not in c.get("/api/home/blocks?ids=form,streaks", headers=h).json()
