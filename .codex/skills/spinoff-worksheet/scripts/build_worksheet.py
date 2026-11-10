#!/usr/bin/env python3
"""Run the repository's deterministic spinoff worksheet builder."""

from __future__ import annotations

import runpy
from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]
runpy.run_path(str(ROOT / "spinoff_worksheet.py"), run_name="__main__")
