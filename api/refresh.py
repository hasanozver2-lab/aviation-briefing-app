"""Compatibility alias for the protected refresh function."""

import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(API_DIR))
from briefing import handler

__all__ = ["handler"]
