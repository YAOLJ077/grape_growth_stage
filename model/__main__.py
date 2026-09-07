"""Shared CLI: python -m model {list,fit,predict,evaluate}."""
import argparse
from pathlib import Path
import sys

from .registry import list_models


def main(argv=None):
    parser = argparse.ArgumentParser(description="Process-only grapevine models. No data downloads, automatic splits or ML.")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("list", help="List the ten process-model names")
    fitting = commands.add_parser("fit", help="Jointly calibrate using only the supplied calibration records")
    fitting.add_argument("--model", required=True, choices=list_models())
    fitting.add_argument("--calibration-observations", required=True, type=Path,
                         help="Calibration-only CSV; test records must not be included")
    fitting.add_argument("--weather", required=True, type=Path, help="Daily Celsius weather CSV")
    fitting.add_argument("--settings", type=Path, help="JSON bounds, seeds, temperature column/input and optimizer budget")
    fitting.add_argument("--output", required=True, type=Path, help="New saved-fit JSON; never overwrites an existing file")
    prediction = commands.add_parser("predict", help="Predict using saved parameters, without calibration")
    prediction.add_argument("--fit", required=True, type=Path)
    prediction.add_argument("--weather", required=True, type=Path)
    prediction.add_argument("--seasons", required=True, type=Path, help="CSV with site and season (calendar year)")
    prediction.add_argument("--output", required=True, type=Path)
    evaluation = commands.add_parser("evaluate", help="Report errors and attainment; no fitting or selection")
    evaluation.add_argument("--observations", required=True, type=Path)
    evaluation.add_argument("--predictions", required=True, type=Path)
    evaluation.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    if args.command == "list":
        print("\n".join(list_models()))
        return 0
    from .artifacts import load_fit, load_settings, read_csv, save_fit, write_csv
    from .calibration import fit
    from .metrics import evaluate
    from .simulation import predict
    try:
        if args.output.exists():
            raise FileExistsError(f"Output already exists: {args.output}; choose a new filename")
        if args.command == "fit":
            settings = load_settings(args.settings)
            observed = read_csv(args.calibration_observations)
            weather = read_csv(args.weather)
            print(f"Calibrating {args.model}: {len(observed)} supplied records; {len(settings.seeds)} restarts", file=sys.stderr)
            result = fit(args.model, observed, weather, settings)
            save_fit(result, args.output)
            print(f"Objective: {result.objective_value:.6g} days; optimizer_converged={result.optimizer_converged}")
            if result.diagnostics["boundary_hits"]:
                print(f"Warning: fitted parameters near search bounds: {result.diagnostics['boundary_hits']}", file=sys.stderr)
        elif args.command == "predict":
            saved = load_fit(args.fit)
            predicted = predict(saved.model_name, saved.parameters, read_csv(args.weather), read_csv(args.seasons),
                                temperature_column=saved.temperature_column, temperature_input=saved.temperature_input)
            write_csv(predicted, args.output)
            print(f"Saved {len(predicted)} stage predictions")
        else:
            summary = evaluate(read_csv(args.observations), read_csv(args.predictions))
            write_csv(summary, args.output)
            print(f"Saved {len(summary)} stage-level summaries")
    except (OSError, ValueError, TypeError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
