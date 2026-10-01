from __future__ import annotations

import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
ROOT = REPO / "output" / "precision_candidates"

PAIR_FILE = ROOT / "pair_association_v2_exp.json"
PRECISION_FILE = ROOT / "precision_summary.json"
AUDIT_FILE = ROOT / "track_quality_audit.json"

OUTPUT_JSON = ROOT / "dog_walker_events_exp.json"


# Generic defaults.
#
# These are NOT based on known ground-truth timestamps.
MIN_PAIR_SCORE = 0.55
MIN_PAIR_SPAN_SEC = 1.0
MIN_DOG_FRAMES = 5

# Dog-track fragments associated with the same person can be
# merged when separated by only a short temporal gap.
MERGE_GAP_SEC = 1.5


def format_time(seconds: float) -> str:
    minutes = int(seconds // 60)
    secs = seconds - (minutes * 60)
    return f"{minutes:02d}:{secs:05.2f}"


def main() -> int:

    pair_data = json.loads(
        PAIR_FILE.read_text(encoding="utf-8")
    )

    precision_data = json.loads(
        PRECISION_FILE.read_text(encoding="utf-8")
    )

    audit_data = json.loads(
        AUDIT_FILE.read_text(encoding="utf-8")
    )

    candidate_source_offsets = {}

    for item in precision_data["candidates"]:
        candidate_name = (
            f"candidate_{item['candidate_index']:03d}"
        )

        candidate_source_offsets[candidate_name] = {
            "start": float(item["source_start_sec"]),
            "end": float(item["source_end_sec"]),
        }

    raw_events = []

    print("")
    print("===== RAW DOG-WALKER EVENT EVIDENCE =====")

    for candidate_name, candidate in pair_data.items():

        offsets = candidate_source_offsets.get(
            candidate_name
        )

        if offsets is None:
            continue

        dog_audit = {
            int(item["track_id"]): item
            for item in audit_data.get(
                candidate_name,
                {}
            ).get(
                "dog_tracks",
                []
            )
        }

        for dog_id_text, rankings in candidate.get(
            "dogs",
            {}
        ).items():

            dog_id = int(dog_id_text)

            if not rankings:
                continue

            dog_info = dog_audit.get(dog_id)

            if dog_info is None:
                continue

            dog_frames = int(
                dog_info["detection_frames"]
            )

            dog_span_sec = float(
                dog_info["span_sec"]
            )

            best = rankings[0]

            pair_score = float(
                best["score"]
            )

            pair_span_sec = float(
                best["common_span_sec"]
            )

            person_id = int(
                best["person_id"]
            )

            accepted = (
                dog_frames >= MIN_DOG_FRAMES
                and dog_span_sec >= MIN_PAIR_SPAN_SEC
                and pair_span_sec >= MIN_PAIR_SPAN_SEC
                and pair_score >= MIN_PAIR_SCORE
            )

            source_start = (
                offsets["start"]
                + float(dog_info["start_sec"])
            )

            source_end = (
                offsets["start"]
                + float(dog_info["end_sec"])
            )

            event = {
                "candidate": candidate_name,
                "dog_track_id": dog_id,
                "person_track_id": person_id,

                "pair_score": pair_score,
                "pair_span_sec": pair_span_sec,

                "dog_frames": dog_frames,
                "dog_span_sec": dog_span_sec,

                "dog_coverage": float(
                    best["dog_coverage"]
                ),

                "median_normalized_distance": float(
                    best["median_normalized_distance"]
                ),

                "direction_score": float(
                    best["direction_score"]
                ),

                "source_start_sec": source_start,
                "source_end_sec": source_end,

                "accepted": accepted,
            }

            raw_events.append(event)

            state = (
                "ACCEPT"
                if accepted
                else "REJECT"
            )

            print(
                f"{state:6s} "
                f"{candidate_name} "
                f"DOG #{dog_id:<4d} "
                f"PERSON #{person_id:<4d} "
                f"score={pair_score:.3f} "
                f"pair={pair_span_sec:.2f}s "
                f"dog={dog_span_sec:.2f}s "
                f"{format_time(source_start)}"
                f"-{format_time(source_end)}"
            )

    accepted_events = [
        event
        for event in raw_events
        if event["accepted"]
    ]

    accepted_events.sort(
        key=lambda x: x["source_start_sec"]
    )

    # --------------------------------------------------------
    # Merge fragmented dog tracks.
    #
    # Same candidate + same associated person + short time gap
    # => one dog-walking event.
    # --------------------------------------------------------

    merged = []

    for event in accepted_events:

        if not merged:
            merged.append(
                {
                    "candidate": event["candidate"],
                    "person_track_id": event["person_track_id"],
                    "dog_track_ids": [
                        event["dog_track_id"]
                    ],
                    "start_sec": event["source_start_sec"],
                    "end_sec": event["source_end_sec"],
                    "pair_scores": [
                        event["pair_score"]
                    ],
                }
            )
            continue

        previous = merged[-1]

        gap = (
            event["source_start_sec"]
            - previous["end_sec"]
        )

        same_context = (
            event["candidate"]
            == previous["candidate"]
            and event["person_track_id"]
            == previous["person_track_id"]
        )

        if (
            same_context
            and gap <= MERGE_GAP_SEC
        ):
            previous["end_sec"] = max(
                previous["end_sec"],
                event["source_end_sec"],
            )

            previous["dog_track_ids"].append(
                event["dog_track_id"]
            )

            previous["pair_scores"].append(
                event["pair_score"]
            )

        else:
            merged.append(
                {
                    "candidate": event["candidate"],
                    "person_track_id": event["person_track_id"],
                    "dog_track_ids": [
                        event["dog_track_id"]
                    ],
                    "start_sec": event["source_start_sec"],
                    "end_sec": event["source_end_sec"],
                    "pair_scores": [
                        event["pair_score"]
                    ],
                }
            )

    final_events = []

    for index, event in enumerate(
        merged,
        1,
    ):
        duration = (
            event["end_sec"]
            - event["start_sec"]
        )

        mean_score = (
            sum(event["pair_scores"])
            / len(event["pair_scores"])
        )

        final_events.append(
            {
                "event_id": index,
                "candidate": event["candidate"],
                "person_track_id": (
                    event["person_track_id"]
                ),
                "dog_track_ids": (
                    event["dog_track_ids"]
                ),
                "start_sec": event["start_sec"],
                "end_sec": event["end_sec"],
                "start_time": format_time(
                    event["start_sec"]
                ),
                "end_time": format_time(
                    event["end_sec"]
                ),
                "duration_sec": duration,
                "mean_pair_score": mean_score,
            }
        )

    result = {
        "parameters": {
            "min_pair_score": MIN_PAIR_SCORE,
            "min_pair_span_sec": MIN_PAIR_SPAN_SEC,
            "min_dog_frames": MIN_DOG_FRAMES,
            "merge_gap_sec": MERGE_GAP_SEC,
        },
        "raw_evidence": raw_events,
        "events": final_events,
    }

    OUTPUT_JSON.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print("===== FINAL DOG-WALKER EVENTS =====")

    if not final_events:
        print("NO DOG-WALKER EVENTS")
    else:
        for event in final_events:
            print(
                f"EVENT {event['event_id']:03d} "
                f"{event['start_time']}"
                f" - "
                f"{event['end_time']} "
                f"duration={event['duration_sec']:.2f}s "
                f"PERSON #{event['person_track_id']} "
                f"DOG TRACKS={event['dog_track_ids']} "
                f"score={event['mean_pair_score']:.3f}"
            )

    print("")
    print(f"OUTPUT: {OUTPUT_JSON}")
    print("")
    print("STAGE3_2_EVENT_GENERATION_OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

