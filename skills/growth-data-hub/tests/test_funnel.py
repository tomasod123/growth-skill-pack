"""The join: channel matching, outcomes per contact, funnel maths."""
import funnel


def test_source_medium_matching(cfg):
    assert funnel.match_source_medium("facebook / paid", cfg) == "meta"
    assert funnel.match_source_medium("ig / paid", cfg) == "meta"
    assert funnel.match_source_medium("google / cpc", cfg) == "google_ads"
    assert funnel.match_source_medium("google / organic", cfg) == "other"
    assert funnel.match_source_medium("instagram.com / referral", cfg) == "other"


def test_contact_matching(cfg):
    m = lambda **k: funnel.match_contact(dict({"tags": []}, **k), cfg)
    assert m(fbclid=True) == "meta"
    assert m(gclid=True) == "google_ads"
    assert m(session_source="paid search") == "google_ads"
    assert m(utm_source="google", utm_medium="cpc") == "google_ads"
    assert m(utm_source="google", utm_medium="organic") == "other"  # utm_medium must also match
    assert m(source="Facebook Lead Form") == "meta"
    assert m(tags=["meta lead"]) == "meta"
    assert m(source="form") == "other"


def test_outcomes_combine_appointments_and_stages():
    g = {"contacts": [{"id": "a"}, {"id": "b"}, {"id": "c"}, {"id": "d"}],
         "appointments": [{"contact_id": "a", "status": "confirmed"}, {"contact_id": "b", "status": "noshow"},
                          {"contact_id": "c", "status": "noshow"}, {"contact_id": "zz", "status": "showed"}],
         "opportunities": [{"contact_id": "c", "kind": "showed"}, {"contact_id": "d", "kind": "won"}]}
    o = funnel.contact_outcomes(g)
    assert o["a"] == {"booked": True, "showed": False, "no_show": False, "won": False}
    assert o["b"]["no_show"] and not o["b"]["showed"]
    assert o["c"]["showed"] and not o["c"]["no_show"]  # rebooked and showed
    assert o["d"] == {"booked": True, "showed": True, "no_show": False, "won": True}
    assert "zz" not in o


def test_build_demo_funnel(data, cfg):
    f = funnel.build(data, cfg)
    ch = {c["key"]: c for c in f["channels"]}
    m = ch["meta"]
    assert m["spend"] == 4150.0 and m["clicks"] == 4220 and m["sessions"] == 2450 + 520 + 330
    assert m["leads"] == 95 and m["platform_leads"] == 123  # CRM is the source of truth for leads
    assert m["booked"] == 14 and m["showed"] == 9 and m["no_show"] == 3 and m["won"] == 3
    assert abs(m["lead_to_booked"] - 14 / 95) < 1e-9
    assert abs(m["show_rate"] - 9 / 12) < 1e-9
    assert abs(m["cpl"] - 4150 / 95) < 1e-9
    assert ch["google_ads"]["booked"] == 22
    assert ch["other"]["spend"] == 0 and ch["other"]["cpl"] is None
    t = f["total"]
    assert t["leads"] == 174 and t["spend"] == 6550.0
    assert abs(t["click_to_session"] - (3300 + 1150) / (4220 + 1280)) < 1e-9


def test_build_without_crm_falls_back_to_platform_leads(data, cfg):
    d = dict(data, ghl=None)
    f = funnel.build(d, cfg)
    m = next(c for c in f["channels"] if c["key"] == "meta")
    assert m["lead_source"] == "platform" and m["leads"] == 123 and m["booked"] is None
    assert m["lead_to_booked"] is None and m["show_rate"] is None


def test_build_only_one_source(data, cfg):
    f = funnel.build({"meta": data["meta"]}, cfg)
    assert [c["key"] for c in f["channels"]] == ["meta"]
    assert f["total"]["sessions"] is None


def test_rates_handle_zero():
    r = funnel.rates({"spend": 0, "impressions": 0, "clicks": 0, "sessions": 0, "leads": 0,
                      "booked": 0, "showed": 0, "no_show": 0, "won": 0})
    assert r["ctr"] is None and r["cpl"] is None and r["show_rate"] is None


def test_unknown_leads_are_not_zero(data, cfg):
    f = funnel.build({"ga4": data["ga4"], "meta": data["meta"]}, cfg)
    g = next(c for c in f["channels"] if c["key"] == "google_ads")
    assert g["leads"] is None and g["session_to_lead"] is None
    m = next(c for c in f["channels"] if c["key"] == "meta")
    assert m["leads"] == 123
