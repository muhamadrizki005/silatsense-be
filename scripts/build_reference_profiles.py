"""Build measured reference profiles; never consumes COCO keypoints."""

import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps
from app.core.config import settings
from app.intelligence.contracts import FEATURE_VERSION
from app.intelligence.pose.mediapipe_extractor import MediaPipePoseExtractor
from app.intelligence.preprocessing.landmarks import VisibleLandmarkPreprocessor
from app.intelligence.features.biomechanics import BiomechanicalFeatures

VARIANTS = {
    "kuda kuda belakang": "belakang",
    "kuda kuda depan": "depan",
    "kuda kuda samping": "samping",
    "kuda kuda silang belakang": "silang_belakang",
    "kuda kuda silang depan": "silang_depan",
    "kuda kuda tengah": "tengah",
    "Tangkisan3": "tangkisan3",
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--movement", choices=["kuda_kuda", "tangkisan"], required=True)
    parser.add_argument(
        "--rotate",
        type=int,
        choices=[0, 90, 180, 270],
        default=0,
        help="Explicit counter-clockwise correction after EXIF transpose",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Debug only; never register partial runs as final references",
    )
    args = parser.parse_args()
    extractor = MediaPipePoseExtractor(settings.pose_model_path)
    preprocessor, features = VisibleLandmarkPreprocessor(), BiomechanicalFeatures()
    groups, counts, seen = defaultdict(list), defaultdict(int), set()
    report = {
        "source": str(args.dataset),
        "rotation": args.rotate,
        "feature_version": FEATURE_VERSION,
        "images_seen": 0,
        "pose_valid": 0,
        "skipped": 0,
        "original_splits_used_for_accuracy": False,
    }
    try:
        for annotations_path in sorted(args.dataset.rglob("_annotations.coco.json")):
            data = json.loads(annotations_path.read_text(encoding="utf-8"))
            categories = {c["id"]: c["name"] for c in data["categories"]}
            annotations = defaultdict(list)
            for a in data["annotations"]:
                annotations[a["image_id"]].append(a)
            for entry in data["images"]:
                if args.limit and report["images_seen"] >= args.limit:
                    break
                report["images_seen"] += 1
                labels = annotations[entry["id"]]
                if (
                    len(labels) != 1
                    or categories[labels[0]["category_id"]] not in VARIANTS
                ):
                    report["skipped"] += 1
                    continue
                variant = VARIANTS[categories[labels[0]["category_id"]]]
                path = annotations_path.parent / entry["file_name"]
                if not path.resolve().is_relative_to(args.dataset.resolve()):
                    raise ValueError("Unsafe dataset filename")
                digest = hashlib.sha256(path.read_bytes()).hexdigest()
                if digest in seen:
                    continue
                seen.add(digest)
                with Image.open(path) as source:
                    image = (
                        ImageOps.exif_transpose(source)
                        .convert("RGB")
                        .rotate(args.rotate, expand=True)
                    )
                    image.thumbnail((1280, 1280))
                    pose = extractor.extract(np.asarray(image))
                normalized = preprocessor.normalize(pose) if pose else None
                if normalized is None:
                    report["skipped"] += 1
                    continue
                measured = features.extract(normalized)
                if len(measured) < 8:
                    report["skipped"] += 1
                    continue
                groups[variant].append(measured)
                counts[variant] += 1
                report["pose_valid"] += 1
                if report["images_seen"] % 100 == 0:
                    print(
                        f"Processed {report['images_seen']} images; valid {report['pose_valid']}",
                        flush=True,
                    )
    finally:
        extractor.close()
    output = Path(settings.reference_root) / args.movement
    output.mkdir(parents=True, exist_ok=True)
    for variant, rows in groups.items():
        stats = {}
        for key in sorted(set().union(*(r.keys() for r in rows))):
            values = [r[key] for r in rows if key in r]
            if len(values) < 10:
                continue
            q1, median, q3 = np.percentile(values, [25, 50, 75])
            stats[key] = {
                "median": float(median),
                "iqr": float(q3 - q1),
                "count": len(values),
            }
        if len([s for s in stats.values() if s["iqr"] > 1e-6]) < 8:
            continue
        profile = {
            "movement": args.movement,
            "variant": variant,
            "version": f"{args.movement}-{variant}-prototype-v1",
            "feature_version": FEATURE_VERSION,
            "evaluator_type": "robust-reference",
            "sample_count": len(rows),
            "feature_statistics": stats,
            "provenance": {
                **report,
                "debug_partial": bool(args.limit),
                "model_sha256": hashlib.sha256(
                    Path(settings.pose_model_path).read_bytes()
                ).hexdigest(),
            },
        }
        (output / f"{variant}.v1.json").write_text(
            json.dumps(profile, indent=2), encoding="utf-8"
        )
    report["variants"] = dict(counts)
    (output / "build-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
