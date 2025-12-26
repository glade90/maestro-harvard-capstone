#!/usr/bin/env python3
"""
Analyze the effect of each prompt line by systematically removing them.

This script:
1. Iterates through the DEFAULT prompt set
2. For each numbered line in each prompt dictionary (io_contract, coding_prompt, requirements_prompt, tdd_prompt):
   - Creates a new temporary prompt set with that line removed
   - Generates an agg_tag (e.g., "io1", "code3", "req2", "tdd5")
   - Calls run_all_e2e.py with the modified prompt set and agg_tag
3. First run clears results, subsequent runs append with agg_tag
"""
import argparse
import subprocess
import sys
from pathlib import Path
from typing import Dict
import importlib.util

def load_prompt_sets_module():
    """Dynamically load prompt_sets module to access DEFAULT."""
    script_dir = Path(__file__).resolve().parent
    prompt_sets_path = script_dir / "prompt_sets.py"
    
    spec = importlib.util.spec_from_file_location("prompt_sets", prompt_sets_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

def create_prompt_set_with_removed_line(original_prompt_set, dict_name: str, key_to_remove):
    """Create a new PromptSet with one line removed from specified dictionary."""
    # Get the original dictionaries
    io_contract = dict(original_prompt_set.io_contract)
    coding_prompt = dict(original_prompt_set.coding_prompt)
    requirements_prompt = dict(original_prompt_set.requirements_prompt)
    tdd_prompt = dict(original_prompt_set.tdd_prompt)
    
    # Remove the specified key from the appropriate dictionary (only if it's numeric)
    if not isinstance(key_to_remove, int):
        raise ValueError(f"key_to_remove must be an int, got {type(key_to_remove)}")
    
    if dict_name == "io_contract" and key_to_remove in io_contract:
        del io_contract[key_to_remove]
    elif dict_name == "coding_prompt" and key_to_remove in coding_prompt:
        del coding_prompt[key_to_remove]
    elif dict_name == "requirements_prompt" and key_to_remove in requirements_prompt:
        del requirements_prompt[key_to_remove]
    elif dict_name == "tdd_prompt" and key_to_remove in tdd_prompt:
        del tdd_prompt[key_to_remove]
    
    # Create new PromptSet
    prompt_sets = load_prompt_sets_module()
    return prompt_sets.PromptSet(
        name=f"REMOVED_{dict_name}_{key_to_remove}",
        io_contract=io_contract,
        coding_prompt=coding_prompt,
        requirements_prompt=requirements_prompt,
        tdd_prompt=tdd_prompt
    )

def save_temp_prompt_set(prompt_set, temp_name: str):
    """Save a temporary prompt set to prompt_sets.py by adding it to the enum."""
    script_dir = Path(__file__).resolve().parent
    prompt_sets_path = script_dir / "prompt_sets.py"
    
    # First, restore to clean state
    restore_prompt_sets()
    
    # Read the current file
    content = prompt_sets_path.read_text(encoding="utf-8")
    
    # Find where to insert the new prompt set (before class PromptSetEnum)
    enum_pos = content.find("class PromptSetEnum(Enum):")
    if enum_pos == -1:
        raise RuntimeError("Could not find PromptSetEnum in prompt_sets.py")
    
    # Create the new prompt set definition
    new_prompt_def = f"\n# Temporary prompt set for analysis\n{temp_name} = PromptSet(\n"
    new_prompt_def += f'    name="{temp_name}",\n'
    new_prompt_def += f"    io_contract={repr(prompt_set.io_contract)},\n"
    new_prompt_def += f"    coding_prompt={repr(prompt_set.coding_prompt)},\n"
    new_prompt_def += f"    requirements_prompt={repr(prompt_set.requirements_prompt)},\n"
    new_prompt_def += f"    tdd_prompt={repr(prompt_set.tdd_prompt)}\n"
    new_prompt_def += ")\n\n"
    
    # Insert before PromptSetEnum
    new_content = content[:enum_pos] + new_prompt_def + content[enum_pos:]
    
    # Find the enum class and add the new member at the end (before the closing of the class)
    # Look for the line with "DEFAULT = DEFAULT"
    default_line_pos = new_content.find("    DEFAULT = DEFAULT", enum_pos)
    if default_line_pos == -1:
        raise RuntimeError("Could not find DEFAULT = DEFAULT in PromptSetEnum")
    
    # Find the end of that line
    default_line_end = new_content.find("\n", default_line_pos)
    
    # Add new enum member after DEFAULT
    new_enum_member = f"\n    {temp_name} = {temp_name}"
    new_content = new_content[:default_line_end] + new_enum_member + new_content[default_line_end:]
    
    # Write back
    prompt_sets_path.write_text(new_content, encoding="utf-8")

def restore_prompt_sets():
    """Restore prompt_sets.py to original state by removing temporary entries."""
    script_dir = Path(__file__).resolve().parent
    prompt_sets_path = script_dir / "prompt_sets.py"
    
    if not prompt_sets_path.exists():
        return
    
    content = prompt_sets_path.read_text(encoding="utf-8")
    
    # Check if there's anything to clean up
    if "# Temporary prompt set for analysis" not in content:
        return
    
    # Remove everything between "# Temporary prompt set" and "class PromptSetEnum"
    temp_start = content.find("# Temporary prompt set for analysis")
    if temp_start != -1:
        # Find the newline before the comment
        if temp_start > 0 and content[temp_start-1] == '\n':
            temp_start -= 1
        
        enum_start = content.find("class PromptSetEnum(Enum):", temp_start)
        if enum_start != -1:
            content = content[:temp_start] + content[enum_start:]
    
    # Remove any REMOVED_* entries from the enum (lines that start with "    REMOVED_")
    lines = content.split("\n")
    filtered_lines = []
    for line in lines:
        # Check if line is an enum member starting with REMOVED_
        stripped = line.strip()
        if stripped.startswith("REMOVED_") and " = " in stripped:
            continue  # Skip this line
        filtered_lines.append(line)
    
    content = "\n".join(filtered_lines)
    
    prompt_sets_path.write_text(content, encoding="utf-8")

def run_experiment(agg_tag: str, prompt_set_name: str, year: str, temperature: float, tag: str, 
                   models: list, modes: list, days: list, clear_summary: bool = False, no_archive: bool = True,
                   stream_output: bool = False):
    """Run run_all_e2e.py with specified parameters."""
    script_dir = Path(__file__).resolve().parent
    run_all_script = script_dir / "run_all_e2e.py"
    
    cmd = [
        sys.executable, str(run_all_script),
        "--years", year,
        "--temperature", str(temperature),
        "--tag", tag,
        "--prompt-set", prompt_set_name,
        "--no-push",
    ]
    
    if no_archive:
        cmd.append("--no-archive")
    
    if stream_output:
        cmd.append("--stream-output")
    
    if models:
        cmd.extend(["--models"] + models)
    if modes:
        cmd.extend(["--modes"] + modes)
    if days:
        cmd.extend(["--days"] + days)
    
    if clear_summary:
        cmd.append("--clear-summary")
    else:
        # Only use agg-tag if not clearing summary
        if agg_tag:
            cmd.extend(["--agg-tag", agg_tag])
    
    print(f"\n[run] {' '.join(cmd)}")
    result = subprocess.run(cmd)
    return result.returncode

def main():
    p = argparse.ArgumentParser(description="Analyze prompt line effects by systematic removal")
    p.add_argument("--year", type=str, required=True, help="Single year to test (e.g., 2021)")
    p.add_argument("--tag", type=str, required=True, help="Tag for this experiment run")
    p.add_argument("--temperature", "-t", type=float, default=1.0, help="Temperature for LLM sampling (default: 1.0)")
    p.add_argument("--models", nargs="+", default=None, help="Models to test (default: from run_all_e2e.py defaults)")
    p.add_argument("--modes", nargs="+", default=["multi"], help="Modes to test (default: multi only)")
    p.add_argument("--days", nargs="+", default=None, help="Days to test (default: all days)")
    p.add_argument("--skip-baseline", action="store_true", help="Skip baseline run (assume results already cleared)")
    p.add_argument("--limit", type=int, default=None, help="Limit number of prompt line experiments to run (for testing)")
    p.add_argument("--no-archive", action="store_true", help="Do not run archive script at the end of all experiments")
    p.add_argument("--stream-output", action="store_true", help="Stream output to console during runs")
    args = p.parse_args()
    
    # Load the DEFAULT prompt set
    prompt_sets = load_prompt_sets_module()
    default_prompt = prompt_sets.DEFAULT
    
    # Define short names for each dictionary
    dict_mappings = {
        "io_contract": "io",
        "coding_prompt": "code",
        "requirements_prompt": "req",
        "tdd_prompt": "tdd"
    }
    
    experiments = []
    
    # Collect all numbered keys from each dictionary
    for dict_name, short_name in dict_mappings.items():
        prompt_dict = getattr(default_prompt, dict_name)
        # Filter to only numeric keys, then sort
        numeric_keys = [k for k in prompt_dict.keys() if isinstance(k, int)]
        for key in sorted(numeric_keys):
            agg_tag = f"{short_name}{key}"
            experiments.append((dict_name, key, agg_tag))
    
    # Apply limit if specified
    if args.limit and args.limit > 0:
        experiments = experiments[:args.limit]
        print(f"[info] Limited to first {len(experiments)} experiments (--limit {args.limit})")
    
    print(f"[info] Found {len(experiments)} prompt lines to analyze")
    print(f"[info] Experiments: {', '.join([exp[2] for exp in experiments])}")
    
    # Step 1: Run baseline (clear results, no agg-tag, use DEFAULT prompt set)
    if not args.skip_baseline:
        print("\n" + "="*80)
        print("BASELINE RUN - Clearing results and establishing baseline")
        print("="*80)
        returncode = run_experiment(
            agg_tag="",
            prompt_set_name="DEFAULT",
            year=args.year,
            temperature=args.temperature,
            tag=args.tag,
            models=args.models,
            modes=args.modes,
            days=args.days,
            clear_summary=True,
            no_archive=True,  # Always skip archive during experiments
            stream_output=args.stream_output
        )
        if returncode != 0:
            print(f"[error] Baseline run failed with return code {returncode}")
            return
    else:
        print("[info] Skipping baseline run (--skip-baseline)")
    
    # Step 2: Run experiments with each line removed
    for i, (dict_name, key, agg_tag) in enumerate(experiments, 1):
        print("\n" + "="*80)
        print(f"EXPERIMENT {i}/{len(experiments)}: Removing {dict_name}[{key}] - agg_tag={agg_tag}")
        print("="*80)
        
        try:
            # Create modified prompt set
            modified_prompt = create_prompt_set_with_removed_line(default_prompt, dict_name, key)
            temp_name = f"REMOVED_{dict_name}_{key}"
            
            # Save temporary prompt set
            save_temp_prompt_set(modified_prompt, temp_name)
            
            # Run experiment
            returncode = run_experiment(
                agg_tag=agg_tag,
                prompt_set_name=temp_name,
                year=args.year,
                temperature=args.temperature,
                tag=args.tag,
                models=args.models,
                modes=args.modes,
                days=args.days,
                clear_summary=False,
                no_archive=True,  # Always skip archive during experiments
                stream_output=args.stream_output
            )
            
            if returncode != 0:
                print(f"[warn] Experiment {agg_tag} failed with return code {returncode}")
            
        finally:
            # Restore prompt_sets.py after each experiment
            restore_prompt_sets()
    
    print("\n" + "="*80)
    print("ALL EXPERIMENTS COMPLETED")
    print("="*80)
    print(f"Results are in the CSV with agg_tag values: {', '.join([exp[2] for exp in experiments])}")
    
    # Generate agg_tag plot at the end
    print("\n" + "="*80)
    print("GENERATING AGG_TAG PLOT")
    print("="*80)
    try:
        script_dir = Path(__file__).resolve().parent
        plot_script = script_dir.parent.parent / "scripts" / "plot_results.py"
        results_csv = script_dir.parent / "datasets" / "aoc" / "results_summary_live.csv"
        output_png = results_csv.parent / "model_comparison_chart_live.png"
        if plot_script.exists() and results_csv.exists():
            plot_cmd = [sys.executable, str(plot_script), str(results_csv), "--by-agg-tag", "-o", str(output_png)]
            print(f"[run] {' '.join(plot_cmd)}")
            result = subprocess.run(plot_cmd, capture_output=True, text=True, timeout=60)
            if result.returncode == 0:
                print(result.stdout)
            else:
                print(f"[warn] plot generation returned non-zero exit code: {result.returncode}")
                if result.stderr:
                    print(result.stderr)
        else:
            if not plot_script.exists():
                print(f"[warn] plot script not found: {plot_script}")
            if not results_csv.exists():
                print(f"[warn] results CSV not found: {results_csv}")
    except Exception as e:
        print(f"[warn] could not generate plot: {e}")
    
    # Run archive script at the end if not disabled
    if not args.no_archive:
        print("\n" + "="*80)
        print("ARCHIVING RESULTS")
        print("="*80)
        try:
            script_dir = Path(__file__).resolve().parent
            archive_script = script_dir / "archive_results.py"
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

if __name__ == "__main__":
    main()
