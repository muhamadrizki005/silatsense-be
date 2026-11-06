"""Offline CLI: extract, prepare, train and predict twelve movement classes."""

import argparse
import json
from pathlib import Path

from app.intelligence.movement_dataset import prepare
from app.intelligence.movement_training import predict, train


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, result):
    content = json.dumps(result, indent=2, allow_nan=False)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        handle.write(content)


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
    extract.add_argument("--sample-fps", type=float, default=15)
    extract.add_argument("--visibility", type=float, default=0.5)
    prepare_parser = commands.add_parser("prepare")
    prepare_parser.add_argument("--manifest", type=Path, required=True)
    prepare_parser.add_argument("--data-root", type=Path, required=True)
    training = commands.add_parser("train")
    training.add_argument("--dataset", type=Path, required=True)
    inference = commands.add_parser("predict")
    inference.add_argument("--model", type=Path, required=True)
    inference.add_argument("--observations", type=Path, required=True)
    for command in (extract, prepare_parser, training, inference):
        command.add_argument(
            "--output",
            type=Path,
            required=True,
            help="New private .cache/... JSON file",
        )
    args = parser.parse_args()
    try:
        if args.output.exists():
            raise ValueError("Output exists; use a new run path")
        if args.command == "extract":
            from app.intelligence.movement_video import extract_video

            result = extract_video(
                args.video, args.pose_model, args.sample_fps, args.visibility
            )
        elif args.command == "prepare":
            result = prepare(args.manifest, args.data_root)
        elif args.command == "train":
            result = train(read(args.dataset))
        else:
            result = predict(read(args.model), read(args.observations))
        write(args.output, result)
    except (ValueError, OSError, KeyError, TypeError, ImportError) as error:
        parser.exit(2, str(error) + "\n")
    print(
        json.dumps(
            {
                "command": args.command,
                "output": str(args.output),
                "evaluations": result.get("evaluations"),
                "qualityAssessment": None,
            }
        )
    )


if __name__ == "__main__":
    main()
