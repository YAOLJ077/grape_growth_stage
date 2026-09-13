"""Build a separate four-target candidate from verified original source tables."""
import argparse,csv,gzip,json
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
from organize_phenology import (ROOT,COLUMNS,INPUTS,resolve_input,transform,event_id,sha256)
from target_qc_v3 import VERSION,STAGES,WINDOWS,ADJACENT,INTERVALS,screen,source_quality,reconcile_dwd


def build(output):
    output=Path(output)
    if output.exists():raise FileExistsError('Use a new versioned candidate directory')
    records=set();metadata=defaultdict(list);sources={};counts=Counter()
    for kind,relative,delimiter in INPUTS:
        path=resolve_input(relative);sources[str(path.resolve())]=sha256(path)
        with path.open(encoding='utf-8-sig',newline='') as f:
            for number,raw in enumerate(csv.DictReader(f,delimiter=delimiter),1):
                counts['source_occurrences']+=1
                result=transform(raw,kind)
                if result is None:continue
                row,mapping,source_stage=result
                if mapping!='direct' or row[6] not in STAGES or not row[5] or row[5]<'1951-01-01':continue
                records.add(row);item=dict(source=relative,source_record_number=number,source_stage=source_stage,kind=kind)
                if kind=='germany':
                    item.update(reporter_type=raw['reporter_type'],quality_level=raw['quality_level'],date_quality_flag=raw['date_quality_flag'],object_id=raw['taxon_id'],phase_id=raw['stage_id'])
                metadata[row].append(item);counts['target_source_occurrences']+=1
        print('Read verified source:',relative,flush=True)
    # Verify original-source reconstruction against both retained and quarantined inventory.
    inventory=ROOT/'phenology_data.csv';quarantine=ROOT/'phenology_data_quarantine.jsonl.gz'
    sources[str(inventory.resolve())]=sha256(inventory);sources[str(quarantine.resolve())]=sha256(quarantine)
    with inventory.open() as f:old={tuple(r[c] for c in COLUMNS) for r in csv.DictReader(f) if r['BBCH'] in STAGES}
    with gzip.open(quarantine,'rt') as f:
        quarantined={tuple(x['record'][c] for c in COLUMNS) for x in map(json.loads,f) if x['record']['BBCH'] in STAGES}
    assert records==old|quarantined,'Original-source target reconstruction differs from recorded inventory'
    ordered=sorted(records,key=lambda r:(r[2],r[0],r[5],r[6],r[1],r[3],r[4]))
    rejected={};quality={}
    for row in ordered:
        dwd=[x for x in metadata[row] if x['kind']=='germany'];quality[row]=source_quality(dwd)
        if quality[row] in {'incorrect','doubtful'}:
            rejected[row]=[dict(rule='provider_'+quality[row],quality_level=max(int(x['quality_level'] or 0) for x in dwd),date_quality_flags=sorted({x['date_quality_flag'] for x in dwd}))]
    candidates=[r for r in ordered if r not in rejected]
    candidates,superseded=reconcile_dwd(candidates,{r:[x for x in metadata[r] if x['kind']=='germany'] for r in candidates});rejected.update(superseded)
    kept,screened=screen(candidates);rejected.update(screened)
    assert set(kept)|set(rejected)==records and not set(kept)&set(rejected)
    assert screen(kept)[0]==kept
    output.mkdir(parents=True)
    with (output/'observations.csv').open('w',newline='') as f:
        writer=csv.writer(f);writer.writerow(COLUMNS);writer.writerows(kept)
    with gzip.open(output/'quarantine.jsonl.gz','wt',encoding='utf-8') as f:
        for row in ordered:
            if row in rejected:f.write(json.dumps(dict(event_id=event_id(row),record=dict(zip(COLUMNS,row)),evidence=rejected[row],policy=VERSION),ensure_ascii=False)+'\n')
    with gzip.open(output/'provenance.jsonl.gz','wt',encoding='utf-8') as f:
        for row in ordered:
            f.write(json.dumps(dict(event_id=event_id(row),status='quarantined' if row in rejected else 'retained',source_quality=quality[row],identity='unspecified_variety_pool' if not row[1] else 'reported_variety_label',occurrences=metadata[row]),ensure_ascii=False)+'\n')
    with (output/'membership_changes.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['event_id',*COLUMNS,'previous_inventory_status','candidate_status','rule_ids'])
        for row in ordered:
            before='retained' if row in old else 'quarantined';after='quarantined' if row in rejected else 'retained'
            if before!=after:w.writerow([event_id(row),*row,before,after,';'.join(sorted({x['rule'] for x in rejected.get(row,[])}))])
    rules=Counter(x['rule'] for r,es in rejected.items() for x in {e['rule']:e for e in es}.values())
    summary=dict(policy=VERSION,created_utc=datetime.now(timezone.utc).isoformat(),scope='four direct target stages; all original eligible countries; no weather filter or refitting',
        source_counts=dict(counts),n_pre_qc_targets=len(records),n_retained=len(kept),n_quarantined=len(rejected),n_previous_retained=len(old),
        n_removed_from_previous=len(old-set(kept)),n_restored_from_previous=len(set(kept)-old),
        stage_counts=dict(Counter(r[6] for r in kept)),country_counts=dict(Counter(r[2] for r in kept)),rules=dict(rules),
        calendar_windows=WINDOWS,adjacent_intervals={f'{a}-{b}':v for (a,b),v in ADJACENT.items()},all_intervals={f'{a}-{b}':v for (a,b),v in INTERVALS.items()},
        input_hashes=sources,source_hashes={str(Path(__file__).resolve()):sha256(Path(__file__)),str(Path(__file__).with_name('target_qc_v3.py').resolve()):sha256(Path(__file__).with_name('target_qc_v3.py')),str(Path(__file__).with_name('organize_phenology.py').resolve()):sha256(Path(__file__).with_name('organize_phenology.py'))},
        production_inputs_modified=False,publication_ready=False,
        limits=['Candidate cohort: date/interval choices are project screening bounds, not physiological limits.','Four-target chronology differs from the previous whole-inventory branch screen.','Source precedence is a declared policy, not proof that every immediate report was a revision.','Unspecified variety and maturity labels do not establish plant identity.','No model residuals, predictions, parameters or test scores were used in cleaning.'],
        output_hashes={p.name:sha256(p) for p in output.iterdir() if p.is_file()})
    assert all(sha256(Path(p))==h for p,h in sources.items())
    (output/'summary.json').write_text(json.dumps(summary,indent=2)+'\n')
    print(json.dumps({k:summary[k] for k in ['n_pre_qc_targets','n_retained','n_quarantined','n_removed_from_previous','n_restored_from_previous','rules']}))

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);build(parser.parse_args().output)
