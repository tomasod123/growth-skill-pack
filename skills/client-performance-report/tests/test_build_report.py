import copy
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(HERE, "scripts"))
import build_report as br  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
REPORT = os.path.join(FIX, "report.json")
BRAND = os.path.join(FIX, "brand.yaml")


def load_report():
    with open(REPORT) as f:
        return json.load(f)


def visible(html):
    """Text a reader sees: drop the style block, inline images and tags."""
    html = re.sub(r"<style>.*?</style>", "", html, flags=re.S)
    html = re.sub(r"src='[^']*'", "", html)
    return re.sub(r"<[^>]+>", " ", html)


@pytest.fixture
def built(tmp_path):
    paths = br.build(REPORT, BRAND, str(tmp_path))
    return {k: open(v, encoding="utf-8").read() for k, v in paths.items()}


def write_report(tmp_path, r):
    p = tmp_path / "report.json"
    p.write_text(json.dumps(r))
    return str(p)


def test_writes_both_pages(built):
    assert set(built) == {"internal.html", "client.html"}
    for html in built.values():
        assert html.startswith("<!doctype html>")
        assert "name='viewport'" in html


def test_self_contained_no_js_no_external_assets(built):
    for html in built.values():
        assert "<script" not in html.lower()
        assert not re.search(r"(src|href)=['\"]https?://", html)
        assert "@import" not in html
    assert "data:image/svg+xml;base64," in built["client.html"]  # local logo is inlined


def test_client_numbers_are_exact(built):
    r = load_report()
    t = r["funnel"]["total"]
    text = visible(built["client.html"])
    assert f"${t['cpl']:,.2f}" in text  # $37.64, full pennies
    for n in (t["leads"], t["booked"], t["showed"]):
        assert re.search(rf"\b{n}\b", text)
    meta = next(c for c in r["funnel"]["channels"] if c["key"] == "meta")
    assert f"${meta['cpl']:,.2f}" in text


def test_speed_to_lead_nudge_uses_real_numbers(built):
    r = load_report()
    meta = next(c for c in r["funnel"]["channels"] if c["key"] == "meta")
    text = visible(built["client.html"])
    assert "biggest difference" in text
    assert f"{meta['leads'] - meta['booked']} people who enquired" in text
    assert f"{meta['lead_to_booked'] * 100:.1f}%" in text
    assert "within 5 minutes" in text


def test_no_nudge_when_booking_rates_are_healthy(tmp_path):
    r = load_report()
    for ch in r["funnel"]["channels"]:
        ch["booked"] = int(ch["leads"] * 0.5)
        ch["lead_to_booked"] = ch["booked"] / ch["leads"]
    br.build(write_report(tmp_path, r), BRAND, str(tmp_path / "o"))
    text = visible((tmp_path / "o" / "client.html").read_text())
    assert "biggest difference" not in text
    assert "have not booked yet" not in text


def test_wins_come_before_next_steps(built):
    html = built["client.html"]
    assert html.index("What is going well") < html.index("What we are doing next")
    assert html.index("What is going well") < html.index("biggest difference")


def test_client_hides_internal_plumbing(built):
    text = visible(built["client.html"])
    for word in br.INTERNAL_WORDS + ["Static - price list v1", "Retargeting - site visitors", "lead form"]:
        assert word.lower() not in text.lower(), word


def test_client_is_a_draft_by_default_and_approved_drops_banner(tmp_path, built):
    assert "Draft for review" in built["client.html"]
    br.build(REPORT, BRAND, str(tmp_path / "ok"), approved=True)
    assert "Draft for review" not in (tmp_path / "ok" / "client.html").read_text()
    assert "noindex" in built["client.html"]


def test_brand_applied(built):
    html = built["client.html"]
    assert "#0F5257" in html and "#E0A458" in html
    assert "'Lato'" in html
    assert "Prepared by Example Growth Team for Demo Clinic" in html


def test_internal_is_candid(built):
    r = load_report()
    html = built["internal.html"]
    text = visible(html)
    assert "The constraint" in text
    assert br.e(r["constraint"]["trigger"]) in html
    for a in r["actions"]:
        assert br.e(a["action"]) in html and br.e(a["owner"]) in html
    assert "Risks and caveats" in text
    assert "the CRM got 95" in text  # lead gap is surfaced internally


def test_skipped_source_listed_internally_not_in_client(tmp_path):
    r = load_report()
    r["sources"]["clarity"] = {"state": "skipped", "why": "missing CLARITY_API_TOKEN"}
    br.build(write_report(tmp_path, r), BRAND, str(tmp_path / "o"))
    assert "missing CLARITY_API_TOKEN" in (tmp_path / "o" / "internal.html").read_text()
    assert "CLARITY_API_TOKEN" not in (tmp_path / "o" / "client.html").read_text()


def test_html_is_escaped(tmp_path):
    b = tmp_path / "brand.yaml"
    b.write_text("client_name: \"<script>alert(1)</script> Clinic\"\ncolors: {primary: '#112233', accent: '#445566'}\n")
    br.build(REPORT, str(b), str(tmp_path / "o"))
    for name in ("client.html", "internal.html"):
        html = (tmp_path / "o" / name).read_text()
        assert "<script>" not in html and "&lt;script&gt;" in html


def test_bad_colour_rejected(tmp_path):
    b = tmp_path / "brand.yaml"
    b.write_text("client_name: Demo\ncolors: {primary: 'red;}body{display:none', accent: '#445566'}\n")
    with pytest.raises(ValueError):
        br.build(REPORT, str(b), str(tmp_path / "o"))


def test_missing_logo_falls_back_to_wordmark(tmp_path):
    b = tmp_path / "brand.yaml"
    b.write_text("client_name: Demo Clinic\nlogo: nope.png\n")
    br.build(REPORT, str(b), str(tmp_path / "o"))
    assert "class='wordmark'" in (tmp_path / "o" / "client.html").read_text()


def test_not_a_report_is_rejected(tmp_path):
    p = tmp_path / "x.json"
    p.write_text("{}")
    with pytest.raises(ValueError):
        br.build(str(p), BRAND, str(tmp_path / "o"))


def test_no_em_dashes(built):
    for html in built.values():
        assert chr(0x2014) not in html and chr(0x2013) not in html


def test_other_currency_uses_code_or_symbol(tmp_path):
    r = load_report()
    r["currency"] = "GBP"
    br.build(write_report(tmp_path, r), BRAND, str(tmp_path / "o"))
    assert "£37.64" in (tmp_path / "o" / "client.html").read_text()
    r["currency"] = "SEK"
    br.build(write_report(tmp_path, copy.deepcopy(r)), BRAND, str(tmp_path / "p"))
    assert "SEK 37.64" in (tmp_path / "p" / "client.html").read_text()


def test_cli(tmp_path, capsys):
    br.main(["--report", REPORT, "--brand", BRAND, "--out", str(tmp_path / "cli")])
    out = capsys.readouterr().out
    assert "DRAFT" in out and (tmp_path / "cli" / "client.html").exists()
