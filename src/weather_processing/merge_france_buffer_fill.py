from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPAIRED_DIR = REPO_ROOT / "data" / "weather" / "processed" / "era5_land_daily_with_coords"
DEFAULT_SUPPLEMENT = REPO_ROOT / "data" / "weather" / "era5_land_daily_grape_1951_france_missing_buffer_fill.csv"
DEFAULT_OUT_DIR = REPO_ROOT / "data" / "weather" / "processed" / "era5_land_daily_complete"
DEFAULT_SUMMARY = REPO_ROOT / "data" / "weather" / "processed" / "weather_complete_merge_summary.json"

WEATHER_COLUMNS = [
    "temperature_2m",
    "temperature_2m_min",
    "temperature_2m_max",
    "dewpoint_temperature_2m",
    "total_precipitation_sum",
    "surface_pressure",
    "surface_solar_radiation_downwards_sum",
    "u_component_of_wind_10m",
    "v_component_of_wind_10m",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge France ERA5-Land buffer-fill rows into repaired weather exports.")
    parser.add_argument("--repaired-dir", type=Path, default=DEFAULT_REPAIRED_DIR)
    parser.add_argument("--supplement", type=Path, default=DEFAULT_SUPPLEMENT)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--chunksize", type=int, default=200_000)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.supplement.exists():
        raise FileNotFoundError(
            f"Supplement file not found: {args.supplement}. "
            "Download it from GEE and place it at this path, or pass --supplement."
        )

    supplement_cols = ["weather_id", "weather_date", "fill_method", "fill_buffer_m", *WEATHER_COLUMNS]
    supplement = pd.read_csv(args.supplement, usecols=lambda c: c in supplement_cols)
    supplement = supplement.drop_duplicates(["weather_id", "weather_date"])
    supplement_ids = set(supplement["weather_id"].astype(str).unique())

    args.out_dir.mkdir(parents=True, exist_ok=True)
    repaired_files = sorted(args.repaired_dir.glob("era5_land_daily_grape_1951_part_*_of_20.csv"))
    if not repaired_files:
        raise FileNotFoundError(f"No repaired weather files found in {args.repaired_dir}")

    total_rows = 0
    patched_rows = 0
    missing_before = {col: 0 for col in WEATHER_COLUMNS}
    missing_after = {col: 0 for col in WEATHER_COLUMNS}
    output_files = []

    for source_path in repaired_files:
        out_path = args.out_dir / source_path.name
        if out_path.exists():
            out_path.unlink()

        first_chunk = True
        file_rows = 0
        for chunk in pd.read_csv(source_path, chunksize=args.chunksize):
            file_rows += len(chunk)
            total_rows += len(chunk)
            for col in WEATHER_COLUMNS:
                missing_before[col] += int(chunk[col].isna().sum())

            chunk["weather_fill_method"] = "original_point_sample"
            chunk["weather_fill_buffer_m"] = pd.NA

            needs_patch = chunk["weather_id"].astype(str).isin(supplement_ids)
            if needs_patch.any():
                patch = supplement[supplement["weather_id"].astype(str).isin(chunk.loc[needs_patch, "weather_id"].astype(str))]
                chunk = chunk.merge(
                    patch,
                    on=["weather_id", "weather_date"],
                    how="left",
                    suffixes=("", "_fill"),
                    validate="many_to_one",
                )
                matched = chunk["fill_method"].notna()
                patched_rows += int(matched.sum())
                for col in WEATHER_COLUMNS:
                    fill_col = f"{col}_fill"
                    if fill_col in chunk.columns:
                        chunk.loc[matched, col] = chunk.loc[matched, fill_col]
                chunk.loc[matched, "weather_fill_method"] = chunk.loc[matched, "fill_method"]
                chunk.loc[matched, "weather_fill_buffer_m"] = chunk.loc[matched, "fill_buffer_m"]
                drop_cols = [c for c in chunk.columns if c.endswith("_fill") or c in {"fill_method", "fill_buffer_m"}]
                chunk = chunk.drop(columns=drop_cols)

            for col in WEATHER_COLUMNS:
                missing_after[col] += int(chunk[col].isna().sum())

            chunk.to_csv(out_path, mode="w" if first_chunk else "a", header=first_chunk, index=False)
            first_chunk = False

        output_files.append({"file": str(out_path.relative_to(REPO_ROOT)), "rows": file_rows})
        print(f"written {out_path.relative_to(REPO_ROOT)} rows={file_rows:,}")

    summary = {
        "repaired_dir": str(args.repaired_dir.relative_to(REPO_ROOT)),
        "supplement": str(args.supplement.relative_to(REPO_ROOT)),
        "output_dir": str(args.out_dir.relative_to(REPO_ROOT)),
        "n_total_rows": total_rows,
        "n_supplement_rows": int(len(supplement)),
        "n_supplement_site_years": int(len(supplement_ids)),
        "n_patched_daily_rows": patched_rows,
        "missing_before": missing_before,
        "missing_after": missing_after,
        "output_files": output_files,
    }
    args.summary.parent.mkdir(parents=True, exist_ok=True)
    args.summary.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
