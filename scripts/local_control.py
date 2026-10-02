#!/usr/bin/env python3
"""Source-checkout entry point for the optional Local Control companion."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from local_control.cli import entry

if __name__ == '__main__':
    entry()
