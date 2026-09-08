"""Literature-fixed curves with display-only forcing normalization; no fitting."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd
from model import responses
from model.registry import list_models
from model.structure_comparison import (
    PROFILE, FORCING_BASE, FORCING_CARDINALS, CHILLING_CARDINALS, threshold_only_settings,
)


def curve_data():
    temperatures = np.unique(np.concatenate((np.round(np.arange(-5, 45.01, .1), 1),
                                            FORCING_CARDINALS, CHILLING_CARDINALS)))
    definitions = [
        ("FL", "forcing", responses.linear(temperatures, FORCING_BASE), "degree_C_day_per_day",
         FORCING_BASE, np.nan, np.nan, "10.1111/j.1755-0238.2011.00140.x", "GFV base; four-stage adaptation"),
        ("FB", "forcing", responses.beta(temperatures, *FORCING_CARDINALS), "response_unit_per_day",
         *FORCING_CARDINALS, "10.1016/j.agrformet.2014.05.011", "Fbeta5* Table 8; maximum from section 3.2"),
        ("CL", "chilling", responses.triangular(temperatures, *CHILLING_CARDINALS), "response_unit_per_day",
         *CHILLING_CARDINALS, "10.1016/j.agrformet.2014.05.011;10.5194/gmd-13-1459-2020",
         "CF10* Table 7 cardinals transferred to triangular equation 1; adaptation"),
        ("CB", "chilling", responses.beta(temperatures, *CHILLING_CARDINALS), "response_unit_per_day",
         *CHILLING_CARDINALS, "10.1016/j.agrformet.2014.05.011", "CF10* Table 7; requirement recalibrated"),
    ]
    frames = []
    for code, process, rates, unit, lower, optimum, upper, doi, basis in definitions:
        divisor = float(responses.linear(FORCING_CARDINALS[1], FORCING_BASE)) if code == "FL" else 1.0
        frames.append(pd.DataFrame(dict(response=code, process=process, temperature_c=temperatures,
            rate=rates, rate_unit=unit, minimum_or_base_c=lower, optimum_c=optimum, maximum_c=upper,
            display_rate=rates / divisor, display_divisor=divisor,
            display_rate_unit="relative_to_25.4_C" if process == "forcing" else unit,
            profile=PROFILE, source_doi=doi, parameter_basis=basis)))
    return pd.concat(frames, ignore_index=True)


def run(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    data = curve_data()
    csv = output / "temperature_responses.csv"
    data.to_csv(csv, index=False, float_format="%.12g")
    spec = dict(profile=PROFILE, visible_title=False, legend_pt=15,
        panels=[["FL", "FB"], ["CL", "CB"]],
        chart_contract=dict(question="How do fixed forcing and chilling responses differ with temperature?",
            takeaway="Linear forcing is uncapped; beta responses are bounded; chilling alternatives share cardinals.",
            family="line", variant="two vertically faceted paired response plots",
            surface="standalone vector PDF and PNG, embedded in manuscript",
            renderer="Swift CoreGraphics/PDFKit", footprint_pt=[453, 420],
            palette_policy="hard two-root cap", colors=["#326C9C", "#B46B28"],
            non_color="solid linear/triangular versus dashed beta responses",
            units="Forcing displayed as R(T)/R(25.4 C); chilling native daily units; no dual axes",
            normalization_scope="Display only; native rates, model equations and thresholds unchanged",
            temperature_grid="-5 to 45 degrees C at 0.1 degree intervals, including exact cardinals"),
        series=[dict(response=code, temperature_c=group.temperature_c.tolist(), rate=group.rate.tolist(),
                     display_rate=group.display_rate.tolist())
                for code, group in data.groupby("response", sort=False)],
        forcing_cardinals=list(FORCING_CARDINALS), chilling_cardinals=list(CHILLING_CARDINALS),
        data_sha256=hashlib.sha256(csv.read_bytes()).hexdigest(),
        sources={"Parker et al. (2011)": "https://doi.org/10.1111/j.1755-0238.2011.00140.x",
                 "Fila et al. (2014)": "https://doi.org/10.1016/j.agrformet.2014.05.011",
                 "de Wergifosse et al. (2020)": "https://doi.org/10.5194/gmd-13-1459-2020"})
    source_paths = [Path(__file__), ROOT / "model/responses.py", ROOT / "model/structure_comparison.py",
                    Path(__file__).with_name("draw_temperature_responses.swift")]
    spec["source_sha256"] = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in source_paths}
    spec_path = output / "temperature_responses.json"
    spec_path.write_text(json.dumps(spec, indent=2, allow_nan=False)+"\n")
    settings_dir = output / "calibration_settings"
    settings_dir.mkdir()
    for name in list_models():
        (settings_dir / f"{name}.json").write_text(json.dumps(asdict(threshold_only_settings(name)), indent=2)+"\n")
    subprocess.run(["swift", "-module-cache-path", "/tmp/grape-workflow-swift-cache",
                    str(source_paths[-1]), str(spec_path), str(output)], check=True)
    return spec


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "fig/model_functions")
    run(parser.parse_args().output)
