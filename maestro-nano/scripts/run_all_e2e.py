#!/usr/bin/env python3
"""
Run run_e2e.py for multiple models and modes, collecting logs.

Usage:
  python run_all_e2e.py            # runs default models and modes and then runs collect_aoc_results.py
  python run_all_e2e.py --trial    # propagate trial-run to each invocation
  python run_all_e2e.py --models gpt-4o-mini gpt-5-nano --modes single
  python run_all_e2e.py --no-collect  # skip running collect_aoc_results.py at the end
"""
from pathlib import Path
import subprocess
import sys
import os
import argparse
from datetime import datetime
import traceback
from subprocess import PIPE, STDOUT, Popen

from paths import get_maestro_nano_root

#DEFAULT_MODELS = ["gpt-3.5-turbo", "gpt-4o-mini"], "gpt-5-nano"]
DEFAULT_MODELS = [ "gpt-4.1-mini"]

DEFAULT_MODES = ["single", "multi"]
#DEFAULT_YEARS = ["2020", "2021", "2022", "2023", "2024"]
DEFAULT_YEARS = ["2021"]

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--models", nargs="*", default=DEFAULT_MODELS, help="Models to run")
    p.add_argument("--modes", nargs="*", default=DEFAULT_MODES, help="Modes to run (single/multi)")
    p.add_argument("--trial-run", action="store_true", help="Pass --trial-run to run_e2e.py")
    p.add_argument("--no-collect", action="store_true", help="Do not run collect_aoc_results.py after runs (default: run it)")
    p.add_argument("--timeout", type=int, default=None, help="Per-invocation timeout in seconds (default: no timeout)")
    p.add_argument("--stream-output", action="store_true", help="Stream child stdout/stderr to console while still saving logs")
    p.add_argument("--clear-summary", action="store_true", help="Pass --clear-results to collect_aoc_results.py")
    p.add_argument("--years", nargs="*", default=DEFAULT_YEARS, help="Limit runs to these years (e.g. 2020 2021). Default: %(default)s")
    p.add_argument("--days", nargs="*", default=None, help="Limit to these days (e.g. day01 day02 or 1 2). Default: all days 1-25")
    p.add_argument("--no-tdd", action="store_true", help="Disable TDD agent in multi-agent mode (passed to run_e2e.py)")
    p.add_argument("--temperature", "-t", type=float, default=1.0, help="Temperature for LLM sampling (0.0-2.0, default: 1.0)")
    p.add_argument("--no-push", action="store_true", help="Do not run git pull/add/commit/push at the end")
    p.add_argument("--tag", type=str, default=None, help="Optional tag to include in timestamped results summary filename and commit message")
    p.add_argument("--agg-tag", type=str, default="", help="Aggregation tag to add as last column in results_summary_live.csv (cannot be used with --clear-summary)")
    p.add_argument("--prompt-set", type=str, default="DEFAULT", help="Prompt set to use (default: DEFAULT)")
    p.add_argument("--no-archive", action="store_true", help="Do not run archive script after each run (pass to run_e2e.py)")
    p.add_argument("--no-plot", action="store_true", help="Do not generate plots in collect_aoc_results.py")
    args = p.parse_args()
    
    # Validate that agg-tag and clear-summary are not both supplied
    if args.agg_tag and args.clear_summary:
        print("[error] Cannot use --agg-tag with --clear-summary")
        sys.exit(1)

    script_dir = Path(__file__).resolve().parents[0]
    print(f"[info] script directory: {script_dir}")
    maestro_nano_root = get_maestro_nano_root()
    print(f"[info] maestro-nano directory: {maestro_nano_root}")
    results_dir = maestro_nano_root / "baseline" / "results"
    print(f"[info] results directory: {results_dir}")
    run_e2e = script_dir / "run_e2e.py"
    if not run_e2e.exists():
        print(f"run_e2e.py not found at {run_e2e}")
        sys.exit(2)

    summary_root = results_dir / "run_all_logs" / datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_root.mkdir(parents=True, exist_ok=True)

    for model in args.models:
        for mode in args.modes:
            name = f"{model}__{mode}"
            print(f"[run] {name}")
            cmd = [sys.executable, str(run_e2e), "--model", model, "--mode", mode]
            if args.years:
                cmd.extend(["--years"] + list(args.years))
            if args.days:
                cmd.extend(["--days"] + list(args.days))
            if args.trial_run:
                cmd.append("--trial-run")
            if args.no_tdd:
                cmd.append("--no-tdd")
            if args.temperature != 1.0:
                cmd.extend(["--temperature", str(args.temperature)])
            if args.prompt_set != "DEFAULT":
                cmd.extend(["--prompt-set", args.prompt_set])
            if args.no_archive:
                cmd.append("--no-archive")
            # run and capture output
            run_kwargs = {"capture_output": True, "text": True}
            if args.timeout is not None:
                run_kwargs["timeout"] = args.timeout
            
            try:
                proc = _run_and_capture(cmd, run_kwargs, stream=args.stream_output)
            except Exception as e:
                log_path = summary_root / f"{name}.log"
                with log_path.open("w", encoding="utf-8") as fh:
                    fh.write(f"$ {' '.join(cmd)}\n\n")
                    fh.write(f"Exception during invocation: {repr(e)}\n\n")
                    fh.write(traceback.format_exc())
                print(f"[error] {name} invocation failed: {e}")
                continue

            log_path = summary_root / f"{name}.log"
            with log_path.open("w", encoding="utf-8") as fh:
                fh.write(f"$ {' '.join(cmd)}\n\n")
                fh.write(f"returncode: {proc.returncode}\n\n")
                fh.write("=== STDOUT ===\n")
                fh.write(proc.stdout or "")
                fh.write("\n\n=== STDERR ===\n")
                fh.write(proc.stderr or "")
            if proc.returncode == 0:
                print(f"[ok] {name} completed, log: {log_path}")
            else:
                print(f"[fail] {name} returned {proc.returncode}, log: {log_path}")

    print(f"[done] logs saved to: {summary_root}")

    # optionally run collect_aoc_results.py (default: run it unless --no-collect)
    if not args.no_collect:
        collect_script = script_dir / "collect_aoc_results.py"
        if not collect_script.exists():
            print(f"[warn] collect_aoc_results.py not found at {collect_script}; skipping collection")
            return

        collect_name = "collect_aoc_results"
        collect_cmd = [sys.executable, str(collect_script)]
        if args.clear_summary:
            collect_cmd.append("--clear-results")
        if args.trial_run:
            collect_cmd.append("--trial-run")
        # forward selection filters used for the run to the collector
        if args.years:
            collect_cmd.extend(["--years"] + list(args.years))
        if args.days:
            collect_cmd.extend(["--days"] + list(args.days))
        if args.models:
            collect_cmd.extend(["--models"] + list(args.models))
        # forward optional tag to collector so it embeds into timestamped summary filename
        if args.tag:
            collect_cmd.extend(["--tag", args.tag])
        # forward agg-tag to collector for CSV column
        if args.agg_tag:
            collect_cmd.extend(["--agg-tag", args.agg_tag])
        # forward no-archive flag to collector
        if args.no_archive:
            collect_cmd.append("--no-archive")
        # forward no-plot flag to collector
        if args.no_plot:
            collect_cmd.append("--no-plot")
        print(f"[run] running {collect_name}")
        collect_kwargs = {"capture_output": True, "text": True}
        if args.timeout is not None:
            collect_kwargs["timeout"] = args.timeout
        print(f"[info] collect command: {' '.join(collect_cmd)}")
        try:
            proc = subprocess.run(collect_cmd, **collect_kwargs)
            collect_log = summary_root / f"{collect_name}.log"
            with collect_log.open("w", encoding="utf-8") as fh:
                fh.write(f"$ {' '.join(collect_cmd)}\n\n")
                fh.write(f"returncode: {proc.returncode}\n\n")
                fh.write("=== STDOUT ===\n")
                fh.write(proc.stdout or "")
                fh.write("\n\n=== STDERR ===\n")
                fh.write(proc.stderr or "")
            if proc.returncode == 0:
                print(f"[ok] collection completed, log: {collect_log}")
            else:
                print(f"[fail] collection returned {proc.returncode}, log: {collect_log}")
        except Exception as e:
            collect_log = summary_root / f"{collect_name}.log"
            with collect_log.open("w", encoding="utf-8") as fh:
                fh.write(f"$ {' '.join(collect_cmd)}\n\n")
                fh.write(f"Exception during collect invocation: {repr(e)}\n\n")
                fh.write(traceback.format_exc())
            print(f"[error] running collection failed: {e}")
    else:
        print("[info] skipping collection step (--no-collect)")

    # --- optional Git push the repo with a summary commit ---
    if args.no_push:
        print("[info] --no-push set; skipping git pull/add/commit/push sequence")
    else:
        try:
            repo_dir = script_dir.parent.parent if (script_dir.parent.parent.exists()) else script_dir.parent
            commit_msg = (
                f"push after run: models={','.join(args.models)} modes={','.join(args.modes)} "
                f"years={','.join(args.years) if args.years else 'all'} "
                f"days={','.join(args.days) if args.days else 'all'} "
                f"trial_run={args.trial_run} tag={args.tag or 'none'} timestamp={datetime.now().isoformat()}"
            )
            print(f"[info] Git push: repo_dir={repo_dir}")
            def _run_git(cmd):
                r = subprocess.run(cmd, cwd=repo_dir, capture_output=True, text=True)
                out = (r.stdout or "").strip()
                err = (r.stderr or "").strip()
                print(f"[git] {' '.join(cmd)} -> rc={r.returncode}")
                if out:
                    print("[git stdout]", out)
                if err:
                    print("[git stderr]", err)
                return r

            # 1) git pull
            _run_git(["git", "pull"])

            # 2) git add -A
            _run_git(["git", "add", "-A"])

            # 3) git commit -m "..."
            commit_proc = _run_git(["git", "commit", "-m", commit_msg])
            if commit_proc.returncode != 0:
                # common benign message: nothing to commit
                stderr = (commit_proc.stderr or "").lower()
                if "nothing to commit" in stderr or "no changes added to commit" in stderr:
                    print("[git] nothing to commit; skipping push")
                else:
                    print("[warn] git commit failed (see messages above)")

            # 4) git push
            _run_git(["git", "push"])
            print("[ok] git push sequence completed")
        except Exception as e:
            print(f"[error] git push sequence failed: {e}")

    # --- run analyze_results.py on the live CSV ---
    if not args.no_collect:
        analyze_script = script_dir.parent / "scripts" / "analyze_results.py"
        results_csv = maestro_nano_dir / "baseline" / "datasets" / "aoc" / "results_summary_live.csv"
        
        if analyze_script.exists() and results_csv.exists():
            analyze_name = "analyze_results"
            analyze_cmd = [sys.executable, str(analyze_script), str(results_csv)]
            print(f"[run] running {analyze_name}")
            
            try:
                proc = subprocess.run(analyze_cmd, capture_output=True, text=True)
                analyze_log = summary_root / f"{analyze_name}.log"
                with analyze_log.open("w", encoding="utf-8") as fh:
                    fh.write(f"$ {' '.join(analyze_cmd)}\n\n")
                    fh.write(f"returncode: {proc.returncode}\n\n")
                    fh.write("=== STDOUT ===\n")
                    fh.write(proc.stdout or "")
                    fh.write("\n\n=== STDERR ===\n")
                    fh.write(proc.stderr or "")
                if proc.returncode == 0:
                    print(f"[ok] analysis completed, log: {analyze_log}")
                else:
                    print(f"[fail] analysis returned {proc.returncode}, log: {analyze_log}")
            except Exception as e:
                analyze_log = summary_root / f"{analyze_name}.log"
                with analyze_log.open("w", encoding="utf-8") as fh:
                    fh.write(f"$ {' '.join(analyze_cmd)}\n\n")
                    fh.write(f"Exception during analysis: {repr(e)}\n\n")
                    fh.write(traceback.format_exc())
                print(f"[error] running analysis failed: {e}")
        else:
            if not analyze_script.exists():
                print(f"[warn] analyze_results.py not found at {analyze_script}; skipping analysis")
            if not results_csv.exists():
                print(f"[warn] results_summary_live.csv not found at {results_csv}; skipping analysis")
    else:
        print("[info] skipping analysis step (--no-collect)")

def _run_and_capture(cmd, run_kwargs, stream=True):
    if not stream:
        return subprocess.run(cmd, **run_kwargs)
    
    # When streaming is requested we must NOT pipe the child's stdout/stderr:
    # if stdout is piped, tqdm inside the child detects a non-tty and prints
    # line-by-line progress rather than an updating progress bar. To allow
    # in-place progress bars, let the child inherit the parent's terminal.
    #
    # Note: this means we won't capture stdout/stderr text for logs. We still
    # return a CompletedProcess-like object with the child's returncode.
    env = None
    try:
        env = os.environ.copy()
        env["PYTHONUNBUFFERED"] = "1"  # make child's python output unbuffered
    except Exception:
        env = None

    proc = Popen(cmd, stdout=None, stderr=None, env=env)
    try:
        proc.wait(timeout=run_kwargs.get("timeout", None))
    except KeyboardInterrupt:
        proc.kill()
        raise
    except Exception:
        proc.kill()
        raise

    # Return a CompletedProcess-like object; stdout/stderr not captured when streaming
    return subprocess.CompletedProcess(cmd, proc.returncode, stdout=None, stderr=None)

if __name__ == "__main__":
    main()