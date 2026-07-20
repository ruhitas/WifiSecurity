"""Create the platform's relational schema in MSSQL (WirelesSecureDB)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wids.schema import ensure_schema  # noqa: E402

if __name__ == "__main__":
    tables = ensure_schema()
    print("Schema ready. Tables:", ", ".join(tables) or "(none)")
