# 残差学习机制组消融报告

固定使用 `main_final` 的阶段残差学习算法和每折超参数配置；仅改变机制组特征集合。

残差定义：`residual_days = observed_doy - mechanistic_predicted_doy`。正残差表示过程模型预测偏早，负残差表示过程模型预测偏晚。

## 1. 机制组贡献摘要

| stage               | mechanism_group       |   n_group_features | addon_profile                     |   addon_mae_gain_vs_anchor_days |   addon_rmse_gain_vs_anchor_days | leaveout_profile                  |   leaveout_mae_cost_vs_all_days |   leaveout_rmse_cost_vs_all_days |
|:--------------------|:----------------------|-------------------:|:----------------------------------|--------------------------------:|---------------------------------:|:----------------------------------|--------------------------------:|---------------------------------:|
| budburst            | process_state         |                  1 | anchor_only                       |                           0     |                            0     | environment_only_no_process_state |                           0.349 |                            0.872 |
| budburst            | process_timing        |                  0 | anchor_plus_process_timing        |                           0     |                            0     | all_minus_process_timing          |                           0     |                            0     |
| budburst            | temperature_structure |                  4 | anchor_plus_temperature_structure |                           0.257 |                            0.419 | all_minus_temperature_structure   |                           0.143 |                            0.179 |
| budburst            | water_drought         |                  0 | anchor_plus_water_drought         |                           0     |                            0     | all_minus_water_drought           |                           0     |                            0     |
| budburst            | radiation_light       |                  1 | anchor_plus_radiation_light       |                           0.106 |                            0.095 | all_minus_radiation_light         |                           0.048 |                            0.036 |
| budburst            | terrain_spatial       |                  5 | anchor_plus_terrain_spatial       |                          -0.009 |                            0.181 | all_minus_terrain_spatial         |                          -0.092 |                           -0.041 |
| flowering           | process_state         |                  1 | anchor_only                       |                           0     |                            0     | environment_only_no_process_state |                           0.01  |                            0.003 |
| flowering           | process_timing        |                  0 | anchor_plus_process_timing        |                           0     |                            0     | all_minus_process_timing          |                           0     |                            0     |
| flowering           | temperature_structure |                  4 | anchor_plus_temperature_structure |                           0.663 |                            0.47  | all_minus_temperature_structure   |                           0.327 |                            0.194 |
| flowering           | water_drought         |                  4 | anchor_plus_water_drought         |                           0.381 |                            0.301 | all_minus_water_drought           |                           0.084 |                            0.052 |
| flowering           | radiation_light       |                  1 | anchor_plus_radiation_light       |                           0.296 |                            0.252 | all_minus_radiation_light         |                          -0.003 |                            0.016 |
| flowering           | terrain_spatial       |                  2 | anchor_plus_terrain_spatial       |                          -0.106 |                           -0.058 | all_minus_terrain_spatial         |                          -0.03  |                           -0.019 |
| veraison            | process_state         |                  2 | anchor_only                       |                           0     |                            0     | environment_only_no_process_state |                           0.139 |                            0.166 |
| veraison            | process_timing        |                  1 | anchor_plus_process_timing        |                           0.255 |                            0.352 | all_minus_process_timing          |                           0.108 |                            0.15  |
| veraison            | temperature_structure |                  5 | anchor_plus_temperature_structure |                           0.125 |                            0.18  | all_minus_temperature_structure   |                           0.074 |                            0.038 |
| veraison            | water_drought         |                  1 | anchor_plus_water_drought         |                           0.002 |                            0.009 | all_minus_water_drought           |                          -0.018 |                           -0.006 |
| veraison            | radiation_light       |                  0 | anchor_plus_radiation_light       |                           0     |                            0     | all_minus_radiation_light         |                           0     |                            0     |
| veraison            | terrain_spatial       |                  4 | anchor_plus_terrain_spatial       |                           0.462 |                            0.63  | all_minus_terrain_spatial         |                           0.276 |                            0.421 |
| maturity_or_harvest | process_state         |                  1 | anchor_only                       |                           0     |                            0     | environment_only_no_process_state |                           0.148 |                            0.185 |
| maturity_or_harvest | process_timing        |                  0 | anchor_plus_process_timing        |                           0     |                            0     | all_minus_process_timing          |                           0     |                            0     |
| maturity_or_harvest | temperature_structure |                  3 | anchor_plus_temperature_structure |                           0.378 |                            0.384 | all_minus_temperature_structure   |                           0.121 |                            0.122 |
| maturity_or_harvest | water_drought         |                  3 | anchor_plus_water_drought         |                           0.369 |                            0.381 | all_minus_water_drought           |                           0.057 |                            0.052 |
| maturity_or_harvest | radiation_light       |                  1 | anchor_plus_radiation_light       |                           0.156 |                            0.157 | all_minus_radiation_light         |                           0.024 |                            0.022 |
| maturity_or_harvest | terrain_spatial       |                  3 | anchor_plus_terrain_spatial       |                          -0.018 |                            0.022 | all_minus_terrain_spatial         |                          -0.067 |                           -0.024 |

## 2. 外层空间性能矩阵

| stage               | profile                           | algorithm   |   n_features |   mae_days |   rmse_days |   bias_days |   within_7d_pct |   mae_gain_vs_process_days |   rmse_gain_vs_process_days |
|:--------------------|:----------------------------------|:------------|-------------:|-----------:|------------:|------------:|----------------:|---------------------------:|----------------------------:|
| budburst            | all_minus_terrain_spatial         | ridge       |            6 |      6.094 |       8.305 |       0.061 |          68.239 |                      0.703 |                       1.257 |
| budburst            | all_mechanisms                    | ridge       |           11 |      6.187 |       8.346 |      -0.028 |          67.17  |                      0.611 |                       1.217 |
| budburst            | all_minus_process_timing          | ridge       |           11 |      6.187 |       8.346 |      -0.028 |          67.17  |                      0.611 |                       1.217 |
| budburst            | all_minus_water_drought           | ridge       |           11 |      6.187 |       8.346 |      -0.028 |          67.17  |                      0.611 |                       1.217 |
| budburst            | anchor_plus_temperature_structure | ridge       |            5 |      6.155 |       8.348 |       0.055 |          67.965 |                      0.643 |                       1.214 |
| budburst            | all_minus_radiation_light         | ridge       |           10 |      6.235 |       8.382 |      -0.035 |          66.731 |                      0.563 |                       1.181 |
| budburst            | all_minus_temperature_structure   | ridge       |            7 |      6.33  |       8.524 |       0.039 |          65.469 |                      0.468 |                       1.038 |
| budburst            | anchor_plus_terrain_spatial       | ridge       |            6 |      6.421 |       8.586 |       0.042 |          65.003 |                      0.377 |                       0.976 |
| budburst            | anchor_plus_radiation_light       | ridge       |            2 |      6.307 |       8.672 |       0.131 |          67.06  |                      0.491 |                       0.89  |
| budburst            | anchor_only                       | ridge       |            1 |      6.412 |       8.768 |       0.13  |          65.826 |                      0.386 |                       0.795 |
| budburst            | anchor_plus_process_timing        | ridge       |            1 |      6.412 |       8.768 |       0.13  |          65.826 |                      0.386 |                       0.795 |
| budburst            | anchor_plus_water_drought         | ridge       |            1 |      6.412 |       8.768 |       0.13  |          65.826 |                      0.386 |                       0.795 |
| budburst            | environment_only_no_process_state | ridge       |           10 |      6.536 |       9.218 |       0.074 |          66.648 |                      0.262 |                       0.344 |
| flowering           | all_minus_terrain_spatial         | rf          |           10 |      5.025 |       7.69  |       0.157 |          78.941 |                      0.692 |                       0.518 |
| flowering           | all_mechanisms                    | rf          |           12 |      5.055 |       7.709 |       0.149 |          78.288 |                      0.661 |                       0.499 |
| flowering           | all_minus_process_timing          | rf          |           12 |      5.055 |       7.709 |       0.149 |          78.288 |                      0.661 |                       0.499 |
| flowering           | environment_only_no_process_state | rf          |           11 |      5.065 |       7.711 |       0.134 |          78.335 |                      0.651 |                       0.496 |
| flowering           | all_minus_radiation_light         | rf          |           11 |      5.052 |       7.724 |       0.136 |          78.172 |                      0.665 |                       0.483 |
| flowering           | all_minus_water_drought           | rf          |            8 |      5.14  |       7.76  |       0.087 |          77.472 |                      0.577 |                       0.447 |
| flowering           | anchor_plus_temperature_structure | rf          |            5 |      5.117 |       7.791 |       0.144 |          77.472 |                      0.6   |                       0.416 |
| flowering           | all_minus_temperature_structure   | rf          |            8 |      5.383 |       7.903 |       0.121 |          75.63  |                      0.334 |                       0.304 |
| flowering           | anchor_plus_water_drought         | rf          |            5 |      5.399 |       7.96  |       0.016 |          75.373 |                      0.318 |                       0.247 |
| flowering           | anchor_plus_radiation_light       | rf          |            2 |      5.484 |       8.009 |       0.069 |          74.114 |                      0.233 |                       0.198 |
| flowering           | anchor_only                       | rf          |            1 |      5.78  |       8.261 |       0.056 |          71.922 |                     -0.064 |                      -0.054 |
| flowering           | anchor_plus_process_timing        | rf          |            1 |      5.78  |       8.261 |       0.056 |          71.922 |                     -0.064 |                      -0.054 |
| flowering           | anchor_plus_terrain_spatial       | rf          |            3 |      5.886 |       8.319 |       0.204 |          71.082 |                     -0.169 |                      -0.111 |
| veraison            | all_minus_water_drought           | ridge       |           11 |     11.801 |      14.586 |      -0.027 |          34.266 |                      0.566 |                       0.899 |
| veraison            | all_mechanisms                    | ridge       |           12 |     11.819 |      14.592 |      -0.063 |          34.012 |                      0.548 |                       0.893 |
| veraison            | all_minus_radiation_light         | ridge       |           12 |     11.819 |      14.592 |      -0.063 |          34.012 |                      0.548 |                       0.893 |
| veraison            | all_minus_temperature_structure   | ridge       |            7 |     11.893 |      14.631 |      -0.075 |          34.058 |                      0.474 |                       0.854 |
| veraison            | all_minus_process_timing          | ridge       |           11 |     11.927 |      14.743 |      -0.166 |          34.613 |                      0.441 |                       0.742 |
| veraison            | environment_only_no_process_state | ridge       |           10 |     11.958 |      14.758 |      -0.201 |          33.595 |                      0.409 |                       0.727 |
| veraison            | anchor_plus_terrain_spatial       | ridge       |            5 |     11.992 |      14.855 |      -0.116 |          34.636 |                      0.375 |                       0.63  |
| veraison            | all_minus_terrain_spatial         | ridge       |            8 |     12.095 |      15.013 |       0.113 |          33.85  |                      0.272 |                       0.472 |
| veraison            | anchor_plus_process_timing        | ridge       |            2 |     12.199 |      15.133 |       0.098 |          34.289 |                      0.168 |                       0.352 |
| veraison            | anchor_plus_temperature_structure | ridge       |            6 |     12.329 |      15.305 |       0.009 |          33.896 |                      0.038 |                       0.18  |
| veraison            | anchor_plus_water_drought         | ridge       |            2 |     12.452 |      15.477 |      -0.002 |          33.665 |                     -0.085 |                       0.008 |
| veraison            | anchor_only                       | ridge       |            1 |     12.454 |      15.485 |       0.005 |          33.526 |                     -0.087 |                      -0     |
| veraison            | anchor_plus_radiation_light       | ridge       |            1 |     12.454 |      15.485 |       0.005 |          33.526 |                     -0.087 |                      -0     |
| maturity_or_harvest | all_minus_terrain_spatial         | rf          |            8 |      8.086 |      10.535 |       0.204 |          53.194 |                     19.692 |                      19.966 |
| maturity_or_harvest | all_mechanisms                    | rf          |           11 |      8.153 |      10.559 |      -0.038 |          52.314 |                     19.625 |                      19.941 |
| maturity_or_harvest | all_minus_process_timing          | rf          |           11 |      8.153 |      10.559 |      -0.038 |          52.314 |                     19.625 |                      19.941 |
| maturity_or_harvest | all_minus_radiation_light         | rf          |           10 |      8.177 |      10.581 |      -0.007 |          51.948 |                     19.602 |                      19.919 |
| maturity_or_harvest | all_minus_water_drought           | rf          |            8 |      8.21  |      10.611 |      -0.063 |          52.039 |                     19.569 |                      19.89  |
| maturity_or_harvest | anchor_plus_temperature_structure | rf          |            4 |      8.207 |      10.655 |       0.225 |          52.387 |                     19.571 |                      19.846 |
| maturity_or_harvest | anchor_plus_water_drought         | rf          |            4 |      8.216 |      10.658 |       0.187 |          52.076 |                     19.562 |                      19.843 |
| maturity_or_harvest | all_minus_temperature_structure   | rf          |            8 |      8.274 |      10.681 |      -0.147 |          51.581 |                     19.504 |                      19.819 |
| maturity_or_harvest | environment_only_no_process_state | rf          |           10 |      8.301 |      10.744 |      -0.043 |          51.618 |                     19.477 |                      19.757 |
| maturity_or_harvest | anchor_plus_radiation_light       | rf          |            2 |      8.429 |      10.882 |       0.036 |          50.829 |                     19.349 |                      19.619 |
| maturity_or_harvest | anchor_plus_terrain_spatial       | rf          |            4 |      8.604 |      11.016 |      -0.073 |          49.4   |                     19.174 |                      19.484 |
| maturity_or_harvest | anchor_plus_process_timing        | rf          |            1 |      8.586 |      11.039 |       0.282 |          49.83  |                     19.192 |                      19.462 |
| maturity_or_harvest | anchor_only                       | rf          |            1 |      8.586 |      11.039 |       0.282 |          49.83  |                     19.192 |                      19.462 |

## 3. profile矩阵

| stage               | profile                           |   n_features | feature_groups                                                                     | is_noop   |
|:--------------------|:----------------------------------|-------------:|:-----------------------------------------------------------------------------------|:----------|
| budburst            | anchor_only                       |            1 | process_anchor                                                                     | False     |
| budburst            | anchor_plus_process_timing        |            1 | process_anchor;process_timing                                                      | False     |
| budburst            | anchor_plus_temperature_structure |            5 | process_anchor;temperature_structure                                               | False     |
| budburst            | anchor_plus_water_drought         |            1 | process_anchor;water_drought                                                       | False     |
| budburst            | anchor_plus_radiation_light       |            2 | process_anchor;radiation_light                                                     | False     |
| budburst            | anchor_plus_terrain_spatial       |            6 | process_anchor;terrain_spatial                                                     | False     |
| budburst            | all_mechanisms                    |           11 | process_anchor;temperature_structure;radiation_light;terrain_spatial               | False     |
| budburst            | all_minus_process_timing          |           11 | process_anchor;temperature_structure;radiation_light;terrain_spatial               | True      |
| budburst            | all_minus_temperature_structure   |            7 | process_anchor;radiation_light;terrain_spatial                                     | False     |
| budburst            | all_minus_water_drought           |           11 | process_anchor;temperature_structure;radiation_light;terrain_spatial               | True      |
| budburst            | all_minus_radiation_light         |           10 | process_anchor;temperature_structure;terrain_spatial                               | False     |
| budburst            | all_minus_terrain_spatial         |            6 | process_anchor;temperature_structure;radiation_light                               | False     |
| budburst            | environment_only_no_process_state |           10 | temperature_structure;radiation_light;terrain_spatial                              | False     |
| flowering           | anchor_only                       |            1 | process_anchor                                                                     | False     |
| flowering           | anchor_plus_process_timing        |            1 | process_anchor;process_timing                                                      | False     |
| flowering           | anchor_plus_temperature_structure |            5 | process_anchor;temperature_structure                                               | False     |
| flowering           | anchor_plus_water_drought         |            5 | process_anchor;water_drought                                                       | False     |
| flowering           | anchor_plus_radiation_light       |            2 | process_anchor;radiation_light                                                     | False     |
| flowering           | anchor_plus_terrain_spatial       |            3 | process_anchor;terrain_spatial                                                     | False     |
| flowering           | all_mechanisms                    |           12 | process_anchor;temperature_structure;water_drought;radiation_light;terrain_spatial | False     |
| flowering           | all_minus_process_timing          |           12 | process_anchor;temperature_structure;water_drought;radiation_light;terrain_spatial | True      |
| flowering           | all_minus_temperature_structure   |            8 | process_anchor;water_drought;radiation_light;terrain_spatial                       | False     |
| flowering           | all_minus_water_drought           |            8 | process_anchor;temperature_structure;radiation_light;terrain_spatial               | False     |
| flowering           | all_minus_radiation_light         |           11 | process_anchor;temperature_structure;water_drought;terrain_spatial                 | False     |
| flowering           | all_minus_terrain_spatial         |           10 | process_anchor;temperature_structure;water_drought;radiation_light                 | False     |
| flowering           | environment_only_no_process_state |           11 | temperature_structure;water_drought;radiation_light;terrain_spatial                | False     |
| veraison            | anchor_only                       |            1 | process_anchor                                                                     | False     |
| veraison            | anchor_plus_process_timing        |            2 | process_anchor;process_timing                                                      | False     |
| veraison            | anchor_plus_temperature_structure |            6 | process_anchor;temperature_structure                                               | False     |
| veraison            | anchor_plus_water_drought         |            2 | process_anchor;water_drought                                                       | False     |
| veraison            | anchor_plus_radiation_light       |            1 | process_anchor;radiation_light                                                     | False     |
| veraison            | anchor_plus_terrain_spatial       |            5 | process_anchor;terrain_spatial                                                     | False     |
| veraison            | all_mechanisms                    |           12 | process_anchor;process_timing;temperature_structure;water_drought;terrain_spatial  | False     |
| veraison            | all_minus_process_timing          |           11 | process_anchor;temperature_structure;water_drought;terrain_spatial                 | False     |
| veraison            | all_minus_temperature_structure   |            7 | process_anchor;process_timing;water_drought;terrain_spatial                        | False     |
| veraison            | all_minus_water_drought           |           11 | process_anchor;process_timing;temperature_structure;terrain_spatial                | False     |
| veraison            | all_minus_radiation_light         |           12 | process_anchor;process_timing;temperature_structure;water_drought;terrain_spatial  | True      |
| veraison            | all_minus_terrain_spatial         |            8 | process_anchor;process_timing;temperature_structure;water_drought                  | False     |
| veraison            | environment_only_no_process_state |           10 | temperature_structure;water_drought;terrain_spatial                                | False     |
| maturity_or_harvest | anchor_only                       |            1 | process_anchor                                                                     | False     |
| maturity_or_harvest | anchor_plus_process_timing        |            1 | process_anchor;process_timing                                                      | False     |
| maturity_or_harvest | anchor_plus_temperature_structure |            4 | process_anchor;temperature_structure                                               | False     |
| maturity_or_harvest | anchor_plus_water_drought         |            4 | process_anchor;water_drought                                                       | False     |
| maturity_or_harvest | anchor_plus_radiation_light       |            2 | process_anchor;radiation_light                                                     | False     |
| maturity_or_harvest | anchor_plus_terrain_spatial       |            4 | process_anchor;terrain_spatial                                                     | False     |
| maturity_or_harvest | all_mechanisms                    |           11 | process_anchor;temperature_structure;water_drought;radiation_light;terrain_spatial | False     |
| maturity_or_harvest | all_minus_process_timing          |           11 | process_anchor;temperature_structure;water_drought;radiation_light;terrain_spatial | True      |
| maturity_or_harvest | all_minus_temperature_structure   |            8 | process_anchor;water_drought;radiation_light;terrain_spatial                       | False     |
| maturity_or_harvest | all_minus_water_drought           |            8 | process_anchor;temperature_structure;radiation_light;terrain_spatial               | False     |
| maturity_or_harvest | all_minus_radiation_light         |           10 | process_anchor;temperature_structure;water_drought;terrain_spatial                 | False     |
| maturity_or_harvest | all_minus_terrain_spatial         |            8 | process_anchor;temperature_structure;water_drought;radiation_light                 | False     |
| maturity_or_harvest | environment_only_no_process_state |           10 | temperature_structure;water_drought;radiation_light;terrain_spatial                | False     |

Elapsed minutes: 1.55
