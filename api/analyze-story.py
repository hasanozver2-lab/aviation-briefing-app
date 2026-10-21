"""Compatibility alias for hyphenated endpoint in serverless runtimes."""

import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(API_DIR))
from analyze_story import handler

__all__ = ["handler"]
