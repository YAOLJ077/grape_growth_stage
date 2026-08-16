from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT = REPO_ROOT / "data" / "gee" / "weather_download_index_1951.csv"
DEFAULT_OUTPUT = REPO_ROOT / "data" / "gee" / "weather_download_index_1951_gee_20parts.csv"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a Google Earth Engine upload table from the weather download "
            "index, adding deterministic part IDs for split Drive exports."
        )
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--n-parts", type=int, default=20)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.n_parts < 1:
        raise ValueError("--n-parts must be >= 1")

    index = pd.read_csv(args.input)
    index = index.sort_values(["country", "site_id", "year"]).reset_index(drop=True)

    index.insert(0, "gee_part", index.index % args.n_parts)
    index.insert(
        1,
        "gee_part_key",
        index["gee_part"].map(lambda value: f"part_{int(value):02d}_of_{args.n_parts:02d}"),
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    index.to_csv(args.output, index=False)

    print(f"GEE index rows written: {len(index):,}")
    print(index["gee_part_key"].value_counts().sort_index().to_string())
    print(f"Output: {args.output.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
