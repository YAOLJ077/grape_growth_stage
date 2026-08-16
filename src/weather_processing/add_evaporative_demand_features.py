#!/usr/bin/env python
"""Add daily FAO-56 ET0 and VPD variables to adjusted ERA5-Land weather."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pandas as pd


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_INPUT_DIR = (
    REPO_ROOT / "data" / "weather" / "processed" / "era5_land_daily_france_germany_adjusted"
)
DEFAULT_OUTPUT_DIR = (
    REPO_ROOT / "data" / "weather" / "processed" / "era5_land_daily_france_germany_evaporative_demand"
)
INPUT_PATTERN = "era5_land_daily_france_germany_adjusted_part_*.parquet"
OUTPUT_PREFIX = "era5_land_daily_france_germany_evaporative_demand"
MAX_N_JOBS = 4
SOLAR_CONSTANT_MJ_M2_MIN = 0.0820
STEFAN_BOLTZMANN_MJ_K4_M2_DAY = 4.903e-9
REFERENCE_CROP_ALBEDO = 0.23
WIND_MEASUREMENT_HEIGHT_M = 10.0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--n-jobs", type=int, default=4)
    parser.add_argument("--compression", default="zstd", choices=("zstd", "snappy", "gzip"))
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def saturation_vapor_pressure_kpa(temperature_c: pd.Series | np.ndarray) -> np.ndarray:
    temperature = np.asarray(temperature_c, dtype=float)
    return 0.6108 * np.exp((17.27 * temperature) / (temperature + 237.3))


def slope_saturation_vapor_pressure_curve_kpa_c(temperature_c: pd.Series | np.ndarray) -> np.ndarray:
    temperature = np.asarray(temperature_c, dtype=float)
    saturation_pressure = saturation_vapor_pressure_kpa(temperature)
    return 4098.0 * saturation_pressure / np.square(temperature + 237.3)


def wind_speed_at_2m(wind_speed_m_s: pd.Series | np.ndarray, measurement_height_m: float = WIND_MEASUREMENT_HEIGHT_M) -> np.ndarray:
    wind_speed = np.asarray(wind_speed_m_s, dtype=float)
    conversion = 4.87 / np.log((67.8 * measurement_height_m) - 5.42)
    return wind_speed * conversion


def extraterrestrial_radiation_mj_m2_day(latitude_deg: pd.Series | np.ndarray, doy: pd.Series | np.ndarray) -> np.ndarray:
    latitude_rad = np.deg2rad(np.asarray(latitude_deg, dtype=float))
    day_of_year = np.asarray(doy, dtype=float)
    inverse_relative_distance = 1.0 + 0.033 * np.cos((2.0 * np.pi / 365.0) * day_of_year)
    solar_declination = 0.409 * np.sin((2.0 * np.pi / 365.0) * day_of_year - 1.39)
    sunset_angle_argument = -np.tan(latitude_rad) * np.tan(solar_declination)
    sunset_hour_angle = np.arccos(np.clip(sunset_angle_argument, -1.0, 1.0))
    seasonal_term = (
        sunset_hour_angle * np.sin(latitude_rad) * np.sin(solar_declination)
        + np.cos(latitude_rad) * np.cos(solar_declination) * np.sin(sunset_hour_angle)
    )
    radiation = (
        (24.0 * 60.0 / np.pi)
        * SOLAR_CONSTANT_MJ_M2_MIN
        * inverse_relative_distance
        * seasonal_term
    )
    return np.maximum(radiation, 0.0)


def fao56_penman_monteith_et0(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    temperature_mean_c = out["temperature_2m_c_adjusted_main_6p5c_km"].astype(float)
    temperature_min_c = out["temperature_2m_min_c_adjusted_main_6p5c_km"].astype(float)
    temperature_max_c = out["temperature_2m_max_c_adjusted_main_6p5c_km"].astype(float)
    dewpoint_c = out["dewpoint_temperature_2m_c"].astype(float)
    pressure_kpa = out["surface_pressure_kpa"].astype(float)
    shortwave_radiation_mj_m2 = out["surface_solar_radiation_downwards_mj_m2"].astype(float).clip(lower=0.0)
    wind_speed_2m_m_s = wind_speed_at_2m(out["wind_speed_10m_m_s"])
    site_elevation_m = out["dem_elevation_m"].astype(float)

    saturation_pressure_min_kpa = saturation_vapor_pressure_kpa(temperature_min_c)
    saturation_pressure_max_kpa = saturation_vapor_pressure_kpa(temperature_max_c)
    saturation_pressure_mean_kpa = (saturation_pressure_min_kpa + saturation_pressure_max_kpa) / 2.0
    saturation_pressure_tmean_kpa = saturation_vapor_pressure_kpa(temperature_mean_c)
    actual_vapor_pressure_kpa = np.minimum(
        saturation_vapor_pressure_kpa(dewpoint_c),
        saturation_pressure_mean_kpa,
    )
    actual_vapor_pressure_kpa = np.maximum(actual_vapor_pressure_kpa, 0.0)

    slope_curve_kpa_c = slope_saturation_vapor_pressure_curve_kpa_c(temperature_mean_c)
    psychrometric_constant_kpa_c = 0.000665 * pressure_kpa
    atmospheric_vpd_kpa = np.maximum(saturation_pressure_mean_kpa - actual_vapor_pressure_kpa, 0.0)
    mean_temperature_vpd_kpa = np.maximum(saturation_pressure_tmean_kpa - actual_vapor_pressure_kpa, 0.0)

    extraterrestrial_radiation = extraterrestrial_radiation_mj_m2_day(out["lat"], out["weather_doy"])
    clear_sky_radiation = np.maximum((0.75 + 0.00002 * site_elevation_m) * extraterrestrial_radiation, 1e-6)
    relative_shortwave = np.clip(shortwave_radiation_mj_m2 / clear_sky_radiation, 0.0, 1.0)
    net_shortwave_radiation = (1.0 - REFERENCE_CROP_ALBEDO) * shortwave_radiation_mj_m2
    temperature_min_k = temperature_min_c + 273.16
    temperature_max_k = temperature_max_c + 273.16
    cloudiness_term = np.maximum((1.35 * relative_shortwave) - 0.35, 0.0)
    humidity_term = np.maximum(0.34 - 0.14 * np.sqrt(actual_vapor_pressure_kpa), 0.0)
    net_longwave_radiation = (
        STEFAN_BOLTZMANN_MJ_K4_M2_DAY
        * ((np.power(temperature_max_k, 4.0) + np.power(temperature_min_k, 4.0)) / 2.0)
        * humidity_term
        * cloudiness_term
    )
    net_radiation = net_shortwave_radiation - net_longwave_radiation
    numerator = (
        0.408 * slope_curve_kpa_c * net_radiation
        + psychrometric_constant_kpa_c
        * (900.0 / (temperature_mean_c + 273.0))
        * wind_speed_2m_m_s
        * atmospheric_vpd_kpa
    )
    denominator = slope_curve_kpa_c + psychrometric_constant_kpa_c * (1.0 + 0.34 * wind_speed_2m_m_s)
    et0 = np.maximum(numerator / denominator, 0.0)

    out["wind_speed_2m_m_s"] = wind_speed_2m_m_s
    out["saturation_vapor_pressure_mean_kpa"] = saturation_pressure_mean_kpa
    out["actual_vapor_pressure_kpa"] = actual_vapor_pressure_kpa
    out["vpd_mean_kpa"] = mean_temperature_vpd_kpa
    out["vpd_fao56_kpa"] = atmospheric_vpd_kpa
    out["extraterrestrial_radiation_mj_m2_day"] = extraterrestrial_radiation
    out["clear_sky_radiation_mj_m2_day"] = clear_sky_radiation
    out["net_radiation_mj_m2_day"] = net_radiation
    out["et0_fao56_penman_monteith_mm_day"] = et0
    out["climatic_water_deficit_fao56_mm_day"] = et0 - out["total_precipitation_mm"].astype(float)
    return out


def output_path_for(source_path: Path, output_dir: Path) -> Path:
    match = re.search(r"(part_\d+_of_\d+)", source_path.stem)
    if not match:
        raise ValueError(f"Cannot parse partition label from {source_path.name}")
    return output_dir / f"{OUTPUT_PREFIX}_{match.group(1)}.parquet"


def summarize_output(frame: pd.DataFrame, output_path: Path) -> dict[str, object]:
    et0 = frame["et0_fao56_penman_monteith_mm_day"]
    vpd = frame["vpd_mean_kpa"]
    return {
        "file": str(output_path.relative_to(REPO_ROOT)),
        "rows": int(len(frame)),
        "weather_ids": int(frame["weather_id"].nunique()),
        "first_date": str(pd.to_datetime(frame["weather_date"]).min().date()),
        "last_date": str(pd.to_datetime(frame["weather_date"]).max().date()),
        "mean_et0_mm_day": float(et0.mean()),
        "max_et0_mm_day": float(et0.max()),
        "mean_vpd_kpa": float(vpd.mean()),
        "max_vpd_kpa": float(vpd.max()),
        "bytes": int(output_path.stat().st_size),
    }


def process_partition(source_path: Path, output_dir: Path, compression: str) -> dict[str, object]:
    frame = pd.read_parquet(source_path)
    augmented = fao56_penman_monteith_et0(frame)
    output_path = output_path_for(source_path, output_dir)
    augmented.to_parquet(output_path, index=False, compression=compression)
    return summarize_output(augmented, output_path)


def write_readme(output_dir: Path) -> None:
    (output_dir / "README.md").write_text(
        """# France-Germany ERA5-Land evaporative-demand layer

Generated by `src/weather_processing/add_evaporative_demand_features.py`.

- Input: elevation-adjusted France-Germany ERA5-Land daily weather partitions.
- ET0: FAO-56 daily Penman-Monteith reference evapotranspiration, mm day-1.
- VPD: daily vapor pressure deficit from adjusted temperature and ERA5-Land dewpoint, kPa.
- Wind: ERA5-Land 10 m wind converted to 2 m using the FAO-56 logarithmic profile.
- Radiation: net radiation estimated from shortwave radiation, latitude, DOY and site elevation.
- Soil moisture is not included here; it should be joined after the GEE soil-moisture export is available.
""",
        encoding="utf-8",
    )


def main() -> int:
    args = parse_args()
    if args.n_jobs < 1:
        raise ValueError("--n-jobs must be at least 1")
    n_jobs = min(args.n_jobs, MAX_N_JOBS)
    files = sorted(args.input_dir.glob(INPUT_PATTERN))
    if not files:
        raise FileNotFoundError(f"No adjusted weather partitions found in {args.input_dir}")

    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        if not args.overwrite:
            raise FileExistsError(f"Output directory is not empty: {args.output_dir}; use --overwrite")
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    started = {
        "input_dir": str(args.input_dir.relative_to(REPO_ROOT)),
        "output_dir": str(args.output_dir.relative_to(REPO_ROOT)),
        "n_input_files": len(files),
        "n_jobs": n_jobs,
        "compression": args.compression,
    }
    print(json.dumps(started, indent=2, ensure_ascii=False))

    output_files: list[dict[str, object]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=n_jobs) as executor:
        futures = [
            executor.submit(process_partition, source_path, args.output_dir, args.compression)
            for source_path in files
        ]
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            output_files.append(result)
            print(f"Evaporative demand: {Path(str(result['file'])).name} rows={result['rows']:,}")

    output_files = sorted(output_files, key=lambda record: str(record["file"]))
    summary = {
        **started,
        "n_output_files": len(output_files),
        "n_daily_rows": int(sum(int(record["rows"]) for record in output_files)),
        "n_site_years": int(sum(int(record["weather_ids"]) for record in output_files)),
        "mean_et0_mm_day": float(np.average(
            [float(record["mean_et0_mm_day"]) for record in output_files],
            weights=[int(record["rows"]) for record in output_files],
        )),
        "mean_vpd_kpa": float(np.average(
            [float(record["mean_vpd_kpa"]) for record in output_files],
            weights=[int(record["rows"]) for record in output_files],
        )),
        "max_et0_mm_day": float(max(float(record["max_et0_mm_day"]) for record in output_files)),
        "max_vpd_kpa": float(max(float(record["max_vpd_kpa"]) for record in output_files)),
        "output_files": output_files,
    }
    (args.output_dir / "evaporative_demand_summary.json").write_text(
        json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    write_readme(args.output_dir)
    print(json.dumps({key: value for key, value in summary.items() if key != "output_files"}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
