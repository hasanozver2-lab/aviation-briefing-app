"""Rewrite the derived metric_approx and tier columns of config/entities/*.csv from raw fleet/passenger inputs."""

import sys
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))

from api import entities


def main():
    counts = entities.recompute_derived_columns()
    print("Recomputed:", ", ".join(f"{name}={count}" for name, count in counts.items()))
    entities.load_all()
    print("Entity CSVs are consistent.")


if __name__ == "__main__":
    main()
