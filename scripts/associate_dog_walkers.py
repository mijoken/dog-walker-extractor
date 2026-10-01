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

            class_name = row["class_name"]

            tracks[(class_name, track_id)].append(
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
        tracks[key].sort(key=lambda x: x["frame"])

    return tracks


def frame_map(rows: list[dict]) -> dict[int, dict]:
    return {
        row["frame"]: row
        for row in rows
    }


def cosine_similarity(ax, ay, bx, by) -> float:
    amag = math.hypot(ax, ay)
    bmag = math.hypot(bx, by)

    if amag < 1e-6 or bmag < 1e-6:
        return 0.5

    value = (
        ax * bx + ay * by
    ) / (amag * bmag)

    return max(-1.0, min(1.0, value))


def pair_score(
    person_rows: list[dict],
    dog_rows: list[dict],
) -> dict | None:

    pmap = frame_map(person_rows)
    dmap = frame_map(dog_rows)

    common_frames = sorted(
        set(pmap) & set(dmap)
    )

    if len(common_frames) < 3:
        return None

    distances = []
    proximity_scores = []

    direction_scores = []
    speed_scores = []

    prev = None

    for frame in common_frames:
        p = pmap[frame]
        d = dmap[frame]

        dx = d["cx"] - p["cx"]
        dy = d["cy"] - p["cy"]

        # Person height is used as scene-scale normalization.
        scale = max(20.0, p["h"])

        normalized_distance = (
            math.hypot(dx, dy) / scale
        )

        distances.append(
            normalized_distance
        )

        # Smooth proximity score.
        # Nearer pairs approach 1.0.
        proximity = math.exp(
            -0.70 * normalized_distance
        )

        proximity_scores.append(proximity)

        if prev is not None:
            prev_frame = prev

            pp = pmap[prev_frame]
            dd = dmap[prev_frame]

            pvx = p["cx"] - pp["cx"]
            pvy = p["cy"] - pp["cy"]

            dvx = d["cx"] - dd["cx"]
            dvy = d["cy"] - dd["cy"]

            cos = cosine_similarity(
                pvx,
                pvy,
                dvx,
                dvy,
            )

            direction_score = (
                cos + 1.0
            ) / 2.0

            direction_scores.append(
                direction_score
            )

            pspeed = math.hypot(
                pvx,
                pvy,
            )

            dspeed = math.hypot(
                dvx,
                dvy,
            )

            if max(pspeed, dspeed) < 1.0:
                speed_score = 1.0
            else:
                speed_score = (
                    min(pspeed, dspeed)
                    / max(pspeed, dspeed)
                )

            speed_scores.append(
                speed_score
            )

        prev = frame

    first_frame = common_frames[0]
    last_frame = common_frames[-1]

    overlap_frame_span = (
        last_frame
        - first_frame
        + 1
    )

    overlap_continuity = (
        len(common_frames)
        / overlap_frame_span
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

    # Temporal persistence saturates around 3 sec at 30 fps.
    persistence = min(
        1.0,
        len(common_frames) / 90.0,
    )

    # Initial general-purpose score.
    final_score = (
        0.40 * proximity_mean
        + 0.20 * direction_mean
        + 0.15 * speed_mean
        + 0.15 * overlap_continuity
        + 0.10 * persistence
    )

    return {
        "score": final_score,
        "common_frames": len(common_frames),
        "first_common_frame": first_frame,
        "last_common_frame": last_frame,
        "overlap_continuity": overlap_continuity,
        "mean_normalized_distance": (
            sum(distances)
            / len(distances)
        ),
        "median_normalized_distance": (
            median(distances)
        ),
        "proximity_score": proximity_mean,
        "direction_score": direction_mean,
        "speed_score": speed_mean,
        "persistence_score": persistence,
    }


def main() -> int:

    overall = {}

    print("")
    print("===== DOG-WALKER PAIR ASSOCIATION =====")

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

        tracks = load_tracks(csv_path)

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
            overall[candidate_dir.name] = candidate_result
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

                result["person_id"] = person_id
                rankings.append(result)

            rankings.sort(
                key=lambda x: -x["score"]
            )

            candidate_result["dogs"][str(dog_id)] = rankings[:10]

            print("")
            print(
                f"DOG #{dog_id} "
                f"frames={len(dog_rows)}"
            )

            if not rankings:
                print("  NO PERSON CANDIDATES")
                continue

            for rank, item in enumerate(
                rankings[:5],
                1,
            ):
                print(
                    f"  #{rank} "
                    f"PERSON #{item['person_id']} "
                    f"score={item['score']:.3f} "
                    f"frames={item['common_frames']} "
                    f"dist={item['median_normalized_distance']:.2f} "
                    f"dir={item['direction_score']:.3f} "
                    f"speed={item['speed_score']:.3f} "
                    f"cont={item['overlap_continuity']:.3f}"
                )

        overall[candidate_dir.name] = candidate_result

    output = ROOT / "pair_association.json"

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
    print("STAGE3_PAIR_ASSOCIATION_OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
