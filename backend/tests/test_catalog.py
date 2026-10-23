from app.catalog import BIKE_TEMPLATES, CATALOG, catalog_payload


def test_every_template_category_exists():
    for bike_type, cats in BIKE_TEMPLATES.items():
        for c in cats:
            assert c in CATALOG, (bike_type, c)


def test_rules_have_an_interval_and_sane_wet_factor():
    for comp in CATALOG.values():
        assert comp.rules, comp.category
        for r in comp.rules:
            assert r.interval_km or r.interval_months, r.label
            assert 1.0 <= r.wet_factor <= 5.0, r.label


def test_chain_counts_wet_km_double():
    wear = [r for r in CATALOG["chain"].rules if "wechseln" in r.label][0]
    assert wear.wet_factor == 2.0 and wear.interval_km == 3000


def test_payload_is_serializable():
    import json
    json.dumps(catalog_payload())
