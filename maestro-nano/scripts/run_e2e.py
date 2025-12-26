#!/usr/bin/env python
import argparse
import re
import os
import sys

from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI
from pathlib import Path
from typing import Union

from prompt_sets import get_prompt_set

from paths import get_maestro_nano_root

try:
    from tqdm import tqdm
    _have_tqdm = True
except Exception:
    _have_tqdm = False
    
def create_client() -> OpenAI:
    """
    Create OpenAI client, loading the API key from the environment.
    """
    # Load environment variables
    load_dotenv()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set.\n"
            "Set it in your terminal with `export OPENAI_API_KEY=\"your-api-key-here\"` "
        )

    return OpenAI(api_key=api_key)


def load_problem(problem_dir: Path) -> str:
    """
    Load the description for problem.
    """
    path = problem_dir / "README.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")

    raise FileNotFoundError(
        f"Could not find {path}"
    )


def call_llm(client: OpenAI, model: str, prompt: str, temperature: float = 1.0) -> tuple:
    """
    Call the OpenAI Responses API with the given prose and
    return (text_output, model_used).
    """
    response = client.responses.create(
        model=model,
        input=prompt,
        temperature=temperature,
    )

    # Extract model used when available
    model_used = getattr(response, "model", None)

    # 1. GPT-5 / Responses convenience
    text = getattr(response, "output_text", None)
    if isinstance(text, str) and text.strip():
        return text, model_used

    # 2. GPT-4o / older shape
    try:
        text = response.output[0].content[0].text
        if isinstance(text, str):
            return text, model_used
    except Exception:
        pass

    return "", model_used


def _read_input_sample(input_path: Union[str, Path], n: int = 5) -> str:
    """Return first n lines of input_path as a single string (or empty if not available)."""
    try:
        p = Path(input_path)
        if not p.is_file():
            return ""
        lines = []
        with p.open("r", encoding="utf-8", errors="ignore") as fh:
            for i, ln in enumerate(fh):
                if i >= n:
                    break
                lines.append(ln.rstrip("\n"))
        return "\n".join(lines)
    except Exception:
        return ""

def e2e(
    client: OpenAI,
    model: str,
    problem_description: str,
    mode: str,
    input_path: Union[str, Path],
    out_dir: Path = None,
    no_tdd: bool = False,
    temperature: float = 0.2,   # ← NEW ARGUMENT (default low for stability)
    pipeline: str = "rtc",  # ← NEW ARGUMENT: multi-agent pipeline (r=requirements, t=tdd, c=code)
    prompt_set_name: str = "DEFAULT",  # ← NEW ARGUMENT: prompt set to use
) -> str:

    input_path_p = Path(input_path)
    input_sample = _read_input_sample(input_path_p, n=5)
    
    # Get prompt set
    prompt_set = get_prompt_set(prompt_set_name)
    
    # Build io_contract from prompt set
    io_contract = prompt_set.build_io_contract()

    # ----------------------------------------------------------------------
    # SINGLE AGENT
    # ----------------------------------------------------------------------
    if mode == "single":
        prompt = prompt_set.build_coding_prompt(
            problem_description=problem_description,
            io_contract=io_contract,
            input_sample=input_sample
        )

        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "prompt_single.txt").write_text(prompt, encoding="utf-8")

        # CALL WITH TEMPERATURE
        text, model_used = call_llm(client, model, prompt, temperature=temperature)

        if out_dir and model_used:
            (out_dir / "model").write_text(str(model_used), encoding="utf-8")

        return text

    # ----------------------------------------------------------------------
    # MULTI AGENT
    # ----------------------------------------------------------------------
    elif mode == "multi":
        # Normalize pipeline string
        pipeline = pipeline.lower()
        
        # ---------------------------
        # PIPELINE: 'c' - CODE AGENT ONLY
        # ---------------------------
        if pipeline == 'c':
            code_prompt = prompt_set.build_coding_agent_prompt(
                problem_description=problem_description,
                io_contract=io_contract,
                input_sample=input_sample
            )
            
            if out_dir:
                out_dir.mkdir(parents=True, exist_ok=True)
                (out_dir / "prompts_multi.txt").write_text(
                    "=== CODE PROMPT ===\n" + code_prompt,
                    encoding="utf-8"
                )
            
            code_text, code_model = call_llm(
                client, model, code_prompt, temperature=temperature
            )
            
            if out_dir and code_model:
                (out_dir / "model").write_text(str(code_model), encoding="utf-8")
            
            return code_text
        
        # Initialize variables
        structured_requirements = ""
        requirements_prompt = ""
        test_suite = ""
        tdd_prompt = ""
        
        # ---------------------------
        # REQUIREMENTS AGENT (if 'r' in pipeline)
        # ---------------------------
        if 'r' in pipeline:
            requirements_prompt = prompt_set.build_requirements_prompt(
                problem_description=problem_description,
                io_contract=io_contract,
                input_sample=input_sample
            )

            structured_requirements, model_used = call_llm(
                client, model, requirements_prompt, temperature=temperature
            )

        # ---------------------------
        # TDD AGENT (if 't' in pipeline)
        # ---------------------------
        if 't' in pipeline:
            # If we have structured requirements, use them; otherwise use problem description
            req_text = structured_requirements if structured_requirements else problem_description
            tdd_prompt = prompt_set.build_tdd_prompt(
                structured_requirements=req_text,
                problem_description=problem_description,
                io_contract=io_contract,
                input_sample=input_sample
            )

            test_suite, _ = call_llm(
                client, model, tdd_prompt, temperature=temperature
            )

        # ---------------------------
        # CODE GENERATION AGENT (always runs for non-'c' pipelines)
        # ---------------------------
        # Use structured requirements if available, otherwise use problem description
        req_text = structured_requirements if structured_requirements else problem_description
        
        code_prompt = prompt_set.build_code_generation_prompt(
            structured_requirements=req_text,
            problem_description=problem_description,
            io_contract=io_contract,
            test_suite=test_suite,
            input_sample=input_sample
        )

        if out_dir:
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / "prompts_multi.txt").write_text(
                "=== REQUIREMENTS PROMPT ===\n" + requirements_prompt +
                "\n\n=== TDD PROMPT ===\n" + (tdd_prompt or "") +
                "\n\n=== CODE PROMPT ===\n" + code_prompt,
                encoding="utf-8"
            )

        # FINAL CALL — WITH TEMPERATURE
        code_text, code_model = call_llm(
            client, model, code_prompt, temperature=temperature
        )

        if out_dir and code_model:
            (out_dir / "model").write_text(str(code_model), encoding="utf-8")

        return code_text

def extract_py_blocks(text: str) -> str:
    pattern = r"```python(.*?)```"
    blocks = re.findall(pattern, text, flags=re.DOTALL)
    return "\n\n".join(b.strip() for b in blocks)


def main() -> None:
    p = argparse.ArgumentParser(
        description="Test LLM on requirements."
    )
    p.add_argument(
        "--model",
        default="gpt-4o-mini",
        help="LLM to test.",
    )
    p.add_argument(
        "--mode",
        required=True,
        choices=["single","multi"],
        help="Use a single or multi agent pipeline. (default: single)",
    )
    p.add_argument(
        "--years",
        "-y",
        nargs="+",
        help="Limit to these years (e.g. 2020 2021). If omitted, all years discovered are processed",
    )
    p.add_argument(
        "--days",
        "-d",
        nargs="+",
        help="Limit to these days (e.g. day01 day02 or 1 2 3). If omitted, all days 1-25 are processed",
    )
    p.add_argument(
        "--trial-run",
        action="store_true",
        help="Only show which files would be processed, no API calls.",
    )
    p.add_argument(
        "--no-tdd",
        action="store_true",
        help="Disable TDD agent in multi-agent mode (Requirements -> Code only). Deprecated: use --pipeline instead.",
    )
    p.add_argument(
        "--pipeline",
        type=str,
        default="rtc",
        help="Multi-agent pipeline configuration (default: rtc). Options: rtc (requirements+tdd+code), rc (requirements+code), tc (tdd+code), c (code only).",
    )
    p.add_argument(
        "--temperature",
        "-t",
        type=float,
        default=1.0,
        help="Temperature for LLM sampling (0.0-2.0, default: 1.0). Lower = more deterministic.",
    )
    p.add_argument(
        "--prompt-set",
        type=str,
        default="DEFAULT",
        help="Prompt set to use (default: DEFAULT).",
    )
    p.add_argument(
        "--no-archive",
        action="store_true",
        help="Do not run archive script after run.",
    )
    args = p.parse_args()
    
    maestro_nano_root = get_maestro_nano_root()
    baseline_dir = maestro_nano_root / "baseline"

    datasets_dir = baseline_dir / "datasets"
    #print(f"[info] datasets directory in E2E script: {datasets_dir}")
    results_dir = baseline_dir / "results"
    aoc_dir = datasets_dir / "aoc"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_results_dir = results_dir / args.mode / f"{timestamp}_{args.model}"

    client = create_client()
    print(f"model: {args.model}")

    if args.trial_run:
        print(f"trial run")
    else:
        current_results_dir.mkdir(parents=True, exist_ok=True)
        print(f"official run")
    
    print(f"{args.mode} agent")

    # Advent of Code 
    # iterate years and days with optional tqdm wrappers
    years_iter = tqdm(args.years, desc="Years", unit="year") if _have_tqdm else args.years
    for year in years_iter:
        year_dir = aoc_dir / year
        # Advent of Code has 25 days in total
        #print(f"\n*** Year: {year} ***", flush=True)

        # build list of days to run (preserve user order if provided)
        if args.days:
            days = []
            for tok in args.days:
                s = str(tok).strip()
                if re.match(r"^day\d{1,2}$", s, re.I):
                    days.append(s.lower())
                    continue
                if s.isdigit():
                    n = int(s)
                    if 1 <= n <= 25:
                        days.append(f"day{n:02d}")
                        continue
                # ignore invalid token but warn
                print(f"[warn] ignoring invalid --days token: {tok}")
            # dedupe while preserving order
            seen = set()
            days = [d for d in days if not (d in seen or seen.add(d))]
            if not days:
                print("[warn] no valid days provided via --days; defaulting to all days")
                days = [f"day{i:02d}" for i in range(1, 26)]
        else:
            days = [f"day{i:02d}" for i in range(1, 26)]
        days_iter = tqdm(days, desc=f"Days ({year})", unit="day") if _have_tqdm else days
        for day in days_iter:
            # ensure immediate flush so wrapper streaming shows lines promptly
            #print(f"\n=== Day: {day} ===", flush=True)
            day_dir = year_dir / day
            if not day_dir.is_dir():
                print(f"Skipping: directory not found: {day_dir}")
                continue

            try:
                problem_text = load_problem(day_dir)
            except FileNotFoundError as e:
                print(f"Skipping: {e}")
                continue
            
            code_dir = current_results_dir / year / day
            code_path = code_dir / "attempt.py"

            if not args.trial_run:
                # Determine pipeline: use --pipeline if provided, otherwise use --no-tdd for backward compatibility
                pipeline = args.pipeline
                if args.no_tdd and pipeline == "rtc":
                    pipeline = "rc"  # Convert --no-tdd to pipeline without 't'
                
                # tell e2e to write prompts into the run folder so prompt.txt appears next to attempt.py
                text = e2e(client, args.model, problem_text, args.mode, day_dir / "input.txt", out_dir=code_dir, temperature=args.temperature, pipeline=pipeline, prompt_set_name=args.prompt_set)
                code = extract_py_blocks(text)

                code_dir.mkdir(parents=True, exist_ok=True)
                code_path.write_text(code, encoding="utf-8")
                # ensure prompt.txt exists (multi branch creates it). If not, attempt to copy other variants.
                try:
                    std = code_dir / "prompt.txt"
                    if not std.exists():
                        for alt in ("prompts_multi.txt", "prompts.txt", "prompt_multi.txt", "prompt_single.txt"):
                            altp = code_dir / alt
                            if altp.exists():
                                try:
                                    std.write_bytes(altp.read_bytes())
                                    break
                                except Exception:
                                    continue
                except Exception:
                    pass
            #print(
            #    f"Problem: {day_dir / 'README.md'} \n"
            #    f"Code   : {code_path} "
            #)

if __name__ == "__main__":
    main()