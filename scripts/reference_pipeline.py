"""Offline correct-Coach references: extract, prepare, fit, compare, evaluate, overlay."""

import argparse
import json
from pathlib import Path

from app.intelligence.coach_reference import compare, evaluate, fit, prepare
from scripts.movement_pipeline import read, write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    extract = commands.add_parser("extract")
    extract.add_argument("--video", type=Path, required=True)
    extract.add_argument(
        "--pose-model",
        type=Path,
        default=Path("artifacts/pose/pose_landmarker_lite.task"),
    )
    preparing = commands.add_parser("prepare")
    preparing.add_argument("--manifest", type=Path, required=True)
    preparing.add_argument("--data-root", type=Path, required=True)
    fitting = commands.add_parser("fit")
    fitting.add_argument("--dataset", type=Path, required=True)
    comparing = commands.add_parser("compare")
    comparing.add_argument("--model", type=Path, required=True)
    comparing.add_argument("--observations", type=Path, required=True)
    comparing.add_argument("--movement", required=True)
    evaluating = commands.add_parser("evaluate")
    evaluating.add_argument("--model", type=Path, required=True)
    evaluating.add_argument("--dataset", type=Path, required=True)
    evaluating.add_argument("--split", choices=("validation", "test"), required=True)
    overlay = commands.add_parser("overlay")
    overlay.add_argument("--video", type=Path, required=True)
    overlay.add_argument("--observations", type=Path, required=True)
    overlay.add_argument("--comparison", type=Path, required=True)
    for command in (extract, preparing, fitting, comparing, evaluating, overlay):
        command.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output exists; use a new run path")
        if args.command == "extract":
            from app.intelligence.movement_video import extract_video

            result = extract_video(args.video, args.pose_model, include_landmarks=True)
        elif args.command == "prepare":
            result = prepare(args.manifest, args.data_root)
        elif args.command == "fit":
            result = fit(read(args.dataset))
        elif args.command == "compare":
            result = compare(read(args.model), read(args.observations), args.movement)
        elif args.command == "evaluate":
            result = evaluate(read(args.model), read(args.dataset), args.split)
        else:
            from app.intelligence.reference_overlay import render

            result = render(
                args.video, read(args.observations), read(args.comparison), args.output
            )
        if args.command != "overlay":
            write(args.output, result)
    except (ValueError, OSError, KeyError, TypeError, ImportError) as error:
        parser.exit(2, str(error) + "\n")
    print(
        json.dumps(
            {
                "command": args.command,
                "output": str(args.output),
                "status": result.get("status"),
                "productionReady": False,
            }
        )
    )


if __name__ == "__main__":
    main()
