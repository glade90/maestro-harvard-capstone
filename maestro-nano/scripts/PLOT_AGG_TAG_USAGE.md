# Plot Results by Aggregation Tag

## Overview
The `plot_results.py` script now supports grouping results by aggregation tag (`agg_tag`) on the X-axis, enabling visualization of prompt line analysis experiments.

## Usage

### Basic Command
```bash
python scripts/plot_results.py results_summary_live.csv --by-agg-tag
```

### With Custom Output Path
```bash
python scripts/plot_results.py results_summary_live.csv --by-agg-tag -o custom_chart.png
```

### Default Output Path
When using `--by-agg-tag`, the default output filename is:
- `model_comparison_chart_agg_tag.png` (saved next to the input CSV)

## Workflow Example

### 1. Run Prompt Line Analysis
```bash
python alpha/scripts/analyze_prompt_lines.py
```

This will:
- Create temporary prompt sets with individual lines removed
- Run experiments with agg_tags like: `io1`, `io2`, `code1`, `req3`, `tdd5`, etc.
- Generate `results_summary_live.csv` with agg_tag column populated

### 2. Visualize Results
```bash
python scripts/plot_results.py alpha/results/results_summary_live.csv --by-agg-tag
```

This will:
- Group results by agg_tag values
- Show success rates for single-agent vs multi-agent modes
- Display pie charts showing failure distribution per agg_tag
- Save chart as `model_comparison_chart_agg_tag.png`

## Chart Features

### Bar Chart (Top)
- X-axis: Aggregation tags (sorted alphabetically)
- Y-axis: Success rate percentage (0-100%)
- Two bars per tag:
  - Gray bar: Single-agent success rate
  - Blue bar: Multi-agent success rate
- Percentage labels on top of each bar

### Pie Charts (Bottom)
- One pie chart per aggregation tag
- Shows distribution of multi-agent outcomes:
  - SUCCESS (green)
  - FAIL-ERROR (red)
  - FAIL-INCORRECT (orange)
  - FAIL-MISSING (gray)

## Implementation Details

### Modified Functions
- `plot_from_csv()`: Added `by_agg_tag` parameter
- Category extraction: Reads `agg_tag` column from CSV when enabled
- Title generation: Shows "by Aggregation Tag" subtitle
- X-tick labels: Displays agg_tag values directly

### Data Requirements
- CSV must have `agg_tag` column
- Empty agg_tag values are filtered out
- Categories are sorted alphabetically

## Comparison with Other Modes

| Mode | X-Axis | Command |
|------|--------|---------|
| By Year | Year values | `python plot_results.py results.csv` |
| By Day | Day numbers with year | `python plot_results.py results.csv --by-day` |
| By Agg Tag | Aggregation tag values | `python plot_results.py results.csv --by-agg-tag` |

## Example Agg Tags
When running `analyze_prompt_lines.py`, typical agg_tag values include:
- `baseline`: Results with all prompt lines included
- `io1`: Results with IO contract line 1 removed
- `io2`: Results with IO contract line 2 removed
- `code1`: Results with coding prompt line 1 removed
- `req1`: Results with requirements prompt line 1 removed
- `tdd1`: Results with TDD prompt line 1 removed

This allows you to identify which prompt lines have the most impact on success rates.
