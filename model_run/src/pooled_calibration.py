"""Isolated fixed-response threshold evaluation and equal-site calibration metrics.

No changes to the frozen model API. Prefix sums retain discarded daily overshoot
and next-day stage starts; every published fit requires canonical replay.
"""
import numpy as np
import pandas as pd
from numba import njit, prange

from model import responses
from model.parameters import validate_parameters
from model.registry import get_model
from model.specification import STAGES
from model.structure_comparison import fixed_parameters


@njit(cache=True, inline='always')
def prefix_crossing(prefix, inverse, n, requirement, offset, start):
    target = requirement + offset
    if prefix[n] - offset < requirement:
        return n + 1
    bucket = min(255, max(0, int(target / prefix[n] * 256)))
    lo = max(start, inverse[bucket])
    hi = max(lo, inverse[bucket+1])
    # Protect lookup-bin arithmetic at exact floating-point boundaries.
    if lo > start and prefix[lo-1] - offset >= requirement:
        lo = start
    if prefix[hi] - offset < requirement:
        hi = n + 1
    while lo < hi:
        mid = (lo + hi) // 2
        if prefix[mid] - offset >= requirement:
            hi = mid
        else:
            lo = mid + 1
    return lo


@njit(cache=True, parallel=True)
def crossings(f, c, fc, f_inverse, c_inverse, lengths, january, requirements, chill, minimum, interaction):
    result = np.full((len(lengths), 4), -1, dtype=np.int64)
    for i in prange(len(lengths)):
        n = lengths[i]
        start = january[i] if interaction == 0 else 0
        cap = n
        if interaction == 1:
            start = prefix_crossing(c[i],c_inverse[i],n,chill*(1-1e-12),0.,1)
        if interaction == 2:
            lo, hi = 0, n
            while lo < hi:
                mid = (lo + hi) // 2
                if c[i, mid] >= chill:
                    hi = mid
                else:
                    lo = mid + 1
            cap = lo
        for s in range(4):
            if start >= n:
                break
            lo, hi = start + 1, n + 1
            target = requirements[s] * (1 - 1e-12)
            if s != 0 or interaction != 2:
                lo = prefix_crossing(f[i],f_inverse[i],n,target,f[i,start],start+1)
            elif target > (minimum*f[i,cap]+(1-minimum)*fc[i,cap]/chill)*(1+1e-12):
                offset = (1-minimum)*(f[i,cap]-fc[i,cap]/chill)
                lo = prefix_crossing(f[i],f_inverse[i],n,target,offset,1)
            else:
                hi = min(n+1,cap+1)
                while lo < hi:
                    mid = (lo + hi) // 2
                    upto = min(mid, cap)
                    value = minimum * f[i, mid] + (1 - minimum) * (
                        fc[i, upto] / chill + f[i, mid] - f[i, upto])
                    if value >= target:
                        hi = mid
                    else:
                        lo = mid + 1
            if lo > n:
                break
            result[i, s] = lo - 1
            start = lo
    return result


class RateEvaluator:
    def __init__(self, name, prepared):
        self.name, self.prepared = name, prepared
        self.fixed = fixed_parameters(name)
        spec = get_model(name)
        self.interaction = {'none':0, 'sequential':1, 'parallel':2}[spec.interaction]
        self.lengths = np.array([len(w.dates) for w in prepared], dtype=np.int64)
        n = int(self.lengths.max())
        self.f = np.zeros((len(prepared), n + 1))
        self.c = np.zeros_like(self.f)
        self.fc = np.zeros_like(self.f)
        self.f_inverse = np.zeros((len(prepared),257),dtype=np.int64)
        self.c_inverse = np.zeros_like(self.f_inverse)
        self.date_numbers = np.full((len(prepared), n), np.iinfo(np.int64).min, dtype=np.int64)
        self.january = np.zeros(len(prepared), dtype=np.int64)
        for i, w in enumerate(prepared):
            length = len(w.dates)
            self.date_numbers[i,:length] = w.dates.astype('datetime64[D]').astype(np.int64)
            self.january[i] = np.searchsorted(w.dates, np.datetime64(f'{w.season}-01-01'))
            rate = (responses.linear(w.temperature, self.fixed['forcing_base_07']) if spec.forcing == 'linear'
                    else responses.beta(w.temperature, self.fixed['forcing_minimum'],
                        self.fixed['forcing_optimum_07'], self.fixed['forcing_maximum']))
            self.f[i,1:length+1] = np.cumsum(rate)
            self.f_inverse[i] = np.searchsorted(self.f[i,:length+1],np.linspace(0,self.f[i,length],257))
            if spec.chilling != 'none':
                fn = responses.triangular if spec.chilling == 'triangular' else responses.beta
                cold = fn(w.temperature, *[self.fixed[f'chilling_{k}'] for k in ['minimum','optimum','maximum']])
                self.c[i,1:length+1] = np.cumsum(cold)
                self.fc[i,1:length+1] = np.cumsum(rate * self.c[i,:length])
                self.c_inverse[i] = np.searchsorted(self.c[i,:length+1],np.linspace(0,self.c[i,length],257))

    def positions(self, parameters):
        return crossings(self.f, self.c, self.fc, self.f_inverse, self.c_inverse, self.lengths, self.january,
            np.array([parameters[f'forcing_requirement_{s}'] for s in STAGES]),
            parameters.get('chilling_requirement', 1.), parameters.get('minimum_response', 0.), self.interaction)

    def predict(self, parameters):
        validate_parameters(self.name, parameters)
        if any(parameters[k] != v for k,v in self.fixed.items()):
            raise ValueError('Fixed response profile changed')
        pos = self.positions(parameters)
        result = np.full(pos.shape, np.iinfo(np.int64).min, dtype=np.int64)
        rows, cols = np.nonzero(pos >= 0)
        result[rows,cols] = self.date_numbers[rows,pos[rows,cols]]
        return result.astype('datetime64[D]')


@njit(cache=True)
def metric_values(errors, groups, site_stages, counts, stage_counts, site_counts):
    sums = np.zeros((len(counts), 4))
    for i in range(len(errors)):
        if np.isfinite(errors[i]):
            g = groups[i]
            sums[g,0] += abs(errors[i])
            sums[g,1] += errors[i] ** 2
            sums[g,2] += errors[i]
            sums[g,3] += 1
    result = np.zeros((4,6))
    finite_sites = np.zeros(4)
    for g in range(len(counts)):
        s = site_stages[g]
        finite = sums[g,3]
        if finite:
            finite_sites[s] += 1
            result[s,0] += sums[g,0] / finite
            result[s,1] += sums[g,1] / finite
            result[s,2] += sums[g,2] / finite
        result[s,3] += finite
        result[s,4] += finite / counts[g]
        result[s,5] += (sums[g,1] + (counts[g]-finite)*1e6) / counts[g]
    for s in range(4):
        for col in range(3):
            result[s,col] = result[s,col] / finite_sites[s] if finite_sites[s] else np.nan
        result[s,1] = np.sqrt(result[s,1])
        result[s,3] /= stage_counts[s]
        result[s,4] /= site_counts[s]
        result[s,5] = np.sqrt(result[s,5] / site_counts[s])
    return result


class Metrics:
    """Columns: finite-site MAE, RMSE, bias, record/site attainment, old loss."""
    def __init__(self, frame):
        if set(frame.BBCH) != set(STAGES):
            raise ValueError('Require all four stages')
        index = pd.MultiIndex.from_frame(frame[['BBCH','site']])
        self.groups, unique = pd.factorize(index, sort=True)
        self.site_stages = np.array([STAGES.index(s) for s, _ in unique], dtype=np.int64)
        self.counts = np.bincount(self.groups).astype(float)
        self.stage_counts = np.array([(frame.BBCH == s).sum() for s in STAGES], dtype=float)
        self.site_counts = np.bincount(self.site_stages, minlength=4).astype(float)

    def __call__(self, errors):
        errors = np.asarray(errors, dtype=float)
        if errors.shape != self.groups.shape:
            raise ValueError('An error or non-attainment is required for every observation')
        return metric_values(errors, self.groups, self.site_stages, self.counts, self.stage_counts, self.site_counts)


def weighted_median(values, weights):
    good = np.isfinite(values) & np.isfinite(weights) & (weights > 0)
    if not good.any():
        raise ValueError('No valid weighted median inputs')
    order = np.argsort(values[good], kind='stable')
    v, w = values[good][order], weights[good][order]
    return float(v[np.searchsorted(np.cumsum(w), w.sum()/2, side='left')])


def select_partitions(observations, protocol):
    obs = observations.copy()
    obs['Date'] = pd.to_datetime(obs.Date, errors='raise')
    obs['season'] = obs.Date.dt.year
    joined = obs.merge(protocol, on=['site','season'], how='left', validate='many_to_one')
    if joined.partition.isna().any() or set(joined.partition) != {'calibration','test'}:
        raise ValueError('Every observation needs its frozen calibration/test assignment')
    train = joined[joined.partition.eq('calibration')].reset_index(drop=True)
    test = joined[joined.partition.eq('test')].reset_index(drop=True)
    if set(train.site) & set(test.site):
        raise ValueError('Calibration and test sites overlap')
    return train, test
