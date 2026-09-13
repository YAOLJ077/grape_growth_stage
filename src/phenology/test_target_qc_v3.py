"""Regression cases for candidate four-target screening and source precedence."""
import importlib.util
from pathlib import Path
import pytest
P=Path(__file__).with_name('target_qc_v3.py')

def api():
    assert P.exists(), 'Four-target QC implementation is not present yet'
    spec=importlib.util.spec_from_file_location('target_qc_v3',P)
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def row(stage,day,site='DE:test:1',variety='A'):
    return (site,variety,'DE','49','9',day,stage)

def test_inclusive_windows_and_leap_day():
    m=api()
    for stage,lo,hi in [('07','2000-02-01','2000-06-15'),('65','2000-04-01','2000-07-31'),('81','2000-06-01','2000-10-15'),('89','2000-07-15','2000-11-15')]:
        for day in [lo,hi]:assert m.screen([row(stage,day)])[0]==[row(stage,day)]
    assert m.screen([row('07','2000-02-29')])[0]
    assert not m.screen([row('07','2000-01-31')])[0]

def test_minimum_maximum_and_missing_intermediate():
    m=api()
    for days in [20,120]:
        from datetime import date,timedelta
        a=row('07','2000-03-01');b=row('65',(date(2000,3,1)+timedelta(days=days)).isoformat())
        # The minimum example must also pass the flowering calendar window.
        if days==20:a=row('07','2000-03-12');b=row('65','2000-04-01')
        assert len(m.screen([a,b])[0])==2
    a=row('07','2000-06-01');b=row('65','2000-06-20');assert not m.screen([a,b])[0]
    # Missing flowering does not remove a feasible budburst/veraison pair.
    assert len(m.screen([row('07','2000-04-01'),row('81','2000-07-01')])[0])==2
    # Enforce the derived minimum even when flowering was never observed.
    assert not m.screen([row('07','2000-05-20'),row('81','2000-06-10')])[0]

def test_preserve_supported_alternative_and_unrelated_stage():
    m=api();a=row('07','2000-04-01');bad=row('65','2000-04-02');good=row('65','2000-06-01');last=row('89','2000-09-01')
    kept,rejected=m.screen([a,bad,good,last]);assert set(kept)=={a,good,last};assert bad in rejected
    assert m.screen([a,last])[0]==[a,last]

def test_no_cross_site_variety_or_year_comparison():
    m=api();a=row('07','2000-06-01');b=row('65','2000-04-01',variety='');c=row('65','2000-04-01',site='DE:test:2');d=row('65','2001-04-01')
    assert len(m.screen([a,b,c,d])[0])==4

def test_source_quality_uses_highest_documented_level():
    m=api();assert m.source_quality([{'quality_level':'10','date_quality_flag':'5'},{'quality_level':'1','date_quality_flag':'0'}])=='doubtful'
    assert m.source_quality([{'quality_level':'10','date_quality_flag':'2'}])=='accepted'
    assert m.source_quality([{'quality_level':'10','date_quality_flag':'3'}])=='accepted'
    assert m.source_quality([{'quality_level':'1','date_quality_flag':'0'}])=='provisional'

def test_source_precedence_requires_matching_object_phase_and_quality():
    m=api();a=row('81','2000-08-01');b=row('81','2000-09-15')
    info={a:[{'reporter_type':'immediate','quality_level':'1','date_quality_flag':'0','object_id':'411','phase_id':'42'}],b:[{'reporter_type':'annual','quality_level':'10','date_quality_flag':'1','object_id':'411','phase_id':'42'}]}
    kept,rejected=m.reconcile_dwd([a,b],info);assert kept==[b] and rejected[a][0]['rule']=='higher_quality_annual_report'
    info[b][0]['object_id']='413';assert len(m.reconcile_dwd([a,b],info)[0])==2

def test_order_independent_and_idempotent():
    m=api();rows=[row('07','2000-04-01'),row('65','2000-06-01'),row('81','2000-06-02'),row('89','2000-09-01')]
    kept,rejected=m.screen(rows);assert set(m.screen(list(reversed(rows)))[0])==set(kept)
    assert m.screen(kept)[0]==kept
