"""Prediction-only metrics; every observed event must have an explicit prediction status."""
import numpy as np
import pandas as pd

from .data import dates, observations
from .registry import get_model
from .specification import STAGES


def evaluate(observation_frame, predictions):
    observed = observations(observation_frame)
    required = {"site", "season", "BBCH", "predicted_date", "status", "model_name", "temperature_input"}
    if not required.issubset(predictions.columns) or predictions.empty:
        raise ValueError(f"Predictions require {sorted(required)} and cannot be empty")
    work = predictions.loc[:, sorted(required)].copy()
    work["BBCH"] = work.BBCH.astype(str).str.zfill(2)
    supplied_dates = work.predicted_date.replace("", None)
    present = supplied_dates.notna()
    parsed_dates = pd.Series(pd.NaT, index=work.index, dtype="datetime64[ns]")
    if present.any():
        parsed_dates.loc[present] = dates(supplied_dates.loc[present], "predicted_date")
    work["predicted_date"] = parsed_dates
    if not work.BBCH.isin(STAGES).all():
        raise ValueError("Unsupported predicted BBCH stage")
    keys = ["site", "season", "BBCH"]
    if work.duplicated(["model_name", "temperature_input", *keys]).any():
        raise ValueError("Duplicate prediction keys")
    if not work.status.isin(["attained", "unmet_chilling", "unmet_forcing", "previous_stage_unattained"]).all():
        raise ValueError("Unknown prediction attainment status")
    if not work.status.eq("attained").eq(work.predicted_date.notna()).all():
        raise ValueError("Prediction dates and attainment status disagree")
    records = []
    for (name, temperature), group in work.groupby(["model_name", "temperature_input"], dropna=False, sort=False):
        get_model(name)
        if temperature not in {"RAW", "DEM"}:
            raise ValueError("Prediction temperature input must be RAW or DEM")
        joined = observed.merge(group, on=keys, how="left", validate="many_to_one", indicator=True)
        if not joined._merge.eq("both").all():
            raise ValueError("Each observation needs a prediction row, including unattained events")
        joined["error"] = (joined.predicted_date - joined.Date).dt.days.astype(float)
        for stage in STAGES:
            all_events = joined[joined.BBCH.eq(stage)]
            if all_events.empty:
                continue
            valid = all_events[all_events.error.notna()]
            n = len(all_events)
            record = {"model_name": name, "temperature_input": temperature, "BBCH": stage,
                      "n_observations": n, "n_sites": int(all_events.site.nunique()),
                      "n_attained": len(valid), "n_unattained": n - len(valid),
                      "n_sites_attained": int(valid.site.nunique()), "attainment_rate": len(valid) / n}
            record.update({metric: np.nan for metric in
                           ("mae", "rmse", "bias", "site_balanced_mae", "site_balanced_rmse", "site_balanced_bias")})
            if len(valid):
                error = valid.error
                per_site = pd.DataFrame({"site": valid.site, "ae": error.abs(), "se": error ** 2, "error": error}).groupby("site").mean()
                record.update(mae=float(error.abs().mean()), rmse=float(np.sqrt((error ** 2).mean())), bias=float(error.mean()),
                              site_balanced_mae=float(per_site.ae.mean()), site_balanced_rmse=float(np.sqrt(per_site.se.mean())),
                              site_balanced_bias=float(per_site.error.mean()))
            records.append(record)
    return pd.DataFrame.from_records(records)
