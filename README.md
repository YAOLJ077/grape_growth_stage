# Grape Growth Stage

面向欧洲葡萄物候研究的数据处理与分析仓库。项目整合 France TEMPO、
Germany DWD 和 PEP725 的葡萄物候观测，将来源特异的阶段统一到标准
BBCH，并准备 1951 年以来可用于物候—气候建模的站点事件、ERA5-Land
逐日天气和 Copernicus DEM 地形数据。

当前仓库覆盖法国、德国、奥地利、瑞士、斯洛伐克和西班牙。它侧重数据
获取、标准化、质量审计、描述性分析和模型输入准备；尚不包含预测模型。

## 数据流水线

```text
TEMPO / DWD / PEP725 raw observations
                    |
                    v
source-specific standardized tables
                    |
                    v
six-country standardized BBCH layer
                    |
                    v
1951+ observation-level base table
                    |
                    v
site x year x BBCH event table
                    |
                    v
GEE weather index and ERA5-Land daily exports
                    |
                    v
coordinate repair and France buffer fill
```

核心脚本按执行顺序排列如下：

1. `src/download_grape_phenology.py`：下载 France TEMPO 和 Germany DWD
   公共物候数据。
2. `src/standardize_grape_phenology.py`：标准化法国和德国数据。
3. `src/standardize_pep725_selected_countries.py`：筛选并标准化 PEP725
   中的四个扩展国家。
4. `src/standardize_bbch_analysis_layer.py`：构建六国标准 BBCH 分析层。
5. `src/base_table/build_base_table.py`：生成 1951+ 观测级基表。
6. `src/base_table/build_site_topography.py`：从本地 Copernicus GLO-30
   瓦片为全部 1951+ 建模站点提取统一高程、坡度和坡向。
7. `src/base_table/build_model_ready_tables.py`：生成简化观测表和
   `site x year x BBCH` 事件表。
8. `src/base_table/build_weather_download_index.py`：生成站点—年份天气
   提取索引。
9. `src/base_table/build_gee_weather_index.py`：将索引确定性拆分为 20 个
   GEE 导出分区。
10. `src/weather_processing/repair_gee_weather_exports.py` 和
   `src/weather_processing/merge_france_buffer_fill.py`：修复导出结果并
   合并法国沿海、岛屿站点的缓冲区天气补值。
11. `src/base_table/build_site_era5_grid_crosswalk.py`：建立站点与官方
    ERA5-Land 0.1° 网格的对应关系；读取 ECMWF 位势高度作为模型格点
    高程，并独立聚合 GLO-30 以刻画亚格点地形异质性。
12. `src/weather_processing/prepare_model_ready_weather.py`：转换逐日天气
    单位、保留来源层并生成站点—年份完整性和物理范围审计。

GEE 提取仍包含人工步骤，具体脚本和说明见
`data/gee/gee_era5_download_script.md`。

## 目录结构

```text
data/
  phenology/   原始、标准化和派生物候数据
  gee/         GEE 天气提取索引与导出脚本
  weather/     ERA5-Land 逐日天气及修复结果
  topography/  Copernicus DEM 元数据和派生地形数据
fig/           描述性统计和空间分布图
note/          BBCH 标准化规则与分析报告
reference/     文献库
src/           数据流水线和绘图代码
tests/         不依赖完整数据集的单元测试
```

更详细的数据产品说明见 `data/README.md`，BBCH 映射规则见
`note/bbch_standardization_rules.md`。

## 环境安装

建议使用 Python 3.10 或更高版本，并在独立虚拟环境中安装依赖：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

开发和测试环境：

```bash
python -m pip install -r requirements-dev.txt
pytest
```

Cartopy、Rasterio 和 Shapely 带有地理空间二进制依赖。在部分平台上，
使用 conda-forge 安装这些包会更方便。

## 重建核心表

以下命令假定原始来源文件已经位于 `data/phenology/raw/`：

```bash
python src/standardize_grape_phenology.py
python src/standardize_pep725_selected_countries.py
python src/standardize_bbch_analysis_layer.py
python src/base_table/build_base_table.py
python src/base_table/build_site_topography.py
python src/base_table/build_model_ready_tables.py
python src/base_table/build_weather_download_index.py
python src/base_table/build_gee_weather_index.py
python src/base_table/build_site_era5_grid_crosswalk.py
python src/weather_processing/prepare_model_ready_weather.py
python src/base_table/report_environment_preprocessing.py
python src/base_table/build_france_germany_four_stage_dataset.py
python src/descriptive_phenology/plot_france_germany_four_stage_sites.py
python src/descriptive_phenology/plot_france_germany_four_stage_dem_overlap.py
```

France TEMPO 的统一来源海拔优先使用自报 `altitude`，缺失时回填
`altitudeIgn`，并通过 `altitude_source` 保留来源。跨国家地形建模应统一
使用 `site_topography.csv` 中的 Copernicus `dem_elevation_m`。

天气索引默认从物候年份前一年的 9 月 1 日覆盖至物候年份的 12 月 31 日，
以支持冬季冷量和当年强迫量特征构建。

`era5_land_daily_complete/` 保留 GEE 来源单位；后续分析优先读取
`era5_land_daily_model_ready/` 中的摄氏度、毫米、kPa 和 MJ m-2 day-1
版本。地形温度订正尚未施加，Copernicus 站点 DEM 与 ERA5 官方格点
位势高度之差保存在
`data/topography/processed/site_era5_land_grid_crosswalk.csv`，供模型阶段
进行原始与订正温度的公平比较。

## 描述性分析

六国描述性图表可通过以下命令重建：

```bash
python src/descriptive_phenology/plot_descriptive_phenology_six_countries.py
python src/plot_phenology_sites_by_source_with_pep725.py
python src/plot_phenology_sites_dem_overlap.py
```

这些六国地图默认仅使用 1951 年及以后的观测站点，与建模研究期一致；如需
敏感性分析，可通过 `--start-year` 显式修改起始年份。DEM 是静态地形背景，
不按年份裁剪，但所有由站点位置驱动的 DEM 瓦片选择均采用相同的起始年份。

旧的 France/Germany 双国绘图脚本仍保留，用于复核早期分析结果；当前
建模流水线以六国标准 BBCH 表为准。

France–Germany 四阶段候选研究使用精确 BBCH 07、65、81、89，派生数据位于
`data/phenology/derived/modeling/france_germany_four_stage/`。对应双面板站点图为
`fig/phenology_distribution/france_germany_four_stage_site_distribution.pdf`。
同一批建模站点的 GLO-30 DEM 叠加版本为
`fig/phenology_distribution/france_germany_four_stage_site_distribution_dem_overlap.pdf`。

## 大文件与 Git LFS

大型物候表和完整天气分片由 Git LFS 管理。克隆仓库前请安装 Git LFS：

```bash
git lfs install
git clone <repository-url>
```

Copernicus DEM 原始瓦片位于 `data/topography/raw/`，默认不进入 Git
历史，需要通过下载脚本重新获取。

## 数据使用注意事项

- 跨来源分析应使用 `bbch_standard` 和 `phenophase_standard`，不要直接
  比较来源特异的 `stage_id`。
- France 历史跨度很长，但早期记录与现代观测网络可能并不同质。
- France 的来源海拔中包含大量 0 值，地形分析应优先使用 DEM 派生海拔。
- PEP725 扩展国家的阶段覆盖和样本量不均，应按国家和 BBCH 分层建模。
- 映射置信度与具体依据保存在 `bbch_mapping_confidence` 和
  `bbch_mapping_note` 中。
