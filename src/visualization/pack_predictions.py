#!/usr/bin/env python3
"""One-time packaging of locked predictions; ordinary reproduction reads the bundle.

This packaging command requires the original completed model_run files. It verifies
all source hashes and recomputes errors from dates before writing a compact cube.
"""
from pathlib import Path
import json
import numpy as np
import pandas as pd
from common import ROOT,DATA,MODELS,digest

def main():
    run=ROOT/'model_run/results/median_cutoff_ml_20260912'
    manifest=json.loads((run/'final_analysis/manifest.json').read_text())
    identity=None;models=[];sources={}
    for model in MODELS:
        arms=[]
        for temperature in ['RAW','DEM']:
            key=f'{model}/{temperature}/predictions.csv.gz';path=run/key
            assert digest(path)==manifest['source_sha256'][key],key
            sources[key]=digest(path)
            f=pd.read_csv(path,usecols=['observation_id','site','BBCH','Date','partition',
                'temperature_zone_id','country','method','scoring_date','scoring_error_days'],
                dtype={'site':str,'BBCH':str})
            for method in ['process','tabm']:
                g=f[f.method.eq(method)].sort_values('observation_id').reset_index(drop=True)
                ids=g[['observation_id','site','BBCH','Date','partition','temperature_zone_id','country']]
                if identity is None:identity=ids
                else:pd.testing.assert_frame_equal(identity,ids)
                errors=(pd.to_datetime(g.scoring_date)-pd.to_datetime(g.Date)).dt.total_seconds()/86400
                np.testing.assert_allclose(errors,g.scoring_error_days,equal_nan=True,atol=1e-9)
                arms.append(errors.to_numpy())
        models.append(np.array(arms).T)
    sites=pd.read_csv(DATA/'environment/environmental_zone_sites.csv',usecols=['site','group_id'],dtype=str)
    identity=identity.merge(sites,on='site',validate='many_to_one',how='left',sort=False)
    assert len(identity)==74618 and identity.group_id.notna().all()
    folder=DATA/'predictions';folder.mkdir(exist_ok=True)
    identity.to_csv(folder/'identity.csv.gz',index=False,compression={'method':'gzip','mtime':0})
    np.savez_compressed(folder/'scoring_errors.npz',errors=np.stack(models,axis=1))
    provenance={'shape':[74618,10,4],'models':MODELS,'arms':['RAW_process','RAW_ML','DEM_process','DEM_ML'],
        'row_identity':'identity.csv.gz, sorted by observation_id','unit':'days',
        'definition':'scoring_date minus observed Date; fixed 4 November assignments retained',
        'source_predictions_verified':sources,'errors_independently_recomputed_from_dates':True}
    (folder/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
    p=DATA/'manifest.json';m=json.loads(p.read_text())
    for item in folder.iterdir():
        m['files'][str(item.relative_to(DATA))]={'source':'Verified locked predictions; see predictions/provenance.json','sha256':digest(item)}
    m['scope']='Recompute published scoring-error statistics and figures from locked predictions, frozen covariates, observations and map inputs; no model retraining'
    p.write_text(json.dumps(m,indent=2)+'\n')
    print('Packaged 74,618 observations × 10 structures × 4 prediction arms.')

if __name__=='__main__':main()
