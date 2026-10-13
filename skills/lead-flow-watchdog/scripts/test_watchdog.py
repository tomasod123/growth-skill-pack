"""Tests for the lead-flow watchdog. Run: python -m pytest scripts -q"""

import sys
from datetime import date, datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import watchdog as wd  # noqa: E402
from detect import CRITICAL, INFO, WARNING, DayStats, detect, worst  # noqa: E402
from ghl_client import GHLClient, GHLError, classify  # noqa: E402
from meta_graph import GraphClient, count_leads  # noqa: E402

RULES = {"tags": ["Facebook Lead"], "sources": ["facebook", "instagram"], "utm_sources": ["fb", "ig"]}


def layers(alerts):
    return {a.layer: a.severity for a in alerts}


def stats(**kw):
    base = dict(name="Biz", currency="GBP", target_cpl=40.0, crm_tagged=5, crm_source=5, crm_meta=5,
                crm_meta_avg7=5.0, meta_leads=5, meta_spend=200.0, meta_leads_avg7=5.0,
                meta_spend_7d=1400.0, meta_leads_7d=35)
    base.update(kw)
    return DayStats(**base)


# ---------------------------------------------------------------- counting and matching

def test_meta_leads_exact_action_type():
    acts = [{"action_type": "lead", "value": "4"},
            {"action_type": "onsite_conversion.lead_grouped", "value": "4"},
            {"action_type": "offsite_conversion.fb_pixel_lead", "value": "2"}]
    assert count_leads(acts) == 4


@pytest.mark.parametrize("contact,expect", [
    ({"tags": ["facebook lead"], "source": ""}, (True, False)),
    ({"tags": ["FACEBOOK LEAD "], "source": "Facebook Form Lead"}, (True, True)),
    ({"tags": [], "source": "instagram"}, (False, True)),
    ({"tags": [], "attributions": [{"utmSource": "FB"}]}, (False, True)),
    ({"tags": [], "attributionSource": {"utm_source": "ig"}}, (False, True)),
    ({"tags": ["website enquiry"], "source": "website form",
      "attributions": [{"utmSource": "google"}]}, (False, False)),
    ({"tags": ["facebook lead old"], "source": ""}, (False, False)),   # tags match exactly, not by substring
])
def test_classify(contact, expect):
    assert classify(contact, RULES) == expect


# ---------------------------------------------------------------- detection layers

def test_healthy_day_is_ok():
    alerts = detect(stats())
    assert alerts == [] and worst(alerts) == "OK"


def test_processing_break():
    a = detect(stats(crm_tagged=0, crm_source=4, crm_meta=4))
    assert layers(a)["processing-break"] == CRITICAL
    assert "integration-break" not in layers(a)


def test_partial_processing_break():
    a = detect(stats(crm_tagged=1, crm_source=6, crm_meta=6, meta_leads=6))
    assert layers(a)["partial-processing-break"] == WARNING


def test_integration_break():
    a = detect(stats(crm_tagged=0, crm_source=0, crm_meta=0, meta_leads=7))
    assert layers(a)["integration-break"] == CRITICAL
    assert a[0].severity == CRITICAL


def test_integration_break_needs_meta_leads():
    a = detect(stats(crm_tagged=0, crm_source=0, crm_meta=0, meta_leads=0, meta_spend=5.0,
                     meta_leads_avg7=0.5))
    assert "integration-break" not in layers(a)


def test_crm_gap_warning():
    a = detect(stats(crm_tagged=3, crm_source=3, crm_meta=3, meta_leads=10, meta_spend=400))
    assert layers(a)["crm-gap"] == WARNING


def test_small_gap_from_merges_is_fine():
    a = detect(stats(crm_tagged=4, crm_source=4, crm_meta=4, meta_leads=5))
    assert "crm-gap" not in layers(a)


def test_spend_no_leads():
    a = detect(stats(meta_leads=0, meta_spend=45.0, crm_tagged=0, crm_source=0, crm_meta=0))
    assert layers(a)["spend-no-leads"] == CRITICAL
    assert "delivery-drop" not in layers(a)


def test_spend_no_leads_under_threshold():
    a = detect(stats(meta_leads=0, meta_spend=20.0, crm_tagged=0, crm_source=0, crm_meta=0,
                     meta_leads_avg7=1.0))
    assert "spend-no-leads" not in layers(a)


def test_delivery_drop_and_ramp():
    s = stats(meta_leads=2, meta_spend=80.0, meta_leads_avg7=6.0, crm_tagged=2, crm_source=2, crm_meta=2)
    assert layers(detect(s))["delivery-drop"] == WARNING
    s.in_ramp = True
    assert layers(detect(s))["delivery-drop"] == INFO


def test_delivery_drop_uses_crm_without_meta():
    s = stats(meta_leads=None, meta_spend=None, meta_leads_avg7=None, crm_tagged=1, crm_source=1,
              crm_meta=1, crm_meta_avg7=5.0)
    assert layers(detect(s))["delivery-drop"] == WARNING


def test_cpl_vs_target_and_trailing():
    a = detect(stats(meta_leads=5, meta_spend=450.0))          # CPL 90 vs target 40, 7-day 40
    assert layers(a)["cpl-vs-target"] == WARNING
    assert layers(a)["cpl-vs-trailing"] == WARNING
    a = detect(stats(meta_leads=5, meta_spend=320.0, meta_spend_7d=1400, meta_leads_7d=35))  # CPL 64
    assert layers(a)["cpl-vs-target"] == INFO and "cpl-vs-trailing" not in layers(a)


def test_data_errors_are_info_and_skip_checks():
    a = detect(stats(crm_error="GHL 401", crm_tagged=0, crm_source=0, crm_meta=0))
    assert layers(a)["data-check"] == INFO
    assert "integration-break" not in layers(a)


# ---------------------------------------------------------------- GHL client

class Resp:
    def __init__(self, status, body):
        self.status_code, self._body = status, body

    def json(self):
        return self._body


class FakeGHL:
    def __init__(self, replies):
        self.replies, self.bodies, self.headers = list(replies), [], None

    def post(self, url, json=None, headers=None, timeout=None):
        self.bodies.append(json)
        self.headers = headers
        return self.replies.pop(0)


def contact(cid, when="2026-03-10T09:00:00.000Z"):
    return {"id": cid, "dateAdded": when, "tags": []}


START = datetime(2026, 3, 10, tzinfo=timezone.utc)
END = datetime(2026, 3, 11, tzinfo=timezone.utc)


def test_ghl_search_request_shape_and_paging():
    s = FakeGHL([
        Resp(200, {"contacts": [contact("a"), contact("b")], "total": 3}),
        Resp(200, {"contacts": [contact("b"), contact("c")], "total": 3}),   # "b" repeated across pages
    ])
    rows = GHLClient("tok", session=s, page_limit=2).search_contacts("loc1", START, END)
    assert sorted(c["id"] for c in rows) == ["a", "b", "c"]
    assert len(s.bodies) == 2                                    # stopped at the reported total
    body = s.bodies[0]
    assert isinstance(body["pageLimit"], int) and body["page"] == 1
    assert body["filters"][0]["field"] == "dateAdded" and body["filters"][0]["operator"] == "range"
    assert s.headers["Version"] == "2021-07-28"
    assert s.headers["User-Agent"].startswith("Mozilla/5.0")


def test_ghl_drops_out_of_window_contacts():
    s = FakeGHL([Resp(200, {"contacts": [contact("a"), contact("old", "2026-03-01T09:00:00Z")], "total": 2})])
    rows = GHLClient("tok", session=s).search_contacts("loc1", START, END)
    assert [c["id"] for c in rows] == ["a"]


def test_ghl_stops_on_empty_page():
    s = FakeGHL([Resp(200, {"contacts": [contact("a")]}), Resp(200, {"contacts": []})])
    rows = GHLClient("tok", session=s, page_limit=1).search_contacts("loc1", START, END)
    assert len(rows) == 1 and len(s.bodies) == 2


def test_ghl_retries_429_then_errors_clearly():
    slept = []
    s = FakeGHL([Resp(429, {}), Resp(200, {"contacts": [], "total": 0})])
    GHLClient("tok", session=s, sleep=slept.append).search_contacts("loc1", START, END)
    assert len(slept) == 1
    with pytest.raises(GHLError, match="pageLimit"):
        GHLClient("tok", session=FakeGHL([Resp(422, {})])).search_contacts("loc1", START, END)


# ---------------------------------------------------------------- Meta + end to end

def test_meta_days_by_date():
    class S:
        def get(self, url, params=None, timeout=None):
            assert params["time_increment"] == 1 and params["level"] == "account"
            return Resp(200, {"data": [
                {"date_start": "2026-03-09", "spend": "100", "actions": [{"action_type": "lead", "value": "2"}]},
                {"date_start": "2026-03-10", "spend": "50.5", "actions": []}]})
    out = wd.meta_days(GraphClient("t", session=S()), "act_X", date(2026, 3, 10))
    assert out == {"2026-03-09": (100.0, 2), "2026-03-10": (50.5, 0)}


def test_crm_days_bucket_by_local_date():
    rows = [{"id": "a", "dateAdded": "2026-03-10T23:30:00Z", "tags": ["facebook lead"]}]
    out = wd.crm_days(rows, RULES, ZoneInfo("Australia/Sydney"))
    assert "2026-03-11" in out and out["2026-03-11"]["tagged"] == 1


def test_demo_runs_offline(tmp_path, capsys):
    assert wd.main(["--demo", "--out", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Demo Clinic North: OK" in out
    assert "Demo Clinic South: CRITICAL" in out and "none are tagged" in out
    assert "Demo Clinic East: CRITICAL" in out and "no Meta-tagged contacts" in out
    assert "Demo Clinic West: CRITICAL" in out and "no leads" in out
    assert (tmp_path / "watchdog_2026-03-10.md").exists()
