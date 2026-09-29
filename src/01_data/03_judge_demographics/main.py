"""
Run the judge demographics pipeline to clean FJC judge data and match to case data via judge names extracted by Gemini.
"""

import importlib
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

STEPS = [
    "02_build_judge_tables",
    "03_match_judges",
]

if __name__ == "__main__":
    for step in STEPS:
        print(f"\n{'=' * 60}\n{step}\n{'=' * 60}")
        importlib.import_module(step).main()
