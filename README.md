# Maestro: Harvard Capstone

This repo contains the code and artifacts for the **Maestro** capstone project, including experiment runners for LLM-based solution generation and evaluation on **Advent of Code (AoC)** datasets.

Quick links:
- Paper: [paper/MaestroAI-Capstone.pdf](paper/MaestroAI-Capstone.pdf)
- Slides: [slides/annotated-Maestro.AI_CapstonePresentationSlides.pdf](slides/annotated-Maestro.AI_CapstonePresentationSlides.pdf)

## Repo Layout

- `maestro-nano/`
	- `baseline/datasets/aoc/` — AoC problems, inputs, and baseline answers (e.g., `result1.txt`, `result2.txt`)
	- `scripts/` — experiment runners, collectors, analysis and plotting utilities
- `paper/` — capstone paper (PDF)
- `slides/` — presentation slides (PDF)

## Setup

### Prerequisites

- Python 3.10+ recommended
- An OpenAI API key in your environment

### Install Python dependencies

There is no pinned `requirements.txt` in this repo, so install the runtime dependencies used by the scripts:

```bash
pip install openai python-dotenv tqdm matplotlib numpy
```

### Configure environment

Set `OPENAI_API_KEY` (the runners use `python-dotenv`, so a local `.env` also works).

This repo also supports a dedicated Maestro path variable:

- `MAESTRO_NANO_ROOT` — absolute path to your `maestro-nano/` folder
	- If set, scripts will use it to locate datasets and write results/logs.
	- If not set, scripts fall back to auto-detecting paths relative to `maestro-nano/scripts/`.

PowerShell:
```powershell
$env:OPENAI_API_KEY = "..."
$env:MAESTRO_NANO_ROOT = "C:\\Development\\maestro-harvard-capstone\\maestro-nano"
```

bash:
```bash
export OPENAI_API_KEY="..."
export MAESTRO_NANO_ROOT="/abs/path/to/maestro-harvard-capstone/maestro-nano"
```

Optional `.env` (create at the repo root *or* inside `maestro-nano/`):

```dotenv
OPENAI_API_KEY=...
MAESTRO_NANO_ROOT=C:\\Development\\maestro-harvard-capstone\\maestro-nano
```

## Run Experiments

All commands below assume your working directory is the repo root.
If you prefer, you can also `cd maestro-nano` and run the same scripts via `python scripts/...`.

### Run end-to-end evaluation (single + multi)

Runs the AoC suite for the selected years/days and saves logs. By default it also runs collection to regenerate the live CSV summary.

```bash
python maestro-nano/scripts/run_all_e2e.py --years 2021 --models gpt-4.1-mini --clear-summary --stream-output
```

Useful flags:
- `--modes single multi` — select run modes
- `--days 1 2 3` or `--days day01 day02` — limit to specific days
- `--temperature 0.2` — sampling temperature
- `--prompt-set DEFAULT` — prompt set selection
- `--no-collect` — skip the collection step

### Repeat runs (variance / stability)

```bash
python maestro-nano/scripts/run_all_repeats.py -n 10 --year 2021 --day 16 --models gpt-4.1-nano
```

### Replay a specific command (debugging)

```bash
python maestro-nano/scripts/replay_cmds.py <INDEX> --csv <PATH_TO_FILE> --package
```

### Prompt-line analysis

```bash
python maestro-nano/scripts/analyze_prompt_lines.py --year 2021 --tag 2021_prompt-line_test --no-archive --temperature 0.1 --stream-output
```

## Results & Analysis

### Primary results CSV

The canonical “live” summary is written here:

- [maestro-nano/baseline/datasets/aoc/results_summary_live.csv](maestro-nano/baseline/datasets/aoc/results_summary_live.csv)

It is produced by:

```bash
python maestro-nano/scripts/collect_aoc_results.py
```

### Statistical summary

```bash
python maestro-nano/scripts/analyze_results.py maestro-nano/baseline/datasets/aoc/results_summary_live.csv
```

### Plotting

Year-by-year:
```bash
python maestro-nano/scripts/plot_results.py maestro-nano/baseline/datasets/aoc/results_summary_live.csv
```

Day-by-day:
```bash
python maestro-nano/scripts/plot_results.py maestro-nano/baseline/datasets/aoc/results_summary_live.csv --by-day
```

Agg-tag plots (see notes in [maestro-nano/scripts/PLOT_AGG_TAG_USAGE.md](maestro-nano/scripts/PLOT_AGG_TAG_USAGE.md)):
```bash
python maestro-nano/scripts/plot_results.py maestro-nano/baseline/datasets/aoc/results_summary_live.csv --by-agg-tag
```

## Logs

Run logs are written under:

- `maestro-nano/results/run_all_logs/`
- `maestro-nano/baseline/results/run_all_logs/` (depending on the script)

On macOS/Linux you can tail logs like:

```bash
tail -f maestro-nano/results/run_all_logs/*/*.log
```
