import pytest

from app.advisor.clothing import advise, wind_chill_loss


def base(**kw):
    d = dict(temp_avg=22.0, wind_kmh=8, duration_min=120)
    d.update(kw)
    return advise(**d)


def test_wind_chill():
    assert wind_chill_loss(25, 30) == 0.0
    assert 2.5 < wind_chill_loss(10, 30) < 4.5  # 10 °C bei 30 km/h fühlen sich wie ca. 6,6 °C an
    assert wind_chill_loss(15, 30) == pytest.approx(wind_chill_loss(10, 30) / 2, abs=1.2)
    assert wind_chill_loss(5, 3) == 0.0


def test_warm_day_is_short_short():
    a = base(temp_avg=27.0, uv=7)
    assert a.headline == "Kurz / kurz"
    assert "Sonnencreme" in a.groups["Sonne"]
    assert "Regen & Wind" not in a.groups


def test_cool_day_needs_long_clothes_and_gloves():
    a = base(temp_avg=9.0, wind_kmh=5)
    assert a.headline.startswith("Lang / lang")
    assert any("handschuhe" in x.lower() for x in a.groups["Hände"])
    assert any("Überschuhe" in x for x in a.groups["Füße"])


def test_colder_means_more_clothes_monotonic():
    order = ["Kurz / kurz", "Kurz mit Armlingen / kurz", "Lang / Beinlinge", "Lang / lang"]
    seen = []
    for t in (26, 21, 17, 13, 9, 5, 1, -4):
        a = base(temp_avg=t, wind_kmh=0)
        key = a.headline if a.headline in order else "Lang / lang"
        seen.append(order.index(key))
    assert seen == sorted(seen)


def test_rain_dresses_one_step_warmer_and_adds_rain_gear():
    dry = base(temp_avg=15.0, wind_kmh=0, precip_mm=0.0)
    wet = base(temp_avg=15.0, wind_kmh=0, precip_mm=2.0, wet_minutes=60, precip_prob=90)
    assert wet.effective_temp < dry.effective_temp - 3
    assert any("Regenjacke" in x for x in wet.groups["Regen & Wind"])
    assert "Regen & Wind" not in dry.groups


def test_intensity_and_sensitivity():
    easy = base(temp_avg=14.0, intensity="easy")
    hard = base(temp_avg=14.0, intensity="hard")
    cold = base(temp_avg=14.0, sensitivity="cold")
    assert easy.effective_temp < hard.effective_temp
    assert cold.effective_temp < base(temp_avg=14.0).effective_temp


def test_short_rides_start_warmer_long_rides_pack_reserve():
    short = base(temp_avg=18.0, duration_min=40)
    long_ = base(temp_avg=18.0, duration_min=300)
    assert short.effective_temp < base(temp_avg=18.0).effective_temp
    assert any("Notfall" in x for x in long_.groups["Mitnehmen"])
    assert "Mitnehmen" not in base(temp_avg=22.0, duration_min=90).groups


def test_temperature_swing_darkness_and_ice():
    a = base(temp_avg=14.0, temp_start=8.0, temp_min=8.0, temp_max=17.0, dark_minutes=40)
    assert any("Armlinge" in x for x in a.groups["Mitnehmen"])
    assert "Licht vorn und hinten" in a.groups["Sichtbarkeit"]
    ice = base(temp_avg=1.0, temp_min=-1.0, precip_mm=0.4, precip_prob=70)
    assert any("Glatteis" in w for w in ice.warnings)


def test_invalid():
    with pytest.raises(ValueError):
        advise(temp_avg=10, intensity="rasant")
