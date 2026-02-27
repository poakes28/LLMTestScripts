"""
Shared dependency: ensures project root is on sys.path before any src.* imports.
Import this module first in api/main.py via `import api.deps`.
"""
import sys
from pathlib import Path

_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))
