import numpy as np
import pandas as pd
import pytest

from model_run.factorial.features import build_features


def fixture():
    dates = pd.date_range('1999-06-04', '2000-12-31')
    weather = pd.DataFrame(dict(site='s', Date=dates, Tmean=10., Tmean_DEM=8.))
    terrain = pd.DataFrame([dict(site='s',lat=45.,dem_elevation_m=100.,slope_deg=2.,
        northness=1.,eastness=0.,dem_local_std_m=4.)])
    predictions = pd.DataFrame([dict(site='s',season=2000,BBCH='07',
        predicted_date=pd.Timestamp('1999-09-10'),phase_start_date=pd.Timestamp('1999-09-01'))])
    return predictions,weather,terrain


def test_actual_previous_year_phase_and_selected_temperature():
    predictions,weather,terrain=fixture()
    raw=build_features(predictions,weather,terrain,'RAW')
    dem=build_features(predictions,weather,terrain,'DEM')
    assert raw.phase_duration_days.iloc[0] == 10
    assert raw.Tmean_mean_90.iloc[0] == 10
    assert dem.Tmean_mean_90.iloc[0] == 8
    assert raw.pbm_doy.iloc[0] < 0
    assert raw.feature_end_date.iloc[0] == pd.Timestamp('1999-09-10')


def test_complete_actual_history_and_no_invented_stage():
    predictions,weather,terrain=fixture()
    with pytest.raises(ValueError,match='window'):
        build_features(predictions,weather.drop(index=30),terrain,'DEM')
    predictions['predicted_date']=pd.NaT
    assert build_features(predictions,weather,terrain,'DEM').Tmean_mean_90.isna().all()
