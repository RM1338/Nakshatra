"""Evidence dossier (LLD §8.3, API §5.2, SRS-RP-4): the only output with raw contributor IDs.

Sections: summary, seed place, method and parameters, rings (pseudonym ↔ contributor ID, shared places with
dates), statistical evidence, credit ledger with SerpApi search IDs, limitations.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

from nakshatra.report.templates import check_copy
from nakshatra.store.db import Store

ENGINES = {"google_maps": "Google Maps (place lookup / area search)", "google_maps_reviews": "Google Maps Reviews",
           "google_maps_contributor_reviews": "Google Maps Contributor Reviews"}
WARNING = ("This file contains Google Maps contributor IDs. Use it for reporting to Google or a consumer authority, "
           "not for publication.")
LIMITATIONS = [
    "This is a statistical anomaly with evidence, not a finding about anyone's intent. Real communities "
    "(a college group, a family, a tour group) can look like coordinated groups; check the notes and the evidence.",
    "Only groups that reuse the same accounts across several places are detectable. Single accounts, groups smaller "
    "than 4 accounts by 3 places, and reviews Google has already removed are not; any finding is a lower bound.",
    "The adjusted rating describes the newest sampled reviews only. Its interval reflects sampling noise with group "
    "membership held fixed, not uncertainty about who belongs to a group.",
    "Contributor histories are capped at 200 reviews by SerpApi and carry relative dates (\"2 months ago\"), which are "
    "intervals, not points. Exact dates come only from place review pages.",
    "Places whose total review count was never fetched are weighted as if they had 50 reviews.",
]


def _day(t: float | None) -> str:
    return datetime.fromtimestamp(t, UTC).strftime("%d %b %Y") if t is not None else "?"


def _when(r: dict) -> str:
    if r["t_lo"] is None or r["t_hi"] is None:
        return "date unknown"
    return _day(r["t_lo"]) if r["exact"] else f"between {_day(r['t_lo'])} and {_day(r['t_hi'])}"


def _table(head: list[str], rows: list[list]) -> list[str]:
    esc = lambda x: str(x).replace("|", "\\|").replace("\n", " ")  # noqa: E731
    return ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)] + \
           ["| " + " | ".join(esc(c) for c in r) + " |" for r in rows]


def render_md(store: Store, run_id: str) -> str:
    row = store.run_get(run_id)
    res = store.result_get(run_id)
    if row is None or res is None:
        raise ValueError(f"run {run_id} has no result")
    cfg = json.loads(row["config_json"])
    raw = {i: json.loads(m) for i, m in store.conn.execute(
        "SELECT idx, members_json FROM rings WHERE run_id=? ORDER BY idx", (run_id,))}
    seed, rating, cov = res["seed"], res["rating"], res["coverage"]
    reported = [r for r in res["rings"] if r["reported"]]
    L: list[str] = [f"# Nakshatra evidence dossier: {seed['title']}", "", f"> {WARNING}", ""]

    L += ["## 1. Summary", "", res.get("verdict") or res.get("no_coordination_message") or "", ""]
    if row["state"] != "done":
        L += [f"Partial result: the investigation ended as **{row['state']}** before full coverage.", ""]
    lo, hi = rating["ci"]
    L += [f"- Rating shown on Google: {rating['displayed']}",
          f"- Recent rating with coordinated accounts set aside: {rating['adjusted']} (95% interval {lo}–{hi}), "
          f"from the newest {rating['n_sampled']} reviews",
          f"- Coordinated groups reported: {len(reported)}; other candidates tested: {len(res['rings']) - len(reported)}",
          f"- Coverage: {cov['reviewers_expanded']} reviewer histories, {cov['places']} places, {cov['edges']} reviews"
          + (" (low coverage)" if cov.get("low_coverage") else ""), ""]

    L += ["## 2. Seed place", "", f"- Name: {seed['title']}", f"- Google Maps data ID: `{seed['data_id']}`",
          f"- Rating {seed['rating']} from {seed['d_p']} reviews",
          f"- Investigation `{run_id}`, started {_day(row['started_at'])} (UTC)", ""]

    st = cfg["stats"]
    L += ["## 3. Method and parameters", "",
          "Reviewers of the place were followed to their other reviews through SerpApi, in priority order, within a "
          f"budget of {row['budget']} searches. Groups were mined by popularity-weighted densest-subgraph peeling "
          "(each place weighted by 1/log(reviews + 5), using its total Google review count), and tested by rewiring the "
          f"crawled graph {st['n_perm']}–{st['n_perm_max']} times with every account's and place's number of reviews "
          "kept, rerunning the same search. A group is reported when fewer than "
          f"{st['alpha']:.0%} of the rewired graphs produce one as dense. No language model is involved in any decision.",
          "", f"- Configuration hash: `{res['config_hash']}`",
          f"- Minimum group: {cfg['ring']['min_users']} accounts × {cfg['ring']['min_places']} places, each account "
          f"covering ≥ {cfg['ring']['min_coverage']:.0%} of them",
          f"- Timing window δ = {cfg['time']['delta_days']:g} days; rating shrinkage κ = {cfg['rating']['kappa']:g}, "
          f"τ = {cfg['rating']['tau']:g}; bootstrap {cfg['rating']['bootstrap_n']} resamples, seed "
          f"{cfg['rating']['bootstrap_seed']}", ""]

    L += ["## 4. Coordinated groups", ""]
    if not reported:
        L += ["No group passed the test.", ""]
    for n, r in enumerate(reported, 1):
        ids = raw.get(r["idx"], [])
        L += [f"### Group {n}: {len(r['members'])} accounts, {len(r['places'])} shared places", ""]
        L += _table(["Account", "Google Maps contributor ID"],
                    [[m, ids[i] if i < len(ids) else "?"] for i, m in enumerate(r["members"])]) + [""]
        for p in r.get("evidence", []):
            L += [f"**{p['title']}** (`{p['data_id']}`, {p['d_p'] if p['d_p'] is not None else 'unknown'} reviews in "
                  f"total{', most members posted within ' + format(cfg['time']['delta_days'], 'g') + ' days' if p['lockstep'] else ''})", ""]
            L += _table(["Account", "Stars", "When"], [[x["member"], f"{x['rating']:g}", _when(x)] for x in p["reviews"]])
            L.append("")
        L += [f"Notes: {' '.join(r['notes'])}", ""] if r.get("notes") else []

    L += ["## 5. Statistical evidence", ""]
    rows = [[n, r["density"], r["pval"], r["expected_overlap"], r["observed_overlap"],
             f"{r.get('poisson_expected', '–')} / {r.get('pair_pval', '–')}",
             "not resolvable" if r["lockstep_ratio"] is None else f"{r['lockstep_ratio']:.0%}",
             "reported" if r["reported"] else "not reported"]
            for n, r in enumerate(res["rings"], 1)]
    L += (_table(["Group", "Density", "Permutation p", "Shared by chance (mean)", "Shared observed (mean)",
                  "City model: expected / p", "Posted together", "Outcome"], rows) if rows else ["No candidates."])
    L += ["", "Shared places by chance: mean over account pairs in the rewired graphs. City model: Poisson, with each "
          "place's share of all observed reviews; shown for reference, it does not decide reporting.", ""]

    ledger = store.ledger(run_id, 0, 10_000)
    tot = store.ledger_totals(run_id)
    L += ["## 6. Credit ledger", "", f"{tot['billed']} searches billed, {tot['cached']} served from the local cache, "
          f"{tot['failed']} failed. Each search ID can be looked up in SerpApi's Search Archive.", ""]
    L += _table(["#", "Engine", "Cost", "Search ID"],
                [[i, ENGINES.get(x["engine"], x["engine"]), "cache" if x["cached"] else "1 credit" if x["billed"] else "none",
                  x["search_id"] or "–"] for i, x in enumerate(ledger, 1)]) + [""]

    L += ["## 7. Limitations", ""] + [f"- {x}" for x in LIMITATIONS] + [""]
    return check_copy("\n".join(L))


def render_pdf(md: str) -> bytes:
    """Raises ImportError/OSError when WeasyPrint or its system libraries are missing (API: E_PDF_UNAVAILABLE)."""
    import markdown
    import weasyprint
    body = markdown.markdown(md, extensions=["tables"])
    css = ("body{font-family:sans-serif;font-size:10pt;line-height:1.45;margin:0 1cm}"
           "table{border-collapse:collapse;margin:.4em 0}td,th{border:1px solid #ccd;padding:2px 6px;text-align:left}"
           "blockquote{border-left:3px solid #F0A33A;margin:0;padding-left:.8em}code{font-size:9pt}")
    return weasyprint.HTML(string=f"<html><head><meta charset='utf-8'><style>{css}</style></head><body>{body}</body></html>"
                           ).write_pdf()
