#!/usr/bin/env python
"""Run the main final residual-ML workflow."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

try:
    from src.modeling.run_mechanistic_baselines import REPO_ROOT
except ModuleNotFoundError:
    from run_mechanistic_baselines import REPO_ROOT  # type: ignore


DEFAULT_WEATHER_DIR = (
    REPO_ROOT / "data/weather/processed/era5_land_daily_france_germany_evaporative_demand"
)
DEFAULT_DATA_DIR = (
    REPO_ROOT / "results/france_germany_four_stage/residual_machine_learning_main_final"
)
DEFAULT_MODEL_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/main_final_minrmse_four_stage"
)
DEFAULT_FIXED_DIR = (
    REPO_ROOT
    / "results/france_germany_four_stage/residual_modeling/main_final_fixed_stage_models_refit"
)
DEFAULT_REPORT_PATH = REPO_ROOT / "results/report/main_final_fixed_stage_hybrid_results.md"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER_DIR)
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    parser.add_argument("--model-dir", type=Path, default=DEFAULT_MODEL_DIR)
    parser.add_argument("--fixed-dir", type=Path, default=DEFAULT_FIXED_DIR)
    parser.add_argument("--report-path", type=Path, default=DEFAULT_REPORT_PATH)
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--skip-fixed", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def run_command(command: list[str]) -> None:
    print("\n$ " + " ".join(command), flush=True)
    subprocess.run(command, check=True)


def main() -> int:
    args = parse_args()
    overwrite_flag = ["--overwrite"] if args.overwrite else []
    run_command(
        [
            sys.executable,
            "src/modeling/build_residual_ml_dataset.py",
            "--feature-profile",
            "main_final",
            "--weather-dir",
            str(args.weather_dir),
            "--output-dir",
            str(args.data_dir),
            *overwrite_flag,
        ]
    )
    run_command(
        [
            sys.executable,
            "src/modeling/run_residual_ml_models.py",
            "--input-dir",
            str(args.data_dir),
            "--output-dir",
            str(args.model_dir),
            "--search-level",
            "formal",
            "--selection-rule",
            "min_rmse",
            "--n-jobs",
            str(args.n_jobs),
            *overwrite_flag,
        ]
    )
    if not args.skip_fixed:
        run_command(
            [
                sys.executable,
                "src/modeling/run_fixed_stage_hybrid_models.py",
                "--data-dir",
                str(args.data_dir),
                "--selection-source-dir",
                str(args.model_dir),
                "--output-dir",
                str(args.fixed_dir),
                "--report-path",
                str(args.report_path),
                "--stage-algorithm-rule",
                "min_rmse",
                "--n-jobs",
                str(args.n_jobs),
                *overwrite_flag,
            ]
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
