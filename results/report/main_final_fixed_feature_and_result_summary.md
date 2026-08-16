# Final stagewise residual-ML feature set and fixed hybrid results

## Fixed feature profile

- Profile: `main_final`

- Feature counts: BBCH07 = 11, BBCH65 = 12, BBCH81 = 12, BBCH89 = 11

- Residual definition: `observed_doy - mechanistic_predicted_doy`

- Algorithm fixation: stage-level `min_rmse`; final fixed algorithms are Ridge, RF, Ridge, RF


## Fixed hybrid performance

| stage               | algorithm   |   n_features |     n |   mae_days |   rmse_days |   bias_days |   sd_outer_fold_mae_days |   worst_outer_fold_mae_days |
|:--------------------|:------------|-------------:|------:|-----------:|------------:|------------:|-------------------------:|----------------------------:|
| budburst            | ridge       |           11 |  3646 |      6.187 |       8.346 |      -0.028 |                    0.288 |                       6.683 |
| flowering           | rf          |           12 |  4288 |      5.06  |       7.716 |       0.156 |                    0.414 |                       5.521 |
| veraison            | ridge       |           12 |  4325 |     11.819 |      14.592 |      -0.063 |                    1.131 |                      13.237 |
| maturity_or_harvest | rf          |           11 | 10911 |      8.156 |      10.559 |      -0.064 |                    0.677 |                       9.193 |


## Gain over process model

| stage               | algorithm   |   n_features |   process_mae_days |   hybrid_mae_days |   mae_gain_days |   mae_gain_pct |   process_rmse_days |   hybrid_rmse_days |   rmse_gain_days |   rmse_gain_pct |
|:--------------------|:------------|-------------:|-------------------:|------------------:|----------------:|---------------:|--------------------:|-------------------:|-----------------:|----------------:|
| budburst            | ridge       |           11 |              6.798 |             6.187 |           0.611 |          8.99  |               9.563 |              8.346 |            1.217 |          12.724 |
| flowering           | rf          |           12 |              5.716 |             5.06  |           0.657 |         11.492 |               8.207 |              7.716 |            0.491 |           5.982 |
| veraison            | ridge       |           12 |             12.367 |            11.819 |           0.548 |          4.433 |              15.485 |             14.592 |            0.893 |           5.764 |
| maturity_or_harvest | rf          |           11 |             27.778 |             8.156 |          19.622 |         70.639 |              30.501 |             10.559 |           19.942 |          65.382 |


## Output tables

- `results/paper_results/main_final_fixed_hybrid_metrics.csv`

- `results/paper_results/main_final_fixed_hybrid_vs_process_gain.csv`

- `results/paper_results/main_final_fixed_algorithm_selection.csv`

- `results/paper_results/main_final_fixed_hybrid_outer_fold_metrics.csv`

- `results/paper_results/main_final_candidate_outer_metrics.csv`

- `results/paper_results/main_final_feature_sets.csv`
