#!/usr/bin/env python3
"""
Plot year-by-year or day-by-day success chart from a results CSV.

Usage:
  python plot_results.py results_summary_live.csv [-o out.png] [--by-day]

If -o is omitted, writes "model_comparison_chart_year.png" (or *_day.png) next to the input CSV.
"""
from pathlib import Path
import sys
import csv
import re
from collections import defaultdict

from paths import get_maestro_nano_root

try:
    import matplotlib.pyplot as plt
    import numpy as np
    from matplotlib.gridspec import GridSpec
    _have_mpl = True
except Exception:
    _have_mpl = False

DAY_RE = re.compile(r"day\s*?0*(\d{1,2})", re.I)
NUM_RE = re.compile(r"\b(\d{1,2})\b")
AGG_TAG_RE = re.compile(r"^(io|req|tdd|code)\s*0*(\d+)\b", re.I)


def _agg_tag_sort_key(tag: str):
    """Sort agg tags as: io1..io11..req1..tdd1..code1..; unknowns go last."""
    t = (tag or "").strip()
    m = AGG_TAG_RE.match(t)
    if not m:
        return (99, 10**9, t.lower())
    group = m.group(1).lower()
    num = int(m.group(2))
    group_order = {"io": 0, "req": 1, "tdd": 2, "code": 3}
    return (group_order.get(group, 98), num, t.lower())

def _extract_day_from_row(r: dict) -> int | None:
    # try common keys first
    for k in ("day", "day_label", "daynum", "problem", "title", "problem_description"):
        v = (r.get(k) or "").strip()
        if not v:
            continue
        m = DAY_RE.search(v)
        if m:
            return int(m.group(1))
        m2 = NUM_RE.search(v)
        if m2:
            # fallback: prefer numbers that look like day numbers <= 25
            val = int(m2.group(1))
            if 1 <= val <= 25:
                return val
    # try any value in row
    for v in r.values():
        if not isinstance(v, str):
            continue
        mv = DAY_RE.search(v)
        if mv:
            return int(mv.group(1))
        mv2 = NUM_RE.search(v)
        if mv2:
            val = int(mv2.group(1))
            if 1 <= val <= 25:
                return val
    return None

def plot_from_csv(csv_path: Path, out_path: Path, by_day: bool = False, by_agg_tag: bool = False):
    if not _have_mpl:
        print("[warn] matplotlib/numpy not available; cannot generate chart")
        return

    if not csv_path.exists():
        print(f"[error] CSV not found: {csv_path}")
        return

    outcome_keys = ["SUCCESS", "FAIL-ERROR", "FAIL-INCORRECT", "FAIL-MISSING"]
    categories = []
    single_counts = defaultdict(lambda: {"succ": 0, "attempted": 0})
    multi_counts = defaultdict(lambda: {"succ": 0, "attempted": 0})
    per_cat_multi = defaultdict(lambda: {k: 0 for k in outcome_keys})

    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            if by_agg_tag:
                cat = (r.get("agg_tag") or "").strip()
                if not cat:
                    continue
            elif by_day:
                day = _extract_day_from_row(r)
                if day is None:
                    continue
                year = (r.get("year") or "").strip()
                # category key is tuple (day, year) so tick labels can include both
                cat = (int(day), year)
            else:
                cat = (r.get("year") or "").strip()
                if not cat:
                    continue
            if cat not in categories:
                categories.append(cat)

            s_out = (r.get("single_outcome") or "").strip().upper()
            if s_out:
                single_counts[cat]["attempted"] += 1
                if s_out == "SUCCESS":
                    single_counts[cat]["succ"] += 1

            m_out = (r.get("multi_outcome") or "").strip().upper()
            if m_out:
                multi_counts[cat]["attempted"] += 1
                if m_out == "SUCCESS":
                    multi_counts[cat]["succ"] += 1
                per_cat_multi[cat][m_out if m_out in outcome_keys else "FAIL-INCORRECT"] += 1
            else:
                per_cat_multi[cat]["FAIL-MISSING"] += 1

    # normalize sort order: for days numeric sort (by day then year), for years string sort, for agg_tag custom io/req/tdd/code order
    if by_agg_tag:
        categories = sorted(set(categories), key=_agg_tag_sort_key)
    elif by_day:
        categories = sorted(set(categories), key=lambda x: (int(x[0]), x[1] or ""))
    else:
        categories = sorted(set(categories))

    if not categories:
        print("[warn] no data rows found in CSV for chosen mode")
        return

    single_rates = []
    multi_rates = []
    for c in categories:
        s = single_counts[c]
        m = multi_counts[c]
        sr = (s["succ"] / s["attempted"] * 100) if s["attempted"] > 0 else 0.0
        mr = (m["succ"] / m["attempted"] * 100) if m["attempted"] > 0 else 0.0
        single_rates.append(sr)
        multi_rates.append(mr)

    # styling
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "Times", "DejaVu Serif"],
        "font.size": 11,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
        "legend.fontsize": 10,
        "figure.dpi": 300,
    })

    single_col = "#bdbdbd"
    # lighter blue
    multi_col = "#7BAAF7"
    pie_colors = {"SUCCESS": "#54A24B", "FAIL-ERROR": "#E45756", "FAIL-INCORRECT": "#F58518", "FAIL-MISSING": "#9D9DA1"}

    # Special mode: by aggregation tag should be horizontal and multi-only
    if by_agg_tag:
        total_attempted = sum(multi_counts[c]["attempted"] for c in categories)
        total_success = sum(multi_counts[c]["succ"] for c in categories)
        avg_rate = (total_success / total_attempted * 100) if total_attempted > 0 else 0.0

        n = len(categories)
        # make figure ~20% narrower than before
        fig_w = 8
        # make this mode taller so labels remain readable
        fig_h = max(10, n * 0.60)
        fig, ax = plt.subplots(figsize=(fig_w, fig_h))

        # no title (requested)

        # Color rule (as requested): highest=red, lowest=green (ties allowed), all others=original blue.
        default_blue = "#7BAAF7"
        max_red = "#d62728"
        min_green = "#2ca02c"
        max_rate = max(multi_rates)
        min_rate = min(multi_rates)
        if max_rate == min_rate:
            bar_colors = [max_red for _ in multi_rates]
        else:
            bar_colors = [max_red if r == max_rate else (min_green if r == min_rate else default_blue) for r in multi_rates]

        y = np.arange(n)
        bar_thickness = 0.90
        bars = ax.barh(y, multi_rates, height=bar_thickness, label="Multi Agent", color=bar_colors, alpha=0.98)
        # no x-axis labels (requested)
        ax.set_xlabel("")
        ax.set_yticks(y)
        ax.set_yticklabels(categories)
        # Make first category appear at the top (matplotlib barh defaults to bottom-up)
        ax.invert_yaxis()
        ax.set_xlim(0, 120)
        ax.set_xticks([])
        ax.axvline(avg_rate, color="#888888", linestyle=":", linewidth=2, alpha=0.9)
        ax.annotate(
            f"x\u0304 = {avg_rate:.0f}%",
            xy=(avg_rate, 1.0),
            xycoords=("data", "axes fraction"),
            xytext=(0, 6),
            textcoords="offset points",
            ha="center",
            va="bottom",
            fontsize=12,
            color="#777777",
        )
        ax.tick_params(axis="y", labelsize=14)
        ax.tick_params(axis="x", bottom=False, labelbottom=False)
        # no gridlines (requested)
        ax.set_axisbelow(True)
        for name, spine in ax.spines.items():
            spine.set_visible(False)
        ax.spines["left"].set_visible(True)
        ax.spines["left"].set_color("#444444")
        ax.spines["left"].set_linewidth(0.8)
        ax.legend(loc="lower right", frameon=False)

        for b in bars:
            w = b.get_width()
            ax.annotate(f"{w:.0f}%", xy=(w, b.get_y() + b.get_height() / 2), xytext=(6, 0),
                        textcoords="offset points", ha="left", va="center", fontsize=12)

        plt.tight_layout(rect=[0, 0.02, 1, 0.96])
        try:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
            plt.close(fig)
            print(f"[ok] chart saved to {out_path}")
        except Exception as e:
            print(f"[error] failed to save chart: {e}")
        return

    n = len(categories)
    # scale width: days tend to be many columns so keep per-column width smaller
    fig_w = max(10, n * (0.48 if by_day else 1.2))
    fig_h = 8
    fig = plt.figure(figsize=(fig_w, fig_h))
    # keep a small spacer row between bar chart and pies
    gs = GridSpec(3, n, height_ratios=[2.4, 0.04, 1], figure=fig)

    # Master H1 title
    if by_agg_tag:
        title = "Single Vs. Multi Agent Testing by Aggregation Tag"
    elif by_day:
        title = "Single Vs. Multi Agent Testing by Day"
    else:
        title = "Single Vs. Multi Agent Testing by Year"
    fig.suptitle(title, fontsize=16, fontweight="bold", y=0.99)

    ax_bar = fig.add_subplot(gs[0, :])
    x = np.arange(n)
    width = 0.36
    bars1 = ax_bar.bar(x - width/2, single_rates, width, label="Single Agent", color=single_col, alpha=0.98)
    bars2 = ax_bar.bar(x + width/2, multi_rates,  width, label="Multi Agent",  color=multi_col,  alpha=0.98)

    for b in bars1 + bars2:
        h = b.get_height()
        ax_bar.annotate(f"{h:.0f}%", xy=(b.get_x() + b.get_width()/2, h), xytext=(0, 6),
                        textcoords="offset points", ha="center", va="bottom", fontsize=12)

    # remove X axis label (keep ticks) but append Year + "Day " in by-day mode to tick labels
    ax_bar.set_ylabel("Success Rate (%)", fontweight="bold")
    ax_bar.set_xticks(x)
    # format tick labels:
    if by_agg_tag:
        ax_bar.set_xticklabels(categories, rotation=45, ha="right")
    elif by_day:
        xticks = []
        for c in categories:
            day, year = c
            if year:
                xticks.append(f"{year} Day {int(day)}")
            else:
                xticks.append(f"Day {int(day)}")
        ax_bar.set_xticklabels(xticks, rotation=45, ha="right")
    else:
        ax_bar.set_xticklabels(categories, rotation=45, ha="right")

    ax_bar.set_ylim(0, 120)
    ax_bar.set_yticks([0,20,40,60,80,100])
    ax_bar.yaxis.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
    ax_bar.set_axisbelow(True)
    ax_bar.legend(loc="upper right", frameon=False)
    for name, spine in ax_bar.spines.items():
        spine.set_visible(False)
    ax_bar.spines["bottom"].set_visible(True)
    ax_bar.spines["bottom"].set_color("#444444")
    ax_bar.spines["bottom"].set_linewidth(0.8)

    # reserve middle row for pies (draw pies there so they sit closer to top)
    ax_title = fig.add_subplot(gs[1, :])
    ax_title.axis("off")

    # draw pies in middle row
    for i, c in enumerate(categories):
        ax = fig.add_subplot(gs[2, i])
        data = per_cat_multi[c]
        vals = [data.get(k, 0) for k in outcome_keys]
        if sum(vals) == 0:
            vals = [1,0,0,0]
        colors = [pie_colors[k] for k in outcome_keys]
        wedges, texts, autotexts = ax.pie(
            vals,
            labels=None,
            autopct=lambda p: f"{p:.0f}%" if p > 0 else "",
            colors=colors,
            startangle=90,
            pctdistance=1.12,
            textprops={"fontsize": 10},
        )
        for at in autotexts:
            at.set_fontsize(12)
            at.set_fontweight("bold")
            at.set_color("#222222")
        # no per-pie title (removed to reduce clutter)
        centre_circle = plt.Circle((0,0), 0.55, fc='white')
        ax.add_artist(centre_circle)
        ax.set_aspect("equal")

    import matplotlib.patches as mpatches
    handles = [mpatches.Patch(color=pie_colors[k], label=k.replace("-", " ")) for k in outcome_keys]
    legend = fig.legend(
        handles,
        [h.get_label() for h in handles],
        loc="lower center",
        ncol=len(outcome_keys),
        bbox_to_anchor=(0.5, 0.02),
        frameon=False,
        title="Multi Agent failures",
        title_fontsize=13,
    )
    try:
        legend.get_title().set_fontweight("bold")
    except Exception:
        pass

    plt.tight_layout(rect=[0, 0.04, 1, 0.96])
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(out_path, dpi=300, bbox_inches="tight", facecolor="white")
        plt.close(fig)
        print(f"[ok] chart saved to {out_path}")
    except Exception as e:
        print(f"[error] failed to save chart: {e}")

def main(argv):
    import argparse
    ap = argparse.ArgumentParser(description="Plot results summary chart from CSV")
    maestro_nano_root = get_maestro_nano_root()
    default_csv = maestro_nano_root / "baseline" / "datasets" / "aoc" / "results_summary_live.csv"
    ap.add_argument("csv", nargs="?", default=str(default_csv), help="Path to results CSV")
    ap.add_argument("-o", "--out", help="Output PNG path (optional)")
    ap.add_argument("--by-day", action="store_true", help="Plot with x-axis = Day number instead of Year")
    ap.add_argument("--by-agg-tag", action="store_true", help="Plot with x-axis = Aggregation Tag")
    args = ap.parse_args(argv)

    csv_path = Path(args.csv)
    if args.out:
        out_path = Path(args.out)
    elif args.by_agg_tag:
        out_path = csv_path.parent / "model_comparison_chart_agg_tag.png"
    elif args.by_day:
        out_path = csv_path.parent / "model_comparison_chart_day.png"
    else:
        out_path = csv_path.parent / "model_comparison_chart_year.png"
    plot_from_csv(csv_path, out_path, by_day=args.by_day, by_agg_tag=args.by_agg_tag)

if __name__ == "__main__":
    main(sys.argv[1:])