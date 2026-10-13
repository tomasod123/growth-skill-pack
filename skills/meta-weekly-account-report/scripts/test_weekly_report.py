"""Tests for the weekly report parser and flags. Run: python -m pytest scripts -q"""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import weekly_report as wr  # noqa: E402
from meta_graph import GraphClient, GraphError, count_leads  # noqa: E402


# ---------------------------------------------------------------- parser

def test_count_leads_exact_action_type_only():
    actions = [
        {"action_type": "lead", "value": "7"},
        {"action_type": "onsite_conversion.lead_grouped", "value": "7"},
        {"action_type": "offsite_conversion.fb_pixel_lead", "value": "3"},
        {"action_type": "leadgen.other", "value": "2"},
        {"action_type": "link_click", "value": "90"},
    ]
    assert count_leads(actions) == 7
    assert count_leads(None) == 0
    assert count_leads([]) == 0


def test_parse_row_computes_link_ctr_cpm_cpl():
    m = wr.parse_row({"spend": "200.00", "impressions": "10000", "inline_link_clicks": "150",
                      "frequency": "2.5", "actions": [{"action_type": "lead", "value": "4"}]})
    assert m.spend == 200 and m.impressions == 10000 and m.clicks == 150 and m.leads == 4
    assert m.ctr == pytest.approx(1.5)
    assert m.cpm == pytest.approx(20.0)
    assert m.cpl == pytest.approx(50.0)
    assert m.frequency == 2.5


def test_parse_row_handles_missing_fields():
    m = wr.parse_row({})
    assert m.spend == 0 and m.leads == 0 and m.ctr is None and m.cpl is None and m.frequency is None


def test_join_rows_pairs_periods():
    this = [{"ad_id": "a1", "ad_name": "New name", "spend": "10", "campaign_id": "c1"}]
    prior = [{"ad_id": "a1", "ad_name": "Old name", "spend": "5"},
             {"ad_id": "a2", "ad_name": "Paused ad", "spend": "3"}]
    out = wr.join_rows(this, prior, "ad")
    assert out["a1"].this.spend == 10 and out["a1"].prior.spend == 5
    assert out["a1"].name == "New name"
    assert out["a2"].this.spend == 0 and out["a2"].prior.spend == 3


def test_delta_arrows():
    assert wr.delta(110, 100) == "▲ 10%"
    assert wr.delta(60, 100) == "▼ 40%"
    assert wr.delta(100, 100) == "= 0%"
    assert wr.delta(5, 0) == "▲ new"
    assert wr.delta(0, 0) == "same"
    assert wr.delta(None, 3) == "n/a"


def test_windows_end_yesterday():
    from datetime import date
    this, prior = wr.windows(date(2026, 3, 12))
    assert this == (date(2026, 3, 5), date(2026, 3, 11))
    assert prior == (date(2026, 2, 26), date(2026, 3, 4))


# ---------------------------------------------------------------- flags

def ad(id_, spend, leads, freq=1.0, p_spend=0.0, p_leads=0):
    e = wr.Entity(id=id_, name=id_)
    e.this = wr.Metrics(spend=spend, impressions=1000, clicks=10, leads=leads, frequency=freq)
    e.prior = wr.Metrics(spend=p_spend, impressions=1000, clicks=10, leads=p_leads)
    return e


def test_kill_candidates():
    ads = {
        "zero": ad("zero", 80, 0),        # 2x target with 0 leads -> kill
        "under": ad("under", 79, 0),      # just under 2x, keep watching
        "dear": ad("dear", 250, 3),       # CPL 83 > 80 -> kill
        "fine": ad("fine", 120, 4),       # CPL 30 -> fine
    }
    kills = {a.id for a, _ in wr.find_kills(ads, 40, 2.0, "GBP")}
    assert kills == {"zero", "dear"}
    assert wr.find_kills(ads, None, 2.0, "GBP") == []


def test_best_ad_needs_min_leads_and_skips_kills():
    ads = {
        "few": ad("few", 10, 1),         # CPL 10 but only 1 lead
        "good": ad("good", 90, 3),       # CPL 30
        "ok": ad("ok", 120, 3),          # CPL 40
    }
    assert wr.find_best(ads, 3).id == "good"
    assert wr.find_best(ads, 3, exclude={"good"}).id == "ok"
    assert wr.find_best(ads, 10) is None


def test_fatigue_flag():
    ads = {"tired": ad("tired", 10, 1, freq=4.0), "fresh": ad("fresh", 10, 1, freq=3.99)}
    assert [a.id for a in wr.find_fatigue(ads, 4.0)] == ["tired"]


@pytest.mark.parametrize("this_spend,this_leads,prior_spend,prior_leads,expect", [
    (100, 6, 100, 10, 0.4),     # spend held, leads -40% -> flag
    (120, 3, 100, 10, 0.7),     # spend rose, leads -70% -> flag
    (100, 7, 100, 10, None),    # -30% only
    (50, 2, 100, 10, None),     # spend fell too, so a normal slowdown
    (100, 0, 100, 0, None),     # no prior leads to compare
])
def test_sudden_drop(this_spend, this_leads, prior_spend, prior_leads, expect):
    e = ad("x", this_spend, this_leads, p_spend=prior_spend, p_leads=prior_leads)
    fall = wr.is_sudden_drop(e, 0.40, 0.90)
    assert (fall is None) if expect is None else fall == pytest.approx(expect)


def test_pacing_uses_minor_units():
    camps = {"c1": ad("c1", 350, 5), "c2": ad("c2", 700, 5)}
    meta = [{"id": "c1", "name": "c1", "daily_budget": "10000"},      # 100.00/day -> 700/wk
            {"id": "c2", "name": "c2", "daily_budget": "10000"},
            {"id": "c3", "name": "c3", "lifetime_budget": "90000"},
            {"id": "c4", "name": "c4", "effective_status": "PAUSED", "daily_budget": "100"}]
    rows = {r["id"]: r for r in wr.compute_pacing(meta, camps, "GBP", {}, wr.DEFAULTS)}
    assert rows["c1"]["daily"] == 100 and rows["c1"]["status"] == "underspending"
    assert rows["c2"]["status"] == "on pace"
    assert "lifetime" in rows["c3"]["status"]
    assert "c4" not in rows


def test_pacing_zero_decimal_currency():
    rows = wr.compute_pacing([{"id": "c1", "name": "c1", "daily_budget": "10000"}],
                             {"c1": ad("c1", 70000, 1)}, "JPY", {}, wr.DEFAULTS)
    assert rows[0]["daily"] == 10000 and rows[0]["status"] == "on pace"


def test_actions_capped_at_three_and_drop_first():
    res = wr.AccountResult(cfg={"target_cpl": 40}, currency="GBP", account=ad("acct", 100, 1),
                           campaigns={}, ads={})
    res.drops = [("account", res.account, 0.5)]
    res.kills = [(ad("k", 100, 0), "spent £100 with 0 leads")]
    res.fatigued = [ad("f", 10, 1, freq=5)]
    res.pacing = [{"name": "p", "status": "underspending", "ratio": 0.3}]
    acts = wr.build_actions(res, wr.DEFAULTS)
    assert len(acts) == 3
    assert "lead form to CRM sync" in acts[0]


# ---------------------------------------------------------------- Graph client

class FakeResp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class FakeSession:
    def __init__(self, replies):
        self.replies, self.calls = list(replies), []

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params))
        return self.replies.pop(0)


def test_paging_follows_next():
    s = FakeSession([
        FakeResp(200, {"data": [{"n": 1}], "paging": {"next": "https://graph.example.com/next"}}),
        FakeResp(200, {"data": [{"n": 2}], "paging": {}}),
    ])
    rows = GraphClient("tok", session=s, sleep=lambda _: None).get_all("act_X/insights", {"level": "ad"})
    assert rows == [{"n": 1}, {"n": 2}]
    assert s.calls[1] == ("https://graph.example.com/next", None)


@pytest.mark.parametrize("code", [17, 80004, 4, 613])
def test_rate_limit_backoff_then_success(code):
    slept = []
    s = FakeSession([
        FakeResp(400, {"error": {"code": code, "message": "User request limit reached"}}),
        FakeResp(200, {"data": [{"ok": True}]}),
    ])
    rows = GraphClient("tok", session=s, sleep=slept.append).get_all("act_X/insights")
    assert rows == [{"ok": True}] and len(slept) == 1


def test_non_retryable_error_raises_without_token():
    s = FakeSession([FakeResp(400, {"error": {"code": 190, "message": "Invalid OAuth access token"}})])
    with pytest.raises(GraphError) as exc:
        GraphClient("secret-token", session=s, sleep=lambda _: None).get_all("act_X/insights")
    assert exc.value.code == 190 and "secret-token" not in str(exc.value)


def test_rate_limit_gives_up_after_retries():
    s = FakeSession([FakeResp(400, {"error": {"code": 17, "message": "limit"}})] * 3)
    with pytest.raises(GraphError):
        GraphClient("tok", session=s, max_retries=2, sleep=lambda _: None).get_all("act_X/insights")


# ---------------------------------------------------------------- end to end

def test_demo_runs_offline(tmp_path, capsys):
    assert wr.main(["--demo", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Demo Clinic UK (GBP)" in out and "Demo Clinic US (USD)" in out
    assert "lead form to CRM sync" in out
    md = next(tmp_path.glob("weekly_report_*.md")).read_text()
    assert "| GBP |" in md and "| USD |" in md      # totals kept per currency
    assert "Price static" in md and "underspending" in md
    # 21 leads in the UK demo account: lead_grouped / fb_pixel_lead not double counted
    assert "| Leads | 21 |" in md
