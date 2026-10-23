import pytest

from app.advisor.tires import PSI_PER_BAR, berto_rear_psi, real_width, recommend


def test_formula_matches_published_worked_example():
    # 83 kg System, 28 mm Reifen auf 21 mm Maulweite: veröffentlicht 68/73 psi
    r = recommend(rider_kg=75, bike_kg=8, luggage_kg=0, tire_width_mm=28, rim_inner_mm=21, bike_type="road")
    assert r.real_width_mm == 29.5
    assert (r.front_psi, r.rear_psi) == (68, 73)


def test_more_weight_more_pressure_wider_tire_less():
    base = dict(bike_kg=8, tire_width_mm=28, bike_type="road")
    light = recommend(rider_kg=60, **base)
    heavy = recommend(rider_kg=90, **base)
    wide = recommend(rider_kg=90, **{**base, "tire_width_mm": 32})
    assert light.rear_psi < heavy.rear_psi
    assert wide.rear_psi < heavy.rear_psi
    assert 6 <= (heavy.rear_psi - light.rear_psi) / 3 <= 11  # grob 6 bis 11 psi je 10 kg Fahrergewicht


def test_front_is_lower_than_rear():
    r = recommend(rider_kg=75, bike_kg=9, tire_width_mm=30)
    assert r.front_psi < r.rear_psi


def test_surface_wet_and_tube_adjustments():
    base = dict(rider_kg=75, bike_kg=9, tire_width_mm=40, bike_type="gravel")
    asphalt = recommend(**base)
    gravel = recommend(surface="gravel", **base)
    wet = recommend(wetness="wet", **base)
    tube = recommend(tubeless=False, **base)
    assert gravel.rear_psi < asphalt.rear_psi * 0.88
    assert wet.rear_psi == pytest.approx(asphalt.rear_psi * 0.90, abs=1.5)
    assert tube.rear_psi > asphalt.rear_psi


def test_hookless_cap_and_warning():
    r = recommend(rider_kg=110, bike_kg=9, tire_width_mm=25, hookless=True)
    assert r.rear_bar <= 5.0 and any("Hookless" in w for w in r.warnings)
    wide_rim = recommend(rider_kg=110, bike_kg=9, tire_width_mm=25, hookless=True, rim_inner_mm=30)
    assert wide_rim.rear_psi <= 60


def test_real_width_prefers_measurement():
    assert real_width(28, 21, "road", 30.4) == 30.4
    assert real_width(40, None, "gravel", None) == pytest.approx(40 + 0.3 + 0.4 * 6)


def test_invalid_input():
    with pytest.raises(ValueError):
        recommend(rider_kg=0, bike_kg=8, tire_width_mm=28)
    with pytest.raises(ValueError):
        recommend(rider_kg=70, bike_kg=8, tire_width_mm=28, surface="mond")


def test_bar_conversion_consistent():
    r = recommend(rider_kg=75, bike_kg=8, tire_width_mm=28)
    assert abs(r.rear_bar - r.rear_psi / PSI_PER_BAR) < 0.06
    assert berto_rear_psi(100, 30) > 0
