"""Original equal-site, equal-stage group bootstrap; 2,000 draws, seed 20260913.

Derived from model_run/src/analyze_raw_structure_spatial.py. Alternative process
structures are fixed, not bootstrap replicates; missing stages remain missing.
"""
import numpy as np
import pandas as pd
from common import STAGES
NBOOT=2000

def summarise(data,columns,seed=20260913):
    """Fixed-model summaries; resample original groups, never alternative models."""
    site=data.groupby(['group_id','site','BBCH'],sort=True)[columns].mean().reset_index()
    groups=sorted(site.group_id.unique());n=len(groups)
    sums=np.zeros((n,4,len(columns)));counts=np.zeros((n,4));index={g:i for i,g in enumerate(groups)}
    for j,stage in enumerate(STAGES):
        rows=site[site.BBCH.eq(stage)];a=rows.groupby('group_id')[columns].sum();b=rows.groupby('group_id').size()
        ii=[index[g] for g in a.index];sums[ii,j]=a;counts[ii,j]=b
    def score(s,c):
        return np.divide(s,c[...,None],out=np.full_like(s,np.nan),where=c[...,None]>0)
    point=score(sums.sum(0),counts.sum(0));rng=np.random.default_rng(seed)
    weights=rng.multinomial(n,np.full(n,1/n),size=NBOOT) if n else np.empty((NBOOT,0))
    boot=score(np.einsum('bg,gsk->bsk',weights,sums,optimize=False),weights@counts)
    rows=[]
    for j,stage in enumerate([*STAGES,'ALL']):
        values=point.mean(0) if stage=='ALL' else point[j]
        samples=boot.mean(1) if stage=='ALL' else boot[:,j]
        eligible=data if stage=='ALL' else data[data.BBCH.eq(stage)]
        support=(counts>0).sum(0);enough=(support>=10).all() if stage=='ALL' else support[j]>=10
        for k,col in enumerate(columns):
            transform=np.sqrt if col.endswith('mse') else lambda x:x
            v=float(transform(values[k]));draws=transform(samples[:,k]);valid=np.isfinite(draws)
            available=enough and valid.sum()>=.95*NBOOT
            ci=np.quantile(draws[valid],[.025,.975]) if available else [np.nan,np.nan]
            rows.append(dict(BBCH=stage,metric=col.replace('mse','rmse'),value=v,ci_low=ci[0],ci_high=ci[1],
                ci_status='available' if available else 'missing_stage' if not np.isfinite(v) else 'insufficient_groups',
                n_observations=len(eligible),n_sites=eligible.site.nunique(),n_groups=eligible.group_id.nunique()))
        if 'left_abs' in columns:
            a,b=columns.index('left_abs'),columns.index('right_abs');draws=samples[:,b]-samples[:,a]
            valid=np.isfinite(draws);available=enough and valid.sum()>=.95*NBOOT
            ci=np.quantile(draws[valid],[.025,.975]) if available else [np.nan,np.nan]
            rows.append(dict(BBCH=stage,metric='mae_change',value=float(values[b]-values[a]),ci_low=ci[0],ci_high=ci[1],
                ci_status='available' if available else 'insufficient_groups',n_observations=len(eligible),
                n_sites=eligible.site.nunique(),n_groups=eligible.group_id.nunique()))
    return pd.DataFrame(rows)
