"""Export/check the public OpenAPI snapshot without connecting to any database."""

import argparse
import json
from pathlib import Path
from app.main import app


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    path = Path("docs/openapi.json")
    content = (
        json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    )
    if args.check:
        if not path.exists() or path.read_text(encoding="utf-8") != content:
            raise SystemExit(
                "OpenAPI snapshot differs; run python -m scripts.export_openapi"
            )
        print("OpenAPI snapshot matches application")
    else:
        path.write_text(content, encoding="utf-8")
        print("Exported docs/openapi.json")


if __name__ == "__main__":
    main()
