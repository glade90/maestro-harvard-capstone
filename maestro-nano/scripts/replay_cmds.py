#!/usr/bin/env python3
"""Replay single_cmd / multi_cmd from results_summary_live.csv by index.

Usage:
  python replay_cmds.py 123        # run both commands for index 123
  python replay_cmds.py 123 --which single
  python replay_cmds.py 123 --package        # create zip package for the record (keeps running commands)
  python replay_cmds.py 123 --package --out C:\tmp\rec123.zip
  python replay_cmds.py 123 --csv C:\path\to\custom.csv  # use custom CSV file
"""
from __future__ import annotations
from pathlib import Path
import csv
import subprocess
import sys
import argparse
import zipfile
from datetime import datetime
import re

from paths import get_maestro_nano_root, get_repo_root

MAESTRO_NANO_ROOT = get_maestro_nano_root()
REPO_ROOT = get_repo_root()
DEFAULT_CSV_PATH = MAESTRO_NANO_ROOT / "baseline" / "datasets" / "aoc" / "results_summary_live.csv"

def load_row_by_index(idx: int, csv_path: Path):
    if not csv_path.exists():
        print(f"[error] CSV not found: {csv_path}", file=sys.stderr)
        sys.exit(2)
    with csv_path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            try:
                if int(r.get("index", -1)) == idx:
                    return r
            except Exception:
                # skip rows with non-int index
                continue
    return None

def print_record_as_series(row: dict):
    print("\n==== Record ====")
    for k, v in row.items():
        print(f"{k}: {v}")

def run_cmd(cmd: str, timeout: int | None):
    """
    Run command and return CompletedProcess. Do NOT raise on non-zero exit;
    caller handles errors so we can always proceed to packaging.
    """
    if not cmd or not cmd.strip():
        print("[info] no command to run")
        return None
    print(f"[run] {cmd}")
    proc = subprocess.run(cmd, shell=True, text=True, capture_output=True, timeout=timeout)
    if proc.stdout:
        print("--- STDOUT ---")
        print(proc.stdout, end="")
    if proc.stderr:
        print("--- STDERR ---", file=sys.stderr)
        print(proc.stderr, file=sys.stderr, end="")
    if proc.returncode == 0:
        print(f"[ok] exit {proc.returncode}")
    else:
        print(f"[error] exit {proc.returncode} (continuing)", file=sys.stderr)
    return proc

def _first_path_from_field(val: str) -> str:
    if not val:
        return ""
    parts = [p.strip() for p in str(val).split(",") if p.strip()]
    return parts[0] if parts else ""

def _find_first_path_from_row(row: dict, fields):
    """Try one or many candidate CSV field names and return the first non-empty path token."""
    if isinstance(fields, (list, tuple)):
        for f in fields:
            v = row.get(f)
            if v and str(v).strip():
                return _first_path_from_field(v)
        return ""
    else:
        return _first_path_from_field(row.get(fields, "") or "")

def _slugify(s: str, maxlen: int = 40) -> str:
    """Make a filesystem-safe short token from arbitrary text."""
    if not s:
        return ""
    t = str(s).strip()
    # prefer short stems when given a path
    try:
        p = Path(t)
        if p.name and p.suffix:
            t = p.stem
    except Exception:
        pass
    # replace non-alnum with underscore, collapse underscores, trim
    t = re.sub(r"[^A-Za-z0-9]+", "_", t)
    t = re.sub(r"_+", "_", t).strip("_")
    return t[:maxlen]

def package_row_to_zip(row: dict, out_path: Path, extra_contents: dict | None = None):
    # mapping CSV fields -> archive keys
    mapping = [
        ("1_PROBLEM", ["readme_path", "readme", "problem_path", "problem"]),
        ("2_SINGLE_AGENT_PROMPT", ["single_prompt_path", "single_prompt", "prompt_single", "prompt_path", "prompt"]),
        ("3_MULTI_AGENT_PROMPT", ["multi_prompt_path", "multi_prompt", "prompt_multi", "prompts", "prompt_path"]),
        ("4_MULTI_ERROR", ["multi_error_path", "multi_error", "multi_result_path", "multi_result", "multi_error_log"]),
        ("5_SINGLE_AGENT_CODE", ["single_attempt_path", "single_attempt", "single_code_path", "single_attempt"]),
        ("6_MULTI_AGENT_CODE", ["multi_attempt_path", "multi_attempt", "multi_code_path", "multi_attempt"]),
        ("7_SINGLE_AGENT_RESULT", ["single_result_path", "single_result", "single_result_file"]),
        ("8_MULTI_AGENT_RESULT", ["multi_result_path", "multi_result", "multi_result_file"]),
        ("9_CORRECT_RESULT", ["result1_path", "result1", "results1", "results1_path", "results1.txt"]),
    ]

    preset_text = (
        "You are a Prompt Engineer. we are chooseing examples where a single agent seems to outperform a multi agent...."
        "IMPORTANT: this is an experiment so anything we fix must be considered for both single and multi agent setups except changes to Requirements and TDD Agent"
        "im going to give you 1. the problem. 2. The single agent promt. 3. The multi agent prompt. 4. The error we got on the multi agent."
        " 5. The code that the single Agent wrote and 6. the code that the mult agent wrote.... WHAT I WANT YOU TO DO is TELL ME HOW TO REFINE THE PROMPT SO THAT in General the multi agent improves its performance."
    )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_lines = []
    manifest_lines.append(f"Record index: {row.get('index')}")
    manifest_lines.append(f"Generated: {datetime.now().isoformat()}")
    manifest_lines.append("")
    added = 0
    with zipfile.ZipFile(out_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        # add preset readme
        zf.writestr("0_PRESET_README.txt", preset_text)
        manifest_lines.append("0_PRESET_README.txt -> added")

        for key, field in mapping:
            val = _find_first_path_from_row(row, field)
            if not val:
                manifest_lines.append(f"{key}: <missing csv field {field}>")
                continue
            p = Path(val)
            if not p.is_absolute():
                alt = REPO_ROOT / val
                if alt.exists():
                    p = alt
            if p.exists():
                arcname = f"{key}_{p.name}"
                zf.write(p, arcname=str(arcname))
                manifest_lines.append(f"{key}: {p} -> {arcname}")
                added += 1
            else:
                # record missing file into manifest inside zip
                missing_note = f"{key}: referenced path {val} not found"
                zf.writestr(f"{key}_MISSING.txt", missing_note)
                manifest_lines.append(missing_note)

        # write manifest
        zf.writestr("MANIFEST.txt", "\n".join(manifest_lines))
        # include any extra in-memory contents (e.g. captured stderr/stdout)
        if extra_contents:
            for name, content in extra_contents.items():
                try:
                    if isinstance(content, bytes):
                        zf.writestr(name, content)
                    else:
                        zf.writestr(name, str(content))
                    manifest_lines.append(f"EXTRA: {name} -> added")
                except Exception:
                    manifest_lines.append(f"EXTRA: {name} -> failed to add")

    print(f"[ok] created package: {out_path} (files added: {added})")
    return out_path

def main():
    p = argparse.ArgumentParser()
    p.add_argument("index", type=int, help="Index value from results_summary_live.csv to replay")
    p.add_argument("--csv", type=str, default=None, help=f"Path to CSV file (default: {DEFAULT_CSV_PATH})")
    p.add_argument("--which", choices=["single", "multi", "both"], default="both", help="Which command(s) to run")
    p.add_argument("--timeout", type=int, default=None, help="Timeout seconds for each command")
    p.add_argument("--package", action="store_true", help="Create zip package of record files (does not prevent running commands)")
    p.add_argument("--out", type=str, default=None, help="Output zip path when --package is used")
    args = p.parse_args()

    csv_path = Path(args.csv) if args.csv else DEFAULT_CSV_PATH
    
    row = load_row_by_index(args.index, csv_path)
    if not row:
        print(f"[error] no row with index {args.index} found in {csv_path}", file=sys.stderr)
        sys.exit(3)

    print_record_as_series(row)
    extra_contents = {}
    # create package if requested (always attempt, even if commands failed)
    if args.package:
        if args.out:
            outp = Path(args.out)
        else:
            # build descriptive filename: YEAR_PROBLEM_MULTIOUTCOME.zip
            year_tok = _slugify(row.get("year", "") or "")
            # prefer explicit problem column, then readme_path stem
            raw_problem = row.get("problem") or row.get("problem_name") or Path(row.get("readme_path","")).stem or ""
            # remove any "day" tokens like "day16" (case-insensitive) and surrounding separators
            problem_clean = re.sub(r"(?i)\bday[_-]?\d+\b", "", raw_problem)
            # normalize whitespace/underscores then slugify
            problem_clean = re.sub(r"[_\s]+", "_", problem_clean).strip("_")
            problem_tok = _slugify(problem_clean) or "problem"
            multi_tok = _slugify(row.get("multi_outcome") or row.get("multi_result") or "")
            parts = [p for p in (year_tok, problem_tok, multi_tok) if p]
            base = "_".join(parts) if parts else "record"
            outp = Path(f"{base}.zip")
        try:
            package_row_to_zip(row, outp, extra_contents=extra_contents)
            # print absolute path of created zip
            print(str(outp.resolve()))
        except Exception as e:
            print(f"[error] packaging failed: {e}", file=sys.stderr)
            sys.exit(4)

    # ensure commands are read from the CSV row so run_cmd has them available
    single_cmd = (row.get("single_cmd") or "").strip()
    multi_cmd = (row.get("multi_cmd") or "").strip()
    if not single_cmd:
        print("[warn] single_cmd is empty for this record")
    if not multi_cmd:
        print("[warn] multi_cmd is empty for this record")
    
    # run commands but don't abort on failure; capture outputs for packaging
    try:
        if args.which in ("single", "both"):
            print("\n==== Running Command (Single) ====")
            print(f"[info] running single_cmd (index={args.index})")
            p = run_cmd(single_cmd, timeout=args.timeout)
            if p is not None and p.returncode != 0:
                extra_contents["single_error.txt"] = f"STDOUT:\n{p.stdout or ''}\n\nSTDERR:\n{p.stderr or ''}"
        if args.which in ("multi", "both"):
            print("\n==== Running Command (Multi) ====")
            print(f"[info] running multi_cmd (index={args.index})")
            p = run_cmd(multi_cmd, timeout=args.timeout)
            if p is not None and p.returncode != 0:
                extra_contents["multi_error.txt"] = f"STDOUT:\n{p.stdout or ''}\n\nSTDERR:\n{p.stderr or ''}"
    except Exception as e:
        # catch unexpected exceptions but continue to packaging
        print(f"[error] unexpected failure while running commands: {e}", file=sys.stderr)
        extra_contents["replay_exception.txt"] = str(e)


if __name__ == "__main__":
    main()