"""Run one or all process models at the first inventory site and compare dates."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

# Direct execution works from any directory without installing this paper repo.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd

from model.artifacts import load_fit, read_csv, write_csv
from model.data import observations as validate_observations
from model.metrics import evaluate
from model.parameters import default_parameters
from model.registry import get_model, list_models
from model.simulation import predict
from src.weather_processing.site_weather import INVENTORY, file_hash, load_inventory

OBSERVATIONS = ROOT / "data/phenology/derived/paper_targets/observations.csv"
WEATHER = ROOT / "data/weather/sites"


def observation_identity(inventory_uid):
    """Explicit mapping between the historical inventory and canonical observations."""
    country, source, identifier = inventory_uid.split("|")
    prefixes = {("France", "france_tempo"): "FR:tempo",
                ("Germany", "germany_dwd"): "DE:dwd"}
    if (country, source) not in prefixes:
        raise ValueError(f"No documented observation identity mapping for {inventory_uid}")
    return f"{prefixes[country, source]}:{identifier}"


def calculate(inventory=INVENTORY, observations_path=OBSERVATIONS, weather_dir=WEATHER,
              output=None, *, model_name=None, fit_path=None):
    """Prediction-only demonstration: no observation-dependent parameter fitting."""
    site = load_inventory(inventory)[0]
    obs_id = observation_identity(site.uid)
    observed = read_csv(observations_path)
    if "site" not in observed:
        raise ValueError("Canonical observations require the site column")
    observed = observed.loc[observed.site.eq(obs_id)].copy()
    if observed.empty:
        raise ValueError(f"No observations for the first inventory site: {obs_id}")
    observed = validate_observations(observed)
    if not {"lat", "lon"}.issubset(observed):
        raise ValueError("Canonical observations require lat and lon")
    # Identity alone is insufficient if coordinates refer to a different location.
    coordinates = observed[["lat", "lon"]].apply(pd.to_numeric)
    if (coordinates.isna().any().any()
            or (coordinates.lat - site.lat).abs().gt(1e-4).any()
            or (coordinates.lon - site.lon).abs().gt(1e-4).any()):
        raise ValueError("Observation and weather-inventory coordinates disagree")
    weather_path = Path(weather_dir) / site.filename
    weather = read_csv(weather_path)
    if weather.columns.tolist() != ["Date", "Tmean"]:
        raise ValueError("Site weather file must have exactly Date,Tmean columns, in Celsius")
    weather["site"] = obs_id

    if fit_path:
        fitted = load_fit(fit_path)
        if model_name and model_name != fitted.model_name:
            raise ValueError("Requested model and saved-fit model disagree")
        if fitted.temperature_input != "RAW":
            raise ValueError("A DEM fit cannot use this RAW ERA5-Land weather file")
        name, parameters = fitted.model_name, fitted.parameters
        parameter_source = "saved_fit"
    else:
        name = model_name or "FL"
        parameters = default_parameters(name)
        parameter_source = "illustrative_uncalibrated"

    output = Path(output) if output is not None else ROOT / "model_run/results" / f"first_site_{name}"
    if output.exists():
        raise FileExistsError(f"Output already exists; choose a new --output directory: {output}")
    seasons = observed[["site", "season"]].drop_duplicates().sort_values(["site", "season"])
    predictions = predict(name, parameters, weather, seasons,
                          temperature_column="Tmean", temperature_input="RAW")
    comparison = observed.rename(columns={"Date": "observed_date"}).merge(
        predictions, on=["site", "season", "BBCH"], how="left", validate="many_to_one")
    comparison["delta_days"] = (comparison.predicted_date - comparison.observed_date).dt.days.astype("Int64")
    comparison["absolute_error_days"] = comparison.delta_days.abs()
    comparison["site_name"] = site.name
    comparison["parameter_source"] = parameter_source
    comparison = comparison.sort_values(["season", "BBCH", "observed_date"], kind="stable").reset_index(drop=True)
    metrics = evaluate(observed, predictions)
    metrics["parameter_source"] = parameter_source
    metadata = {"site_uid": site.uid, "observation_site": obs_id, "site_name": site.name,
                "lat": site.lat, "lon": site.lon, "model_name": name,
                "definition_version": get_model(name).version, "parameters": parameters,
                "parameter_source": parameter_source, "temperature_input": "RAW",
                "weather_column": "Tmean", "weather_units": "degrees Celsius",
                "n_observations": len(observed), "seasons": seasons.season.tolist(),
                "delta_definition": "predicted calendar date minus observed calendar date, in days",
                "calibration_performed": False, "independent_validation_established": False,
                "note": "Illustrative comparison, not estimated predictive skill; no parameters fitted to these observations."
                        if not fit_path else "Saved parameters reused without refitting; calibration/test independence is not verified.",
                "inputs": {"inventory": str(Path(inventory).resolve()),
                           "observations": str(Path(observations_path).resolve()),
                           "weather": str(weather_path.resolve())},
                "input_sha256": {"inventory": file_hash(inventory),
                                 "observations": file_hash(observations_path), "weather": file_hash(weather_path)},
                "saved_fit": str(Path(fit_path).resolve()) if fit_path else None,
                "saved_fit_sha256": file_hash(fit_path) if fit_path else None,
                "optimizer_converged": fitted.optimizer_converged if fit_path else None}
    for frame in (predictions, comparison, metrics):
        frame.insert(0, "model", name)
    return {"comparison": comparison, "predictions": predictions, "metrics": metrics,
            "metadata": metadata, "output": output}


def run(inventory=INVENTORY, observations_path=OBSERVATIONS, weather_dir=WEATHER,
        output=None, *, model_name=None, fit_path=None):
    if model_name == "all":
        if fit_path:
            raise ValueError("--model all cannot use one saved fit; select its individual model with --fit")
        output = Path(output) if output is not None else ROOT / "model_run/results/first_site_all"
        results = [calculate(inventory, observations_path, weather_dir, output, model_name=name)
                   for name in list_models()]
        metadata = results[0]["metadata"].copy()
        if any(item["metadata"]["input_sha256"] != metadata["input_sha256"] for item in results):
            raise ValueError("Inputs changed during the all-model comparison; rerun with stable files")
        metadata["model_names"] = list(list_models())
        metadata["models"] = {item["metadata"]["model_name"]: {
            field: item["metadata"][field] for field in ("parameters", "definition_version", "parameter_source")}
            for item in results}
        for field in ("model_name", "parameters", "definition_version"):
            metadata.pop(field)
        result = {key: pd.concat([item[key] for item in results], ignore_index=True)
                  for key in ("comparison", "predictions", "metrics")}
        result.update(metadata=metadata, output=output)
    else:
        result = calculate(inventory, observations_path, weather_dir, output,
                           model_name=model_name, fit_path=fit_path)
    # Compute and validate every requested model before creating any output.
    output = result["output"]
    output.mkdir(parents=True, exist_ok=False)
    for key in ("predictions", "comparison", "metrics"):
        write_csv(result[key], output / f"{key}.csv")
    with (output / "run.json").open("x", encoding="utf-8") as stream:
        json.dump(result["metadata"], stream, indent=2, allow_nan=False)
        stream.write("\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--inventory", type=Path, default=INVENTORY)
    parser.add_argument("--observations", type=Path, default=OBSERVATIONS)
    parser.add_argument("--weather-dir", type=Path, default=WEATHER)
    parser.add_argument("--model", choices=(*list_models(), "all"), help="One model or all ten; default FL, or the saved fit's model")
    parser.add_argument("--fit", type=Path, help="Optional saved RAW fit; never refits to this site's observations")
    parser.add_argument("--output", type=Path, help="New output directory; existing outputs are not overwritten")
    args = parser.parse_args(argv)
    try:
        result = run(args.inventory, args.observations, args.weather_dir, args.output,
                     model_name=args.model, fit_path=args.fit)
    except (OSError, ValueError) as exc:
        parser.exit(2, f"Error: {exc}\n")
    metadata = result["metadata"]
    print(f"Site: {metadata['site_name']} ({metadata['observation_site']})")
    model_label = metadata.get("model_name") or ", ".join(metadata["model_names"])
    print(f"Model: {model_label}; parameters: {metadata['parameter_source']}")
    print(metadata["note"])
    print("delta_days = predicted minus observed; positive means late, negative means early.")
    print(result["comparison"][["model", "season", "BBCH", "observed_date", "predicted_date", "delta_days", "status"]].to_string(index=False))
    print(f"Outputs: {result['output']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
