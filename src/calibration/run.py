#!/usr/bin/env python3
"""Recalibrate the final study in a fresh directory using the frozen engines."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
RESULTS = ROOT / 'model_run/results'


def validate_output(output: Path, root: Path = ROOT) -> Path:
    output, root = output.resolve(), root.resolve()
    if output == root or output.is_relative_to(root / 'model_run/results'):
        raise ValueError('Choose a fresh output outside the frozen model_run/results tree')
    if output.exists():
        raise FileExistsError(f'Output already exists: {output}; choose a new directory')
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['all', 'pooled', 'process', 'hybrid'], default='all')
    parser.add_argument('--output', type=Path, required=True,
                        help='Fresh parent directory; each selected phase gets its own subdirectory')
    parser.add_argument('--threads', type=int, choices=range(1, 8), default=7)
    parser.add_argument('--cohort', type=Path, default=RESULTS / 'publication_cohort_20260910')
    parser.add_argument('--initial-run', type=Path, default=RESULTS / 'publication_factorial_20260911_v3')
    parser.add_argument('--observations', type=Path, default=RESULTS / 'cleaned_reevaluation_20260912/observations.csv')
    parser.add_argument('--population-run', type=Path, default=RESULTS / 'pooled_calibration_20260912',
                        help='Frozen pooled population/locks for process or hybrid alone')
    parser.add_argument('--process-run', type=Path, default=RESULTS / 'median_cutoff_calibration_20260912',
                        help='Completed process source when selecting hybrid alone')
    parser.add_argument('--dry-run', action='store_true', help='Print exact commands without creating files')
    args = parser.parse_args(argv)
    output = validate_output(args.output)
    phases = ['pooled', 'process', 'hybrid'] if args.phase == 'all' else [args.phase]
    pooled = output / 'pooled' if args.phase == 'all' else args.population_run.resolve()
    process = output / 'process' if args.phase == 'all' else args.process_run.resolve()
    engine = ROOT / 'model_run/src'
    commands = {
        'pooled': [sys.executable, str(engine / 'calibrate_pooled_sites.py'),
                   '--run', str(args.initial_run.resolve()), '--cohort', str(args.cohort.resolve()),
                   '--observations', str(args.observations.resolve()), '--output', str(output / 'pooled')],
        'process': [sys.executable, str(engine / 'calibrate_median_cutoff.py'),
                    '--source-run', str(pooled), '--cohort', str(args.cohort.resolve()),
                    '--output', str(output / 'process'), '--threads', str(args.threads)],
        'hybrid': [sys.executable, str(engine / 'run_cutoff_ml.py'),
                   '--source-run', str(process), '--population-run', str(pooled),
                   '--cohort', str(args.cohort.resolve()), '--output', str(output / 'hybrid'),
                   '--threads', str(args.threads)],
    }
    selected = {phase: commands[phase] for phase in phases}
    print(json.dumps(selected, indent=2), flush=True)
    if args.dry_run:
        return 0
    # A historical process manifest stores absolute input keys. Fresh phases
    # produce local keys; a relocated hybrid-only source requires process refit.
    if args.phase == 'hybrid':
        source = json.loads((process / 'run.json').read_text())['sources']
        required = [pooled / 'calibration_observations.csv.gz',
                    pooled / 'test_observations.csv.gz', args.cohort.resolve() / 'weather.csv.gz']
        if any(str(path) not in source for path in required):
            raise ValueError('Process input keys belong to another checkout. Run --phase all, or supply '
                             '--process-run and --population-run produced together in this checkout.')
    output.mkdir(parents=True)
    (output / 'commands.json').write_text(json.dumps(selected, indent=2) + '\n')
    environment = os.environ.copy()
    environment['NUMBA_NUM_THREADS'] = str(args.threads)
    for name in ['OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'VECLIB_MAXIMUM_THREADS']:
        environment[name] = '1'
    for command in selected.values():
        subprocess.run(command, check=True, cwd=ROOT, env=environment)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
