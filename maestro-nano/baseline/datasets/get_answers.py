#!/usr/bin/env python3
import requests
from pathlib import Path

BASE_URL = "https://advent.fly.dev"

def main():
    for year in range(2015, 2025):
        for day in range(1, 26):
            day_dir = Path("aoc") / str(year) / f"day{day:02d}"
            input_path = day_dir / "input.txt"
            if not input_path.exists():
                print(f"[skip] {input_path} (missing)")
                continue

            data = input_path.read_text(encoding="utf-8")
            url = f"{BASE_URL}/solve/{year}/{day}/1"  # change /1 -> /2 for part 2
            try:
                resp = requests.post(
                    url,
                    headers={
                        "accept": "text/plain",
                        "content-type": "text/plain",
                    },
                    data=data,
                    timeout=30,
                )
                resp.raise_for_status()
            except requests.RequestException as e:
                print(f"[error] {year} day {day:02d}: {e}")
                continue

            answer = resp.text.strip()
            output_path = day_dir / "results1.txt"
            output_path.write_text(answer + "\n", encoding="utf-8")
            print(f"[ok] {year} day {day:02d} -> {output_path} = {answer}")

if __name__ == "__main__":
    main()
