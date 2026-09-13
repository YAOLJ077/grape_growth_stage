"""Immutable RAW/DEM × process/TabM experiments with nested grouped cross-fitting."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import itertools
import json
import os
from pathlib import Path
import platform
import time

import numpy as np
import pandas as pd

from model.artifacts import load_fit, save_fit
from model.calibration import FitSettings, _weather_hash
from model.data import observations as normalize_observations, prepare_weather
from model.registry import MODEL_NAMES, get_model
from model.specification import STAGES
from model.structure_comparison import PROFILE, fixed_parameters, threshold_only_settings
from model.residual.storage import digest, read_json, publish, json_once, table_once, check_hashes, run_lock
from .features import FEATURES, KEYS, TEMPERATURE_COLUMNS, build_features, correct_dates

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SEEDS = (20260907,20260908,20260909)


def log(message):
    print(f'{datetime.now(timezone.utc).isoformat(timespec="seconds")} {message}',flush=True)


def plain(value):
    return json.loads(json.dumps(value,sort_keys=True))


def frame_hash(frame):
    return hashlib.sha256(frame.to_csv(index=False,date_format='%Y-%m-%d').encode()).hexdigest()


def versions():
    return {'python':platform.python_version(), **{name:importlib.metadata.version(name) for name in
        ('numpy','pandas','scipy','scikit-learn','numba','torch','tabm','rtdl_num_embeddings','matplotlib')}}


def sources():
    paths = [*sorted((ROOT/'model').rglob('*.py')), *sorted((ROOT/'model_run/factorial').glob('*.py')),
             ROOT/'model_run/src/run_factorial_experiment.py']
    return {str(path):digest(path) for path in paths}


def read_table(path):
    try:
        frame = pd.read_csv(path,dtype={'site':str,'BBCH':str,'observation_id':str,'group_id':str},keep_default_na=False)
    except pd.errors.EmptyDataError:
        return pd.DataFrame()
    for column in frame.columns:
        if column.endswith('_date') or column == 'Date':
            frame[column] = pd.to_datetime(frame[column],errors='raise')
    # Standard pandas numeric inference is retained except empty numerical cells.
    for column in frame.columns:
        if frame[column].dtype == object and column not in {'site','BBCH','observation_id','group_id','variety','country'}:
            nonempty = frame[column].mask(frame[column].eq(''),np.nan)
            try:
                frame[column] = pd.to_numeric(nonempty)
            except (ValueError,TypeError):
                pass
    return frame


def select_observations(observations,pairs):
    """Exact site-season membership: temporal holdout sites may occur in training."""
    keys = pd.DataFrame(pairs,columns=['site','season'])
    if keys.duplicated().any():
        raise ValueError('Duplicate site-season selection')
    return observations.merge(keys,on=['site','season'],how='inner',validate='many_to_one')


def _pairs(frame):
    return [[str(site),int(year)] for site,year in frame[['site','season']].drop_duplicates().sort_values(
        ['site','season']).itertuples(index=False,name=None)]


def crossfit_jobs(protocol):
    if protocol.duplicated(['site','season']).any():
        raise ValueError('Duplicate protocol site-season')
    calibration = protocol.loc[protocol.partition.eq('calibration')]
    if set(calibration.inner_fold.astype(int)) != set(range(4)):
        raise ValueError('Require all four calibration folds')
    jobs = [dict(name='full',excluded_folds=[],train_pairs=_pairs(calibration),predict_pairs=_pairs(protocol))]
    for excluded in [*( (i,) for i in range(4)), *itertools.combinations(range(4),2)]:
        name = 'oof_'+str(excluded[0]) if len(excluded)==1 else 'nested_'+'_'.join(map(str,excluded))
        train = calibration.loc[~calibration.inner_fold.isin(excluded)]
        target = calibration.loc[calibration.inner_fold.isin(excluded)]
        jobs.append(dict(name=name,excluded_folds=list(excluded),train_pairs=_pairs(train),predict_pairs=_pairs(target)))
    return jobs


def _seal_task(directory):
    artifacts = {str(p.relative_to(directory)):digest(p) for p in directory.rglob('*')
                 if p.is_file() and p.name!='complete.json' and not any(x.startswith('.') for x in p.relative_to(directory).parts)}
    json_once(directory/'complete.json',dict(artifacts=artifacts))


def _check_task(directory):
    marker = read_json(directory/'complete.json')
    check_hashes({str(directory/name):value for name,value in marker['artifacts'].items()})


def completion_status(output,tasks):
    missing=[]
    for task in tasks:
        folder=Path(output)/task
        if not (folder/'complete.json').is_file():
            missing.append(task)
        else:
            _check_task(folder)
    missing_set=set(missing)
    return dict(complete=not missing,completed=len(tasks)-len(missing),expected=len(tasks),missing=missing,
        states={task:('complete' if task not in missing_set else
            'started_or_interrupted' if (Path(output)/task).exists() else 'pending') for task in tasks})


def _status(output,tasks):
    status=completion_status(output,tasks)
    temporary=output/'.status.tmp'
    temporary.write_text(json.dumps(status,indent=2)+'\n')
    os.replace(temporary,output/'status.json')
    return status


def expected_tasks(experiments,models,temperatures,ml,seeds):
    jobs=['full',*[f'oof_{i}' for i in range(4)],*[f'nested_{i}_{j}' for i,j in itertools.combinations(range(4),2)]]
    result=[]
    for experiment,model,temperature in itertools.product(experiments,models,temperatures):
        root=f'experiments/{experiment}/{model}/{temperature}'
        result.extend(f'{root}/pbm/{job}' for job in jobs)
        if 'tabm' in ml:
            for stage,seed in itertools.product(STAGES,seeds):
                result.extend(f'{root}/stages/{stage}/tune_{seed}_{fold}' for fold in range(4))
                result.append(f'{root}/stages/{stage}/final_{seed}')
        result.append(f'{root}/assembly')
    result.append('evaluation')
    return result


def settings_for(model,temperature,optimizer,maxiter=None):
    values={**optimizer,'temperature_column':TEMPERATURE_COLUMNS[temperature],'temperature_input':temperature}
    if maxiter is not None:
        values['maxiter']=maxiter
    values['seeds']=tuple(values['seeds'])
    return threshold_only_settings(model,**values)


def validate_fit(fitted,model,temperature,obs,weather,settings):
    observed=normalize_observations(obs)
    earliest=1 if get_model(model).interaction=='none' else None
    prepared=prepare_weather(weather,observed[['site','season']].drop_duplicates(),settings.temperature_column,earliest)
    if (fitted.model_name!=model or fitted.temperature_input!=temperature or
            fitted.calibration_hash!=frame_hash(observed) or fitted.weather_hash!=_weather_hash(prepared) or
            plain(fitted.settings)!=plain(asdict(settings)) or
            any(fitted.parameters[key]!=value for key,value in fixed_parameters(model).items())):
        raise ValueError('Cached PBM fit differs from model, temperature, training observations/weather, or fixed settings')


def generate_crossfit(job,cohort,model,temperature,optimizer,retry_maxiter,directory,replay=False):
    from model.fast_thresholds import fit, predict_with_starts
    directory=Path(directory)
    obs=select_observations(cohort['observations'],job['train_pairs'])
    weather=cohort['weather'].loc[cohort['weather'].site.isin(obs.site)]
    provenance=dict(**job,model=model,temperature_input=temperature,observation_ids=obs.observation_id.tolist(),
                    observation_hash=frame_hash(obs),temperature_column=TEMPERATURE_COLUMNS[temperature])
    if replay:
        if read_json(directory/'job.json')!=plain(provenance):
            raise ValueError('PBM task training provenance differs')
        _check_task(directory)
    else:
        json_once(directory/'job.json',provenance)
    initial=settings_for(model,temperature,optimizer)
    if (directory/'fit.json').exists():
        fitted=load_fit(directory/'fit.json')
        settings=settings_for(model,temperature,optimizer,maxiter=fitted.settings['maxiter'])
        if settings.maxiter not in (initial.maxiter,retry_maxiter):
            raise ValueError('Unrecognized optimizer budget in cached fit')
        validate_fit(fitted,model,temperature,obs,weather,settings)
    else:
        if replay:
            raise ValueError('Missing cached fit')
        log(f'{model}/{temperature}/{job["name"]}: fit {len(obs)} calibration observations')
        start=time.monotonic()
        fitted=None
        if (directory/'initial_fit.json').exists():
            fitted=load_fit(directory/'initial_fit.json')
            validate_fit(fitted,model,temperature,obs,weather,initial)
        elif not (directory/'initial_failure.json').exists():
            try:
                fitted=fit(model,obs,weather,initial)
            except ValueError as error:
                if retry_maxiter<=initial.maxiter or not str(error).startswith((
                        'No finite predictions for at least one calibration stage',
                        'No feasible finite calibration solution')):
                    raise
                json_once(directory/'initial_failure.json',dict(error=str(error),
                    settings=asdict(initial),test_labels_accessed=False))
            if fitted is not None:
                publish(directory/'initial_fit.json',lambda path:save_fit(fitted,path))
        retried=(fitted is None or not fitted.optimizer_converged) and retry_maxiter>initial.maxiter
        if retried:
            log(f'{model}/{temperature}/{job["name"]}: unconverged, retry {retry_maxiter} generations')
            fitted=fit(model,obs,weather,settings_for(model,temperature,optimizer,maxiter=retry_maxiter))
        publish(directory/'fit.json',lambda path:save_fit(fitted,path))
        json_once(directory/'optimization.json',dict(retried=retried,optimizer_converged=fitted.optimizer_converged,
            objective_value=fitted.objective_value,elapsed_seconds=time.monotonic()-start,
            selection='calibration objective only',test_labels_accessed=False))
    target=pd.DataFrame(job['predict_pairs'],columns=['site','season'])
    predicted=predict_with_starts(model,fitted.parameters,
        cohort['weather'].loc[cohort['weather'].site.isin(target.site)],target,
        temperature_column=TEMPERATURE_COLUMNS[temperature],temperature_input=temperature)
    predicted['pbm_fit_id']=str(directory.relative_to(directory.parents[5])) if len(directory.parents)>5 else str(directory)
    if replay:
        assert_table(predicted,read_table(directory/'predictions.csv'))
    else:
        table_once(directory/'predictions.csv',predicted)
        _seal_task(directory)
    return predicted


def residual_rows(features,observations):
    selected=select_observations(observations,_pairs(features))
    rows=selected.rename(columns={'Date':'observed_date'}).merge(features,on=KEYS,how='left',validate='many_to_one',indicator=True)
    if not rows._merge.eq('both').all():
        raise ValueError('Missing residual PBM prediction/status')
    rows=rows.drop(columns='_merge')
    rows['observed_date']=pd.to_datetime(rows.observed_date)
    rows['residual_days']=(rows.observed_date-pd.to_datetime(rows.predicted_date)).dt.days
    return rows


def learner_data(rows,stage):
    selected=rows.loc[rows.BBCH.eq(stage)&rows.residual_days.notna()]
    if len(selected)<2:
        raise ValueError(f'Insufficient attained BBCH{stage} residual training rows')
    return selected[FEATURES],selected.residual_days.to_numpy(float),selected.site.to_numpy()


def _ids(rows,stage):
    return rows.loc[rows.BBCH.eq(stage)&rows.residual_days.notna(),'observation_id'].tolist()


def train_stage(stage,nested,oof,protocol,directory,config,seeds,replay=False):
    from model.residual.learner import fit_learner,load_predictor
    for seed in seeds:
        selected_epochs=[]
        for fold in range(4):
            folder=directory/f'tune_{seed}_{fold}'
            validation=select_observations(oof,_pairs(protocol.loc[protocol.inner_fold.eq(fold)&protocol.partition.eq('calibration')]))
            training=nested[fold]
            provenance=dict(stage=stage,seed=seed,validation_fold=fold,
                train_observation_ids=_ids(training,stage),validation_observation_ids=_ids(validation,stage),
                train_features_hash=frame_hash(training),validation_features_hash=frame_hash(validation),config=asdict(config))
            if replay:
                _check_task(folder)
                if read_json(folder/'provenance.json')!=plain(provenance):
                    raise ValueError('Residual tuning provenance differs')
            else:
                json_once(folder/'provenance.json',provenance)
                if not (folder/'tuning.json').exists():
                    result=fit_learner(*learner_data(training,stage),seed=seed,config=config,
                        validation=learner_data(validation,stage))
                    publish(folder/'checkpoint.pt',result.predictor.save)
                    json_once(folder/'tuning.json',dict(best_epoch=result.best_epoch,history=result.history))
                _seal_task(folder)
            load_predictor(folder/'checkpoint.pt')
            selected_epochs.append(read_json(folder/'tuning.json')['best_epoch'])
        epochs=max(1,int(np.rint(np.median(selected_epochs))))
        folder=directory/f'final_{seed}'
        provenance=dict(stage=stage,seed=seed,epochs=epochs,selected_epochs=selected_epochs,
            train_observation_ids=_ids(oof,stage),train_features_hash=frame_hash(oof),config=asdict(config),
            epoch_rule='nearest-even rounded median of four inner-fold selected epochs')
        if replay:
            _check_task(folder)
            if read_json(folder/'provenance.json')!=plain(provenance):
                raise ValueError('Residual final-training provenance differs')
        else:
            json_once(folder/'provenance.json',provenance)
            if not (folder/'checkpoint.pt').exists() or not (folder/'history.json').exists():
                result=fit_learner(*learner_data(oof,stage),seed=seed,config=config,epochs=epochs)
                publish(folder/'checkpoint.pt',result.predictor.save)
                json_once(folder/'history.json',result.history)
            _seal_task(folder)
        load_predictor(folder/'checkpoint.pt')
    log(f'BBCH{stage}: four-fold tuning and final residual checkpoints verified')


def make_predictions(features,stage_root,seeds,ml):
    from model.residual.learner import load_predictor
    valid=features.predicted_date.notna()
    seed_values={seed:np.full(len(features),np.nan) for seed in seeds}
    if 'tabm' in ml:
        for stage in STAGES:
            mask=features.BBCH.eq(stage)&valid
            if mask.any():
                for seed in seeds:
                    seed_values[seed][mask]=load_predictor(stage_root/stage/f'final_{seed}'/'checkpoint.pt').predict(features.loc[mask,FEATURES])
    results=[]
    for algorithm in ml:
        residuals=np.where(valid,0.,np.nan) if algorithm=='none' else np.mean(list(seed_values.values()),axis=0)
        result=correct_dates(features.drop(columns=FEATURES+['feature_end_date']),residuals)
        result['ml_algorithm']=algorithm
        if algorithm=='tabm':
            result['model_name']=result.model_name+'-ML'
            for seed in seeds:
                result[f'residual_seed_{seed}']=seed_values[seed]
        results.append(result)
    return pd.concat(results,ignore_index=True)


def comparison_table(observations,sites,predictions,protocol,experiment,partition_override=None):
    frames=[]
    for _,part in predictions.groupby('ml_algorithm',sort=False):
        selected=select_observations(observations,_pairs(part))
        joined=selected.rename(columns={'Date':'observed_date'}).merge(part,on=KEYS,how='left',validate='many_to_one')
        protocol_columns=['site','season','partition','inner_fold']
        if 'temperature_zone_id' in protocol:
            protocol_columns.append('temperature_zone_id')
            joined=joined.drop(columns='temperature_zone_id',errors='ignore')
        joined=joined.merge(protocol[protocol_columns],on=['site','season'],validate='many_to_one')
        # Prepared observations carry canonical groups; spatial scenarios supply
        # their coarser groups through sites. Keep exactly one evaluation group.
        joined=joined.drop(columns='group_id',errors='ignore').merge(
            sites[['site','group_id']],on='site',validate='many_to_one')
        joined['experiment']=experiment
        if partition_override:
            joined['partition']=partition_override
        joined['evaluation_role']=joined.partition.map({'calibration':'apparent_training','test':'locked_holdout','oof':'calibration_crossfit'})
        joined.loc[joined.partition.eq('oof')&joined.ml_algorithm.eq('tabm'),
            'evaluation_role']='calibration_tuning_validation'
        joined['delta_days']=(pd.to_datetime(joined.predicted_date)-pd.to_datetime(joined.observed_date)).dt.days
        frames.append(joined)
    return pd.concat(frames,ignore_index=True)


def assert_table(expected,actual):
    if not len(expected.columns) and not len(actual.columns) and expected.empty and actual.empty:
        return
    if set(expected.columns)!=set(actual.columns):
        raise ValueError('Replayed table columns differ')
    # CSV float round-trip and empty strings are normalized without relaxing numeric accuracy.
    from io import StringIO
    left=pd.read_csv(StringIO(expected.to_csv(index=False,date_format='%Y-%m-%d')),dtype={'BBCH':str,'site':str,'observation_id':str,'group_id':str})
    right=pd.read_csv(StringIO(actual[expected.columns].to_csv(index=False,date_format='%Y-%m-%d')),dtype={'BBCH':str,'site':str,'observation_id':str,'group_id':str})
    pd.testing.assert_frame_equal(left,right,check_dtype=False,rtol=1e-7,atol=1e-7)


def _scenario_sites(cohort,experiment,metadata):
    sites=cohort['sites'].copy()
    if experiment.startswith('spatial_'):
        mapping=pd.DataFrame(metadata['spatial_groups']).set_index('site').group_id
        sites['group_id']=sites.site.map(mapping)
    return sites


def _oof_predictions(features,stage_root,seeds,ml,protocol):
    from model.residual.learner import load_predictor
    frames=[]
    for fold in range(4):
        subset=select_observations(features,_pairs(protocol.loc[protocol.inner_fold.eq(fold)&protocol.partition.eq('calibration')]))
        valid=subset.predicted_date.notna()
        for algorithm in ml:
            values={seed:np.full(len(subset),np.nan) for seed in seeds}
            if algorithm=='tabm':
                for stage in STAGES:
                    mask=subset.BBCH.eq(stage)&valid
                    for seed in seeds:
                        if mask.any():
                            values[seed][mask]=load_predictor(stage_root/stage/f'tune_{seed}_{fold}'/'checkpoint.pt').predict(subset.loc[mask,FEATURES])
                residual=np.mean(list(values.values()),axis=0)
            else:
                residual=np.where(valid,0.,np.nan)
            corrected=correct_dates(subset.drop(columns=FEATURES+['feature_end_date']),residual)
            corrected['ml_algorithm']=algorithm
            if algorithm=='tabm':
                corrected['model_name']=corrected.model_name+'-ML'
                for seed in seeds:
                    corrected[f'residual_seed_{seed}']=values[seed]
            frames.append(corrected)
    return pd.concat(frames,ignore_index=True)


def bounded_workers(weather,requested):
    if requested not in (1,2):
        raise ValueError('At most two PBM workers are allowed')
    try:
        import psutil
        available=psutil.virtual_memory().available
    except ImportError:
        # Unknown memory availability is a reason for serial execution.
        return 1
    estimate=max(512*1024**2,int(weather.memory_usage(deep=True).sum())*5)
    return max(1,min(requested,int(available*.6//estimate)))


def run_unit(cohort,protocol,metadata,experiment,model,temperature,run,output,replay=False):
    from model.residual.learner import TabMConfig
    folder=output/'experiments'/experiment/model/temperature
    jobs=crossfit_jobs(protocol)
    def execute(job):
        return job['name'],generate_crossfit(job,cohort,model,temperature,run['optimizer'],
            run['retry_maxiter'],folder/'pbm'/job['name'],replay=replay)
    workers=1 if replay else bounded_workers(cohort['weather'],run['workers'])
    log(f'{experiment}/{model}/{temperature}: {len(jobs)} joint PBM fits, workers={workers}')
    if workers==1:
        predictions=dict(execute(job) for job in jobs)
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            predictions=dict(pool.map(execute,jobs))
    terrain=cohort['sites']
    oof_features=build_features(pd.concat([predictions[f'oof_{fold}'] for fold in range(4)],ignore_index=True),
        cohort['weather'],terrain,temperature)
    oof=residual_rows(oof_features,cohort['observations'])
    nested={}
    if 'tabm' in run['ml']:
        for heldfold in range(4):
            pieces=[]
            for predictedfold in range(4):
                if predictedfold==heldfold:
                    continue
                pair='_'.join(map(str,sorted((heldfold,predictedfold))))
                target=_pairs(protocol.loc[protocol.inner_fold.eq(predictedfold)&protocol.partition.eq('calibration')])
                pieces.append(select_observations(predictions[f'nested_{pair}'],target))
            nested_features=build_features(pd.concat(pieces,ignore_index=True),cohort['weather'],terrain,temperature)
            nested[heldfold]=residual_rows(nested_features,cohort['observations'])
        for stage in STAGES:
            train_stage(stage,nested,oof,protocol,folder/'stages'/stage,TabMConfig(**run['config']),run['seeds'],replay=replay)
    features=build_features(predictions['full'],cohort['weather'],terrain,temperature)
    predicted=make_predictions(features,folder/'stages',run['seeds'],run['ml'])
    sites=_scenario_sites(cohort,experiment,metadata)
    comparison=comparison_table(cohort['observations'],sites,predicted,protocol,experiment)
    oof_predicted=_oof_predictions(oof_features,folder/'stages',run['seeds'],run['ml'],protocol)
    comparison=pd.concat([comparison,comparison_table(cohort['observations'],sites,oof_predicted,
        protocol,experiment,partition_override='oof')],ignore_index=True)
    provenance=dict(oof_observation_ids=oof.observation_id.tolist(),
        nested_observation_ids={str(fold):rows.observation_id.tolist() for fold,rows in nested.items()},
        feature_columns=FEATURES,temperature_input=temperature,
        training_metrics='apparent calibration; OOF reported separately',
        residual_definition='observed calendar date minus fold-specific PBM predicted calendar date',
        nonattainment='no residual prediction for an unattained PBM stage')
    assembly=folder/'assembly'
    if replay:
        _check_task(assembly)
        for name,frame in [('features',features),('oof',oof),('predictions',predicted),('comparison',comparison)]:
            assert_table(frame,read_table(assembly/f'{name}.csv'))
        if read_json(assembly/'provenance.json')!=plain(provenance):
            raise ValueError('Assembly residual provenance differs')
    else:
        for name,frame in [('features',features),('oof',oof),('predictions',predicted),('comparison',comparison)]:
            table_once(assembly/f'{name}.csv',frame)
        json_once(assembly/'provenance.json',provenance)
        _seal_task(assembly)
    return comparison


def _evaluation_tables(output,run,cohort,terrain_cuts):
    from .evaluation import evaluate_comparison
    parts={}
    for experiment,model in itertools.product(run['experiments'],run['models']):
        comparison=pd.concat([read_table(output/'experiments'/experiment/model/temp/'assembly/comparison.csv')
                              for temp in run['temperatures']],ignore_index=True)
        tables=evaluate_comparison(comparison,cohort['sites'],n_bootstrap=run['n_bootstrap'],
            seed=20260909,terrain_cuts=terrain_cuts)
        for key,table in tables.items():
            parts.setdefault(key,[]).append(table)
    return {key:pd.concat(tables,ignore_index=True) for key,tables in parts.items()}


def _comparison_export(output,run,destination):
    import shutil
    def writer(temporary):
        with temporary.open('wb') as stream:
            first=True
            for experiment,model,temperature in itertools.product(run['experiments'],run['models'],run['temperatures']):
                with (output/'experiments'/experiment/model/temperature/'assembly/comparison.csv').open('rb') as source:
                    if not first:
                        source.readline()
                    shutil.copyfileobj(source,stream)
                    first=False
    publish(destination,writer)


def plot_summary(metrics,directory):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    value='site_balanced_mae' if 'site_balanced_mae' in metrics else 'site_mae'
    if value not in metrics:
        candidates=[c for c in metrics if 'mae' in c.lower() and 'site' in c.lower()]
        if not candidates:
            raise ValueError('Evaluation did not return an equal-site MAE field')
        value=candidates[0]
    for experiment,part in metrics.loc[metrics.partition.eq('test')].groupby('experiment',sort=True):
        fig,axes=plt.subplots(2,2,figsize=(12,8),constrained_layout=True)
        models=list(dict.fromkeys(part.model_name.str.replace('-ML','',regex=False)))
        for ax,stage in zip(axes.flat,STAGES):
            selected=part.loc[part.BBCH.astype(str).str.zfill(2).eq(stage)].copy()
            selected['structure']=selected.model_name.str.replace('-ML','',regex=False)
            for (temperature,ml),rows in selected.groupby(['temperature_input','ml_algorithm']):
                values=rows.set_index('structure')[value].reindex(models)
                ax.plot(range(len(models)),values,marker='o',markersize=4,label=f'{temperature} / {"PBM" if ml=="none" else "TabM"}')
            ax.set_xticks(range(len(models)),models,rotation=55,ha='right')
            ax.set_title(f'BBCH{stage}')
            ax.set_ylabel('Equal-site MAE (days)')
            ax.grid(axis='y',alpha=.2)
        axes[0,0].legend(fontsize=8)
        fig.suptitle(f'{experiment}: locked test predictions')
        for suffix in ('pdf','png'):
            path=directory/f'{experiment}_test_mae.{suffix}'
            if not path.exists():
                publish(path,lambda temp:fig.savefig(temp,dpi=220,metadata={'Creator':'grape factorial experiment'}))
        plt.close(fig)


def check_inputs(run):
    check_hashes(run['input_hashes'])
    check_hashes(run['source_hashes'])
    if versions()!=run['versions']:
        raise ValueError('Dependency versions differ from frozen experiment')


def _context(run):
    from .cohort import load_cohort
    from .validation import make_protocols
    cohort=load_cohort(run['cohort'])
    climate=Path(run['climate']) if run['climate'] else None
    protocols=make_protocols(cohort,climate=climate,monthly_normals=run.get('monthly_normals'),
        normal_metadata=run.get('normal_metadata'))
    zone_rows=protocols.attrs.get('metadata',{}).get('site_temperature_zones')
    if zone_rows is not None:
        zone_lookup=pd.DataFrame(zone_rows).set_index('site').temperature_zone_id
        cohort['sites']['temperature_zone_id']=cohort['sites'].site.map(zone_lookup)
    selected=protocols.loc[protocols.experiment.isin(run['experiments'])].copy()
    if set(selected.experiment)!=set(run['experiments']):
        raise ValueError('Requested holdout protocol is unavailable')
    primary=protocols.loc[protocols.experiment.eq('site_holdout')&protocols.partition.eq('calibration'),'site']
    std=pd.to_numeric(cohort['sites'].loc[cohort['sites'].site.isin(primary),'dem_local_std_m'],errors='coerce')
    finite=std.loc[np.isfinite(std)]
    cuts=finite.quantile([1/3,2/3]).to_list() if len(finite) else []
    if len(cuts)!=2:
        raise ValueError('Cannot freeze terrain relief tertiles without finite primary calibration terrain')
    return cohort,selected,protocols.attrs.get('metadata',{}),cuts


def verify_run(output,*,replay=True):
    output=Path(output).resolve()
    run=read_json(output/'run.json')
    check_inputs(run)
    status=completion_status(output,run['tasks'])
    if not status['complete']:
        raise ValueError(f'Incomplete factorial run: {len(status["missing"])} missing tasks')
    cohort,protocols,metadata,cuts=_context(run)
    assert_table(protocols,read_table(output/'protocols.csv'))
    if read_json(output/'protocol_metadata.json')!=plain(metadata) or read_json(output/'terrain_cuts.json')!=cuts:
        raise ValueError('Frozen split metadata or terrain cuts differ')
    if replay:
        combined_hash=hashlib.sha256()
        first=True
        for experiment,model,temperature in itertools.product(run['experiments'],run['models'],run['temperatures']):
            with (output/'experiments'/experiment/model/temperature/'assembly/comparison.csv').open('rb') as stream:
                if not first:
                    stream.readline()
                for chunk in iter(lambda:stream.read(1024*1024),b''):
                    combined_hash.update(chunk)
            first=False
        if combined_hash.hexdigest()!=digest(output/'evaluation/comparison.csv'):
            raise ValueError('Global comparison does not equal the exact ordered task-table union')
        for experiment,model,temperature in itertools.product(run['experiments'],run['models'],run['temperatures']):
            run_unit(cohort,protocols.loc[protocols.experiment.eq(experiment)],metadata,
                experiment,model,temperature,run,output,replay=True)
        tables=_evaluation_tables(output,run,cohort,cuts)
        for name,frame in tables.items():
            assert_table(frame,read_table(output/'evaluation'/f'{name}.csv'))
    if (output/'completion.json').exists():
        completion=read_json(output/'completion.json')
        check_hashes({str(output/name):value for name,value in completion['artifacts'].items()})
    return dict(verified=True,replayed=bool(replay),tasks=status['expected'],experiments=run['experiments'],
        configurations_per_stage=len(run['models'])*len(run['temperatures'])*len(run['ml']),
        smoke=run['smoke'],observations=len(cohort['observations']),sites=len(cohort['sites']))


def run_experiment(cohort_path,output,*,climate=None,monthly_normals=None,normal_metadata=None,
                   models=MODEL_NAMES,temperatures=('RAW','DEM'),
                   ml=('none','tabm'),experiments=None,optimizer=None,retry_maxiter=1000,
                   config=None,seeds=DEFAULT_SEEDS,workers=2,n_bootstrap=2000,make_plot=True,
                   resume=False,smoke=False):
    from model.residual.learner import TabMConfig
    cohort_path,output=Path(cohort_path).resolve(),Path(output).resolve()
    if output.exists() and not resume:
        raise FileExistsError('Choose a new output directory or resume this exact experiment')
    if resume and not output.exists():
        raise FileNotFoundError('Cannot resume missing experiment')
    if resume:
        stored=read_json(output/'run.json')
        if climate is None:
            climate=stored.get('climate')
        if monthly_normals is None:
            monthly_normals=stored.get('monthly_normals')
            if normal_metadata is None:
                normal_metadata=stored.get('normal_metadata')
    if monthly_normals is not None:
        monthly_normals=Path(monthly_normals).resolve()
        normal_metadata=Path(normal_metadata).resolve() if normal_metadata is not None else monthly_normals.with_name('request.json')
    models,temperatures,ml=tuple(models),tuple(temperatures),tuple(ml)
    if not models or len(set(models))!=len(models) or not set(models).issubset(MODEL_NAMES):
        raise ValueError('Invalid or repeated process model')
    if not temperatures or len(set(temperatures))!=len(temperatures) or not set(temperatures).issubset(TEMPERATURE_COLUMNS):
        raise ValueError('Invalid or repeated temperature input')
    if not ml or len(set(ml))!=len(ml) or not set(ml).issubset({'none','tabm'}):
        raise ValueError('Invalid ML selection')
    if workers not in (1,2) or n_bootstrap<1:
        raise ValueError('Require one/two workers and positive bootstrap count')
    if not seeds or len(set(seeds))!=len(seeds):
        raise ValueError('Require distinct neural seeds')
    optimizer=optimizer or dict(seeds=DEFAULT_SEEDS,maxiter=300,popsize=15,tol=.001)
    if retry_maxiter<int(optimizer['maxiter']):
        raise ValueError('Retry budget is below initial budget')
    config=config or TabMConfig()
    if not smoke and (plain(optimizer)!=plain(dict(seeds=DEFAULT_SEEDS,maxiter=300,popsize=15,tol=.001)) or
            tuple(seeds)!=DEFAULT_SEEDS or retry_maxiter!=1000 or config!=TabMConfig()):
        raise ValueError('Reduced or altered optimizer/neural budgets require explicit smoke=True')
    from .cohort import load_cohort
    from .validation import make_protocols
    cohort=load_cohort(cohort_path)
    protocols=make_protocols(cohort,climate=climate,monthly_normals=monthly_normals,normal_metadata=normal_metadata)
    experiments=tuple(experiments) if experiments is not None else tuple(protocols.experiment.unique())
    if not experiments or len(set(experiments))!=len(experiments) or not set(experiments).issubset(set(protocols.experiment)):
        raise ValueError('Requested holdout protocol is unavailable or repeated')
    output.mkdir(parents=True,exist_ok=True)
    with run_lock(output):
        inputs=[path for path in cohort_path.iterdir() if path.is_file() and not path.name.startswith('.')]
        if climate is not None:
            inputs.append(Path(climate).resolve())
        normal_inputs=protocols.attrs.get('metadata',{}).get('normal_input_hashes',{})
        run=dict(schema_version=2,cohort=str(cohort_path),climate=str(Path(climate).resolve()) if climate else None,
            monthly_normals=str(monthly_normals) if monthly_normals is not None else None,
            normal_metadata=str(normal_metadata) if normal_metadata is not None else None,
            publication_primary_design=monthly_normals is not None,
            models=models,temperatures=temperatures,ml=ml,experiments=experiments,optimizer=optimizer,
            retry_maxiter=retry_maxiter,config=asdict(config),seeds=list(seeds),workers=workers,n_bootstrap=n_bootstrap,
            make_plot=make_plot,smoke=smoke,response_profile=PROFILE,versions=versions(),source_hashes=sources(),
            input_hashes={**{str(path):digest(path) for path in inputs},**normal_inputs},
            tasks=expected_tasks(experiments,models,temperatures,ml,seeds),
            warm_protocols_available=climate is not None,
            feature_contract=dict(columns=FEATURES,windows=[7,30,90],end='inclusive PBM predicted date',
                start='actual model phase_start_date',std_ddof=0,
                excludes=['observation date','site ID','country','year','cultivar']))
        # Include original cohort input hashes: regenerated weather invalidates a resume.
        run['input_hashes'].update(cohort['metadata'].get('input_hashes',{}))
        json_once(output/'run.json',run)
        run=read_json(output/'run.json')
        check_inputs(run)
        if (output/'completion.json').exists():
            return verify_run(output)
        cohort,protocols,metadata,cuts=_context(run)
        table_once(output/'protocols.csv',protocols)
        json_once(output/'protocol_metadata.json',metadata)
        json_once(output/'terrain_cuts.json',cuts)
        _status(output,run['tasks'])
        for experiment,model,temperature in itertools.product(experiments,models,temperatures):
            run_unit(cohort,protocols.loc[protocols.experiment.eq(experiment)],metadata,
                experiment,model,temperature,run,output)
            _status(output,run['tasks'])
        check_inputs(run)
        tables=_evaluation_tables(output,run,cohort,cuts)
        for name,frame in tables.items():
            table_once(output/'evaluation'/f'{name}.csv',frame)
        _comparison_export(output,run,output/'evaluation/comparison.csv')
        if make_plot:
            plot_summary(tables['metrics'],output/'evaluation')
        _seal_task(output/'evaluation')
        _status(output,run['tasks'])
        verified=verify_run(output)
        artifacts={str(path.relative_to(output)):digest(path) for path in output.rglob('*') if path.is_file()
            and not any(part.startswith('.') for part in path.relative_to(output).parts)
            and path.name not in ('status.json','completion.json','verification.json')}
        json_once(output/'completion.json',dict(complete=True,artifacts=artifacts,verification=verified))
        json_once(output/'verification.json',verified)
        log('All requested factorial tasks completed and replay-verified')
        return verified
