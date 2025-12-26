#!/usr/bin/env python
import argparse
import json
import time
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()


SYSTEM_INSTR = (
    "You are a concise technical writer. Convert the provided requirements markdown into "
    "clear, human-readable prose paragraphs that preserve all requirement intent and scope. "
    "Do not lose any requirements details and do not make any requirements up. "
    "They should not be in anything like agile format, but rather as coherent prose. "
    "The purpose is to mimic how a human user (non Businessanalyst) would provide requirements. "
    "Then append the verbatim 'Technical Requirements' section labeled exactly as shown. "
    "Do not add new requirements or remove anything required by the source files."
)

USER_PROMPT_TEMPLATE = """Source requirements (MARKDOWN):
---
{requirements_md}
---

Technical requirements file (verbatim, may be missing):
---
{tech_md}
---

Instructions:
1) Produce a short title line, then 1–4 paragraphs of prose that capture the requirements in natural-language form (complete coverage, concise).
2) After the prose paragraphs include a section:

## Technical Requirements

and paste the Technical Requirements content verbatim (or a one-line note if missing).

Keep the prose neutral, present tense, and avoid implementation details unless present in the source.
"""

def call_llm(client: OpenAI, model: str, prompt: str, retries: int = 3, wait: float = 1.0):
    """
    Call the Responses API using the `input=` parameter (some SDK versions do not accept `messages=`).
    Return (text, raw_response).
    """
    for attempt in range(retries):
        try:
            # Use `input=` with a list of role/content dicts so it's compatible with the Responses API
            resp = client.responses.create(
                model=model,
                input=[
                    {"role": "system", "content": SYSTEM_INSTR},
                    {"role": "user", "content": prompt},
                ],
            )

            # Preferred simple accessor if available
            if hasattr(resp, "output_text") and resp.output_text:
                return resp.output_text, resp

            # Try the structured output array
            if hasattr(resp, "output") and resp.output:
                parts = []
                for out in resp.output:
                    # each out may have a 'content' list of dicts
                    content = out.get("content", [])
                    for c in content:
                        # c can be a dict with 'text'
                        if isinstance(c, dict):
                            text = c.get("text") or c.get("title") or c.get("content")
                            if text:
                                parts.append(text)
                        else:
                            # fallback: string-like
                            parts.append(str(c))
                if parts:
                    return "\n\n".join(parts), resp

            # Older / alternate shapes: inspect `data` or top-level fields
            if hasattr(resp, "data") and resp.data:
                parts = []
                for item in resp.data:
                    text = ""
                    # some SDKs nest text in item['text'] or item['content']
                    if isinstance(item, dict):
                        text = item.get("text") or item.get("content") or ""
                        if isinstance(text, list):
                            # join if a list of chunks
                            text = " ".join(str(t) for t in text)
                    if text:
                        parts.append(text)
                if parts:
                    return "\n\n".join(parts), resp

            # Last resort: stringify the response
            return json.dumps(resp.to_dict() if hasattr(resp, "to_dict") else resp.__dict__), resp

        except TypeError as te:
            # Common cause: unexpected kwargs like `messages` on some SDK versions
            # Surface a clearer message on final failure
            if attempt + 1 == retries:
                raise RuntimeError(f"LLM call failed (TypeError): {te}. Check SDK version and use `input=` instead of `messages`.") from te
            time.sleep(wait * (2 ** attempt))
        except Exception as e:
            if attempt + 1 == retries:
                raise
            time.sleep(wait * (2 ** attempt))

def process_task(client: OpenAI, model: str, task_dir: Path, out_name: str = "requirements-nl-prose.md", dry_run: bool = False):
    req_md_path = task_dir / "requirements-nl.md"
    tech_md_path = task_dir / "requirements-nl-tech.md"
    if not req_md_path.exists():
        print(f"Skipping {task_dir.name}: requirements-nl.md not found")
        return None

    req_md = req_md_path.read_text(encoding="utf-8")
    tech_md = tech_md_path.read_text(encoding="utf-8") if tech_md_path.exists() else "_No technical requirements file found._"

    prompt = USER_PROMPT_TEMPLATE.format(requirements_md=req_md, tech_md=tech_md)
    print(f"[info] calling LLM for task: {task_dir.name} (model={model})")
    if dry_run:
        out_path = task_dir / out_name
        out_path.write_text("# PROSE (dry-run)\n\n" + "LLM call skipped (dry-run).", encoding="utf-8")
        print(f"[dry-run] wrote placeholder: {out_path}")
        return out_path

    text, raw_resp = call_llm(client, model, prompt)
    # write prose and raw response
    out_path = task_dir / out_name
    raw_path = task_dir / (out_name + ".raw.json")
    out_path.write_text(text.strip() + "\n", encoding="utf-8")
    try:
        with raw_path.open("w", encoding="utf-8") as fh:
            json.dump(raw_resp.to_dict() if hasattr(raw_resp, "to_dict") else raw_resp, fh, indent=2, ensure_ascii=False)
    except Exception:
        raw_path.write_text(str(raw_resp), encoding="utf-8")
    print(f"[ok] wrote prose: {out_path}  (raw: {raw_path})")
    return out_path

def main():
    p = argparse.ArgumentParser(description="Generate prose requirements using an LLM.")
    p.add_argument("--benchmark-dir", type=Path, default=Path(__file__).resolve().parents[2] / "benchmark")
    p.add_argument("--model", type=str, default="gpt-5-mini", help="Model name to call")
    p.add_argument("--tasks", nargs="*", help="Optional list of tasks (folder names) to process")
    p.add_argument("--dry-run", action="store_true", help="Don't call the LLM; write placeholders")
    args = p.parse_args()

    client = OpenAI()

    benchmark = args.benchmark_dir
    if not benchmark.is_dir():
        raise SystemExit(f"Benchmark directory not found: {benchmark}")

    tasks = []
    if args.tasks:
        for t in args.tasks:
            td = benchmark / t
            if td.is_dir():
                tasks.append(td)
            else:
                print(f"[warn] task not found, skipping: {t}")
    else:
        tasks = [p for p in sorted(benchmark.iterdir()) if p.is_dir()]

    for td in tasks:
        try:
            process_task(client, args.model, td, dry_run=args.dry_run)
        except Exception as e:
            print(f"[error] task {td.name} failed: {e}")

if __name__ == "__main__":
    main()