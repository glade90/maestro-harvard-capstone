#!/usr/bin/env python
import argparse
import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

TASKS = [
    "advent_day6",
    "alarm_system",
    "bowling_game",
    "darts",
    "lcd_digits",
    "simple_add",
    "tetris",
    "tic_tac_toe",
]


def create_client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY not set")
    return OpenAI(api_key=api_key)


def call_llm(client: OpenAI, model: str, prompt: str, retries: int = 3):
    for attempt in range(retries):
        try:
            resp = client.responses.create(model=model, input=prompt, temperature=0.2)
            if hasattr(resp, "output_text") and resp.output_text:
                return resp.output_text, resp
            if hasattr(resp, "output") and resp.output:
                parts = []
                for out in resp.output:
                    content = out.get("content", [])
                    for c in content:
                        if isinstance(c, dict):
                            txt = c.get("text") or c.get("title") or ""
                            if txt:
                                parts.append(txt)
                        else:
                            parts.append(str(c))
                if parts:
                    return "\n\n".join(parts), resp
            if hasattr(resp, "data") and resp.data:
                parts = []
                for item in resp.data:
                    if isinstance(item, dict):
                        txt = item.get("text") or item.get("content") or ""
                        if txt:
                            parts.append(txt if isinstance(txt, str) else " ".join(map(str, txt)))
                if parts:
                    return "\n\n".join(parts), resp
            return json.dumps(resp.to_dict() if hasattr(resp, "to_dict") else resp.__dict__), resp
        except TypeError as te:
            if attempt + 1 == retries:
                raise RuntimeError(f"LLM call TypeError: {te}") from te


CODE_FENCE_RE = re.compile(r"```(?:[^\n]*)\n(.*?)(?:\n```|```$)", re.S | re.I)


def extract_py_blocks(md: str):
    blocks = CODE_FENCE_RE.findall(md)
    if blocks:
        return blocks
    if "```" in md:
        parts = md.split("```")
        return [parts[i] for i in range(1, len(parts), 2)]
    return []


def save_artifacts_from_md(results_base_dir: Path, timestamp_dir: Path, task: str, timestamp: str, md_text: str):
    """
    Save markdown and extracted python artifacts into a single timestamped folder layout:
      results_base_dir / timestamp / <task> / ...
    """
    out_dir = timestamp_dir / task
    out_dir.mkdir(parents=True, exist_ok=True)

    blocks = extract_py_blocks(md_text)

    impl_parts = [b for b in blocks]

    if impl_parts:
        (out_dir / "implementation.py").write_text("\n\n".join(impl_parts), encoding="utf-8")

    return out_dir


def main():
    p = argparse.ArgumentParser(description="Run LLM on prose requirements only and save artifacts.")
    p.add_argument("--model", default="gpt-4o-mini")
    p.add_argument("--trial-run", action="store_true")
    p.add_argument("--tasks", nargs="*", help="Optional list of task names to run")
    args = p.parse_args()

    repo_dir = Path(__file__).resolve().parents[2]
    benchmark_dir = repo_dir / "benchmark"
    results_root = repo_dir / "vanilla" / "results"

    client = create_client()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    timestamp_dir = results_root / timestamp

    tasks = args.tasks if args.tasks else TASKS

    # strict check: require prose file for every requested task
    missing = []
    for task in tasks:
        pfile = benchmark_dir / task / "requirements-nl-prose.md"
        if not pfile.exists():
            missing.append(str(pfile))
    if missing:
        print("Error: missing requirements-nl-prose.md for the following tasks:")
        for m in missing:
            print("  " + m)
        sys.exit(1)

    # create single timestamp folder up-front
    timestamp_dir.mkdir(parents=True, exist_ok=True)

    for task in tasks:
        task_dir = benchmark_dir / task
        print(f"[info] Task: {task}")
        prose_path = task_dir / "requirements-nl-prose.md"
        requirements_text = prose_path.read_text(encoding="utf-8")

        if args.trial_run:
            print("[trial-run] would call LLM and write artifacts")
            continue

        prompt = (
            "You are an expert Python developer. Given the following "
            "requirements (prose), produce idiomatic Python implementation code "
            "that aims to satisfy the requirements (prose). "
            "Return output as fenced python code blocks only.\n\n"
            "Requirements (Prose):\n\n"
            f"{requirements_text}\n"
        )


        try:
            print(f"[info] calling LLM for task: {task} (model={args.model})")
            text, raw = call_llm(client, args.model, prompt)
        except Exception as e:
            print(f"[error] LLM call failed for {task}: {e}")
            continue

        out_dir = save_artifacts_from_md(results_root, timestamp_dir, task, timestamp, text)
        try:
            raw_path = out_dir / "response.raw.json"
            with raw_path.open("w", encoding="utf-8") as fh:
                json.dump(raw.to_dict() if hasattr(raw, "to_dict") else raw.__dict__, fh, indent=2, ensure_ascii=False)
        except Exception:
            pass

        print(f"[ok] wrote artifacts to: {out_dir}")

    print(f"[done] results written under: {timestamp_dir}")


if __name__ == "__main__":
    main()
