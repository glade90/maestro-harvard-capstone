import argparse
import re
import subprocess
import shutil
import tempfile
from pathlib import Path
from typing import Tuple

# Match fenced code blocks like ```python, ```py, ```python3, ``` etc.
# Allow closing fence at EOF (no trailing newline) and arbitrary language tag.
CODE_FENCE_RE = re.compile(r"```(?:[^\n]*)\n(.*?)(?:\n```|```$)", re.S | re.I)


def extract_blocks(md_text: str):
    blocks = CODE_FENCE_RE.findall(md_text)
    if blocks:
        return blocks
    # fallback: if there are any triple-backticks at all, extract between them
    if "```" in md_text:
        parts = md_text.split("```")
        # code appears in odd-indexed parts
        blocks = [parts[i] for i in range(1, len(parts), 2)]
        return blocks
    return []


def split_impl_and_tests(blocks):
    impl_parts = []
    test_parts = []
    for b in blocks:
        lowered = b.lower()
        # broaden heuristic for test detection
        is_test = False
        if re.search(r"\bdef\s+test_", b):
            is_test = True
        if re.search(r"\bassert\b", b):
            # many tests use assert; implementations sometimes use asserts too,
            # but treat blocks with multiple asserts or with pytest/unittest imports as tests.
            if re.search(r"\bpytest\b", lowered) or re.search(r"\bimport unittest\b", lowered) or b.count("assert") > 1:
                is_test = True
        if re.search(r"\bself\.assert", b):
            is_test = True
        if re.search(r"\bfrom\s+pytest\b", lowered):
            is_test = True

        if is_test:
            test_parts.append(b)
        else:
            impl_parts.append(b)
    return impl_parts, test_parts


def run_pytests(workdir: Path) -> Tuple[int, int]:
    """Run pytest in workdir, return (passed, total)."""
    # Run pytest capturing output
    proc = subprocess.run(
        ["pytest", "-q", str(workdir)],
        capture_output=True,
        text=True,
    )
    out = proc.stdout + proc.stderr

    # Try to parse summary lines like "== 3 passed, 1 failed in 0.12s =="
    m = re.search(r"=+\s*([\d ,a-zA-Z]+)\s*=+", out)
    passed = 0
    total = 0
    if m:
        summary = m.group(1)
        # find counts
        p = re.search(r"(\d+)\s+passed", summary)
        f = re.search(r"(\d+)\s+failed", summary)
        s = re.search(r"(\d+)\s+skipped", summary)
        x = re.search(r"(\d+)\s+xfailed", summary)
        passed = int(p.group(1)) if p else 0
        failed = int(f.group(1)) if f else 0
        skipped = int(s.group(1)) if s else 0
        xfailed = int(x.group(1)) if x else 0
        total = passed + failed + skipped + xfailed
    else:
        # Fallback: treat nonzero exit as failure of unknown count
        if proc.returncode == 0:
            # nothing in summary but success -> assume at least 1 passed
            passed = 1
            total = 1
        else:
            passed = 0
            total = 0
    return passed, total


def evaluate_task(task_dir: Path, results_dir: Path):
    # find latest result file(s) for this task
    md_files = sorted(results_dir.glob(f"{task_dir.name}/*.md"))
    if not md_files:
        print(f"  No result .md files for {task_dir.name}")
        return None

    # pick most recent
    md_path = md_files[-1]
    md = md_path.read_text(encoding="utf-8")
    blocks = extract_blocks(md)
    impl_parts, test_parts = split_impl_and_tests(blocks)
    # debug: show what we found
    if not blocks:
        print(f"  [debug] no fenced code blocks found in {md_path.name}")
    else:
        print(f"  [debug] found {len(blocks)} code block(s): impl_parts={len(impl_parts)} test_parts={len(test_parts)}")

    with tempfile.TemporaryDirectory() as td:
        w = Path(td)
        # write implementation
        if impl_parts:
            impl_file = w / "implementation.py"
            impl_file.write_text("\n\n".join(impl_parts), encoding="utf-8")
        else:
            # if no impl, maybe benchmark provides reference implementation - we'll still run tests (they should import)
            impl_file = None

        # write generated tests (TDD)
        if test_parts:
            tdd_file = w / "test_generated.py"
            tdd_file.write_text("\n\n".join(test_parts), encoding="utf-8")
        else:
            tdd_file = None

        # 1) run generated tests (if any)
        tdd_passed, tdd_total = (0, 0)
        if tdd_file:
            tdd_passed, tdd_total = run_pytests(w)

        # 2) run eval_tests from benchmark/task_dir / eval_tests
        eval_passed, eval_total = (0, 0)
        eval_tests_dir = task_dir / "eval_tests"
        if eval_tests_dir.is_dir():
            # copy all eval tests into temp dir
            for f in eval_tests_dir.glob("*.py"):
                shutil.copy(f, w / f.name)
            # if implementation exists, ensure it's importable as module
            if impl_file:
                # nothing to do; implementation.py sits in test path
                pass
            eval_passed, eval_total = run_pytests(w)

        # 3) run tdd_tests (if present in benchmark/task/tdd_tests) - this is the dataset's own TDD suite
        tddset_passed, tddset_total = (0, 0)
        tddset_dir = task_dir / "tdd_tests"
        if tddset_dir.is_dir():
            for f in tddset_dir.glob("*.py"):
                shutil.copy(f, w / f.name)
            # ensure implementation is present if extracted above; else tests may import reference impl
            tddset_passed, tddset_total = run_pytests(w)

        return {
            "task": task_dir.name,
            "tdd_generated": (tdd_passed, tdd_total),
            "eval_tests": (eval_passed, eval_total),
            "tdd_dataset": (tddset_passed, tddset_total),
            "result_file": md_path,
        }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo-root", type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument("--results-dir", type=Path, default=None)
    args = parser.parse_args()

    repo = args.repo_root
    benchmark = repo / "benchmark"
    # default results dir mirrors earlier script
    results_dir = args.results_dir or (repo / "vanilla" / "results")

    tasks = [p for p in benchmark.iterdir() if p.is_dir()]
    summary = []
    for t in sorted(tasks):
        print(f"Evaluating: {t.name}")
        r = evaluate_task(t, results_dir)
        if r:
            summary.append(r)

    # Print summary
    total_tdd_passed = total_tdd = 0
    total_eval_passed = total_eval = 0
    total_tddset_passed = total_tddset = 0
    print("\nSummary per-task:")
    for r in summary:
        tp, tt = r["tdd_generated"]
        ep, et = r["eval_tests"]
        sp, st = r["tdd_dataset"]
        print(f"- {r['task']}: generated tests passed {tp}/{tt}, eval_tests passed {ep}/{et}, tdd_dataset passed {sp}/{st}")
        total_tdd_passed += tp; total_tdd += tt
        total_eval_passed += ep; total_eval += et
        total_tddset_passed += sp; total_tddset += st

    def pct(p, t):
        return f"{p}/{t} ({100.0*p/t:.1f}%)" if t else "N/A"

    print("\nOverall rates:")
    print("Generated TDD tests:", pct(total_tdd_passed, total_tdd))
    print("Eval tests:", pct(total_eval_passed, total_eval))
    print("Dataset TDD tests:", pct(total_tddset_passed, total_tddset))

    # --- write a single CSV summary into the results directory ---
    import csv

    out_csv = results_dir / "evaluation_summary.csv"
    results_dir.mkdir(parents=True, exist_ok=True)

    headers = [
        "task",
        "generated_passed", "generated_total", "generated_pct",
        "eval_passed", "eval_total", "eval_pct",
        "tdd_dataset_passed", "tdd_dataset_total", "tdd_dataset_pct",
        "result_file"
    ]

    def pct_val(p, t):
        return round(100.0 * p / t, 1) if t else None

    with out_csv.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(headers)
        for r in summary:
            tp, tt = r["tdd_generated"]
            ep, et = r["eval_tests"]
            sp, st = r["tdd_dataset"]
            writer.writerow([
                r["task"],
                tp, tt, pct_val(tp, tt),
                ep, et, pct_val(ep, et),
                sp, st, pct_val(sp, st),
                str(r["result_file"])
            ])

    print(f"\nSaved CSV summary: {out_csv}")


if __name__ == "__main__":
    main()