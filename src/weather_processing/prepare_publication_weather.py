#!/usr/bin/env python3
"""Create a separate, hash-verified RAW/DEM weather snapshot from site terrain.

Original files remain unchanged. Date and Tmean field strings are preserved,
including missing values. Existing DEM columns are audited and recalculated
using the supplied official-grid elevation. No missing dates are filled.
"""
from __future__ import annotations

import argparse
import csv
from datetime import date
import hashlib
import json
import math
from pathlib import Path
import tempfile

import pandas as pd

LAPSE_RATE = 0.0065


def file_hash(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + '.tmp')
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True, allow_nan=False) + '\n')
    temporary.replace(path)


def record_hash(value):
    payload = {key: item for key, item in value.items() if key != 'record_sha256'}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, allow_nan=False).encode()).hexdigest()


def temperature(value):
    if value.strip().lower() in {'', 'nan', 'na', 'null', 'none'}:
        return None
    number = float(value)
    if not math.isfinite(number):
        raise ValueError('Nonfinite nonmissing temperature')
    return number


def convert_file(source, destination, offset):
    output, seen, first, last = [], set(), None, None
    finite_raw = old_finite = changed = 0
    max_change = 0.0
    with source.open(newline='') as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames not in [['Date', 'Tmean'], ['Date', 'Tmean', 'Tmean_DEM']]:
            raise ValueError(f'Unexpected weather schema: {source}')
        had_dem = 'Tmean_DEM' in reader.fieldnames
        for row in reader:
            if None in row or any(v is None for v in row.values()):
                raise ValueError(f'Malformed CSV row: {source}')
            day = date.fromisoformat(row['Date'])
            if day.isoformat() != row['Date'] or day in seen:
                raise ValueError(f'Invalid or duplicate Date: {source}: {row["Date"]}')
            seen.add(day)
            first = min(first, day) if first else day
            last = max(last, day) if last else day
            raw = temperature(row['Tmean'])
            adjusted = raw + offset if raw is not None else None
            if adjusted is not None and not math.isfinite(adjusted):
                raise ValueError('Nonfinite corrected temperature')
            finite_raw += raw is not None
            if had_dem:
                old = temperature(row['Tmean_DEM'])
                old_finite += old is not None
                if old is not None and adjusted is not None:
                    difference = abs(old - adjusted)
                    changed += difference > 1e-6
                    max_change = max(max_change, difference)
            output.append([row['Date'], row['Tmean'], '' if adjusted is None else repr(adjusted)])
    if not output:
        raise ValueError(f'Empty weather file: {source}')
    # Only expose the destination after every source record has passed validation.
    temporary = destination.with_suffix('.csv.tmp')
    with temporary.open('w', newline='') as stream:
        writer = csv.writer(stream, lineterminator='\n')
        writer.writerow(['Date', 'Tmean', 'Tmean_DEM'])
        writer.writerows(output)
    temporary.replace(destination)
    return dict(n_rows=len(output), n_finite_raw=int(finite_raw),
                n_missing_raw=len(output)-int(finite_raw), first_date=first.isoformat(),
                last_date=last.isoformat(), source_had_dem=had_dem,
                n_old_dem_finite=int(old_finite), n_old_dem_changed=int(changed),
                max_absolute_old_dem_change_c=max_change, temperature_offset_c=offset)


def prepare(terrain_path, weather_dir, output):
    terrain_path, weather_dir, output = map(Path, (terrain_path, weather_dir, output))
    terrain = pd.read_csv(terrain_path, dtype=str, keep_default_na=False)
    required = ['site', 'filename', 'dem_elevation_m', 'era5_grid_elevation_m',
                'site_minus_grid_elevation_m', 'era5_grid_id']
    if not set(required).issubset(terrain.columns):
        raise ValueError(f'Terrain requires {required}')
    for name in ['site', 'filename', 'era5_grid_id']:
        if terrain[name].eq('').any():
            raise ValueError(f'Empty terrain {name}')
    if terrain.site.duplicated().any() or terrain.filename.duplicated().any():
        raise ValueError('Duplicate site identity or weather filename')
    if any(Path(name).name != name or '/' in name or '\\' in name for name in terrain.filename):
        raise ValueError('Weather filename must be a basename')
    if output.resolve() == weather_dir.resolve() or (output / 'sites').resolve() == weather_dir.resolve():
        raise ValueError('Output must be separate from original weather')
    request = dict(schema_version=1, terrain_path=str(terrain_path.resolve()),
                   terrain_sha256=file_hash(terrain_path), weather_dir=str(weather_dir.resolve()),
                   source_sha256=file_hash(__file__), lapse_rate_c_per_m=LAPSE_RATE,
                   equation='Tmean_DEM = Tmean - 0.0065 * site_minus_grid_elevation_m',
                   raw_preservation='exact CSV field strings and record order; no missing-date insertion')
    if output.exists():
        if not (output / 'request.json').exists() or json.loads((output / 'request.json').read_text()) != request:
            raise ValueError('Publication weather request/hash mismatch')
    else:
        output.mkdir(parents=True)
        write_json(output / 'request.json', request)
        (output / 'source.py').write_bytes(Path(__file__).read_bytes())
    (output / 'sites').mkdir(exist_ok=True)
    (output / 'records').mkdir(exist_ok=True)
    audits = []
    for row in terrain.sort_values('site').itertuples(index=False):
        record = output / 'records' / (hashlib.sha256(row.site.encode()).hexdigest() + '.json')
        source, destination = weather_dir / row.filename, output / 'sites' / row.filename
        source_hash = file_hash(source) if source.exists() else None
        if record.exists():
            audit = json.loads(record.read_text())
            if (audit.get('record_sha256') != record_hash(audit) or
                    any(audit.get(key) != getattr(row, key) for key in ['site', 'filename', 'era5_grid_id'])):
                raise ValueError(f'Publication weather record identity/hash mismatch: {row.site}')
            if audit['source_sha256'] != source_hash:
                raise ValueError(f'Original weather hash mismatch: {row.site}')
            if audit['status'] == 'completed' and (not destination.exists() or file_hash(destination) != audit['output_sha256']):
                raise ValueError(f'Generated weather hash mismatch: {row.site}')
            audits.append(audit)
            continue
        audit = dict(site=row.site, filename=row.filename, era5_grid_id=row.era5_grid_id,
                     source_sha256=source_hash, output_sha256=None)
        elevations = [temperature(getattr(row, name)) for name in required[2:5]]
        if any(value is None for value in elevations):
            audit['status'] = 'nonfinite_elevation'
        elif not math.isclose(elevations[0]-elevations[1], elevations[2], rel_tol=0, abs_tol=1e-6):
            raise ValueError(f'Elevation difference mismatch: {row.site}')
        elif not source.is_file():
            audit['status'] = 'missing_weather'
        else:
            if destination.exists():
                # Recover a crash between data publication and record commit only
                # after independent re-conversion proves the exact existing bytes.
                with tempfile.TemporaryDirectory(prefix='weather-recovery-', dir=output) as temporary:
                    candidate = Path(temporary) / row.filename
                    details = convert_file(source, candidate, -LAPSE_RATE * elevations[2])
                    if file_hash(candidate) != file_hash(destination):
                        raise ValueError(f'Unrecorded output hash mismatch: {row.site}')
                audit.update(details)
            else:
                audit.update(convert_file(source, destination, -LAPSE_RATE * elevations[2]))
            if file_hash(source) != source_hash:
                destination.unlink()
                raise ValueError(f'Original weather changed during conversion: {row.site}')
            audit.update(status='completed', output_sha256=file_hash(destination))
        audit['record_sha256'] = record_hash(audit)
        write_json(record, audit)
        audits.append(audit)
        if len(audits) % 250 == 0:
            print(f'Publication weather: {len(audits)}/{len(terrain)} sites', flush=True)
    pd.DataFrame(audits).to_csv(output / 'audit.csv', index=False)
    completed = sum(row['status'] == 'completed' for row in audits)
    summary = dict(n_sites=len(audits), n_completed=completed, n_excluded=len(audits)-completed,
                   n_rows=sum(row.get('n_rows', 0) for row in audits),
                   n_missing_raw=sum(row.get('n_missing_raw', 0) for row in audits),
                   audit_sha256=file_hash(output / 'audit.csv'), request=request,
                   limitation='Full-window eligibility is determined separately by the modelling cohort audit.')
    write_json(output / 'completion.json', summary)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--terrain', type=Path, required=True)
    parser.add_argument('--weather-dir', type=Path, default=Path('data/weather/sites'))
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(args.terrain, args.weather_dir, args.output), indent=2))


if __name__ == '__main__':
    main()
