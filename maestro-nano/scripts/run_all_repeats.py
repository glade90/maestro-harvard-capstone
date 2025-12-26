#!/usr/bin/env python3
"""
Run run_all_e2e.py multiple times (first run with --clear-summary).
Saves per-run logs under results/run_all_repeats/<timestamp>/run_XXX.log

Usage:
  python run_all_repeats.py --count 5 --year 2021 --day 16
  python run_all_repeats.py --count 3 --stream --year 2021 --day day16
"""
from pathlib import Path
import subprocess
import sys
import argparse
from datetime import datetime
from tqdm import tqdm

def _normalize_day_token(tok: str) -> str:
    t = str(tok).strip()
    if t.isdigit():
        n = int(t)
        if 1 <= n <= 25:
            return f"day{n:02d}"
    # allow dayNN style or pass-through
    return t.lower()

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--count", "-n", type=int, default=1, help="Number of times to invoke run_all_e2e.py")
    p.add_argument("--stream", action="store_true", help="Let child inherit stdout/stderr (no log capture)")
    p.add_argument("--timeout", type=int, default=None, help="Per-invocation timeout seconds (passed to subprocess.run)")
    p.add_argument("--extra-args", nargs="*", default=[], help="Extra arguments to forward to run_all_e2e.py")
    p.add_argument("--models", nargs="*", default=None, help="Limit to these models; forwarded to run_all_e2e.py and collector")
    p.add_argument("--year", type=str, default=None, help="Limit runs to this year (e.g. 2021)")
    p.add_argument("--day", type=str, default=None, help="Limit runs to this day (e.g. 16 or day16)")
    p.add_argument("--temperature", "-t", type=float, default=None, help="Temperature for LLM sampling (0.0-2.0, forwarded to run_all_e2e.py)")
    p.add_argument("--prompt-set", type=str, default=None, help="Prompt set to use (e.g. DEFAULT, POST_2021_CHECK, forwarded to run_all_e2e.py)")
    args = p.parse_args()

    script_dir = Path(__file__).resolve().parents[0]
    runner = script_dir / "run_all_e2e.py"
    if not runner.exists():
        print(f"run_all_e2e.py not found at {runner}", file=sys.stderr)
        sys.exit(2)

    out_root = script_dir.parent / "results" / "run_all_repeats" / datetime.now().strftime("%Y%m%d_%H%M%S")
    out_root.mkdir(parents=True, exist_ok=True)

    runs = args.count
    failures = 0

    it = tqdm(range(1, runs + 1), desc="Runs", unit="run", dynamic_ncols=True)
    for i in it:
        cmd = [sys.executable, str(runner)]
        # first run add --clear-summary
        if i == 1:
            cmd.append("--clear-summary")

        # tell run_all_e2e not to run its internal collection/summary (we collect externally)
        cmd.append("--no-collect")
        
        # tell run_all_e2e not to push to git during repeat experiments
        cmd.append("--no-push")
        
        # forward year/day if provided (normalize day)
        if args.year:
            cmd.extend(["--years", str(args.year)])
        if args.day:
            cmd.extend(["--days", _normalize_day_token(args.day)])
        # forward model filter if provided
        if args.models:
            cmd.extend(["--models"] + list(args.models))
        
        # forward temperature if provided
        if args.temperature is not None:
            cmd.extend(["--temperature", str(args.temperature)])
        
        # forward prompt-set if provided
        if args.prompt_set is not None:
            cmd.extend(["--prompt-set", args.prompt_set])

        # forward any extra args
        if args.extra_args:
            cmd.extend(args.extra_args)
        # forward streaming preference to child so it can avoid piping when streaming
        if args.stream:
            cmd.append("--stream")

        it.set_postfix({"run": f"{i}/{runs}"})
        log_path = out_root / f"run_{i:03d}.log"

        if args.stream:
            # let child print to console; no capture to file
            try:
                rc = subprocess.run(cmd, timeout=args.timeout)
                with log_path.open("w", encoding="utf-8") as fh:
                    fh.write(f"$ {' '.join(cmd)}\n\nreturncode: {rc.returncode}\n")
                if rc.returncode != 0:
                    failures += 1
                it.set_description(f"Run {i} rc={rc.returncode}")
            except Exception as e:
                failures += 1
                with log_path.open("w", encoding="utf-8") as fh:
                    fh.write(f"$ {' '.join(cmd)}\n\nException: {e}\n")
                it.set_description(f"Run {i} EXC")
        else:
            # capture stdout/stderr and save to log file
            try:
                proc = subprocess.run(cmd, capture_output=True, text=True, timeout=args.timeout)
                with log_path.open("w", encoding="utf-8") as fh:
                    fh.write(f"$ {' '.join(cmd)}\n\n")
                    fh.write(f"returncode: {proc.returncode}\n\n")
                    fh.write("=== STDOUT ===\n")
                    fh.write(proc.stdout or "")
                    fh.write("\n\n=== STDERR ===\n")
                    fh.write(proc.stderr or "")
                if proc.returncode != 0:
                    failures += 1
                it.set_description(f"Run {i} rc={proc.returncode}")
            except Exception as e:
                failures += 1
                with log_path.open("w", encoding="utf-8") as fh:
                    fh.write(f"$ {' '.join(cmd)}\n\nException: {e}\n")
                it.set_description(f"Run {i} EXC")

        # Run collector after each run, but only clear results on the very first iteration.
        collect_script = script_dir / "collect_aoc_results.py"
        if collect_script.exists():
            collect_cmd = [sys.executable, str(collect_script)]
            if i == 1:
                collect_cmd.append("--clear-results")
            # forward year/day/models filters if provided
            if args.year:
                collect_cmd.extend(["--years", str(args.year)])
            if args.day:
                collect_cmd.extend(["--days", _normalize_day_token(args.day)])
            if args.models:
                collect_cmd.extend(["--models"] + list(args.models))
            # don't archive during repeat experiments
            collect_cmd.append("--no-archive")

            collect_log = out_root / f"collect_after_run_{i:03d}.log"
            try:
                # capture collector output to per-run log
                cproc = subprocess.run(collect_cmd, capture_output=True, text=True, timeout=args.timeout)
                with collect_log.open("w", encoding="utf-8") as fh:
                    fh.write(f"$ {' '.join(collect_cmd)}\n\n")
                    fh.write(f"returncode: {cproc.returncode}\n\n")
                    fh.write("=== STDOUT ===\n")
                    fh.write(cproc.stdout or "")
                    fh.write("\n\n=== STDERR ===\n")
                    fh.write(cproc.stderr or "")
                if cproc.returncode == 0:
                    it.write(f"[ok] collect completed after run {i}, log: {collect_log}")
                else:
                    it.write(f"[fail] collect returned {cproc.returncode} after run {i}, log: {collect_log}")
            except Exception as e:
                with collect_log.open("w", encoding="utf-8") as fh:
                    fh.write(f"$ {' '.join(collect_cmd)}\n\nException: {e}\n")
                it.write(f"[error] running collector after run {i}: {e}")
        else:
            it.write(f"[warn] collect_aoc_results.py not found at {collect_script}; skipping collector")

    print(f"\nCompleted {runs} runs. Failures: {failures}. Logs: {out_root}")

    # results run directories root (single/multi)
    results_root = script_dir.parent / "baseline" / "results"
    single_root = results_root / "single"
    multi_root = results_root / "multi"

    # snapshot of existing run dirs before we started (look for dirs created by other runs)
    def _list_run_dirs(root: Path):
        if not root.exists():
            return set()
        return {d.name for d in root.iterdir() if d.is_dir()}

    # compute new run dirs created by this batch
    before_single = _list_run_dirs(single_root)
    before_multi = _list_run_dirs(multi_root)

    # refresh after a small pause to let filesystems settle (best-effort)
    import time
    time.sleep(0.1)
    after_single = _list_run_dirs(single_root)
    after_multi = _list_run_dirs(multi_root)

    new_single = after_single - before_single
    new_multi = after_multi - before_multi
    new_dirs = list(new_single | new_multi)

    if not new_dirs:
        print("[warn] no new run folders detected under results/single or results/multi; running collect without everything-after")
        collect_cmd = [sys.executable, str(collect_script)]
    else:
        # extract timestamp prefix YYYYMMDD_HHMMSS from run dir names and pick earliest
        import re
        ts_re = re.compile(r"^(\d{8}_\d{6})")
        prefixes = []
        for name in new_dirs:
            m = ts_re.match(name)
            if m:
                prefixes.append(m.group(1))
        if not prefixes:
            print("[warn] no timestamp-like prefixes found in new run dirs; running collect without everything-after")
            collect_cmd = [sys.executable, str(collect_script)]
        else:
            earliest = sorted(prefixes)[0]
            print(f"[info] running collect in everything mode starting at: {earliest}")
            collect_cmd = [sys.executable, str(collect_script), "--everything-after", earliest]

    # forward optional year/day and model filters if provided to collector
    if args.year:
        collect_cmd.extend(["--years", str(args.year)])
    if args.day:
        collect_cmd.extend(["--days", _normalize_day_token(args.day)])
    if args.models:
        collect_cmd.extend(["--models"] + list(args.models))
    # don't archive during repeat experiments
    collect_cmd.append("--no-archive")

if __name__ == "__main__":
    main()