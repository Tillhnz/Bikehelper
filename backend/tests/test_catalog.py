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


def test_chain_rules_by_lube():
    from app.catalog import CHAIN_LUBES, LUBE_LABELS, chain_rules

    oil_lube, oil_wear = chain_rules("oil")
    wax_lube, wax_wear = chain_rules("hot_wax")
    drip_lube, drip_wear = chain_rules("drip_wax")
    assert chain_rules(None) == chain_rules("oil") == chain_rules("unbekannt")
    assert oil_lube.interval_km == 200 and wax_lube.interval_km > drip_lube.interval_km > oil_lube.interval_km
    assert oil_wear.interval_km < drip_wear.interval_km < wax_wear.interval_km
    assert wax_lube.wet_factor > oil_lube.wet_factor  # Wachs verliert bei Nässe schneller seinen Schutz
    assert all(w.label == "Kette wechseln" for w in (oil_wear, wax_wear, drip_wear))
    assert LUBE_LABELS == {v["lube"].label for v in CHAIN_LUBES.values()} and len(LUBE_LABELS) == 3
