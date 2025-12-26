import os
import time
import requests

SESSION_COOKIE = "53616c7465645f5f6db673d2f314e7208786a0ecc2dfeca9c43ce8f6ce43b5a1521c9e4c0c2ca59f12d27c107d9ccf0afb1c84e27c8a57f913c2793874bf2cc3"  # value of the 'session' cookie from adventofcode.com
USER_AGENT = "Capstone Project tahateke@g.harvard.edu"

BASE_URL = "https://adventofcode.com/{year}/day/{day}/input"


def fetch_input(year: int, day: int) -> str:
    url = BASE_URL.format(year=year, day=day)
    resp = requests.get(
        url,
        cookies={"session": SESSION_COOKIE},
        headers={"User-Agent": USER_AGENT},
        timeout=10,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Failed for {year}-Day{day}: HTTP {resp.status_code}")
    return resp.text


def main():
    for year in range(2015, 2025):          # 2015-2024       
        for day in range(1, 26):            # 1-25
            day_dir = os.path.join("aoc", str(year), f"day{day:02}")
            os.makedirs(day_dir, exist_ok=True)

            out_path = os.path.join(day_dir, "input.txt")
            if os.path.exists(out_path):
                print(f"Skip {year} Day {day} (already exists)")
                continue

            try:
                print(f"Fetching {year} Day {day}...")
                data = fetch_input(year, day)
                with open(out_path, "w", encoding="utf-8") as f:
                    f.write(data.rstrip("\n") + "\n")
            except Exception as e:
                print(f"Error on {year} Day {day}: {e}")


if __name__ == "__main__":
    main()
