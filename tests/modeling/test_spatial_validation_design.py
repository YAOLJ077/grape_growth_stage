import pandas as pd

from src.modeling.build_spatial_validation_design import (
    add_validation_weather_blocks,
    balanced_group_assignment,
)


def synthetic_events():
    rows = []
    for block_index in range(8):
        country = "France" if block_index < 4 else "Germany"
        for stage in ("budburst", "flowering"):
            for event_index in range(block_index + 1):
                rows.append(
                    {
                        "record_id": f"{block_index}-{stage}-{event_index}",
                        "site_uid": f"site-{block_index}-{event_index}",
                        "country": country,
                        "target_stage": stage,
                        "validation_block_1deg_id": f"block-{block_index}",
                    }
                )
    return pd.DataFrame(rows)


def test_weather_blocks_are_anchored_to_grid_centers():
    frame = pd.DataFrame(
        {
            "era5_grid_lat": [49.95, 49.95, 50.05],
            "era5_grid_lon": [8.95, 8.95, 9.05],
            "spatial_block_1deg_id": ["site-left", "site-right", "site-other"],
        }
    )
    result = add_validation_weather_blocks(frame)

    assert result.loc[0, "validation_block_1deg_id"] == result.loc[1, "validation_block_1deg_id"]
    assert result.loc[0, "validation_block_1deg_id"] != result.loc[2, "validation_block_1deg_id"]


def test_balanced_assignment_is_deterministic_and_keeps_groups_intact():
    events = synthetic_events()
    first, first_score = balanced_group_assignment(
        events, "validation_block_1deg_id", n_folds=2, seed=17, n_restarts=30
    )
    second, second_score = balanced_group_assignment(
        events, "validation_block_1deg_id", n_folds=2, seed=17, n_restarts=30
    )

    pd.testing.assert_frame_equal(first, second)
    assert first_score == second_score
    assert first["validation_block_1deg_id"].is_unique
    assert set(first["fold"]) == {1, 2}
