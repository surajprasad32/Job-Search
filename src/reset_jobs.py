"""One-time utility: reset processed=False on all jobs so they get re-scored."""
import json
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
import config

jobs = json.loads(config.JOBS_DATA_PATH.read_text(encoding="utf-8"))
for job in jobs.values():
    job["processed"] = False
    job["score"] = 0
config.JOBS_DATA_PATH.write_text(json.dumps(jobs, indent=2))
print(f"Reset {len(jobs)} jobs to unprocessed.")
