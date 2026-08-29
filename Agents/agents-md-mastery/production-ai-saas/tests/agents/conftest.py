"""
conftest.py for AGENTS.md behavior tests.

Sets up the path so tests can import from the project root.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Add the project root to sys.path so tests can import scripts/
ROOT = Path(__file__).parents[2]
sys.path.insert(0, str(ROOT))
