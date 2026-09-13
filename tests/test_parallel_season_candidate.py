"""A workqueue-backed seasonal kernel must survive concurrent Python callers."""
from pathlib import Path
import os
import subprocess
import sys


def test_parallel_season_candidate_preserves_outputs_with_two_fitting_threads():
    root = Path(__file__).resolve().parents[1]
    script = r'''
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import sys
from threading import Barrier
import numba
import numpy as np
from model.fast_thresholds import _seasonal_batch
kernel = _seasonal_batch
rng = np.random.default_rng(20260911)
forcing = rng.uniform(0., 10., (100, 4, 730))
chilling = np.cumsum(rng.uniform(0., 1., (100, 730)), axis=1)
before = np.column_stack([np.zeros(100), chilling[:, :-1]])
args = (forcing, chilling, before, np.full(100, 730, dtype=np.int64),
        np.array([400., 650., 600., 450.]), 40., .2, 1)
def equal(left, right):
    for a, b in zip(left, right):
        np.testing.assert_array_equal(a, b)
expected = _seasonal_batch(*args)
equal(expected, kernel(*args))
assert numba.threading_layer() == 'workqueue'
start = Barrier(2)
def fit_worker(_):
    start.wait(timeout=10)
    for _ in range(20):
        equal(expected, kernel(*args))
with ThreadPoolExecutor(max_workers=2) as pool:
    list(pool.map(fit_worker, range(2)))
print('40 concurrent-caller evaluations match the serial kernel')
'''
    env = {**os.environ, 'NUMBA_NUM_THREADS': '2', 'NUMBA_THREADING_LAYER': 'workqueue',
           'OPENBLAS_NUM_THREADS': '1', 'OMP_NUM_THREADS': '1'}
    completed = subprocess.run([sys.executable, '-c', script], cwd=root, env=env,
                               capture_output=True, text=True, timeout=45)
    assert completed.returncode == 0, completed.stderr[-2000:]
    assert '40 concurrent-caller evaluations match' in completed.stdout
