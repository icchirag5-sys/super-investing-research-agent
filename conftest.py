# Makes the project root importable when running `pytest` (modules live at the top level).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
