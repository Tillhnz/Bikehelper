"""Tests für die Import-Module. Sie brauchen nur die Standardbibliothek und laufen ohne Datenbank."""
import gzip
import io
import math
import zipfile
from datetime import datetime, timedelta

import pytest

from app.importers import polyline
from app.importers.parsers import (
    ParseError, is_cycling, parse_activity_file, parse_time,
)
from app.importers.strava_export import clean_gear_name, gear_key, index_export

DEG_PER_M = 1 / (math.radians(1) * 6371008.8)


def make_gpx(n=1000, speed=8.0, with_time=True, gap_at=None, gap_s=120, sport="cycling",
             start=datetime(2026, 10, 23, 7, 15, 0)):
    """Gleichmäßige Fahrt nach Norden; Höhe steigt auf den ersten 500 Punkten um 100 m."""
    pts = []
    for i in range(n):
        t = start + timedelta(seconds=i + (gap_s if gap_at is not None and i >= gap_at else 0))
        lat = 53.55 + i * speed * DEG_PER_M
        ele = 100 * min(i, 500) / 500
        time = f"<time>{t.strftime('%Y-%m-%dT%H:%M:%SZ')}</time>" if with_time else ""
        pts.append(f'<trkpt lat="{lat:.7f}" lon="10.0000000"><ele>{ele:.1f}</ele>{time}</trkpt>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<gpx version="1.1" creator="test" xmlns="http://www.topografix.com/GPX/1/1">'
        f"<trk><name>Testfahrt</name><type>{sport}</type><trkseg>{''.join(pts)}</trkseg></trk></gpx>"
    ).encode()


def test_gpx_distance_time_elevation():
    a = parse_activity_file("ride.gpx", make_gpx())
    assert a.name == "Testfahrt"
    assert a.start == datetime(2026, 10, 23, 7, 15, 0)
    assert abs(a.distance_km - 7.992) < 0.01
    assert a.moving_time_s == 999
    assert 95 <= a.elevation_m <= 100.5
    assert a.sport == "cycling" and is_cycling(a.sport)
    assert abs(a.start_lat - 53.55) < 1e-6 and abs(a.start_lng - 10.0) < 1e-6


def test_pause_is_not_counted_as_moving_time():
    a = parse_activity_file("ride.gpx", make_gpx(gap_at=500))
    assert 997 <= a.moving_time_s <= 998


def test_gzip_is_unpacked():
    a = parse_activity_file("123.gpx.gz", gzip.compress(make_gpx()))
    assert abs(a.distance_km - 7.992) < 0.01


def test_name_falls_back_to_file_name():
    data = make_gpx().replace(b"<name>Testfahrt</name>", b"")
    assert parse_activity_file("Morgenrunde.gpx", data).name == "Morgenrunde"


def test_route_without_timestamps_is_rejected():
    with pytest.raises(ParseError, match="Zeitstempel"):
        parse_activity_file("route.gpx", make_gpx(with_time=False))


def test_entity_definitions_are_rejected():
    evil = b'<?xml version="1.0"?><!DOCTYPE gpx [<!ENTITY a "aaaa">]><gpx>&a;</gpx>'
    with pytest.raises(ParseError, match="Entity"):
        parse_activity_file("x.gpx", evil)


def test_unknown_format_and_broken_xml():
    with pytest.raises(ParseError):
        parse_activity_file("notes.txt", b"hello")
    with pytest.raises(ParseError):
        parse_activity_file("broken.gpx", b"<gpx><trk>")


def test_tcx_uses_cumulative_distance():
    pts = []
    for i in range(100):
        t = (datetime(2026, 5, 1, 8, 0, 0) + timedelta(seconds=i)).strftime("%Y-%m-%dT%H:%M:%SZ")
        pts.append(
            f"<Trackpoint><Time>{t}</Time><Position><LatitudeDegrees>{53.55 + i * 7 * DEG_PER_M:.7f}"
            f"</LatitudeDegrees><LongitudeDegrees>10.0</LongitudeDegrees></Position>"
            f"<AltitudeMeters>20</AltitudeMeters><DistanceMeters>{7 * i}</DistanceMeters></Trackpoint>"
        )
    tcx = (
        '<?xml version="1.0"?><TrainingCenterDatabase xmlns="http://www.garmin.com/xmlschemas/TrainingCenterDatabase/v2">'
        f'<Activities><Activity Sport="Biking"><Lap><Track>{"".join(pts)}</Track></Lap></Activity></Activities>'
        "</TrainingCenterDatabase>"
    ).encode()
    a = parse_activity_file("ride.tcx", tcx)
    assert a.sport == "Biking"
    assert a.distance_km == pytest.approx(0.693, abs=0.001)
    assert a.moving_time_s == 99


def test_polyline_reference_value_and_roundtrip():
    pts = [(38.5, -120.2), (40.7, -120.95), (43.252, -126.453)]
    assert polyline.encode(pts) == "_p~iF~ps|U_ulLnnqC_mqNvxq`@"
    for (la, lo), (la2, lo2) in zip(pts, polyline.decode(polyline.encode(pts))):
        assert abs(la - la2) < 1e-5 and abs(lo - lo2) < 1e-5


def test_long_track_is_downsampled():
    a = parse_activity_file("long.gpx", make_gpx(n=5000))
    assert 2 <= len(polyline.decode(a.polyline)) <= 601


def test_parse_time_variants():
    expected = datetime(2026, 10, 23, 7, 15, 0)
    assert parse_time("2026-10-23T07:15:00Z") == expected
    assert parse_time("2026-10-23T09:15:00+02:00") == expected
    assert parse_time("2026-10-23T07:15:00.123456789Z") == expected.replace(microsecond=123456)
    assert parse_time("kein Datum") is None


def test_is_cycling():
    for s in ("Ride", "Gravel Ride", "Mountain Bike Ride", "E-Bike Ride", "Virtual Ride", "cycling road", "Biking", None):
        assert is_cycling(s), s
    for s in ("Run", "Walk", "Swim", "Hike", "Alpine Ski"):
        assert not is_cycling(s), s


# ---------- Strava-Export ----------

CSV_HEADER = (
    "Activity ID,Activity Date,Activity Name,Activity Type,Activity Description,Elapsed Time,Distance,"
    "Max Heart Rate,Relative Effort,Commute,Activity Private Note,Activity Gear,Filename,Elapsed Time,Distance"
)


def make_export(csv_text, files, bikes_csv=None):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("activities.csv", csv_text)
        if bikes_csv:
            zf.writestr("bikes.csv", bikes_csv)
        for name, data in files.items():
            zf.writestr(name, data)
    buf.seek(0)
    return zipfile.ZipFile(buf)


def test_strava_export_with_csv():
    csv_text = "\n".join([
        CSV_HEADER,
        '111,"Oct 23, 2026, 7:15:00 AM",Morgenrunde,Ride,,3600,30.5,,,false,,Canyon Endurace,activities/111.gpx.gz,3600,30500',
        '222,"Oct 24, 2026, 7:15:00 AM",Laufen,Run,,1800,5.0,,,false,,,activities/222.gpx,1800,5000',
        '333,"Oct 25, 2026, 7:15:00 AM",Manuell,Ride,,3600,20,,,false,,Canyon Endurace,,3600,20000',
        '444,"Oct 26, 2026, 7:15:00 AM",Gravel,Gravel Ride,,3600,40,,,false,,Canyon+Grail,activities/444.fit.gz,3600,40000',
    ])
    bikes = "Bike Name,Bike Brand,Bike Model,Default Sport Types\nCanyon+Endurace,Canyon,Endurace CF SL,Ride\n"
    zf = make_export(csv_text, {"activities/111.gpx.gz": b"x", "activities/222.gpx": b"x", "activities/444.fit.gz": b"x"}, bikes)
    idx = index_export(zf)
    assert idx.used_csv
    assert idx.rows_without_file == 1
    assert [(e.strava_id, e.type, e.gear) for e in idx.entries] == [
        (111, "Ride", "Canyon Endurace"),
        (222, "Run", None),
        (444, "Gravel Ride", "Canyon Grail"),
    ]
    assert idx.entries[0].name == "Morgenrunde" and idx.entries[0].path == "activities/111.gpx.gz"
    assert idx.bikes[gear_key("Canyon Endurace")] == ("Canyon Endurace", "Canyon", "Endurace CF SL")


def test_strava_export_without_filename_column_falls_back_to_files():
    csv_text = "Aktivitäts-ID,Datum,Name,Typ\n1,x,y,Fahrt\n"
    zf = make_export(csv_text, {"activities/555.fit.gz": b"x", "activities/556.gpx": b"x", "media/foto.jpg": b"x"})
    idx = index_export(zf)
    assert not idx.used_csv
    assert [e.strava_id for e in idx.entries] == [555, 556]
    assert all(e.gear is None for e in idx.entries)


def test_gear_name_cleaning():
    assert clean_gear_name("Canyon+Endurace+CF") == "Canyon Endurace CF"
    assert clean_gear_name("Rad 7+") == "Rad 7+"  # echtes Pluszeichen bleibt erhalten
    assert gear_key("  Canyon Endurace ") == gear_key("canyon+endurace")


def test_german_export_is_read_by_content_not_by_header_language():
    csv_text = "\n".join([
        "Aktivitäts-ID,Aktivitätsdatum,Aktivitätsname,Aktivitätsart,Beschreibung,Ausrüstung der Aktivität,Dateiname",
        '16000000001,"23.10.2026, 07:15:00",Morgenrunde,Radfahrt,,Canyon Endurace,activities/16000000001.fit.gz',
        '16000000002,"24.10.2026, 07:15:00",Abendrunde,Radfahrt,,Canyon Endurace,activities/16000000002.fit.gz',
    ])
    zf = make_export(csv_text, {"activities/16000000001.fit.gz": b"x", "activities/16000000002.fit.gz": b"x"},
                     "Name des Fahrrads,Marke,Modell\nCanyon Endurace,Canyon,CF SL\n")
    idx = index_export(zf)
    assert idx.used_csv and idx.gear_column
    assert [e.gear for e in idx.entries] == ["Canyon Endurace", "Canyon Endurace"]
    assert idx.entries[0].name == "Morgenrunde"
    assert idx.bikes[gear_key("Canyon Endurace")] == ("Canyon Endurace", "Canyon", "CF SL")


def test_gear_column_found_by_matching_bike_names_with_odd_header():
    csv_text = "\n".join([
        "Id,Datum,Titel,Sorte,Zeug,Datei",
        '16000000001,x,A,Fahrt,Canyon Endurace,activities/16000000001.gpx',
        '16000000002,x,B,Fahrt,,activities/16000000002.gpx',
    ])
    zf = make_export(csv_text, {"activities/16000000001.gpx": b"x", "activities/16000000002.gpx": b"x"},
                     "Bike Name\nCanyon Endurace\n")
    idx = index_export(zf)
    assert idx.gear_column
    assert [e.gear for e in idx.entries] == ["Canyon Endurace", None]


def test_csv_without_gear_column_is_reported():
    csv_text = "Activity ID,Activity Name,Filename\n16000000001,A,activities/16000000001.gpx\n"
    idx = index_export(make_export(csv_text, {"activities/16000000001.gpx": b"x"}))
    assert idx.used_csv and not idx.gear_column


def test_is_cycling_localized_types():
    for t in ("Radfahrt", "Fahrradfahrt", "Virtuelle Radfahrt", "Cyclisme", "Vélo", "Ciclismo"):
        assert is_cycling(t), t
    for t in ("Lauf", "Run", "Wanderung", "Schwimmen", "Treadmill"):
        assert not is_cycling(t), t
