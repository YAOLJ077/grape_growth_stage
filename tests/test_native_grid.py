import copy
import importlib
import json
from pathlib import Path

import pandas as pd
import pytest

PROJECTION = {'crs':'EPSG:4326','transform':[.1,0,-180.05,0,-.1,90.05]}


def module():
    try:
        return importlib.import_module('src.weather_processing.resolve_native_grid')
    except ModuleNotFoundError:
        pytest.fail('Native grid resolver is missing')


def probes():
    folder=Path(__file__).resolve().parents[1]/'data/topography/processed/native_grid_20260910/batches'
    identifiers=['FR:pep725:13:7032', 'HR:pep725:2101:19294']
    # The frozen native-grid samples contain the same two half-pixel probes.
    samples={row['properties']['site']: row for path in folder.glob('*.json')
             for row in json.loads(path.read_text())['payload']['features']
             if row['properties']['site'] in identifiers}
    payload={'type':'FeatureCollection','features':[samples[site] for site in identifiers]}
    sites=pd.DataFrame([{'site':row['properties']['site'],
        'lat':str(row['properties']['lat']),'lon':str(row['properties']['lon'])}
        for row in payload['features']])
    return sites,payload


def test_actual_half_pixel_probes_transform_directly_and_preserve_input_precision():
    sites,payload=probes()
    sites.loc[0,'lat']='43.35000'
    result=module().validate_samples(sites,payload,PROJECTION)
    assert result.era5_grid_lat.tolist()==[43.4,43.2]
    assert result.era5_grid_lon.tolist()==[3.5,16.5]
    assert result.pixel_x.tolist()==[1835.5,1965.5]
    assert result.pixel_y.tolist()==[466.5,468.5]
    assert result.lat.tolist()==['43.35000','43.167']
    assert result.site.tolist()==sites.site.tolist()


@pytest.mark.parametrize('kind',['duplicate','missing','unexpected','missing_pixel','nonfinite_pixel','off_grid','outside_world','wrong_pixel','changed_coordinate'])
def test_invalid_sample_population_or_coordinates_are_rejected(kind):
    sites,payload=probes()
    payload=copy.deepcopy(payload)
    first=payload['features'][0]['properties']
    if kind=='duplicate': payload['features'].append(copy.deepcopy(payload['features'][0]))
    if kind=='missing': payload['features'].pop()
    if kind=='unexpected': first['site']='other'
    if kind=='missing_pixel': first.pop('x')
    if kind=='nonfinite_pixel': first['x']=float('nan')
    if kind=='off_grid': first['x']=1835.7
    if kind=='outside_world': first['x']=5000.5
    if kind=='wrong_pixel': first['x']=1836.5
    if kind=='changed_coordinate': first['lat']=43.3
    with pytest.raises(ValueError): module().validate_samples(sites,payload,PROJECTION)


def test_site_input_requires_unique_complete_valid_coordinates():
    sites,_=probes()
    for invalid in [pd.concat([sites,sites.iloc[[0]]]),sites.assign(lat='nan'),
                    sites.assign(lon='181'),sites.assign(site='')]:
        with pytest.raises(ValueError): module().validate_sites(invalid)


def test_batch_cache_resumes_without_download_and_checks_fingerprints(tmp_path):
    sites,payload=probes()
    requests=[]
    def fetch(batch):
        requests.append(batch.site.tolist())
        return payload
    resolver=module()
    result=resolver.resolve_batches(sites,PROJECTION,tmp_path,{'input':'hash'},fetch,batch_size=2)
    assert len(requests)==1 and len(result)==2
    resolver.resolve_batches(sites,PROJECTION,tmp_path,{'input':'hash'},fetch,batch_size=2)
    assert len(requests)==1
    with pytest.raises(ValueError,match='fingerprint'):
        resolver.resolve_batches(sites,PROJECTION,tmp_path,{'input':'changed'},fetch,batch_size=2)
    assert len(requests)==1
