# main_final 机制组消融摘要

固定使用 `main_final` 的阶段残差学习算法和每折超参数配置；仅改变机制组特征集合。

## Full mechanism performance

| stage               | algorithm   |   n_features |     n |   mae_days |   rmse_days |   bias_days |   sd_outer_fold_mae_days |   worst_outer_fold_mae_days |
|:--------------------|:------------|-------------:|------:|-----------:|------------:|------------:|-------------------------:|----------------------------:|
| budburst            | ridge       |           11 |  3646 |      6.187 |       8.346 |      -0.028 |                    0.288 |                       6.683 |
| flowering           | rf          |           12 |  4288 |      5.055 |       7.709 |       0.149 |                    0.422 |                       5.525 |
| veraison            | ridge       |           12 |  4325 |     11.819 |      14.592 |      -0.063 |                    1.131 |                      13.237 |
| maturity_or_harvest | rf          |           11 | 10911 |      8.153 |      10.559 |      -0.038 |                    0.666 |                       9.173 |

## Ranked group contribution

| stage               | mechanism_group       |   n_group_features |   addon_rmse_gain_vs_anchor_days |   leaveout_rmse_cost_vs_all_days |   addon_mae_gain_vs_anchor_days |   leaveout_mae_cost_vs_all_days |
|:--------------------|:----------------------|-------------------:|---------------------------------:|---------------------------------:|--------------------------------:|--------------------------------:|
| budburst            | process_state         |                  1 |                            0     |                            0.872 |                           0     |                           0.349 |
| budburst            | temperature_structure |                  4 |                            0.419 |                            0.179 |                           0.257 |                           0.143 |
| budburst            | radiation_light       |                  1 |                            0.095 |                            0.036 |                           0.106 |                           0.048 |
| budburst            | terrain_spatial       |                  5 |                            0.181 |                           -0.041 |                          -0.009 |                          -0.092 |
| flowering           | temperature_structure |                  4 |                            0.47  |                            0.194 |                           0.663 |                           0.327 |
| flowering           | water_drought         |                  4 |                            0.301 |                            0.052 |                           0.381 |                           0.084 |
| flowering           | radiation_light       |                  1 |                            0.252 |                            0.016 |                           0.296 |                          -0.003 |
| flowering           | process_state         |                  1 |                            0     |                            0.003 |                           0     |                           0.01  |
| flowering           | terrain_spatial       |                  2 |                           -0.058 |                           -0.019 |                          -0.106 |                          -0.03  |
| maturity_or_harvest | process_state         |                  1 |                            0     |                            0.185 |                           0     |                           0.148 |
| maturity_or_harvest | temperature_structure |                  3 |                            0.384 |                            0.122 |                           0.378 |                           0.121 |
| maturity_or_harvest | water_drought         |                  3 |                            0.381 |                            0.052 |                           0.369 |                           0.057 |
| maturity_or_harvest | radiation_light       |                  1 |                            0.157 |                            0.022 |                           0.156 |                           0.024 |
| maturity_or_harvest | terrain_spatial       |                  3 |                            0.022 |                           -0.024 |                          -0.018 |                          -0.067 |
| veraison            | terrain_spatial       |                  4 |                            0.63  |                            0.421 |                           0.462 |                           0.276 |
| veraison            | process_state         |                  2 |                            0     |                            0.166 |                           0     |                           0.139 |
| veraison            | process_timing        |                  1 |                            0.352 |                            0.15  |                           0.255 |                           0.108 |
| veraison            | temperature_structure |                  5 |                            0.18  |                            0.038 |                           0.125 |                           0.074 |
| veraison            | water_drought         |                  1 |                            0.009 |                           -0.006 |                           0.002 |                          -0.018 |

## Output tables

- `results/paper_results/main_final_mechanism_group_ablation_aggregate_metrics.csv`
- `results/paper_results/main_final_mechanism_group_ablation_contribution_summary.csv`
- `results/paper_results/main_final_mechanism_group_ablation_outer_fold_metrics.csv`
- `results/paper_results/main_final_mechanism_group_ablation_matrix.csv`
- `results/paper_results/main_final_mechanism_group_feature_assignments.csv`
- `results/paper_results/main_final_mechanism_group_fixed_model_configs.csv`
- `results/paper_results/main_final_mechanism_group_ablation_ranked_contribution.csv`
