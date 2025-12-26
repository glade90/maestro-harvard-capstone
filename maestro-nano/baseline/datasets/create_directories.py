import os

for year in range(2015, 2025):          # 2015–2024
    for day in range(1, 26):            # 1–25
        year_path = f"aoc/{year}"
        os.makedirs(year_path, exist_ok=True)
        
        day_path = f"{year_path}/day{day:02}"
        os.makedirs(day_path, exist_ok=True)