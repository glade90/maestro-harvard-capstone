#!/usr/bin/env python3
"""
Merge multiple results CSV files into one and re-index the 'index' column.

Usage:
  python merge_results.py file1.csv file2.csv ... [-o OUTPATH]
  python merge_results.py --dir "C:\path\to\dir" [-o OUTPATH]

Default output:
    <repo>/maestro-nano/baseline/datasets/aoc/results_summary_merged_<timestamp>.csv
"""
import argparse
import csv
from pathlib import Path
from collections import OrderedDict
from datetime import datetime

# default: use the directory containing the referenced collect_aoc_results.py if it exists,
# otherwise fall back to the script's parent directory.
REPO_ROOT = Path(__file__).resolve().parent.parent
MAESTRO_NANO_ROOT = REPO_ROOT / "maestro-nano"

_DEFAULT_COLLECT_FILE = REPO_ROOT / "scripts" / "collect_aoc_results.py"
DEFAULT_DIR = _DEFAULT_COLLECT_FILE.parent if _DEFAULT_COLLECT_FILE.exists() else Path(__file__).resolve().parent

def _default_outpath():
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return (MAESTRO_NANO_ROOT / "baseline" / "datasets" / "aoc") / f"results_summary_merged_{ts}.csv"

DEFAULT_OUT = _default_outpath()


def gather_files(args):
    files = []
    # choose directory: provided or default
    dir_to_use = Path(args.dir) if args.dir else DEFAULT_DIR
    if dir_to_use:
        p = dir_to_use
        if not p.exists() or not p.is_dir():
            raise SystemExit(f"[error] --dir {p} not found or not a directory")
        for f in sorted(p.glob("results_summary*.csv")):
            files.append(f)
    files.extend([Path(f) for f in args.inputs or []])
    # remove duplicates while preserving order
    seen = set()
    out = []
    for f in files:
        try:
            resolved = f.resolve()
        except Exception:
            resolved = f
        if resolved in seen:
            continue
        seen.add(resolved)
        out.append(f)
    return out


def read_rows(files):
    all_rows = []
    field_order = []  # maintain first-seen order
    seen_fields = set()
    totals = {}
    for f in files:
        if not f.exists():
            print(f"[warn] input file not found: {f}")
            continue
        with f.open("r", encoding="utf-8", newline="") as fh:
            rdr = csv.DictReader(fh)
            # record header fields
            for fn in rdr.fieldnames or []:
                if fn not in seen_fields:
                    field_order.append(fn)
                    seen_fields.add(fn)
            count = 0
            for r in rdr:
                # ensure keys for all observed fields (will be filled when writing)
                all_rows.append(dict(r))
                count += 1
            totals[str(f)] = count
    return all_rows, field_order, totals


def write_merged(rows, field_order, outpath):
    # Ensure 'index' is first column
    if "index" in field_order:
        field_order = [f for f in field_order if f != "index"]
    fieldnames = ["index"] + field_order
    outdir = outpath.parent
    outdir.mkdir(parents=True, exist_ok=True)
    with outpath.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for i, row in enumerate(rows, start=1):
            out_row = {k: "" for k in fieldnames}
            out_row.update(row or {})
            out_row["index"] = str(i)
            w.writerow(out_row)
    return len(rows)


def main():
    ap = argparse.ArgumentParser(description="Merge results CSV files and re-index them.")
    ap.add_argument("inputs", nargs="*", help="Input CSV files (can specify many).")
    ap.add_argument("--dir", "-d", help=f"Directory to glob results_summary*.csv from (default: {DEFAULT_DIR})")
    ap.add_argument("--out", "-o", help=f"Output CSV path (default: {DEFAULT_OUT})")
    args = ap.parse_args()

    files = gather_files(args)
    if not files:
        raise SystemExit("[error] no input files found/specified")

    print(f"[info] merging {len(files)} files:")
    for f in files:
        print(f"  - {f}")

    rows, field_order, totals = read_rows(files)
    for k, v in totals.items():
        print(f"[info] read {v} rows from {k}")

    outpath = Path(args.out) if args.out else DEFAULT_OUT
    written = write_merged(rows, field_order, outpath)
    print(f"[ok] wrote {written} rows to {outpath.resolve()}")

if __name__ == "__main__":
    main()