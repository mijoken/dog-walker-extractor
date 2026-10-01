from __future__ import annotations

import csv
import json
import math
from collections import defaultdict
from pathlib import Path
from statistics import median


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "output" / "precision_candidates"


def load_tracks(path: Path) -> dict:
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

            tracks[
                (row["class_name"], track_id)
            ].append(
                {
                    "frame": int(row["frame_index"]),
                    "time": float(row["timestamp_sec"]),
                    "cx": float(row["center_x"]),
                    "cy": float(row["center_y"]),
                    "w": float(row["width"]),
                    "h": float(row["height"]),
                    "conf": float(row["confidence"]),
                }
            )

    for key in tracks:
        tracks[key].sort(
            key=lambda x: x["frame"]
        )

    return tracks


def frame_map(rows):
    return {
        row["frame"]: row
        for row in rows
    }


def cosine_similarity(ax, ay, bx, by):
    amag = math.hypot(ax, ay)
    bmag = math.hypot(bx, by)

    if amag < 1e-6 or bmag < 1e-6:
        return 0.5

    value = (
        ax * bx + ay * by
    ) / (amag * bmag)

    return max(
        -1.0,
        min(1.0, value),
    )


def pair_score(
    person_rows,
    dog_rows,
    motion_lag=5,
):
    pmap = frame_map(person_rows)
    dmap = frame_map(dog_rows)

    common = sorted(
        set(pmap) & set(dmap)
    )

    if len(common) < 3:
        return None

    distances = []
    proximity_scores = []

    for frame in common:
        p = pmap[frame]
        d = dmap[frame]

        dx = d["cx"] - p["cx"]
        dy = d["cy"] - p["cy"]

        # Perspective-aware normalization.
        person_scale = max(
            20.0,
            p["h"],
        )

        normalized_distance = (
            math.hypot(dx, dy)
            / person_scale
        )

        distances.append(
            normalized_distance
        )

        proximity_scores.append(
            math.exp(
                -0.70
                * normalized_distance
            )
        )

    direction_scores = []
    speed_scores = []

    common_set = set(common)

    for frame in common:

        previous_frame = (
            frame - motion_lag
        )

        if previous_frame not in common_set:
            continue

        p0 = pmap[previous_frame]
        p1 = pmap[frame]

        d0 = dmap[previous_frame]
        d1 = dmap[frame]

        pvx = p1["cx"] - p0["cx"]
        pvy = p1["cy"] - p0["cy"]

        dvx = d1["cx"] - d0["cx"]
        dvy = d1["cy"] - d0["cy"]

        cos = cosine_similarity(
            pvx,
            pvy,
            dvx,
            dvy,
        )

        direction_scores.append(
            (cos + 1.0) / 2.0
        )

        pspeed = math.hypot(
            pvx,
            pvy,
        )

        dspeed = math.hypot(
            dvx,
            dvy,
        )

        if max(pspeed, dspeed) < 2.0:
            speed_score = 1.0
        else:
            speed_score = (
                min(pspeed, dspeed)
                / max(pspeed, dspeed)
            )

        speed_scores.append(
            speed_score
        )

    first = common[0]
    last = common[-1]

    overlap_span_frames = (
        last - first + 1
    )

    overlap_continuity = (
        len(common)
        / overlap_span_frames
    )

    dog_frame_count = len(dog_rows)

    dog_coverage = (
        len(common)
        / dog_frame_count
        if dog_frame_count
        else 0.0
    )

    first_time = max(
        pmap[first]["time"],
        dmap[first]["time"],
    )

    last_time = min(
        pmap[last]["time"],
        dmap[last]["time"],
    )

    common_span_sec = max(
        0.0,
        last_time - first_time,
    )

    proximity_mean = (
        sum(proximity_scores)
        / len(proximity_scores)
    )

    direction_mean = (
        sum(direction_scores)
        / len(direction_scores)
        if direction_scores
        else 0.5
    )

    speed_mean = (
        sum(speed_scores)
        / len(speed_scores)
        if speed_scores
        else 0.5
    )

    # Continuous persistence factor.
    # About 3 sec is enough to reach full persistence evidence.
    persistence = min(
        1.0,
        common_span_sec / 3.0,
    )

    # Base relationship evidence.
    base_score = (
        0.35 * proximity_mean
        + 0.20 * direction_mean
        + 0.10 * speed_mean
        + 0.10 * overlap_continuity
        + 0.15 * dog_coverage
        + 0.10 * persistence
    )

    # Brief encounters should not beat persistent companionship.
    #
    # 0 sec -> 0
    # 1 sec -> 0.577
    # 2.5 sec -> 1
    duration_factor = min(
        1.0,
        math.sqrt(
            common_span_sec / 2.5
        )
        if common_span_sec > 0
        else 0.0,
    )

    # A pair covering only a tiny portion of the dog's track
    # receives an explicit penalty.
    coverage_factor = math.sqrt(
        max(
            0.0,
            min(1.0, dog_coverage),
        )
    )

    final_score = (
        base_score
        * duration_factor
        * coverage_factor
    )

    return {
        "score": final_score,
        "base_score": base_score,

        "common_frames": len(common),
        "common_span_sec": common_span_sec,

        "dog_track_frames": dog_frame_count,
        "dog_coverage": dog_coverage,

        "first_common_frame": first,
        "last_common_frame": last,

        "overlap_continuity": (
            overlap_continuity
        ),

        "mean_normalized_distance": (
            sum(distances)
            / len(distances)
        ),

        "median_normalized_distance": (
            median(distances)
        ),

        "proximity_score": (
            proximity_mean
        ),

        "direction_score": (
            direction_mean
        ),

        "speed_score": (
            speed_mean
        ),

        "persistence_score": (
            persistence
        ),

        "duration_factor": (
            duration_factor
        ),

        "coverage_factor": (
            coverage_factor
        ),
    }


def main():

    overall = {}

    print("")
    print(
        "===== DOG-WALKER PAIR ASSOCIATION V2 ====="
    )

    for candidate_dir in sorted(
        ROOT.glob("candidate_*")
    ):

        csv_path = (
            candidate_dir
            / "tracking"
            / "tracks.csv"
        )

        if not csv_path.exists():
            continue

        tracks = load_tracks(
            csv_path
        )

        persons = {
            track_id: rows
            for (class_name, track_id), rows
            in tracks.items()
            if class_name == "person"
        }

        dogs = {
            track_id: rows
            for (class_name, track_id), rows
            in tracks.items()
            if class_name == "dog"
        }

        candidate_result = {
            "dog_count": len(dogs),
            "dogs": {},
        }

        print("")
        print(
            f"===== {candidate_dir.name} ====="
        )

        if not dogs:
            print("NO DOG TRACKS")
            overall[
                candidate_dir.name
            ] = candidate_result
            continue

        for dog_id, dog_rows in dogs.items():

            rankings = []

            for person_id, person_rows in persons.items():

                result = pair_score(
                    person_rows,
                    dog_rows,
                )

                if result is None:
                    continue

                result[
                    "person_id"
                ] = person_id

                rankings.append(
                    result
                )

            rankings.sort(
                key=lambda x: -x["score"]
            )

            candidate_result[
                "dogs"
            ][str(dog_id)] = rankings[:10]

            print("")
            print(
                f"DOG #{dog_id} "
                f"frames={len(dog_rows)}"
            )

            if not rankings:
                print(
                    "  NO PERSON CANDIDATES"
                )
                continue

            for rank, item in enumerate(
                rankings[:5],
                1,
            ):

                print(
                    f"  #{rank} "
                    f"PERSON #{item['person_id']} "
                    f"score={item['score']:.3f} "
                    f"base={item['base_score']:.3f} "
                    f"time={item['common_span_sec']:.2f}s "
                    f"coverage={item['dog_coverage']:.3f} "
                    f"frames={item['common_frames']} "
                    f"dist={item['median_normalized_distance']:.2f} "
                    f"dir={item['direction_score']:.3f}"
                )

        overall[
            candidate_dir.name
        ] = candidate_result

    output = (
        ROOT
        / "pair_association_v2_exp.json"
    )

    output.write_text(
        json.dumps(
            overall,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print(
        f"OUTPUT: {output}"
    )
    print("")
    print(
        "STAGE3_1_ASSOCIATION_V2_OK"
    )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())


