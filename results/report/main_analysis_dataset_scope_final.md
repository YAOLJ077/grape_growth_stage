# 主分析数据口径固定说明

## 固定主分析口径

本文主分析数据集固定为：法国 TEMPO 与德国 DWD 物候数据，1951--2026 年，覆盖 BBCH07、BBCH65、BBCH81 和 BBCH89 四个阶段。

| 项目 | 数量 |
|---|---:|
| 站点 | 707 |
| 站点—年份 | 12,209 |
| 物候事件 | 23,170 |

该口径用于论文摘要、workflow、固定过程模型与固定混合模型对比、空间稳健性分析、机制组消融和 SHAP 解释。

## 阶段与国家构成

| 阶段 | France | Germany | 合计 |
|---|---:|---:|---:|
| BBCH07 萌芽 | 396 | 3,250 | 3,646 |
| BBCH65 开花 | 433 | 3,855 | 4,288 |
| BBCH81 转色 | 711 | 3,614 | 4,325 |
| BBCH89 成熟/采收 | 1,672 | 9,239 | 10,911 |
| 合计 | 3,212 | 19,958 | 23,170 |

## 时空范围

| 项目 | 范围 |
|---|---|
| 年份 | 1951--2026 |
| 纬度 | 42.52--53.77°N |
| 经度 | -1.35--14.95°E |

## 口径分层

| 口径 | 站点 | 站点—年份 | 事件 | 用途 |
|---|---:|---:|---:|---|
| 上游空间验证基础库 | 2,324 | 17,172 | 31,439 | 数据来源、空间阻断设计和样本审计 |
| 残差基础表 | 707 | 12,625 | 23,671 | 过程模型残差生成与质量控制 |
| 最终主分析数据集 | 707 | 12,209 | 23,170 | 论文主结果和摘要/workflow 口径 |

501 条 BBCH89 记录未进入最终主分析数据集，主要原因是对应过程模型未能生成有效预测日期，因而无法形成可用于残差学习的完整记录。后续论文文字中若未特别说明，数据规模均采用最终主分析数据集口径。

## 固定结果来源

| 内容 | 固定文件 |
|---|---|
| 主分析数据规模 | `results/paper_results/main_analysis_dataset_scope.csv` |
| 数据口径分层 | `results/paper_results/main_analysis_dataset_scope_hierarchy.csv` |
| 固定混合模型汇总 | `results/paper_results/main_final_stage_result_summary.csv` |
| 固定过程模型 1:1 图汇总 | `results/paper_results/selected_process_model_observed_predicted_summary.csv` |
| 固定混合模型 1:1 图汇总 | `results/paper_results/selected_hybrid_model_observed_predicted_summary.csv` |

