import pandas as pd

from src.base_table.build_base_table import BASE_COLUMNS, build_base_table


def make_row(**overrides):
    row = {column: pd.NA for column in BASE_COLUMNS}
    row.update(
        {
            "source_system": "test_source",
            "country_name": "France",
            "site_id": "site-1",
            "site_name": "Test site",
            "latitude": 48.0,
            "longitude": 2.0,
            "altitude": 100.0,
            "date": "2000-04-09",
            "year": 2000,
            "month": 4,
            "day": 9,
            "doy": 100,
            "bbch_standard": "7",
            "bbch_major": "0",
            "phenophase_standard": "budburst",
            "phenophase_order": 1,
            "bbch_mapping_confidence": "high",
        }
    )
    row.update(overrides)
    return row


def test_base_table_filters_to_valid_1951_plus_rows_and_adds_continuity():
    frame = pd.DataFrame(
        [
            make_row(year=2000, date="2000-04-09", doy=100),
            make_row(year=2001, date="2001-04-10", doy=100),
            make_row(year=1950, date="1950-04-10", doy=100),
            make_row(site_id="missing-coordinates", latitude=pd.NA),
        ]
    )

    result = build_base_table(frame, start_year=1951)

    assert len(result) == 2
    assert result["year"].tolist() == [2000, 2001]
    assert result["bbch_standard"].tolist() == ["07", "07"]
    assert result["n_years_site_bbch"].tolist() == [2, 2]
    assert result["n_observations_site_bbch"].tolist() == [2, 2]
