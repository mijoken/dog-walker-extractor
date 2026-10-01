from __future__ import annotations

import csv
import json
from collections import defaultdict
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "output" / "precision_candidates"


def analyze_csv(path: Path) -> dict:
    tracks = defaultdict(list)

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        reader = csv.DictReader(f)

        for row in reader:
            track_id = int(row["track_id"])

            if track_id < 0:
                continue

            key = (
                row["class_name"],
                track_id,
            )

            tracks[key].append(
                {
                    "frame": int(row["frame_index"]),
                    "time": float(row["timestamp_sec"]),
                    "confidence": float(row["confidence"]),
                    "cx": float(row["center_x"]),
                    "cy": float(row["center_y"]),
                }
            )

    result = {
        "person": [],
        "dog": [],
    }

    for (class_name, track_id), rows in tracks.items():

        rows.sort(key=lambda x: x["frame"])

        first = rows[0]
        last = rows[-1]

        frame_span = last["frame"] - first["frame"] + 1
        detection_frames = len(rows)

        continuity = (
            detection_frames / frame_span
            if frame_span > 0
            else 0.0
        )

        result[class_name].append(
            {
                "track_id": track_id,
                "first_frame": first["frame"],
                "last_frame": last["frame"],
                "start_sec": first["time"],
                "end_sec": last["time"],
                "span_sec": max(
                    0.0,
                    last["time"] - first["time"],
                ),
                "detection_frames": detection_frames,
                "frame_span": frame_span,
                "continuity": continuity,
                "mean_confidence": (
                    sum(r["confidence"] for r in rows)
                    / len(rows)
                ),
                "start_x": first["cx"],
                "start_y": first["cy"],
                "end_x": last["cx"],
                "end_y": last["cy"],
            }
        )

    for class_name in result:
        result[class_name].sort(
            key=lambda x: (
                -x["span_sec"],
                -x["detection_frames"],
            )
        )

    return result


def summarize(items: list[dict]) -> dict:

    if not items:
        return {
            "track_count": 0,
            "longest_span_sec": 0.0,
            "tracks_ge_1s": 0,
            "tracks_ge_2s": 0,
            "tracks_ge_5s": 0,
        }

    return {
        "track_count": len(items),
        "longest_span_sec": max(
            x["span_sec"]
            for x in items
        ),
        "tracks_ge_1s": sum(
            x["span_sec"] >= 1.0
            for x in items
        ),
        "tracks_ge_2s": sum(
            x["span_sec"] >= 2.0
            for x in items
        ),
        "tracks_ge_5s": sum(
            x["span_sec"] >= 5.0
            for x in items
        ),
    }


def main() -> int:

    overall = {}

    print("")
    print("===== TRACK QUALITY AUDIT =====")

    for candidate_dir in sorted(ROOT.glob("candidate_*")):

        csv_path = (
            candidate_dir
            / "tracking"
            / "tracks.csv"
        )

        if not csv_path.exists():
            continue

        result = analyze_csv(csv_path)

        person_summary = summarize(
            result["person"]
        )

        dog_summary = summarize(
            result["dog"]
        )

        candidate_name = candidate_dir.name

        overall[candidate_name] = {
            "person_summary": person_summary,
            "dog_summary": dog_summary,
            "longest_person_tracks": result["person"][:10],
            "dog_tracks": result["dog"],
        }

        print("")
        print(f"===== {candidate_name} =====")

        print(
            "PERSON "
            f"tracks={person_summary['track_count']} "
            f"longest={person_summary['longest_span_sec']:.2f}s "
            f">=1s={person_summary['tracks_ge_1s']} "
            f">=2s={person_summary['tracks_ge_2s']} "
            f">=5s={person_summary['tracks_ge_5s']}"
        )

        print(
            "DOG    "
            f"tracks={dog_summary['track_count']} "
            f"longest={dog_summary['longest_span_sec']:.2f}s "
            f">=1s={dog_summary['tracks_ge_1s']} "
            f">=2s={dog_summary['tracks_ge_2s']} "
            f">=5s={dog_summary['tracks_ge_5s']}"
        )

        if result["dog"]:
            print("")
            print("DOG TRACK DETAILS")

            for track in result["dog"]:
                print(
                    f"  ID={track['track_id']:4d} "
                    f"{track['start_sec']:6.2f}s"
                    f"-{track['end_sec']:6.2f}s "
                    f"span={track['span_sec']:5.2f}s "
                    f"frames={track['detection_frames']:4d} "
                    f"continuity={track['continuity']:.3f} "
                    f"conf={track['mean_confidence']:.3f}"
                )

    output = ROOT / "track_quality_audit.json"

    output.write_text(
        json.dumps(
            overall,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print(f"OUTPUT: {output}")
    print("")
    print("STAGE2_7_AUDIT_OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
