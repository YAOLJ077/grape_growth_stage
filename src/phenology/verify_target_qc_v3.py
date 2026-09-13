"""Independently audit candidate membership, stage support and provenance."""
import csv,gzip,hashlib,json,argparse
from collections import defaultdict,Counter
from datetime import date
from itertools import combinations
from pathlib import Path
FIELDS=['site','variety','country','lat','lon','Date','BBCH']
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def eid(r):return hashlib.sha256(json.dumps([r[c] for c in FIELDS],ensure_ascii=False,separators=(',',':')).encode()).hexdigest()
def verify(folder):
    folder=Path(folder);summary=json.loads((folder/'summary.json').read_text())
    for name,digest in summary['output_hashes'].items():assert sha(folder/name)==digest
    for path,digest in {**summary['input_hashes'],**summary['source_hashes']}.items():assert sha(path)==digest
    with (folder/'observations.csv').open() as f:
        reader=csv.DictReader(f);assert reader.fieldnames==FIELDS;rows=list(reader)
    retained={eid(r):r for r in rows};assert len(retained)==len(rows)==summary['n_retained']
    with gzip.open(folder/'quarantine.jsonl.gz','rt') as f:excluded={r['event_id']:r for r in map(json.loads,f)}
    assert not retained.keys()&excluded.keys();assert len(retained)+len(excluded)==summary['n_pre_qc_targets']
    for k,r in excluded.items():assert eid(r['record'])==k and r['evidence']
    with gzip.open(folder/'provenance.jsonl.gz','rt') as f:provenance={r['event_id']:r for r in map(json.loads,f)}
    assert provenance.keys()==retained.keys()|excluded.keys()
    for k,r in provenance.items():assert r['occurrences'] and (r['status']=='retained')==(k in retained)
    groups=defaultdict(lambda:defaultdict(set));checked=0
    for r in rows:
        d=date.fromisoformat(r['Date']);lo,hi=summary['calendar_windows'][r['BBCH']]
        assert d.year>=1951 and lo<=d.strftime('%m-%d')<=hi
        assert -90<=float(r['lat'])<=90 and -180<=float(r['lon'])<=180
        groups[(r['site'],r['variety'],d.year)][r['BBCH']].add(d)
        assert provenance[eid(r)]['source_quality'] not in {'incorrect','doubtful'}
    repeated=[]
    for (site,variety,year),stages in groups.items():
        for a,b in combinations(sorted(stages),2):
            lo,hi=summary['all_intervals'][a+'-'+b]
            for x in stages[a]:assert any(lo<=(y-x).days<=hi for y in stages[b]);checked+=1
            for y in stages[b]:assert any(lo<=(y-x).days<=hi for x in stages[a]);checked+=1
        for stage,ds in stages.items():
            if len(ds)>1:repeated.append(dict(site=site,variety=variety,year=year,BBCH=stage,n_dates=len(ds),span_days=(max(ds)-min(ds)).days,dates=';'.join(str(d) for d in sorted(ds)),status='retained_ambiguous_repeated_dates'))
    counts=Counter()
    for item in excluded.values():
        r=item['record'];source=r['site'].split(':')[1]
        for rule in {e['rule'] for e in item['evidence']}:
            for dimension,value in [('country',r['country']),('source',source),('BBCH',r['BBCH']),('year',r['Date'][:4])]:counts[(dimension,value,rule)]+=1
    with (folder/'exclusions_by_dimension_rule.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['dimension','value','rule','n_observations']);w.writerows([*k,n] for k,n in sorted(counts.items()))
    with (folder/'retained_repeated_dates.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['site','variety','year','BBCH','n_dates','span_days','dates','status']);w.writeheader();w.writerows(repeated)
    result=dict(retained=len(rows),quarantined=len(excluded),source_occurrences=sum(len(r['occurrences']) for r in provenance.values()),independent_pair_support_checks=checked,retained_repeated_date_groups=len(repeated),retained_repeated_groups_span_over_30_days=sum(r['span_days']>30 for r in repeated),partition_reconstruction=True,input_output_source_hashes_verified=True,script_sha256=sha(__file__))
    (folder/'verification.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('folder');verify(p.parse_args().folder)
