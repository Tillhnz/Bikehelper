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
    from app.catalog import CHAIN_LUBES, LUBE_LABELS, WAX_LUBE_LABEL, WAX_VARIANTS, chain_rules, wax_interval_km

    oil_lube, oil_wear = chain_rules("oil")
    wax_lube, wax_wear = chain_rules("wax")
    assert chain_rules(None) == chain_rules("oil") == chain_rules("unbekannt")
    assert chain_rules("hot_wax") == chain_rules("drip_wax") == chain_rules("wax")  # frühere Werte
    assert oil_lube.interval_km == 200 and wax_lube.interval_km > oil_lube.interval_km
    assert oil_wear.interval_km < wax_wear.interval_km
    assert wax_lube.wet_factor > oil_lube.wet_factor  # Wachs verliert bei Nässe schneller seinen Schutz
    assert wax_lube.label == WAX_LUBE_LABEL and oil_wear.label == wax_wear.label == "Kette wechseln"
    assert set(CHAIN_LUBES) == {"oil", "wax"}
    assert {v["lube"].label for v in CHAIN_LUBES.values()} <= LUBE_LABELS
    assert "Kette neu wachsen (Heißwachs)" in LUBE_LABELS  # alte Bezeichnungen werden weiter erkannt

    # Das Intervall der Wachsregel hängt von der Wachsart der letzten Wartung ab
    assert set(WAX_VARIANTS) == {"hot_wax", "drip_wax"}
    assert wax_interval_km(WAX_LUBE_LABEL, "hot_wax", 500) == 500
    assert wax_interval_km(WAX_LUBE_LABEL, "drip_wax", 500) == 250
    assert wax_interval_km(WAX_LUBE_LABEL, None, 500) == 500
    assert wax_interval_km("Kette wechseln", "drip_wax", 5000) == 5000


def test_every_catalog_rule_has_guides():
    from app.catalog import CATALOG, CHAIN_LUBES, GUIDES, guides_for
    labels = {r.label for c in CATALOG.values() for r in c.rules}
    for spec in CHAIN_LUBES.values():
        labels |= {spec["lube"].label, spec["wear"].label}
    assert not [l for l in labels if l not in GUIDES]
    for gs in GUIDES.values():
        for g in gs:
            assert g.url.startswith("https://") and g.title and g.source
    assert guides_for("gibt es nicht") == []


def test_every_category_has_a_visual_check():
    from app.catalog import CATALOG, CHECKS, LEGACY_CATEGORIES, catalog_payload
    for cat in CATALOG:
        if cat in LEGACY_CATEGORIES:
            continue
        c = CHECKS[cat]
        assert c.how and c.good and c.bad and c.act and c.tools, cat
    assert "tires" in CHECKS
    assert set(catalog_payload()["checks"]) == set(CHECKS)
