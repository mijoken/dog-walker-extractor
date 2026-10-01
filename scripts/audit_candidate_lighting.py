from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import cv2
import numpy as np


HUMAN_LABELS = {
    1: {
        "dog_walker": True,
        "passage": "A",
        "note": "Dog walker enters from right edge; rear view.",
    },
    2: {
        "dog_walker": True,
        "passage": "B",
        "note": "Distant dog walker; dark dog difficult to see.",
    },
    3: {
        "dog_walker": True,
        "passage": "B",
        "note": "Same dog walker as candidate 002, closer to camera.",
    },
    4: {
        "dog_walker": False,
        "passage": None,
        "note": "Fluttering/frilled lower clothing resembles dog.",
    },
    5: {
        "dog_walker": True,
        "passage": "C",
        "note": "Rear-view dog walker enters close from left edge.",
    },
    6: {
        "dog_walker": True,
        "passage": "C",
        "note": "Same dog walker as candidate 005.",
    },
    7: {
        "dog_walker": True,
        "passage": "C",
        "note": "Same dog walker as 005/006, farther from camera.",
    },
    8: {
        "dog_walker": False,
        "passage": None,
        "note": "Brown handbag lifted/carried; no dog confirmed.",
    },
    9: {
        "dog_walker": False,
        "passage": None,
        "note": "Runner only; no dog confirmed.",
    },
    10: {
        "dog_walker": True,
        "passage": "D",
        "note": "Person walking two dogs.",
    },
    11: {
        "dog_walker": False,
        "passage": None,
        "note": "Person pulling wheeled suitcase; visually dog-like.",
    },
    12: {
        "dog_walker": False,
        "passage": None,
        "note": "No dog confirmed; false proposal source unclear.",
    },
    13: {
        "dog_walker": False,
        "passage": None,
        "note": "No dog confirmed; false proposal source unclear.",
    },
    14: {
        "dog_walker": False,
        "passage": None,
        "note": "Handbag can superficially resemble dog walking.",
    },
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def frame_lighting(frame: np.ndarray):
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    mean = float(np.mean(gray))
    median = float(np.median(gray))
    p10 = float(np.percentile(gray, 10))
    p90 = float(np.percentile(gray, 90))
    contrast = p90 - p10

    dark_ratio_32 = float(np.mean(gray < 32))
    dark_ratio_64 = float(np.mean(gray < 64))
    bright_ratio_192 = float(np.mean(gray > 192))

    return {
        "mean": mean,
        "median": median,
        "p10": p10,
        "p90": p90,
        "contrast": contrast,
        "dark_ratio_32": dark_ratio_32,
        "dark_ratio_64": dark_ratio_64,
        "bright_ratio_192": bright_ratio_192,
    }


def audit_clip(path: Path, sample_stride: int = 15):
    cap = cv2.VideoCapture(str(path))

    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video: {path}")

    values = []
    frame_index = 0

    while True:
        ok, frame = cap.read()

        if not ok:
            break

        if frame_index % sample_stride == 0:
            values.append(frame_lighting(frame))

        frame_index += 1

    cap.release()

    if not values:
        raise RuntimeError(f"No sampled frames: {path}")

    result = {
        "sampled_frames": len(values),
    }

    for key in values[0]:
        arr = np.asarray(
            [row[key] for row in values],
            dtype=np.float64,
        )

        result[f"{key}_mean"] = float(np.mean(arr))
        result[f"{key}_median"] = float(np.median(arr))
        result[f"{key}_min"] = float(np.min(arr))
        result[f"{key}_max"] = float(np.max(arr))

    return result


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        required=True,
    )

    parser.add_argument(
        "--output",
        required=True,
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()
    output = Path(args.output).resolve()

    precision = load_json(
        root / "precision_summary.json"
    )

    audit = load_json(
        root / "track_quality_audit.json"
    )

    baseline = load_json(
        root / "dog_walker_events_v0.1_frozen.json"
    )

    experiment = load_json(
        root / "dog_walker_events_v0.2_exp_A_frozen.json"
    )

    baseline_candidates = {
        int(str(event["candidate"]).split("_")[-1])
        for event in baseline.get("events", [])
    }

    experiment_candidates = {
        int(str(event["candidate"]).split("_")[-1])
        for event in experiment.get("events", [])
    }

    candidate_info = {}

    for item in precision["candidates"]:
        idx = int(item["candidate_index"])
        candidate_info[idx] = item

    rows = []

    for idx in sorted(candidate_info):
        name = f"candidate_{idx:03d}"

        clip = (
            root
            / name
            / "source_clip.mp4"
        )

        lighting = audit_clip(
            clip,
            sample_stride=15,
        )

        dog_tracks = (
            audit.get(name, {})
            .get("dog_tracks", [])
        )

        if dog_tracks:
            longest_dog_span = max(
                float(x.get("span_sec", 0.0))
                for x in dog_tracks
            )

            max_dog_frames = max(
                int(x.get("detection_frames", 0))
                for x in dog_tracks
            )

            best_dog_conf = max(
                float(x.get("mean_confidence", 0.0))
                for x in dog_tracks
            )
        else:
            longest_dog_span = 0.0
            max_dog_frames = 0
            best_dog_conf = 0.0

        label = HUMAN_LABELS[idx]

        source_start = float(
            candidate_info[idx]["source_start_sec"]
        )

        source_end = float(
            candidate_info[idx]["source_end_sec"]
        )

        row = {
            "candidate_index": idx,
            "candidate": name,
            "source_start_sec": source_start,
            "source_end_sec": source_end,
            "human_dog_walker": label["dog_walker"],
            "human_passage": label["passage"],
            "human_note": label["note"],
            "v0_1_event": idx in baseline_candidates,
            "v0_2_exp_A_event": idx in experiment_candidates,
            "dog_track_count": len(dog_tracks),
            "longest_dog_span_sec": longest_dog_span,
            "max_dog_frames": max_dog_frames,
            "best_dog_mean_conf": best_dog_conf,
            **lighting,
        }

        rows.append(row)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_path = output.with_suffix(".json")
    csv_path = output.with_suffix(".csv")

    json_path.write_text(
        json.dumps(
            {
                "description": (
                    "Blind Validation 004 lighting and "
                    "tracking-quality audit. Human labels "
                    "were added only after v0.1 and "
                    "v0.2-exp-A predictions were frozen."
                ),
                "candidate_count": len(rows),
                "rows": rows,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    with csv_path.open(
        "w",
        newline="",
        encoding="utf-8-sig",
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=list(rows[0].keys()),
        )

        writer.writeheader()
        writer.writerows(rows)

    print("")
    print("=" * 118)
    print("VALIDATION 004 - LIGHTING / DETECTION AUDIT")
    print("=" * 118)

    print(
        f"{'ID':>3} "
        f"{'Truth':>6} "
        f"{'Pass':>5} "
        f"{'v0.1':>5} "
        f"{'v0.2A':>5} "
        f"{'Lum':>7} "
        f"{'Med':>7} "
        f"{'Dark64':>8} "
        f"{'DogSec':>7} "
        f"{'Frames':>7} "
        f"{'DogConf':>8}"
    )

    for row in rows:
        print(
            f"{row['candidate_index']:>3} "
            f"{str(row['human_dog_walker']):>6} "
            f"{str(row['human_passage'] or '-'):>5} "
            f"{str(row['v0_1_event']):>5} "
            f"{str(row['v0_2_exp_A_event']):>5} "
            f"{row['mean_mean']:7.2f} "
            f"{row['median_mean']:7.2f} "
            f"{row['dark_ratio_64_mean']:8.3f} "
            f"{row['longest_dog_span_sec']:7.2f} "
            f"{row['max_dog_frames']:7d} "
            f"{row['best_dog_mean_conf']:8.3f}"
        )

    positives = [
        x for x in rows
        if x["human_dog_walker"]
    ]

    negatives = [
        x for x in rows
        if not x["human_dog_walker"]
    ]

    print("")
    print("HUMAN REVIEW SUMMARY")
    print(
        "positive candidate windows :",
        len(positives),
    )
    print(
        "negative candidate windows :",
        len(negatives),
    )

    passages = sorted({
        x["human_passage"]
        for x in positives
        if x["human_passage"]
    })

    print(
        "human dog-walker passages  :",
        len(passages),
        passages,
    )

    print("")
    print(f"JSON: {json_path}")
    print(f"CSV : {csv_path}")
    print("")
    print("VALIDATION004_LIGHTING_AUDIT_OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

