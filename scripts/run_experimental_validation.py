from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path


REPO = Path(__file__).resolve().parents[1]
SCRIPTS = REPO / "scripts"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)

    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load module: {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    return module


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Run v0.2 experimental association/event generation "
            "against an existing precision-candidate root."
        )
    )

    parser.add_argument(
        "--root",
        required=True,
        help="Existing precision_candidates directory.",
    )

    args = parser.parse_args()

    root = Path(args.root)

    if not root.is_absolute():
        root = (REPO / root).resolve()
    else:
        root = root.resolve()

    if not root.exists():
        raise FileNotFoundError(root)

    print("")
    print("==========================================")
    print(" v0.2 EXPERIMENT A PIPELINE")
    print("==========================================")
    print(f"root: {root}")

    # ------------------------------------------------------------
    # Experimental association
    # ------------------------------------------------------------

    assoc = load_module(
        "associate_dog_walkers_v2_exp_runtime",
        SCRIPTS / "associate_dog_walkers_v2_exp.py",
    )

    # The original association script uses a module-global ROOT.
    assoc.ROOT = root

    print("")
    print("===== EXPERIMENTAL ASSOCIATION =====")

    assoc.main()

    pair_file = root / "pair_association_v2_exp.json"

    if not pair_file.exists():
        raise FileNotFoundError(
            f"Association output missing: {pair_file}"
        )

    # ------------------------------------------------------------
    # Experimental event generator
    # ------------------------------------------------------------

    event = load_module(
        "generate_dog_walker_events_exp_runtime",
        SCRIPTS / "generate_dog_walker_events_exp.py",
    )

    # Its paths are created as module globals, so redirect all of them.
    if hasattr(event, "ROOT"):
        event.ROOT = root

    event.PAIR_FILE = pair_file
    event.PRECISION_FILE = root / "precision_summary.json"
    event.AUDIT_FILE = root / "track_quality_audit.json"
    event.OUTPUT_JSON = root / "dog_walker_events_exp.json"

    print("")
    print("===== EXPERIMENTAL EVENT GENERATOR =====")

    event.main()

    if not event.OUTPUT_JSON.exists():
        raise FileNotFoundError(
            f"Event output missing: {event.OUTPUT_JSON}"
        )

    print("")
    print("==========================================")
    print(" v0.2 EXPERIMENT A COMPLETE")
    print("==========================================")
    print(f"pair : {pair_file}")
    print(f"event: {event.OUTPUT_JSON}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

