
## Example Commands

### Command to run a single year: 
python %ROOT%\maestro-nano\scripts\run_all_e2e.py --years 2021 --models gpt-4.1-mini --clear-summary --stream-output

### Command example to run something 10 times 
python %ROOT%\maestro-nano\scripts\run_all_repeats.py -n 10 --year 2021 --day 16 --models gpt-4.1-nano

### replay a test:
python <ROOT>\maestro-nano\scripts\replay_cmds.py xx --package

### Prompt Line Test
python <ROOT>/maestro-nano/scripts/analyze_prompt_lines.py --year 2021 --tag 2021_prompt-line_test --no-archive --temperature 0.1 --stream-output

### plot by day 
python.exe c:/Development/python-tdd-dataset/scripts/analyze_results.py %ROOT%\maestro-nano\baseline\datasets\aoc\results_summary_live.csv --by-day

### Results: 
%ROOT%\maestro-nano\baseline\datasets\aoc\results_summary_live.csv

### Tail Logs
tail -f maestro-nano/baseline/results/run_all_logs/
