import pandas as pd

from src.standardize_grape_phenology import harmonize_france_altitude


def test_france_altitude_prefers_reported_and_fills_from_ign():
    frame = pd.DataFrame(
        {
            "altitude": [120, pd.NA, -9999, pd.NA],
            "altitudeIgn": [125, 240, 300, pd.NA],
        }
    )

    result = harmonize_france_altitude(frame)

    assert result["altitude"].tolist()[:3] == [120.0, 240.0, 300.0]
    assert pd.isna(result.loc[3, "altitude"])
    assert result["altitude_source"].tolist()[:3] == [
        "tempo_reported",
        "tempo_ign",
        "tempo_ign",
    ]
