"""Put the repo root on sys.path so tests can import the `workspace` package.

The engine itself is installed (`pip install -e .`), but household
definitions live outside it deliberately — a household is data about real
people, not library code.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
