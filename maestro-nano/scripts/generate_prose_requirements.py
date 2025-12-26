
##!/usr/bin/env python
import argparse
import re
from pathlib import Path
from datetime import datetime

def md_to_prose(md: str) -> str:
    """
    Convert a markdown requirements file into paragraph-style prose.
    - strips headings and list markers
    - preserves paragraph breaks (blank lines)
    - removes inline markup (backticks, links, emphasis)
    """
    # normalize line endings
    lines = md.replace("\r\n", "\n").splitlines()
    paragraphs = []
    buf = []

    def flush_buf():
        if not buf:
            return
        s = " ".join(p.strip() for p in buf)
        s = re.sub(r"\s+", " ", s).strip()
        if s and s[-1] not in ".!?:":
            s += "."
        # Capitalize first character if lowercase
        if s and s[0].islower():
            s = s[0].upper() + s[1:]
        paragraphs.append(s)
        buf.clear()

    for line in lines:
        s = line.strip()
        # skip fenced code blocks entirely
        if s.startswith("```"):
            # consume until closing fence
            # find next fence in remaining lines
            # (simple approach: skip current line and continue; closing handled by check)
            continue
        # treat heading lines as regular content but remove markdown markers
        s = re.sub(r"^#{1,6}\s*", "", s)
        # remove list markers (dash/star/number)
        s = re.sub(r"^(\-|\*|\+)\s+", "", s)
        s = re.sub(r"^\d+\.\s+", "", s)
        # remove inline code/backticks
        s = s.replace("`", "")
        # replace markdown links [text](url) -> text
        s = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", s)
        # remove emphasis markers
        s = s.replace("**", "").replace("*", "").replace("__", "").replace("_", "")
        # if blank line -> paragraph break
        if s == "":
            flush_buf()
            continue
        # append line to buffer
        buf.append(s)
    flush_buf()
    return "\n\n".join(paragraphs) if paragraphs else ""

def generate_prose_for_task(task_dir: Path, out_name: str = "requirements-nl-prose.md") -> Path:
    req_md = task_dir / "requirements-nl.md"
    tech_md = task_dir / "requirements-nl-tech.md"
    out_path = task_dir / out_name

    if not req_md.exists():
        print(f"Skipping {task_dir.name}: requirements-nl.md not found")
        return None

    raw = req_md.read_text(encoding="utf-8")
    prose = md_to_prose(raw)
    if not prose:
        prose = "No prose could be extracted from requirements-nl.md."

    # prepare technical requirements content (verbatim)
    if tech_md.exists():
        tech_text = tech_md.read_text(encoding="utf-8").strip()
        tech_section = tech_text
    else:
        tech_section = "_No technical requirements file (requirements-nl-tech.md) found._"

    header = f"# {task_dir.name} — Requirements (Prose)\n\n"
    meta = f"_Generated: {datetime.utcnow().isoformat()}Z_\n\n"
    technical_header = "\n\n## Technical Requirements\n\n"

    content = header + meta + prose + technical_header + tech_section + "\n"
    out_path.write_text(content, encoding="utf-8")
    print(f"Wrote: {out_path}")
    return out_path

def main():
    parser = argparse.ArgumentParser(description="Generate prose versions of requirements-nl.md for each benchmark task.")
    parser.add_argument("--benchmark-dir", type=Path, default=Path(__file__).resolve().parents[2] / "benchmark",
                        help="Path to benchmark directory (default: repo benchmark/)")
    parser.add_argument("--tasks", nargs="*", help="Optional list of task names to process (default: all folders).")
    args = parser.parse_args()

    benchmark = args.benchmark_dir
    if not benchmark.is_dir():
        raise SystemExit(f"Benchmark directory not found: {benchmark}")

    tasks = []
    if args.tasks:
        for t in args.tasks:
            p = benchmark / t
            if p.is_dir():
                tasks.append(p)
            else:
                print(f"Task not found, skipping: {t}")
    else:
        tasks = [p for p in sorted(benchmark.iterdir()) if p.is_dir()]

    for t in tasks:
        generate_prose_for_task(t)

if __name__ == "__main__":
    main()