from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.importers.parsers import Point, power_curve, second_by_second
from app.main import app
from app.stats import deep as D
from app.stats.overview import Row

TZ = ZoneInfo("Europe/Berlin")


def _rows(n=30):
    out = []
    t = datetime(2026, 5, 1, 8)
    for i in range(n):
        t += timedelta(days=1 + i % 3)
        km = 30 + i
        out.append(Row(
            id=i + 1, name=f"Runde {i}", bike_id=1 + i % 2, start=t, km=km, time_s=int(km / (24 + i % 5) * 3600),
            elev_m=km * 7, temp_c=5 + i % 20, wind_kmh=5 + i % 30, wet_minutes=0 if i % 4 else 40,
            avg_power=150 + i, curve={"300": 300, "1200": 240, "3600": 210},
        ))
    return out


def test_power_curve_from_points():
    t0 = datetime(2026, 1, 1)
    pts = [Point(time=t0 + timedelta(seconds=i), pwr=200 if i < 600 else 100) for i in range(1800)]
    pc = power_curve(pts)
    assert pc["300"] == 200 and pc["1200"] == 150
    assert power_curve(pts[:5]) is None  # zu kurz


def test_pause_does_not_fake_power():
    t0 = datetime(2026, 1, 1)
    pts = [Point(time=t0 + timedelta(seconds=i), pwr=300) for i in range(60)]
    pts += [Point(time=t0 + timedelta(seconds=600 + i), pwr=300) for i in range(60)]
    pc = power_curve(pts)
    assert pc["60"] == 300 and "300" in pc and pc["300"] < 300  # die Pause zählt als 0 W


def test_ftp_is_95_percent_of_20_minutes():
    ftp, basis = D.estimate_ftp({1200: 260, 3600: 200})
    assert round(ftp) == 247 and "20" in basis
    ftp, _ = D.estimate_ftp({1200: 200, 3600: 195})
    assert round(ftp) == 195  # beste Stunde, wenn sie höher liegt als 95 % der 20 Minuten
    assert D.estimate_ftp({300: 400}) == (None, None)


def test_power_block_has_ftp_zones_and_form():
    rows = _rows()
    out = D.build_power(rows, TZ, date(2026, 7, 1), 80)
    assert out["has_curve"] and out["ftp"] == 228 and out["ftp_wkg"] == 2.85
    assert [z["name"][:2] for z in out["zones"]] == ["Z1", "Z2", "Z3", "Z4", "Z5", "Z6", "Z7"]
    assert out["form"] and set(out["form"][0]) == {"date", "tss", "fitness", "fatigue", "form"}


def test_power_block_without_data():
    rows = [Row(id=1, name="x", bike_id=None, start=datetime(2026, 5, 1), km=20, time_s=3600, elev_m=100)]
    assert D.build_power(rows, TZ, date(2026, 7, 1), None)["has_curve"] is False


def test_profile_curve_for_old_rides():
    prof = {"d": [i * 0.5 for i in range(1, 301)], "s": [30] * 300, "p": [200] * 150 + [250] * 150}
    assert D.curve_from_profile({"profile": prof})["300"] == 250
    assert D.curve_from_profile({"profile": {}}) is None


def test_conditions_patterns_bikes():
    rows = _rows()
    c = D.build_conditions(rows)
    assert c["rides"] == 30 and c["temp"] and c["wet_dry"]["wet_rides"] >= 3
    p = D.build_patterns(rows, TZ, date(2026, 7, 1))
    assert len(p["weekday"]) == 7 and p["median_pause_days"] is not None
    b = D.build_bike_compare(rows, {1: "A", 2: "B"}, {1: 2})
    assert {x["name"] for x in b["bikes"]} == {"A", "B"} and abs(sum(x["share"] for x in b["bikes"]) - 100) < 0.3


def test_routes_group_similar_rides_only():
    rows = _rows(8)
    base = [(52.0 + 0.0005 * k, 13.0 + 0.0003 * k) for k in range(200)]
    other = [(52.3 + 0.0005 * k, 13.3 + 0.0003 * k) for k in range(200)]
    for r in rows:
        r.km, r.time_s = 20.0, 3000
    paths = {r.id: (base if r.id <= 5 else other) for r in rows}
    out = D.build_routes(rows, paths, TZ)
    assert [x["rides"] for x in out["routes"]] == [5, 3]  # die drei anderen liegen 30 km entfernt: eigene Runde, nicht vermischt


def test_forecast_uses_pace():
    st = {"status": "ok", "progress": 0.5, "interval_km_eff": 3000, "effective_km": 1500, "months_since": 1, "interval_months": None}
    it = D.forecast_item("Kette", "K", "Rad", st, 100, date(2026, 7, 1))
    assert it["days"] == 105 and it["basis"] == "Kilometer" and it["km_left"] == 1500
    assert D.forecast_item("x", "K", "Rad", {"status": "unknown", "progress": 0}, 100, date(2026, 7, 1)) is None


def test_ride_impact_fitness_and_ftp():
    rows = _rows(20)
    last = rows[-1]
    last.curve = {"300": 400, "1200": 300, "3600": 250}  # klar besser als alle davor
    out = D.ride_impact(rows, last.id, TZ)
    assert out["load"]["fitness"]["delta"] > 0 and out["load"]["fatigue"]["delta"] > out["load"]["fitness"]["delta"]
    assert out["load"]["form"]["delta"] < 0 and out["load"]["level"] in ("locker", "normal", "fordernd", "sehr hart", "sehr locker")
    assert out["ftp"]["available"] and out["ftp"]["delta"] > 0 and {r["label"] for r in out["ftp"]["records"]} == {"5 min", "20 min", "60 min"}
    first = D.ride_impact(rows, rows[0].id, TZ)  # erste Fahrt: nichts davor
    assert first["load"]["fitness"]["before"] == 0 and first["ftp"]["records"]
    rows[3].curve = None
    assert D.ride_impact(rows, rows[3].id, TZ)["ftp"] == {"available": False}
    assert D.ride_impact(rows, 9999, TZ) is None


def test_ride_analysis_zones_np_and_hr():
    t0 = datetime(2026, 1, 1)
    pts = [Point(time=t0 + timedelta(seconds=i), pwr=250 if i % 120 < 60 else 100, hr=130 + i // 60, cad=90 if i % 100 else 0) for i in range(3600)]
    details = {"v": 2, "avg_power": 175, "max_power": 250, "avg_hr": 160, "max_hr": 189, "avg_cadence": 89, **second_by_second(pts)}
    assert details["np"] > details["avg_power"] and details["kj"] == 630 and details["dec"] > 5
    out = D.ride_analysis(details, ftp=250, ftp_note="x", max_hr=190, max_hr_note="y", weight_kg=70, best_curve={300: 260, 1200: 150}, moving_time_s=3600)
    p = out["power"]
    assert p["vi"] > 1 and p["if"] and p["tss"] and p["wkg"] == 2.5
    z = {r["name"][:2]: r["seconds"] for r in p["zones"]}
    assert z["Z4"] == 1800 and z["Z1"] == 1800 and sum(z.values()) == 3600  # 250 W = 100 % FTP (Z4), 100 W = 40 % (Z1)
    assert p["zones"][-1]["to"] is None
    assert sum(r["pct"] for r in out["hr"]["zones"]) > 99 and out["hr"]["ef"] and out["hr"]["decoupling"] > 5
    assert out["cadence"]["buckets"][0]["seconds"] == 36 and out["exact"]
    peaks = {x["label"]: x for x in p["peaks"]}
    assert peaks["20 min"]["is_best"] and not peaks["5 min"]["is_best"]
    # alte Fahrt ohne Sekundenauswertung: genähert, ohne Entkopplung
    old = {"avg_power": 200, "avg_hr": 150, "avg_cadence": 85, "profile": {"d": [i * 0.5 for i in range(1, 101)], "s": [30] * 100, "p": [200] * 100, "h": [150] * 100, "c": [85] * 100}}
    o = D.ride_analysis(old, ftp=250, ftp_note=None, max_hr=190, max_hr_note=None, weight_kg=None, best_curve=None, moving_time_s=6000)
    assert not o["exact"] and o["power"]["zones"] and "decoupling" not in o["hr"]
    assert D.ride_analysis(None, ftp=None, ftp_note=None, max_hr=None, max_hr_note=None, weight_kg=None, best_curve=None, moving_time_s=0) == {"exact": False}


def test_endpoints_answer_for_new_account():
    with TestClient(app) as c:
        c.post("/api/auth/register", json={"email": "deep@example.com", "password": "geheim1234"})
        t = c.post("/api/auth/login", json={"email": "deep@example.com", "password": "geheim1234"}).json()["access_token"]
        h = {"Authorization": f"Bearer {t}"}
        for path in ("power", "conditions", "patterns", "bikes", "routes", "forecast"):
            r = c.get(f"/api/stats/{path}", headers=h)
            assert r.status_code == 200, (path, r.text)
        assert c.get("/api/stats/power", headers=h).json()["has_curve"] is False
        assert c.get("/api/stats/ride-impact/12345", headers=h).status_code == 404
        assert c.get("/api/stats/ride-analysis/12345", headers=h).status_code == 404
        assert c.put("/api/settings/profile", headers=h, json={"weight_kg": 70, "max_hr": 188}).json()["max_hr"] == 188
        assert c.put("/api/settings/profile", headers=h, json={"max_hr": 50}).status_code == 422
