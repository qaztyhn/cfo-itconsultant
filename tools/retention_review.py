"""D5 non-PII synthetic retention metadata review. No database access or deletion command."""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app.core import clock
from app.jobs.retention_policy import ReviewInput, summarize


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", required=True, type=Path)
    args = parser.parse_args()
    try:
        clock.init_from_settings(os.environ.get("APP_NOW"))
        data = ReviewInput.model_validate_json(args.metadata.read_bytes())
        result = summarize(data, now=clock.now())
    except (ValueError, KeyError, OSError):
        print(
            "Retention review failed; check synthetic metadata schema, timestamps and timezone."
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
