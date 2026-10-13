#!/usr/bin/env python3
"""MODULE 1 - Google Ads account audit (READ-ONLY).

  python3 audit_account.py CUSTOMER [options]

Options
  --days N              performance window, default 30
  --out DIR             write account-audit.json + ACCOUNT-AUDIT.md here (default: ./gads-audit-output)
  --expect-url URL      the landing page the ads are supposed to point at; any other final URL is drift
  --priority-geo "a,b"  places the client SAYS matter (so a negative keyword blocking one is flagged)
  --market-top-bid X    what the market needs (account currency) to compare effective CPC bids against
  --keywords-json FILE  keyword_research.py output; derives the market bid from the matched terms instead
  --brandsafety "a,b"   extra auto-created shared-list names to treat as brand safety, not intent
  --quiet               findings table only

What it pulls (one GAQL read each, all read-only)
  customer, campaign + budget + bidding strategy, campaign metrics incl. the three impression-share
  fields, ad groups, keywords + quality_info (keyword_view), campaign-level negatives,
  attached shared negative lists AND their members, ad schedule, locations, devices,
  ads (final URLs, approval, RSA headlines), conversion actions, search terms.

The decision tree it encodes: serving status first, then lost-to-rank vs lost-to-budget, then
negatives, then conversion counting, then schedule/geo/device, then quality score.
Quality score fields are NULL until a keyword has impressions - that is reported as "no data yet",
never as a zero.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gadslib import (finding, g, gads_search, md_table, money, now_stamp, pct, read_json,
                     sort_findings, write_json, today)
import datetime as dt

# Google auto-creates these account-level negative lists for brand safety. Having them attached is
# NOT the same as having intent negatives (job seekers, courses, investors). Checked separately.
BRANDSAFETY_LISTS = {"adult", "terrorism", "download", "covid", "sensitive", "gambling",
                     "tragedy and conflict", "shocking content", "profanity"}
MINUTE_ENUM = {"ZERO": 0, "FIFTEEN": 15, "THIRTY": 30, "FORTY_FIVE": 45}
DAYS = ["MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"]
LEADGEN_CATEGORIES = {"SUBMIT_LEAD_FORM", "CONTACT", "BOOK_APPOINTMENT", "REQUEST_QUOTE",
                      "PHONE_CALL_LEAD", "GET_DIRECTIONS", "SIGN_UP", "LEAD"}


def camp_start(c):
    """API v25 renamed campaign.start_date to campaign.start_date_time ('YYYY-MM-DD HH:MM:SS')."""
    return (g(c, "campaign.startDateTime") or "")[:10] or None


def arg(flag, default=None, argv=None):
    argv = argv or sys.argv
    if flag in argv:
        i = argv.index(flag) + 1
        if i < len(argv):
            return argv[i]
    return default


def flag(name, argv=None):
    return name in (argv or sys.argv)


def csv_arg(flag_name, default=()):
    v = arg(flag_name)
    return [x.strip() for x in v.split(",") if x.strip()] if v else list(default)


# ----------------------------------------------------------------------------- pulls
def pull(customer, days):
    end = today()
    start = end - dt.timedelta(days=days - 1)
    during = f"segments.date BETWEEN '{start}' AND '{end}'"
    d = {"customer_id": customer, "pulled_at": now_stamp(),
         "window": {"days": days, "start": str(start), "end": str(end)}}

    acct = gads_search(customer, "SELECT customer.id, customer.descriptive_name, customer.currency_code, "
                                 "customer.time_zone, customer.status, customer.auto_tagging_enabled, "
                                 "customer.optimization_score FROM customer")
    d["account"] = acct[0].get("customer", {}) if acct else {}

    d["campaigns_raw"] = gads_search(customer,
        "SELECT campaign.id, campaign.name, campaign.status, campaign.serving_status, "
        "campaign.primary_status, campaign.primary_status_reasons, campaign.advertising_channel_type, "
        "campaign.advertising_channel_sub_type, campaign.bidding_strategy_type, "
        "campaign.start_date_time, campaign.end_date_time, campaign.target_cpa.target_cpa_micros, campaign.target_roas.target_roas, "
        "campaign.manual_cpc.enhanced_cpc_enabled, campaign_budget.id, campaign_budget.amount_micros, "
        "campaign_budget.explicitly_shared, campaign_budget.delivery_method "
        "FROM campaign WHERE campaign.status != 'REMOVED'")

    # window metrics, including the three impression-share fields (the key diagnostic)
    d["campaign_metrics_raw"] = gads_search(customer,
        "SELECT campaign.id, metrics.cost_micros, metrics.impressions, metrics.clicks, "
        "metrics.conversions, metrics.all_conversions, metrics.conversions_value, metrics.average_cpc, "
        "metrics.search_impression_share, metrics.search_rank_lost_impression_share, "
        f"metrics.search_budget_lost_impression_share FROM campaign WHERE {during}")

    # per-day rows (feed the optional gads_daily table)
    d["daily_raw"] = gads_search(customer,
        "SELECT campaign.id, campaign.name, campaign.status, segments.date, metrics.impressions, "
        "metrics.clicks, metrics.cost_micros, metrics.conversions, metrics.conversions_value, "
        "metrics.average_cpc, metrics.search_impression_share, metrics.search_rank_lost_impression_share, "
        f"metrics.search_budget_lost_impression_share FROM campaign WHERE {during}")

    # life of each campaign, so "serving but never spent" is provable
    earliest = min([camp_start(c) or str(end) for c in d["campaigns_raw"]] or [str(end)])
    d["lifetime"] = {"start": earliest, "end": str(end)}
    d["lifetime_raw"] = gads_search(customer,
        "SELECT campaign.id, metrics.cost_micros, metrics.impressions, metrics.clicks, metrics.conversions "
        f"FROM campaign WHERE segments.date BETWEEN '{earliest}' AND '{end}'")

    d["ad_groups_raw"] = gads_search(customer,
        "SELECT campaign.id, ad_group.id, ad_group.name, ad_group.status, ad_group.cpc_bid_micros, "
        "ad_group.type FROM ad_group WHERE ad_group.status != 'REMOVED'")

    d["keywords_raw"] = gads_search(customer,
        "SELECT campaign.id, campaign.name, ad_group.name, ad_group_criterion.criterion_id, "
        "ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type, "
        "ad_group_criterion.status, ad_group_criterion.negative, "
        "ad_group_criterion.effective_cpc_bid_micros, ad_group_criterion.quality_info.quality_score, "
        "ad_group_criterion.quality_info.creative_quality_score, "
        "ad_group_criterion.quality_info.post_click_quality_score, "
        "ad_group_criterion.quality_info.search_predicted_ctr, metrics.impressions, metrics.clicks, "
        f"metrics.cost_micros, metrics.conversions FROM keyword_view WHERE {during}")
    # keywords with zero impressions in the window are missing from the metrics view, so list them too
    d["keywords_all_raw"] = gads_search(customer,
        "SELECT campaign.name, ad_group.name, ad_group_criterion.keyword.text, "
        "ad_group_criterion.keyword.match_type, ad_group_criterion.status, "
        "ad_group_criterion.effective_cpc_bid_micros, ad_group_criterion.quality_info.quality_score "
        "FROM keyword_view WHERE ad_group_criterion.status != 'REMOVED'")

    d["campaign_criteria_raw"] = gads_search(customer,
        "SELECT campaign.id, campaign.name, campaign_criterion.criterion_id, campaign_criterion.type, "
        "campaign_criterion.negative, campaign_criterion.bid_modifier, campaign_criterion.status, "
        "campaign_criterion.keyword.text, campaign_criterion.keyword.match_type, "
        "campaign_criterion.device.type, campaign_criterion.location.geo_target_constant, "
        "campaign_criterion.ad_schedule.day_of_week, campaign_criterion.ad_schedule.start_hour, "
        "campaign_criterion.ad_schedule.start_minute, campaign_criterion.ad_schedule.end_hour, "
        "campaign_criterion.ad_schedule.end_minute "
        "FROM campaign_criterion WHERE campaign_criterion.status != 'REMOVED'")

    d["ad_group_negatives_raw"] = gads_search(customer,
        "SELECT campaign.name, ad_group.name, ad_group_criterion.keyword.text, "
        "ad_group_criterion.keyword.match_type FROM ad_group_criterion "
        "WHERE ad_group_criterion.negative = true AND ad_group_criterion.status != 'REMOVED'")

    d["shared_sets_raw"] = gads_search(customer,
        "SELECT shared_set.id, shared_set.name, shared_set.type, shared_set.member_count, "
        "shared_set.status FROM shared_set")
    d["attached_sets_raw"] = gads_search(customer,
        "SELECT campaign.id, campaign.name, shared_set.id, shared_set.name, shared_set.type, "
        "shared_set.member_count FROM campaign_shared_set")
    d["shared_members_raw"] = gads_search(customer,
        "SELECT shared_set.id, shared_set.name, shared_criterion.keyword.text, "
        "shared_criterion.keyword.match_type, shared_criterion.type FROM shared_criterion")

    d["ads_raw"] = gads_search(customer,
        "SELECT campaign.name, ad_group.name, ad_group_ad.ad.id, ad_group_ad.status, "
        "ad_group_ad.ad.final_urls, ad_group_ad.ad.type, "
        "ad_group_ad.policy_summary.approval_status, ad_group_ad.policy_summary.review_status, "
        "ad_group_ad.ad.responsive_search_ad.headlines, ad_group_ad.ad.responsive_search_ad.descriptions, "
        "ad_group_ad.ad.responsive_search_ad.path1, ad_group_ad.ad.responsive_search_ad.path2 "
        "FROM ad_group_ad WHERE ad_group_ad.status != 'REMOVED' AND campaign.status != 'REMOVED'")

    d["conversion_actions_raw"] = gads_search(customer,
        "SELECT conversion_action.id, conversion_action.name, conversion_action.status, "
        "conversion_action.type, conversion_action.category, conversion_action.origin, "
        "conversion_action.primary_for_goal, conversion_action.counting_type, "
        "conversion_action.include_in_conversions_metric, conversion_action.click_through_lookback_window_days "
        "FROM conversion_action WHERE conversion_action.status != 'REMOVED'")

    # location targets come back as geoTargetConstants/<id>; resolve to real names so a human (and
    # the geo-gap check in build_outputs) reads "Springfield, Illinois, United States", not an id
    geo_ids = sorted({str(g(c, "campaignCriterion.location.geoTargetConstant") or "").split("/")[-1]
                      for c in d["campaign_criteria_raw"]
                      if g(c, "campaignCriterion.type") == "LOCATION"} - {""})
    d["geo_names"] = {}
    for i in range(0, len(geo_ids), 200):
        chunk = geo_ids[i:i + 200]
        rows = gads_search(customer,
            "SELECT geo_target_constant.id, geo_target_constant.name, "
            "geo_target_constant.canonical_name, geo_target_constant.target_type "
            f"FROM geo_target_constant WHERE geo_target_constant.id IN ({','.join(chunk)})")
        for r in rows:
            d["geo_names"][str(g(r, "geoTargetConstant.id"))] = {
                "name": g(r, "geoTargetConstant.name"),
                "canonical": g(r, "geoTargetConstant.canonicalName"),
                "type": g(r, "geoTargetConstant.targetType")}

    d["search_terms_raw"] = gads_search(customer,
        "SELECT campaign.name, search_term_view.search_term, search_term_view.status, "
        "metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions "
        f"FROM search_term_view WHERE {during}")
    return d


# ----------------------------------------------------------------------------- shaping
def schedule_hours(criteria, campaign_id):
    """Hours of 168 covered by AD_SCHEDULE criteria. No schedule criteria at all = all 168."""
    rows = [c for c in criteria
            if g(c, "campaignCriterion.type") == "AD_SCHEDULE" and str(g(c, "campaign.id")) == str(campaign_id)]
    if not rows:
        return 168.0, []
    total, spans = 0.0, []
    for r in rows:
        s = g(r, "campaignCriterion.adSchedule", {}) or {}
        sh = float(s.get("startHour") or 0) + MINUTE_ENUM.get(s.get("startMinute") or "ZERO", 0) / 60.0
        eh = float(s.get("endHour") or 0) + MINUTE_ENUM.get(s.get("endMinute") or "ZERO", 0) / 60.0
        day = s.get("dayOfWeek") or "?"
        total += max(0.0, eh - sh)
        spans.append({"day": day, "start": sh, "end": eh})
    return round(total, 2), sorted(spans, key=lambda x: (DAYS.index(x["day"]) if x["day"] in DAYS else 9, x["start"]))


def shape(d):
    out = {k: d[k] for k in ("customer_id", "pulled_at", "window", "lifetime")}
    geo = d.get("geo_names", {})

    def geoname(res):
        i = str(res or "").split("/")[-1]
        g2 = geo.get(i)
        return (g2["canonical"] or g2["name"]) if g2 else f"geo id {i}"

    a = d["account"]
    out["account"] = {"id": a.get("id"), "name": a.get("descriptiveName"), "currency": a.get("currencyCode"),
                      "time_zone": a.get("timeZone"), "status": a.get("status"),
                      "auto_tagging": bool(a.get("autoTaggingEnabled")),
                      "optimization_score": a.get("optimizationScore")}
    met = {str(g(r, "campaign.id")): r.get("metrics", {}) for r in d["campaign_metrics_raw"]}
    life = {str(g(r, "campaign.id")): r.get("metrics", {}) for r in d["lifetime_raw"]}
    crit = d["campaign_criteria_raw"]

    camps = []
    for c in d["campaigns_raw"]:
        cid = str(g(c, "campaign.id"))
        m, lm = met.get(cid, {}), life.get(cid, {})
        hours, spans = schedule_hours(crit, cid)
        mine = [x for x in crit if str(g(x, "campaign.id")) == cid]
        locs = [geoname(g(x, "campaignCriterion.location.geoTargetConstant")) for x in mine
                if g(x, "campaignCriterion.type") == "LOCATION" and not g(x, "campaignCriterion.negative")]
        neg_locs = [geoname(g(x, "campaignCriterion.location.geoTargetConstant")) for x in mine
                    if g(x, "campaignCriterion.type") == "LOCATION" and g(x, "campaignCriterion.negative")]
        devices = [{"device": g(x, "campaignCriterion.device.type"),
                    "bid_modifier": g(x, "campaignCriterion.bidModifier")}
                   for x in mine if g(x, "campaignCriterion.type") == "DEVICE"]
        negs = [{"text": g(x, "campaignCriterion.keyword.text"),
                 "match": g(x, "campaignCriterion.keyword.matchType")}
                for x in mine if g(x, "campaignCriterion.negative") and g(x, "campaignCriterion.type") == "KEYWORD"]
        camps.append({
            "id": cid, "name": g(c, "campaign.name"), "status": g(c, "campaign.status"),
            "serving_status": g(c, "campaign.servingStatus"), "primary_status": g(c, "campaign.primaryStatus"),
            "primary_status_reasons": g(c, "campaign.primaryStatusReasons") or [],
            "channel": g(c, "campaign.advertisingChannelType"),
            "sub_type": g(c, "campaign.advertisingChannelSubType"),
            "bidding_strategy": g(c, "campaign.biddingStrategyType"),
            "enhanced_cpc": bool(g(c, "campaign.manualCpc.enhancedCpcEnabled")),
            "target_cpa": money(g(c, "campaign.targetCpa.targetCpaMicros")) or None,
            "start_date": camp_start(c), "end_date": (g(c, "campaign.endDateTime") or "")[:10] or None,
            "daily_budget": money(g(c, "campaignBudget.amountMicros")),
            "budget_shared": bool(g(c, "campaignBudget.explicitlyShared")),
            "budget_delivery": g(c, "campaignBudget.deliveryMethod"),
            "window": {"spend": money(m.get("costMicros")), "impressions": int(m.get("impressions", 0) or 0),
                       "clicks": int(m.get("clicks", 0) or 0), "conversions": float(m.get("conversions", 0) or 0),
                       "conv_value": float(m.get("conversionsValue", 0) or 0),
                       "avg_cpc": money(m.get("averageCpc")),
                       "search_impression_share_pct": pct(m.get("searchImpressionShare")),
                       "search_lost_is_rank_pct": pct(m.get("searchRankLostImpressionShare")),
                       "search_lost_is_budget_pct": pct(m.get("searchBudgetLostImpressionShare"))},
            "lifetime": {"spend": money(lm.get("costMicros")), "impressions": int(lm.get("impressions", 0) or 0),
                         "clicks": int(lm.get("clicks", 0) or 0), "conversions": float(lm.get("conversions", 0) or 0)},
            "ad_schedule_hours": hours, "ad_schedule": spans,
            "location_targets": locs, "negative_locations": neg_locs,
            "devices": devices, "campaign_negatives": negs,
        })
    out["campaigns"] = camps

    out["daily"] = [{"campaign_id": str(g(r, "campaign.id")), "campaign_name": g(r, "campaign.name"),
                     "campaign_status": g(r, "campaign.status"), "date": g(r, "segments.date"),
                     "impressions": int(g(r, "metrics.impressions", 0) or 0),
                     "clicks": int(g(r, "metrics.clicks", 0) or 0),
                     "cost_micros": int(g(r, "metrics.costMicros", 0) or 0),
                     "conversions": float(g(r, "metrics.conversions", 0) or 0),
                     "conversions_value": float(g(r, "metrics.conversionsValue", 0) or 0),
                     "avg_cpc_micros": int(g(r, "metrics.averageCpc", 0) or 0),
                     "search_impression_share": g(r, "metrics.searchImpressionShare"),
                     "search_lost_is_rank": g(r, "metrics.searchRankLostImpressionShare"),
                     "search_lost_is_budget": g(r, "metrics.searchBudgetLostImpressionShare")}
                    for r in d["daily_raw"]]

    perf = {}
    for r in d["keywords_raw"]:
        key = (g(r, "campaign.name"), g(r, "adGroup.name"), g(r, "adGroupCriterion.keyword.text"))
        perf[key] = r
    kws = []
    for r in d["keywords_all_raw"]:
        key = (g(r, "campaign.name"), g(r, "adGroup.name"), g(r, "adGroupCriterion.keyword.text"))
        p = perf.get(key, {})
        qi = g(p, "adGroupCriterion.qualityInfo", {}) or g(r, "adGroupCriterion.qualityInfo", {}) or {}
        kws.append({"campaign": g(r, "campaign.name"), "ad_group": g(r, "adGroup.name"),
                    "text": g(r, "adGroupCriterion.keyword.text"),
                    "match": g(r, "adGroupCriterion.keyword.matchType"),
                    "status": g(r, "adGroupCriterion.status"),
                    "bid": money(g(r, "adGroupCriterion.effectiveCpcBidMicros")),
                    "impressions": int(g(p, "metrics.impressions", 0) or 0),
                    "clicks": int(g(p, "metrics.clicks", 0) or 0),
                    "cost": money(g(p, "metrics.costMicros")),
                    "conversions": float(g(p, "metrics.conversions", 0) or 0),
                    "quality_score": qi.get("qualityScore"),
                    "creative_quality": qi.get("creativeQualityScore"),
                    "landing_page_quality": qi.get("postClickQualityScore"),
                    "predicted_ctr": qi.get("searchPredictedCtr")})
    out["keywords"] = sorted(kws, key=lambda k: -k["impressions"])

    members = {}
    for r in d["shared_members_raw"]:
        members.setdefault(str(g(r, "sharedSet.id")), []).append(
            {"text": g(r, "sharedCriterion.keyword.text"), "match": g(r, "sharedCriterion.keyword.matchType")})
    out["shared_sets"] = [{"id": str(g(s, "sharedSet.id")), "name": g(s, "sharedSet.name"),
                           "type": g(s, "sharedSet.type"), "members": int(g(s, "sharedSet.memberCount", 0) or 0),
                           "status": g(s, "sharedSet.status"),
                           "brand_safety": (g(s, "sharedSet.name") or "").strip().lower() in BRANDSAFETY_LISTS,
                           "terms": members.get(str(g(s, "sharedSet.id")), [])}
                          for s in d["shared_sets_raw"]]
    out["attached_sets"] = [{"campaign_id": str(g(s, "campaign.id")), "campaign": g(s, "campaign.name"),
                             "set_id": str(g(s, "sharedSet.id")), "set": g(s, "sharedSet.name"),
                             "type": g(s, "sharedSet.type"),
                             "members": int(g(s, "sharedSet.memberCount", 0) or 0),
                             "brand_safety": (g(s, "sharedSet.name") or "").strip().lower() in BRANDSAFETY_LISTS}
                            for s in d["attached_sets_raw"]]
    out["ad_group_negatives"] = [{"campaign": g(r, "campaign.name"), "ad_group": g(r, "adGroup.name"),
                                  "text": g(r, "adGroupCriterion.keyword.text"),
                                  "match": g(r, "adGroupCriterion.keyword.matchType")}
                                 for r in d["ad_group_negatives_raw"]]

    ads = []
    for r in d["ads_raw"]:
        rsa = g(r, "adGroupAd.ad.responsiveSearchAd", {}) or {}
        ads.append({"campaign": g(r, "campaign.name"), "ad_group": g(r, "adGroup.name"),
                    "ad_id": g(r, "adGroupAd.ad.id"), "status": g(r, "adGroupAd.status"),
                    "type": g(r, "adGroupAd.ad.type"),
                    "approval": g(r, "adGroupAd.policySummary.approvalStatus"),
                    "review": g(r, "adGroupAd.policySummary.reviewStatus"),
                    "final_urls": g(r, "adGroupAd.ad.finalUrls") or [],
                    "headlines": [h.get("text") for h in rsa.get("headlines", []) if h.get("text")],
                    "descriptions": [x.get("text") for x in rsa.get("descriptions", []) if x.get("text")],
                    "paths": [p for p in (rsa.get("path1"), rsa.get("path2")) if p]})
    out["ads"] = ads

    out["conversion_actions"] = [{
        "id": g(c, "conversionAction.id"), "name": g(c, "conversionAction.name"),
        "status": g(c, "conversionAction.status") or "", "type": g(c, "conversionAction.type") or "",
        "category": g(c, "conversionAction.category") or "", "origin": g(c, "conversionAction.origin") or "",
        "primary_for_goal": bool(g(c, "conversionAction.primaryForGoal")),
        "include_in_conversions_metric": bool(g(c, "conversionAction.includeInConversionsMetric")),
        "counting_type": g(c, "conversionAction.countingType") or "",
        "lookback_days": g(c, "conversionAction.clickThroughLookbackWindowDays")}
        for c in d["conversion_actions_raw"]]

    out["search_terms"] = sorted([{"campaign": g(r, "campaign.name"),
                                   "term": g(r, "searchTermView.searchTerm"),
                                   "status": g(r, "searchTermView.status"),
                                   "impressions": int(g(r, "metrics.impressions", 0) or 0),
                                   "clicks": int(g(r, "metrics.clicks", 0) or 0),
                                   "cost": money(g(r, "metrics.costMicros")),
                                   "conversions": float(g(r, "metrics.conversions", 0) or 0)}
                                  for r in d["search_terms_raw"]], key=lambda t: -t["cost"])
    out["ad_groups"] = [{"campaign_id": str(g(r, "campaign.id")), "name": g(r, "adGroup.name"),
                         "status": g(r, "adGroup.status"), "bid": money(g(r, "adGroup.cpcBidMicros"))}
                        for r in d["ad_groups_raw"]]
    return out


# ----------------------------------------------------------------------------- findings
def isp(v):
    """Google caps impression-share metrics: 0.9001 means '>90%', 0.0999 means '<10%'. Never print them as 90/10."""
    if v is None:
        return "n/a"
    if v >= 90.005:
        return ">90%"
    if v <= 9.995:
        return "<10%"
    return f"{v:.1f}%"


def judge(s, expect_url=None, priority_geo=(), market_top_bid=None, extra_brandsafety=()):
    F, cur = [], s["account"].get("currency") or ""
    for name in extra_brandsafety:
        BRANDSAFETY_LISTS.add(name.strip().lower())

    if not s["account"].get("auto_tagging"):
        F.append(finding("AUTOTAGGING_OFF", "warning", "Auto-tagging is off",
                         "Without the gclid Google appends, the CRM (e.g. GoHighLevel) cannot attribute a lead to a click.",
                         action="Turn auto-tagging on in account settings, then confirm gclid arrives on the form."))

    live = [c for c in s["campaigns"] if c["status"] == "ENABLED"]
    if not live:
        F.append(finding("NO_LIVE_CAMPAIGN", "critical", "No enabled campaign",
                         f"{len(s['campaigns'])} campaign(s) exist, none ENABLED.",
                         action="Confirm with the client whether this is deliberate before anything else."))

    for c in s["campaigns"]:
        tag = c["name"]
        if c["status"] == "ENABLED" and c["primary_status"] not in (None, "", "ELIGIBLE", "LIMITED", "LEARNING"):
            F.append(finding("CAMPAIGN_NOT_SERVING", "critical", f"{tag}: not serving ({c['primary_status']})",
                             "Reasons: " + ", ".join(c["primary_status_reasons"] or ["none given"]),
                             action="Clear each primary_status_reason in order; nothing else matters until it serves."))
        if c["status"] != "ENABLED":
            continue

        w, lifetime = c["window"], c["lifetime"]
        if lifetime["spend"] == 0 and c["primary_status"] in (None, "", "ELIGIBLE", "LIMITED", "LEARNING"):
            F.append(finding("SERVING_NO_SPEND", "critical",
                             f"{tag}: eligible and serving but has never spent",
                             f"Life of campaign ({s['lifetime']['start']} to {s['lifetime']['end']}): "
                             f"{lifetime['impressions']} impressions, {lifetime['clicks']} clicks, "
                             f"{cur} {lifetime['spend']:.2f} spend, daily budget {cur} {c['daily_budget']:.2f}.",
                             metric_value=lifetime["spend"],
                             action="Read lost-to-rank vs lost-to-budget below. Rank-lost means the bids never "
                                    "entered the auction; raising budget changes nothing."))
        elif w["spend"] == 0 and w["impressions"] == 0:
            F.append(finding("NO_DELIVERY_IN_WINDOW", "critical", f"{tag}: zero impressions in the window",
                             f"{s['window']['start']} to {s['window']['end']}.",
                             action="Check serving status, bids and whether the ad schedule excluded the window."))

        rank, budget, share = w["search_lost_is_rank_pct"], w["search_lost_is_budget_pct"], w["search_impression_share_pct"]
        if rank is None and budget is None:
            F.append(finding("NO_IMPRESSION_SHARE_DATA", "info", f"{tag}: no impression-share data yet",
                             "Google only reports impression share once the campaign has auction history.",
                             action="Re-run once it has served for a few days."))
        else:
            if rank is not None and rank >= 50:
                F.append(finding("LOST_IS_RANK", "critical", f"{tag}: {isp(rank)} of impressions lost to rank",
                                 f"Impression share {isp(share)}, lost to budget {isp(budget)}. Ad Rank (bid x quality) "
                                 "is the constraint, not money available.",
                                 metric_value=rank,
                                 action="Raise bids towards the market top-of-page bid (or move to a conversion "
                                        "bid strategy) and fix landing-page/ad relevance. Do not raise the budget."))
            elif rank is not None and rank >= 25:
                F.append(finding("LOST_IS_RANK_MODERATE", "warning", f"{tag}: {isp(rank)} lost to rank",
                                 f"Impression share {isp(share)}.", metric_value=rank,
                                 action="Bid up on the terms that convert; leave the budget alone."))
            if budget is not None and budget >= 20:
                F.append(finding("LOST_IS_BUDGET", "warning", f"{tag}: {isp(budget)} of impressions lost to budget",
                                 f"Impression share {isp(share)}, lost to rank {isp(rank)}. This one IS a money cap.",
                                 metric_value=budget,
                                 action="Raise the daily budget, or cut the terms eating it, before raising bids."))

        if c["bidding_strategy"] == "MANUAL_CPC":
            convs = lifetime["conversions"]
            sev = "warning" if convs < 15 else "info"
            F.append(finding("MANUAL_CPC", sev, f"{tag}: manual CPC",
                             f"Enhanced CPC {'on' if c['enhanced_cpc'] else 'off'}, "
                             f"{convs:g} conversions on record. Manual CPC on a young account means a human has "
                             "to guess the auction price; it is the usual cause of a 90%-lost-to-rank campaign.",
                             metric_value=convs,
                             action="Keep manual CPC only while bids are being calibrated, with bids at or above "
                                    "the market top-of-page bid. Move to Maximise clicks (capped) now, then to "
                                    "Maximise conversions once there are about 15-30 conversions in 30 days."))

        # Keyword bids only drive the auction under manual CPC; smart bidding ignores them
        # (a Maximise-conversions campaign with a leftover 0.01 keyword bid would otherwise false-fire).
        # Brand terms are cheap by nature; the market figure is for generic core terms.
        if market_top_bid and c["bidding_strategy"] == "MANUAL_CPC" and "brand" not in tag.lower():
            bids = [k["bid"] for k in s["keywords"] if k["campaign"] == tag and k["bid"]]
            if bids:
                med = sorted(bids)[len(bids) // 2]
                capped = budget is not None and budget >= 20
                if med < float(market_top_bid) and capped:
                    # Bidding up a budget-capped campaign buys fewer clicks with the same money.
                    F.append(finding("BID_BELOW_MARKET_BUDGET_CAPPED", "warning",
                                     f"{tag}: median keyword bid {cur} {med:.2f} vs market {cur} {float(market_top_bid):.2f}, "
                                     f"but {isp(budget)} of impressions are already lost to budget",
                                     "The budget runs out before the bid matters. Raising bids alone spends the same "
                                     "money on fewer clicks.",
                                     metric_value=med,
                                     action="Do not raise bids yet. Fix where the clicks land and what is tracked, then "
                                            "either raise the budget or cut the campaign to the terms that convert, "
                                            "and only then bid towards the market price."))
                elif med < float(market_top_bid):
                    F.append(finding("BID_BELOW_MARKET", "critical" if med < float(market_top_bid) * 0.6 else "warning",
                                     f"{tag}: median keyword bid {cur} {med:.2f} vs market {cur} {float(market_top_bid):.2f}",
                                     "Market figure supplied from keyword research (top-of-page bid). A bid under "
                                     "the top-of-page range rarely shows above the organic results.",
                                     metric_value=med,
                                     action=f"Take bids to at least {cur} {float(market_top_bid):.2f} on the "
                                            "terms that matter, or let a smart bidding strategy price them."))

        hours = c["ad_schedule_hours"]
        if hours < 42:
            F.append(finding("AD_SCHEDULE_THIN", "warning",
                             f"{tag}: ads run {hours:g} hours of 168 ({hours / 168 * 100:.0f}% of the week)",
                             "Spans: " + "; ".join(f"{x['day'][:3]} {x['start']:g}-{x['end']:g}" for x in c["ad_schedule"]),
                             metric_value=hours,
                             action="Widen to evenings and weekends unless the client has told us enquiries "
                                    "outside those hours are worthless. Families research after work."))
        elif hours < 120:
            F.append(finding("AD_SCHEDULE_PARTIAL", "info",
                             f"{tag}: ads run {hours:g} hours of 168", metric_value=hours,
                             action="Check the excluded hours against when enquiries actually arrive."))

        if not c["devices"]:
            F.append(finding("NO_DEVICE_CRITERIA", "info", f"{tag}: no device criteria rows", "",
                             action="Nothing to fix; device data is still reportable."))
        elif all(dv.get("bid_modifier") in (None, 1, 1.0) for dv in c["devices"]):
            F.append(finding("DEVICE_NO_MODIFIERS", "info", f"{tag}: no device bid modifiers set",
                             "All devices bid the same.",
                             action="Leave it until there is device-level conversion data, then adjust."))

        nlocs = len(c["location_targets"])
        if nlocs == 0:
            F.append(finding("NO_LOCATION_TARGET", "critical", f"{tag}: no location targeting",
                             "The campaign is showing to the whole country or worse.",
                             action="Add the client's real service areas."))
        elif nlocs >= 5:
            F.append(finding("MANY_SMALL_GEOS", "info", f"{tag}: {nlocs} location targets",
                             "Suburb/LGA-level targets are fine, but suburb-level KEYWORDS usually have no volume. "
                             "Check keyword_research.py output before adding suburb terms.",
                             metric_value=nlocs,
                             action="Keep the geo targets, drop suburb-level keywords with no measurable volume."))

        if c["budget_shared"]:
            F.append(finding("BUDGET_SHARED", "info", f"{tag}: shared budget",
                             "Another campaign can eat this one's money.",
                             action="Give the campaign its own budget if it has its own goal."))

    # ---- negatives, in three layers. A shared list being attached is not the same as intent negatives.
    for c in s["campaigns"]:
        if c["status"] != "ENABLED":
            continue
        own = len(c["campaign_negatives"])
        ag = len([n for n in s["ad_group_negatives"] if n["campaign"] == c["name"]])
        attached = [a for a in s["attached_sets"] if a["campaign_id"] == c["id"] and a["type"] == "NEGATIVE_KEYWORDS"]
        intent = [a for a in attached if not a["brand_safety"]]
        safety = [a for a in attached if a["brand_safety"]]
        intent_terms = sum(a["members"] for a in intent)
        if own + ag + intent_terms == 0:
            detail = (f"Campaign-level negatives: {own}. Ad-group negatives: {ag}. "
                      f"Attached negative lists: {len(attached)}"
                      + (f" but all {len(safety)} are Google's auto brand-safety lists "
                         f"({', '.join(a['set'] for a in safety)}), which block adult/terror terms, not job "
                         "seekers, course hunters or property investors." if safety else "."))
            F.append(finding("ZERO_NEGATIVES", "critical", f"{c['name']}: no intent negative keywords anywhere",
                             detail, metric_value=0,
                             action="Add the negative set from keyword_research.py (job/salary/course/volunteer/"
                                    "marketplace/investor terms) BEFORE any bid or budget rise, or the extra money "
                                    "buys job-seeker clicks."))
        else:
            F.append(finding("NEGATIVES_PRESENT", "info",
                             f"{c['name']}: {own + ag + intent_terms} intent negatives in place",
                             f"campaign {own}, ad group {ag}, shared lists {intent_terms} "
                             f"({', '.join(a['set'] for a in intent) or 'none'}); plus "
                             f"{len(safety)} Google brand-safety list(s).",
                             metric_value=own + ag + intent_terms,
                             action="Re-check against this run's negative candidates for gaps."))
        if intent_terms and intent_terms < 15:
            F.append(finding("NEGATIVES_THIN", "warning", f"{c['name']}: only {intent_terms} intent negatives",
                             "Thin for a niche that shares vocabulary with job hunting or property investing.",
                             metric_value=intent_terms, action="Extend from this run's negative candidate list."))

    # negatives that block a place the client says matters
    all_neg = ([(n["text"], n["match"], "campaign") for c in s["campaigns"] for n in c["campaign_negatives"]]
               + [(n["text"], n["match"], "ad group") for n in s["ad_group_negatives"]]
               + [(t["text"], t["match"], f"list:{st['name']}") for st in s["shared_sets"]
                  if not st["brand_safety"] for t in st["terms"]])
    attached_ids = {a["set_id"] for a in s["attached_sets"]}
    for geo in priority_geo:
        hits = [n for n in all_neg if n[0] and geo.strip().lower() in n[0].lower()
                and (not n[2].startswith("list:") or any(st["name"] == n[2][5:] and st["id"] in attached_ids
                                                         for st in s["shared_sets"]))]
        if hits:
            F.append(finding("NEGATIVE_BLOCKS_PRIORITY_GEO", "critical",
                             f"Negative keyword blocks a priority location: {geo}",
                             "; ".join(f"'{t}' ({m}, {src})" for t, m, src in hits),
                             action=f"The client named {geo} a priority. Either remove the negative or confirm in "
                                    "writing that it is deliberate, before launching anything there."))

    # ---- ads
    enabled_ads = [a for a in s["ads"] if a["status"] == "ENABLED"]
    if not enabled_ads:
        F.append(finding("NO_ENABLED_ADS", "critical", "No enabled ads", "",
                         action="Nothing can serve. Enable or build ads."))
    for a in enabled_ads:
        if a["approval"] not in (None, "", "APPROVED", "APPROVED_LIMITED"):
            F.append(finding("AD_DISAPPROVED", "critical",
                             f"{a['campaign']} / {a['ad_group']}: ad {a['approval']}",
                             f"Review status {a['review']}. Ad id {a['ad_id']}.",
                             action="Read the policy reason in the UI and rewrite; a disapproved ad serves nothing."))
        elif a["approval"] == "APPROVED_LIMITED":
            F.append(finding("AD_APPROVED_LIMITED", "warning",
                             f"{a['campaign']} / {a['ad_group']}: ad approved with limits", "",
                             action="Check which policy limited it; limited ads lose a lot of eligible traffic."))
    urls = sorted({u for a in enabled_ads for u in a["final_urls"]})
    if len(urls) > 1:
        F.append(finding("MULTIPLE_FINAL_URLS", "info", f"{len(urls)} different final URLs across live ads",
                         "; ".join(urls), metric_value=len(urls),
                         action="Fine if deliberate, one page per ad group. Confirm each page matches its ads."))
    if expect_url:
        drift = [u for u in urls if u.rstrip("/") != expect_url.rstrip("/")]
        if drift:
            F.append(finding("AD_FINAL_URL_DRIFT", "critical", "Live ads point somewhere other than the agreed page",
                             f"Expected {expect_url}; found " + "; ".join(drift),
                             action="Repoint the final URLs, or agree the new page and re-audit it."))

    # ---- conversions
    ca = s["conversion_actions"]
    counted = [c for c in ca if c["include_in_conversions_metric"] and c["status"] == "ENABLED"]
    primary = [c for c in counted if c["primary_for_goal"]]
    if not ca:
        F.append(finding("NO_CONVERSION_ACTIONS", "critical", "No conversion actions exist",
                         "Nothing is being measured, so no bid strategy can optimise and no report can be true.",
                         action="Build the lead-form and call conversions before spending more."))
    elif not primary:
        F.append(finding("CONV_NO_PRIMARY", "critical", "No primary conversion action",
                         f"{len(ca)} action(s), none primary_for_goal. Smart bidding has nothing to aim at.",
                         action="Mark the real lead action primary; make everything else secondary."))
    for c in counted:
        if c["counting_type"] == "MANY_PER_CLICK" and (c["category"] in LEADGEN_CATEGORIES
                                                       or "lead" in (c["name"] or "").lower()
                                                       or "form" in (c["name"] or "").lower()):
            F.append(finding("CONV_COUNTING_MANY", "warning",
                             f"Conversion '{c['name']}' counts EVERY submission (MANY_PER_CLICK)",
                             "One person submitting three times reads as three leads, which inflates the "
                             "conversion count and misprices every bid built on it.",
                             action="Set counting to One (ONE_PER_CLICK) for lead actions. Keep Every for sales."))
        if c["origin"] in ("GOOGLE_ANALYTICS_4", "GOOGLE_ANALYTICS", "ANALYTICS"):
            F.append(finding("CONV_ORIGIN_GA4_IMPORT", "info",
                             f"Conversion '{c['name']}' is imported from Analytics ({c['origin']})",
                             "GA4 imports lag and can double-count alongside a website tag.",
                             action="Pick one source per action. Prefer the Google Ads tag or the CRM import "
                                    "for the lead itself."))
    names = [c["name"] for c in counted]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        F.append(finding("CONV_DUPLICATE_NAMES", "warning", "Duplicate counted conversion names",
                         ", ".join(sorted(dupes)), action="Pause the duplicate; one action per real event."))

    clicks = sum(c["window"]["clicks"] for c in s["campaigns"])
    convs = sum(c["window"]["conversions"] for c in s["campaigns"])
    if clicks >= 50 and convs == 0:
        F.append(finding("CLICKS_NO_CONVERSIONS", "critical",
                         f"{clicks} clicks and zero conversions in the window",
                         "Either tracking is broken or the landing page is not converting.",
                         metric_value=clicks,
                         action="Test the form end to end (module 3) before touching bids."))

    # ---- quality score
    kws = [k for k in s["keywords"] if k["status"] == "ENABLED"]
    scored = [k for k in kws if k["quality_score"]]
    if kws and not scored:
        F.append(finding("QS_NO_DATA", "info", f"No quality score on any of {len(kws)} keywords yet",
                         "Google leaves quality_score, creative_quality_score, post_click_quality_score and "
                         "search_predicted_ctr NULL until a keyword has impressions. This is 'no data yet', "
                         "not a score of zero.", metric_value=len(kws),
                         action="Re-run after the campaign has served. Until then judge the landing page with "
                                "module 3's measured numbers."))
    elif scored:
        avg = sum(int(k["quality_score"]) for k in scored) / len(scored)
        low = [k for k in scored if int(k["quality_score"]) <= 4]
        F.append(finding("QS_AVERAGE", "info" if avg >= 6 else "warning",
                         f"Average quality score {avg:.1f} across {len(scored)} scored keywords",
                         f"{len(low)} at 4 or below.", metric_value=round(avg, 2),
                         action="Below 6: fix ad-to-keyword relevance and the landing page before bidding up, "
                                "because Ad Rank multiplies bid by quality."))
        bad_lp = [k for k in scored if k["landing_page_quality"] == "BELOW_AVERAGE"]
        if bad_lp:
            F.append(finding("QS_LANDING_PAGE_BELOW_AVERAGE", "critical",
                             f"Google rates the landing page below average on {len(bad_lp)} keyword(s)",
                             ", ".join(k["text"] for k in bad_lp[:10]), metric_value=len(bad_lp),
                             action="This is Google's own landing-page verdict and it is the authoritative one. "
                                    "Fix message match and speed (module 3), then re-check."))
        bad_ctr = [k for k in scored if k["predicted_ctr"] == "BELOW_AVERAGE"]
        if bad_ctr:
            F.append(finding("QS_PREDICTED_CTR_BELOW_AVERAGE", "warning",
                             f"Expected click-through rate below average on {len(bad_ctr)} keyword(s)",
                             ", ".join(k["text"] for k in bad_ctr[:10]), metric_value=len(bad_ctr),
                             action="Rewrite headlines to carry the keyword and the offer."))

    zero = [k for k in kws if k["impressions"] == 0]
    if kws and len(zero) >= max(3, len(kws) // 2):
        F.append(finding("KEYWORDS_NO_IMPRESSIONS", "warning",
                         f"{len(zero)} of {len(kws)} keywords got no impressions in the window",
                         "Either bids are below the auction floor or the terms have no search volume. "
                         "Module 2 tells you which.", metric_value=len(zero),
                         action="Check each against measured search volume. Pause the ones with no volume; "
                                "bid up the ones that have it."))
    broad = [k for k in kws if k["match"] == "BROAD"]
    if broad:
        F.append(finding("BROAD_MATCH_IN_USE", "warning", f"{len(broad)} broad match keyword(s)",
                         ", ".join(k["text"] for k in broad[:10]), metric_value=len(broad),
                         action="Broad match needs a full negative list and weekly search-term review. "
                                "Confirm with the client that it is wanted."))

    waste = [t for t in s["search_terms"] if t["cost"] > 0 and t["conversions"] == 0]
    if waste:
        F.append(finding("SEARCH_TERM_WASTE", "warning",
                         f"{len(waste)} search terms spent with no conversion",
                         "Top: " + "; ".join(f"{t['term']} ({cur} {t['cost']:.2f})" for t in waste[:8]),
                         metric_value=round(sum(t["cost"] for t in waste), 2),
                         action="Negative the irrelevant ones; leave relevant ones to accumulate data."))
    return sort_findings(F)


# ----------------------------------------------------------------------------- report
def markdown(s, F):
    cur = s["account"].get("currency") or ""
    w = s["window"]
    L = [f"# Google Ads account audit - {s['account'].get('name') or s['customer_id']}",
         "",
         f"Account {s['customer_id']}, {cur}, {s['account'].get('time_zone')}, status "
         f"{s['account'].get('status')}, auto-tagging {'ON' if s['account'].get('auto_tagging') else 'OFF'}.",
         f"Pulled {s['pulled_at']} via the Google Ads API (read-only, through the manager account). "
         f"Window {w['start']} to {w['end']} ({w['days']} days). Money is in {cur}, never rounded.",
         "", "## Findings", ""]
    L.append(md_table(["Severity", "Code", "Finding", "Do this"],
                      [[f["severity"].upper(), f["code"], f["title"], f["recommended_action"]] for f in F]))
    L += ["", "## Campaigns", ""]
    L.append(md_table(["Campaign", "Status", "Primary status", "Budget/day", f"Spend ({w['days']}d)",
                       "Impr", "Clicks", "Conv", "Impr share", "Lost: rank", "Lost: budget",
                       "Bidding", "Schedule hrs/168"],
                      [[c["name"], c["status"], c["primary_status"] or "", f"{c['daily_budget']:.2f}",
                        f"{c['window']['spend']:.2f}", c["window"]["impressions"], c["window"]["clicks"],
                        f"{c['window']['conversions']:g}",
                        "no data" if c["window"]["search_impression_share_pct"] is None
                        else f"{c['window']['search_impression_share_pct']:.2f}%",
                        "no data" if c["window"]["search_lost_is_rank_pct"] is None
                        else f"{c['window']['search_lost_is_rank_pct']:.2f}%",
                        "no data" if c["window"]["search_lost_is_budget_pct"] is None
                        else f"{c['window']['search_lost_is_budget_pct']:.2f}%",
                        c["bidding_strategy"], f"{c['ad_schedule_hours']:g}"] for c in s["campaigns"]]))
    L += ["", "## Negative keywords (three layers)", ""]
    rows = []
    for c in s["campaigns"]:
        att = [a for a in s["attached_sets"] if a["campaign_id"] == c["id"]]
        rows.append([c["name"], len(c["campaign_negatives"]),
                     len([n for n in s["ad_group_negatives"] if n["campaign"] == c["name"]]),
                     "; ".join(f"{a['set']} ({a['members']})" for a in att if not a["brand_safety"]) or "none",
                     "; ".join(a["set"] for a in att if a["brand_safety"]) or "none"])
    L.append(md_table(["Campaign", "Campaign-level", "Ad-group", "Intent lists attached", "Brand-safety lists"], rows))
    L += ["", "## Ads", ""]
    L.append(md_table(["Campaign", "Ad group", "Status", "Approval", "Final URL", "First headlines"],
                      [[a["campaign"], a["ad_group"], a["status"], a["approval"],
                        "; ".join(a["final_urls"]), " / ".join(a["headlines"][:3])] for a in s["ads"]]))
    L += ["", "## Conversion actions", ""]
    L.append(md_table(["Name", "Status", "Primary", "Counted", "Counting", "Origin", "Category"],
                      [[c["name"], c["status"], "YES" if c["primary_for_goal"] else "no",
                        "YES" if c["include_in_conversions_metric"] else "no",
                        c["counting_type"], c["origin"], c["category"]] for c in s["conversion_actions"]]))
    kws = s["keywords"]
    L += ["", f"## Keywords ({len(kws)})", "",
          "Quality score columns are empty until a keyword has impressions. Empty means no data yet, not zero.", ""]
    L.append(md_table(["Keyword", "Match", "Status", "Bid", "Impr", "Clicks", "Conv", "QS", "Landing page", "Exp. CTR"],
                      [[k["text"], k["match"], k["status"], f"{k['bid']:.2f}", k["impressions"], k["clicks"],
                        f"{k['conversions']:g}", k["quality_score"] or "no data",
                        k["landing_page_quality"] or "no data", k["predicted_ctr"] or "no data"] for k in kws]))
    if s["search_terms"]:
        L += ["", "## Search terms that cost money", ""]
        L.append(md_table(["Term", "Impr", "Clicks", "Cost", "Conv"],
                          [[t["term"], t["impressions"], t["clicks"], f"{t['cost']:.2f}", f"{t['conversions']:g}"]
                           for t in s["search_terms"][:40]]))
    L += ["", "## Location and schedule", ""]
    for c in s["campaigns"]:
        L.append(f"- **{c['name']}**: {len(c['location_targets'])} location target(s) "
                 f"({', '.join(str(x) for x in c['location_targets'])}), "
                 f"{c['ad_schedule_hours']:g} of 168 hours, devices: "
                 + ", ".join(f"{d['device']} {d.get('bid_modifier') or 'no modifier'}" for d in c["devices"]))
    L += ["", "Read-only throughout. Nothing was changed in the account.", ""]
    return "\n".join(L)


def main():
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    customer = argv[0]
    days = int(arg("--days", "30") or 30)
    out = os.path.abspath(arg("--out", "gads-audit-output"))
    os.makedirs(out, exist_ok=True)
    raw = pull(customer, days)
    s = shape(raw)
    F = judge(s, expect_url=arg("--expect-url"), priority_geo=csv_arg("--priority-geo"),
              market_top_bid=market_bid(), extra_brandsafety=csv_arg("--brandsafety"))
    s["findings"] = F
    write_json(os.path.join(out, "account-audit.json"), s)
    md = markdown(s, F)
    with open(os.path.join(out, "ACCOUNT-AUDIT.md"), "w") as fh:
        fh.write(md)
    if flag("--quiet"):
        for f in F:
            print(f"{f['severity'].upper():8} {f['code']:32} {f['title']}")
    else:
        print(md)
    print(f"\n[gads-audit] wrote {out}/account-audit.json and ACCOUNT-AUDIT.md "
          f"({len(F)} findings: " + ", ".join(f"{n} {sv}" for sv, n in
          sorted({sv: sum(1 for f in F if f['severity'] == sv) for sv in {x['severity'] for x in F}}.items())) + ")",
          file=sys.stderr)
    return 0


def market_bid():
    v = arg("--market-top-bid")
    if v:
        return float(v)
    kj = arg("--keywords-json")
    if kj:
        k = read_json(kj, {}) or {}
        b = (k.get("market") or {}).get("core_median_top_of_page_bid_account_currency")
        return float(b) if b else None
    return None


if __name__ == "__main__":
    sys.exit(main())
