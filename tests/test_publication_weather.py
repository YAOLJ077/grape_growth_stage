"""Publication weather must preserve RAW evidence and reject unsafe resumption."""
import csv
import importlib.util
import json
from pathlib import Path

import pandas as pd
import pytest

MODULE = Path(__file__).resolve().parents[1] / 'src/weather_processing/prepare_publication_weather.py'


def module():
    assert MODULE.exists(), 'Publication weather preparation is not implemented'
    spec = importlib.util.spec_from_file_location('publication_weather', MODULE)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def inputs(tmp_path, content='Date,Tmean,Tmean_DEM\n2000-02-28,10.000000000000001,9\n2000-02-29,,\n2000-03-01,-2.5,-3\n'):
    source = tmp_path / 'original'
    source.mkdir()
    (source / '0001.csv').write_text(content)
    terrain = tmp_path / 'terrain.csv'
    pd.DataFrame([dict(site='FR:tempo:0001', filename='0001.csv',
                      dem_elevation_m=1000, era5_grid_elevation_m=500,
                      site_minus_grid_elevation_m=500, era5_grid_id='45.0_7.0')]).to_csv(terrain, index=False)
    return terrain, source, tmp_path / 'publication'


def test_new_correction_preserves_raw_strings_missing_days_and_source(tmp_path):
    m = module()
    terrain, source, output = inputs(tmp_path)
    before = (source / '0001.csv').read_bytes()
    summary = m.prepare(terrain, source, output)
    with (output / 'sites/0001.csv').open() as f:
        rows = list(csv.DictReader(f))
    assert rows[0]['Tmean'] == '10.000000000000001'
    assert float(rows[0]['Tmean_DEM']) == pytest.approx(6.75)
    assert rows[1] == dict(Date='2000-02-29', Tmean='', Tmean_DEM='')
    assert float(rows[2]['Tmean_DEM']) == -5.75
    assert (source / '0001.csv').read_bytes() == before
    assert summary['n_completed'] == 1
    audit = pd.read_csv(output / 'audit.csv')
    assert audit.iloc[0].n_finite_raw == 2
    assert audit.iloc[0].n_old_dem_changed == 2


@pytest.mark.parametrize('content', [
    'Date,Tmean\n2000-02-29,10\n2000-02-29,11\n',
    'Date,Tmean\n2001-02-29,10\n',
    'Date,Tmean\n2000-02-29,inf\n',
    'Date,Tmean\n2000-02-29,invalid\n',
])
def test_invalid_original_weather_never_becomes_completed(tmp_path, content):
    m = module()
    terrain, source, output = inputs(tmp_path, content)
    with pytest.raises(ValueError):
        m.prepare(terrain, source, output)
    assert not (output / 'sites/0001.csv').exists()
    assert not (output / 'completion.json').exists()


def test_resume_verifies_original_and_generated_files(tmp_path):
    m = module()
    terrain, source, output = inputs(tmp_path)
    m.prepare(terrain, source, output)
    first = (output / 'sites/0001.csv').read_bytes()
    m.prepare(terrain, source, output)
    assert (output / 'sites/0001.csv').read_bytes() == first
    (output / 'sites/0001.csv').write_text('Date,Tmean,Tmean_DEM\n')
    with pytest.raises(ValueError, match='hash'):
        m.prepare(terrain, source, output)


def test_resume_rejects_changed_source(tmp_path):
    m = module()
    terrain, source, output = inputs(tmp_path)
    m.prepare(terrain, source, output)
    with (source / '0001.csv').open('a') as f:
        f.write('2000-03-02,3,2\n')
    with pytest.raises(ValueError, match='hash'):
        m.prepare(terrain, source, output)


def test_resume_rejects_corrupted_audit_identity(tmp_path):
    m = module()
    terrain, source, output = inputs(tmp_path)
    m.prepare(terrain, source, output)
    record = next((output / 'records').glob('*.json'))
    payload = json.loads(record.read_text())
    payload['site'] = 'wrong:site'
    record.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='record'):
        m.prepare(terrain, source, output)


def test_resume_recovers_only_identical_output_after_record_commit_interruption(tmp_path, monkeypatch):
    m = module()
    terrain, source, output = inputs(tmp_path)
    write = m.write_json

    def interrupted_write(path, value):
        if path.parent.name == 'records':
            raise RuntimeError('interrupted before per-site record commit')
        write(path, value)

    monkeypatch.setattr(m, 'write_json', interrupted_write)
    with pytest.raises(RuntimeError, match='interrupted'):
        m.prepare(terrain, source, output)
    first = (output / 'sites/0001.csv').read_bytes()
    monkeypatch.setattr(m, 'write_json', write)
    assert m.prepare(terrain, source, output)['n_completed'] == 1
    assert (output / 'sites/0001.csv').read_bytes() == first
    for record in (output / 'records').glob('*.json'):
        record.unlink()
    (output / 'sites/0001.csv').write_text('Date,Tmean,Tmean_DEM\n2000-02-28,99,95.75\n')
    with pytest.raises(ValueError, match='Unrecorded output.*mismatch'):
        m.prepare(terrain, source, output)


def test_missing_elevation_audited_without_fabricating_weather(tmp_path):
    m = module()
    terrain, source, output = inputs(tmp_path)
    frame = pd.read_csv(terrain)
    frame.loc[0, 'dem_elevation_m'] = float('nan')
    frame.to_csv(terrain, index=False)
    summary = m.prepare(terrain, source, output)
    assert summary['n_completed'] == 0
    assert summary['n_excluded'] == 1
    assert not (output / 'sites/0001.csv').exists()
    assert pd.read_csv(output / 'audit.csv').iloc[0].status == 'nonfinite_elevation'


@pytest.mark.parametrize('name', ['../escape.csv', '/escape.csv'])
def test_filename_escape_rejected_before_any_output(tmp_path, name):
    m = module()
    terrain, source, output = inputs(tmp_path)
    frame = pd.read_csv(terrain)
    frame.loc[0, 'filename'] = name
    frame.to_csv(terrain, index=False)
    with pytest.raises(ValueError, match='basename'):
        m.prepare(terrain, source, output)
    assert not output.exists()
