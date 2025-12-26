#!/usr/bin/env python3
"""
Rewritten collector for AoC agent runs.

Requirements implemented:
1. Find most recent run per model under results/single and results/multi using folder name pattern <YYYYMMDD_HHMMSS>_<model>.
2. Traverse each run's subfolders (year/day) and invoke attempt.py with the dataset input file (datasets/aoc/<YEAR>/<DAY>/input.txt).
3. Capture attempt output (extract Part 1 if present, else whole stdout trimmed) and save to <run>/<year>/<day>/result.txt.
4. Read baseline result1.txt/result2.txt from datasets root and produce CSV:
   year,model,day,result1,result2,single_part1,single_outcome,multi_part1,multi_outcome
   Outcomes: SUCCESS (matches result1), FAIL-MISSING (no result), FAIL-INCORRECT (present but mismatch).
"""
from __future__ import annotations
from pathlib import Path
import re
import csv
import subprocess
import sys
from collections import defaultdict
import os
import argparse
import shutil
from datetime import datetime
import zipfile

from paths import get_maestro_nano_root

try:
    from tqdm import tqdm
    _have_tqdm = True
except Exception:
    _have_tqdm = False

# prefer external plotting utility (scripts/plot_results.py).  Add scripts dir to sys.path and import.
plot_from_csv = None
_have_external_plot = False
analyze_results = None
_have_analyze = False
try:
    SCRIPTS_DIR = Path(__file__).resolve().parent
    if SCRIPTS_DIR.exists():
        sys.path.insert(0, str(SCRIPTS_DIR))
    from plot_results import plot_from_csv  # type: ignore
    _have_external_plot = True
    from analyze_results import analyze, nice_print  # type: ignore
    _have_analyze = True
except Exception:
    _have_external_plot = False
    plot_from_csv = None
    _have_analyze = False

# Configuration
# This script lives at <repo>/maestro-nano/scripts/collect_aoc_results.py.
# Use that to robustly locate the maestro-nano root and its results folder.
MAESTRO_NANO_ROOT = get_maestro_nano_root()
REPO_ROOT = MAESTRO_NANO_ROOT.parent
DATASETS_ROOT = MAESTRO_NANO_ROOT / "baseline" / "datasets" / "aoc"
RESULTS_ROOT = MAESTRO_NANO_ROOT  / "baseline" /  "results"
SINGLE_RESULTS_DIR = RESULTS_ROOT / "single"
MULTI_RESULTS_DIR = RESULTS_ROOT / "multi"
OUT_CSV = DATASETS_ROOT / "results_summary_live.csv"

print(f"[info] Using datasets root: {MAESTRO_NANO_ROOT}")
print(f"[info] Using datasets root: {REPO_ROOT}")
print(f"[info] Using datasets root: {DATASETS_ROOT}")
print(f"[info] Using results root: {RESULTS_ROOT}")
print(f"[info] Using output CSV: {OUT_CSV}")

# Regex to parse run directory names and to extract "Part 1" from outputs
RUN_DIR_RE = re.compile(r"^(\d{8}_\d{6})_(.+)$")
PART1_RE = re.compile(r"Part\s*1\s*[:\-]\s*(.+)", re.IGNORECASE)


def _parse_run_dirs(root_dir: Path):
    """
    Scan root_dir and return dict mapping model_name -> (best_key:int, path:Path)
    where best_key is the parsed timestamp (as int) or mtime fallback.
    """
    models = {}
    if not root_dir.exists():
        return models

    for p in root_dir.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        m = RUN_DIR_RE.match(name)
        if m:
            key = int(m.group(1).replace("_", ""))
            model = m.group(2)
        else:
            # fallback: try split on first '_' to get model part, else use full name
            parts = name.split("_", 1)
            model = parts[1] if len(parts) == 2 else name
            key = int(p.stat().st_mtime * 1_000_000)

        cur = models.get(model)
        if cur is None or key > cur[0]:
            models[model] = (key, p)
    return models


def get_latest_runs_by_model():
    """
    Return mapping model_name -> {"single": Path|None, "multi": Path|None}
    """
    single = _parse_run_dirs(SINGLE_RESULTS_DIR)
    multi = _parse_run_dirs(MULTI_RESULTS_DIR)

    all_models = set(single.keys()) | set(multi.keys())
    out = {}
    for m in sorted(all_models):
        out[m] = {
            "single": single.get(m, (None, None))[1] if single.get(m) else None,
            "multi": multi.get(m, (None, None))[1] if multi.get(m) else None,
        }
    return out


def extract_part1_or_whole(output: str) -> str:
    """
    Prefer a 'Part 1: ...' match; otherwise return a cleaned value.
    If a numeric token is present, return the last numeric token (e.g. turn
    'Sum of risk levels of all low points: 423' -> '423').
    Otherwise, fall back to the last colon-separated segment or the first non-empty line.
    """
    if not output:
        return ""
    # prefer explicit "Part 1: ..." capture if present
    m = PART1_RE.findall(output)
    text = m[-1].strip() if m else output.strip()

    # If there are integer-like tokens, return the last one (handles many AoC outputs)
    nums = re.findall(r"-?\d+", text)
    if nums:
        return nums[-1].lstrip("+")  # return as bare numeric string

    # If no numeric token, try last colon-separated segment (removes prefixes)
    if ":" in text:
        return text.split(":")[-1].strip()

    # Otherwise return first non-empty line
    for line in text.splitlines():
        line = line.strip()
        if line:
            return line

    return ""


def run_attempt_and_capture(attempt_py: Path, input_file: Path, timeout: int = 30) -> (str, int, str, str, str):
    """
    Run attempt.py passing input_file as argv[1]. Return (captured_result_string, returncode, stdout, stderr).
    The captured_result_string is the extracted Part 1 if present else trimmed stdout.
    """
    cmd = [sys.executable, str(attempt_py), str(input_file)]
    cmd_str = " ".join(cmd)
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except Exception as e:
        # on exception return error indicator and exception text as stderr
        return f"__ERROR__: {e}", 1, "", str(e), cmd_str

    stdout = proc.stdout or ""
    stderr = proc.stderr or ""
    combined_for_extract = stdout if stdout.strip() else stderr
    captured = extract_part1_or_whole(combined_for_extract)
    return captured, proc.returncode, stdout, stderr, cmd_str


def _clear_existing_results():
    """Remove existing per-run result files so runs are re-executed fresh."""
    removed = 0
    for root in (SINGLE_RESULTS_DIR, MULTI_RESULTS_DIR):
        if not root.exists():
            continue
        for p in root.rglob("result.txt"):
            try:
                p.unlink()
                removed += 1
            except Exception:
                pass
        for p in root.rglob("result.fail.txt"):
            try:
                p.unlink()
                removed += 1
            except Exception:
                pass
    print(f"[info] cleared {removed} existing result files")


def _has_complete_year(run_dir: Path, year: str) -> bool:
    """Return True if run_dir/<year> contains all day01..day25 directories."""
    ydir = run_dir / year
    if not ydir.is_dir():
        return False
    for n in range(1, 26):
        dname = f"day{n:02d}"
        if not (ydir / dname).is_dir():
            return False
    return True


def _candidate_runs_for_model(slot_root: Path, model_name: str) -> list:
    """Return sorted list of run dirs under slot_root matching model_name (newest first)."""
    runs = []
    if not slot_root.exists():
        return runs
    for p in slot_root.iterdir():
        if not p.is_dir():
            continue
        name = p.name
        if name.lower() == "archive" or name.startswith("."):
            continue
        m = RUN_DIR_RE.match(name)
        if m:
            model = m.group(2)
            if model != model_name:
                continue
            key = int(m.group(1).replace("_", ""))
        else:
            # fallback: try split on first '_' to get model part, else use full name
            parts = name.split("_", 1)
            model = parts[1] if len(parts) == 2 else name
            if model != model_name:
                continue
            key = int(p.stat().st_mtime * 1_000_000)
        runs.append((key, p))
    # newest first
    runs.sort(reverse=True, key=lambda x: x[0])
    return [r for _, r in runs]


def _consolidate_year_into_latest(slot_root: Path, model_name: str, latest_run: Path, year: str):
    """
    If latest_run is missing the year (or incomplete), find the most recent other run
    that contains a complete set of days for that year, copy that year folder into latest_run,
    then remove the copied year folder from the source run. Print actions performed.
    """
    if not latest_run:
        return
    if _has_complete_year(latest_run, year):
        return  # nothing to do

    candidates = _candidate_runs_for_model(slot_root, model_name)
    # skip the latest itself
    candidates = [c for c in candidates if c.resolve() != latest_run.resolve()]
    for cand in candidates:
        if _has_complete_year(cand, year):
            src = cand / year
            dst = latest_run / year
            try:
                # ensure parent exists
                dst_parent = dst.parent
                dst_parent.mkdir(parents=True, exist_ok=True)
                if dst.exists():
                    # if dst exists but was incomplete, remove it first to ensure clean copy
                    try:
                        shutil.rmtree(dst)
                    except Exception as e:
                        print(f"[warn] failed to remove existing destination {dst}: {e}")
                shutil.copytree(src, dst)
                print(f"[info] Consolidated: copied {src} -> {dst}")
                # remove only the copied year folder from the source run (do not remove entire run)
                try:
                    shutil.rmtree(src)
                    print(f"[info] Removed source year folder: {src}")
                except Exception as e:
                    print(f"[warn] failed to remove source year folder {src}: {e}")
                # done for this year
                return
            except Exception as e:
                print(f"[warn] failed to consolidate year {year} from {cand} into {latest_run}: {e}")
                return
    # if we reach here, no candidate found
    print(f"[info] No complete source found to consolidate year {year} for model {model_name} in {slot_root}")


def collect(clear_results: bool = False, years: list | None = None, gpt_levels: list | None = None,
            days: list | None = None, models_filter: list | None = None, everything_after: str | None = None,
            tag: str | None = None, agg_tag: str = ""):
    if clear_results:
        _clear_existing_results()

    # If everything_after is provided, discover all run dirs (single/multi) whose run-name
    # timestamp prefix (YYYYMMDD_HHMMSS) is >= the provided string and treat each run as its
    # own "model" entry so we process every matching run.
    if everything_after:
        print(f"[info] everything-after mode enabled: selecting runs >= {everything_after}")
        runs_root_single = RESULTS_ROOT / "single"
        runs_root_multi = RESULTS_ROOT / "multi"
        discovered = []
        for slot_key, root in (("single", runs_root_single), ("multi", runs_root_multi)):
            if not root.exists():
                continue
            for rd in root.iterdir():
                if not rd.is_dir():
                    continue
                name = rd.name
                # require run dir name to contain timestamp prefix of length >= 15 (YYYYMMDD_HHMMSS)
                if len(name) < 15:
                    continue
                ts = name[:15]
                try:
                    if ts >= everything_after:
                        # extract model name part (model begins after date_time + '_' -> index 16)
                        model_name = name[16:] if len(name) > 16 else name
                        discovered.append((model_name, slot_key, rd))
                except Exception:
                    continue

        if not discovered:
            print(f"[warn] no runs found after {everything_after}")
            return None, "", None

        # Build a models mapping where each run is treated as a separate model key so existing
        # processing can be reused (key includes run-dir to keep unique)
        models = {}
        for model_name, slot_key, rd in discovered:
            key = f"{model_name}__{rd.name}"
            models.setdefault(key, {})
            models[key][slot_key] = rd

        print(f"[info] discovered {len(discovered)} runs -> {len(models)} model-run entries")
    else:
        models = get_latest_runs_by_model()
        if not models:
            print("[info] No model runs found under results/single or results/multi.")
            return None, "", None

    # Consolidation pass: for each model/slot ensure latest run has full years copied in
    YEARS_TO_CONSOLIDATE = [str(y) for y in range(2015, 2025)]
    for model_name, slots in list(models.items()):
        for slot_key, slot_root in (("single", SINGLE_RESULTS_DIR), ("multi", MULTI_RESULTS_DIR)):
            latest_run = slots.get(slot_key)
            if not latest_run:
                continue
            # perform consolidation per-year
            for y in YEARS_TO_CONSOLIDATE:
                _consolidate_year_into_latest(slot_root, model_name, latest_run, y)

    # apply existing model filtering if requested
    if models_filter:
        want = [str(x).strip().lower() for x in models_filter if str(x).strip()]
        filtered = {}
        for m, slots in models.items():
            lname = m.lower()
            if any(tok in lname or tok == lname for tok in want):
                filtered[m] = slots
        if not filtered:
            print(f"[warn] No models matched --models {models_filter}; nothing to run.")
            return None, "", None
        models = filtered

    # Filter models by GPT major versions if requested (e.g. --gpt 3 3.5 4 5)
    if gpt_levels:
        print(f"[info] Applying --gpt filter: {gpt_levels}")
        pats = []
        for tok in gpt_levels:
            s = str(tok).strip()
            if not s:
                continue
            pats.append(re.compile(rf"gpt[-_]?{re.escape(s)}", re.I))

        filtered = {}
        for m, slots in models.items():
            if any(p.search(m) for p in pats):
                filtered[m] = slots

        if filtered:
            print(f"[info] Models matching --gpt {gpt_levels}: {', '.join(sorted(filtered.keys()))}")
            models = filtered
        else:
            print(f"[warn] No models matched --gpt {gpt_levels}; nothing to run.")
            return None, "", None

    if not models:
        print("[info] No model runs found under results/single or results/multi.")
        return None, "", None

    # debug: show which run dir was selected per model
    print("[debug] selected runs:")
    for m, slots in models.items():
        print(f"  MODEL: {m}")
        print(f"    single: {slots.get('single')}")
        print(f"    multi : {slots.get('multi')}")
    print("")

    # Prepare the summary CSV file location.
    # Only truncate (start fresh) when clear_results is requested; otherwise append.
    try:
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        if clear_results:
            # clear existing CSV so subsequent runs start fresh
            try:
                with OUT_CSV.open("w", newline="", encoding="utf-8"):
                    pass
            except Exception as e:
                print(f"[warn] could not truncate {OUT_CSV}: {e}")
        else:
            # leave existing CSV intact (append mode used later)
            pass
    except Exception as e:
        print(f"[warn] could not prepare {OUT_CSV}: {e}")
    
    # Prepare CSV writer in append mode so we can write rows as we go
    # index first, file paths last, include command columns (with args)
    fieldnames = [
        "index",
        "year", "model", "day",
        "problem",
        "result1", "result2",
        "single_part1", "single_outcome", "multi_part1", "multi_outcome",
        "single_cmd", "multi_cmd",
        "single_attempt_path", "single_result_path",
        "multi_attempt_path",  "multi_result_path",
        "prompt_path",
        "multi_prompt_path",
        "single_prompt_path",
        "multi_error_path",
        "readme_path",          # path to README.md for the problem
        "agg_tag",              # aggregation tag (last column)
    ]
    need_header = not OUT_CSV.exists() or OUT_CSV.stat().st_size == 0
    # compute starting index = current number of data rows in CSV (exclude header) + 1
    start_idx = 1
    if OUT_CSV.exists():
        try:
            with OUT_CSV.open("r", encoding="utf-8", newline="") as _fh:
                rdr = csv.DictReader(_fh)
                row_count = sum(1 for _ in rdr)
                start_idx = row_count + 1
        except Exception:
            # fall back to 1 if anything goes wrong
            start_idx = 1
    csv_fh = OUT_CSV.open("a", newline="", encoding="utf-8")
    writer = csv.DictWriter(csv_fh, fieldnames=fieldnames)
    if need_header:
        writer.writeheader()
        csv_fh.flush()
        os.fsync(csv_fh.fileno())

    # build list of years to process (use provided list if passed, otherwise discover)
    if years:
        # normalize and validate requested years
        requested = [str(y) for y in years]
        years_list = []
        missing = []
        for y in requested:
            p = DATASETS_ROOT / y
            if p.is_dir():
                years_list.append(y)
            else:
                missing.append(y)
        if missing:
            print(f"[warn] requested years not found under datasets root: {', '.join(missing)}")
        if not years_list:
            print("[info] no valid years found to process; exiting")
            return
    else:
        years_list = sorted([d.name for d in DATASETS_ROOT.iterdir() if d.is_dir()])
    # build list of days (normalize user --days tokens if provided)
    if days:
        import re as _re
        days_list = []
        for tok in days:
            s = str(tok).strip()
            if _re.match(r"^day\d{1,2}$", s, _re.I):
                days_list.append(s.lower())
            elif s.isdigit():
                n = int(s)
                if 1 <= n <= 25:
                    days_list.append(f"day{n:02d}")
            else:
                print(f"[warn] ignoring invalid --days token: {tok}")
        # dedupe while preserving order
        seen = set()
        days = [d for d in days_list if not (d in seen or seen.add(d))]
        if not days:
            print("[warn] no valid days provided via --days; defaulting to all days")
            days = [f"day{n:02d}" for n in range(1, 26)]
    else:
        days = [f"day{n:02d}" for n in range(1, 26)]
 
    idx = start_idx
    for model_name, slots in models.items():
        print(f"[info] Processing model: {model_name}")
        single_run = slots.get("single")
        multi_run = slots.get("multi")

        for year in years_list:
            print(f"[info]  Year: {year}")
            # use tqdm for per-day progress when available
            days_iter = tqdm(days, desc=f"Year {year}", unit="day") if _have_tqdm else days
            for day in days_iter:
                dataset_day_dir = DATASETS_ROOT / year / day
                input_file = dataset_day_dir / "input.txt"
                baseline_r1 = dataset_day_dir / "results1.txt"
                baseline_r2 = dataset_day_dir / "results2.txt"
                readme_path = dataset_day_dir / "README.md"

                # read problem description: take first non-empty line of README (trim to 500 chars)
                problem = ""
                readme_path_str = ""
                if readme_path.exists():
                    readme_path_str = str(readme_path)
                    try:
                        txt = readme_path.read_text(encoding="utf-8", errors="ignore")
                        for line in txt.splitlines():
                            line = line.strip()
                            if line:
                                problem = line[:500]
                                break
                    except Exception:
                        problem = ""
 
                # read baselines if present
                result1 = baseline_r1.read_text(encoding="utf-8").strip() if baseline_r1.exists() else ""
                result2 = baseline_r2.read_text(encoding="utf-8").strip() if baseline_r2.exists() else ""

                # prepare CSV row (file paths last). index will be written and incremented.
                single_attempt_path = str((single_run / year / day / "attempt.py")) if single_run else ""
                multi_attempt_path = str((multi_run / year / day / "attempt.py")) if multi_run else ""
                single_result_path = str((single_run / year / day / "result.txt")) if single_run else ""
                multi_result_path = str((multi_run / year / day / "result.txt")) if multi_run else ""
                single_prompt_path = str((single_run / year / day / "prompt.txt")) if single_run else ""
                multi_prompt_path = str((multi_run / year / day / "prompt.txt")) if multi_run else ""
                
                multi_error_path = str((multi_run / year / day / "result.fail.txt")) if multi_run else ""

                row = {
                    "index": idx,
                    "year": year,
                    "model": model_name,
                    "day": day,
                    "problem": problem,
                    "result1": result1,
                    "result2": result2,
                    "single_part1": "",
                    "single_outcome": "",
                    "multi_part1": "",
                    "multi_outcome": "",
                    "single_cmd": "",
                    "multi_cmd": "",
                    "single_attempt_path": single_attempt_path,
                    "single_result_path": single_result_path,
                    "multi_attempt_path": multi_attempt_path,
                    "multi_result_path": multi_result_path,
                    "prompt_path": multi_prompt_path,
                    "single_prompt_path": single_prompt_path,
                    "multi_prompt_path": multi_prompt_path,
                    "multi_error_path": multi_error_path,
                    "readme_path": readme_path_str,
                    "agg_tag": agg_tag,
                }

                # Only attempt runs if dataset input exists
                if not input_file.exists():
                    # nothing to do for this day
                    writer.writerow(row)
                    continue

                # Helper to run a slot (single/multi)
                def _process_slot(slot_run_dir: Path, slot_key: str):
                    """
                    Returns (captured_value, outcome, cmd_str)
                    """
                    cmd_expected = ""
                    if not slot_run_dir:
                        return "", "FAIL-MISSING", cmd_expected
                    attempt_py = slot_run_dir / year / day / "attempt.py"
                    result_txt_path = slot_run_dir / year / day / "result.txt"
                    failure_txt_path = slot_run_dir / year / day / "result.fail.txt"
                    # ensure destination folder exists
                    (slot_run_dir / year / day).mkdir(parents=True, exist_ok=True)

                    # expected command string (even if attempt.py missing)
                    cmd_expected = f"{sys.executable} {attempt_py} {input_file}"

                    # If a result.txt already exists, prefer it (don't require attempt.py)
                    if result_txt_path.exists():
                        existing = result_txt_path.read_text(encoding="utf-8").strip()
                        print(f"[debug] found existing result for {slot_key} @ {result_txt_path}: {existing!r}")
                        # If there's a valid non-failure result, use it
                        if existing and not (existing.upper().startswith("FAIL") or existing.startswith("__ERROR__")):
                            if result1 and existing == result1:
                                return existing, "SUCCESS", cmd_expected
                            return existing, "FAIL-INCORRECT", cmd_expected
                        # Normalize empty or failure marker to explicit FAIL entry and return appropriate outcome
                        if not existing:
                            try:
                                result_txt_path.write_text("FAIL\n", encoding="utf-8")
                            except Exception:
                                pass
                            return "", "FAIL-MISSING", cmd_expected
                        if existing.startswith("__ERROR__"):
                            return "", "FAIL-ERROR", cmd_expected
                        # existing indicates failure already (e.g. "FAIL"), treat as missing/failed
                        return "", "FAIL-MISSING", cmd_expected

                    if not attempt_py.exists():
                        # no attempt in this run for that day
                        return "", "FAIL-MISSING", cmd_expected

                    captured, code, stdout, stderr, cmd_str = run_attempt_and_capture(attempt_py, input_file)
                    # On non-zero exit => record FAIL in result.txt and write failure details
                    if code != 0:
                        try:
                            result_txt_path.write_text("FAIL\n", encoding="utf-8")
                        except Exception:
                            pass
                        # write verbose failure file (stdout+stderr/exception)
                        try:
                            with failure_txt_path.open("w", encoding="utf-8") as fh:
                                fh.write("=== STDOUT ===\n")
                                fh.write(stdout or "")
                                fh.write("\n\n=== STDERR / EXCEPTION ===\n")
                                fh.write(stderr or "")
                        except Exception:
                            pass
                        # indicate an execution error
                        return "", "FAIL-ERROR", cmd_str

                    # If capture is empty, treat as failure and write "FAIL"
                    if not captured:
                        try:
                            result_txt_path.write_text("FAIL\n", encoding="utf-8")
                        except Exception:
                            pass
                        return "", "FAIL-MISSING", cmd_str

                    # Success: write captured result and determine outcome
                    try:
                        result_txt_path.write_text((captured or "") + ("\n" if captured and not captured.endswith("\n") else ""), encoding="utf-8")
                    except Exception:
                        pass

                    if result1 and captured == result1:
                        return captured, "SUCCESS", cmd_str
                    else:
                        return captured, "FAIL-INCORRECT", cmd_str

                # process single slot
                sp, so, scmd = _process_slot(single_run, "single")
                row["single_part1"] = sp
                row["single_outcome"] = so
                row["single_cmd"] = scmd

                # process multi slot
                mp, mo, mcmd = _process_slot(multi_run, "multi")
                row["multi_part1"] = mp
                row["multi_outcome"] = mo
                row["multi_cmd"] = mcmd

                # locate or standardize prompt.txt for multi runs (write CSV field)
                prompt_path_str = ""
                try:
                    if multi_run:
                        candidate_dir = multi_run / year / day
                        # standardized target
                        std_prompt = candidate_dir / "prompt.txt"
                        # common variant names the multi agent might produce
                        variants = [
                            candidate_dir / "prompts_multi.txt",
                            candidate_dir / "prompts.txt",
                            candidate_dir / "prompt_multi.txt",
                            candidate_dir / "prompts_multi.md",
                        ]
                        # prefer existing prompt.txt first
                        if std_prompt.exists():
                            prompt_path_str = str(std_prompt)
                        else:
                            for v in variants:
                                if v.exists():
                                    try:
                                        # copy variant content to standardized prompt.txt (do not remove original)
                                        std_prompt.write_bytes(v.read_bytes())
                                        prompt_path_str = str(std_prompt)
                                        break
                                    except Exception:
                                        # fallback to recording variant path if copy fails
                                        prompt_path_str = str(v)
                                        break
                except Exception:
                    prompt_path_str = ""

                row["prompt_path"] = prompt_path_str

                # write row immediately and flush to disk, then bump index
                try:
                    writer.writerow(row)
                    csv_fh.flush()
                    os.fsync(csv_fh.fileno())
                except Exception:
                    pass
                idx += 1

    # close incremental CSV writer
    try:
        csv_fh.close()
        print(f"[ok] incremental summary written to {OUT_CSV}")
    except Exception as e:
        print(f"[error] closing CSV: {e}")

    # create a timestamped copy of the live summary (optionally include a user-provided tag)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    def _sanitize(s: str) -> str:
        s = s.strip().replace(" ", "_")
        # keep only safe chars
        return re.sub(r"[^A-Za-z0-9_.-]", "", s)
    tag_part = ""
    if tag:
        safe = _sanitize(tag)
        if safe:
            tag_part = f"_{safe}"
    
    timestamped_csv = None
    try:
        # new naming: results_summary_<timestamp>[_<tag>].csv
        dst_name = f"results_summary_{ts}{tag_part}.csv"
        dst_path = OUT_CSV.parent / dst_name
        # avoid overwriting existing file
        if not dst_path.exists():
            shutil.copy2(OUT_CSV, dst_path)
            timestamped_csv = dst_path
            print(f"[ok] timestamped summary written to {dst_path}")
        else:
            # create unique name if collision
            unique = OUT_CSV.parent / f"results_summary_{ts}{tag_part}_{int(datetime.now().timestamp())}.csv"
            shutil.copy2(OUT_CSV, unique)
            timestamped_csv = unique
            print(f"[ok] timestamped summary written to {unique}")
    except Exception as e:
        print(f"[warn] could not create timestamped results_summary copy: {e}")
    
    return ts, tag_part, timestamped_csv


def generate_analysis(csv_path: Path, output_dir: Path, alpha: float = 0.05, timestamp: str = None, tag_part: str = ""):
    """
    Generate statistical analysis of results:
     - results_analysis_live.txt: text report with statistics
     Note: Visualization is handled separately by plot_results.py
     Returns (analysis_results, text_output, txt_path, None, timestamped_txt, None)
    """
    if not _have_analyze:
        print("[warn] analyze_results module not available; skipping analysis")
        return None, None, None, None, None, None

    if not csv_path.exists():
        print(f"[warn] CSV not found: {csv_path}; skipping analysis")
        return None, None, None, None, None, None

    txt_path = output_dir / "results_analysis_live.txt"
    png_path = output_dir / "results_analysis_live.png"

    try:
        # perform analysis
        res = analyze(csv_path, alpha)
        
        # write text report
        import io
        import sys as sys_mod
        old_stdout = sys_mod.stdout
        sys_mod.stdout = buffer = io.StringIO()
        try:
            nice_print(res, alpha)
            text_output = buffer.getvalue()
        finally:
            sys_mod.stdout = old_stdout
        
        txt_path.write_text(text_output, encoding="utf-8")
        print(f"[ok] analysis text written to {txt_path}")
        
        # create timestamped copy of txt
        timestamped_txt = None
        if timestamp:
            try:
                ts_txt_name = f"results_analysis_{timestamp}{tag_part}.txt"
                ts_txt_path = output_dir / ts_txt_name
                shutil.copy2(txt_path, ts_txt_path)
                timestamped_txt = ts_txt_path
                print(f"[ok] timestamped analysis text written to {ts_txt_path}")
            except Exception as e:
                print(f"[warn] could not create timestamped analysis text: {e}")
        
        # Note: visualization is handled by plot_results.py, not here
        return res, text_output, txt_path, None, timestamped_txt, None
            
    except Exception as e:
        print(f"[warn] analysis generation failed: {e}")
        return None, None, None, None, None, None

def generate_charts_from_csv(csv_path: Path, out_path: Path):
    """
    Produce a two-pane chart (stacked top/bottom):
     - top: years on x axis, grouped bars for %success (single vs multi)
     - bottom: row of pie charts, left-to-right by year, showing Multi-Agent outcomes only.
       No slice labels inside each pie; a single legend and a pane header "Outcome by Year".
    """
    if not _have_external_plot:
        print("[warn] external plotting utility not available; skipping chart generation")
        return

    if not csv_path.exists():
        print(f"[warn] CSV not found: {csv_path}; skipping charts")
        return

    # delegate to external plot_results.py utility
    try:
        plot_from_csv(csv_path, out_path)
    except Exception as e:
        print(f"[warn] chart generation failed: {e}")

if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--clear-results", action="store_true", help="Delete existing result.txt/result.fail.txt files before running")
    p.add_argument("--years", "-y", nargs="+", help="Limit to these years (e.g. 2020 2021). If omitted, all years discovered are processed")
    p.add_argument("--days", "-d", nargs="+", help="Limit to these days (e.g. day01 day02 3 4). If omitted, all days 01-25 are processed")
    p.add_argument("--models", "-m", nargs="+", help="Limit to these model names (exact or substring match, case-insensitive)")
    p.add_argument("--gpt", nargs="+", help="Limit to models containing these tokens (e.g. 3 3.5 4 5). Matches substring in model name")
    p.add_argument("--comp-only", action="store_true", help="Only generate comparison charts from existing results_summary_live.csv")
    p.add_argument("--chart-path", type=str, default=str(DATASETS_ROOT / "model_comparison_chart_live.png"), help="Output chart PNG path")
    p.add_argument("--tag", type=str, default=None, help="Optional tag to include in timestamped results summary filename")
    p.add_argument("--agg-tag", type=str, default="", help="Aggregation tag to add as last column in results_summary_live.csv (cannot be used with --clear-results)")
    p.add_argument("--no-archive", action="store_true", help="Do not run archive script after collection")
    p.add_argument("--no-plot", action="store_true", help="Do not generate plots after collection")
    args = p.parse_args()
    
    # Validate that agg-tag and clear-results are not both supplied
    if args.agg_tag and args.clear_results:
        print("[error] Cannot use --agg-tag with --clear-results")
        sys.exit(1)

    # Debug: show which filters will be applied
    print(f"[info] filters -> years={args.years}, days={args.days}, models={args.models}, gpt={args.gpt}, clear_results={args.clear_results}, agg_tag={args.agg_tag}")

    if args.comp_only:
        if _have_external_plot and plot_from_csv:
            csv_path = Path(args.chart_path).parent / "results_summary_live.csv"
            # detect number of years in CSV to determine by_day mode
            by_day = False
            try:
                import csv as csv_mod
                with csv_path.open("r", encoding="utf-8", newline="") as fh:
                    reader = csv_mod.DictReader(fh)
                    years_in_csv = set()
                    for row in reader:
                        y = (row.get("year") or "").strip()
                        if y:
                            years_in_csv.add(y)
                    by_day = len(years_in_csv) == 1
            except Exception:
                pass
            plot_from_csv(csv_path, Path(args.chart_path), by_day=by_day)
        else:
            print("[warn] plot_results module not available; cannot generate comparison chart (--comp-only).")
        sys.exit(0)

    # forward days and models selection into collect
    ts, tag_part, timestamped_csv = collect(
        clear_results=args.clear_results,
        years=args.years,
        gpt_levels=args.gpt,
        days=args.days,
        models_filter=args.models,
        tag=args.tag,
        agg_tag=args.agg_tag,
    )
    
    # always generate charts after a normal run (use external scripts/plot_results.py)
    chart_path = Path(args.chart_path)
    timestamped_chart = None
    if not args.no_plot and _have_external_plot and plot_from_csv:
        # detect number of years to determine by_day mode
        by_day = False
        if args.years and len(args.years) == 1:
            by_day = True
        elif not args.years:
            # if no years specified, check CSV for unique years
            try:
                import csv as csv_mod
                with OUT_CSV.open("r", encoding="utf-8", newline="") as fh:
                    reader = csv_mod.DictReader(fh)
                    years_in_csv = set()
                    for row in reader:
                        y = (row.get("year") or "").strip()
                        if y:
                            years_in_csv.add(y)
                    by_day = len(years_in_csv) == 1
            except Exception:
                pass
        plot_from_csv(OUT_CSV, chart_path, by_day=by_day)
        
        # create timestamped copy of chart
        if ts:
            try:
                ts_chart_name = f"model_comparison_chart_{ts}{tag_part}.png"
                ts_chart_path = chart_path.parent / ts_chart_name
                shutil.copy2(chart_path, ts_chart_path)
                timestamped_chart = ts_chart_path
                print(f"[ok] timestamped chart written to {ts_chart_path}")
            except Exception as e:
                print(f"[warn] could not create timestamped chart: {e}")
    else:
        print("[warn] plot_results module not available; skipping chart generation")
    
    # generate statistical analysis
    analysis_res, analysis_text, txt_path, png_path, timestamped_txt, timestamped_png = generate_analysis(
        OUT_CSV, DATASETS_ROOT, timestamp=ts, tag_part=tag_part
    )
    
    # create zip file with all timestamped artifacts
    if ts and any([timestamped_csv, timestamped_chart, timestamped_txt, timestamped_png]):
        try:
            zip_name = f"results_bundle_{ts}{tag_part}.zip"
            zip_path = DATASETS_ROOT / zip_name
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                if timestamped_csv and timestamped_csv.exists():
                    zf.write(timestamped_csv, timestamped_csv.name)
                if timestamped_chart and timestamped_chart.exists():
                    zf.write(timestamped_chart, timestamped_chart.name)
                if timestamped_txt and timestamped_txt.exists():
                    zf.write(timestamped_txt, timestamped_txt.name)
                if timestamped_png and timestamped_png.exists():
                    zf.write(timestamped_png, timestamped_png.name)
            print(f"[ok] results bundle created: {zip_path}")
        except Exception as e:
            print(f"[warn] could not create results bundle zip: {e}")
    
    # run archive process to move old runs and timestamped artifacts
    if not args.no_archive:
        print("\n" + "="*80)
        print("ARCHIVING OLD RESULTS")
        print("="*80)
        try:
            archive_script = Path(__file__).parent / "archive_results.py"
            if archive_script.exists():
                result = subprocess.run([sys.executable, str(archive_script), "--yes"], 
                                       capture_output=True, text=True, timeout=60)
                if result.returncode == 0:
                    print(result.stdout)
                else:
                    print(f"[warn] archive process returned non-zero exit code: {result.returncode}")
                    if result.stderr:
                        print(result.stderr)
            else:
                print(f"[warn] archive script not found: {archive_script}")
        except Exception as e:
            print(f"[warn] could not run archive process: {e}")
    else:
        print("[info] --no-archive set; skipping archive process")
    
    # print analysis results at the very end (after archiving)
    print("\n" + "="*80)
    print("ANALYSIS RESULTS")
    print("="*80)
    
    # Print analysis results - either from generated text or read from file
    if analysis_text:
        print(analysis_text)
    else:
        # Fallback: read from results_analysis_live.txt if it exists
        analysis_live_path = DATASETS_ROOT / "results_analysis_live.txt"
        if analysis_live_path.exists():
            try:
                print(analysis_live_path.read_text(encoding="utf-8"))
            except Exception as e:
                print(f"[warn] could not read analysis results: {e}")
        else:
            print("[warn] no analysis results available")