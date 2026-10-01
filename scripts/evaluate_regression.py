from __future__ import annotations

import argparse
import json
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def overlaps(a0: float, a1: float, b0: float, b1: float) -> bool:
    return max(a0, b0) <= min(a1, b1)


def event_interval(event: dict) -> tuple[float, float]:
    return float(event["start_sec"]), float(event["end_sec"])


def find_event_json(validation: dict, root: Path) -> Path | None:
    for rel in validation["event_json_candidates"]:
        p = root / rel
        if p.exists():
            return p
    return None


def matching_events(events: list[dict], windows: list[dict]) -> list[dict]:
    matched = []

    for event in events:
        e0, e1 = event_interval(event)

        if any(
            overlaps(
                e0,
                e1,
                float(w["start_sec"]),
                float(w["end_sec"]),
            )
            for w in windows
        ):
            matched.append(event)

    return matched


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate dog-walker outputs against human-reviewed regression cases."
    )

    parser.add_argument(
        "--manifest",
        default="tests/regression/ground_truth_v0.1.json",
    )

    parser.add_argument(
        "--root",
        default=".",
        help="Repository/result root.",
    )

    parser.add_argument(
        "--json-output",
        default="output/regression_v0.1_report.json",
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()

    manifest_path = root / args.manifest
    manifest = load_json(manifest_path)

    report = {
        "manifest": str(manifest_path),
        "validations": [],
        "totals": {
            "positive_cases": 0,
            "positive_hits": 0,
            "positive_misses": 0,
            "negative_windows": 0,
            "negative_windows_with_prediction": 0,
            "duplicate_positive_cases": 0,
        },
    }

    print("")
    print("=" * 72)
    print("DOG WALKER REGRESSION EVALUATION")
    print("=" * 72)

    for validation in manifest["validations"]:
        vid = validation["id"]

        path = find_event_json(validation, root)

        print("")
        print(f"===== VALIDATION {vid} =====")

        if path is None:
            print("EVENT JSON: NOT FOUND -> SKIPPED")

            report["validations"].append(
                {
                    "id": vid,
                    "status": "SKIPPED_EVENT_JSON_NOT_FOUND",
                }
            )
            continue

        data = load_json(path)
        events = data.get("events", [])

        print(f"event json : {path}")
        print(f"events     : {len(events)}")

        v_report = {
            "id": vid,
            "status": "EVALUATED",
            "event_json": str(path),
            "event_count": len(events),
            "positive_cases": [],
            "negative_windows": [],
        }

        for case in validation.get("positive_cases", []):
            matches = matching_events(
                events,
                case["windows"],
            )

            hit = len(matches) > 0
            duplicate = len(matches) > 1

            report["totals"]["positive_cases"] += 1

            if hit:
                report["totals"]["positive_hits"] += 1
            else:
                report["totals"]["positive_misses"] += 1

            if duplicate:
                report["totals"]["duplicate_positive_cases"] += 1

            status = "HIT" if hit else "MISS"

            print(
                f"POS {case['case_id']:<16} "
                f"{status:<5} "
                f"predictions={len(matches)}"
            )

            v_report["positive_cases"].append(
                {
                    "case_id": case["case_id"],
                    "hit": hit,
                    "prediction_count": len(matches),
                    "possible_oversegmentation": duplicate,
                    "baseline_status": case.get("baseline_status"),
                    "improvement_target": bool(
                        case.get("improvement_target", False)
                    ),
                    "matched_events": matches,
                }
            )

        for neg in validation.get("negative_windows", []):
            matches = matching_events(
                events,
                [neg],
            )

            regression_fp = len(matches) > 0

            report["totals"]["negative_windows"] += 1

            if regression_fp:
                report["totals"][
                    "negative_windows_with_prediction"
                ] += 1

            status = "FP!" if regression_fp else "CLEAR"

            print(
                f"NEG {neg['case_id']:<16} "
                f"{status:<5} "
                f"predictions={len(matches)} "
                f"{neg['description']}"
            )

            v_report["negative_windows"].append(
                {
                    "case_id": neg["case_id"],
                    "prediction_count": len(matches),
                    "regression_false_positive": regression_fp,
                    "description": neg["description"],
                    "matched_events": matches,
                }
            )

        report["validations"].append(v_report)

    totals = report["totals"]

    print("")
    print("=" * 72)
    print("REGRESSION SUMMARY")
    print("=" * 72)

    print(
        f"known positive cases          : "
        f"{totals['positive_cases']}"
    )

    print(
        f"positive cases hit            : "
        f"{totals['positive_hits']}"
    )

    print(
        f"positive cases missed         : "
        f"{totals['positive_misses']}"
    )

    print(
        f"known negative windows        : "
        f"{totals['negative_windows']}"
    )

    print(
        f"negative windows with event   : "
        f"{totals['negative_windows_with_prediction']}"
    )

    print(
        f"positive cases with >1 event  : "
        f"{totals['duplicate_positive_cases']}"
    )

    output = root / args.json_output
    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    output.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("")
    print(f"report: {output}")
    print("")
    print("REGRESSION_EVALUATION_OK")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
