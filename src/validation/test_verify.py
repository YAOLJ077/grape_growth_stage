"""Regression checks for portable evidence verification and fresh-output safety."""
import hashlib
import importlib
import json

import pandas as pd
import pytest


def test_relocated_sources_use_current_checkout_and_reject_escape(tmp_path):
    verify = importlib.import_module('src.validation.verify')
    source = tmp_path / 'model' / 'responses.py'
    source.parent.mkdir()
    source.write_text('frozen source\n')
    assert verify.resolve_source('/old/checkout/model/responses.py', tmp_path) == source
    with pytest.raises(ValueError):
        verify.resolve_source('../outside.py', tmp_path)


def test_sealed_files_fail_after_corruption(tmp_path):
    verify = importlib.import_module('src.validation.verify')
    value = tmp_path / 'predictions.csv'
    value.write_text('date\n2020-04-01\n')
    marker = tmp_path / 'complete.json'
    marker.write_text(json.dumps({'verified': True, 'artifacts': {
        'predictions.csv': hashlib.sha256(value.read_bytes()).hexdigest()}}))
    assert verify.verify_marker(marker, {}) == 1
    value.write_text('date\n2020-04-02\n')
    with pytest.raises(ValueError, match='SHA-256'):
        verify.verify_marker(marker, {})


def test_metrics_weight_sites_equally_and_retain_missing_predictions():
    verify = importlib.import_module('src.validation.verify')
    frame = pd.DataFrame({'site': ['a', 'a', 'b', 'c'],
        'scoring_error_days': [2., 4., -10., float('nan')],
        'raw_attained': [True, True, True, False],
        'attained_by_cutoff': [True, True, True, False],
        'cutoff_assigned': [False, False, False, False]})
    result = verify.metric_values(frame, 'scoring')
    assert result['mae_days'] == 6.5
    assert result['bias_days'] == -3.5
    assert result['rmse_days'] == pytest.approx(55 ** .5)
    assert result['n_sites'] == 3
    assert result['n_scored'] == 3
    assert result['raw_site_attainment'] == pytest.approx(2 / 3)


def test_fresh_runner_refuses_frozen_and_existing_outputs(tmp_path):
    run = importlib.import_module('src.calibration.run')
    frozen = tmp_path / 'model_run' / 'results'
    frozen.mkdir(parents=True)
    with pytest.raises(ValueError):
        run.validate_output(frozen / 'new', tmp_path)
    existing = tmp_path / 'existing'
    existing.mkdir()
    with pytest.raises(FileExistsError):
        run.validate_output(existing, tmp_path)
    assert run.validate_output(tmp_path / 'fresh', tmp_path) == tmp_path / 'fresh'
