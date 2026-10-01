from pathlib import Path
import sys

repo = Path(__file__).resolve().parents[1]
src = repo / "src"
sys.path.insert(0, str(src))

from dogwalker.tracking.engine import TrackRecord, run_tracking

print("STAGE2_IMPORT_OK")
print(TrackRecord)
print(run_tracking)
