import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scansynclib'))

collect_ignore = [] if os.environ.get("E2E") == "1" else ["e2e"]
