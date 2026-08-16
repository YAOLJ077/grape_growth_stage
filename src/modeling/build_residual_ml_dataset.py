#!/usr/bin/env python
"""Build leakage-controlled residual-ML tables from frozen mechanistic models."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
from tqdm.auto import tqdm

try:
    from src.modeling.mechanistic_models import brin_daily_chill_action, brin_daily_gdh
    from src.modeling.run_mechanistic_baselines import DEFAULT_WEATHER_DIR, REPO_ROOT
    from src.modeling.select_stage_mechanistic_models import (
        HARVEST_CHAIN_MODEL_ID,
        VERAISON_CHAIN_MODEL_ID,
    )
except ModuleNotFoundError:
    from mechanistic_models import brin_daily_chill_action, brin_daily_gdh  # type: ignore
    from run_mechanistic_baselines import DEFAULT_WEATHER_DIR, REPO_ROOT  # type: ignore
    from select_stage_mechanistic_models import (  # type: ignore
        HARVEST_CHAIN_MODEL_ID,
        VERAISON_CHAIN_MODEL_ID,
    )


DEFAULT_BASELINE_DIR = (
    REPO_ROOT / "data/phenology/derived/modeling/france_germany_four_stage/baseline_mechanistic"
)
DEFAULT_OUTPUT_DIR = REPO_ROOT / "results/france_germany_four_stage/residual_machine_learning"

STATIC_COLUMNS = [
    "record_id", "weather_id", "site_uid", "country", "source", "site_id",
    "lat", "lon", "year", "bbch", "target_stage", "target_stage_order",
    "dem_elevation_m", "era5_grid_id", "era5_grid_elevation_m",
    "site_minus_grid_elevation_m", "abs_site_grid_elevation_difference_m",
    "validation_block_1deg_id", "outer_spatial_fold", "dem_local_median_m",
    "dem_local_std_m", "dem_local_range_m", "slope_deg", "aspect_deg",
    "northness", "eastness", "era5_grid_lat", "era5_grid_lon",
    "era5_grid_land_fraction", "glo30_grid_std_m", "glo30_grid_range_m",
    "coastal_or_island_buffer_fill_flag",
]

WEATHER_COLUMNS = [
    "weather_id", "year", "weather_date", "weather_year", "weather_doy",
    "temperature_2m_c",
    "temperature_2m_min_c", "temperature_2m_max_c",
    "temperature_2m_c_adjusted_main_6p5c_km",
    "temperature_2m_min_c_adjusted_main_6p5c_km",
    "temperature_2m_max_c_adjusted_main_6p5c_km",
    "dewpoint_temperature_2m_c", "total_precipitation_mm",
    "surface_solar_radiation_downwards_mj_m2", "wind_speed_10m_m_s",
]

OPTIONAL_WEATHER_COLUMNS = [
    "vpd_mean_kpa",
    "vpd_fao56_kpa",
    "et0_fao56_penman_monteith_mm_day",
    "climatic_water_deficit_fao56_mm_day",
    "volumetric_soil_water_layer_1",
    "volumetric_soil_water_layer_2",
    "volumetric_soil_water_layer_3",
    "volumetric_soil_water_layer_4",
    "volumetric_soil_water_layer_1_m3_m3",
    "volumetric_soil_water_layer_2_m3_m3",
    "volumetric_soil_water_layer_3_m3_m3",
    "volumetric_soil_water_layer_4_m3_m3",
]

VPD_THRESHOLDS_KPA = (1.5, 2.0)
RAIN_DAY_THRESHOLD_MM = 1.0
SOIL_LAYER_DEPTH_WEIGHTS_M = {
    1: 0.07,
    2: 0.21,
    3: 0.72,
}

WINDOW_PREFIXES = {
    "target_year": "ty",
    "model_start": "ms",
    "trailing_15d": "t15",
    "trailing_30d": "t30",
    "trailing_60d": "t60",
    "previous_aug": "pa",
}

STAGE_WINDOW_PREFIXES = {
    "flowering": "budburst_to_flowering",
    "veraison": "flowering_to_veraison",
    "maturity_or_harvest": "veraison_to_harvest",
}

UPSTREAM_STAGES = {"flowering": "budburst", "veraison": "flowering"}

COMMON_SELECTED_FEATURES = [
    "mechanistic_predicted_doy",
    "dem_elevation_m",
    "dem_local_std_m",
    "northness",
]

STAGE_FEATURE_SETS = {
    "budburst": [
        *COMMON_SELECTED_FEATURES,
        "preseason_chill_days_tmean_0_10c",
        "preseason_frost_degree_days_below0_c_days",
    ],
    "flowering": [
        "mechanistic_predicted_doy",
        "dem_elevation_m",
        "northness",
        "budburst_to_flowering_tmean_adjusted_sd_c",
        "budburst_to_flowering_diurnal_temperature_range_mean_c",
        "budburst_to_flowering_solar_radiation_sum_mj_m2",
        "budburst_to_flowering_cool_degree_days_below10_c_days",
        "budburst_to_flowering_solar_radiation_mean_mj_m2_day",
    ],
    "veraison": [
        *COMMON_SELECTED_FEATURES,
        "flowering_to_veraison_tmean_adjusted_sd_c",
        "flowering_to_veraison_diurnal_temperature_range_mean_c",
        "flowering_to_veraison_heat_degree_days_above30_c_days",
        "flowering_to_veraison_precipitation_sum_mm",
        "flowering_to_veraison_solar_radiation_sum_mj_m2",
        "preveraison_30d_heat_degree_days_above35_c_days",
        "preveraison_30d_vpd_raw_grid_mean_kpa",
    ],
    "maturity_or_harvest": [
        *COMMON_SELECTED_FEATURES,
        "veraison_to_harvest_tmean_adjusted_sd_c",
        "veraison_to_harvest_diurnal_temperature_range_mean_c",
        "veraison_to_harvest_heat_degree_days_above30_c_days",
        "veraison_to_harvest_precipitation_sum_mm",
        "veraison_to_harvest_solar_radiation_sum_mj_m2",
    ],
}

WATER_SPATIAL_STAGE_FEATURE_SETS = {
    "budburst": [
        *STAGE_FEATURE_SETS["budburst"],
        "lat",
        "lon",
    ],
    "flowering": [
        *STAGE_FEATURE_SETS["flowering"],
        "lat",
        "lon",
        "budburst_to_flowering_vpd_fao56_mean_kpa",
        "budburst_to_flowering_et0_fao56_sum_mm",
        "budburst_to_flowering_positive_climatic_water_deficit_sum_mm",
    ],
    "veraison": [
        *STAGE_FEATURE_SETS["veraison"],
        "lat",
        "lon",
        "preveraison_30d_vpd_fao56_mean_kpa",
        "preveraison_30d_et0_fao56_sum_mm",
        "preveraison_30d_positive_climatic_water_deficit_sum_mm",
    ],
    "maturity_or_harvest": [
        *STAGE_FEATURE_SETS["maturity_or_harvest"],
        "lat",
        "lon",
        "veraison_to_harvest_vpd_fao56_mean_kpa",
        "veraison_to_harvest_et0_fao56_sum_mm",
        "veraison_to_harvest_positive_climatic_water_deficit_sum_mm",
    ],
}

WATER_SPATIAL_SOIL_STAGE_FEATURE_SETS = {
    "budburst": WATER_SPATIAL_STAGE_FEATURE_SETS["budburst"],
    "flowering": [
        *WATER_SPATIAL_STAGE_FEATURE_SETS["flowering"],
        "budburst_to_flowering_soil_water_rootzone_l1_l3_mean_m3_m3",
        "budburst_to_flowering_soil_water_rootzone_l1_l3_min_m3_m3",
    ],
    "veraison": [
        *WATER_SPATIAL_STAGE_FEATURE_SETS["veraison"],
        "preveraison_30d_soil_water_rootzone_l1_l3_mean_m3_m3",
        "preveraison_30d_soil_water_rootzone_l1_l3_min_m3_m3",
    ],
    "maturity_or_harvest": [
        *WATER_SPATIAL_STAGE_FEATURE_SETS["maturity_or_harvest"],
        "veraison_to_harvest_soil_water_rootzone_l1_l3_mean_m3_m3",
        "veraison_to_harvest_soil_water_rootzone_l1_l3_min_m3_m3",
    ],
}

WATER_SPATIAL_COUNTRY_ENHANCED_STAGE_FEATURE_SETS = {
    "budburst": [
        *WATER_SPATIAL_STAGE_FEATURE_SETS["budburst"],
        "country_france",
        "country_germany",
        "country_france_x_mechanistic_predicted_doy",
        "budburst_pre15d_gdd5_rate_c_day",
        "budburst_pre30d_gdd5_rate_c_day",
        "budburst_pre15d_frost_degree_days_below0_c_days",
        "budburst_pre30d_frost_degree_days_below0_c_days",
    ],
    "flowering": [
        *WATER_SPATIAL_STAGE_FEATURE_SETS["flowering"],
        "country_france",
        "country_germany",
        "country_france_x_mechanistic_predicted_doy",
        "flowering_predicted_stage_length_days",
        "budburst_to_flowering_gdd0_rate_c_day",
        "budburst_to_flowering_gdd10_rate_c_day",
        "flowering_pre15d_heat_degree_days_above30_c_days",
        "flowering_pre15d_solar_radiation_mean_mj_m2_day",
    ],
    "veraison": [
        *WATER_SPATIAL_STAGE_FEATURE_SETS["veraison"],
        "country_france",
        "country_germany",
        "country_france_x_mechanistic_predicted_doy",
        "veraison_predicted_stage_length_days",
        "flowering_to_veraison_gdd0_rate_c_day",
        "flowering_to_veraison_gdd10_rate_c_day",
        "preveraison_30d_vpd_et0_interaction_kpa_mm",
        "preveraison_30d_vpd_precipitation_interaction_kpa_mm",
        "country_france_x_preveraison_30d_vpd_fao56_mean_kpa",
    ],
    "maturity_or_harvest": WATER_SPATIAL_STAGE_FEATURE_SETS["maturity_or_harvest"],
}

WATER_SPATIAL_ABLATION_REDUCED_STAGE_FEATURE_SETS = {
    "budburst": [
        *WATER_SPATIAL_STAGE_FEATURE_SETS["budburst"],
        "budburst_pre15d_gdd5_rate_c_day",
        "budburst_pre30d_gdd5_rate_c_day",
        "budburst_pre15d_frost_degree_days_below0_c_days",
        "budburst_pre30d_frost_degree_days_below0_c_days",
    ],
    "flowering": [
        *[
            feature
            for feature in WATER_SPATIAL_STAGE_FEATURE_SETS["flowering"]
            if feature not in {"lat", "lon"}
        ],
        "country_france",
        "country_germany",
        "country_france_x_mechanistic_predicted_doy",
        "flowering_predicted_stage_length_days",
        "budburst_to_flowering_gdd0_rate_c_day",
        "budburst_to_flowering_gdd10_rate_c_day",
        "flowering_pre15d_heat_degree_days_above30_c_days",
        "flowering_pre15d_solar_radiation_mean_mj_m2_day",
    ],
    "veraison": [
        *WATER_SPATIAL_STAGE_FEATURE_SETS["veraison"],
        "veraison_predicted_stage_length_days",
        "flowering_to_veraison_gdd0_rate_c_day",
        "flowering_to_veraison_gdd10_rate_c_day",
        "preveraison_30d_vpd_et0_interaction_kpa_mm",
        "preveraison_30d_vpd_precipitation_interaction_kpa_mm",
    ],
    "maturity_or_harvest": [
        *[
            feature
            for feature in WATER_SPATIAL_STAGE_FEATURE_SETS["maturity_or_harvest"]
            if feature not in {"lat", "lon"}
        ],
    ],
}

WATER_SPATIAL_ABLATION_PRUNED_STAGE_FEATURE_SETS = {
    "budburst": WATER_SPATIAL_ABLATION_REDUCED_STAGE_FEATURE_SETS["budburst"],
    "flowering": [
        feature
        for feature in WATER_SPATIAL_ABLATION_REDUCED_STAGE_FEATURE_SETS["flowering"]
        if feature
        not in {
            "budburst_to_flowering_solar_radiation_sum_mj_m2",
            "country_germany",
            "country_france_x_mechanistic_predicted_doy",
            "budburst_to_flowering_gdd0_rate_c_day",
        }
    ],
    "veraison": [
        feature
        for feature in WATER_SPATIAL_ABLATION_REDUCED_STAGE_FEATURE_SETS["veraison"]
        if feature
        not in {
            "flowering_to_veraison_solar_radiation_sum_mj_m2",
            "preveraison_30d_vpd_raw_grid_mean_kpa",
            "flowering_to_veraison_gdd0_rate_c_day",
            "preveraison_30d_vpd_et0_interaction_kpa_mm",
            "preveraison_30d_vpd_precipitation_interaction_kpa_mm",
        }
    ],
    "maturity_or_harvest": WATER_SPATIAL_ABLATION_REDUCED_STAGE_FEATURE_SETS[
        "maturity_or_harvest"
    ],
}

BASELINE_PRE15_BASE_FEATURES = [
    "mechanistic_predicted_doy",
    "dem_elevation_m",
    "dem_local_std_m",
    "northness",
    "lat",
    "lon",
    "country_france",
]

BASELINE_PRE15_STAGE_FEATURE_SETS = {
    "budburst": [
        *BASELINE_PRE15_BASE_FEATURES,
        "budburst_pre15d_gdd5_rate_c_day",
        "budburst_pre15d_cool_degree_days_below10_c_days",
        "budburst_pre15d_frost_degree_days_below0_c_days",
        "budburst_pre15d_solar_radiation_sum_mj_m2",
        "budburst_pre15d_precipitation_sum_mm",
        "budburst_pre15d_rain_days_ge1mm",
        "budburst_pre15d_vpd_fao56_mean_kpa",
    ],
    "flowering": [
        *BASELINE_PRE15_BASE_FEATURES,
        "flowering_pre15d_gdd10_rate_c_day",
        "flowering_pre15d_cool_degree_days_below10_c_days",
        "flowering_pre15d_heat_degree_days_above30_c_days",
        "flowering_pre15d_solar_radiation_sum_mj_m2",
        "flowering_pre15d_precipitation_sum_mm",
        "flowering_pre15d_rain_days_ge1mm",
        "flowering_pre15d_vpd_fao56_mean_kpa",
    ],
    "veraison": [
        *BASELINE_PRE15_BASE_FEATURES,
        "veraison_pre15d_gdd10_rate_c_day",
        "veraison_pre15d_heat_degree_days_above35_c_days",
        "veraison_pre15d_solar_radiation_sum_mj_m2",
        "veraison_pre15d_precipitation_sum_mm",
        "veraison_pre15d_rain_days_ge1mm",
        "veraison_pre15d_vpd_fao56_mean_kpa",
        "veraison_pre15d_vpd_degree_days_above2_kpa_days",
    ],
    "maturity_or_harvest": [
        *BASELINE_PRE15_BASE_FEATURES,
        "maturity_pre15d_gdd10_rate_c_day",
        "maturity_pre15d_heat_degree_days_above30_c_days",
        "maturity_pre15d_solar_radiation_sum_mj_m2",
        "maturity_pre15d_precipitation_sum_mm",
        "maturity_pre15d_rain_days_ge1mm",
        "maturity_pre15d_vpd_fao56_mean_kpa",
        "maturity_pre15d_vpd_degree_days_above2_kpa_days",
    ],
}

BASELINE_PRE15_PLUS_KEY_STAGE_FEATURE_SETS = {
    "budburst": [
        *BASELINE_PRE15_BASE_FEATURES,
        "budburst_pre15d_gdd5_rate_c_day",
        "budburst_pre15d_frost_degree_days_below0_c_days",
        "budburst_pre15d_solar_radiation_sum_mj_m2",
        "budburst_pre15d_rain_days_ge1mm",
        "preseason_chill_days_tmean_0_10c",
        "preseason_frost_degree_days_below0_c_days",
        "budburst_pre30d_gdd5_rate_c_day",
    ],
    "flowering": [
        *BASELINE_PRE15_BASE_FEATURES,
        "flowering_pre15d_heat_degree_days_above30_c_days",
        "flowering_pre15d_solar_radiation_sum_mj_m2",
        "flowering_pre15d_vpd_fao56_mean_kpa",
        "budburst_to_flowering_gdd10_rate_c_day",
        "budburst_to_flowering_diurnal_temperature_range_mean_c",
        "budburst_to_flowering_solar_radiation_mean_mj_m2_day",
        "budburst_to_flowering_vpd_fao56_mean_kpa",
        "budburst_to_flowering_et0_fao56_sum_mm",
        "budburst_to_flowering_positive_climatic_water_deficit_sum_mm",
    ],
    "veraison": [
        *BASELINE_PRE15_BASE_FEATURES,
        "veraison_pre15d_gdd10_rate_c_day",
        "veraison_pre15d_heat_degree_days_above35_c_days",
        "veraison_pre15d_rain_days_ge1mm",
        "veraison_predicted_stage_length_days",
        "flowering_to_veraison_gdd10_rate_c_day",
        "flowering_to_veraison_tmean_adjusted_sd_c",
        "flowering_to_veraison_heat_degree_days_above30_c_days",
        "preveraison_30d_et0_fao56_sum_mm",
        "preveraison_30d_positive_climatic_water_deficit_sum_mm",
    ],
    "maturity_or_harvest": [
        *BASELINE_PRE15_BASE_FEATURES,
        "maturity_pre15d_gdd10_rate_c_day",
        "maturity_pre15d_heat_degree_days_above30_c_days",
        "maturity_pre15d_rain_days_ge1mm",
        "veraison_to_harvest_tmean_adjusted_sd_c",
        "veraison_to_harvest_solar_radiation_sum_mj_m2",
        "veraison_to_harvest_vpd_fao56_mean_kpa",
        "veraison_to_harvest_et0_fao56_sum_mm",
        "veraison_to_harvest_precipitation_sum_mm",
        "veraison_to_harvest_positive_climatic_water_deficit_sum_mm",
    ],
}

PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS = {
    "budburst": [
        "mechanistic_predicted_doy",
        "dem_elevation_m",
        "dem_local_std_m",
        "northness",
        "preseason_chill_days_tmean_0_10c",
        "preseason_frost_degree_days_below0_c_days",
        "lat",
        "lon",
        "budburst_pre15d_gdd5_rate_c_day",
        "budburst_pre30d_gdd5_rate_c_day",
        "budburst_pre15d_frost_degree_days_below0_c_days",
        "budburst_pre15d_solar_radiation_sum_mj_m2",
    ],
    "flowering": [
        "mechanistic_predicted_doy",
        "dem_elevation_m",
        "northness",
        "budburst_to_flowering_tmean_adjusted_sd_c",
        "budburst_to_flowering_diurnal_temperature_range_mean_c",
        "budburst_to_flowering_cool_degree_days_below10_c_days",
        "budburst_to_flowering_solar_radiation_mean_mj_m2_day",
        "budburst_to_flowering_vpd_fao56_mean_kpa",
        "budburst_to_flowering_et0_fao56_sum_mm",
        "budburst_to_flowering_positive_climatic_water_deficit_sum_mm",
        "budburst_to_flowering_gdd10_rate_c_day",
        "flowering_pre15d_solar_radiation_sum_mj_m2",
        "flowering_pre15d_vpd_fao56_mean_kpa",
    ],
    "veraison": [
        "mechanistic_predicted_doy",
        "dem_elevation_m",
        "dem_local_std_m",
        "northness",
        "flowering_to_veraison_tmean_adjusted_sd_c",
        "flowering_to_veraison_diurnal_temperature_range_mean_c",
        "flowering_to_veraison_heat_degree_days_above30_c_days",
        "preveraison_30d_heat_degree_days_above35_c_days",
        "lat",
        "lon",
        "preveraison_30d_positive_climatic_water_deficit_sum_mm",
        "veraison_predicted_stage_length_days",
        "veraison_pre15d_gdd10_rate_c_day",
    ],
    "maturity_or_harvest": [
        "mechanistic_predicted_doy",
        "dem_elevation_m",
        "dem_local_std_m",
        "northness",
        "veraison_to_harvest_tmean_adjusted_sd_c",
        "veraison_to_harvest_precipitation_sum_mm",
        "veraison_to_harvest_solar_radiation_sum_mj_m2",
        "veraison_to_harvest_vpd_fao56_mean_kpa",
        "veraison_to_harvest_positive_climatic_water_deficit_sum_mm",
        "maturity_pre15d_gdd10_rate_c_day",
        "maturity_pre15d_heat_degree_days_above30_c_days",
    ],
}

PRUNED_PLUS_PRE15_SELECTED_V2_STAGE_FEATURE_SETS = {
    "budburst": [
        feature
        for feature in PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS["budburst"]
        if feature != "budburst_pre15d_frost_degree_days_below0_c_days"
    ],
    "flowering": [
        *[
            feature
            for feature in PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS["flowering"]
            if feature != "budburst_to_flowering_tmean_adjusted_sd_c"
        ],
        "flowering_pre30d_diurnal_temperature_range_mean_c",
        "flowering_pre30d_et0_fao56_sum_mm",
    ],
    "veraison": [
        feature
        for feature in PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS["veraison"]
        if feature != "preveraison_30d_heat_degree_days_above35_c_days"
    ],
    "maturity_or_harvest": [
        *[
            feature
            for feature in PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS[
                "maturity_or_harvest"
            ]
            if feature != "veraison_to_harvest_tmean_adjusted_sd_c"
        ],
        "maturity_pre30d_cool_degree_days_below10_c_days",
        "maturity_pre30d_vpd_degree_days_above1p5_kpa_days",
    ],
}

PRUNED_PLUS_PRE15_STAGEWISE_BBCH65_SLIM_STAGE_FEATURE_SETS = {
    "budburst": PRUNED_PLUS_PRE15_SELECTED_V2_STAGE_FEATURE_SETS["budburst"],
    "flowering": [
        feature
        for feature in PRUNED_PLUS_PRE15_SELECTED_V2_STAGE_FEATURE_SETS["flowering"]
        if feature
        not in {
            "flowering_pre15d_solar_radiation_sum_mj_m2",
            "flowering_pre30d_et0_fao56_sum_mm",
        }
    ],
    "veraison": PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS["veraison"],
    "maturity_or_harvest": PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS[
        "maturity_or_harvest"
    ],
}

PRUNED_PLUS_PRE15_STAGEWISE_BBCH81_MINUS_DEM_STAGE_FEATURE_SETS = {
    "budburst": PRUNED_PLUS_PRE15_SELECTED_V2_STAGE_FEATURE_SETS["budburst"],
    "flowering": PRUNED_PLUS_PRE15_SELECTED_V2_STAGE_FEATURE_SETS["flowering"],
    "veraison": [
        feature
        for feature in PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS["veraison"]
        if feature != "dem_elevation_m"
    ],
    "maturity_or_harvest": PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS[
        "maturity_or_harvest"
    ],
}

PRUNED_PLUS_PRE15_FINAL_STAGEWISE_STAGE_FEATURE_SETS = {
    "budburst": PRUNED_PLUS_PRE15_SELECTED_V2_STAGE_FEATURE_SETS["budburst"],
    "flowering": PRUNED_PLUS_PRE15_STAGEWISE_BBCH65_SLIM_STAGE_FEATURE_SETS[
        "flowering"
    ],
    "veraison": PRUNED_PLUS_PRE15_STAGEWISE_BBCH81_MINUS_DEM_STAGE_FEATURE_SETS[
        "veraison"
    ],
    "maturity_or_harvest": PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS[
        "maturity_or_harvest"
    ],
}

FEATURE_PROFILES = {
    "baseline_pre15": BASELINE_PRE15_STAGE_FEATURE_SETS,
    "baseline_pre15_plus_key_stage": BASELINE_PRE15_PLUS_KEY_STAGE_FEATURE_SETS,
    "main_final": PRUNED_PLUS_PRE15_FINAL_STAGEWISE_STAGE_FEATURE_SETS,
    "pruned_plus_pre15_final_stagewise": (
        PRUNED_PLUS_PRE15_FINAL_STAGEWISE_STAGE_FEATURE_SETS
    ),
    "pruned_plus_pre15_selected": PRUNED_PLUS_PRE15_SELECTED_STAGE_FEATURE_SETS,
    "pruned_plus_pre15_stagewise_bbch65_slim": (
        PRUNED_PLUS_PRE15_STAGEWISE_BBCH65_SLIM_STAGE_FEATURE_SETS
    ),
    "pruned_plus_pre15_stagewise_bbch81_minus_dem": (
        PRUNED_PLUS_PRE15_STAGEWISE_BBCH81_MINUS_DEM_STAGE_FEATURE_SETS
    ),
    "pruned_plus_pre15_selected_v2": PRUNED_PLUS_PRE15_SELECTED_V2_STAGE_FEATURE_SETS,
    "selected": STAGE_FEATURE_SETS,
    "water_spatial_ablation_pruned": WATER_SPATIAL_ABLATION_PRUNED_STAGE_FEATURE_SETS,
    "water_spatial_ablation_reduced": WATER_SPATIAL_ABLATION_REDUCED_STAGE_FEATURE_SETS,
    "water_spatial": WATER_SPATIAL_STAGE_FEATURE_SETS,
    "water_spatial_country_enhanced": WATER_SPATIAL_COUNTRY_ENHANCED_STAGE_FEATURE_SETS,
    "water_spatial_soil": WATER_SPATIAL_SOIL_STAGE_FEATURE_SETS,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", type=Path, default=DEFAULT_BASELINE_DIR)
    parser.add_argument("--weather-dir", type=Path, default=DEFAULT_WEATHER_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--reuse-existing-features",
        action="store_true",
        help="Regenerate manifests/training-ready views from an existing combined parquet.",
    )
    parser.add_argument(
        "--feature-profile",
        choices=sorted(FEATURE_PROFILES),
        default="selected",
        help="Feature set profile used to generate training_ready stage tables.",
    )
    return parser.parse_args()


def standardize_chain(
    frame: pd.DataFrame,
    split: str,
    model_id: str,
    stage: str,
) -> pd.DataFrame:
    result = frame.copy()
    result["split"] = split
    result["model_id"] = model_id
    result["stage"] = stage
    result["analysis_set"] = "independent_stage"
    result["selection_eligible"] = True
    if "harvest_forcing_threshold_c_days" in result:
        result["forcing_threshold_c_days"] = result["harvest_forcing_threshold_c_days"]
    elif "veraison_forcing_threshold_c_days" in result:
        result["forcing_threshold_c_days"] = result["veraison_forcing_threshold_c_days"]
    elif "forcing_threshold_c_days" not in result:
        raise ValueError("Chain predictions do not contain a forcing threshold column")
    return result


def selected_training_oof_predictions(baseline_dir: Path) -> pd.DataFrame:
    baseline = pd.read_parquet(baseline_dir / "nested_cv_predictions.parquet")
    baseline = baseline.loc[
        baseline["split"].eq("inner_validation")
        & baseline["analysis_set"].eq("independent_stage")
        & baseline["selection_eligible"].astype(bool)
    ].copy()
    chain_frames = []
    veraison_chain_path = (
        baseline_dir / "bbch81_independent" / "predicted_flowering_to_bbch81_inner_predictions.parquet"
    )
    if veraison_chain_path.exists():
        chain_frames.append(
            standardize_chain(
                pd.read_parquet(veraison_chain_path),
                "inner_validation",
                VERAISON_CHAIN_MODEL_ID,
                "veraison",
            )
        )
    harvest_chain_path = (
        baseline_dir / "bbch89_independent" / "predicted_veraison_to_bbch89_inner_predictions.parquet"
    )
    if harvest_chain_path.exists():
        chain_frames.append(
            standardize_chain(
                pd.read_parquet(harvest_chain_path),
                "inner_validation",
                HARVEST_CHAIN_MODEL_ID,
                "maturity_or_harvest",
            )
        )
    candidates = pd.concat([baseline, *chain_frames], ignore_index=True, sort=False)
    decisions = pd.read_csv(baseline_dir / "stage_model_selection_decisions.csv").rename(
        columns={
            "selected_temperature_branch": "temperature_branch",
            "selected_model_id": "model_id",
        }
    )
    keys = ["outer_fold", "stage", "temperature_branch", "model_id"]
    selected = candidates.merge(
        decisions[keys], on=keys, how="inner", validate="many_to_one"
    )
    selected["dataset_role"] = "training_region_oof"
    return selected


def selected_spatial_test_predictions(baseline_dir: Path) -> pd.DataFrame:
    selected = pd.read_parquet(
        baseline_dir / "formal_selected_model_outer_predictions.parquet"
    ).copy()
    if "predicted_veraison_doy" not in selected:
        selected["predicted_veraison_doy"] = pd.NA
    missing_upstream = (
        selected["stage"].eq("maturity_or_harvest")
        & selected["model_id"].eq(HARVEST_CHAIN_MODEL_ID)
        & selected["predicted_veraison_doy"].isna()
    )
    if missing_upstream.any():
        chain = pd.read_parquet(
            baseline_dir / "bbch89_independent"
            / "predicted_veraison_to_bbch89_outer_predictions.parquet"
        )[
            ["outer_fold", "temperature_branch", "record_id", "predicted_veraison_doy"]
        ].rename(columns={"predicted_veraison_doy": "predicted_veraison_doy_chain"})
        selected = selected.merge(
            chain,
            on=["outer_fold", "temperature_branch", "record_id"],
            how="left",
            validate="one_to_one",
        )
        selected["predicted_veraison_doy"] = selected["predicted_veraison_doy"].fillna(
            selected["predicted_veraison_doy_chain"]
        )
        selected = selected.drop(columns="predicted_veraison_doy_chain")
    selected["dataset_role"] = "spatial_test"
    return selected


def add_chain_starts(frame: pd.DataFrame, baseline_dir: Path) -> pd.DataFrame:
    chain = pd.read_parquet(
        baseline_dir / "bbch89_independent"
        / "predicted_veraison_to_bbch89_inner_predictions.parquet"
    )[
        [
            "outer_fold", "inner_fold", "temperature_branch", "record_id",
            "predicted_veraison_doy",
        ]
    ]
    result = frame.merge(
        chain,
        on=["outer_fold", "inner_fold", "temperature_branch", "record_id"],
        how="left",
        validate="one_to_one",
        suffixes=("", "_chain"),
    )
    if "predicted_veraison_doy_chain" in result:
        result["predicted_veraison_doy"] = result["predicted_veraison_doy"].fillna(
            result["predicted_veraison_doy_chain"]
        )
        result = result.drop(columns="predicted_veraison_doy_chain")
    return result


def attach_upstream_parameters(frame: pd.DataFrame, baseline_dir: Path) -> pd.DataFrame:
    """Attach fold-specific upstream thresholds without using target-fold observations."""
    result = frame.copy()
    result["upstream_stage"] = result["stage"].map(UPSTREAM_STAGES)
    decisions = pd.read_csv(baseline_dir / "stage_model_selection_decisions.csv").rename(
        columns={
            "stage": "upstream_stage",
            "selected_temperature_branch": "upstream_temperature_branch",
            "selected_model_id": "upstream_model_id",
        }
    )
    result = result.merge(
        decisions[
            ["outer_fold", "upstream_stage", "upstream_temperature_branch", "upstream_model_id"]
        ],
        on=["outer_fold", "upstream_stage"],
        how="left",
        validate="many_to_one",
    )
    result["upstream_model_start_doy"] = result["upstream_model_id"].map(
        {
            "budburst__calibrated_gdd5": 1.0,
            "budburst__calibrated_brin_aug1": np.nan,
            "flowering__calibrated_gfv": 60.0,
            VERAISON_CHAIN_MODEL_ID: np.nan,
        }
    )
    result["upstream_model_base_temperature_c"] = result["upstream_model_id"].map(
        {
            "budburst__calibrated_gdd5": 5.0,
            "budburst__calibrated_brin_aug1": 5.0,
            "flowering__calibrated_gfv": 0.0,
            VERAISON_CHAIN_MODEL_ID: 10.0,
        }
    )
    result["upstream_forcing_threshold_c_days"] = np.nan
    result["upstream_chill_threshold_cu"] = np.nan
    fits = pd.read_csv(baseline_dir / "nested_cv_threshold_fits.csv")
    for role, split in (
        ("training_region_oof", "inner_validation"),
        ("spatial_test", "outer_test"),
    ):
        row_mask = result["dataset_role"].eq(role) & result["upstream_model_id"].notna()
        if not row_mask.any():
            continue
        left = result.loc[
            row_mask,
            [
                "residual_row_id", "outer_fold", "inner_fold",
                "upstream_temperature_branch", "upstream_model_id",
            ],
        ].copy()
        fit = fits.loc[fits["split"].eq(split)].copy().rename(
            columns={
                "model_id": "upstream_model_id",
                "forcing_threshold_c_days": "upstream_forcing_threshold_c_days",
            }
        )
        fit = fit.rename(columns={"temperature_branch": "upstream_temperature_branch"})
        keys = ["outer_fold", "upstream_temperature_branch", "upstream_model_id"]
        if split == "inner_validation":
            left["inner_fold"] = pd.to_numeric(left["inner_fold"]).astype(int)
            fit["inner_fold"] = pd.to_numeric(fit["inner_fold"]).astype(int)
            keys.append("inner_fold")
        else:
            fit = fit.drop(columns="inner_fold", errors="ignore")
            left = left.drop(columns="inner_fold")
        fit_columns = [*keys, "upstream_forcing_threshold_c_days"]
        if "chill_threshold_cu" in fit:
            fit = fit.rename(columns={"chill_threshold_cu": "upstream_chill_threshold_cu"})
            fit_columns.append("upstream_chill_threshold_cu")
        matched = left.merge(
            fit[fit_columns],
            on=keys,
            how="left",
            validate="many_to_one",
        )
        if matched["upstream_forcing_threshold_c_days"].isna().any():
            raise ValueError(f"Missing fold-specific upstream threshold for {role}")
        threshold_lookup = matched.set_index("residual_row_id")[
            "upstream_forcing_threshold_c_days"
        ]
        result.loc[row_mask, "upstream_forcing_threshold_c_days"] = result.loc[
            row_mask, "residual_row_id"
        ].map(threshold_lookup)
        if "upstream_chill_threshold_cu" in matched:
            chill_lookup = matched.set_index("residual_row_id")["upstream_chill_threshold_cu"]
            result.loc[row_mask, "upstream_chill_threshold_cu"] = result.loc[
                row_mask, "residual_row_id"
            ].map(chill_lookup)
    maturity = result["stage"].eq("maturity_or_harvest")
    result.loc[maturity, "upstream_model_id"] = "veraison__calibrated_gfv"
    result.loc[maturity, "upstream_temperature_branch"] = result.loc[
        maturity, "temperature_branch"
    ]
    return result


def prepare_residual_rows(baseline_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    training = add_chain_starts(selected_training_oof_predictions(baseline_dir), baseline_dir)
    test = selected_spatial_test_predictions(baseline_dir)
    events = pd.read_csv(
        baseline_dir / "primary_analysis_event_index.csv",
        usecols=STATIC_COLUMNS,
        low_memory=False,
    ).rename(columns={"outer_spatial_fold": "event_assigned_outer_fold"})
    keep = [
        "split", "outer_fold", "inner_fold", "model_id", "stage",
        "temperature_branch", "forcing_threshold_c_days", "record_id",
        "weather_id", "country", "year", "observed_doy", "predicted_doy",
        "threshold_reached", "dataset_role", "predicted_flowering_doy",
        "predicted_veraison_doy",
    ]
    frames = []
    for frame in (training, test):
        for column in keep:
            if column not in frame:
                frame[column] = pd.NA
        subset = frame[keep].copy()
        subset["inner_fold"] = pd.to_numeric(subset["inner_fold"], errors="coerce").astype("Int64")
        frames.append(subset)
    combined = pd.concat(frames, ignore_index=True)
    combined = combined.merge(
        events,
        on=["record_id", "weather_id", "country", "year"],
        how="left",
        validate="many_to_one",
    )
    if combined["site_uid"].isna().any():
        raise ValueError("Some residual rows did not match the primary event index")
    combined["mechanistic_predicted_doy"] = combined["predicted_doy"].astype(float)
    combined["residual_days"] = (
        combined["observed_doy"].astype(float) - combined["mechanistic_predicted_doy"]
    )
    combined["absolute_mechanistic_error_days"] = combined["residual_days"].abs()
    combined["residual_ml_eligible"] = combined["mechanistic_predicted_doy"].notna()
    combined["model_forcing_start_doy"] = np.select(
        [
            combined["stage"].eq("budburst"),
            combined["stage"].isin(["flowering", "veraison"]),
            combined["stage"].eq("maturity_or_harvest"),
        ],
        [1.0, 60.0, combined["predicted_veraison_doy"].astype(float) + 1.0],
        default=np.nan,
    )
    veraison_chain = (
        combined["stage"].eq("veraison")
        & combined["model_id"].eq(VERAISON_CHAIN_MODEL_ID)
        & combined["predicted_flowering_doy"].notna()
    )
    combined.loc[veraison_chain, "model_forcing_start_doy"] = (
        combined.loc[veraison_chain, "predicted_flowering_doy"].astype(float) + 1.0
    )
    combined["residual_row_id"] = (
        combined["dataset_role"].astype(str)
        + "|test_fold=" + combined["outer_fold"].astype(str)
        + "|" + combined["record_id"].astype(str)
    )
    if combined["residual_row_id"].duplicated().any():
        raise ValueError("Residual row identifiers are not unique")
    combined["country_network"] = combined["country"].map(
        {"France": "France_TEMPO", "Germany": "Germany_DWD"}
    )
    combined = attach_upstream_parameters(combined, baseline_dir)
    training = combined.loc[combined["dataset_role"].eq("training_region_oof")].copy()
    test = combined.loc[combined["dataset_role"].eq("spatial_test")].copy()
    if not training["event_assigned_outer_fold"].ne(training["outer_fold"]).all():
        raise ValueError("Training residuals contain records from the current spatial test fold")
    if not test["event_assigned_outer_fold"].eq(test["outer_fold"]).all():
        raise ValueError("Spatial-test residual rows do not match their assigned test fold")
    return training, test


def saturation_vapor_pressure_kpa(temperature_c: np.ndarray) -> np.ndarray:
    return 0.6108 * np.exp((17.27 * temperature_c) / (temperature_c + 237.3))


def vpd_threshold_suffix(threshold: float) -> str:
    if float(threshold).is_integer():
        return str(int(threshold))
    return str(threshold).replace(".", "p")


def feature_sets_for_profile(profile: str) -> dict[str, list[str]]:
    try:
        return FEATURE_PROFILES[profile]
    except KeyError as error:
        raise ValueError(f"Unknown feature profile: {profile}") from error


def display_path(path: Path) -> str:
    resolved = path.resolve()
    try:
        return str(resolved.relative_to(REPO_ROOT))
    except ValueError:
        return str(resolved)


def weather_partition_files(weather_dir: Path) -> list[Path]:
    patterns = [
        "era5_land_daily_france_germany_evaporative_demand_part_*.parquet",
        "era5_land_daily_france_germany_adjusted_part_*.parquet",
    ]
    for pattern in patterns:
        files = sorted(weather_dir.glob(pattern))
        if files:
            return files
    raise FileNotFoundError(f"No supported weather partitions found in {weather_dir}")


def parquet_column_names(path: Path) -> set[str]:
    import pyarrow.parquet as pq

    return set(pq.ParquetFile(path).schema.names)


def read_weather_partition(path: Path) -> pd.DataFrame:
    available = parquet_column_names(path)
    missing_required = set(WEATHER_COLUMNS).difference(available)
    if missing_required:
        raise ValueError(f"{path.name} is missing required weather columns: {sorted(missing_required)}")
    columns = [column for column in WEATHER_COLUMNS + OPTIONAL_WEATHER_COLUMNS if column in available]
    weather = pd.read_parquet(path, columns=columns)
    for column in OPTIONAL_WEATHER_COLUMNS:
        if column not in weather.columns:
            weather[column] = np.nan
    return weather


def finite_mean(values: np.ndarray) -> float:
    return float(np.nanmean(values)) if np.isfinite(values).any() else np.nan


def finite_sum(values: np.ndarray) -> float:
    return float(np.nansum(values)) if np.isfinite(values).any() else np.nan


def finite_min(values: np.ndarray) -> float:
    return float(np.nanmin(values)) if np.isfinite(values).any() else np.nan


def first_available_array(frame: pd.DataFrame, candidates: tuple[str, ...]) -> np.ndarray:
    for column in candidates:
        if column in frame.columns:
            return frame[column].to_numpy(float)
    return np.repeat(np.nan, len(frame))


def soil_layer_array(frame: pd.DataFrame, layer: int) -> np.ndarray:
    return first_available_array(
        frame,
        (
            f"volumetric_soil_water_layer_{layer}_m3_m3",
            f"volumetric_soil_water_layer_{layer}",
        ),
    )


def rootzone_soil_water_l1_l3(frame: pd.DataFrame) -> np.ndarray:
    layer_values = []
    weights = []
    for layer, weight in SOIL_LAYER_DEPTH_WEIGHTS_M.items():
        values = soil_layer_array(frame, layer)
        if not np.isfinite(values).any():
            return np.repeat(np.nan, len(frame))
        layer_values.append(values)
        weights.append(weight)
    matrix = np.vstack(layer_values).T
    return np.average(matrix, axis=1, weights=np.asarray(weights, dtype=float))


def summarize_window(group: pd.DataFrame, mask: np.ndarray) -> dict[str, float]:
    if not mask.any():
        result = {
            "n_days": 0.0,
            "tmean_adjusted_mean_c": np.nan,
            "tmean_adjusted_sd_c": np.nan,
            "tmin_adjusted_min_c": np.nan,
            "tmax_adjusted_max_c": np.nan,
            "diurnal_temperature_range_mean_c": np.nan,
            "cool_days_tmean_lt10c": np.nan,
            "cool_degree_days_below10_c_days": np.nan,
            "frost_days": np.nan,
            "frost_degree_days_below0_c_days": np.nan,
            "hot_days_ge30": np.nan,
            "hot_days_ge35": np.nan,
            "heat_degree_days_above30_c_days": np.nan,
            "heat_degree_days_above35_c_days": np.nan,
            "gdd0_adjusted_c_days": np.nan,
            "gdd5_adjusted_c_days": np.nan,
            "gdd10_adjusted_c_days": np.nan,
            "precipitation_sum_mm": np.nan,
            "rain_days_ge1mm": np.nan,
            "solar_radiation_sum_mj_m2": np.nan,
            "solar_radiation_mean_mj_m2_day": np.nan,
            "vpd_raw_grid_mean_kpa": np.nan,
            "vpd_mean_kpa": np.nan,
            "vpd_fao56_mean_kpa": np.nan,
            "et0_fao56_sum_mm": np.nan,
            "et0_fao56_mean_mm_day": np.nan,
            "climatic_water_deficit_sum_mm": np.nan,
            "positive_climatic_water_deficit_sum_mm": np.nan,
            "soil_water_rootzone_l1_l3_mean_m3_m3": np.nan,
            "soil_water_rootzone_l1_l3_min_m3_m3": np.nan,
            "wind_speed_mean_m_s": np.nan,
        }
        for layer in range(1, 5):
            result[f"soil_water_layer{layer}_mean_m3_m3"] = np.nan
            result[f"soil_water_layer{layer}_min_m3_m3"] = np.nan
        for threshold in VPD_THRESHOLDS_KPA:
            suffix = vpd_threshold_suffix(threshold)
            result[f"vpd_days_above{suffix}_kpa"] = np.nan
            result[f"vpd_degree_days_above{suffix}_kpa_days"] = np.nan
        return result
    subset = group.loc[mask]
    tmean = subset["temperature_2m_c_adjusted_main_6p5c_km"].to_numpy(float)
    tmin = subset["temperature_2m_min_c_adjusted_main_6p5c_km"].to_numpy(float)
    tmax = subset["temperature_2m_max_c_adjusted_main_6p5c_km"].to_numpy(float)
    dewpoint = subset["dewpoint_temperature_2m_c"].to_numpy(float)
    raw_tmean = subset["temperature_2m_c"].to_numpy(float)
    fallback_vpd = np.maximum(
        saturation_vapor_pressure_kpa(raw_tmean) - saturation_vapor_pressure_kpa(dewpoint),
        0.0,
    )
    vpd = first_available_array(subset, ("vpd_mean_kpa",))
    if not np.isfinite(vpd).any():
        vpd = fallback_vpd
    vpd_fao56 = first_available_array(subset, ("vpd_fao56_kpa",))
    if not np.isfinite(vpd_fao56).any():
        vpd_fao56 = vpd
    radiation = subset["surface_solar_radiation_downwards_mj_m2"].to_numpy(float)
    et0 = first_available_array(subset, ("et0_fao56_penman_monteith_mm_day",))
    water_deficit = first_available_array(subset, ("climatic_water_deficit_fao56_mm_day",))
    if not np.isfinite(water_deficit).any() and np.isfinite(et0).any():
        water_deficit = et0 - subset["total_precipitation_mm"].to_numpy(float)
    rootzone = rootzone_soil_water_l1_l3(subset)
    precipitation = subset["total_precipitation_mm"].to_numpy(float)
    result = {
        "n_days": float(len(subset)),
        "tmean_adjusted_mean_c": float(np.nanmean(tmean)),
        "tmean_adjusted_sd_c": float(np.nanstd(tmean, ddof=0)),
        "tmin_adjusted_min_c": float(np.nanmin(tmin)),
        "tmax_adjusted_max_c": float(np.nanmax(tmax)),
        "diurnal_temperature_range_mean_c": float(np.nanmean(tmax - tmin)),
        "cool_days_tmean_lt10c": float(np.sum(tmean < 10.0)),
        "cool_degree_days_below10_c_days": float(np.nansum(np.maximum(10.0 - tmean, 0.0))),
        "frost_days": float(np.sum(tmin < 0.0)),
        "frost_degree_days_below0_c_days": float(np.nansum(np.maximum(-tmin, 0.0))),
        "hot_days_ge30": float(np.sum(tmax >= 30.0)),
        "hot_days_ge35": float(np.sum(tmax >= 35.0)),
        "heat_degree_days_above30_c_days": float(np.nansum(np.maximum(tmax - 30.0, 0.0))),
        "heat_degree_days_above35_c_days": float(np.nansum(np.maximum(tmax - 35.0, 0.0))),
        "gdd0_adjusted_c_days": float(np.nansum(np.maximum(tmean, 0.0))),
        "gdd5_adjusted_c_days": float(np.nansum(np.maximum(tmean - 5.0, 0.0))),
        "gdd10_adjusted_c_days": float(np.nansum(np.maximum(tmean - 10.0, 0.0))),
        "precipitation_sum_mm": float(np.nansum(precipitation)),
        "rain_days_ge1mm": float(np.sum(precipitation >= RAIN_DAY_THRESHOLD_MM)),
        "solar_radiation_sum_mj_m2": float(np.nansum(radiation)),
        "solar_radiation_mean_mj_m2_day": float(np.nanmean(radiation)),
        "vpd_raw_grid_mean_kpa": finite_mean(fallback_vpd),
        "vpd_mean_kpa": finite_mean(vpd),
        "vpd_fao56_mean_kpa": finite_mean(vpd_fao56),
        "et0_fao56_sum_mm": finite_sum(et0),
        "et0_fao56_mean_mm_day": finite_mean(et0),
        "climatic_water_deficit_sum_mm": finite_sum(water_deficit),
        "positive_climatic_water_deficit_sum_mm": finite_sum(np.maximum(water_deficit, 0.0)),
        "soil_water_rootzone_l1_l3_mean_m3_m3": finite_mean(rootzone),
        "soil_water_rootzone_l1_l3_min_m3_m3": finite_min(rootzone),
        "wind_speed_mean_m_s": float(np.nanmean(subset["wind_speed_10m_m_s"])),
    }
    for layer in range(1, 5):
        soil = soil_layer_array(subset, layer)
        result[f"soil_water_layer{layer}_mean_m3_m3"] = finite_mean(soil)
        result[f"soil_water_layer{layer}_min_m3_m3"] = finite_min(soil)
    for threshold in VPD_THRESHOLDS_KPA:
        suffix = vpd_threshold_suffix(threshold)
        result[f"vpd_days_above{suffix}_kpa"] = float(np.sum(vpd > threshold))
        result[f"vpd_degree_days_above{suffix}_kpa_days"] = float(
            np.nansum(np.maximum(vpd - threshold, 0.0))
        )
    return result


def feature_masks(
    group: pd.DataFrame, year: int, cutoff_doy: int, start_doy: int
) -> dict[str, np.ndarray]:
    dates = group["weather_date"].to_numpy(dtype="datetime64[D]")
    cutoff_date = np.datetime64(pd.Timestamp(year, 1, 1) + pd.Timedelta(days=cutoff_doy - 1), "D")
    year_start = np.datetime64(pd.Timestamp(year, 1, 1), "D")
    model_start = np.datetime64(pd.Timestamp(year, 1, 1) + pd.Timedelta(days=start_doy - 1), "D")
    previous_aug = np.datetime64(pd.Timestamp(year - 1, 8, 1), "D")
    return {
        "target_year": (dates >= year_start) & (dates <= cutoff_date),
        "model_start": (dates >= model_start) & (dates <= cutoff_date),
        "trailing_15d": (dates >= cutoff_date - np.timedelta64(14, "D")) & (dates <= cutoff_date),
        "trailing_30d": (dates >= cutoff_date - np.timedelta64(29, "D")) & (dates <= cutoff_date),
        "trailing_60d": (dates >= cutoff_date - np.timedelta64(59, "D")) & (dates <= cutoff_date),
        "previous_aug": (dates >= previous_aug) & (dates <= cutoff_date),
    }


def predicted_stage_window_mask(
    group: pd.DataFrame,
    year: int,
    upstream_doy: float,
    current_doy: float,
) -> np.ndarray:
    """Return days after the OOF upstream prediction through the current prediction."""
    dates = group["weather_date"].to_numpy(dtype="datetime64[D]")
    if not np.isfinite(upstream_doy) or not np.isfinite(current_doy):
        return np.zeros(len(group), dtype=bool)
    upstream = int(round(upstream_doy))
    current = int(round(current_doy))
    if current <= upstream:
        return np.zeros(len(group), dtype=bool)
    year_start = pd.Timestamp(year, 1, 1)
    start_date = np.datetime64(year_start + pd.Timedelta(days=upstream), "D")
    end_date = np.datetime64(year_start + pd.Timedelta(days=current - 1), "D")
    return (dates >= start_date) & (dates <= end_date)


def build_weather_features(rows: pd.DataFrame, weather_dir: Path) -> pd.DataFrame:
    requests = rows.loc[
        rows["residual_ml_eligible"],
        [
            "residual_row_id", "weather_id", "year", "mechanistic_predicted_doy",
            "model_forcing_start_doy", "stage", "lat", "predicted_veraison_doy",
            "upstream_model_start_doy", "upstream_model_base_temperature_c",
            "upstream_forcing_threshold_c_days",
            "upstream_model_id", "upstream_temperature_branch",
            "upstream_chill_threshold_cu",
        ],
    ].copy()
    request_ids = set(requests["weather_id"].astype(str))
    records: list[dict[str, object]] = []
    files = weather_partition_files(weather_dir)
    for path in tqdm(files, desc="Residual weather features", unit="file"):
        weather = read_weather_partition(path)
        weather["weather_id"] = weather["weather_id"].astype(str)
        weather = weather.loc[weather["weather_id"].isin(request_ids)].copy()
        if weather.empty:
            continue
        weather["weather_date"] = pd.to_datetime(weather["weather_date"])
        grouped = {key: value.sort_values("weather_date") for key, value in weather.groupby("weather_id")}
        part_requests = requests.loc[requests["weather_id"].isin(grouped)]
        for request in part_requests.itertuples(index=False):
            group = grouped[str(request.weather_id)]
            cutoff = int(round(float(request.mechanistic_predicted_doy)))
            start = int(round(float(request.model_forcing_start_doy)))
            row: dict[str, object] = {"residual_row_id": request.residual_row_id}
            for window, mask in feature_masks(group, int(request.year), cutoff, start).items():
                prefix = WINDOW_PREFIXES[window]
                for name, value in summarize_window(group, mask).items():
                    row[f"{prefix}_{name}"] = value
            dates = group["weather_date"].to_numpy(dtype="datetime64[D]")
            chill_start = np.datetime64(pd.Timestamp(int(request.year) - 1, 8, 1), "D")
            chill_end = np.datetime64(pd.Timestamp(int(request.year), 2, 29 if pd.Timestamp(int(request.year), 12, 31).is_leap_year else 28), "D")
            chill_mask = (dates >= chill_start) & (dates <= chill_end)
            chill_temperature = group.loc[
                chill_mask, "temperature_2m_c_adjusted_main_6p5c_km"
            ].to_numpy(float)
            row["preseason_chill_days_tmean_0_10c"] = float(
                np.sum((chill_temperature >= 0.0) & (chill_temperature <= 10.0))
            )
            chill_tmin = group.loc[
                chill_mask, "temperature_2m_min_c_adjusted_main_6p5c_km"
            ].to_numpy(float)
            row["preseason_frost_degree_days_below0_c_days"] = float(
                np.nansum(np.maximum(-chill_tmin, 0.0))
            )
            row["forcing_temperature_variability_c"] = row[
                "ty_tmean_adjusted_sd_c"
            ]

            upstream_prediction = np.nan
            if request.stage == "maturity_or_harvest" and pd.notna(request.predicted_veraison_doy):
                upstream_prediction = float(request.predicted_veraison_doy)
            elif (
                request.upstream_model_id == "budburst__calibrated_brin_aug1"
                and pd.notna(request.upstream_chill_threshold_cu)
                and pd.notna(request.upstream_forcing_threshold_c_days)
            ):
                if request.upstream_temperature_branch == "raw":
                    minimum = group["temperature_2m_min_c"].to_numpy(float)
                    maximum = group["temperature_2m_max_c"].to_numpy(float)
                else:
                    minimum = group[
                        "temperature_2m_min_c_adjusted_main_6p5c_km"
                    ].to_numpy(float)
                    maximum = group[
                        "temperature_2m_max_c_adjusted_main_6p5c_km"
                    ].to_numpy(float)
                chill = np.cumsum(brin_daily_chill_action(minimum, maximum, q10=2.17))
                break_position = int(
                    np.searchsorted(
                        chill, float(request.upstream_chill_threshold_cu), side="left"
                    )
                )
                daily_gdh = brin_daily_gdh(
                    minimum, maximum, base_temperature_c=5.0, maximum_temperature_c=25.0
                )
                cumulative_gdh = np.cumsum(daily_gdh)
                target_positions = np.flatnonzero(
                    group["weather_year"].to_numpy(int) == int(request.year)
                )
                if break_position < len(group) and len(target_positions):
                    offset = cumulative_gdh[break_position - 1] if break_position > 0 else 0.0
                    forcing = np.maximum(cumulative_gdh[target_positions] - offset, 0.0)
                    forcing[target_positions < break_position] = 0.0
                    position = int(
                        np.searchsorted(
                            np.maximum.accumulate(forcing),
                            float(request.upstream_forcing_threshold_c_days),
                            side="left",
                        )
                    )
                    if position < len(target_positions):
                        upstream_prediction = float(
                            group.iloc[target_positions[position]]["weather_doy"]
                        )
            elif pd.notna(request.upstream_forcing_threshold_c_days):
                target_year = group.loc[group["weather_year"].eq(int(request.year))]
                target_year = target_year.loc[
                    target_year["weather_doy"].ge(int(request.upstream_model_start_doy))
                ]
                temperature = target_year[
                    "temperature_2m_c_adjusted_main_6p5c_km"
                ].to_numpy(float)
                cumulative = np.cumsum(
                    np.maximum(
                        temperature - float(request.upstream_model_base_temperature_c), 0.0
                    )
                )
                position = int(
                    np.searchsorted(
                        cumulative, float(request.upstream_forcing_threshold_c_days), side="left"
                    )
                )
                if position < len(target_year):
                    upstream_prediction = float(target_year.iloc[position]["weather_doy"])
            row["upstream_mechanistic_predicted_doy"] = upstream_prediction
            row["mechanistic_interval_from_upstream_days"] = (
                float(request.mechanistic_predicted_doy) - upstream_prediction
                if np.isfinite(upstream_prediction)
                else np.nan
            )
            stage_prefix = STAGE_WINDOW_PREFIXES.get(str(request.stage))
            if stage_prefix is not None:
                stage_mask = predicted_stage_window_mask(
                    group,
                    int(request.year),
                    upstream_prediction,
                    float(request.mechanistic_predicted_doy),
                )
                for name, value in summarize_window(group, stage_mask).items():
                    row[f"{stage_prefix}_{name}"] = value
            if request.stage == "flowering":
                row["flowering_pre15d_cool_days_tmean_lt10c"] = row[
                    "t15_cool_days_tmean_lt10c"
                ]
                row["flowering_pre15d_frost_degree_days_below0_c_days"] = row[
                    "t15_frost_degree_days_below0_c_days"
                ]
                row["flowering_pre15d_vpd_fao56_mean_kpa"] = row[
                    "t15_vpd_fao56_mean_kpa"
                ]
                row["flowering_pre15d_et0_fao56_sum_mm"] = row[
                    "t15_et0_fao56_sum_mm"
                ]
                row["flowering_pre15d_positive_climatic_water_deficit_sum_mm"] = row[
                    "t15_positive_climatic_water_deficit_sum_mm"
                ]
            elif request.stage == "veraison":
                row["preveraison_30d_heat_degree_days_above35_c_days"] = row[
                    "t30_heat_degree_days_above35_c_days"
                ]
                row["preveraison_30d_vpd_raw_grid_mean_kpa"] = row[
                    "t30_vpd_raw_grid_mean_kpa"
                ]
                row["preveraison_30d_precipitation_sum_mm"] = row[
                    "t30_precipitation_sum_mm"
                ]
                row["preveraison_30d_vpd_fao56_mean_kpa"] = row[
                    "t30_vpd_fao56_mean_kpa"
                ]
                row["preveraison_30d_et0_fao56_sum_mm"] = row[
                    "t30_et0_fao56_sum_mm"
                ]
                row["preveraison_30d_positive_climatic_water_deficit_sum_mm"] = row[
                    "t30_positive_climatic_water_deficit_sum_mm"
                ]
                row["preveraison_30d_soil_water_rootzone_l1_l3_mean_m3_m3"] = row[
                    "t30_soil_water_rootzone_l1_l3_mean_m3_m3"
                ]
                row["preveraison_30d_soil_water_rootzone_l1_l3_min_m3_m3"] = row[
                    "t30_soil_water_rootzone_l1_l3_min_m3_m3"
                ]
            records.append(row)
    features = pd.DataFrame.from_records(records)
    if features["residual_row_id"].duplicated().any():
        raise ValueError("Weather feature rows are duplicated")
    missing = set(requests["residual_row_id"]).difference(set(features["residual_row_id"]))
    if missing:
        raise ValueError(f"Weather features are missing for {len(missing)} eligible residual rows")
    return features


def daylength_hours(latitude_deg: pd.Series, doy: pd.Series) -> pd.Series:
    latitude = np.deg2rad(latitude_deg.astype(float).to_numpy())
    day = doy.astype(float).to_numpy()
    declination = 0.409 * np.sin((2.0 * np.pi * day / 365.0) - 1.39)
    cosine = np.clip(-np.tan(latitude) * np.tan(declination), -1.0, 1.0)
    return pd.Series(24.0 * np.arccos(cosine) / np.pi, index=latitude_deg.index)


def safe_rate(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    denominator = denominator.astype(float)
    return numerator.astype(float).where(denominator.gt(0.0)) / denominator.where(
        denominator.gt(0.0)
    )


def add_derived_residual_features(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result["country_france"] = result["country"].eq("France").astype(float)
    result["country_germany"] = result["country"].eq("Germany").astype(float)
    result["country_france_x_mechanistic_predicted_doy"] = (
        result["country_france"] * result["mechanistic_predicted_doy"].astype(float)
    )
    result["budburst_pre15d_gdd5_rate_c_day"] = safe_rate(
        result["t15_gdd5_adjusted_c_days"], result["t15_n_days"]
    )
    result["budburst_pre30d_gdd5_rate_c_day"] = safe_rate(
        result["t30_gdd5_adjusted_c_days"], result["t30_n_days"]
    )
    result["budburst_pre15d_frost_degree_days_below0_c_days"] = result[
        "t15_frost_degree_days_below0_c_days"
    ].astype(float)
    result["budburst_pre30d_frost_degree_days_below0_c_days"] = result[
        "t30_frost_degree_days_below0_c_days"
    ].astype(float)
    result["flowering_predicted_stage_length_days"] = result[
        "budburst_to_flowering_n_days"
    ].astype(float)
    result["budburst_to_flowering_gdd0_rate_c_day"] = safe_rate(
        result["budburst_to_flowering_gdd0_adjusted_c_days"],
        result["budburst_to_flowering_n_days"],
    )
    result["budburst_to_flowering_gdd10_rate_c_day"] = safe_rate(
        result["budburst_to_flowering_gdd10_adjusted_c_days"],
        result["budburst_to_flowering_n_days"],
    )
    result["flowering_pre15d_heat_degree_days_above30_c_days"] = result[
        "t15_heat_degree_days_above30_c_days"
    ].astype(float)
    result["flowering_pre15d_solar_radiation_mean_mj_m2_day"] = result[
        "t15_solar_radiation_mean_mj_m2_day"
    ].astype(float)
    result["veraison_predicted_stage_length_days"] = result[
        "flowering_to_veraison_n_days"
    ].astype(float)
    result["flowering_to_veraison_gdd0_rate_c_day"] = safe_rate(
        result["flowering_to_veraison_gdd0_adjusted_c_days"],
        result["flowering_to_veraison_n_days"],
    )
    result["flowering_to_veraison_gdd10_rate_c_day"] = safe_rate(
        result["flowering_to_veraison_gdd10_adjusted_c_days"],
        result["flowering_to_veraison_n_days"],
    )
    result["preveraison_30d_vpd_et0_interaction_kpa_mm"] = (
        result["preveraison_30d_vpd_fao56_mean_kpa"].astype(float)
        * result["preveraison_30d_et0_fao56_sum_mm"].astype(float)
    )
    result["preveraison_30d_vpd_precipitation_interaction_kpa_mm"] = (
        result["preveraison_30d_vpd_fao56_mean_kpa"].astype(float)
        * result["preveraison_30d_precipitation_sum_mm"].astype(float)
    )
    result["country_france_x_preveraison_30d_vpd_fao56_mean_kpa"] = (
        result["country_france"] * result["preveraison_30d_vpd_fao56_mean_kpa"].astype(float)
    )
    pre15_prefix_by_stage = {
        "budburst": "budburst_pre15d",
        "flowering": "flowering_pre15d",
        "veraison": "veraison_pre15d",
        "maturity_or_harvest": "maturity_pre15d",
    }
    pre15_aliases = {
        "cool_degree_days_below10_c_days": "cool_degree_days_below10_c_days",
        "frost_degree_days_below0_c_days": "frost_degree_days_below0_c_days",
        "heat_degree_days_above30_c_days": "heat_degree_days_above30_c_days",
        "heat_degree_days_above35_c_days": "heat_degree_days_above35_c_days",
        "solar_radiation_sum_mj_m2": "solar_radiation_sum_mj_m2",
        "precipitation_sum_mm": "precipitation_sum_mm",
        "rain_days_ge1mm": "rain_days_ge1mm",
        "vpd_fao56_mean_kpa": "vpd_fao56_mean_kpa",
        "vpd_degree_days_above2_kpa_days": "vpd_degree_days_above2_kpa_days",
        "et0_fao56_sum_mm": "et0_fao56_sum_mm",
        "positive_climatic_water_deficit_sum_mm": (
            "positive_climatic_water_deficit_sum_mm"
        ),
    }
    for stage, prefix in pre15_prefix_by_stage.items():
        mask = result["stage"].eq(stage)
        result[f"{prefix}_gdd5_rate_c_day"] = np.nan
        result.loc[mask, f"{prefix}_gdd5_rate_c_day"] = safe_rate(
            result.loc[mask, "t15_gdd5_adjusted_c_days"],
            result.loc[mask, "t15_n_days"],
        )
        result[f"{prefix}_gdd10_rate_c_day"] = np.nan
        result.loc[mask, f"{prefix}_gdd10_rate_c_day"] = safe_rate(
            result.loc[mask, "t15_gdd10_adjusted_c_days"],
            result.loc[mask, "t15_n_days"],
        )
        for source, suffix in pre15_aliases.items():
            result[f"{prefix}_{suffix}"] = np.nan
            result.loc[mask, f"{prefix}_{suffix}"] = result.loc[
                mask, f"t15_{source}"
            ].astype(float)
    pre30_prefix_by_stage = {
        "budburst": "budburst_pre30d",
        "flowering": "flowering_pre30d",
        "veraison": "veraison_pre30d",
        "maturity_or_harvest": "maturity_pre30d",
    }
    pre30_aliases = {
        "tmean_adjusted_sd_c": "tmean_adjusted_sd_c",
        "diurnal_temperature_range_mean_c": "diurnal_temperature_range_mean_c",
        "cool_degree_days_below10_c_days": "cool_degree_days_below10_c_days",
        "frost_degree_days_below0_c_days": "frost_degree_days_below0_c_days",
        "heat_degree_days_above30_c_days": "heat_degree_days_above30_c_days",
        "heat_degree_days_above35_c_days": "heat_degree_days_above35_c_days",
        "solar_radiation_sum_mj_m2": "solar_radiation_sum_mj_m2",
        "precipitation_sum_mm": "precipitation_sum_mm",
        "rain_days_ge1mm": "rain_days_ge1mm",
        "vpd_fao56_mean_kpa": "vpd_fao56_mean_kpa",
        "vpd_degree_days_above1p5_kpa_days": (
            "vpd_degree_days_above1p5_kpa_days"
        ),
        "vpd_degree_days_above2_kpa_days": "vpd_degree_days_above2_kpa_days",
        "et0_fao56_sum_mm": "et0_fao56_sum_mm",
        "positive_climatic_water_deficit_sum_mm": (
            "positive_climatic_water_deficit_sum_mm"
        ),
    }
    for stage, prefix in pre30_prefix_by_stage.items():
        mask = result["stage"].eq(stage)
        result[f"{prefix}_gdd5_rate_c_day"] = np.nan
        result.loc[mask, f"{prefix}_gdd5_rate_c_day"] = safe_rate(
            result.loc[mask, "t30_gdd5_adjusted_c_days"],
            result.loc[mask, "t30_n_days"],
        )
        result[f"{prefix}_gdd10_rate_c_day"] = np.nan
        result.loc[mask, f"{prefix}_gdd10_rate_c_day"] = safe_rate(
            result.loc[mask, "t30_gdd10_adjusted_c_days"],
            result.loc[mask, "t30_n_days"],
        )
        for source, suffix in pre30_aliases.items():
            result[f"{prefix}_{suffix}"] = np.nan
            result.loc[mask, f"{prefix}_{suffix}"] = result.loc[
                mask, f"t30_{source}"
            ].astype(float)
    return result


def feature_set_manifest(feature_sets: dict[str, list[str]] | None = None) -> pd.DataFrame:
    if feature_sets is None:
        feature_sets = STAGE_FEATURE_SETS
    rationale = {
        "mechanistic_predicted_doy": "Baseline state retained for strict residual learning",
        "dem_elevation_m": "Site thermal environment and elevational gradient",
        "dem_local_std_m": "Local terrain heterogeneity proxy",
        "northness": "North-facing versus south-facing terrain exposure",
        "preseason_chill_days_tmean_0_10c": "Daily-data proxy for dormancy chilling exposure",
        "preseason_frost_degree_days_below0_c_days": "Fixed-window preseason cold-stress intensity",
        "forcing_temperature_variability_c": "Temperature variability from January 1 through the OOF budburst prediction",
        "mechanistic_interval_from_upstream_days": "Cross-fitted seasonal stage continuity",
        "lat": "Raw station latitude retained only in sensitivity profiles",
        "lon": "Raw station longitude retained only in sensitivity profiles",
        "country_france": "Country one-hot term for network-level residual offset",
        "country_germany": "Country one-hot term for network-level residual offset",
        "country_france_x_mechanistic_predicted_doy": "Country-specific residual slope against the mechanistic prediction",
        "budburst_pre15d_gdd5_rate_c_day": "Mean recent forcing rate before the mechanistic budburst prediction",
        "budburst_pre30d_gdd5_rate_c_day": "Mean recent forcing rate before the mechanistic budburst prediction",
        "flowering_predicted_stage_length_days": "Predicted budburst-to-flowering interval length",
        "veraison_predicted_stage_length_days": "Predicted flowering-to-veraison interval length",
        "preveraison_30d_vpd_et0_interaction_kpa_mm": "Near-event atmospheric drought and evaporative demand interaction",
        "preveraison_30d_vpd_precipitation_interaction_kpa_mm": "Near-event atmospheric drought and precipitation interaction",
        "country_france_x_preveraison_30d_vpd_fao56_mean_kpa": "Country-specific near-veraison VPD response term",
    }
    records = []
    for stage, features in feature_sets.items():
        for order, feature in enumerate(features, start=1):
            if feature in rationale:
                reason = rationale[feature]
            elif "soil_water" in feature:
                reason = "ERA5-Land root-zone soil-water proxy over a leakage-safe window"
            elif "et0_fao56" in feature:
                reason = "FAO-56 atmospheric evaporative demand over a leakage-safe window"
            elif "climatic_water_deficit" in feature:
                reason = "ET0 minus precipitation water-deficit proxy over a leakage-safe window"
            elif "rain_days_ge1mm" in feature:
                reason = "Number of days with precipitation at least 1 mm over a leakage-safe window"
            elif "precipitation" in feature:
                reason = "Cumulative water input over a leakage-safe window"
            elif "solar_radiation" in feature:
                reason = "Cumulative shortwave radiation over a leakage-safe window"
            elif "frost_degree" in feature:
                reason = "Cold-stress intensity, not only frost-day frequency"
            elif "heat_degree" in feature:
                reason = "Supra-optimal heat intensity above 30 degrees C"
            elif "rate_c_day" in feature:
                reason = "Thermal accumulation rate over a leakage-safe predicted window"
            elif "interaction" in feature:
                reason = "Pre-specified residual interaction over a leakage-safe window"
            elif "diurnal_temperature_range" in feature:
                reason = "Mean diurnal thermal amplitude over the predicted stage window"
            elif "tmean" in feature:
                reason = "Temperature variability over the predicted stage window"
            else:
                reason = "Pre-specified stage-relevant predictor"
            records.append(
                {
                    "stage": stage,
                    "feature_set": "selected",
                    "feature_order": order,
                    "feature": feature,
                    "rationale": reason,
                }
            )
    return pd.DataFrame.from_records(records)


def feature_exclusion_log() -> pd.DataFrame:
    records = [
        ("predicted_doy", "duplicate", "Exact duplicate of mechanistic_predicted_doy"),
        ("target_stage_order", "within_stage_constant", "Stages are trained separately"),
        ("forcing_threshold_c_days; model_forcing_start_doy", "mechanistic_redundancy", "Already encoded by frozen structure and predicted DOY"),
        ("era5_grid_elevation_m; site_minus_grid_elevation_m; abs_site_grid_elevation_difference_m", "temperature_adjustment_redundancy", "Site-grid elevation mismatch already determines lapse-rate-adjusted temperature; retained only as adjustment audit metadata"),
        ("dem_local_median_m; dem_local_range_m; glo30_grid_std_m; glo30_grid_range_m", "terrain_redundancy", "One local DEM standard deviation retained"),
        ("lat; lon; era5_grid_lat; era5_grid_lon", "spatial_memorization_risk", "Raw coordinates are excluded from the default profile and retained only for sensitivity tests"),
        ("slope_deg", "terrain_collinearity", "Absolute correlation with local DEM standard deviation is approximately 0.79-0.82"),
        ("aspect_deg; eastness", "aspect_parsimony", "Only northness is retained as the directly interpretable north-south exposure gradient"),
        ("all *_gdd0/5/10 fields", "mechanistic_collinearity", "Accumulation is near the calibrated threshold or strongly redundant with baseline prediction"),
        ("all *_n_days fields", "deterministic_window_length", "Determined by prediction and window definitions"),
        ("target-year; fixed trailing-30/60-day; model-start overlapping summaries", "temporal_redundancy", "Post-budburst stages use only their cross-fitted predicted stage window"),
        ("all wind-speed summaries", "weak_prior_support", "No clear pre-specified residual mechanism in the selected literature"),
        ("raw country; source; country_network", "regional_shortcut", "Raw categorical network labels are excluded; country one-hot terms are retained only in the enhanced diagnostic profile"),
        ("year; daylength_hours_at_mechanistic_prediction", "temporal_spatial_proxy", "Excluded to avoid unresolved trend and latitude-season proxies"),
        ("budburst ty_tmean_adjusted_mean_c; ty_tmin_adjusted_min_c", "correlation_and_outlier_risk", "Mean forcing temperature overlaps with the mechanistic rule; a single Tmin extreme is less robust than accumulated frost intensity"),
        ("forcing_temperature_variability_c", "high_correlation", "Absolute correlation with preseason frost intensity is approximately 0.84-0.86; accumulated frost intensity retained"),
        ("flowering t30_frost_degree_days_below0_c_days", "near_zero_variance", "Zero for 99.97% of eligible training rows"),
        ("flowering mechanistic_interval_from_upstream_days", "high_correlation", "Absolute correlation with cumulative stage radiation is approximately 0.91-0.92; cumulative radiation retained"),
        ("veraison and maturity mechanistic_interval_from_upstream_days", "high_correlation", "Absolute correlation with mechanistic predicted DOY is approximately 0.824 and 0.776; omitted for parsimony"),
        ("flowering_pre15d_frost_degree_days_below0_c_days", "zero_variance", "Zero for all eligible flowering training rows in the current cohort"),
        ("budburst_to_flowering_heat_degree_days_above35_c_days", "zero_variance", "Zero for all eligible flowering training rows in the current cohort"),
        ("flowering_to_veraison_heat_degree_days_above35_c_days", "high_correlation", "Absolute correlation with preveraison_30d_heat_degree_days_above35_c_days is approximately 0.96; the near-event stress metric is retained"),
    ]
    return pd.DataFrame(records, columns=["excluded_field_or_group", "reason_code", "reason"])


def feature_dictionary(
    frame: pd.DataFrame,
    feature_sets: dict[str, list[str]] | None = None,
) -> pd.DataFrame:
    if feature_sets is None:
        feature_sets = STAGE_FEATURE_SETS
    roles: dict[str, tuple[str, str]] = {
        "residual_row_id": ("identifier", "Unique nested-CV row identifier"),
        "record_id": ("identifier", "Phenology event identifier"),
        "weather_id": ("identifier", "Site-year weather identifier"),
        "dataset_role": ("fold_control", "Training-region OOF or spatial test"),
        "outer_fold": ("fold_control", "Current spatial test round"),
        "inner_fold": ("fold_control", "Training-region validation fold"),
        "event_assigned_outer_fold": ("fold_control", "Event's fixed spatial fold"),
        "validation_block_1deg_id": ("fold_control", "Spatial block; never a predictor"),
        "observed_doy": ("target_source", "Observed event day; never a predictor"),
        "residual_days": ("target", "Observed DOY minus mechanistic OOF DOY"),
        "absolute_mechanistic_error_days": ("diagnostic_only", "Absolute baseline error"),
        "residual_ml_eligible": ("quality_control", "Mechanistic prediction and residual available"),
        "threshold_reached": ("quality_control", "Thermal threshold reached in target year"),
        "site_minus_grid_elevation_m": (
            "adjustment_audit_only",
            "Elevation mismatch already used to construct adjusted temperature; never a residual-ML predictor",
        ),
    }
    sensitivity_tokens = (
        "precipitation", "solar_radiation", "vpd", "wind_speed", "et0_fao56",
        "climatic_water_deficit", "soil_water",
    )
    identifier_tokens = ("site_uid", "site_id", "era5_grid_id")
    selected_features = {
        feature for features in feature_sets.values() for feature in features
    }
    records = []
    for column in frame.columns:
        if column in roles:
            role, description = roles[column]
        elif column in selected_features:
            role, description = "selected_feature", "Frozen predictor for at least one stage"
        elif any(token in column for token in sensitivity_tokens):
            role, description = "sensitivity_feature", "Leakage-safe weather summary ending at mechanistic prediction"
        elif any(column == token for token in identifier_tokens):
            role, description = "identifier", "Grouping identifier; not a default predictor"
        elif column in {"source", "country", "country_network"}:
            role, description = "regional_structure_feature", "Country/source structure; interpretation is confounded"
        elif column in {"lat", "lon", "era5_grid_lat", "era5_grid_lon", "aspect_deg"}:
            role, description = "sensitivity_feature", "Spatial feature; assess extrapolation sensitivity"
        elif column in {"model_id", "temperature_branch", "stage", "target_stage", "bbch"}:
            role, description = "stratum", "Model or stage definition; fit stages separately"
        elif column in {
            "predicted_doy", "mechanistic_predicted_doy", "forcing_threshold_c_days",
            "model_forcing_start_doy", "predicted_veraison_doy", "year",
            "upstream_mechanistic_predicted_doy",
            "mechanistic_interval_from_upstream_days",
            "preseason_chill_days_tmean_0_10c",
        }:
            role, description = "core_feature", "Mechanistic or temporal predictor available before residual target"
        elif column == "daylength_hours_at_mechanistic_prediction":
            role, description = "sensitivity_feature", "Photoperiod calculated from latitude and mechanistic prediction DOY"
        elif column.startswith(tuple(f"{prefix}_" for prefix in WINDOW_PREFIXES.values())):
            role, description = "core_feature", "Leakage-safe weather summary ending at mechanistic prediction"
        elif column.startswith(tuple(f"{prefix}_" for prefix in STAGE_WINDOW_PREFIXES.values())):
            role, description = "selected_feature", "Weather summary over a cross-fitted predicted stage window"
        elif column in STATIC_COLUMNS:
            role, description = "core_feature", "Static site or terrain predictor"
        else:
            role, description = "metadata", "Retained for audit"
        records.append({"column": column, "role": role, "description": description})
    return pd.DataFrame.from_records(records)


def main() -> int:
    args = parse_args()
    feature_sets = feature_sets_for_profile(args.feature_profile)
    if args.output_dir.exists() and any(args.output_dir.iterdir()) and not args.overwrite:
        raise FileExistsError(f"Output directory is not empty: {args.output_dir}; use --overwrite")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    combined_path = args.output_dir / "residual_nested_spatial_cv.parquet"
    if args.reuse_existing_features:
        if not combined_path.exists():
            raise FileNotFoundError(f"Existing combined residual table is missing: {combined_path}")
        combined = pd.read_parquet(combined_path)
        weather_feature_rows = int(combined["residual_ml_eligible"].sum())
    else:
        training, test = prepare_residual_rows(args.baseline_dir)
        combined = pd.concat([training, test], ignore_index=True)
        weather_features = build_weather_features(combined, args.weather_dir)
        weather_feature_rows = int(len(weather_features))
        combined = combined.merge(
            weather_features, on="residual_row_id", how="left", validate="one_to_one"
        )
    combined = add_derived_residual_features(combined)
    training = combined.loc[combined["dataset_role"].eq("training_region_oof")].copy()
    test = combined.loc[combined["dataset_role"].eq("spatial_test")].copy()

    training.to_parquet(args.output_dir / "residual_training_oof.parquet", index=False)
    test.to_parquet(args.output_dir / "residual_spatial_test.parquet", index=False)
    combined.to_parquet(args.output_dir / "residual_nested_spatial_cv.parquet", index=False)
    feature_dictionary(combined, feature_sets).to_csv(
        args.output_dir / "residual_feature_dictionary.csv", index=False
    )
    manifest = feature_set_manifest(feature_sets)
    missing_features = set(manifest["feature"]).difference(combined.columns)
    if missing_features:
        raise ValueError(f"Frozen residual-ML features are missing: {sorted(missing_features)}")
    manifest.to_csv(args.output_dir / "residual_ml_feature_sets.csv", index=False)
    feature_exclusion_log().to_csv(
        args.output_dir / "residual_ml_feature_exclusion_log.csv", index=False
    )
    ready_dir = args.output_dir / "training_ready"
    ready_dir.mkdir(parents=True, exist_ok=True)
    control_columns = [
        "residual_row_id", "record_id", "weather_id", "site_uid", "dataset_role",
        "outer_fold", "inner_fold", "event_assigned_outer_fold",
        "validation_block_1deg_id", "stage", "model_id", "temperature_branch",
        "observed_doy", "mechanistic_predicted_doy", "residual_days",
        "residual_ml_eligible", "threshold_reached",
    ]
    for stage, features in feature_sets.items():
        stage_columns = list(dict.fromkeys([*control_columns, *features]))
        stage_table = combined.loc[combined["stage"].eq(stage), stage_columns].copy()
        stage_table.to_parquet(ready_dir / f"{stage}_residual_ml.parquet", index=False)

    summary_rows = []
    for (role, stage), group in combined.groupby(["dataset_role", "stage"], sort=True):
        eligible = group["residual_ml_eligible"].astype(bool)
        summary_rows.append(
            {
                "dataset_role": role,
                "stage": stage,
                "n_rows": int(len(group)),
                "n_unique_events": int(group["record_id"].nunique()),
                "n_residual_ml_eligible": int(eligible.sum()),
                "eligible_pct": float(eligible.mean() * 100),
                "residual_mean_days": float(group.loc[eligible, "residual_days"].mean()),
                "residual_mae_days": float(group.loc[eligible, "residual_days"].abs().mean()),
                "residual_sd_days": float(group.loc[eligible, "residual_days"].std()),
            }
        )
    summary_table = pd.DataFrame(summary_rows)
    summary_table.to_csv(args.output_dir / "residual_dataset_summary.csv", index=False)
    audit = {
        "scope": "strict nested spatial-CV residual ML foundation",
        "training_oof_rows": int(len(training)),
        "spatial_test_rows": int(len(test)),
        "unique_events": int(combined["record_id"].nunique()),
        "training_rows_per_event_expected": 4,
        "training_rows_per_event_check": bool(training.groupby("record_id").size().eq(4).all()),
        "spatial_test_rows_per_event_check": bool(test.groupby("record_id").size().eq(1).all()),
        "current_test_fold_excluded_from_training_residuals": bool(
            training["event_assigned_outer_fold"].ne(training["outer_fold"]).all()
        ),
        "weather_feature_cutoff": "mechanistic predicted DOY; never observed event DOY",
        "veraison_feature_window": (
            "after fold-specific OOF mechanistic flowering prediction through "
            "fold-specific OOF mechanistic BBCH81 prediction; no observed boundary dates"
        ),
        "weather_feature_rows": weather_feature_rows,
        "feature_profile": args.feature_profile,
        "frozen_selected_features_by_stage": {
            stage: len(features) for stage, features in feature_sets.items()
        },
        "output_directory": display_path(args.output_dir),
    }
    (args.output_dir / "run_summary.json").write_text(
        json.dumps(audit, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    readme = "# Residual machine-learning foundation\n\n"
    readme += "Generated from the four frozen mechanistic model structures. Training residuals are produced only by four-fold spatial cross-fitting inside each current training region; spatial-test residuals are retained only for later evaluation and must never train or tune the residual model. Weather features end at the mechanistic predicted date, not the observed event date. For BBCH81, the strict feature window starts after the fold-specific OOF mechanistic flowering prediction and ends at the fold-specific OOF mechanistic BBCH81 prediction; neither boundary uses an observed phenology date.\n\n"
    readme += "`residual_ml_feature_sets.csv` freezes one parsimonious predictor set per stage; `residual_ml_feature_exclusion_log.csv` records deduplication decisions. The four `training_ready/*.parquet` files contain only fold controls, targets and the frozen stage features. Site-grid elevation mismatch remains only in the full audit table because it already determines the adjusted temperature. Imputation, scaling and encoding remain to be fitted inside each current training region.\n"
    (args.output_dir / "README.md").write_text(readme, encoding="utf-8")
    print("\nResidual ML dataset completed")
    print(json.dumps(audit, ensure_ascii=False, indent=2))
    print("\nResidual summary")
    print(summary_table.round(3).to_string(index=False))
    print("\nFrozen residual-ML feature sets")
    for stage, features in feature_sets.items():
        print(f"\n[{stage}] selected ({len(features)})")
        print("  " + ", ".join(features))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
