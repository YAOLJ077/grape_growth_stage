"""Prepare, run, resume or replay-verify the complete grape phenology factorial."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0,str(ROOT))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=('prepare','run','resume','verify'))
    parser.add_argument('--observations',type=Path)
    parser.add_argument('--weather-dir',type=Path)
    parser.add_argument('--terrain',type=Path)
    parser.add_argument('--climate',type=Path)
    parser.add_argument('--monthly-normals',type=Path,help='Verified common 1991–2020 RAW monthly normals for publication temperature zones')
    parser.add_argument('--normal-metadata',type=Path,help='Normals provenance JSON; defaults to sibling request.json')
    parser.add_argument('--cohort',type=Path)
    parser.add_argument('--output',type=Path)
    parser.add_argument('--models',nargs='+')
    parser.add_argument('--experiments',nargs='+')
    parser.add_argument('--temperatures',nargs='+',choices=('RAW','DEM'),default=['RAW','DEM'])
    parser.add_argument('--ml',nargs='+',choices=('none','tabm'),default=['none','tabm'])
    parser.add_argument('--workers',type=int,choices=(1,2),default=2)
    parser.add_argument('--smoke',action='store_true',help='Persist explicit tiny test budgets; never publication results')
    parser.add_argument('--no-plots',action='store_true')
    args=parser.parse_args(argv)
    if args.command=='prepare':
        for name in ('observations','weather_dir','terrain','cohort'):
            if getattr(args,name) is None:
                parser.error(f'prepare requires --{name.replace("_","-")}')
        from model_run.factorial.cohort import prepare_cohort,save_cohort
        cohort=prepare_cohort(args.observations,args.weather_dir,args.terrain)
        save_cohort(cohort,args.cohort)
        print(json.dumps(cohort['metadata'],indent=2))
        return
    if args.output is None:
        parser.error('run/resume/verify requires --output')
    from model_run.factorial.runner import run_experiment,verify_run,read_json
    if args.command=='verify':
        print(json.dumps(verify_run(args.output),indent=2))
        return
    if args.command=='resume':
        from model.residual.learner import TabMConfig
        stored=read_json(args.output/'run.json')
        result=run_experiment(stored['cohort'],args.output,climate=stored['climate'],
            monthly_normals=stored.get('monthly_normals'),normal_metadata=stored.get('normal_metadata'),models=stored['models'],
            temperatures=stored['temperatures'],ml=stored['ml'],experiments=stored['experiments'],
            optimizer=stored['optimizer'],retry_maxiter=stored['retry_maxiter'],config=TabMConfig(**stored['config']),
            seeds=stored['seeds'],workers=stored['workers'],n_bootstrap=stored['n_bootstrap'],
            make_plot=stored['make_plot'],smoke=stored['smoke'],resume=True)
    else:
        if args.cohort is None:
            parser.error('run requires --cohort')
        from model.registry import MODEL_NAMES
        extra={}
        if args.smoke:
            from model.residual.learner import TabMConfig
            extra=dict(optimizer=dict(seeds=(7,),maxiter=15,popsize=5,tol=.001),retry_maxiter=15,seeds=(7,),
                n_bootstrap=20,config=TabMConfig(n_blocks=1,d_block=8,k=2,n_bins=3,d_embedding=2,
                    max_epochs=2,patience=1,batch_size=32,threads=1))
        result=run_experiment(args.cohort,args.output,climate=args.climate,
            monthly_normals=args.monthly_normals,normal_metadata=args.normal_metadata,models=args.models or MODEL_NAMES,
            experiments=args.experiments,temperatures=args.temperatures,ml=args.ml,workers=args.workers,
            smoke=args.smoke,make_plot=not args.no_plots,**extra)
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()
