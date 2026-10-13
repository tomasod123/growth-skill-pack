"""
AI Visibility Report -- deterministic aggregator.

Turns the compact per-cell classification checkpoint into the full `sections`
numeric structure, so the operator never computes shares/rates/matrices in-context
(saves output tokens) and the math is reproducible (not "done in the model's head").

Usage:
    python aggregate.py <config.json> <cells.json> [<prose.json>] -o <data.json>

Inputs
------
config.json : the merged config block (Appendix A) -- prompts (with `branded`),
              competitors, llms_covered, brand_domain, score_weights, white_label, ...
cells.json  : the classification checkpoint -- a JSON list of per-(prompt,model) records:
    {
      "prompt_id": "p2",
      "model": "ChatGPT (GPT-5.6 Luna)",     # must match a llms_covered[].label
      "status": "measured",                   # "measured" | "not_measured"
      "brand_mention": true,
      "brand_citation": true,
      "prominence": "Named first",            # brand prominence; "Absent" if no mention
      "competitor_mentions": ["semrush.com"], # competitor DOMAINS mentioned in this answer
      "competitor_citations": ["semrush.com"],# competitor DOMAINS cited as sources
      "cited_sources": [                       # every source link in the answer
        {"domain": "dataforseo.com", "page": "/apis/serp-api"},
        {"domain": "g2.com", "page": "/best-serp-api"}
      ]
    }
prose.json  : optional LLM-authored text merged onto the computed numbers:
    {
      "summary":            {"narrative": "...", "insight": "..."},
      "by_llm":             {"insight": "..."},
      "by_prompt":          {"insight": "..."},
      "citation_landscape": {"insight": "..."},
      "competitors":        {"insight": "..."},
      "search_volume":      {"rows": [{"keyword":"serp api","ai_search_volume":41}], "insight":"..."},
      "opportunities":      {"actions": [ ... ]}
    }

Output
------
data.json : the full payload {config, sections} ready for build_report.py.

Only NARRATIVE and INSIGHT strings, `search_volume` (Track A, not derivable from
cells) and `opportunities` come from prose.json; every number is computed here.
"""

import sys, json, os
from collections import Counter, defaultdict

# Must match build_report.py PROMINENCE_ORDER (strongest -> absent).
PROMINENCE_ORDER = ["Named first", "Shortlist", "Passing mention", "Absent"]


def _num(v, d=0):
    try: return float(v)
    except: return d


def _round(v, n=1):
    return round(v, n) if v is not None else None


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def build_sections(config, cells, prose):
    prompts   = config.get("prompts", []) or []
    models    = [m.get("label", "") for m in (config.get("llms_covered", []) or [])]
    n_models  = len(models)
    competitors = [c.get("domain", "") for c in (config.get("competitors", []) or [])]
    brand_domain = (config.get("brand_domain", "") or "").lower().lstrip("www.")
    weights   = config.get("score_weights", {"mention": 0.6, "citation": 0.4})
    wm, wc    = _num(weights.get("mention", 0.6)), _num(weights.get("citation", 0.4))
    live_comp = config.get("competitor_live_probing", True) is not False

    branded_of = {p["id"]: bool(p.get("branded")) for p in prompts}
    text_of    = {p["id"]: p.get("text", "") for p in prompts}
    order_of   = {p["id"]: i for i, p in enumerate(prompts)}

    # Index measured cells by (prompt_id, model).
    measured = {}
    n_failed = 0
    for c in cells:
        key = (c.get("prompt_id"), c.get("model"))
        if c.get("status") == "not_measured":
            n_failed += 1
            continue
        measured[key] = c

    unbranded_ids = [p["id"] for p in prompts if not branded_of.get(p["id"])]

    # ── Summary (headline: UNBRANDED, measured cells only) ────────────────────
    unbranded_cells = [measured[(pid, m)] for pid in unbranded_ids for m in models
                if (pid, m) in measured]
    D = len(unbranded_cells)  # score denominator
    brand_mentions_unbranded  = sum(1 for c in unbranded_cells if c.get("brand_mention"))
    brand_citations_unbranded = sum(1 for c in unbranded_cells if c.get("brand_citation"))
    mention_share  = _round(100.0 * brand_mentions_unbranded / D) if D else None
    citation_share = _round(100.0 * brand_citations_unbranded / D) if D else None
    score = _round(wm * (mention_share or 0) + wc * (citation_share or 0)) if D else None

    pw_mention = sum(1 for pid in unbranded_ids
                     if any((pid, m) in measured and measured[(pid, m)].get("brand_mention")
                            for m in models))
    pw_citation = sum(1 for pid in unbranded_ids
                      if any((pid, m) in measured and measured[(pid, m)].get("brand_citation")
                             for m in models))

    summary = {
        "mention_share": mention_share,
        "citation_share": citation_share,
        "ai_visibility_score": score,
        "prompts_total": len(unbranded_ids),
        "prompts_with_mention": pw_mention,
        "prompts_with_citation": pw_citation,
        "models_total": n_models,
        "cells_total": len(prompts) * n_models,
        "cells_measured": len(measured),
        "cells_failed": n_failed,
        "score_denominator": D,
    }
    summary.update(prose.get("summary", {}))          # narrative, insight, previous
    summary.setdefault("narrative", "")
    summary.setdefault("insight", "")

    # ── By-LLM (all prompts incl. branded, per model) ─────────────────────────
    by_llm_rows = []
    for m in models:
        cells_m = [measured[(p["id"], m)] for p in prompts if (p["id"], m) in measured]
        tested = len(cells_m)
        mentions  = sum(1 for c in cells_m if c.get("brand_mention"))
        citations = sum(1 for c in cells_m if c.get("brand_citation"))
        proms = [c.get("prominence") for c in cells_m if c.get("brand_mention")]
        avg_prom = Counter(proms).most_common(1)[0][0] if proms else "Absent"
        by_llm_rows.append({
            "model_label": m,
            "prompts_tested": tested,
            "mentions": mentions,
            "mention_rate": _round(100.0 * mentions / tested) if tested else 0,
            "citations": citations,
            "citation_rate": _round(100.0 * citations / tested) if tested else 0,
            "avg_prominence": avg_prom,
        })
    by_llm = {"rows": by_llm_rows}
    by_llm.update(prose.get("by_llm", {}))
    by_llm.setdefault("insight", "")

    # ── By-prompt (all prompts) ───────────────────────────────────────────────
    by_prompt_rows, invisible = [], []
    for p in prompts:
        pid = p["id"]
        mentioning = [m for m in models
                      if (pid, m) in measured and measured[(pid, m)].get("brand_mention")]
        cited = any((pid, m) in measured and measured[(pid, m)].get("brand_citation")
                    for m in models)
        visible = bool(mentioning)
        proms = [measured[(pid, m)].get("prominence") for m in models
                 if (pid, m) in measured and measured[(pid, m)].get("brand_mention")]
        best = min(proms, key=lambda x: PROMINENCE_ORDER.index(x)
                   if x in PROMINENCE_ORDER else 99) if proms else "Absent"
        by_prompt_rows.append({
            "prompt": text_of[pid], "type": p.get("type", ""),
            "models_mentioning": mentioning, "models_total": n_models,
            "prominence": best, "cited": cited, "visible": visible,
        })
        if not visible and not cited:          # #16: invisible = no mention AND no citation
            invisible.append(text_of[pid])
    by_prompt = {"rows": by_prompt_rows, "invisible_prompts": invisible}
    by_prompt.update(prose.get("by_prompt", {}))
    by_prompt.setdefault("insight", "")

    # ── Citation landscape (from cited_sources across all measured cells) ──────
    dom_counts = Counter()
    page_counts = Counter()  # (domain, page) -> count
    for c in measured.values():
        seen_dom, seen_page = set(), set()
        for src in (c.get("cited_sources", []) or []):
            dom = (src.get("domain", "") or "").lower().lstrip("www.")
            page = src.get("page", "")
            if dom and dom not in seen_dom:
                dom_counts[dom] += 1; seen_dom.add(dom)
            if dom and (dom, page) not in seen_page:
                page_counts[(dom, page)] += 1; seen_page.add((dom, page))
    total_dom = sum(dom_counts.values())
    top_domains = [{
        "domain": d, "citations": n,
        "share": _round(100.0 * n / total_dom) if total_dom else 0,
        "is_brand": d == brand_domain,
    } for d, n in sorted(dom_counts.items(), key=lambda kv: (-kv[1], kv[0]))[:10]]
    top_pages = [{
        "page": pg, "domain": d, "citations": n, "is_brand": d == brand_domain,
    } for (d, pg), n in sorted(page_counts.items(), key=lambda kv: (-kv[1], kv[0][0]))[:8]]
    brand_pages = sorted({f"{d}{pg}" for (d, pg), n in page_counts.items()
                          if d == brand_domain})
    citation_landscape = {"top_domains": top_domains, "top_pages": top_pages,
                          "brand_cited_pages": brand_pages}
    citation_landscape.update(prose.get("citation_landscape", {}))
    citation_landscape.setdefault("insight", "")

    # ── Competitors (live basis, SoV over UNBRANDED measured cells) ───────────
    competitors_section = None
    if competitors and live_comp:
        name_of = {c.get("domain", ""): c.get("name", c.get("domain", ""))
                   for c in (config.get("competitors", []) or [])}
        entities = ["__brand__"] + competitors

        def ment(entity, cellset):
            if entity == "__brand__":
                return sum(1 for c in cellset if c.get("brand_mention"))
            return sum(1 for c in cellset if entity in (c.get("competitor_mentions") or []))

        def cite(entity, cellset):
            if entity == "__brand__":
                return sum(1 for c in cellset if c.get("brand_citation"))
            return sum(1 for c in cellset if entity in (c.get("competitor_citations") or []))

        m_counts = {e: ment(e, unbranded_cells) for e in entities}
        c_counts = {e: cite(e, unbranded_cells) for e in entities}
        m_sum, c_sum = sum(m_counts.values()), sum(c_counts.values())
        rows = []
        for e in entities:
            msov = _round(100.0 * m_counts[e] / m_sum) if m_sum else 0
            csov = _round(100.0 * c_counts[e] / c_sum) if c_sum else None
            vis = _round(wm * (msov or 0) + wc * csov) if csov is not None \
                else _round(wm * (msov or 0))
            row = {
                "name": config.get("brand_name", brand_domain) if e == "__brand__" else name_of.get(e, e),
                "domain": brand_domain if e == "__brand__" else e,
                "mention_share": msov, "citation_share": csov, "ai_visibility_score": vis,
            }
            if e == "__brand__":
                row["is_brand"] = True
            rows.append(row)

        by_model = []
        for m in models:
            cm = [measured[(pid, m)] for pid in unbranded_ids if (pid, m) in measured]
            mm = {e: ment(e, cm) for e in entities}
            tot = sum(mm.values())
            by_model.append({
                "model_label": m,
                "brand_mention_share": _round(100.0 * mm["__brand__"] / tot) if tot else 0,
                "competitors": [{"domain": d, "mention_share": _round(100.0 * mm[d] / tot) if tot else 0}
                                for d in competitors],
            })
        competitors_section = {"live_basis": True, "rows": rows, "by_model": by_model}
        competitors_section.update(prose.get("competitors", {}))
        competitors_section.setdefault("insight", "")
    elif competitors:
        # dataset basis: numbers come from Track A via prose (operator supplies rows).
        competitors_section = prose.get("competitors")

    sections = {
        "summary": summary,
        "by_llm": by_llm,
        "by_prompt": by_prompt,
        "citation_landscape": citation_landscape,
    }
    if competitors_section:
        sections["competitors"] = competitors_section
    if prose.get("search_volume"):
        sections["search_volume"] = prose["search_volume"]
    sections["opportunities"] = prose.get("opportunities", {"actions": []})
    return sections


def main(argv):
    args = [a for a in argv if a != "-o"]
    out = None
    if "-o" in argv:
        out = argv[argv.index("-o") + 1]
        args = [a for a in args if a != out]
    if len(args) < 2:
        print("Usage: python aggregate.py <config.json> <cells.json> [<prose.json>] -o <data.json>")
        return 1
    config_path, cells_path = args[0], args[1]
    prose_path = args[2] if len(args) > 2 else None

    config = load(config_path)
    cells  = load(cells_path)
    prose  = load(prose_path) if prose_path and os.path.exists(prose_path) else {}

    sections = build_sections(config, cells, prose)
    payload = {"config": config, "sections": sections}

    if not out:
        out = config.get("output_path", "").replace(".pdf", ".json") or "data.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    s = sections["summary"]
    print(f"Aggregated {len(cells)} cells -> {out}")
    print(f"  Score {s['ai_visibility_score']}/100 | mention {s['mention_share']}% | "
          f"citation {s['citation_share']}% | {s['score_denominator']} unbranded measured | "
          f"{s['cells_failed']} failed")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
