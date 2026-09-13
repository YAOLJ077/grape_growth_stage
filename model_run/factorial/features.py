"""Prediction-bounded weather features using the selected forcing and actual starts."""
import numpy as np
import pandas as pd

from model.residual.data import FEATURES, KEYS, TERRAIN, correct_dates

TEMPERATURE_COLUMNS = {'RAW': 'Tmean', 'DEM': 'Tmean_DEM'}


def build_features(predictions, weather, terrain, temperature_input):
    column = TEMPERATURE_COLUMNS[temperature_input]
    result = predictions.copy().reset_index(drop=True)
    result['BBCH'] = result.BBCH.astype(str).str.zfill(2)
    for name in ('predicted_date', 'phase_start_date'):
        result[name] = pd.to_datetime(result[name])
    if result.duplicated(KEYS).any() or terrain.site.duplicated().any():
        raise ValueError('Duplicate prediction keys or terrain sites')
    topography = terrain.set_index('site')
    if not set(result.site).issubset(topography.index):
        raise ValueError('Missing terrain sites')
    weather = weather.loc[weather.site.isin(result.site), ['site','Date',column]].copy()
    weather['Date'] = pd.to_datetime(weather.Date)
    if weather.duplicated(['site','Date']).any():
        raise ValueError('Duplicate weather dates')
    lookup = {site: (part.Date.to_numpy(dtype='datetime64[D]'), part[column].to_numpy(float))
              for site,part in weather.sort_values(['site','Date']).groupby('site',sort=False)}
    values = np.full((len(result),len(FEATURES)), np.nan)
    for row in result.itertuples():
        if pd.isna(row.predicted_date):
            continue
        if pd.isna(row.phase_start_date) or row.phase_start_date > row.predicted_date:
            raise ValueError('Require actual valid PBM phase_start_date')
        doy = (row.predicted_date - pd.Timestamp(int(row.season),1,1)).days + 1
        features = [doy, (row.predicted_date-row.phase_start_date).days+1]
        if row.site not in lookup:
            raise ValueError('Missing weather feature window')
        days, temperature = lookup[row.site]
        end = np.datetime64(row.predicted_date,'D')
        for window in (7,30,90):
            wanted = np.arange(end-np.timedelta64(window-1,'D'),end+np.timedelta64(1,'D'))
            indices = np.searchsorted(days,wanted)
            if (indices >= len(days)).any() or not np.array_equal(days[indices],wanted):
                raise ValueError(f'Incomplete weather feature window: {row.site} {end}')
            t = temperature[indices]
            if not np.isfinite(t).all():
                raise ValueError('Nonfinite weather feature window')
            features.extend((t.mean(),t.std(ddof=0),t.min(),t.max()))
        terrain_row = topography.loc[row.site]
        declination = .409*np.sin(2*np.pi*row.predicted_date.dayofyear/365-1.39)
        angle = np.arccos(np.clip(-np.tan(np.deg2rad(float(terrain_row.lat)))*np.tan(declination),-1,1))
        terrain_values = terrain_row[TERRAIN].to_numpy(float)
        if np.isinf(terrain_values).any() or not np.isfinite(terrain_row.lat):
            raise ValueError('Invalid terrain predictors')
        features.extend((24/np.pi*angle,*terrain_values))
        values[row.Index] = features
    result[FEATURES] = values
    result['feature_end_date'] = result.predicted_date
    return result
