"""Pytest configuration: add src/ to sys.path for imports to work correctly.

This avoids the PYTHONPATH=src issue where src/types.py shadows stdlib types module.
"""
import sys
from pathlib import Path

# Add src/ to sys.path (not PYTHONPATH) so imports like "from node.xxx import YYY" work
# while stdlib "types" module is already loaded and not shadowed.
SRC_DIR = Path(__file__).resolve().parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))