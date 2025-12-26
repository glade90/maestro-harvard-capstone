#!/usr/bin/env python3
"""
Analyze a results_summary CSV and report overall counts, percentages,
95% CIs and a one-tailed two-proportion z-test comparing Single vs Multi success rates.
(H0: multi <= single, Ha: multi > single)

Usage:
  python analyze_results.py path/to/results_summary_live.csv [--alpha 0.05] [--out out.json]
"""
from pathlib import Path
import csv
import json
import math
import argparse

def phi(z):
    # standard normal CDF
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))

def two_proportion_ztest_one_tailed(x1, n1, x2, n2):
    """
    One-tailed z-test for proportions.
    H0: p2 <= p1 (multi <= single)
    Ha: p2 > p1 (multi > single)
    Returns one-tailed p-value for Ha: multi > single
    """
    if n1 == 0 or n2 == 0:
        return None
    p1 = x1 / n1
    p2 = x2 / n2
    p_pool = (x1 + x2) / (n1 + n2)
    se = math.sqrt(p_pool * (1 - p_pool) * (1.0 / n1 + 1.0 / n2))
    if se == 0:
        return None
    z = (p2 - p1) / se  # Note: p2 - p1 (multi - single) for testing multi > single
    # One-tailed p-value: P(Z > z) if z > 0, else very high p-value
    p_value = 1 - phi(z)
    return {"z": z, "p_value": p_value, "diff": p2 - p1, "p1": p1, "p2": p2}

def ci_for_prop(x, n, alpha=0.05):
    if n == 0:
        return (None, None)
    p = x / n
    z = abs(math.erf(0))  # placeholder
    z = 1.96 if abs(alpha - 0.05) < 1e-9 else -1  # default 95% if alpha 0.05
    se = math.sqrt(p * (1 - p) / n)
    lo = p - 1.96 * se
    hi = p + 1.96 * se
    lo = max(0.0, lo)
    hi = min(1.0, hi)
    return (lo, hi)

def analyze(path: Path, alpha: float = 0.05):
    multi_outcomes = {}
    single_outcomes = {}
    rows = 0
    single_attempts = single_successes = 0
    multi_attempts = multi_successes = 0
    with path.open("r", encoding="utf-8", newline="") as fh:
        rdr = csv.DictReader(fh)
        for r in rdr:
            rows += 1
            s_out = (r.get("single_outcome") or "").strip().upper()
            m_out = (r.get("multi_outcome") or "").strip().upper()
            # single agent bookkeeping
            if s_out:
                single_attempts += 1
                single_outcomes[s_out] = single_outcomes.get(s_out, 0) + 1
                if s_out == "SUCCESS":
                    single_successes += 1
            else:
                # treat missing single outcome explicitly
                single_outcomes["FAIL-MISSING"] = single_outcomes.get("FAIL-MISSING", 0) + 1

            # multi agent bookkeeping
            if m_out:
                multi_attempts += 1
                multi_outcomes[m_out] = multi_outcomes.get(m_out, 0) + 1
                if m_out == "SUCCESS":
                    multi_successes += 1
            else:
                # treat missing multi outcome explicitly
                multi_outcomes["FAIL-MISSING"] = multi_outcomes.get("FAIL-MISSING", 0) + 1

    res = {
        "rows": rows,
        "single": {"attempts": single_attempts, "successes": single_successes},
        "multi": {"attempts": multi_attempts, "successes": multi_successes},
        "multi_outcome_breakdown": multi_outcomes,
        "single_outcome_breakdown": single_outcomes,
    }

    # proportions & CIs
    def pct(x, n):
        return 100.0 * x / n if n > 0 else None
    res["single"]["pct"] = pct(single_successes, single_attempts)
    res["multi"]["pct"] = pct(multi_successes, multi_attempts)
    res["single"]["95ci"] = tuple(ci_for_prop(single_successes, single_attempts, alpha))
    res["multi"]["95ci"] = tuple(ci_for_prop(multi_successes, multi_attempts, alpha))

    # one-tailed two-proportion z-test (H0: multi <= single, Ha: multi > single)
    tp = two_proportion_ztest_one_tailed(single_successes, single_attempts, multi_successes, multi_attempts)
    res["two_proportion_test"] = tp
    if tp:
        res["significant"] = tp["p_value"] < alpha
    else:
        res["significant"] = None

    # effect size metrics
    if single_attempts > 0 and multi_attempts > 0:
        p1 = single_successes / single_attempts if single_attempts else 0.0
        p2 = multi_successes / multi_attempts if multi_attempts else 0.0
        res["effect"] = {"difference": p1 - p2, "relative_risk": (p2 / p1) if p1 > 0 else None}
    else:
        res["effect"] = {"difference": None, "relative_risk": None}

    return res

def nice_print(res, alpha=0.05):
    print("=== Overall Results Summary ===")
    print(f"Rows processed: {res['rows']}")
    print("")
    s = res["single"]
    m = res["multi"]
    def fmt_pct(v):
        return f"{v:.2f}%" if v is not None else "N/A"
    print(f"Single Agent: {s['successes']} / {s['attempts']}  => {fmt_pct(s['pct'])} (95% CI: {fmt_pct(s['95ci'][0]*100) if s['95ci'][0] is not None else 'N/A'} - {fmt_pct(s['95ci'][1]*100) if s['95ci'][1] is not None else 'N/A'})")
    print(f"Multi  Agent: {m['successes']} / {m['attempts']}  => {fmt_pct(m['pct'])} (95% CI: {fmt_pct(m['95ci'][0]*100) if m['95ci'][0] is not None else 'N/A'} - {fmt_pct(m['95ci'][1]*100) if m['95ci'][1] is not None else 'N/A'})")
    print("")
    print("Single Agent outcome breakdown:")
    total_single = sum(res["single_outcome_breakdown"].values()) if res.get("single_outcome_breakdown") else 0
    for k, v in sorted(res["single_outcome_breakdown"].items(), key=lambda x: -x[1]):
        pctv = 100.0 * v / total_single if total_single > 0 else 0.0
        print(f"  {k}: {v} ({pctv:.1f}%)")
    print("")
    print("Multi Agent outcome breakdown:")
    total_multi = sum(res["multi_outcome_breakdown"].values())
    for k, v in sorted(res["multi_outcome_breakdown"].items(), key=lambda x: -x[1]):
        pctv = 100.0 * v / total_multi if total_multi > 0 else 0.0
        print(f"  {k}: {v} ({pctv:.1f}%)")
    print("")
    tp = res.get("two_proportion_test")
    if tp:
        print("One-tailed two-proportion z-test (H0: multi <= single, Ha: multi > single):")
        print(f"  p1 (single) = {tp['p1']:.4f}, p2 (multi) = {tp['p2']:.4f}")
        print(f"  diff (multi - single) = {tp['diff']:.4f}")
        print(f"  z = {tp['z']:.3f}, p-value (one-tailed) = {tp['p_value']:.4f}")
        if res["significant"] is True:
            print(f"  Conclusion: Multi SIGNIFICANTLY OUTPERFORMS Single at alpha={alpha}")
        elif res["significant"] is False:
            print(f"  Conclusion: NOT statistically significant at alpha={alpha}")
        else:
            print("  Conclusion: Test could not be performed (insufficient data).")
    else:
        print("Insufficient data to perform two-proportion test.")

def main():
    ap = argparse.ArgumentParser(description="Analyze results_summary CSV (overall percentages & stats)")
    ap.add_argument("csv", help="Path to results_summary CSV")
    ap.add_argument("--alpha", type=float, default=0.05, help="significance level (default 0.05)")
    ap.add_argument("--out", help="Optional JSON output path")
    args = ap.parse_args()
    path = Path(args.csv)
    if not path.exists():
        raise SystemExit(f"[error] file not found: {path}")
    res = analyze(path, args.alpha)
    nice_print(res, args.alpha)
    if args.out:
        out = Path(args.out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as fh:
            json.dump(res, fh, indent=2)
        print(f"[ok] JSON written to {out.resolve()}")

if __name__ == "__main__":
    main()