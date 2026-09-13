#!/usr/bin/env python3
"""Resolve actual ERA5-Land native pixel assignments at unchanged site points.

Earth Engine pixelCoordinates supplies half-pixel x/y coordinates. Apply the
reported affine transform directly, without adding another half pixel. The
coordinate image has no temperature mask; no interpolation or extrapolation
is used. Validated batches are cached atomically for exact-input resumption.
"""
from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from src.base_table.build_site_era5_grid_crosswalk import grid_id, nearest_grid_center

COLLECTION = 'ECMWF/ERA5_LAND/DAILY_AGGR'
SOURCE_DATE = '2000-01-01'


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',', ':'),allow_nan=False)


def sha(value):
    return hashlib.sha256(value).hexdigest()


def atomic_once(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes() != payload:
            raise ValueError(f'Existing artifact or fingerprint differs: {path}')
        return
    with tempfile.TemporaryDirectory(prefix='.publishing-',dir=path.parent) as folder:
        temporary = Path(folder)/path.name
        with temporary.open('xb') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary,path)


def validate_sites(sites):
    if not {'site','lat','lon'}.issubset(sites.columns):
        raise ValueError('Require site, lat and lon')
    result = sites[['site','lat','lon']].copy().reset_index(drop=True)
    if result.empty or result.site.isna().any() or result.site.astype(str).str.strip().eq('').any():
        raise ValueError('Missing site identifiers')
    result['site'] = result.site.astype(str)
    if result.site.duplicated().any():
        raise ValueError('Duplicate site identifiers')
    for column,bound in [('lat',90),('lon',180)]:
        try:
            values = result[column].map(float)
        except (ValueError,TypeError) as error:
            raise ValueError(f'Invalid {column} coordinates') from error
        if not (np.isfinite(values)&values.between(-bound,bound)).all():
            raise ValueError(f'Invalid {column} coordinates')
    return result


def validate_samples(sites, payload, projection):
    sites = validate_sites(sites)
    transform = np.asarray(projection.get('transform',[]),dtype=float)
    if (projection.get('crs') != 'EPSG:4326' or transform.shape != (6,)
            or not np.isfinite(transform).all()
            or not np.allclose(transform[[0,1,3,4]],[.1,0,0,-.1],rtol=0,atol=1e-12)):
        raise ValueError('Require native unrotated geographic 0.1 degree projection')
    try:
        sampled = pd.DataFrame([item['properties'] for item in payload['features']])
    except (KeyError,TypeError) as error:
        raise ValueError('Malformed sampled FeatureCollection') from error
    if (not {'site','lat','lon','x','y'}.issubset(sampled.columns)
            or sampled.site.duplicated().any() or set(sampled.site)!=set(sites.site)):
        raise ValueError('Missing, duplicate or unexpected sampled sites/pixel coordinates')
    sampled = sampled.set_index('site').loc[sites.site]
    try:
        values = sampled[['lat','lon','x','y']].map(float).to_numpy()
    except (ValueError,TypeError) as error:
        raise ValueError('Invalid sampled coordinate values') from error
    if not np.isfinite(values).all():
        raise ValueError('Nonfinite sampled coordinates')
    if not np.array_equal(values[:,:2],sites[['lat','lon']].map(float).to_numpy()):
        raise ValueError('Sampled coordinates differ from original site coordinates')
    x,y = values[:,2],values[:,3]
    if not np.allclose(values[:,2:]-.5,np.rint(values[:,2:]-.5),rtol=0,atol=1e-8):
        raise ValueError('Native pixel coordinates are not half-pixel centers')
    longitude = transform[0]*x+transform[1]*y+transform[2]
    latitude = transform[3]*x+transform[4]*y+transform[5]
    if (not np.isfinite([latitude,longitude]).all() or (np.abs(latitude)>90+1e-8).any()
            or (np.abs(longitude)>180+1e-8).any()
            or not np.allclose(latitude,np.round(latitude,1),rtol=0,atol=1e-8)
            or not np.allclose(longitude,np.round(longitude,1),rtol=0,atol=1e-8)):
        raise ValueError('Transformed sample is outside or off the regular 0.1 degree grid')
    longitude_distance = np.abs((longitude-values[:,1]+180)%360-180)
    if (np.abs(latitude-values[:,0])>.05+1e-8).any() or (longitude_distance>.05+1e-8).any():
        raise ValueError('Sampled native pixel does not contain its original site point')
    result = sites.copy()
    # Remove affine floating-point noise only after alignment is verified.
    result['era5_grid_lat'],result['era5_grid_lon'] = np.round(latitude,1),np.round(longitude,1)
    result['era5_grid_id'] = [grid_id(lat,lon) for lat,lon in zip(result.era5_grid_lat,result.era5_grid_lon)]
    result['pixel_x'],result['pixel_y'] = x,y
    return result


def resolve_batches(sites, projection, output, fingerprints, fetch, batch_size=500):
    sites = validate_sites(sites)
    if not isinstance(batch_size,int) or not 1<=batch_size<=500:
        raise ValueError('Batch size must be between 1 and 500')
    output = Path(output)
    output.mkdir(parents=True,exist_ok=True)
    contract = dict(fingerprints=fingerprints,projection=projection,batch_size=batch_size,
        sites_sha256=sha(sites.to_csv(index=False).encode()))
    with (output/'.resolve.lock').open('a+') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        atomic_once(output/'batches.json',(canonical(contract)+'\n').encode())
        results = []
        for start in range(0,len(sites),batch_size):
            batch = sites.iloc[start:start+batch_size]
            path = output/'batches'/f'{start//batch_size:04d}.json'
            identity = dict(contract_sha256=sha(canonical(contract).encode()),sites=batch.site.tolist())
            if path.exists():
                cached = json.loads(path.read_text())
                if cached['identity']!=identity or cached['payload_sha256']!=sha(canonical(cached['payload']).encode()):
                    raise ValueError(f'Cached batch fingerprint differs: {path}')
                payload = cached['payload']
            else:
                payload = fetch(batch)
                validate_samples(batch,payload,projection)
                cached = dict(identity=identity,payload=payload,payload_sha256=sha(canonical(payload).encode()))
                atomic_once(path,(canonical(cached)+'\n').encode())
            results.append(validate_samples(batch,payload,projection))
            print(f'Native grid: {min(start+batch_size,len(sites))}/{len(sites)} sites verified',flush=True)
        result = pd.concat(results,ignore_index=True)
        if result.site.tolist()!=sites.site.tolist():
            raise ValueError('Final sampled site population differs')
        return result


def resolve(sites_path, output, project, batch_size=500):
    sites_path,output = Path(sites_path).resolve(),Path(output).resolve()
    sites = validate_sites(pd.read_csv(sites_path,dtype=str,keep_default_na=False))
    sources = [Path(__file__),ROOT/'src/base_table/build_site_era5_grid_crosswalk.py']
    fingerprints = dict(sites_path=str(sites_path),input_sha256=sha(sites_path.read_bytes()),
        source_sha256={str(path.resolve()):sha(path.read_bytes()) for path in sources},
        project=project,collection=COLLECTION,source_date=SOURCE_DATE,band='temperature_2m')
    client = []
    def earth_engine():
        if not client:
            import ee
            import httplib2
            ee.Initialize(project=project,http_transport=httplib2.Http(timeout=60))
            client.append(ee)
        return client[0]
    request_path = output/'request.json'
    if request_path.exists():
        request = json.loads(request_path.read_text())
        if request['fingerprints']!=fingerprints:
            raise ValueError('Native-grid request fingerprint differs')
        projection = request['projection']
        if request['projection_sha256']!=sha(canonical(projection).encode()):
            raise ValueError('Projection fingerprint differs')
    else:
        ee = earth_engine()
        source = ee.ImageCollection(COLLECTION).filterDate(SOURCE_DATE,'2000-01-02').first().select('temperature_2m')
        projection = source.projection().getInfo()
        request = dict(fingerprints=fingerprints,projection=projection,
            projection_sha256=sha(canonical(projection).encode()),
            sampling='unmasked pixelCoordinates; native crsTransform; Reducer.first; direct affine x/y')
        atomic_once(request_path,(canonical(request)+'\n').encode())
    def fetch(batch):
        ee = earth_engine()
        native = ee.Projection(projection['crs'],projection['transform'])
        points = ee.FeatureCollection([ee.Feature(ee.Geometry.Point([float(row.lon),float(row.lat)]),
            dict(site=row.site,lat=float(row.lat),lon=float(row.lon))) for row in batch.itertuples()])
        return ee.Image.pixelCoordinates(native).reduceRegions(collection=points,reducer=ee.Reducer.first(),
            crs=projection['crs'],crsTransform=projection['transform'],tileScale=4).getInfo()
    result = resolve_batches(sites,projection,output,fingerprints,fetch,batch_size)
    if sha(sites_path.read_bytes())!=fingerprints['input_sha256'] or any(
            sha(Path(path).read_bytes())!=expected for path,expected in fingerprints['source_sha256'].items()):
        raise ValueError('Input/source changed during native-grid sampling')
    legacy = result.copy()
    legacy['legacy_grid_lat'] = sites.lat.map(float).map(nearest_grid_center)
    legacy['legacy_grid_lon'] = sites.lon.map(float).map(nearest_grid_center)
    legacy['legacy_grid_id'] = [grid_id(lat,lon) for lat,lon in zip(legacy.legacy_grid_lat,legacy.legacy_grid_lon)]
    differences = legacy.loc[legacy.era5_grid_id.ne(legacy.legacy_grid_id)]
    artifacts = {}
    for name,frame in [('site_native_grid.csv',result),('legacy_differences.csv',differences)]:
        payload = frame.to_csv(index=False).encode()
        atomic_once(output/name,payload)
        artifacts[name] = sha(payload)
    diagnostics = dict(n_sites=len(result),n_grids=result.era5_grid_id.nunique(),
        n_different_from_legacy=len(differences),legacy_method='nearest center, lower-coordinate ties',
        authoritative_method=request['sampling'],fingerprints=fingerprints,
        projection=projection,projection_sha256=request['projection_sha256'],artifacts=artifacts,
        batches={path.name:sha(path.read_bytes()) for path in sorted((output/'batches').glob('*.json'))})
    atomic_once(output/'diagnostics.json',(canonical(diagnostics)+'\n').encode())
    print(json.dumps(diagnostics,indent=2),flush=True)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sites',type=Path,default=ROOT/'data/site_inventory.csv')
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--project',default='smart-soil-erosion')
    parser.add_argument('--batch-size',type=int,default=500)
    args = parser.parse_args()
    resolve(args.sites,args.output,args.project,args.batch_size)


if __name__=='__main__':
    main()
