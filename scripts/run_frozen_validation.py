from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(
        name,
        path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            f"Could not load module: {path}"
        )

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def main() -> int:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--root",
        required=True,
        help="Precision candidate root.",
    )

    args = parser.parse_args()

    root = Path(args.root).resolve()

    precision = root / "precision_summary.json"
    audit = root / "track_quality_audit.json"

    if not precision.exists():
        raise FileNotFoundError(precision)

    if not audit.exists():
        raise FileNotFoundError(audit)

    print("")
    print("==========================================")
    print(" OFFICIAL v0.2 VALIDATION PIPELINE")
    print("==========================================")
    print(f"root: {root}")

    # ----------------------------------------------------------
    # Association V2
    #
    # Load the current official v0.2 association implementation.
    # Only ROOT is redirected.
    # ----------------------------------------------------------

    print("")
    print("===== OFFICIAL v0.2 ASSOCIATION V2 =====")

    association = load_module(
        "frozen_association_v2",
        SCRIPTS / "associate_dog_walkers_v2.py",
    )

    association.ROOT = root

    rc = association.main()

    if rc not in (None, 0):
        raise RuntimeError(
            f"Association failed: {rc}"
        )

    pair_file = (
        root
        / "pair_association_v2.json"
    )

    if not pair_file.exists():
        raise RuntimeError(
            f"Missing association output: {pair_file}"
        )

    # ----------------------------------------------------------
    # Event generation
    #
    # Load the official event generator.
    # Event acceptance thresholds remain unchanged from v0.1.
    # ----------------------------------------------------------

    print("")
    print("===== OFFICIAL v0.2 EVENT GENERATOR =====")

    events = load_module(
        "frozen_event_generator",
        SCRIPTS / "generate_dog_walker_events.py",
    )

    events.ROOT = root
    events.PAIR_FILE = pair_file
    events.PRECISION_FILE = precision
    events.AUDIT_FILE = audit
    events.OUTPUT_JSON = (
        root
        / "dog_walker_events.json"
    )

    rc = events.main()

    if rc not in (None, 0):
        raise RuntimeError(
            f"Event generation failed: {rc}"
        )

    print("")
    print("==========================================")
    print(" OFFICIAL v0.2 VALIDATION PIPELINE COMPLETE")
    print("==========================================")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

