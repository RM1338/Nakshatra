"""Control places: false positives (SRS-NF-8) and calibration of s and τ (ALG §6.3, §7.2, §10.1).

    python -m eval.controls

Controls = real places listed in eval/controls.txt (cached runs) + synthetic cities without a planted crew.
Prints *suggested* values; freezing them in config.yaml is a deliberate, committed step (T31).
"""
from __future__ import annotations

import argparse
from itertools import combinations
from pathlib import Path

import numpy as np
from scipy.stats import poisson

from eval.common import eval_config, real_sources, synthetic_source, write_json
from nakshatra.algo import peel, significance
from nakshatra.algo.judge import judge


def control_sources(n_synth: int, cfg):
    ids = [ln.strip() for ln in (Path(__file__).parent / "controls.txt").read_text().splitlines()
           if ln.strip() and not ln.startswith("#")]
    real = [s for s in real_sources(cfg=cfg) if any(s.name.endswith(i[-8:]) for i in ids)]
    return real + [synthetic_source(200 + i, ring_size=0, cfg=cfg) for i in range(n_synth)]


def run(n_synth: int) -> dict:
    cfg = eval_config()
    srcs = control_sources(n_synth, cfg)
    flagged, densities, lam1, m_obs = [], [], [], []
    for src in srcs:
        judged = judge(src.g, src.seed, src.baseline_dps, cfg)
        flagged.append(any(j.reported for j in judged))
        adj, cw = peel.build(src.g, src.seed)
        S_u, S_p, _ = peel.peel_once(adj, peel._transpose(adj), cw)  # densest block, ring or not
        densities.append(max([j.ring.density for j in judged] + [peel.ring_density(S_u, S_p, adj, cw)]))
        d_ps = [p.d_p if p.d_p is not None else 50 for p in src.g.places] + src.baseline_dps
        H1 = significance.city_concentration(d_ps, 1.0)
        expanded = [u for u in adj if src.g.users[u].expanded]
        for u, v in combinations(expanded, 2):
            ku = max(src.g.users[u].k_u or 0, len(adj[u]))
            kv = max(src.g.users[v].k_u or 0, len(adj[v]))
            lam1.append(ku * kv * H1)
            m_obs.append(len(adj[u] & adj[v]))
    alpha = cfg.stats.alpha
    lam1, m_obs = np.array(lam1), np.array(m_obs)
    grid = np.round(np.logspace(0, 2, 41), 3)
    share = {float(s): float(np.mean([(poisson.sf(m - 1, lam / s**2) if m > 0 else 1.0) < alpha
                                      for lam, m in zip(lam1, m_obs, strict=True)])) if len(m_obs) else None
             for s in grid}
    ok = [s for s, sh in share.items() if sh is not None and sh <= alpha]
    return {"config_hash": cfg.hash(), "alpha": alpha, "sources": [s.name for s in srcs],
            "flagged": int(sum(flagged)), "n_controls": len(srcs), "target_max_flagged_per_10": 1,
            "pairs": len(m_obs), "pair_share_below_alpha_by_s": share,
            "suggested": {"mass_scale": min(ok) if ok else None,
                          "tau": float(np.percentile(densities, 95)) if densities else None},
            "control_best_densities": densities}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--synth", type=int, default=5)
    res = run(ap.parse_args(argv).synth)
    print("wrote", write_json("controls", eval_config(), res))
    print({k: res[k] for k in ("flagged", "n_controls", "pairs", "suggested")})


if __name__ == "__main__":
    main()
