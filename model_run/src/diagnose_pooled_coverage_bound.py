"""Conservative calibration-only feasibility certificate for RAW FL/FB maturity."""
from pathlib import Path
import sys,json,hashlib
import numpy as np,pandas as pd
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from model.responses import linear,beta
from model.data import SeasonWeather
from model.structure_comparison import fixed_parameters
from model_run.src.pooled_calibration import RateEvaluator
r=ROOT/'model_run/results/pooled_calibration_20260912'
configuration=json.loads((r/'run.json').read_text())
obs=pd.read_csv(r/'calibration_observations.csv.gz',dtype={'site':str,'BBCH':str},keep_default_na=False)
assert obs.partition.eq('calibration').all()
obs=obs[obs.BBCH.eq('89')].copy()
keys=obs[['site','season']].drop_duplicates()
parts=[]
w=ROOT/'model_run/results/publication_cohort_20260910/weather.csv.gz'
for chunk in pd.read_csv(w,chunksize=300000,usecols=['site','Date','Tmean'],dtype={'site':str,'Date':str}):
 chunk['season']=chunk.Date.str[:4].astype(int)
 selected=chunk.merge(keys,on=['site','season'],how='inner',validate='many_to_one')
 if len(selected): parts.append(selected)
daily=pd.concat(parts,ignore_index=True)
weather={}
for key,g in daily.groupby(['site','season']):
 g=g.sort_values('Date')
 expected=pd.date_range(f'{key[1]}-01-01',f'{key[1]}-12-31')
 assert np.array_equal(pd.to_datetime(g.Date).to_numpy(),expected.to_numpy())
 weather[key]=g
summaries=[]
for model,fn in [('FL',lambda t:linear(t,0.)),('FB',lambda t:beta(t,0.,25.4,35.))]:
 original_paths=[p for p in configuration['sources'] if p.endswith(f'/{model}/RAW/pbm/full/predictions.csv')]
 assert len(original_paths)==1
 original_path=Path(original_paths[0])
 with original_path.open('rb') as stream:
  assert hashlib.file_digest(stream,'sha256').hexdigest()==configuration['sources'][str(original_path)]
 original=pd.read_csv(original_path,dtype={'site':str,'BBCH':str},keep_default_na=False)
 original.BBCH=original.BBCH.str.zfill(2)
 check=obs[['site','season','BBCH']].merge(original,on=['site','season','BBCH'],how='left',validate='many_to_one')
 assert check.predicted_date.notna().all() and check.predicted_date.ne('').all()
 profiles={key:fn(g.Tmean.to_numpy()) for key,g in weather.items()}
 totals={key:float(np.sum(rate)) for key,rate in profiles.items()}
 cap=min(totals.values())
 limiting=[key for key,v in totals.items() if abs(v-cap)<1e-8]
 bounds={}
 for key,rate in profiles.items():
  # The first three stage overshoots are each bounded by the largest daily rate.
  # Use a small upward tolerance, making the latest-date bound conservative.
  target=cap+3*float(np.max(rate))+1e-7
  ix=int(np.searchsorted(np.cumsum(rate),target,side='left'))
  bounds[key]=weather[key].Date.iloc[min(ix,len(rate)-1)]
 result=obs.copy()
 result['latest_possible_date_bound']=[bounds[k] for k in result[['site','season']].itertuples(index=False,name=None)]
 result['bound_error_days']=(pd.to_datetime(result.latest_possible_date_bound)-pd.to_datetime(result.Date)).dt.days
 result['annual_forcing']=[totals[k] for k in result[['site','season']].itertuples(index=False,name=None)]
 result['limiting_site_year']=[k in limiting for k in result[['site','season']].itertuples(index=False,name=None)]
 meanbound=float(result.groupby('site').bound_error_days.mean().mean())
 assert (pd.to_datetime(check.predicted_date).to_numpy() <= pd.to_datetime(result.latest_possible_date_bound).to_numpy()).all()
 prepared=tuple(SeasonWeather(s,int(y),pd.to_datetime(g.Date).to_numpy(),g.Tmean.to_numpy())
  for (s,y),g in weather.items())
 evaluator=RateEvaluator(model,prepared)
 upper=np.array([bounds[(p.site,p.season)] for p in prepared],dtype='datetime64[D]')
 rng=np.random.default_rng(20260912)
 feasible_vectors=0
 for _ in range(100):
  requirements=rng.dirichlet(np.ones(4))*cap*rng.uniform(.1,.99)
  parameters={**fixed_parameters(model),**dict(zip([f'forcing_requirement_{s}' for s in ['07','65','81','89']],requirements))}
  predicted=evaluator.predict(parameters)[:,3]
  if not np.isnat(predicted).any():
   assert (predicted <= upper).all()
   feasible_vectors+=1
 assert feasible_vectors>0
 result.to_csv(r/f'{model}_RAW_coverage_bound.csv',index=False)
 summary={'model':model,'temperature':'RAW','stage':'89','annual_forcing_cap':cap,
  'limiting_site_years':[[s,int(y)] for s,y in limiting],'site_weighted_bias_upper_bound_days':meanbound,
  'one_day_bias_target_impossible_under_full_attainment':meanbound < -1,
  'n_observations':len(result),'n_sites':result.site.nunique(),
  'random_feasible_parameter_vectors_verified':feasible_vectors,'baseline_prediction_bound_verified':True}
 summaries.append(summary);print(json.dumps(summary),flush=True)
sourcehash={}
for path in [w,r/'calibration_observations.csv.gz',Path(__file__),ROOT/'model/responses.py',ROOT/'model/structure_comparison.py']:
 with path.open('rb') as stream: sourcehash[str(path)]=hashlib.file_digest(stream,'sha256').hexdigest()
(r/'coverage_feasibility_bound.json').write_text(json.dumps({'method':'For FL/FB with identical fixed forcing functions across all stages and January 1 start, total four-stage thresholds cannot exceed the minimum annual forcing of any maturity site-year when 100% attainment is required. Three discarded overshoots are bounded by three times that season maximum daily rate. The crossing date of this optimistic budget, or December 31 if the budget is not crossed, bounds any attained maturity prediction from above. An upward 1e-7 response-unit tolerance makes the calculation conservative.','scope':'Calibration observations only; RAW FL and FB have 100% baseline maturity attainment. No inference for DEM fits with pre-existing failures.','sources':sourcehash,'results':summaries},indent=2)+'\n')
