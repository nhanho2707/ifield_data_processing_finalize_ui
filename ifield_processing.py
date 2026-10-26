"""Run the processing pipeline of one project.

The logic lives in app/core/pipeline.py; this file only keeps the old way of working
(edit project_name, then run this file). Equivalent command:

    python -m app run VN2024170_CONCERT_9_2024
"""
from app.cli import main

project_name = "VN2026221_IVORY"

if __name__ == "__main__":
    raise SystemExit(main(["run", project_name]))
