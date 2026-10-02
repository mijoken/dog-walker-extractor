from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
from statistics import median

import cv2
import numpy as np


VERSION = "roi-analyzer-v0.2"


def load_json(path: Path):
    return json.loads(
        path.read_text(encoding="utf-8-sig")
    )


def load_tracks(path: Path):
    rows = []

    with path.open(
        "r",
        encoding="utf-8-sig",
        newline="",
    ) as f:
        for row in csv.DictReader(f):
            rows.append({
                "frame_index": int(row["frame_index"]),
                "timestamp_sec": float(row["timestamp_sec"]),
                "track_id": int(row["track_id"]),
                "class_name": row["class_name"],
                "confidence": float(row["confidence"]),
                "x1": float(row["x1"]),
                "y1": float(row["y1"]),
                "x2": float(row["x2"]),
                "y2": float(row["y2"]),
            })

    return rows


def foot_anchor(row):
    """
    Ground-contact proxy for both people and dogs.

    For a fixed camera, bbox bottom-center is generally more useful
    than bbox center for determining proximity to a ground-level ROI.
    """
    return (
        (row["x1"] + row["x2"]) / 2.0,
        row["y2"],
    )


def norm_polygon_to_pixels(
    points,
    width,
    height,
):
    return [
        (
            float(x) * width,
            float(y) * height,
        )
        for x, y in points
    ]


def signed_distance(
    point,
    polygon,
):
    contour = np.asarray(
        [
            [[float(x), float(y)]]
            for x, y in polygon
        ],
        dtype=np.float32,
    )

    return float(
        cv2.pointPolygonTest(
            contour,
            point,
            True,
        )
    )


def longest_true_run(
    samples,
    key,
    max_gap_sec,
):
    best = []
    current = []

    for sample in samples:

        if not sample[key]:
            if len(current) > len(best):
                best = current

            current = []
            continue

        if current:
            gap = (
                sample["timestamp_sec"]
                - current[-1]["timestamp_sec"]
            )

            if gap > max_gap_sec:
                if len(current) > len(best):
                    best = current

                current = []

        current.append(sample)

    if len(current) > len(best):
        best = current

    return best


def run_duration(run):
    if len(run) < 2:
        return 0.0

    return (
        run[-1]["timestamp_sec"]
        - run[0]["timestamp_sec"]
    )


def compute_speeds(
    samples,
    frame_diag,
):
    previous = None

    for sample in samples:

        sample["speed_norm_per_sec"] = None

        if previous is not None:
            dt = (
                sample["timestamp_sec"]
                - previous["timestamp_sec"]
            )

            if dt > 0:
                dx = (
                    sample["anchor_x"]
                    - previous["anchor_x"]
                )

                dy = (
                    sample["anchor_y"]
                    - previous["anchor_y"]
                )

                dist = math.hypot(dx, dy)

                sample[
                    "speed_norm_per_sec"
                ] = (
                    dist
                    / frame_diag
                    / dt
                )

        previous = sample


def approach_evidence(
    samples,
    window_sec,
):
    if len(samples) < 2:
        return {
            "available": False,
            "distance_drop_px": 0.0,
            "approaching": False,
        }

    end_time = samples[-1]["timestamp_sec"]
    start_time = end_time - window_sec

    window = [
        x
        for x in samples
        if x["timestamp_sec"] >= start_time
    ]

    if len(window) < 2:
        return {
            "available": False,
            "distance_drop_px": 0.0,
            "approaching": False,
        }

    first_distance = abs(
        min(
            0.0,
            window[0][
                "target_signed_distance_px"
            ],
        )
    )

    last_distance = abs(
        min(
            0.0,
            window[-1][
                "target_signed_distance_px"
            ],
        )
    )

    drop = (
        first_distance
        - last_distance
    )

    return {
        "available": True,
        "distance_drop_px": drop,
        "approaching": drop > 0.0,
    }


def analyze_track(
    rows,
    *,
    class_name,
    track_id,
    profile,
):
    width = int(
        profile["frame_width"]
    )

    height = int(
        profile["frame_height"]
    )

    target_polygon = (
        norm_polygon_to_pixels(
            profile[
                "target_polygon_norm"
            ],
            width,
            height,
        )
    )

    near_polygon = (
        norm_polygon_to_pixels(
            profile[
                "near_polygon_norm"
            ],
            width,
            height,
        )
    )

    selected = [
        x
        for x in rows
        if (
            x["class_name"] == class_name
            and x["track_id"] == track_id
        )
    ]

    selected.sort(
        key=lambda x: x[
            "frame_index"
        ]
    )

    if not selected:
        return {
            "class_name": class_name,
            "track_id": track_id,
            "available": False,
            "reason": "track not found",
        }

    samples = []

    for row in selected:
        anchor_x, anchor_y = (
            foot_anchor(row)
        )

        target_distance = (
            signed_distance(
                (
                    anchor_x,
                    anchor_y,
                ),
                target_polygon,
            )
        )

        near_distance = (
            signed_distance(
                (
                    anchor_x,
                    anchor_y,
                ),
                near_polygon,
            )
        )

        samples.append({
            "frame_index":
                row["frame_index"],

            "timestamp_sec":
                row["timestamp_sec"],

            "confidence":
                row["confidence"],

            "anchor_x":
                anchor_x,

            "anchor_y":
                anchor_y,

            "inside_target":
                target_distance >= 0.0,

            "inside_near":
                near_distance >= 0.0,

            "target_signed_distance_px":
                target_distance,

            "near_signed_distance_px":
                near_distance,
        })

    frame_diag = math.hypot(
        width,
        height,
    )

    compute_speeds(
        samples,
        frame_diag,
    )

    thresholds = (
        profile["thresholds"]
    )

    max_gap = float(
        thresholds[
            "max_continuity_gap_sec"
        ]
    )

    target_run = longest_true_run(
        samples,
        "inside_target",
        max_gap,
    )

    near_run = longest_true_run(
        samples,
        "inside_near",
        max_gap,
    )

    target_dwell = run_duration(
        target_run
    )

    near_dwell = run_duration(
        near_run
    )

    near_speeds = [
        x["speed_norm_per_sec"]
        for x in near_run
        if (
            x["speed_norm_per_sec"]
            is not None
        )
    ]

    median_near_speed = (
        median(near_speeds)
        if near_speeds
        else None
    )

    stop_speed_threshold = float(
        thresholds[
            "stop_speed_norm_per_sec"
        ]
    )

    for sample in samples:
        speed = sample[
            "speed_norm_per_sec"
        ]

        sample[
            "low_speed_in_near"
        ] = (
            sample["inside_near"]
            and speed is not None
            and speed
            <= stop_speed_threshold
        )

    stop_run = longest_true_run(
        samples,
        "low_speed_in_near",
        max_gap,
    )

    stop_duration = run_duration(
        stop_run
    )

    first_near_index = next(
        (
            i
            for i, x
            in enumerate(samples)
            if x["inside_near"]
        ),
        None,
    )

    approach = {
        "available": False,
        "distance_drop_px": 0.0,
        "approaching": False,
    }

    if first_near_index is not None:
        approach = approach_evidence(
            samples[
                : first_near_index + 1
            ],
            float(
                thresholds[
                    "approach_window_sec"
                ]
            ),
        )

    arrived = (
        len(target_run) > 0
    )

    dwelled = (
        near_dwell
        >= float(
            thresholds[
                "min_dwell_sec"
            ]
        )
    )

    stopped = (
        stop_duration
        >= float(
            thresholds[
                "min_stop_sec"
            ]
        )
    )

    departed = False

    if first_near_index is not None:

        last_near_index = max(
            i
            for i, x
            in enumerate(samples)
            if x["inside_near"]
        )

        departed = any(
            not x["inside_near"]
            for x in samples[
                last_near_index + 1 :
            ]
        )

    states = []

    if approach["approaching"]:
        states.append(
            "APPROACH"
        )

    if first_near_index is not None:
        states.append(
            "ENTER_NEAR_ZONE"
        )

    if arrived:
        states.append(
            "ARRIVE_TARGET"
        )

    if dwelled:
        states.append(
            "DWELL"
        )

    if stopped:
        states.append(
            "STOP"
        )

    if departed:
        states.append(
            "DEPART"
        )

    return {
        "class_name": class_name,
        "track_id": track_id,
        "available": True,

        "sample_count":
            len(samples),

        "first_time_sec":
            samples[0][
                "timestamp_sec"
            ],

        "last_time_sec":
            samples[-1][
                "timestamp_sec"
            ],

        "states":
            states,

        "approach":
            approach,

        "near_zone": {
            "entered":
                first_near_index
                is not None,

            "longest_dwell_sec":
                near_dwell,
        },

        "target": {
            "arrived":
                arrived,

            "longest_dwell_sec":
                target_dwell,
        },

        "motion": {
            "median_near_speed_norm_per_sec":
                median_near_speed,

            "longest_stop_sec":
                stop_duration,

            "stopped":
                stopped,
        },

        "departed":
            departed,

        "samples":
            samples,
    }


def find_candidate_name(event):
    for key in (
        "candidate",
        "candidate_name",
        "source_candidate",
    ):
        value = event.get(key)

        if value:
            return str(value)

    raise KeyError(
        "event has no candidate identifier"
    )


def summarize_event(
    event,
    rows,
    profile,
):
    person_id = int(
        event["person_track_id"]
    )

    person_result = (
        analyze_track(
            rows,
            class_name="person",
            track_id=person_id,
            profile=profile,
        )
    )

    dog_results = []

    for dog_id in (
        event.get(
            "dog_track_ids",
            []
        )
    ):
        dog_results.append(
            analyze_track(
                rows,
                class_name="dog",
                track_id=int(dog_id),
                profile=profile,
            )
        )

    available_dogs = [
        x
        for x in dog_results
        if x.get("available")
    ]

    dog_entered_near = any(
        x["near_zone"]["entered"]
        for x in available_dogs
    )

    dog_arrived_target = any(
        x["target"]["arrived"]
        for x in available_dogs
    )

    dog_dwelled = any(
        "DWELL" in x["states"]
        for x in available_dogs
    )

    dog_stopped = any(
        "STOP" in x["states"]
        for x in available_dogs
    )

    event_labels = [
        "DOG_WALKER_EVENT"
    ]

    if dog_entered_near:
        event_labels.append(
            "DOG_NEAR_TARGET"
        )

    if dog_arrived_target:
        event_labels.append(
            "DOG_AT_TARGET"
        )

    if dog_dwelled:
        event_labels.append(
            "DOG_DWELL"
        )

    if dog_stopped:
        event_labels.append(
            "DOG_STOP"
        )

    return {
        "person":
            person_result,

        "dogs":
            dog_results,

        "event_labels":
            event_labels,

        "dog_near_target":
            dog_entered_near,

        "dog_at_target":
            dog_arrived_target,

        "dog_dwell":
            dog_dwelled,

        "dog_stop":
            dog_stopped,
    }


def run_self_test():
    """
    Pure geometry/state-machine test.

    No YOLO.
    No video.
    No existing sample is used for parameter tuning.
    """

    profile = {
        "frame_width": 1000,
        "frame_height": 1000,

        "target_polygon_norm": [
            [0.45, 0.45],
            [0.55, 0.45],
            [0.55, 0.55],
            [0.45, 0.55],
        ],

        "near_polygon_norm": [
            [0.35, 0.35],
            [0.65, 0.35],
            [0.65, 0.65],
            [0.35, 0.65],
        ],

        "thresholds": {
            "approach_window_sec": 3.0,
            "min_dwell_sec": 1.5,
            "min_stop_sec": 1.0,
            "stop_speed_norm_per_sec": 0.025,
            "max_continuity_gap_sec": 0.25,
        },
    }

    rows = []

    points = [
        (0.0, 200, 500),
        (0.2, 260, 500),
        (0.4, 320, 500),
        (0.6, 380, 500),
        (0.8, 430, 500),
        (1.0, 470, 500),
        (1.2, 500, 500),

        # stationary / very-low-speed interval
        (1.4, 500, 500),
        (1.6, 501, 500),
        (1.8, 500, 501),
        (2.0, 500, 500),
        (2.2, 501, 500),
        (2.4, 500, 500),
        (2.6, 500, 500),
        (2.8, 501, 500),
        (3.0, 500, 500),

        # departure
        (3.2, 560, 500),
        (3.4, 620, 500),
        (3.6, 680, 500),
        (3.8, 750, 500),
    ]

    for frame, (
        t,
        x,
        y,
    ) in enumerate(points):

        rows.append({
            "frame_index":
                frame,

            "timestamp_sec":
                t,

            "track_id":
                99,

            "class_name":
                "dog",

            "confidence":
                0.9,

            "x1":
                x - 10,

            "y1":
                y - 20,

            "x2":
                x + 10,

            "y2":
                y,
        })

    result = analyze_track(
        rows,
        class_name="dog",
        track_id=99,
        profile=profile,
    )

    required = {
        "APPROACH",
        "ENTER_NEAR_ZONE",
        "ARRIVE_TARGET",
        "DWELL",
        "STOP",
        "DEPART",
    }

    actual = set(
        result["states"]
    )

    print()
    print(
        "SELF TEST STATES:",
        result["states"],
    )

    missing = (
        required - actual
    )

    if missing:
        raise RuntimeError(
            "ROI self-test failed; "
            f"missing states: "
            f"{sorted(missing)}"
        )

    print(
        "ROI_SELF_TEST_OK"
    )


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        help=(
            "precision_candidates "
            "directory"
        ),
    )

    parser.add_argument(
        "--profile",
        help=(
            "camera ROI profile JSON"
        ),
    )

    parser.add_argument(
        "--events",
        default=(
            "dog_walker_events.json"
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            "roi_behavior_events.json"
        ),
    )

    parser.add_argument(
        "--self-test",
        action="store_true",
        help=(
            "Run synthetic ROI "
            "state-machine test only"
        ),
    )

    args = parser.parse_args()

    if args.self_test:
        run_self_test()
        return

    if not args.root:
        parser.error(
            "--root is required "
            "unless --self-test is used"
        )

    if not args.profile:
        parser.error(
            "--profile is required "
            "unless --self-test is used"
        )

    root = Path(
        args.root
    ).resolve()

    profile_path = Path(
        args.profile
    ).resolve()

    profile = load_json(
        profile_path
    )

    if not profile.get(
        "enabled",
        False,
    ):
        raise SystemExit(
            "ROI profile is disabled. "
            "Define the real camera ROI "
            "before enabling it."
        )

    events_path = (
        root / args.events
    )

    events_data = load_json(
        events_path
    )

    results = []

    for event_index, event in enumerate(
        events_data.get(
            "events",
            [],
        ),
        start=1,
    ):

        candidate = (
            find_candidate_name(
                event
            )
        )

        tracks_path = (
            root
            / candidate
            / "tracking"
            / "tracks.csv"
        )

        if not tracks_path.exists():
            results.append({
                "event_index":
                    event_index,

                "candidate":
                    candidate,

                "available":
                    False,

                "reason":
                    (
                        "missing "
                        "tracks.csv: "
                        f"{tracks_path}"
                    ),
            })
            continue

        rows = load_tracks(
            tracks_path
        )

        summary = summarize_event(
            event,
            rows,
            profile,
        )

        results.append({
            "event_index":
                event_index,

            "candidate":
                candidate,

            "available":
                True,

            "dog_walker_score":
                event.get(
                    "mean_pair_score"
                ),

            **summary,
        })

    output_path = (
        root / args.output
    )

    output = {
        "version":
            VERSION,

        "profile":
            profile,

        "event_source":
            str(events_path),

        "result_count":
            len(results),

        "results":
            results,
    }

    output_path.write_text(
        json.dumps(
            output,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print()
    print("=" * 76)
    print(
        "ROI BEHAVIOR "
        "ANALYZER v0.2"
    )
    print("=" * 76)

    for item in results:

        if not item.get(
            "available"
        ):
            print(
                f"EVENT "
                f"{item['event_index']:03d} "
                f"{item['candidate']} "
                "UNAVAILABLE"
            )
            continue

        labels = ",".join(
            item[
                "event_labels"
            ]
        )

        print(
            f"EVENT "
            f"{item['event_index']:03d} "
            f"{item['candidate']} "
            f"labels=[{labels}]"
        )

    print()
    print(
        "OUTPUT:",
        output_path,
    )

    print(
        "ROI_ANALYZER_OK"
    )


if __name__ == "__main__":
    main()
