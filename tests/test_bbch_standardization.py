import pandas as pd

from src.standardize_bbch_analysis_layer import (
    phenophase_from_bbch,
    standardize_bbch,
)


def test_direct_bbch_is_normalized_with_high_confidence():
    bbch, confidence, note = standardize_bbch(
        pd.Series({"source_system": "pep725", "stage_id": 61, "bbch_code": 7})
    )

    assert bbch == "07"
    assert confidence == "high"
    assert "direct" in note


def test_source_specific_extended_stages_are_mapped():
    assert standardize_bbch(
        pd.Series(
            {
                "source_system": "germany_dwd",
                "stage_id": 30,
                "bbch_code": pd.NA,
            }
        )
    )[:2] == ("89", "medium")
    assert standardize_bbch(
        pd.Series(
            {
                "source_system": "pep725",
                "stage_id": 205,
                "bbch_code": pd.NA,
            }
        )
    )[:2] == ("95", "medium")


def test_unmapped_bleeding_stage_keeps_phenophase():
    bbch, confidence, _ = standardize_bbch(
        pd.Series(
            {
                "source_system": "germany_dwd",
                "stage_id": 2,
                "bbch_code": pd.NA,
            }
        )
    )

    assert bbch == ""
    assert confidence == "unmapped"
    assert phenophase_from_bbch("", "germany_dwd", "2") == ("bleeding", 0)


def test_standard_bbch_ranges_map_to_expected_phenophases():
    assert phenophase_from_bbch("07", "pep725", "7") == ("budburst", 1)
    assert phenophase_from_bbch("65", "pep725", "65") == ("flowering", 4)
    assert phenophase_from_bbch("81", "pep725", "81") == ("veraison", 6)
    assert phenophase_from_bbch("89", "pep725", "89") == (
        "maturity_or_harvest",
        7,
    )
