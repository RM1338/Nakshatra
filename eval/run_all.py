"""make eval: every evaluation with fixed seeds, outputs under eval/plots/ tagged with the config hash.

    python -m eval.run_all [--quick]
"""
from __future__ import annotations

import argparse
import time

from eval import controls, efficiency, null_shuffle, run_injection
from eval.common import eval_config, out_path


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--quick", action="store_true", help="smaller samples for a smoke run")
    q = ap.parse_args(argv).quick
    cfg = eval_config()
    t0 = time.time()
    run_injection.main(["--seed", "7", "--synth", "1" if q else "3"])
    controls.main(["--synth", "2" if q else "5"])
    null_shuffle.main(["--n", "40" if q else "200", "--synth", "1" if q else "3"])
    efficiency.main(["--worlds", "1" if q else "3"])
    import json
    load = lambda n: json.loads(out_path(n, cfg, "json").read_text())  # noqa: E731
    inj, ctl, nul, eff = load("injection"), load("controls"), load("null_calibration"), load("credit_efficiency")
    s = inj["summary_rings_ge_8"]
    lines = [
        f"# Evaluation summary (config {cfg.hash()[:8]})", "",
        f"Sources: {', '.join(inj['sources'])}", "",
        "| Check | Result | Target |", "| --- | --- | --- |",
        f"| Injected rings ≥ 8 accounts: recall | {s['recall']:.2f} | ≥ 0.8 |",
        f"| Injected rings ≥ 8 accounts: precision | {s['precision'] if s['precision'] is None else round(s['precision'], 2)} | ≥ 0.8 |",
        f"| Control places flagged | {ctl['flagged']} of {ctl['n_controls']} | ≤ 1 of 10 |",
        f"| Null graphs with p < α ({nul['n_null_graphs']} shuffles) | {nul['share_below_alpha']:.3f} | {nul['target_band'][0]}–{nul['target_band'][1]} |",
        f"| Credits for 0.8 recall: priority / BFS / random | {' / '.join(str(eff['credits_for_0.8_recall'][k]) for k in ('priority', 'bfs', 'random'))} | priority ≤ 50% of BFS |",
        "", "Stress grid (8 × 8, camouflage 0.3), recall by coverage × place popularity:", "",
    ]
    lines += [f"- {k}: {v['recall']:.2f}" for k, v in sorted(inj["stress_8x8_camo0.3"].items())]
    lines += ["", f"Suggested calibration (not yet frozen): {ctl['suggested']}", "", f"Wall time {time.time() - t0:.0f}s"]
    p = out_path("summary", cfg, "md")
    p.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
