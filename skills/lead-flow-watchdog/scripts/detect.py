"""Layered lead-flow checks. Pure functions: numbers in, alerts out."""

from __future__ import annotations

from dataclasses import dataclass, field

CRITICAL, WARNING, INFO = "CRITICAL", "WARNING", "INFO"
RANK = {CRITICAL: 0, WARNING: 1, INFO: 2}

DEFAULT_THRESHOLDS = {
    "processing_break_min_source": 3,     # >= this many Meta-source contacts, 0 tagged -> critical
    "partial_break_min_source": 5,        # >= this many Meta-source contacts ...
    "partial_break_tagged_share": 0.30,   # ... and under 30% tagged -> warning
    "integration_min_meta_leads": 1,      # Meta leads needed before "CRM has 0" is a break
    "crm_gap_min_meta_leads": 5,          # CRM gap check needs this many Meta leads
    "crm_gap_share": 0.50,                # CRM Meta-looking contacts under 50% of Meta leads -> warning
    "no_lead_spend_cpl_multiple": 1.0,    # spend >= 1x target CPL with 0 leads -> spend with no leads
    "no_lead_spend_min": 10.0,            # used when there is no target CPL
    "drop_ratio": 0.50,                   # leads under 50% of the 7-day average -> delivery drop
    "drop_min_avg": 2.0,                  # only when the 7-day average is at least 2 a day
    "cpl_spike_multiple": 2.0,            # CPL over 2x target -> warning
    "cpl_watch_multiple": 1.5,            # CPL over 1.5x target -> info
    "cpl_trailing_multiple": 2.0,         # CPL over 2x the trailing 7-day CPL -> warning
    "cpl_trailing_min_leads": 3,          # trailing CPL needs this many leads in the 7 days
}


@dataclass
class DayStats:
    """One business, one day. Meta fields are None when no ad account is configured."""
    name: str
    currency: str = ""
    target_cpl: float | None = None
    crm_tagged: int = 0             # contacts with a Meta tag
    crm_source: int = 0             # contacts whose source / UTM looks like Meta (tagged or not)
    crm_meta: int = 0               # contacts matching either rule
    crm_meta_avg7: float = 0.0      # daily average of crm_meta over the 7 days before
    tag_rules: bool = True          # False when no tags are configured
    meta_leads: int | None = None
    meta_spend: float | None = None
    meta_leads_avg7: float | None = None
    meta_spend_7d: float | None = None
    meta_leads_7d: int | None = None
    in_ramp: bool = False
    crm_error: str | None = None
    meta_error: str | None = None

    @property
    def meta_cpl(self) -> float | None:
        if self.meta_leads and self.meta_spend is not None:
            return self.meta_spend / self.meta_leads
        return None

    @property
    def trailing_cpl(self) -> float | None:
        if self.meta_leads_7d and self.meta_spend_7d is not None:
            return self.meta_spend_7d / self.meta_leads_7d
        return None


@dataclass
class Alert:
    severity: str
    layer: str
    headline: str
    detail: list[str] = field(default_factory=list)
    next_steps: list[str] = field(default_factory=list)


def money(v: float | None, cur: str) -> str:
    return "n/a" if v is None else f"{v:,.2f} {cur}".strip()


def detect(s: DayStats, thresholds: dict | None = None) -> list[Alert]:
    t = {**DEFAULT_THRESHOLDS, **(thresholds or {})}
    out: list[Alert] = []
    cur = s.currency
    has_meta = s.meta_leads is not None and not s.meta_error

    if s.crm_error:
        out.append(Alert(INFO, "data-check", "CRM pull failed, CRM checks skipped",
                         [s.crm_error], ["Check the GHL token, scopes and location id (see SETUP.md)."]))
    if s.meta_error:
        out.append(Alert(INFO, "data-check", "Meta pull failed, Meta checks skipped",
                         [s.meta_error], ["Check META_ACCESS_TOKEN and the ad account assignment."]))
    crm_ok = not s.crm_error
    critical = False

    # 1. Processing break: Meta leads reach the CRM but the tagging / workflow is not catching them.
    if crm_ok and s.tag_rules:
        if s.crm_source >= t["processing_break_min_source"] and s.crm_tagged == 0:
            critical = True
            out.append(Alert(CRITICAL, "processing-break",
                             "Meta leads are arriving in the CRM but none are tagged",
                             [f"Meta-source contacts: {s.crm_source}", "Meta-tagged contacts: 0"],
                             ["Open the workflow that tags Meta leads. A new or copied lead form is "
                              "probably missing from its trigger's form filter.",
                              "Add the form, then tag and re-run the workflow for the untagged contacts."]))
        elif (s.crm_source >= t["partial_break_min_source"]
              and s.crm_tagged < s.crm_source * t["partial_break_tagged_share"]):
            out.append(Alert(WARNING, "partial-processing-break",
                             "Most Meta leads in the CRM are not tagged",
                             [f"Meta-source contacts: {s.crm_source}",
                              f"Meta-tagged contacts: {s.crm_tagged} "
                              f"({s.crm_tagged / s.crm_source * 100:.0f}%)"],
                             ["Check every live lead form is in the tagging workflow trigger. "
                              "Usually one new form was never added."]))

    # 2. Integration break: Meta recorded leads, the CRM has none.
    matched = s.crm_tagged if s.tag_rules else s.crm_source
    if (crm_ok and has_meta and not critical
            and s.meta_leads >= t["integration_min_meta_leads"] and matched == 0):
        critical = True
        out.append(Alert(CRITICAL, "integration-break",
                         "Meta has leads but the CRM has no Meta-tagged contacts",
                         [f"Meta lead form submissions: {s.meta_leads}",
                          f"CRM Meta-tagged contacts: {s.crm_tagged}",
                          f"CRM Meta-source contacts: {s.crm_source}",
                          f"Meta spend: {money(s.meta_spend, cur)}"],
                         ["In GHL, check Settings > Integrations > Facebook is still connected to the "
                          "right page, and that the lead forms are mapped.",
                          "Submit a test lead from the live form (Meta's Lead Ads Testing Tool) and "
                          "confirm it lands and gets tagged.",
                          "Download yesterday's leads from Meta (Ads Manager or the page's lead "
                          "centre) and add them by hand so nobody goes uncalled."]))

    # 2b. CRM gap: some leads arrive, far fewer than Meta reports.
    if (crm_ok and has_meta and not critical and s.meta_leads >= t["crm_gap_min_meta_leads"]
            and s.crm_meta < s.meta_leads * t["crm_gap_share"]):
        out.append(Alert(WARNING, "crm-gap", "CRM received far fewer Meta leads than Meta reports",
                         [f"Meta lead form submissions: {s.meta_leads}",
                          f"CRM Meta-looking contacts: {s.crm_meta}",
                          "Some gap is normal: GHL merges contacts that share an email or phone, so "
                          "repeat leads do not create new contacts."],
                         ["Check whether one of several lead forms or pages stopped syncing."]))

    # 3. Spend with no leads.
    if has_meta and s.meta_leads == 0:
        floor = (s.target_cpl * t["no_lead_spend_cpl_multiple"]) if s.target_cpl else t["no_lead_spend_min"]
        if (s.meta_spend or 0) >= floor:
            sev = CRITICAL if s.crm_meta == 0 else WARNING
            critical = critical or sev == CRITICAL
            out.append(Alert(sev, "spend-no-leads", "Ads spent money but got no leads",
                             [f"Meta spend: {money(s.meta_spend, cur)}", "Meta leads: 0",
                              f"CRM Meta-looking contacts: {s.crm_meta}"],
                             ["Check Ads Manager for rejected ads, limited ad sets or a paused form.",
                              "Open the live ad on a phone and submit a test lead.",
                              "Check the audience is not exhausted (frequency rising, reach flat)."]))

    # 4. Delivery drop vs the 7-day average.
    spend_no_leads = any(a.layer == "spend-no-leads" for a in out)
    if has_meta:
        today, avg, label = s.meta_leads, s.meta_leads_avg7 or 0.0, "Meta leads"
    else:
        today, avg, label = s.crm_meta, s.crm_meta_avg7, "CRM Meta-looking contacts"
    if (not critical and not spend_no_leads and (has_meta or crm_ok)
            and avg >= t["drop_min_avg"] and today < avg * t["drop_ratio"]):
        out.append(Alert(INFO if s.in_ramp else WARNING, "delivery-drop",
                         f"{label} far under the 7-day average",
                         [f"{label} yesterday: {today}", f"7-day average: {avg:.1f} a day",
                          f"Alert line: under {avg * t['drop_ratio']:.1f}"]
                         + (["Ramp-up period: shown as info only."] if s.in_ramp else []),
                         ["Check creative fatigue (frequency, ad age) and any budget or audience "
                          "changes made in the last 2 days.",
                          "One quiet day is noise. Two in a row is a trend."]))

    # 5. CPL spike vs target and vs trailing average.
    cpl = s.meta_cpl
    if has_meta and cpl is not None:
        if s.target_cpl:
            if cpl > s.target_cpl * t["cpl_spike_multiple"]:
                out.append(Alert(INFO if s.in_ramp else WARNING, "cpl-vs-target",
                                 f"CPL {money(cpl, cur)} is over {t['cpl_spike_multiple']:g}x target",
                                 [f"Target CPL: {money(s.target_cpl, cur)}",
                                  f"Spend {money(s.meta_spend, cur)} for {s.meta_leads} leads"],
                                 ["Single-day CPL is noisy. Act if it holds for 3+ days or the ad has "
                                  "spent 2-3x target CPL without improving."]))
            elif cpl > s.target_cpl * t["cpl_watch_multiple"]:
                out.append(Alert(INFO, "cpl-vs-target",
                                 f"CPL {money(cpl, cur)} is in the watch zone "
                                 f"(over {t['cpl_watch_multiple']:g}x target)",
                                 [f"Target CPL: {money(s.target_cpl, cur)}"]))
        trailing = s.trailing_cpl
        if (trailing and (s.meta_leads_7d or 0) >= t["cpl_trailing_min_leads"]
                and cpl > trailing * t["cpl_trailing_multiple"]):
            out.append(Alert(INFO if s.in_ramp else WARNING, "cpl-vs-trailing",
                             f"CPL {money(cpl, cur)} is over {t['cpl_trailing_multiple']:g}x the "
                             "7-day average",
                             [f"7-day CPL: {money(trailing, cur)}"],
                             ["Look for what changed yesterday: new ads, budget jumps, audience edits."]))

    return sorted(out, key=lambda a: RANK[a.severity])


def worst(alerts: list[Alert]) -> str:
    return min((a.severity for a in alerts), key=lambda x: RANK[x], default="OK")
