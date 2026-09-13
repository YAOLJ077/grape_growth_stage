"""Versioned candidate QC for four direct BBCH targets; no model inputs or residuals.

Bounds define a transparent review cohort, not universal physiological limits.
"""
from collections import defaultdict
from datetime import date

VERSION='four_target_qc_v3_20260912'
STAGES=('07','65','81','89')
WINDOWS={'07':('02-01','06-15'),'65':('04-01','07-31'),
         '81':('06-01','10-15'),'89':('07-15','11-15')}
ADJACENT={('07','65'):(20,120),('65','81'):(30,120),('81','89'):(10,90)}
INTERVALS={}
for i,a in enumerate(STAGES):
    for j in range(i+1,len(STAGES)):
        edges=[ADJACENT[(STAGES[k],STAGES[k+1])] for k in range(i,j)]
        INTERVALS[(a,STAGES[j])]=(sum(x[0] for x in edges),sum(x[1] for x in edges))


def source_quality(occurrences):
    """DWD quality applies at the highest available documented control level."""
    if not occurrences:return 'not_available'
    level=max(int(x.get('quality_level') or 0) for x in occurrences)
    best=[x for x in occurrences if int(x.get('quality_level') or 0)==level]
    flags={x.get('date_quality_flag','') for x in best}
    if '8' in flags:return 'incorrect'
    if flags & {'1','2','3'}:return 'accepted' if level>=7 else 'provisional'
    if '5' in flags:return 'doubtful'
    return 'provisional'


def reconcile_dwd(records,metadata):
    """Prefer one quality-controlled annual date over provisional immediate dates.

    Match station, reported variety, year, BBCH, original object and phase.
    This is an explicit source-precedence policy, not proof of a source revision.
    """
    groups=defaultdict(set);rejected={}
    for r in records:
        for x in metadata.get(r,[]):
            if x.get('object_id') and x.get('phase_id'):
                groups[(r[0],r[1],r[5][:4],r[6],x['object_id'],x['phase_id'])].add(r)
    for key,rows in groups.items():
        def matching(r):return [x for x in metadata[r] if (x['object_id'],x['phase_id'])==key[-2:]]
        authoritative=[r for r in rows if any(x['reporter_type']=='annual' and int(x.get('quality_level') or 0)>=7 and x['date_quality_flag'] in {'1','2','3'} for x in matching(r))]
        dates={r[5] for r in authoritative}
        if len(dates)!=1:continue
        for r in rows:
            if r[5] in dates:continue
            source=matching(r)
            if source and all(x['reporter_type']=='immediate' and int(x.get('quality_level') or 0)<7 for x in source):
                rejected[r]=[dict(rule='higher_quality_annual_report',annual_dates=sorted(dates),object_id=key[-2],phase_id=key[-1],interpretation='source precedence; biological record revision not independently established')]
    return [r for r in records if r not in rejected],rejected


def screen(records):
    """Calendar eligibility, then simultaneous iterative per-record pair support."""
    groups=defaultdict(list);rejected={};ordinals={}
    for r in records:
        if r[6] not in WINDOWS:raise ValueError('Require four target BBCH codes only')
        try:day=date.fromisoformat(r[5])
        except ValueError:
            rejected[r]=[dict(rule='invalid_date')];continue
        if day.year<1951:
            rejected[r]=[dict(rule='before_1951')];continue
        lo,hi=WINDOWS[r[6]]
        if not lo<=r[5][5:]<=hi:
            rejected[r]=[dict(rule='calendar_window',allowed_month_day=[lo,hi],observed_date=r[5])];continue
        groups[(r[0],r[1],day.year)].append(r);ordinals[r]=day.toordinal()
    for group in groups.values():
        active=set(group);iteration=0
        while active:
            iteration+=1;stages=defaultdict(list);drop=defaultdict(list)
            for r in sorted(active):stages[r[6]].append(r)
            for (a,b),(lo,hi) in INTERVALS.items():
                left,right=stages[a],stages[b]
                if not left or not right:continue
                supported_left=set();supported_right=set()
                for x in left:
                    for y in right:
                        if lo<=ordinals[y]-ordinals[x]<=hi:
                            supported_left.add(x);supported_right.add(y)
                for rows,supported,other in [(left,supported_left,right),(right,supported_right,left)]:
                    for r in rows:
                        if r not in supported:
                            drop[r].append(dict(rule='adjacent_interval' if (a,b) in ADJACENT else 'derived_cross_stage_interval',stages=[a,b],allowed_days=[lo,hi],observed_date=r[5],counterpart_dates=sorted({x[5] for x in other}),iteration=iteration,identity='reported_variety' if r[1] else 'unspecified_variety_pool',interpretation='unsupported chronology; erroneous endpoint not identified'))
            if not drop:break
            rejected.update(drop);active.difference_update(drop)
    return [r for r in records if r not in rejected],rejected
