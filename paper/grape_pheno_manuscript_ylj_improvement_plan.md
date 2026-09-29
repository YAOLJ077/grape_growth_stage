# 葡萄物候稿件批注与改进计划

　　源文件：[grape_pheno_manuscript_ylj.docx](grape_pheno_manuscript_ylj.docx)。计划基准日期：2026-09-28。范围包括 Word 中全部 26 条批注、批注对应正文，以及本轮对研究定位、题目、摘要和 CRediT 声明的明确要求。

## 1. 研究定位与修改边界

　　研究主线为：比较十种过程模型结构，识别适合区域葡萄物候预测的结构；进一步评估地形温度校正和新设计的残差模型能否提高预测精度。结构评价是基础，温度输入和残差建模是进一步改进途径。

　　实际试验在全部十种结构上交叉评价温度处理与残差学习。叙述上的递进关系不等于先筛选一个模型、再只对该模型实施校正。最低过程模型 MAE 与最低混合模型 MAE 对应的结构也不必相同。

　　当前题目已确定为：**Beyond thermal accumulation: selecting process structures and learning residual errors for regional grapevine phenology prediction**。

　　区域预测的证据范围为已覆盖温度环境内的站点组留出和基于实况天气的回顾性估计。结构优劣受固定响应函数和校准约束限定；物候精度提高不直接证明局地温度更准确、机制已被识别或管理收益已经实现。新设计的残差模型贡献应落实到过程状态、环境信息和残差校正的具体设计，避免将已有 TabM 架构称为原创架构。

## 2. 批注清点与修订状态

| 原始批注作者 | 条数 |
| --- | ---: |
| Xuefei Wang | 7 |
| 林超 李 | 9 |
| bin chen | 10 |
| 合计 | **26** |

| 内容处理状态 | 条数 | 批注 ID |
| --- | ---: | --- |
| 正文或图件已落实，待批注人复核 | 25 | 2、3、4、6、7、8、9、10、11、13、15、16、17、19、37、41、42、43、45、48、50、54、55、57、58 |
| 作者明确不设置 Funding 节；CRediT 已补齐 | 1 | 63 |

　　以上状态依据 2026-09-28 修订稿正文与图件判断，不代表批注人已接受修订。Word 的 26 条批注均保留为未解决状态；批注扩展记录未列出回复层级。ID 为 Word 原始标识，编号不连续不表示漏读。部分锚点只覆盖词片段或图片，修改范围依据所在段落和章节判定。

　　定位采用当前 DOCX 正文顶层段落序号 P0001、P0002……，不计表格单元格中的段落，也不是 Word 页码或行号。后续增删段落后以章节、批注 ID 和锚定文字为优先定位依据。

## 3. 执行顺序与验收标准

### W01｜保留已确定的题目与摘要

**关联批注：2、3、4。优先级：已完成后的复核。**

- [x] 摘要先说明物候的重要性，再提出区域预测中过程结构适用性与格点温度代表性的限制。
- [x] 突出结构筛选、新设计的残差模型及进一步精度改进，明确葡萄研究对象。
- [x] 结尾集中于模型选择、预测精度及校正收益不能简单相加。
- [x] 全文改写完成后复核摘要与方法、结果和结论的一致性；具体数字、样本口径和推断边界保持对应。

　　验收标准：摘要中存在明确的研究问题、结构评价结果、进一步改进结果和模型层面的结论；不将区域覆盖误写为独立区域迁移验证。

### W02｜重组引言，强化区域预测的两个瓶颈

**关联批注：6、7、8、9、10、11。优先级：高。依赖：W01 的研究定位。**

- [x] 开篇先建立物候对发育时序和环境暴露的意义，再引出预测需求；霜冻、水分和管理作为背景例子。
- [x] 将引言组织为“物候意义与区域需求—过程结构选择—温度代表性与 DEM 校正—残差模型及联合评价缺口—研究目标与验证范围”。
- [x] 将现有 DEM 段落前移至残差学习段落之前，使校正途径与摘要中的顺序一致。
- [x] 明确 DEM 对应站点与格点高程差引起的温度代表性问题；残差模型对应共享过程阈值之外仍可预测的系统误差。
- [x] 将 “Later development” 明确为 veraison 和 maturity/harvest，并区分生物过程异质性、管理影响与观测终点差异。
- [x] 缩短品种和管理背景；如保留，以发育时序差异及模型泛化需求建立衔接。
- [x] 目标段明确：识别表现最好的过程结构，并在全部结构上检验 DEM 与残差模型的额外收益。
- [x] 将预测场景直接表述为已覆盖温度环境内未参与拟合站点的回顾性估计；验证技术细节归入方法。

　　验收标准：读者在引言结束时能分别回答“为什么比较结构”“为什么修正温度”“为什么需要残差模型”“在哪种预测场景下评价”。现有文献支持与模型设计贡献分别陈述。

### W03｜压缩方法，保留决定结果解释的细节

**关联批注：13、15。优先级：高。依赖：W02。**

- [x] 首次出现时同时给出阶段名称与代码：budburst（BBCH07）、flowering（BBCH65）、veraison（BBCH81）、maturity/harvest（BBCH89）。无需仅为定义缩写而将含筛查窗口的整张表强行前移。
- [x] §2.1 用简短概述说明数据、十种结构、两种温度输入、残差模型及分组验证，不逐项复述 Fig. 1。
- [x] 将历史数据版本、记录匹配实现、重复的筛查说明、优化重试设置和逐折训练细节集中至补充材料，并设置准确交叉引用。
- [x] 主文保留结构定义、固定与拟合参数的区别、DEM 公式及分别重校准、残差目标和特征、分组与防泄漏原则、评分截止日、权重及不确定性方法。
- [x] 单独明确残差模型的新设计贡献及其与基础回归架构的关系；避免将核心创新与普通训练参数混在同一长段。

　　验收标准：主文足以理解比较设计和结果含义，补充材料足以追溯实现；压缩不删除独立性、校准约束、行政评分日期或模型未到达状态的说明。

### W04｜简化流程图并补足地图方向信息

**关联批注：16、17、19。优先级：中。依赖：W03 的方法层次。**

- [x] Fig. 1 以“数据与温度输入—过程结构评价—DEM/残差改进—分组验证与误差比较”表达研究关系，用明确箭头连接。
- [x] 图中保留十种结构、两种温度输入和有/无残差学习的全交叉设计；不画成只校正被选中模型的单一路径。
- [x] 移除完整超参数、重复模型代码和过细校准步骤；参数细节放入方法或补充材料，图注仅承担必要解释。
- [x] 增大主要标签字号，统一字体与线条，在稿件最终插图尺寸下检查可读性。
- [x] 若 Fig. 1 改为单一流程图，可取消无必要的 (a)–(e) 标签；若仍为多面板图，可保留标准面板编号。批注中的编号建议不作为通用禁令。
- [x] Fig. 2 添加与投影一致的指北标识，并保留比例尺和经纬度信息；确保没有遮挡数据点、图例或标注。

　　验收标准：流程图无需逐字阅读即可辨识结构评价与进一步改进的关系；图、图注和方法中的配置数量一致；地图方向标识准确。

### W05｜结果聚焦“最佳结构—额外收益—剩余误差”

**关联批注：37。优先级：高。依赖：W02 的问题顺序。**

- [x] 每个结果小节先给主要发现，再给关键数值及必要环境差异。
- [x] §3.4 保留 DEM 总体收益、最有解释价值的阶段或地形差异、局地退化现象及关键稳健性结果。
- [x] 将重复的分组界限、统计定义及缺乏充分支持的区域变异函数细节移至图注或补充材料。
- [x] 明确 11.31 天是模型自身有限评分样本上的最佳 RAW 过程 MAE；11.27 天是该模型在共同配对样本上的 MAE，不混用口径。
- [x] 保留残差学习后的最终误差和模型间误差范围，避免仅比较“改进了多少天”。

　　验收标准：结果叙述与图表互补，不逐项复述全部数值；结构排名、配对增益、最终混合模型精度的口径清楚。

### W06｜重构讨论，回答 DEM 与残差模型的科学问题

**关联批注：41、42、43、45、48、50、54、55。优先级：高。依赖：W05。**

- [x] 讨论首段集中阐明：结构筛选建立预测基础，进一步改进仍然必要，而改进之间存在收益重叠。
- [x] 将七个小节整合为四个主题：结构选择及阶段差异；DEM 何时有帮助；残差模型如何改善预测及其与 DEM 的关系；适用边界与验证重点。
- [x] 结构讨论保留少量直接支持或对照当前结果的文献，解释温度范围、品种组成、固定响应参数及校准条件造成的差异。
- [x] DEM 讨论区分过程模型的 1.06 天收益和混合模型的 0.12 天额外收益，正面回答“为什么仍评价 DEM”；结论不要求所有应用都叠加 DEM。
- [x] 将旧 §4.3 “Asymmetric benefits of elevation correction” 的标题改得更清楚。候选：**When elevation correction improves phenology prediction**。此任务对应批注 48，与已选定的论文总题目不同。
- [x] 残差解释按“过程日期与阶段持续时间—近期天气—光周期与地形”说明输入信息与可预测误差的关系；明确残差目标来自未参与对应过程拟合的观测。
- [x] 区分预测证据和机制假设：误差下降证明条件预测信息有用，但不能识别强迫、品种、管理或生理机制的独立贡献。
- [ ] 可选后续研究（本轮未开展）：如需进一步支撑机制解释，可补充去除地形、去除近期天气和仅保留过程状态的消融试验。这是可选新增分析，现有结果不能替代其证据，也不预设其结果。
- [x] 合并重复限制，将研究范围、数据异质性和验证边界各集中说明一次。
- [x] 保留影响推断的实质限制：固定参数与校准约束、地理及终点不均衡、11 月 4 日评分规则、实况天气的信息时点、初步结果后修订筛查，以及缺乏完全未接触的独立开发外验证。

　　验收标准：讨论直接解释本研究发现；DEM 的增量价值及残差模型的信息来源清晰；压缩文字不扩大因果、迁移或业务收益主张。

### W07｜结论压缩为研究任务、关键发现与适用意义

**关联批注：57、58。优先级：中。依赖：W05、W06。**

- [x] 首句同时交代区域葡萄物候、结构筛选与进一步校正，并使用 11 个国家或 3,169 个站点说明研究覆盖。
- [x] 保留最佳过程结构、DEM 与残差学习的代表性收益，以及联合收益不能简单相加的发现。
- [x] 将现有三段压缩为一至两段，避免再次展开文献、全部数值范围和独立验证清单。
- [x] 区分区域覆盖与测试支持：如数字描述测试集，应采用 635 个测试站点及相应测试国家数，不将总样本数字当作测试样本。

　　验收标准：结论与摘要研究定位一致，包含可核对的发现，保留一处必要适用范围说明。

### W08｜补齐声明与作者事实

**关联批注：63；另含会话明确要求的 CRediT 声明。优先级：投稿前必需。依赖：作者事实信息。**

- [x] 作者明确表示无需列出资助信息，因此不设置 Funding 节；CRediT 中保留已确认的 Funding acquisition 贡献。
- [x] 按全部十位作者的实际贡献填写 CRediT。Linjia Yao、Gang Zhao、Qiang Yu 及其余七位作者的角色均依据作者提供的信息填写。
- [x] Data availability 列明原始数据提供方及许可条件，保留按请求提供支持数据的声明；未声明代码已有公开仓库。
- [x] 复核利益冲突、致谢和补充材料说明是否完整，所陈述内容是否真实。

　　作者贡献已确认。资助信息不单列。公开代码仓库或分析结果存档位置尚未提供，稿件未作相应公开声明。

## 4. 修订前篇幅基线与文献控制

| 内容 | 修订前约计英文词数 | 压缩重点 |
| --- | ---: | --- |
| 引言 | 977 | 重复背景、跳跃的品种管理段及验证细节 |
| 方法，含图表标题 | 5,095 | 历史流程、实施细节及重复统计定义 |
| 结果，含图注 | 2,989 | 图表数值复述和支持不足的细分结果 |
| 讨论，含小节标题 | 3,112 | 跨作物文献铺陈、重复结果和重复限制 |
| 结论 | 252 | 多次重述边界和过长的未来工作列表 |

　　词数按 DOCX 正文文本的空白分隔近似统计，不含表格单元格和公式对象，不属于期刊限字判定。优先消除重复并保证逻辑完整，不以固定删减比例替代内容判断。

　　涉及引言和讨论的引用调整遵守既定文献范围：不使用 MDPI 或 Frontiers 旗下期刊论文；其他期刊论文须符合 Nature、Science 主刊及子刊或相关学科公认专业顶刊的范围。已有 Frontiers 条目需在修改相应论点时一并处理。新文献须先核实来源资格与直接支持关系；证据不足时收窄论点。上述要求属于项目约束，不计入 26 条原始批注。

## 5. 交付与核验清单

- [x] 每条批注均有正文、图件或声明中的对应处理结果；原始 ID 保持可追踪。
- [x] 保留当前已确定的总题目和摘要主线；与引言目标、流程图、讨论及结论一致。
- [x] 检查十种结构、两种温度输入、有/无残差学习及四个阶段的数量关系。
- [x] 检查所有引用、表号、图号、补充材料编号及首次出现的缩写。
- [x] 检查总样本、测试样本和共同配对样本，以及模型自身样本与共同样本的数值口径。
- [x] 检查最终 Word 中图件可读性、公式、批注锚点和参考文献格式。
- [x] CRediT 已按确认信息补齐；Funding 节依作者明确意见省略。
- [x] 批注的“内容已落实”与 Word 的“已解决”状态分别记录；不以措辞变化自动代表批注人认可。

## 6. 原始批注逐条登记（修订前快照）

　　以下保留修订前全部批注原文、作者、时间、位置、基线状态和对应处理要求；当前完成状态见第 2 节。锚点摘录用于定位，过长内容仅显示开头；图片批注以图号定位。时间采用原始记录的 UTC 时间。

### C02｜Abstract

- **原始 ID：** 2
- **作者：** Xuefei Wang
- **时间：** 2026-09-16T14:55:00Z
- **位置：** P0012；Abstract
- **当前锚点：** Grapevine phenology shapes the seasonal conditions experienced during growth and ripening, providing a basis for assessing environmental exposure and supporting vineyard management. However, regional …［摘录］
- **内容状态：** 已落实，保留复核
- **对应任务：** W01

**批注原文：**

> 最开始可以说生育期的重要性，之后再说预测的重要性

　　**处理要求：** 当前摘要以葡萄物候对生长、成熟和环境暴露的意义开篇，随后提出结构与温度输入的预测限制。保留这一顺序，后续仅做全文一致性复核。

### C03｜Abstract

- **原始 ID：** 3
- **作者：** 林超 李
- **时间：** 2026-09-16T16:20:00Z
- **位置：** P0012；Abstract
- **当前锚点：** These results support selecting a suitable process structure as the foundation for regional grapevine phenology estimation and evaluating terrain correction and residual modelling for additional gains…［摘录］
- **内容状态：** 已落实，保留复核
- **对应任务：** W01

**批注原文：**

> The Abstract would benefit from a clear concluding sentence summarizing the main findings.

　　**处理要求：** 摘要末尾已概括结构选择、进一步改进及收益不能简单相加。结尾内容与本轮明确的研究主线一致。

### C04｜Abstract

- **原始 ID：** 4
- **作者：** bin chen
- **时间：** 2026-09-24T22:44:00Z
- **位置：** P0012；Abstract
- **当前锚点：** Their benefits require joint assessment because improvements from individual corrections are not simply additive within the sampled environments.
- **内容状态：** 已落实，保留复核
- **对应任务：** W01

**批注原文：**

> 限制在改进模型本身的意义就可以了

　　**处理要求：** 摘要结尾已限定于模型选择和预测增益。开头的管理意义属于研究背景，不应扩展为本研究已验证的管理效益。

### C06｜1 Introduction

- **原始 ID：** 6
- **作者：** bin chen
- **时间：** 2026-09-24T23:23:00Z
- **位置：** P0014；1 Introduction
- **当前锚点：** Introduction
- **内容状态：** 部分落实
- **对应任务：** W02

**批注原文：**

> 有几个问题，引言可能需要加强：1. 为什么做dem修正温度， 2. 为啥要使用残差学习，

　　**处理要求：** 现有引言已经分别解释 DEM 和残差学习，但残差与验证段先于温度输入段，削弱研究递进。按结构选择、温度代表性、残差模型和联合评价缺口重排，并明确新模型的具体设计贡献。

### C07｜1 Introduction

- **原始 ID：** 7
- **作者：** 林超 李
- **时间：** 2026-09-16T16:26:00Z
- **位置：** P0015；1 Introduction
- **当前锚点：** Grapevine phenology determines when vegetative growth, flowering and fruit ripening encounter seasonal weather, connecting temperature variability with frost exposure, water demand and vineyard operat…［摘录］
- **内容状态：** 待修改
- **对应任务：** W02

**批注原文：**

> The opening sentence could provide a broader background on the importance of grapevine phenology before moving to specific links with frost exposure, water demand, and vineyard operations.

　　**处理要求：** 当前引言首句仍直接列举霜冻、水分和操作。先建立葡萄物候对发育与季节环境关系的总体意义，再引入这些具体例子。摘要已改写不能替代引言首段的处理。

### C08｜1 Introduction

- **原始 ID：** 8
- **作者：** 林超 李
- **时间：** 2026-09-16T16:28:00Z
- **位置：** P0015；1 Introduction
- **当前锚点：** The consequences depend on the stage: frost risk reflects the timing of susceptible buds relative to freezing events, whereas earlier ripening changes the thermal and moisture conditions experienced b…［摘录］
- **内容状态：** 部分落实
- **对应任务：** W02

**批注原文：**

> Please clarify that frost exposure and ripening conditions are examples of stage-specific environmental consequences of phenological shifts, rather than direct research targets of this study. 

　　**处理要求：** 引言末段及讨论已限定预测用途，但首段未直接区分背景例子与本研究评价终点。使语义明确：霜冻和成熟环境说明物候意义，本研究评价阶段日期误差。

### C09｜1 Introduction

- **原始 ID：** 9
- **作者：** 林超 李
- **时间：** 2026-09-16T16:28:00Z
- **位置：** P0015；1 Introduction
- **当前锚点：** Cultivar diversity and managem
- **内容状态：** 待修改
- **对应任务：** W02

**批注原文：**

> The transition from stage-specific environmental consequences to cultivar diversity and management is somewhat abrupt. 

　　**处理要求：** 锚点仅覆盖 cultivar diversity and management 的词片段。修改范围是环境后果到品种与管理的过渡：增加发育时序异质性的逻辑连接，或删去不服务区域预测问题的背景。

### C10｜1 Introduction

- **原始 ID：** 10
- **作者：** 林超 李
- **时间：** 2026-09-16T16:32:00Z
- **位置：** P0016；1 Introduction
- **当前锚点：** Later development involves additional uncertainty.
- **内容状态：** 部分落实
- **对应任务：** W02

**批注原文：**

> Too vague. Please specify which phenological stages are meant and what sources of uncertainty are being referred to.

　　**处理要求：** 后续句已涉及源库关系、水分和管理，但被批注句仍使用 Later development 和 additional uncertainty。直接写明 veraison、maturity/harvest，并归纳生物、观测终点及管理的不确定性。

### C11｜1 Introduction

- **原始 ID：** 11
- **作者：** 林超 李
- **时间：** 2026-09-16T16:34:00Z
- **位置：** P0019；1 Introduction
- **当前锚点：** Holding out independent site groups within represented temperature regimes tests a different application from extrapolation to unobserved regions or climates.
- **内容状态：** 部分落实
- **对应任务：** W02

**批注原文：**

> Please clarify what predictive setting is being evaluated here. 

　　**处理要求：** 引言末段和方法已明确站点组留出与回顾性估计。被批注处仍采用抽象的应用对照，改为直接定义本研究的预测场景，并将技术细节移至方法。

### C13｜2 Materials and methods

- **原始 ID：** 13
- **作者：** bin chen
- **时间：** 2026-09-24T23:11:00Z
- **位置：** P0022；2 Materials and methods
- **当前锚点：** 2 Materials and methods
- **内容状态：** 待修改
- **对应任务：** W03

**批注原文：**

> 感觉写的太长了 ，太多细节，看不到主线了

　　**处理要求：** 批注锚定方法总标题，适用于整节。压缩逐步操作和历史数据叙述，保留决定比较含义的结构、参数、训练独立性、截止日及权重规则；补充材料承接实现细节。

### C15｜2.1 Overall workflow

- **原始 ID：** 15
- **作者：** Xuefei Wang
- **时间：** 2026-09-18T20:24:00Z
- **位置：** P0024；2.1 Overall workflow
- **当前锚点：** BBCH07, BBCH65, BBCH81 and BBCH89
- **内容状态：** 待修改
- **对应任务：** W03

**批注原文：**

> 后面介绍BBCH的表格是否需要前移，这里对于不熟悉BBCH体系的人，看着比较懵

　　**处理要求：** 首次列出四个 BBCH 代码时即附阶段名称。定义表可调整，但不必把包含筛查窗口的整张表前移；全文保持 BBCH07 与其他萌芽代码、BBCH89 与纯生理成熟终点的区别。

### C16｜2.1 Overall workflow

- **原始 ID：** 16
- **作者：** bin chen
- **时间：** 2026-09-24T22:55:00Z
- **位置：** P0025；2.1 Overall workflow
- **当前锚点：** Fig. 1 图片（无文字锚点）
- **内容状态：** 待修改
- **对应任务：** W04

**批注原文：**

> 字有点小了，一般不用（a）(b),(c)这样标吧，缺少逻辑关系展示，稍微有点简陋，ai化

　　**处理要求：** 锚定 Fig. 1 图片。简化文字、增大字号、突出结构评价和进一步改进的逻辑连接。是否保留面板字母取决于最终图形结构，不将批注中的疑问当作期刊禁止使用面板编号的规定。

### C17｜2.1 Overall workflow

- **原始 ID：** 17
- **作者：** 林超 李
- **时间：** 2026-09-16T16:37:00Z
- **位置：** P0026；2.1 Overall workflow
- **当前锚点：** Fig. 1. Workflow underlying the grapevine phenology results. (a) Matched observation, weather and terrain cohort. (b) RAW and elevation-corrected temperatures. (c) Fully crossed process structures, te…［摘录］
- **内容状态：** 待修改
- **对应任务：** W04

**批注原文：**

> Please consider shortening the text, using icons or simple visual cues where appropriate, and retaining only the key steps in the figure itself. Some methodological details could be moved to the caption so that the figure functions more clearly as a schematic overview.

　　**处理要求：** 锚点位于 Fig. 1 图注开头，意见主要针对流程图的信息密度。与批注 16 合并处理；关键步骤放图内，必要解释放图注，详细实现放方法或补充材料。

### C19｜2.2 Study area

- **原始 ID：** 19
- **作者：** bin chen
- **时间：** 2026-09-24T22:59:00Z
- **位置：** P0029；2.2 Study area
- **当前锚点：** Fig. 2 图片（无文字锚点）
- **内容状态：** 待修改
- **对应任务：** W04

**批注原文：**

> 指北针

　　**处理要求：** 锚定 Fig. 2 图片。增加符合地图投影和局地方向的指北标识，并检查比例尺、经纬度和图例布局。

### C37｜3.4 Benefits and terrain dependence of elevation correction

- **原始 ID：** 37
- **作者：** bin chen
- **时间：** 2026-09-24T23:14:00Z
- **位置：** P0126；3.4 Benefits and terrain dependence of elevation correction
- **当前锚点：** correction
- **内容状态：** 待修改
- **对应任务：** W05

**批注原文：**

> 建议删减一些，结果描述太长了

　　**处理要求：** 直接锚点为 §3.4 标题末词，首先压缩 DEM 结果；同类数值堆叠可在其他结果小节同步清理。保留主要收益、关键异质性与必要稳健性说明。

### C41｜4 Discussion

- **原始 ID：** 41
- **作者：** 林超 李
- **时间：** 2026-09-16T16:47:00Z
- **位置：** P0147；4 Discussion
- **当前锚点：** 4 Discussion
- **内容状态：** 待修改
- **对应任务：** W06

**批注原文：**

> The discussion is too long. Please consider condensing the literature comparisons and placing greater emphasis on how previous evidence directly supports or contrasts with the current results.

　　**处理要求：** 批注覆盖讨论整体。围绕当前发现重组讨论，减少独立展开的文献综述和重复限制；前人研究只用于解释一致性、分歧及其可能条件。

### C42｜4 Discussion

- **原始 ID：** 42
- **作者：** Xuefei Wang
- **时间：** 2026-09-18T20:32:00Z
- **位置：** P0148；4 Discussion
- **当前锚点：** Process formulation, temperature input, and residual learning made different contributions to grapevine phenology prediction.
- **内容状态：** 待修改
- **对应任务：** W06

**批注原文：**

> 这个开头不够有力

　　**处理要求：** 现有开头仅说三类因素作出不同贡献，信息力度不足。首段明确最佳过程结构的基础作用、残差模型进一步降低误差，以及 DEM 在混合模型中的有限增量价值。

### C43｜4 Discussion

- **原始 ID：** 43
- **作者：** bin chen
- **时间：** 2026-09-24T23:16:00Z
- **位置：** P0148；4 Discussion
- **当前锚点：** . Residual learning yielded larger gains, and DEM correction added little to average hybrid accuracy
- **内容状态：** 部分落实
- **对应任务：** W06

**批注原文：**

> 如果dem贡献很少，为什么还要加呢

　　**处理要求：** §4.4 已有 1.06 天与 0.12 天及其差值的解释，但讨论首段未突出二者所处工作流不同。说明 DEM 对过程模型有实测预测收益；在混合模型中增量较小是需要联合评价的发现，不要求所有情景都叠加 DEM。

### C45｜4.1 Predictive value of process structure

- **原始 ID：** 45
- **作者：** 林超 李
- **时间：** 2026-09-16T16:46:00Z
- **位置：** P0151；4.1 Predictive value of process structure
- **当前锚点：** The favourable performance of simpler forcing agrees with the limited benefits of increasing complexity reported by Fila et al. (2014), but does not establish a universally preferable temperature resp…［摘录］
- **内容状态：** 待修改
- **对应任务：** W06

**批注原文：**

> Please consider condensing these comparisons and focusing more directly on how they help interpret the present results.

　　**处理要求：** 当前 §4.1 罗列多项葡萄和实验研究。压缩为直接解释当前结构排序的证据对照，保留温度范围、品种和校准条件的差异，不以其他条件下结果否定或普遍化本研究。

### C48｜4.3 Asymmetric benefits of elevation correction

- **原始 ID：** 48
- **作者：** Xuefei Wang
- **时间：** 2026-09-18T20:34:00Z
- **位置：** P0157；4.3 Asymmetric benefits of elevation correction
- **当前锚点：** correction
- **内容状态：** 待修改
- **对应任务：** W06

**批注原文：**

> 标题还可优化

　　**处理要求：** 锚点对应 §4.3 Asymmetric benefits of elevation correction 的 correction，指讨论小节标题，不是论文总题目。重构讨论时改为更直接表达 DEM 适用条件的标题；总题目已确定不等于此批注已解决。

### C50｜4.4 Residual learning and its overlap with temperature correction

- **原始 ID：** 50
- **作者：** bin chen
- **时间：** 2026-09-24T23:27:00Z
- **位置：** P0161；4.4 Residual learning and its overlap with temperature correction
- **当前锚点：** correction
- **内容状态：** 部分落实
- **对应任务：** W06

**批注原文：**

> 如何解释残差模型学习的结果，为什么它能学习到这个残差

　　**处理要求：** §4.4 已说明过程日期、天气、地形和光周期可包含剩余预测信息，但尚缺少紧密的“特征—条件残差—预测改进”解释。按信息来源重写，突出残差模型设计；消融可作为新增证据，不能把未验证解释写成识别出的机制。

### C54｜4.7 Limitations and priorities for independent validation

- **原始 ID：** 54
- **作者：** bin chen
- **时间：** 2026-09-24T23:18:00Z
- **位置：** P0176；4.7 Limitations and priorities for independent validation
- **当前锚点：** Limitations and priorities for independent validation
- **内容状态：** 待修改
- **对应任务：** W06

**批注原文：**

> 写的太多了，让人感觉好多limitation

　　**处理要求：** 合并散见各段的重复限制，保留实质影响推断的条件。不因篇幅和语气要求删除测试后筛查修订、行政评分日期、回顾性天气输入或样本不均衡。

### C55｜4.7 Limitations and priorities for independent validation

- **原始 ID：** 55
- **作者：** Xuefei Wang
- **时间：** 2026-09-18T20:36:00Z
- **位置：** P0176；4.7 Limitations and priorities for independent validation
- **当前锚点：** validation
- **内容状态：** 待修改
- **对应任务：** W06

**批注原文：**

> 讨论分标题可以再少点。

　　**处理要求：** 现有讨论七个小节可合并为四个主题。将阶段差异和环境区差异融入结构、DEM 和残差讨论；应用意义与限制合并为集中段落。

### C58｜5 Conclusions

- **原始 ID：** 58
- **作者：** Xuefei Wang
- **时间：** 2026-09-18T20:37:00Z
- **位置：** P0181；5 Conclusions
- **当前锚点：** the evaluated European monitoring sites,
- **内容状态：** 待修改
- **对应任务：** W07

**批注原文：**

> 是否可以写国家或者监测点数字
> 
> 结论稍有点长。应更强调亮点和干货

　　**处理要求：** 该批注包含两项要求：增加国家或站点数字，并压缩结论、突出核心发现。两项分别验收；总研究覆盖可用 11 国或 3,169 站点，不与测试样本口径混淆。

### C57｜5 Conclusions

- **原始 ID：** 57
- **作者：** bin chen
- **时间：** 2026-09-24T23:19:00Z
- **位置：** P0181；5 Conclusions
- **当前锚点：** Across the evaluated European monitoring sites, grapevine phenology accuracy depended on process structure, temperature representativeness and systematic residual errors.
- **内容状态：** 待修改
- **对应任务：** W07

**批注原文：**

> 结论第一句一般总结文章思路，干了啥吧

　　**处理要求：** 结论首句目前直接概括影响因素，未明确研究任务。改为区域葡萄物候的结构评价与进一步校正这一完整任务，避免空泛的文章过程叙述。

### C63｜Data availability

- **原始 ID：** 63
- **作者：** Xuefei Wang
- **时间：** 2026-09-18T20:38:00Z
- **位置：** P0190；Data availability
- **当前锚点：** request
- **内容状态：** 待作者信息
- **对应任务：** W08

**批注原文：**

> 缺少funding等部分

　　**处理要求：** 批注锚点是 Data availability 的 request，但内容要求补齐 funding 等声明。资助来源和编号需要作者真实信息；会话另已要求 CRediT，当前为空标题，须在取得实际贡献后填写。

## 7. 源文件指纹

　　源 DOCX 的 SHA-256：`c631a585b4eb808cf9db6bc526999c29c23f96587224bac7f670f47e487ddbd4`。该指纹标识本计划的批注与正文快照；后续修订以保留的批注 ID 及相应章节重新定位。


## 8. 修订交付与核验记录

　　修订稿保留已确认的题目和摘要文字。引言调整为结构选择、温度代表性和残差模型的递进关系；方法压缩实现细节；讨论由七个小节整合为四个主题；结论压缩为两段。十种结构的全交叉设计、分组验证、评分日期及推断边界保留。

　　Fig. 1 为简化流程图，取消原面板字母；Fig. 2 新增与 Lambert 投影一致的指北标识。图文摘要以结构比较为起点，两条校正路径覆盖全部十种结构，阶段标签位于图标上方，底部无解释性文字。图文摘要以独立 PNG、TIFF、SVG 和 PDF 文件交付。

　　CRediT 包含全部十位作者的已确认贡献。Funding 节依作者明确意见省略。数据可用性声明保留提供方访问与许可条件。Frontiers 文献及未引用条目已移除，DWD 和 PEP725 数据来源采用官方数据提供方条目。

　　Microsoft Word 原生导出预览共 43 页。43 个可编辑数学对象、4 张表格、26 条批注及其元数据均保留；10 张嵌入图中仅替换 Fig. 1 和 Fig. 2。46 个引用域结构完整，关联 34 个参考条目。批注内容处理完成不代表批注人已接受，Word 批注仍为未解决状态。

　　可选消融分析、独立区域迁移验证和业务预报验证未开展，正文将其保留为证据边界与后续研究方向。

　　修订 DOCX 的 SHA-256：`dd330b5c7602b0731e5fa8cccf412c0050b72ed0326ead4e8c151fe6bf1963f9`。
