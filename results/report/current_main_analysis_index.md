# 当前主分析报告索引

整理日期：2026-08-11

## 1. 固定主文引用口径

- 主分析数据集：707 个站点、12,209 个站点—年份、23,170 条物候事件。
- 阶段范围：BBCH07、BBCH65、BBCH81、BBCH89。
- 年份范围：1951--2026。
- 空间范围：42.52--53.77°N，-1.35--14.95°E。
- 残差定义：`residual_days = observed_doy - mechanistic_predicted_doy`。
- 混合预测：`hybrid_doy = mechanistic_predicted_doy + predicted_residual_days`。
- 主数据 profile：`main_final`。
- 主模型筛选：阶段级固定算法；按训练区内层空间 CV 的平均 RMSE 最小规则确定。
- 主消融：机制组消融；其他探索性分析已归档，不作为论文主文口径。

## 2. 当前主线文件

| 用途 | 文件 |
|---|---|
| 主分析数据规模 | `results/paper_results/main_analysis_dataset_scope.csv` |
| 数据口径分层 | `results/paper_results/main_analysis_dataset_scope_hierarchy.csv` |
| 固定阶段混合模型主结果 | `results/report/main_final_fixed_stage_hybrid_results.md` |
| 固定阶段特征与结果摘要 | `results/report/main_final_fixed_feature_and_result_summary.md` |
| 固定阶段模型结果目录 | `results/france_germany_four_stage/residual_modeling/main_final_fixed_stage_models_refit/` |
| 当前残差 ML 数据 | `results/france_germany_four_stage/residual_machine_learning_main_final/` |
| 过程模型与残差 ML 详细方法 | `note/data_process/france_germany_process_and_residual_ml_methods_detailed.md` |
| 主分析数据口径说明 | `note/data_process/main_analysis_dataset_scope_final.md` |
| 机制组消融结果 | `results/report/main_final_mechanism_group_ablation_summary.md` |
| 机制组消融规则 | `note/residual_mechanism_group_ablation_rules.md` |

## 3. 主分析数据构成

| 阶段 | France | Germany | 合计 | 站点 | 站点—年份 |
|---|---:|---:|---:|---:|---:|
| BBCH07 萌芽 | 396 | 3,250 | 3,646 | 253 | 3,646 |
| BBCH65 开花 | 433 | 3,855 | 4,288 | 278 | 4,288 |
| BBCH81 转色 | 711 | 3,614 | 4,325 | 329 | 4,325 |
| BBCH89 成熟/采收 | 1,672 | 9,239 | 10,911 | 527 | 10,911 |
| 合计 | 3,212 | 19,958 | 23,170 | 707 | 12,209 |

## 4. 当前固定组合与结果

| 阶段 | 过程模型 | 固定残差模型 | 特征数 | 固定混合 MAE | 固定混合 RMSE | MAE 增益 | RMSE 增益 |
|---|---|---|---:|---:|---:|---:|---:|
| BBCH07 萌芽 | BRIN-Aug1 | Ridge | 11 | 6.187 | 8.346 | 0.611 | 1.217 |
| BBCH65 开花 | GFV | RF | 12 | 5.060 | 7.716 | 0.657 | 0.491 |
| BBCH81 转色 | GFV | Ridge | 12 | 11.819 | 14.592 | 0.548 | 0.893 |
| BBCH89 成熟/采收 | PV-GDD10 | RF | 11 | 8.156 | 10.559 | 19.622 | 19.942 |

## 5. 口径说明

- 旧版模型结果、探索性输出和未被当前 manuscript 引用的旧版结果图已清除，避免与主分析口径混淆。
- `note/data_process/france_germany_spatial_validation_and_model_foundation.md`：上游空间验证基础库说明，可用于 Methods 中解释空间阻断设计，不作为摘要或主结果数据规模。
- 若后续未特别说明，所有 Results、Abstract 和 workflow 均采用本索引第 1 节的主分析数据集口径。
