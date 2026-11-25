"""Make the shared synthetic compare fixtures (`eval/fixtures/compare`) importable as `compare`."""
import sys
from pathlib import Path

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures"
if str(FIXTURES) not in sys.path:
    sys.path.insert(0, str(FIXTURES))
