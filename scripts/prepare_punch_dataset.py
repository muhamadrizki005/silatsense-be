"""Validate private clip metadata and export temporal inputs; never invent labels."""

import argparse
import json
from pathlib import Path

from app.intelligence.punch_dataset import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--data-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output sudah ada; gunakan nama eksperimen baru")
        result = prepare(args.manifest, args.data_root)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open("x", encoding="utf-8") as handle:
            json.dump(result, handle, indent=2, allow_nan=False)
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(2, str(error) + "\n")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key != "samples"}, indent=2
        )
    )
    print("Temporal dataset saved; no model has been trained.")


if __name__ == "__main__":
    main()
