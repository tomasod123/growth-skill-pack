"""The constraint finder and the action list."""
import copy

import constraint
import funnel
import hub


def run(data, cfg, bm):
    f = funnel.build(data, cfg)
    res = constraint.analyse(data, f, bm, cfg)
    hub.fill_actions(res, data, f, cfg)
    return f, res


def test_demo_constraint_is_meta_booking_rate(data, cfg, bm):
    _, res = run(data, cfg, bm)
    c = res["constraint"]
    assert (c["channel"], c["stage"]) == ("meta", "lead_to_booked")
    assert res["actions"][0] is c


def test_five_actions_each_with_number_owner_time(data, cfg, bm):
    _, res = run(data, cfg, bm)
    assert len(res["actions"]) == 5
    for a in res["actions"]:
        assert any(ch.isdigit() for ch in a["trigger"]) and a["owner"] and a["minutes"] > 0


def test_zero_lead_ad_flagged(data, cfg, bm):
    _, res = run(data, cfg, bm)
    assert any(f["stage"] == "kill_ad" and f["label"] == "Static - price list v1" for f in res["findings"])


def test_budget_lost_only_when_converting_under_target(data, cfg, bm):
    _, res = run(data, cfg, bm)
    budget = [f for f in res["findings"] if f["stage"] == "lost_is_budget"]
    assert [f["label"] for f in budget] == ["Search - treatment terms"]


def test_worst_page_and_its_channels(data, cfg, bm):
    _, res = run(data, cfg, bm)
    page = next(f for f in res["findings"] if f["type"] == "page")
    assert page["label"] == "/consult" and page["channel"] == "meta"
    assert "/thank-you" not in [p["path"] for p in res["pages"]]  # under the Clarity session minimum


def test_lead_gap_flag(data, cfg, bm):
    _, res = run(data, cfg, bm)
    gap = next(f for f in res["findings"] if f["type"] == "lead_gap")
    assert gap["channel"] == "meta" and abs(gap["value"] - 95 / 123) < 1e-9


def test_small_samples_are_not_judged(data, cfg, bm):
    b = copy.deepcopy(bm)
    b["minimums"]["leads"] = 10_000
    _, res = run(data, cfg, b)
    assert not any(f["stage"] == "lead_to_booked" for f in res["findings"])


def test_healthy_funnel_has_no_constraint_but_still_five_actions(data, cfg, bm):
    b = copy.deepcopy(bm)
    for ch in b["funnel"].values():
        for v in ch.values():
            v["low"] = 0.0
    b["costs"] = {}
    b["search"] = {}
    b["clarity"] = {}
    b["lead_match"]["min_crm_share"] = 0
    _, res = run(data, cfg, b)
    assert res["constraint"] is None and len(res["actions"]) == 5


def test_benchmark_override_per_channel(bm):
    assert constraint._bench(bm, "meta", "ctr")["low"] == 0.008
    assert constraint._bench(bm, "google_ads", "lead_to_booked") == bm["funnel"]["default"]["lead_to_booked"]


def test_demo_end_to_end(tmp_path):
    assert hub.main(["--demo", "--out", str(tmp_path)]) == 0
    html = (tmp_path / "report.html").read_text()
    assert "<script" not in html and "viewport" in html
    md = (tmp_path / "ACTIONS.md").read_text()
    assert md.count("\n1. ") == 1 and "\n5. " in md


def test_no_source_overwrites_stale_actions(tmp_path):
    (tmp_path / "ACTIONS.md").write_text("old demo actions")
    (tmp_path / "report.html").write_text("old")
    cfg = tmp_path / "config.yaml"
    cfg.write_text("currency: USD\n")
    env = tmp_path / ".env"
    env.write_text("")
    import os
    for k in [k for k in os.environ if k.startswith(("META_", "GOOGLE_ADS_", "GA4_", "CLARITY_", "GHL_"))]:
        del os.environ[k]
    assert hub.main(["--config", str(cfg), "--env", str(env), "--out", str(tmp_path)]) == 2
    assert "No report" in (tmp_path / "ACTIONS.md").read_text()
    assert not (tmp_path / "report.html").exists()
