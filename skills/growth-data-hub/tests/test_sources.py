"""Each source's response parser, fed the fixture JSON (same shapes the live APIs return)."""
from conftest import END, START, fixture
from sources import clarity, ga4, ghl, google_ads, meta


def test_meta_counts_only_exact_lead_action(cfg):
    out = meta.parse(fixture("meta"), cfg, START, END)
    # fixtures carry 'lead', 'onsite_conversion.lead_grouped' and 'offsite_conversion.fb_pixel_lead' for the same leads
    assert out["totals"]["leads"] == 74 + 31 + 18
    assert out["totals"]["spend"] == 4150.0


def test_meta_lead_count_ignores_substring_matches():
    acts = [{"action_type": "lead", "value": "5"}, {"action_type": "onsite_conversion.lead_grouped", "value": "5"},
            {"action_type": "offsite_conversion.fb_pixel_lead", "value": "4"}]
    assert meta.lead_count(acts) == 5
    assert meta.lead_count(None) == 0


def test_meta_rates_and_sorting(cfg):
    out = meta.parse(fixture("meta"), cfg, START, END)
    c = out["campaigns"][0]
    assert c["name"] == "Consult offer - broad"
    assert abs(c["ctr"] - 2700 / 210000) < 1e-9
    assert abs(c["cpm"] - 2600 / 210000 * 1000) < 1e-9
    zero = next(a for a in out["ads"] if a["leads"] == 0)
    assert zero["cpl"] is None


def test_meta_missing_reports_both_keys(cfg):
    assert len(meta.missing({"meta": {"ad_account_id": "act_YOUR_AD_ACCOUNT_ID"}}, {})) == 2
    assert meta.missing({"meta": {"ad_account_id": "123"}}, {"META_ACCESS_TOKEN": "x"}) == []


def test_google_ads_micros_and_impression_share(cfg):
    out = google_ads.parse(fixture("google_ads"), cfg, START, END)
    g1 = next(c for c in out["campaigns"] if c["name"].startswith("Search - treatment"))
    assert g1["spend"] == 1400.0 and g1["lost_is_budget"] == 0.32 and g1["lost_is_rank"] == 0.12
    pmax = next(c for c in out["campaigns"] if c["type"] == "PERFORMANCE_MAX")
    assert pmax["lost_is_budget"] is None  # no search impression share outside Search
    assert out["totals"]["spend"] == 2400.0 and out["totals"]["leads"] == 52.0
    assert abs(out["totals"]["ctr"] - (610 + 260) / (9800 + 8600)) < 1e-9  # Search only
    assert out["changes"][0]["what"] == "CAMPAIGN_BUDGET"


def test_google_ads_change_event_query_has_date_filter_and_limit():
    q = google_ads.CHANGES_GAQL.format(start="2026-10-01", end="2026-10-12 23:59:59")
    assert "change_event.change_date_time >=" in q and "LIMIT" in q


def test_google_ads_customer_id_dashes():
    assert google_ads.missing({"google_ads": {"customer_id": "123-456-7890"}},
                              {k: "x" for k in ("GOOGLE_ADS_DEVELOPER_TOKEN", "GOOGLE_ADS_CLIENT_ID",
                                                "GOOGLE_ADS_CLIENT_SECRET", "GOOGLE_ADS_REFRESH_TOKEN")}) == []


def test_ga4_aggregates(cfg):
    out = ga4.parse(fixture("ga4"), cfg, START, END)
    sm = {r["source_medium"]: r for r in out["by_source_medium"]}
    assert sm["facebook / paid"]["sessions"] == 2450 + 520
    lp = {r["landing_page"]: r for r in out["by_landing_page"]}
    assert lp["/consult"]["sessions"] == 2450 + 330
    assert out["totals"]["sessions"] == sum(r["sessions"] for r in out["rows"])


def test_clarity_by_path(cfg):
    out = clarity.parse(fixture("clarity"), cfg, START, END)
    p = {r["path"]: r for r in out["pages"]}
    assert p["/consult"]["sessions"] == 410
    assert p["/consult"]["dead_click_pct"] == 14.2 and p["/consult"]["rage_click_pct"] == 5.1
    assert p["/consult"]["quickback_pct"] == 22.4 and p["/consult"]["scroll_depth"] == 31.0
    assert out["num_days"] == 3


def test_clarity_path_normaliser():
    assert clarity._path("https://www.example.com/book/?utm_source=x#top") == "/book"
    assert clarity._path("https://www.example.com") == "/"
    assert clarity._path("") == ""


def test_clarity_tolerates_metric_name_spacing():
    raw = {"metrics": [{"metricName": "Dead Click Count", "information": [
        {"sessionsWithMetricPercentage": 9.5, "URL": "https://a.example/x"}]}]}
    assert clarity.parse(raw, {}, START, END)["pages"][0]["dead_click_pct"] == 9.5


def test_ghl_window_filter_and_cancelled(cfg):
    out = ghl.parse(fixture("ghl"), cfg, START, END)
    ids = {c["id"] for c in out["contacts"]}
    assert "old1" not in ids and "old2" not in ids
    assert out["totals"]["contacts"] == 95 + 48 + 22 + 9
    assert all(a["status"] != "cancelled" for a in out["appointments"])


def test_ghl_stage_kinds(cfg):
    st = cfg["ghl"]["stages"]
    assert ghl._stage_kind("Call booked", "open", st) == "booked"
    assert ghl._stage_kind("NO SHOW", "open", st) == "no_show"
    assert ghl._stage_kind("Contacted", "won", st) == "won"
    assert ghl._stage_kind("Contacted", "open", st) is None


def test_ghl_contacts_search_sends_numeric_page_limit(monkeypatch):
    sent = []

    class Fake(ghl.Client):
        def req(self, method, path, body=None, version=None):
            sent.append(body)
            return {"contacts": [{"id": "a"}, {"id": "a"}], "total": 2}

    out = ghl._contacts(Fake("t", "loc"), START, END)
    assert isinstance(sent[0]["pageLimit"], int)
    assert [c["id"] for c in out] == ["a"]  # de-duplicated


def test_ghl_sends_browser_user_agent():
    assert "Mozilla" in ghl.Client("t", "loc").h["User-Agent"]


def test_load_env_strips_inline_comments(tmp_path, monkeypatch):
    from sources.common import load_env
    p = tmp_path / ".env"
    p.write_text("A=abc123   # a comment\nB=\nC='x # kept'\nexport D=d\n# E=no\n")
    for k in list(__import__("os").environ):
        if k in ("A", "B", "C", "D"):
            monkeypatch.delenv(k)
    env = load_env(str(p))
    assert env["A"] == "abc123" and env["B"] == "" and env["C"] == "x # kept" and env["D"] == "d" and "E" not in env


def test_error_hints():
    from sources.common import hint
    assert "system user" in hint('{"error":{"message":"Invalid OAuth access token","code":190}}')
    assert "comment" in hint('{"error": "invalid_client"}')
    assert "Viewer" in hint("User does not have sufficient permissions for this property")
    assert hint("something else") == ""


def test_ghl_warns_when_no_stage_matches(cfg):
    import copy
    c = copy.deepcopy(cfg)
    c["ghl"]["stages"] = {"booked": ["Nothing like this"]}
    raw = fixture("ghl")
    for o in raw["opportunities"]:
        o["status"] = "open"
    out = ghl.parse(raw, c, START, END)
    assert any("Your stage names" in w and "Call booked" in w for w in out["warnings"])


def test_ghl_reads_both_attribution_shapes(cfg):
    out = ghl.parse(fixture("ghl"), cfg, START, END)
    raw = {c["id"]: c for c in fixture("ghl")["contacts"]}
    listed = [c for c in out["contacts"] if "attributions" in raw[c["id"]]]
    assert listed and any(c["gclid"] for c in listed) and any(c["utm_source"] == "facebook" for c in listed)
    assert ghl._attribution({"attributions": [{"utmSource": "x"}, {"utmSource": "y", "isFirst": True}]})["utmSource"] == "y"
    assert ghl._attribution({}) == {}


def test_meta_throttle_codes():
    from sources.common import _meta_throttled

    class R:
        def __init__(self, code):
            self.code = code

        def json(self):
            return {"error": {"code": self.code}}
    assert _meta_throttled(R(17)) and _meta_throttled(R(80004)) and not _meta_throttled(R(190))


def test_impression_share_caps():
    import render
    assert render._is(0.0999) == "&lt;10%" and render._is(0.9001) == "&gt;90%" and render._is(None) == "n/a"
