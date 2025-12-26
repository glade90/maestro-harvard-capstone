#!/usr/bin/env python3
"""
Sweep all run folders from results/single and results/multi into results/archive/<timestamp>/

Usage:
  python archive_results.py         # interactive confirm
  python archive_results.py --yes   # proceed without prompt
  python archive_results.py --dry-run  # show what would be moved
"""
from pathlib import Path
from datetime import datetime
import shutil
import argparse
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
RESULTS_ROOT = SCRIPT_DIR.parent / "results"
SINGLE_DIR = RESULTS_ROOT / "single"
MULTI_DIR = RESULTS_ROOT / "multi"
SINGLE_ARCHIVE_ROOT = SINGLE_DIR / "archive"
MULTI_ARCHIVE_ROOT = MULTI_DIR / "archive"

# datasets aoc location and archive for results_summary files
AOC_DIR = SCRIPT_DIR.parent / "datasets" / "aoc"
ARCHIVE_SUMMARY_DIR = AOC_DIR / "archive_results_summary"

def unique_dest(dest: Path) -> Path:
    if not dest.exists():
        return dest
    base = dest
    i = 1
    while True:
        cand = base.with_name(f"{base.name}_{i}")
        if not cand.exists():
            return cand
        i += 1

def collect_runs(slot_dir: Path):
    if not slot_dir.exists():
        return []
    return sorted([d for d in slot_dir.iterdir() if d.is_dir() and d.name != "archive"])

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--dry-run", action="store_true", help="Show actions without moving files")
    p.add_argument("--yes", action="store_true", help="Don't prompt, proceed")
    args = p.parse_args()

    runs_single = collect_runs(SINGLE_DIR)
    runs_multi = collect_runs(MULTI_DIR)
    total = len(runs_single) + len(runs_multi)
    if total == 0:
        print("No run folders found in single/ or multi/. Nothing to archive.")
        return

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    dst_root_single = SINGLE_ARCHIVE_ROOT / stamp
    dst_root_multi = MULTI_ARCHIVE_ROOT / stamp
    print(f"Archive single root: {dst_root_single}")
    print(f"Archive multi root: {dst_root_multi}")
    print(f"Found {len(runs_single)} single runs and {len(runs_multi)} multi runs (total {total}).")

    if not args.yes and not args.dry_run:
        resp = input("Proceed moving these folders into the archive? [y/N]: ").strip().lower()
        if resp != "y":
            print("Aborted.")
            return

    for slot_name, slot_runs in (("single", runs_single), ("multi", runs_multi)):
        for run_dir in slot_runs:
            base_dst = dst_root_single if slot_name == "single" else dst_root_multi
            rel_dest = base_dst / run_dir.name
            final_dest = unique_dest(rel_dest)
            if args.dry_run:
                print(f"[DRY] Move: {run_dir} -> {final_dest}")
                continue
            final_dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(run_dir), str(final_dest))
                print(f"[ok] Moved: {run_dir} -> {final_dest}")
            except Exception as e:
                print(f"[fail] Could not move {run_dir}: {e}", file=sys.stderr)

    # --- archive timestamped artifacts under datasets/aoc (exclude *_live* files) ---
    # search for timestamped results files: results_summary_*, results_analysis_*, model_comparison_chart_*, results_bundle_*
    artifact_files = []
    if AOC_DIR.exists():
        for pattern in ["results_summary_*", "results_analysis_*", "model_comparison_chart_*", "results_bundle_*"]:
            artifact_files.extend([p for p in AOC_DIR.glob(pattern) if p.is_file() and "_live" not in p.name])

    if artifact_files:
        print(f"\nFound {len(artifact_files)} timestamped artifact files under: {AOC_DIR}")
        for f in artifact_files:
            dest = ARCHIVE_SUMMARY_DIR / f.name
            final_dest = unique_dest(dest)
            if args.dry_run:
                print(f"[DRY] Move artifact: {f} -> {final_dest}")
                continue
            final_dest.parent.mkdir(parents=True, exist_ok=True)
            try:
                shutil.move(str(f), str(final_dest))
                print(f"[ok] Moved artifact: {f} -> {final_dest}")
            except Exception as e:
                print(f"[fail] Could not move artifact {f}: {e}", file=sys.stderr)
    else:
        print("\nNo timestamped artifact files found under datasets/aoc (excluding *_live* files)")

    if not args.dry_run:
        print(f"\nArchive complete. Archived runs placed under: {dst_root_single} and {dst_root_multi}")

if __name__ == "__main__":
    main()