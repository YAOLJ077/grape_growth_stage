"""Calibration-only median requirements and explicit administrative scoring dates.

Assigned dates are never passed to the process model or counted as attainment.
"""
import numpy as np
import pandas as pd

from model.specification import STAGES
from model.structure_comparison import fixed_parameters, threshold_only_settings
from model_run.src.pooled_calibration import Metrics, weighted_median
from model_run.src.calibrate_pooled_sites import independent_metrics, observation_errors


def derive_cutoff(frame):
    eligible = frame[frame.partition.eq('calibration') & frame.BBCH.eq('89')]
    if eligible.empty:
        raise ValueError('No calibration maturity dates for cutoff')
    return pd.to_datetime(eligible.Date, errors='raise').dt.strftime('%m-%d').max()


def scoring_predictions(raw, seasons, month_day):
    """Return assigned dates, reasons and per-season cutoffs; leave raw unchanged."""
    raw = np.asarray(raw, dtype='datetime64[D]')
    if raw.shape != (len(seasons), 4):
        raise ValueError('Require season × four-stage prediction array')
    cutoffs = np.array([f'{int(y)}-{month_day}' for y in seasons], dtype='datetime64[D]')
    used = raw.copy()
    reason = np.full(raw.shape, '', dtype='<U24')
    for col in (2, 3):
        missing = np.isnat(raw[:, col])
        late = (~missing) & (raw[:, col] > cutoffs)
        reason[missing, col] = 'unattained'
        reason[late, col] = 'after_cutoff'
        used[missing | late, col] = cutoffs[missing | late]
    inherited = reason[:, 2] != ''
    # This explicit rule also guards against a malformed non-chronological input.
    reason[inherited & (reason[:, 3] == ''), 3] = 'preceding_stage_assigned'
    used[inherited, 3] = cutoffs[inherited]
    return used, reason, cutoffs


class EarlySearch:
    """Only early forcing/chilling parameters vary; maturity is absent from loss."""
    def __init__(self, evaluator, frame, parameters, cutoff):
        if not frame.partition.eq('calibration').all():
            raise ValueError('Only calibration observations may enter fitting')
        self.evaluator, self.frame, self.cutoff = evaluator, frame, cutoff
        settings = threshold_only_settings(evaluator.name)
        self.names = [k for k, (lo, hi) in settings.bounds.items()
                      if hi > lo and k != 'forcing_requirement_89']
        self.bounds = [settings.bounds[k] for k in self.names]
        self.fixed = dict(fixed_parameters(evaluator.name),
                          forcing_requirement_89=parameters['forcing_requirement_89'])
        self.metrics = Metrics(frame)
        lookup = {(w.site, w.season): i for i, w in enumerate(evaluator.prepared)}
        self.rows = np.array([lookup[k] for k in frame[['site', 'season']].itertuples(index=False, name=None)])
        self.cols = frame.BBCH.map({s: i for i, s in enumerate(STAGES)}).to_numpy()
        self.observed = frame.Date.to_numpy(dtype='datetime64[D]').astype(np.int64)
        self.cutoff_numbers = np.array([f'{int(y)}-{cutoff}' for y in frame.season],
                                      dtype='datetime64[D]').astype(np.int64)
        self.last_x = None
        self.calls = 0

    def vector(self, parameters):
        return np.array([parameters[k] for k in self.names], dtype=float)

    def decode(self, x):
        return {**self.fixed, **dict(zip(self.names, map(float, x)))}

    def stats(self, x):
        if self.last_x is None or not np.array_equal(x, self.last_x):
            positions = self.evaluator.positions(self.decode(x))[self.rows, self.cols]
            valid = positions >= 0
            dates = np.zeros(len(positions), dtype=np.int64)
            dates[valid] = self.evaluator.date_numbers[self.rows[valid], positions[valid]]
            errors = np.full(len(positions), np.nan)
            errors[valid] = dates[valid] - self.observed[valid]
            self.raw_stats = self.metrics(errors)
            assigned = (self.cols >= 2) & (~valid | (dates > self.cutoff_numbers))
            scored = errors.copy()
            scored[assigned] = self.cutoff_numbers[assigned] - self.observed[assigned]
            self.last_stats = self.metrics(scored)
            self.last_x = np.array(x).copy()
            self.calls += 1
        return self.last_stats

    def coverage_margin(self, x):
        self.stats(x)
        return (self.raw_stats[:3, 3:5] - .99 + 1e-12).ravel()

    def bias_margin(self, x):
        bias = self.stats(x)[:3, 2]
        return np.where(np.isfinite(bias), 1. - np.abs(bias), -1e9)

    def violation(self, x):
        bias = self.stats(x)[:3, 2]
        return float(max(0., np.max(np.abs(bias)) - 1.)) if np.isfinite(bias).all() else 1e9

    def mae(self, x):
        value = self.stats(x)[:3, 0].mean()
        return float(value) if np.isfinite(value) else 1e9

    def covered(self, x):
        return bool(np.all(self.coverage_margin(x) >= 0))

    def feasible(self, x):
        return self.covered(x) and self.violation(x) <= 1e-10


def maturity_median(evaluator, frame, parameters):
    """Median of positive forcing after raw predicted81, balanced over valid sites."""
    if not frame.partition.eq('calibration').all():
        raise ValueError('Only calibration observations may enter median fitting')
    subset = frame[frame.BBCH.eq('89')].reset_index(drop=True)
    lookup = {(w.site, w.season): i for i, w in enumerate(evaluator.prepared)}
    rows = np.array([lookup[k] for k in subset[['site', 'season']].itertuples(index=False, name=None)], dtype=int)
    previous = evaluator.positions(parameters)[rows, 2]
    starts = previous + 1
    observed = subset.Date.to_numpy(dtype='datetime64[D]').astype(np.int64)
    ends = observed - evaluator.date_numbers[rows, 0]
    valid = (previous >= 0) & (ends >= starts) & (ends < evaluator.lengths[rows])
    values = np.full(len(subset), np.nan)
    values[valid] = evaluator.f[rows[valid], ends[valid] + 1] - evaluator.f[rows[valid], starts[valid]]
    valid &= np.isfinite(values) & (values > 0)
    reason = np.full(len(subset), '', dtype='<U40')
    reason[previous < 0] = 'raw_81_unattained'
    reason[(previous >= 0) & (ends < starts)] = 'observation_not_after_raw_81'
    reason[(previous >= 0) & (ends >= evaluator.lengths[rows])] = 'observation_outside_weather'
    reason[(reason == '') & ~valid] = 'nonpositive_requirement'
    counts = subset.loc[valid, 'site'].value_counts()
    weights = np.zeros(len(subset))
    weights[valid] = 1. / subset.loc[valid, 'site'].map(counts).to_numpy()
    audit = subset[['observation_id', 'site', 'season', 'Date', 'BBCH']].copy()
    audit['eligible_requirement'] = valid
    audit['exclusion_reason'] = reason
    audit['thermal_requirement'] = values
    audit['site_weight'] = weights
    if not valid.any():
        error = ValueError('No valid positive calibration maturity requirements')
        error.audit = audit
        raise error
    median = float(weighted_median(values, weights))
    bounds = threshold_only_settings(evaluator.name).bounds['forcing_requirement_89']
    selected = float(np.clip(median, *bounds))
    fitted = dict(parameters, forcing_requirement_89=selected)
    audit['median_unbounded'] = median
    audit['threshold'] = selected
    audit['bound_adjusted'] = selected != median
    return fitted, audit


def evaluation_rows(evaluator, frame, raw, cutoff, model, temperature, method, partition):
    """Separate score availability, raw attainment and cutoff assignment explicitly."""
    seasons = [w.season for w in evaluator.prepared]
    used, reasons, cutoff_dates = scoring_predictions(raw, seasons, cutoff)
    raw_dates, raw_errors = observation_errors(frame, evaluator.prepared, raw)
    used_dates, errors = observation_errors(frame, evaluator.prepared, used)
    lookup = {(w.site, w.season): i for i, w in enumerate(evaluator.prepared)}
    rows = np.array([lookup[k] for k in frame[['site', 'season']].itertuples(index=False, name=None)])
    cols = frame.BBCH.map({s: i for i, s in enumerate(STAGES)}).to_numpy()
    result = frame.copy()
    result['model'], result['temperature'], result['method'] = model, temperature, method
    result['partition'] = partition
    result['raw_predicted_date'] = raw_dates
    result['predicted_date'] = raw_dates  # Existing generic field always means process prediction.
    result['scoring_date'] = used_dates
    result['cutoff_date'] = cutoff_dates[rows]
    result['raw_error_days'], result['error_days'] = raw_errors, raw_errors
    result['scoring_error_days'] = errors
    result['raw_attained'] = ~np.isnat(raw_dates)
    result['attained_by_cutoff'] = (~np.isnat(raw_dates)) & (raw_dates <= cutoff_dates[rows])
    result['assignment_reason'] = reasons[rows, cols]
    result['cutoff_assigned'] = result.assignment_reason.ne('')
    output = []
    for view, values in [('raw', raw_errors), ('scoring', errors)]:
        computed = Metrics(frame)(values)
        np.testing.assert_allclose(computed, independent_metrics(frame, values), atol=1e-10, rtol=1e-10, equal_nan=True)
        for i, stage in enumerate(STAGES):
            group = result[result.BBCH.eq(stage)]
            site = group.groupby('site')[['raw_attained', 'attained_by_cutoff', 'cutoff_assigned']].mean()
            output.append(dict(model=model, temperature=temperature, method=method, partition=partition,
                BBCH=stage, metric_view=view, n_observations=len(group), n_sites=len(site),
                n_scored=int(np.isfinite(values[frame.BBCH.eq(stage)]).sum()),
                mae_days=computed[i, 0], rmse_days=computed[i, 1], bias_days=computed[i, 2],
                raw_attainment=group.raw_attained.mean(), raw_site_attainment=site.raw_attained.mean(),
                cutoff_attainment=group.attained_by_cutoff.mean(), cutoff_site_attainment=site.attained_by_cutoff.mean(),
                cutoff_assignment_fraction=group.cutoff_assigned.mean(),
                cutoff_assignment_site_fraction=site.cutoff_assigned.mean()))
    return result, pd.DataFrame(output)
