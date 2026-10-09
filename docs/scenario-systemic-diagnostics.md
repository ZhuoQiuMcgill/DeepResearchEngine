# 跨场景共同故障诊断

本轮优先寻找 DeepSeek 和 GPT 共同出现、能由配置、instruction、格式、来源元数据或读写链路解释的问题。两个模型出现同类结果只是排查线索，只有档案对照、固定输入重放或单变量干预才能支持系统根因；报告接受不等于事实正确。

用户进一步明确验收边界：baseline 的搜索深度、探索范围和模型自身判断能力可以有限；本轮要识别和消除的是这些因素之外，系统额外造成的错误和信息损失。两轮内没有追到全部原始来源、模型给定完整证据后仍判断不佳，不能直接算作本轮工具缺陷。原文已有但提取丢失、请求被错误改写、引用或读取错绑、额度未如实执行、已知故障被错误升级，才属于可定位的工程问题。instruction/schema 适配也只能在固定输入证明通用缺陷后处理。

## 实验设计

使用 baseline 12，角色和工具版本沿用 baseline 11。全局 fetch 尝试上限从 20 提高到 40，失败 URL 仍计数；最多两轮，单 Agent 的主机上下文 allowance 262144 tokens。证据交付预算 131072 tokens / 524288 UTF-8 bytes，全局蒸馏调用仍为 20，主机总模型调用/后代上限仍为 40。这些是不同额度，扩大其中一个不会自动扩大其他额度。

八题乘两个模型，共 16 次独立完整流程。每次独立 SQLite，最多两个流程并发；同一外部搜索服务共享，检索结果不被冻结，不能将两次网络运行当作严格相同证据实验。角色、工具实现、请求和依赖文件在整个批次冻结 SHA-256，不覆盖历史结果。三个明确约束版本同时改变范围、来源和深度，属于组合干预，不用于单独估计语法或措辞效应。

配置与完整原文见 [测试集](../examples/benchmarks/scenario-matrix.json)，运行器见 [成对运行器](../examples/benchmarks/run_scenario_matrix.py)。原三题的大小写和语法保持不变，EBD 保持用户指定的精确句子。

| 场景 | 对照 | 需要的来源与深度 | 检查重点 |
| --- | --- | --- | --- |
| 头显比较 | 原始题与指定代际、容量、市场及证据要求 | 官方规格、带日期价格、实测/体验 | 产品版本串用、旧价格当现价、评测当测量 |
| 航班规划 | 原始题与给出日期、身份、联程条件 | 航司路线与政府入境/过境资料 | 缺参数是否诚实；中转不等于分票；不可捏造实时可订性 |
| 食物与睡眠 | 原始题与明确慢性失眠、人体随机试验 | 原始试验、系统综述、对照/剂量/效应 | 机制代替疗效、无对照研究误当 RCT、二手材料代替原始研究 |
| EBD 定义 | 精确原题 | 原始方法文献，适量背景 | 缩写错配、引用链、无必要扩大研究范围 |
| Python sqlite3 | 明确 3.12 版本和三种模式 | 对应版本官方长文档和代码 | 版本、条件/否定词、长页及代码提取、相似段落绑定 |

## 泛化约束

用户明确要求避免针对低分测试题过拟合 instruction。本轮所有六个角色的 instruction、task template 和输入/输出 schema 均未修改。明确约束的题目是诊断对照，不作为角色的领域知识、关键词规则或答案模板。后续如需调整 instruction，应先以固定输入确认失效机制，再使用未参与调整的保留题验证；不得把本轮题目同时用作调参与最终泛化成绩。

## 可测试变量

下表列出可操纵或固定的变量；未在本轮做过的控制不视为已验证。

| 层次 | 变量 | 可用控制方法 | 观测量与归因边界 |
| --- | --- | --- | --- |
| 用户输入 | 原文、语法、大小写、地名拼写 | 同一意图的最小改写，固定其他参数 | 原文逐阶段一致性；查询实体是否变化 |
| 用户输入 | 明确/隐含的来源要求 | 只增加“官方/原始试验/版本文档” | 候选到入选到引用的来源类别变化 |
| 用户输入 | 深度与答案范围 | 简短回答与调查证据方法分别测试 | 计划范围、必答项、停止依据 |
| 用户输入 | 日期、市场、版本、身份 | 每次只增加一个约束 | 查询、筛选和结论中约束保留率 |
| 用户输入 | 语言与地域 | 等义中英文题、检索 language/region 配置 | 区域来源缺口；英文输出与检索语言分开 |
| 规划 | instruction、例子、schema 限制 | 固定题目重放 Planner | 问题覆盖、每条查询目的、四问题上限 |
| 检索 | 查询原文与自动恢复变体 | 同查询重放；记录主/恢复 query | 是否被改写、实体是否丢失 |
| 检索 | max_queries、max_results、页码 | 每次只改一项 | 原始返回/保留/遗漏条数及后续来源质量 |
| 检索 | 搜索工具、引擎、语言、时间筛选 | 同一查询、同一时段比较 | 上游结果变化不能冒充模型差异 |
| 检索 | scholarly 服务的实际 admission | 对照工具意图、结果与配置 | 配置列出工具不等于真正获取学术结果 |
| 候选 | 标题、snippet、abstract、日期、work_id | 固定候选卡片增加/去除一个字段 | 选择改变；元数据裁剪和身份合并 |
| 候选 | 排序与卡片数量/字节限制 | 固定卡片随机置换 | 位置偏差、前 128 条和 256KiB 边界 |
| 获取 | 总 URL 额度与失败计数 | 20/40，同样候选输入 | 获取数、重复/重定向身份、未使用容量 |
| 提取 | HTML/PDF、表格/代码、标题和正文 | 同一原始字节跑提取控制 | 原始有/档案缺的字段；媒体类型与页码 |
| 提取 | 元数据、日期、作者、版本 | 原始 HTML 与 provenance 对照 | 声明日期与真实有效期不同 |
| 读取 | line/page、UTF-8、扫描上限 | 固定 snapshot 边界注入 | 读取字节、SHA、continuation、明确 partial |
| 蒸馏 | chunk 大小、全局调用额度、repair | 固定 chunks，仅改一项 | 读过但未蒸馏、有效引文被排除、尾部遗漏 |
| 交付 | token 估算、字节上限、文档顺序 | 固定档案和蒸馏结果重放 | 全文/仅引文/整源被移除；不得以窗口大推断读全 |
| 综合 | 指令、事实与推断格式、引用绑定 | 固定同一 evidence 重放 | 源内矛盾、单位/日期/对象错配、过度推断 |
| 审阅 | 审阅指令、错误类型与输出门禁 | 对真实草稿注入已知错误并保留正确对照 | 漏报/误报；格式合法不能代表语义支持 |
| 运行环境 | 主机 model/descendant/tool/storage/deadline 额度 | 对照请求、grant、实际消耗与终态 | 下游先耗尽、未调度或截断，不能算模型不愿读 |
| 可复现性 | 模型报告版本、参数、并发、搜索时变 | 保留 request audit 和冻结代码 | 模型名与真实返回 ID；实时成对非严格因果 |

## 结果

第一批 16 次完成，10 次成功生成正式报告，3 次 interrupted，3 次 failed；代码/资源/请求冻结核对通过。所有失败保留，不能把没有报告的样本算作低质量报告或从成功率分母中删去。原始记录保存在 `local/scenario-matrix-20261003/`。

| 问题 | DeepSeek | GPT |
| --- | --- | --- |
| headsets | interrupted · SCHOLAR_RATE_LIMITED · fetch 0/0 | [succeeded · sufficient · fetch 5/7](../local/scenario-matrix-20261003/headsets-gpt-evidence/report.md) |
| headsets-scoped | interrupted · SCHOLAR_RATE_LIMITED · fetch 0/0 | [succeeded · partial · fetch 17/19](../local/scenario-matrix-20261003/headsets-scoped-gpt-evidence/report.md) |
| flights | failed · sufficient · fetch 6/7 | [succeeded · sufficient · fetch 6/6](../local/scenario-matrix-20261003/flights-gpt-evidence/report.md) |
| flights-scoped | [succeeded · partial · fetch 16/16](../local/scenario-matrix-20261003/flights-scoped-deepseek-evidence/report.md) | [succeeded · partial · fetch 6/6](../local/scenario-matrix-20261003/flights-scoped-gpt-evidence/report.md) |
| sleep | [succeeded · sufficient · fetch 10/13](../local/scenario-matrix-20261003/sleep-deepseek-evidence/report.md) | failed · sufficient · fetch 6/8 |
| sleep-scoped | failed · partial · fetch 9/19 | [succeeded · sufficient · fetch 6/11](../local/scenario-matrix-20261003/sleep-scoped-gpt-evidence/report.md) |
| ebd | interrupted · SCHOLAR_RATE_LIMITED · fetch 1/5 | [succeeded · sufficient · fetch 2/7](../local/scenario-matrix-20261003/ebd-gpt-evidence/report.md) |
| sqlite | [succeeded · partial · fetch 12/16](../local/scenario-matrix-20261003/sqlite-deepseek-evidence/report.md) | [succeeded · sufficient · fetch 3/3](../local/scenario-matrix-20261003/sqlite-gpt-evidence/report.md) |

### 优先的共同系统缺陷

| 问题 | 两模型证据 | 固定输入复核 | 当前处理 |
| --- | --- | --- | --- |
| 相对链接和片段丢失当前文档路径 | 两模型航班和 Python 档案均出现；整个首批共 17 份文档、1114 条链接记录受影响，含跨页面/运行及不同锚文本重复 | 同一原始 HTML，旧版把 `other.html`、`#details` 解析到域名根；修正后 1113 条目标恢复，另 1 条导航链接被省略 | 已修复通用 HTML 提取；原始字节及旧档案保留。这证明链接损坏，不证明它解释了所有报告缺口 |
| 括号或引号中的约束被当成主题 | 两模型 headsets-scoped 的实际准备记录都写 `topic=512 GB`；GPT 真正搜索了容量、SSD 等偏题结果，DeepSeek 也执行了容量恢复查询 | 不调用模型，容量、日期、人群、任意比较维度均可误触发 | 已收紧为明确定义或相邻且首字母匹配的缩写展开；保留 EBD 原题 |
| 工具清单与实际启用不一致 | 两模型全部首批任务出现 OpenAlex 本地 quota/admission 拒绝，实际没有 OpenAlex HTTP 请求 | 配置 `openalex_admission=False` 与完整 nondispatch 记录一致 | 这是明确配置状态，并非证明 OpenAlex 服务不可用；“三类工具已登记”不能当作“三个数据源已工作” |

同样确认但首批没有观察到两个模型同时触发的缺陷：Crossref 的已收到 HTTP 429 被放大成整个研究的未知提交。三个 DeepSeek 失败样本中，原结果 `commit_state=not_applicable`，记录完整且清理完成，检索层却抛 `commit_state=unknown`。用这三份原始结果重放，旧处理全部中断，新处理全部保留已有候选、停止对该受限 backend 的本次调用并继续其他来源；不添加自动重试，不改变原 error。即使实际触发集中在一个模型，根因也在不接收模型输入的确定性错误处理里。

### 输入和检索的控制实验

保留了五次无模型、无 fetch 的真实 search 控制，见 [记录](../local/scenario-matrix-20261003/search-controls/results.json)。每个查询只请求一次 `max_results=10`，用同一份返回比较前五条与后续结果，避免把两次不同检索误当成 max_results 的效果。

- 三条保留的 Planner 查询各返回七条；新增第六、第七条没有找回 Python 3.12 官方版本，也没有把加拿大过境资料变成永久居民返加资料。睡眠 RCT 的关键候选在前五条已出现。这个小样本不支持“只增加返回条数就能解决来源错配”。
- GPT 航班查询把 Chinese passport、permanent resident、air travel、transit、visa 放在同一串里，返回集中到 China Transit Program。单独聚焦永久居民返加、PR 卡和官方域名后，前几条出现相关 Canada.ca 页面。控制同时改变了关键词及 site 限定，支持后续做逐项拆分实验，不能单独归因于 site 操作符或某一条 instruction。
- Python 精确路径的 site 查询本次返回 SEARCH_UNAVAILABLE/无可用条目，不能宣称加 site 就总会改善查询。DeepSeek 首批通过另一查询已经取得 3.12 官方页面；GPT 取得的是 `/3/` 当前版本并在报告中承认这一点。因此版本偏差不是两个模型共同的来源读取缺陷。
- 明确睡眠研究要求的 GPT 样本进入原始试验，并区分随机设计、样本、对照、剂量、主客观结局和人群限制；宽泛问题多依赖二手说明。由于题目范围及网络返回都变化，只能作为组合干预结果，不能宣称已证明 instruction 的单独效应。

### 已排除与仍需区分的因素

第一批 16 个 SQLite 全部 integrity ok，无外键异常、无待结算 operation；2418 份 artifact、105 份 snapshot、265 条读段记录、491 条已保留引文绑定通过原审计器。202 份保留的 Agent input 中，原始 question 与各自请求逐字相同。原审计器校验字节与绑定，不校验 HTML 原始 href 的解析语义，因此“审计通过”没有覆盖链接错误；本轮新增原文对照补上了这类观测。

首批最大 19 次 fetch，最大 17 次蒸馏，没有观察到蒸馏 20 次上限导致跳过。40 次是总上限，不是最低消耗要求。后续验证样本已实际超过 20 次 fetch；是否触及蒸馏、总模型调用或上下文限制必须分别读记录，不能从 256k allowance 推断所有内容已交付。

仍保留的独立问题：

- GPT 原始睡眠题在 Writer 阶段遭模型服务 HTTP 429、`tokens` 类型，完整保存 retry-after 提示。本轮不把它记作模型推理能力不足。后续批次限制每个模型最多一个完整研究并发，单流程内部仍保持四个蒸馏并行；这不能保证服务永不限流。
- DeepSeek 明确睡眠题的 Analyst 两次输出超出 claim 字段 maxLength，有限 repair 后停止。需要用固定输入检查信息颗粒度、schema 与 instruction 的适配，目前没有两模型共同触发证据，未通过放宽 schema 隐藏它。
- DeepSeek 原始航班题四次审稿后仍不通过，争议集中于表述是否超出证据。GPT 同题没有该失败，不能据此直接称工具瓶颈。
- 短 HTML 控制样本触发提取库的短文本 fallback 后会去掉链接和部分格式；长代码控制保留原始缩进。本轮已固定输入重现前者，但尚未建立它与真实成对报告缺口的因果关系，未全局调整提取阈值。
- GPT Python 报告承认未获得指定 3.12 版，却仍为 sufficient；DeepSeek 该题有 3.12 版且状态 partial。覆盖标签与用户约束的校准仍需测试，不能将两者概括成共同版本错误。

### 修复验证与实验边界

修复中间版本把 lxml 树直接传给提取库，17 份真实 HTML 重放揭示注释节点兼容回归。`local/scenario-recheck-20261003/` 只执行了两份头显样本；已明确撤回其验收用途，通过 runner 指纹检查阻止余下六次开始，所有记录保留。这个中间批次不纳入修复后成功率。随后恢复提取库正常字符串输入及注释清理，并以 extraction revision 3 标识。

修复后的相关回归 **262 passed in 50.57s**，覆盖搜索主题、限流隔离及负例、HTML/Chromium、方法边界和数据库审计；40 URL revision 注册/旧版隔离另外有明确检查。未改变角色 instruction、角色 schema 或 workflow 节点顺序。

最终实测批次在 `local/scenario-verified-20261003/`，重测头显明确约束、航班明确约束、EBD 和 Python 四个场景的两个模型，结果另列如下。

### 最终复测

八次全部生成正式英文报告，HTTP/SSE、重启后的报告字节一致性和既有数据库审计均通过。生产代码、依赖、资源和请求在这八次期间的冻结核对通过；与首批比对的 165 个 Agent 资源文件 SHA 全部相同。本轮未修改角色 instruction、task template 或角色 schema。

下表 fetch 为成功数/尝试数；`partial`、`sufficient` 是运行中保存的覆盖标签，不是人工准确率评分。

| 场景 | DeepSeek | GPT | 读报告后的归因边界 |
| --- | --- | --- | --- |
| 头显明确约束 | [partial · 20/23](../local/scenario-verified-20261003/headsets-scoped-deepseek-evidence/report.md) | [partial · 12/16](../local/scenario-verified-20261003/headsets-scoped-gpt-evidence/report.md) | 都区分了 M2/M5 和规格/评测；仍缺官方 Meta 规格与指定 M2 的当前价格。没有据此追加领域 instruction 或扩大探索机制 |
| 航班明确约束 | [partial · 18/20](../local/scenario-verified-20261003/flights-scoped-deepseek-evidence/report.md) | [partial · 7/7](../local/scenario-verified-20261003/flights-scoped-gpt-evidence/report.md) | 都找到官方 PR 返加依据，仍没有航司确认的指定日期单票路线及具体第三国过境依据；缺口本身不证明工具丢失 |
| EBD 精确原题 | [sufficient · 2/8](../local/scenario-verified-20261003/ebd-deepseek-evidence/report.md) | [sufficient · 2/6](../local/scenario-verified-20261003/ebd-gpt-evidence/report.md) | 两者基于两篇论文解释方法；没有为了提高来源数强迫更深探索 |
| Python sqlite3 | [sufficient · 5/7](../local/scenario-verified-20261003/sqlite-deepseek-evidence/report.md) | [sufficient · 4/4](../local/scenario-verified-20261003/sqlite-gpt-evidence/report.md) | DeepSeek 取得 `/3.12/`；GPT 仍引用 `/3/` 当前版却以 3.12 为题，覆盖标签不能代表版本约束得到满足；未证明为提取或交付错误 |

这八次不是首批十六次的完整复跑，且检索随时间变化、每模型完整流程并发从最多二降为一。不能以 8/8 对 10/16 宣称三个修复带来的净成功率或报告质量增益。修复归因主要依赖固定原始材料的重放。

可直接确认的工程结果：

- 新批次原始 HTML 与归档链接对照，没有再发现已定位的“当前文档路径丢失”模式（八次均为 0）。首批 17 份原始 HTML 重提取的 1114 条受影响链接记录中，1113 条目标恢复，1 条导航链接被省略；不能把“没有旧错误”写成“所有网页内容均无损”。
- 两个头显流程均没有再将容量 `512 GB` 当作研究主题。固定输入的容量、日期、人群和比较维度负例一并通过，修复不依赖头显关键词。
- DeepSeek 的 Python 复测实际再次遭遇 Crossref HTTP 429，已有候选被保留，流程继续并生成报告。这补充了首批三份固定故障结果重放的真实验证。不是通过取消限流或无限重试实现。
- DeepSeek 头显实际尝试 23 个 URL，确认已越过旧 20 次边界，未超过新 40 次上限。最大蒸馏调用为 20，所有八次 `skipped=[]`，最大总模型调用 34；本批没有证据表明蒸馏或主机模型调用额度造成来源跳过。
- 八个独立 SQLite 均 integrity ok、无外键异常、无未结算 operation、无原审计器 findings；1522 份 artifact、70 份 snapshot、136 条读段、282 条保留引文绑定通过。130 份保留角色输入中的原始问题逐字一致。审计还保留 10 条被排除引文和 2 次角色 repair，不把被剔除内容计入已验证引文。详见 [汇总](../local/scenario-verified-20261003/verification-summary.json)。

### 本轮交付状态

已完成 8 题 × 2 模型首轮诊断、5 次无模型 search 控制、原始网页和工具结果重放，以及修复后的 4 题 × 2 模型复测。中间撤回的 2 次保留记录但不计入验收，总共实际运行 26 次研究流程。

三个通用修复已落地：主题误识别、相对链接解析、已结算 scholarly 限流的故障隔离。40 次 fetch 上限已配置并实测。剩余覆盖不足保留为 baseline 的实际表现；不以提高报告分数作为更改 instruction 的理由。

截至上述批次仍不能宣称全部非模型损失已消除：短 HTML fallback、模型服务 token 限流及 claim 长度失败的归因仍需独立处理。后续进展见下面的持续诊断，不用本轮题目写入角色答案模板。

## 持续诊断：短文结构、长文覆盖与读取调用

本周期资料在 `local/fidelity-cycle-20261003/`。角色 instruction、task template、schema、研究轮次和模型调用额度保持不变。新增的两个场景在修复前未参与提示词调整，原文见 [保留场景测试集](../examples/benchmarks/scenario-heldout.json)：HTTP 429/503/Retry-After 的规范语义，以及蜜蜂如何交流食物方向与距离。后续使用时它们已是回归题，不能继续声称是新的保留集。

### 已修复及验证

1. **短 HTML 的纯文本 fallback。** 提取库默认在正文不足 250 字符时使用另一条纯文本路径，丢失链接、代码缩进、表格列关系、列表编号、上下标。固定输入 14 个失败用例加 1 个正常短文本对照，修复后全部通过；增加防止替代结果丢掉已有条件和同图多链接用例后，相关用例为 17 passed。保留默认正文选择，仅在结构化候选保留已有文本块时采用候选，不全局降低长文提取阈值。
2. **图片相对地址与图片链接。** 图片 src 使用最终文档 URL/base 解析；图片作为链接时保留图片目标和外层访问目标。早期试作向 DOM 插入 alt 文字，真实网页重放发现它改变正文选择、遗漏价格说明，因此撤回。最终实现只在已选中的图片后保留对应目标。撤回试作在 `replay-withdrawn-dom-labels/`，不作为验收结果。
3. **长文扫描的额外桥接调用。** 原来每 200 行之间单独调用一次工具读两行交界，造成近一倍额外调用。现改为下一完整窗口重叠上一窗口最后一行，以原始 byte span 校验重复内容和换行。6001 行固定文档从 61 次降为 31 次，完整字节不变；200 行/10 页、65536 字节、扫描额度及 UTF-8 校验不变。

将前两批 175 份原始材料逐份重提取：0 异常，139 份 text 字节相同，36 份有变化。较新的 revision 3 批次中 62/70 份不变，8 份主要恢复图片访问目标、图片绝对地址及短页链接。没有任何新结果比旧结果更短；长度不是完整性证明，因此另外检查真实差异。所有原始档案未重写，新派生结果单独保存。

三个新网页经过实际 `web.fetch@2` worker、SQLite commit 和完整 `document.read`：example.com、RFC 9110 HTML、Python 3.12 contextlib。三者的原始/text/index 哈希和完整读取均通过。RFC 页也正是下一节发现的反例：完整读出提取结果不能证明完整提取原网页。

最终 HTML 修复状态的全量回归 **1487 passed in 380.83s**。随后单独修改扫描窗口，受影响的 source-access、systemic-baseline、parallel-baseline 回归 **138 passed in 137.30s**。两组覆盖有重叠，不相加为测试总数，也不声称后一次全量套件已重跑。

### 新场景暴露的共同失败

四次新场景运行的代码与请求冻结核对通过，原始失败均保留。运行中使用 HTML extraction revision 4，扫描窗口优化发生在该批结束后。

| 场景 | DeepSeek | GPT |
| --- | --- | --- |
| HTTP 规范 | failed；18/18 fetch；已执行 100 次 document.read，加其他工具正好耗尽 128 次额度 | failed；6/6 fetch；已执行 115 次 document.read，加其他工具正好耗尽 128 次额度 |
| 蜜蜂导航 | [succeeded / sufficient，6/14 fetch](../local/fidelity-cycle-20261003/heldout-runs/bee-navigation-deepseek-evidence/report.md) | [succeeded / partial，3/10 fetch](../local/fidelity-cycle-20261003/heldout-runs/bee-navigation-gpt-evidence/report.md) |

四个数据库的原审计器仍为零 findings。HTTP 两个失败均明确记录 `tool.rejected / LIMIT_EXCEEDED / Shared tool dispatch allowance is exhausted`，不是模型拒绝读取。对这两组全部已下载的 24 份文档做固定字节、无模型的扫描重放：新实现分别用 87 和 72 次读取即可完整覆盖，所有输出字节与档案一致。加原先其他工具为 115 和 85 次。这个控制证明调用开销降低，尚未证明修复后完整模型流程成功，也不能保证扩大提取正文后仍在 128 次之内。

### 当前最重要的未解决工程缺陷

**长 HTML 被局部容器误识别为整篇正文。** 实际抓到的 RFC 9110 HTML 为 1,187,554 bytes，归档提取 text 仅 9400 bytes，主要留下 6.4 节。原 HTML 中 `Retry-After` 出现 17 次，提取后为 0。两模型的研究也都取得了这个不完整版本，并在分析中指出缺少规范正文。这是原文到提取结果之间的损失，不能归咎于 workflow 搜索不深或模型能力。

使用同一份 HTML 的 default/recall/fast/precision 提取均遗漏目标章节。离线候选仅移除 DOM 的 id 属性，可提取约 456 KB（未先解析相对链接的控制输出），恢复 Retry-After 和 503 内容；不修改原始字节。1066 个至少 80 字符的非导航段落中，原提取缺 1056 个；候选覆盖字符由 2543/286644 提高到 286346/286644。但候选仍有 5 个旧输出块不能直接逐字匹配，不能直接全局启用。下一步是通用章节覆盖检测与安全恢复，再验证保留条件、表格、代码和正文来源。不能写针对 RFC 域名或这道题的规则。

同时保留的工程检查项：部分长页表格仍被压平；仅导航/浏览器兼容提示页需要更精确的内容分类；提升正文覆盖后要重新测量共享读取额度。服务 token 限流尚需独立节流/并发测试。

Analyst 格式失败已有进一步归因：instruction 与输出 schema 都明确 claim 最长 2048 字符，两个失败输出实际为 2333 和 2080 字符。未发现字符/字节计数冲突或未告知约束，因此目前没有把它认定为通用契约缺陷；未放宽 schema，也未修改 instruction 来迎合本题。

持续目标保持 active：已证实仍有长文提取损失，不能因为短文修复、测试通过或归档审计正常而宣布接近零系统损失。

## 长文恢复与额度修复（持续周期第二阶段）

上述“当前未解决”描述的是 revision 4 的检查点，以下记录后续结果，不改写旧档案。

- `trafilatura_markdown/5+trafilatura/2.2.0` 在普通抽取后检查同一篇文档中较长段落的覆盖；大量缺失时在 DOM 副本上中和布局 ID/class，以通用正文容器重试。采用候选前必须保住原先文本块、链接/图片目标和代码。网页的唯一 article/main 边界优先于整个 body，避免把推荐卡片误当遗漏正文。没有 RFC、医学或某道测试题专用分支。
- 大篇幅、不同容器属性的固定手册用例，关闭恢复时 **3 failed**，开启后通过。最初的小篇幅控制本来就通过，保留为 `long-before.log`，不能拿它当失败复现；实际故障控制在 `long-large-before.log`。另有防止丢条件、链接、缩进及吸入文章外推荐卡片的负例。
- RFC-editor 同一原文由 **9400 → 773234 bytes**；HTTPWG 同一规范由 **7277 → 687794 bytes**。RFC-editor 的原有输出块保留，`Retry-After` 从 0 处恢复到 16 处。段落重合是启发式指标，不是百分之百内容完整性证明；仍有少量源段落不能逐字匹配。
- 新的可选 `provenance.html_extraction` 为封闭 schema，记录恢复前后匹配、是否尝试/采用及显著未匹配状态，并标记 `semantic_verification: false`。这一诊断随来源描述和 synthesis warning 交付，完整读取归档不再被当成原始页面完整提取的证明。
- 两个历史批次加首次保留场景共 **208 份**原始 snapshot 重放：**0 异常，167 份 text 字节不变，41 份变化**。只有 5 份采用长文恢复（4 份来自两个 RFC 镜像，1 份恢复一篇文章的参考文献等），其他变化承接短文/图片/链接修复。3 份仍有显著未匹配提示，候选未通过保留原内容的安全条件，继续使用原提取结果。所有原始档案未改；详见 `replay-v5-scoped-summary.json`。
- 未限制 article/main 的初版长文恢复会吸入推荐卡片，已撤回验收用途；记录保留在 `replay-v5/`，最终为 `replay-v5-scoped/`。不能把中间版更长的输出记成质量提升。
- 对两组原失败 HTTP 文档重新提取后，再经当前真实读取组件的固定输入重放，全部 24 份输出字节一致：DeepSeek **171 次**完整读取加原观察到的其他工具 28 次，GPT **156 次**加其他工具 13 次。旧 128 次宿主共享额度确实不足。宿主默认工具额度提高为 **512**，仍严格执行调用计数、每次 200 行/10 页/65536 字节、扫描预算、40 次 fetch 和原有模型调用限制。这个上限并不保证所有可能长度的 40 份文档均可完整扫描。
- 读取失败现在保留底层 `message` 与 `details`，可以直接区分共享工具额度不足和来源读取故障，不再只留下泛化的“读取未成功”。
- 第二轮实际 worker/SQLite/完整 document.read 再测 example.com、RFC-editor、Python 3.12 contextlib，三份原始/text/index 哈希及完整读取通过；RFC 实际归档并完整读出 **773234 bytes**，不是仅离线提取成功。见 `live-tools-v5/`。

该状态全量回归 **1497 passed in 385.25s**；HTTP 两模型完整回归见下表。40 URL、两轮搜索、角色 instruction/task/schema 与模型调用额度保持不变。服务限流、长表格和其余显著未匹配页面仍需独立排查，目标未宣布完成。

### 第二阶段真实流程结果

HTTP 两模型回归已结束，`http-verified-v5/progress.json` 的代码/请求冻结核对通过；与前一批相比 **165 个角色资源文件哈希不变**。本批原始问题在 34 份保留的角色 input 中逐字一致。

| 模型 | 真实结果 | 系统归因 |
| --- | --- | --- |
| DeepSeek | [生成英文报告，partial](../local/fidelity-cycle-20261003/http-verified-v5/http-semantics-deepseek-evidence/report.md)；15/15 fetch，149 次 document.read，总工具 174 次，30 次模型调用 | 已越过旧工具上限并完成全部 15 份来源读取。报告实际引用 503/Retry-After 和重试前提的规范正文。partial 由 20 次蒸馏上限导致一个 chunk 未使用，不通过修改 instruction 或探索机制掩盖这个方法取舍 |
| GPT | failed；1/1 fetch，25 次 document.read，总工具 31 次，5 次模型尝试，未生成报告 | 第一个蒸馏批次收到 `provider.http` / HTTP 429 / `rate_limit_exceeded` / `tokens` / `retry_after_seconds: 2.0`。三个并行蒸馏请求的输入估计约 51.6k、69.1k、66.0k tokens；一份限流后另外两份被取消且远程完成状态未知。这是服务可用性失败，不能归为模型理解能力，也不自动重放未知结果 |

两份数据库均 integrity ok、无外键异常/未结算 operation/审计 findings；345 个 artifact、16 个 snapshot、174 条读段及 DeepSeek 的 116 条保留引文绑定通过。DeepSeek 一次 Analyst 格式 repair 保留，没有 quarantine 或被排除引文。本批未变成 2/2 成功；修复读取的归因依赖固定原文重放，不能把不同搜索结果的净质量变化都归于修复。

已完整读过 DeepSeek 报告：503/429 定义、Retry-After 两种值形式、可选性、规范语义与服务器计数策略有来源支撑。仍有重复镜像、较多二手解说、冗长表述及一处 `RP 6585` 拼写，保留为方法/生成质量表现，不追加 HTTP 题目的专门 instruction。

下一项服务层排查还包括：应用边界仅保留 `cause_code`，具体 HTTP 状态/可用的 Retry-After 只能从底层事件找回；当前 Runtime 明确拒绝自动模型重试。应在明确的宿主策略、有限额度及可核对记录下设计排队/退避，不能在 connector 内偷偷重复外部请求，也不能重试另外两个远程完成状态未知的请求。

另一个离线固定输入探针表明：带 div/p 包装的嵌套列表可能整段丢失（包括执行条件），见 `empty_wrapper_probe.py` / `empty-wrapper-probe.jsonl`；空 span 对照保留条件。这个问题不依赖 RFC 用词，尚未修复，列入下一轮结构保真排查。不能以主章节恢复或 1497 项测试通过宣称提取无损。

## Orchestrator 的 API 恢复（持续周期第三阶段）

按用户要求，临时 API 失败的恢复由 application/orchestrator 承担。新增
`RecoveryPolicy` / `RecoveryCoordinator`，不修改任何 Agent 资源或 baseline
探索步骤。Runtime/provider 仍然每个 child invocation 只发起一次调用；应用在
确认失败的执行、清理和记录均已完成后，使用相同角色和相同输入创建新的 child。

默认最多重启三次；HTTP 429 必须具有已识别的 `rate_limit_exceeded`，另接受
500/502/503/504。指数退避从 2 秒开始，带不超过 25% 的抖动，遵守可解析的
Retry-After；单次最长 60 秒，单个逻辑调用累计等待最长 180 秒且不越过根 deadline。
同一 service 的 profile/model 共享冷却，取消可中断等待。没有切换模型、缩短输入
或重置共享 model/descendant 额度。恢复期间其他并行任务继续执行，已完成节点不重跑。

每次尝试、失败、等待、重启、恢复或耗尽都落库，并经既有 SSE 接口可见；用
`recovery_id` 关联同一逻辑调用，用不同 child/action/attempt ID 保留真实调用。
失败记录链接已经提交的 invocation/terminal receipts，重启决定先落库再执行。
认证、余额、格式错误、远程完成状态未知及记录/清理/提交不确定不进入此恢复策略。
格式 repair 仍归原来的有限方法逻辑。实际恢复配置随 research-method manifest 保存。
接口与边界详见 [service 使用说明](usage/research-service.md#orchestrator-recovery-during-execution)。

### 固定输入与完整流程证据

| 验证 | 实际结果 | 可得出的结论 |
| --- | --- | --- |
| 上轮 GPT 失败批次的三份 Distiller 4 大输入，同角色、同字节、并发三 | 新建组件实验共 5 次模型调用；同一份任务实际遇到两次 HTTP 429，分别退避约 2.02、4.18 秒后成功；三份输出均通过原 schema | 临时限流能被应用恢复，另外两份任务没有被取消；不是自动重放历史未知请求，也不是完整研究报告实验 |
| 新建 GPT `baseline@12` 完整 HTTP 题流程 | [生成英文报告](../local/fidelity-cycle-20261003/recovery-workflow/http-semantics-gpt-evidence/report.md)，succeeded / sufficient；3/3 fetch、124 次 document.read、总工具 132 次、17 个逻辑角色调用和 19 次真实模型调用 | 两份蒸馏分别遇到 HTTP 429，服务要求等 15、23 秒，实际退避约 18.23、26.98 秒后完成；临时 API 失败没有再中断报告生成 |

完整流程用时约 227 秒；HTTP/SSE 回放、相同 client_request_id 的幂等性和服务重新
打开后的报告字节一致性均通过。运行期间生产代码与请求冻结核对通过，与上轮比较
165 个角色资源文件哈希全部相同；15 份保存的含 question 角色输入逐字保留原题。
完整流程的检索结果与上轮不同，不能把报告内容差异全部归因于恢复；固定输入组件
实验和实际失败→等待→成功的事件链是恢复效果的直接证据。

两个新 SQLite 数据库均 integrity ok、无外键异常、无未结算 operation、原审计器
零 findings。共核对 157 个 artifact、3 个 snapshot、124 条读取片段和 17 条保留引文。
新增只读恢复审计逐一核对失败 receipt、child 绑定、重启先记后执行、尝试编号及
实际 provider request digest：**20 个逻辑角色调用**（组件 3 + 完整流程 17），
共 **24 次尝试、4 次重启，零 findings**。
两批各两次失败均未报告 usage，仍保留为 unknown，不能按零消耗记账。
原始材料、配置及详细结果分别在 `recovery-replay/`、`recovery-workflow/`；
后者的 `verification-summary.json` 汇总完整检查。

已完整读过新报告：包含两个状态码区别、Retry-After 的日期/秒数形式，以及规范语义
不等于服务限流规则的区分；自动 sufficient 标签仍不是事实准确率保证。本轮未按该题
修改 instruction。DeepSeek 上轮已完成完整流程，本轮没有为了凑成配对而重复运行；
实际恢复故障证据来自 GPT，临时 5xx 等其他分支由受控故障测试验证。

恢复实现的全量回归 **1522 passed in 442.13s**。其中新增 25 个恢复用例覆盖
429/5xx、永久错误、未知结果、等待上限、取消、记账失败、共享额度耗尽和并行任务
隔离；真实调用证据独立保留，不用 mock 成功替代实际验收。之后仅增加 bootstrap
factory 的可选 `recovery_policy` 参数转发，默认值与上述真实实验相同；额外验证见
`recovery-bootstrap-verified.log`：application/architecture **202 passed in 35.16s**，
factory 的默认策略与显式禁用入口也单独核对通过。两次测试有重合，不相加为总数。

恢复策略仍有限：不是跨进程共享的 TPM 调度器，不自动续跑服务崩溃时的未知任务，
也不保证持续服务故障下完成研究。前述 HTML 嵌套列表损失仍未修复，持续目标保持 active。

## HTML 结构恢复（持续周期第四阶段）

上段的嵌套列表缺陷在本阶段继续排查。固定输入确认：含多个短链接的列表会被
Trafilatura 的链接密度启发式当作导航删除，条件和例外随之丢失。隔离环境中升级到
Trafilatura 2.3.0 后，12 个布局/recall 变体仍全部遗漏条件，故没有以升级版本代替修复。
另外复现了合并单元格关系、显式列表编号丢失。最初 10 个固定结构测试在旧实现上
全部失败，见 `structure-before.log`；不依据某道研究题修改 instruction。

本阶段使用免费的 [Markdownify 1.2.3](https://github.com/matthewwithanm/python-markdownify)
作为结构转换器，保留 Trafilatura 2.2.0 的正文选择。提取身份为
`trafilatura_markdown/6+trafilatura/2.2.0+markdownify/1.2.3`。

- 单一 article/main 在初始提取前限定范围；进一步恢复优先使用包含已选正文的最小
  原文容器。含大量额外菜单/推荐信息且边界不明时保留原结果及明确诊断，不把整个
  body 转成所谓补回的正文。
- 保留检查按原文块核对有序的词、数值和标点，允许补入原提取器删掉的日期等内容，
  不允许替换数值、否定词或原有条件。不能把两个列表项拼成一个不可匹配的假句子。
  这个检查不改动后续严格的原文引文定位。
- 嵌套列表保留层级；行列合并、显式/反向编号、定义列表以及带超链接的代码保留
  HTML 结构。普通代码采用 Markdown fence，并区分源码缩进与列表增加的外层缩进。
  否则，链接丰富的语法定义会在代码转换时再次丢掉跳转目标。
- 已经由转换器保留的图片外层链接不重复包裹。HTML 片段不保留注释或可执行属性。
  `aria-hidden` 不被等同于视觉不可见；它可能仅排除辅助技术访问，见
  [WAI-ARIA 定义](https://www.w3.org/TR/wai-aria-1.2/#aria-hidden)。不因外层弹窗属性丢掉正文。
- 新的可选封闭 `html_extraction.structure` 保存检查块数、结构差异、恢复决定和
  unresolved；拒绝候选时，结构问题会进入来源描述和 synthesis warning。
  `semantic_verification` 仍为 false，差异不等于事实错误数，也不保证原文完整。

期间有两个被撤回的候选：`replay-structure/` 向库传入不完整 HTML fragment，短页
被拒绝，且全局 aria-hidden 清理误删正文；`replay-structure-verified/` 虽然零异常，
却仍未恢复真实 RFC 列表，并把菜单/推荐卡片扩入部分页面。两者保留诊断记录但不
计入最终验收。中间状态曾通过全量 **1532** 项测试，这没有阻止真实材料暴露问题，
因此该数字不是最终实现的全量验收结果。

最新针对性回归 **93 passed in 1.99s**，覆盖 HTML 结构、既有保真测试及实际 fetch
提案契约。最终历史重放位于 `replay-structure-accepted/`，实际工具链位于
`live-tools-structure-accepted/`；全量与真实流程结果在各自日志/协议中保留。
在进一步核对这些结果前，不宣布系统损失已经接近零。

### 固定材料与真实工具验收

最终实现全量回归 **1538 passed in 456.63s**，日志为
`structure-accepted-full-tests.log`。不是前述被撤回候选的 1532 项结果。
对同一份、哈希已核验的原始材料重放共 **227** 个快照：零异常，135 份提取文本逐字节
不变，92 份改变；原始响应字节和历史 SQLite 不改写。结构检查分别记录 76 次恢复、
62 次未发现差异、48 次非适用，另外 41 次保留原结果及 unresolved 诊断。41 次中，
22 次边界不明确、6 次原有内容不在候选范围、7 次代码保留检查拒绝、6 次链接检查
拒绝；不是 41 个已证实的事实错误，也不能当作零损失。

三个新网络响应通过实际 worker → proposal → SQLite/不可变 artifact → 完整
document.read 链路：HTTPWG RFC 9110 为 787406 字节、RFC-editor 镜像 879453 字节、
Python 3.12 contextlib 文档 69482 字节。三份均归档哈希一致、所有读取字节重组一致，
没有工具错误。额外按原始 DOM 核对两个 RFC 镜像中 GET + Range + If-Range 的第 5 步：
条件和两个分支文本、层级一致，已恢复上一版遗漏的条件；不能仅由文本变长推断恢复。
证据见 `structure-source-fidelity.json`。

边界排查保留于 `structure-boundary-inspection/`。它揭示剩余问题不只是噪声：
FlightConnections 的换乘城市/时长列表、EveryMac 的规格表、Cleveland Clinic 的
食物组合列表确有原文未进入提取结果。当前范围保护避免把整个页面的账号菜单、币种、
推荐卡片喂给 Agent，但也会阻止这些真实内容的恢复，须继续处理通用的结构范围选择。
另外，HTML 中由 span 分割的代码在可见文本上可能完整，字符串检查仍会拒绝候选；
mailto 链接被转换器过滤，也会使恢复被保留检查拒绝。这些是进一步诊断，未冒充修复。

### 三个原题的配对回归

`structure-model-regression/` 在上述提取实现上冻结代码与请求运行，冻结核对通过。
角色资源 165 个文件与上一批哈希一致，127 份含 question 的保存输入全部逐字保留
三个原题。40 次总 fetch、两轮、256k Agent allowance 以及原有蒸馏次数限制不变。

| 原题 | GPT | DeepSeek |
| --- | --- | --- |
| compare meta quest 3 and apple vision pro | [报告](../local/fidelity-cycle-20261003/structure-model-regression/headsets-gpt-evidence/report.md)，succeeded / sufficient；12/16 fetch | [报告](../local/fidelity-cycle-20261003/structure-model-regression/headsets-deepseek-evidence/report.md)，succeeded / partial；16/21 fetch |
| How do I flight from GuangZhou to Montreal? | [报告](../local/fidelity-cycle-20261003/structure-model-regression/flights-gpt-evidence/report.md)，succeeded / partial；5/5 fetch | failed，14/16 fetch；两次 Analyst 输出均引用不存在的 `r2.source-015`，没有报告 |
| What food can help me sleep well? | [报告](../local/fidelity-cycle-20261003/structure-model-regression/sleep-gpt-evidence/report.md)，succeeded / partial；13/16 fetch | [报告](../local/fidelity-cycle-20261003/structure-model-regression/sleep-deepseek-evidence/report.md)，succeeded / partial；13/22 fetch |

五份报告均已读过。GPT 报告较短，DeepSeek 更详细地列出规格/食物与来源限制；
两者使用的检索结果与证据不同，不能据此把内容差异归因于提取修复或给模型能力排名。
睡眠报告共同保留提取不完整的警告，是来源处理的待解决问题。产品报告中的第三方
240/207 Hz 数值已在两种列顺序的原始 HTML 响应里出现，逐列核对与归档一致；
提取器没有生成该数值或把另一设备的列换过来。来源事实可靠性和模型对冲突来源的
判断不能冒充工具格式错误。

六个 SQLite 均 integrity ok、无外键错误、无 pending operation、审计零 findings。
合计核验 1439 个 artifact、73 个 snapshot、142 条读取片段、379 条保留引文；
8 条未匹配引文被原有机制排除，5 次格式/绑定 repair、零蒸馏 quarantine。
每份 Analyst 输入中的 `available_source_ids` 与实际 evidence 来源块完全一致。
134 次角色调用均有独立完成记录，恢复事件审计零 findings。本批没有 API 临时错误，
不能用它冒充恢复重试证据；真实 429 的恢复证据仍是上一阶段的两个实验。
成功运行的 HTTP/SSE、幂等请求与重新打开后的报告字节检查由 runner 保留，失败运行
保留原始 error/数据库，不把它重新标成成功。汇总为 `verification-summary.json`。

航班失败进一步暴露反馈缺口：模型把 `r2.recovery.source-015` 写成不存在的编号，
输入列表和证据块没有这种错，但旧校验器只反馈“只能引用选中的来源”。新增通用
字段级错误包括 finding 的数组位置、无效/重复 ID、允许的 ID 和研究问题列表，
同样覆盖空白字段及不在计划里的问题。系统不猜测引用替代项，不改变两次尝试上限，
不修改任何角色 instruction。旧实现下新增回归为 5 failed / 1 passed；补充反馈后
decision/systemic/recovery 定向回归 **72 passed in 50.66s**。这次小改动发生在六次
完整流程结束后，不能将此前 1538 项全量或五份报告说成它的重新验收。

随后新建 `decision-feedback-replay/` 组件实验，使用失败运行保留的 Analyst 6 repair
输入，两次真实 DeepSeek 调用只改变 `repair.errors[0].details`。问题、证据、计划、
允许来源、原失败输出、角色资源均相同，冻结核对通过；没有重启或覆盖历史失败运行。
笼统反馈与字段级反馈这次都返回合法决定，因此这两次调用只验证新反馈可用，
**不证明其提高成功率，也不声称航班完整流程已经重跑成功**。组件 SQLite integrity ok、
13 个 artifact 哈希通过、无外键/pending/审计异常，两次角色调用的恢复记录核对通过。
控制测试证明错误能定位且尝试仍有界；真实实验的随机差异和失败历史原样保留。

本阶段继续取得进展，持续目标保持 active。下一优先项是已定位的正文结构遗漏和
保留检查误拒绝，研究范围/深度及模型事实判断仍按原约定排除于系统缺陷修复目标之外。

## 局部结构选择与代码保留（持续周期第五阶段）

上一阶段是实际进展，本阶段继续处理已定位的遗漏。新增独立的
`engine/toolset/html_selection.py`：从原 DOM 中保留已选文字，利用同一局部容器内的
已选段落定位缺失列表/表格，按原文顺序投影候选，再经过原有文字、链接、代码检查。
附近其他文章的子树不能充当段落锚点，局部段落覆盖不足也不能用更大的外层容器
绕过检查。无题目、域名或 CSS 名称特例。恢复一个正文列表的同时，通用样例中的
100 个币种控件仍未进入结果；8 层嵌套包装也不改变正文表格的前后顺序。
新增可选 recovered/unresolved block 数量及 `partially_recovered`，局部恢复不抹掉
剩余不确定性。

结构转换还修复了高亮 div 引入多余空行、字词被 span 分割导致代码误拒绝、代码表格
被压平，以及邮件引用链接被过滤的问题。四个新代码/链接回归在旧实现上均失败，
记录在 `structure-guard-before-final.log`。提取 revision 7 的定向回归为 101 passed，
全量为 **1552 passed in 468.43s**。真实 SQLAlchemy 页面随后揭示一个额外边界：
行内标识符前的源代码换行触发了整页代码保留拒绝。revision 8 跟踪实际渲染行内
代码的原文；102 项相关回归通过（2.12s）。1552 项属于 revision 7 的全量结果，
不是 revision 8 的又一次全量运行。

### 原始材料和工具链核对

历史材料扩展到上一阶段新增的 73 个快照，共 **300** 份相同原始响应。revision 7
重放零异常，269 份文本不变、31 份改变；revision 8 再重放零异常，仅 SQLAlchemy
那一份继续改变，其余 299 份不变。相对 revision 6，最终共 32 份改变、268 份不变。
原始响应哈希核验，历史数据库和源字节未改写。记录分别在 `replay-structure-v7/`
和 `replay-structure-v8/`。最终 300 份诊断包括 122 recovered、79 no_damage_detected、
68 非适用、12 partially_recovered、9 candidate_loses_destinations、
9 primary_content_outside_scope、1 ambiguous_body_scope。仍有 **31** 份 unresolved，
其中包含未识别的控件/外围结构，不能全部算事实错误，也不能算零损失。

`live-tools-structure-v7/` 七个真实 URL 均完成 worker 抓取、三件套归档哈希、完整
document.read 重组验证；`live-tools-structure-v8/` 独立重跑 SQLAlchemy，同样通过。
两个工具数据库分别核验 28 和 4 个 artifact、7 和 1 个 snapshot，integrity ok、
无未结算 operation、无审计异常。代码冻结核对通过。逐项原文验证不是只看字节变多：

| 原始结构 | 实际验证 |
| --- | --- |
| FlightConnections 换乘列表 | 17 条机场/时长组合全部进入同一响应的提取文本；未拿上次网络响应的时刻数值混比 |
| EveryMac 两个设备规格表 | 两张表的行序、列序和每个单元格文字与原始 HTML 一致 |
| Cleveland Clinic 食物组合列表 | 五个列表项全部恢复 |
| Python 3.12 sqlite3 文档 | 50 个原始代码块全部匹配；识别 Markdown 引用容器的缩进，不把它误算成源码缩进 |
| SQLAlchemy 文档 | revision 7 回退文本只匹配 18/78；revision 8 的 158675 字节结果匹配 78/78；其中一个 linked-code block 在列表中，核对时移除对应 Markdown 容器的两格缩进，程序内部缩进保留 |
| SQLite 教程代码表格 | 8 个代码块全部匹配，行号列与程序列未混合 |
| HTTPWG RFC 6585 邮件引用 | 13 个 mailto 目标保留 |

详细核对在两个 live-tools 目录的 `source-content-verification.json`。相关测试和
保存材料仍不能证明所有网站完整提取；代码、数据和外围菜单尚有需继续定位的边界。

### 相同材料的双模型蒸馏与新缺口

`recovered-source-distillation-verified/` 对恢复后的航班、规格表、食物页面分别调用
两种真实模型：Distiller 4、逐字相同的三个原题和同一份保存计划，二者每题收到的
输入字节完全相同，角色资源 165 个文件不变。所有段落来自前述已核验的实际
document.read 回执；这是工具→Agent 的组件实验，**不是六份完整研究报告**。

| 材料 | DeepSeek 的引文验证 | GPT 的引文验证 |
| --- | --- | --- |
| 航班 | 9 保留、0 丢弃，明确使用恢复的换乘机场和时长 | 5 保留、0 丢弃，明确使用恢复的换乘机场列表 |
| 规格表 | 3 保留、3 丢弃 | 3 保留、0 丢弃，包含恢复的 CPU/GPU 单元格 |
| 食物 | 6 保留、0 丢弃 | 6 保留、0 丢弃，包含恢复的列表内容 |

6 次实际调用均完成，34 个 artifact 的组件数据库审计及调用恢复事件审计均零
findings。本批没有发生 API 重试，不替代之前真实 429 恢复证据。两个模型的 claim
仍有可讨论的推断/覆盖问题，原始引文合法不等于整个 claim 获得充分支持；本阶段
没有按具体问题调整 instruction。

规格表的三条丢弃已定位为新的格式适配缺口：DeepSeek 的日期、容量数值正确，
只是在 `Intro.` / `RAM` 和 `</td>` 之间新增了制表符。仅在诊断副本中去掉该单元格
边界空白，三条都能定位到原始保存子串；生产引文匹配目前没有改动。下一步必须
处理这类 HTML 格式空白，同时保留数字、否定词、行列关系和原始偏移的严格校验。
证据在 `input-and-quote-verification.json`。上一阶段被排除的八条引文另作回查，
其中一条需要进一步分析 HTML 标签差异，不能笼统全部归为模型幻觉。

组件实验的首次 harness 把 tool wire range 直接用作 Workflow SourceRange，遗漏
schema_version；两份输入在 API 调用前被拒绝（实际模型调用为零）。失败目录
`recovered-source-distillation/` 原样保留并标记 withdrawn。修正后的实验通过
SourceRange.to_dict() 转换并先执行 pinned AgentSpec.render_task 检查，不把 harness
修复伪称为生产 workflow 故障修复。

本阶段进展已由实际网页、数据库和两种模型验证，但新发现的引文格式损失及剩余
结构边界尚未清除，持续目标继续 active。

## 第六阶段：引文格式回放与真实响应失败诊断

本阶段保持 baseline 12、各角色 instruction/schema、两个搜索轮次、40 URL 总额度和
256k Agent allowance。修复位于共享引文组件及 hardened distillation 的格式接缝。

`html-quote-replay-final/` 回放 422 条历史原始引文：上一轮完整矩阵的 387 条与
恢复页面组件实验的 35 条。原先通过的 411 条全部继续通过，另外恢复 4 条：
三条单元格边界 Tab，以及一条段落末尾可省略的 `</p>`。当前通过 415、剩余 7，
没有丢失旧匹配。对四条新增匹配逐个改写数字的 13 个变体均被拒绝，238 个输入
文件的哈希在回放前后保持一致。

HTML 适配只用于已知 text/html 来源中完整、无代码的存档表格。它不去掉行列、
span 或属性，不合并段落，不修正词语、数值或大小写；返回原始连续子串和原始
偏移。PDF、纯文本、代码和不完整源表格保持原有严格路径。集成测试通过真实
Runtime/SQLite 验证：正确格式变体进入 Analyst，改写容量的引文被排除，
Distiller 只调用一次，原始输出和 validation_changes 均可追溯。

剩余七条需要区分：一条涉及 Markdown 加粗边界，其余包括额外/缺失单词、
大小写、句尾标点及省略中间 HTML 文本。没有把它们全部称为模型幻觉，也没有
用模糊匹配放行。新一轮模型输出另发现多项列表引文省去列表标记，待独立检查。

`html-quote-live-distillation/` 再次运行三个相同材料、两个模型的实际组件实验。
DeepSeek：航班 7 条通过、2 条待查，规格表 6 条通过、食物 8 条通过；GPT：
航班 5 条通过、规格表 3 条通过，食物调用返回 provider.incomplete 并失败。
六次调用、零自动重启；数据库和恢复事件审计零 findings，冻结代码/输入核验通过。
不能把这批写成六个成功任务，也不能用新生成数量直接衡量校验修复效果。

该 GPT 失败是新的诊断缺口：数据库记录 native_finish_reason=incomplete、调用
身份、usage、可见文本摘要，但当时 provider adapter 丢弃 incomplete_details.reason
及响应 error.code，应用边界也未转发这些字段。旧调用缺失的细分原因不能事后
推定；零 usage 是 provider 原始声明，不能据此判为零输出或瞬时服务故障。

已修复上述原因留存链路：model.outcome、Agent terminal、role attempt 和 Workflow
错误均保留白名单原因、捕获状态、可见文本字节数、原始 tool-call 数和 continuation
是否超限。只对完全结算的、空输出/无工具调用的明确 server_error 或
insufficient_system_resource 采用已有有限等待/新 child 策略；truncation、filter、
未知原因和部分输出不进入该策略。Runtime/provider 仍然单次 dispatch。

修改前新增的 8 项 provider 原因留存测试和 10 项 host 分类恢复测试均失败；
修改后 provider、Runtime、应用恢复/输出边界共 **147 passed**，覆盖独立 child、
相同请求、原始预算/usage、零重启配置、unknown reason 和部分结果禁止重试。
这是受控 HTTP/真实 Runtime/SQLite 验证，不冒称重新观察到了真实 server_error。

`response-reason-live-probe/` 对上次 GPT 食物任务的同一输入作一次独立真实诊断调用：
成功，5 条引文通过，无重启；代码/输入冻结检查和数据库/恢复事件审计通过。
旧失败继续保留，不能用这次成功补写旧调用缺失的原因。

验证记录：HTML 引文定向测试 113 passed（随后增加 optional-p 与集成反例），
最终单元组 86 passed、HTML 方法集成组 10 passed。包含最终引文修复和 extraction 8
的完整测试为 **1610 passed、1 failed**（452.65 秒）：Windows 后代进程清理用例
观察到 cleanup_complete=true 时，PID 查询所得进程 handle 尚未 signal。
该进程组单独重跑 9 passed，随后相同场景 50 次未复现；这尚不足以宣告问题不存在。
原始失败日志保留为 `html-quote-full-tests.log`，重复记录在
`process-cleanup-repetition.json`。该次完整测试早于新增的 response 原因修复，
不能称为最终工作区的全量绿灯。Windows 清理竞争与 Markdown 引文格式边界继续追查。

## 第七阶段：Markdown 引文与原始进程句柄验证

继续冻结六个角色的版本和 instruction，仅处理传递与验证层的损失。
新增 MIT 依赖 `markdown-it-py==4.2.0`，用 CommonMark 解析结果识别加粗/斜体
边界及单层无序列表标记，不采用全局删除星号、连字符或模糊文本匹配。
适配后的引文仍返回存档的连续原始子串，保留原始 byte offset/digest；
禁止更改单词、数字、顺序，禁止跨段拼接或扁平化表格、代码、嵌套/有序列表。

跨读取片段的上下文也纳入验证：仅使用从文档开头连续覆盖、重叠一致的已存档
读取作为前缀（最多 2 MiB），识别当前片段是否仍处于代码块中。前缀不能提供
引文字节，也不扩大 Agent 输入。缺失、冲突或无法确认起始上下文时保留严格
匹配；HTML 表格适配采用相同保护。新增真实 Runtime/SQLite 集成检查证实：
正确格式引文到达 Analyst，数值改写被排除，Distiller 不因格式差异重复调用。

`markdown-quote-replay-final/` 回放 458 条历史/组件输出引文：449 条原有匹配
全部保留，新增恢复 3 条，最终 452 条通过，6 条仍不匹配；26 个数字改写变体
全部拒绝，261 个输入文件哈希不变。恢复的是一条加粗边界和两条列表标记差异。
剩余六条涉及大小写、句尾标点、增删词语及省略中间 HTML 文本；没有把它们
全部判为事实幻觉，也没有为了通过率放宽事实校验。回放只衡量传递/校验，
不证明模型报告事实正确或搜索覆盖充分。

Windows 进程检查改为在子进程仍存活时复制它的原始 SYNCHRONIZE 句柄到明确
指定的测试观察进程，在清理后作有界退出等待。这样观察同一个内核进程对象，
不依赖 PID 再查询。生产 `process.py` 本阶段未改。独立压力检查 100 次串行、
400 次四线程运行均未见未退出对象；不能反推旧失败的确切原因或证明永不复现。
进程/实际 Chromium 清理测试最终 11 passed，原始失败日志继续保留。

本阶段验证脚本的两个错误单独保留：最初误把 venv 启动器的父进程当成句柄
观察者，已改为显式 observer PID；超长参数自动生成的 pytest ID 超出 Windows
环境变量 32767 字符限制，已改为短 ID。它们不计为产品故障或修复收益。
最终引文/方法/恢复机制定向测试 **183 passed**（59.84 秒），随后完整测试
**1670 passed**（495.82 秒）。这次全量绿灯包含最终 Markdown 修复和前阶段
response 原因留存/分类恢复；尚不包含下一节新发现的 scholarly URL 修复。

`format-model-regression/` 冻结运行三个原题/两个模型，保留 baseline 12、40 URL、
两轮、256k Agent allowance 和原有角色；165 个角色资源文件哈希未变。六次任务
中五次成功：DeepSeek 头显 sufficient，两个航班和两个睡眠 partial；GPT 头显
因 Crossref 元数据错误中断，不生成报告。五份实际报告已读完。107 次模型调用
均无 provider 错误、无瞬时重启，1 次格式修复，无 Distiller quarantine。
1141 个 artifacts、55 个 snapshots、122 个读取片段、293 条通过引文已审计，
五条引文被排除；数据库、原文输入、来源绑定和恢复事件审计均无 findings。
计数只证明对应记录链路，并不证明事实正确或覆盖充分。

报告中仍存在 baseline/模型问题，例如 DeepSeek 航班表把不含中转等待的飞行时间
放进“总时长”列，而后文又保留了该限定；睡眠报告混用部分观察性/实验性证据
的描述。没有针对此类表现修改问题或 instruction。五条被排除引文分别涉及
Markdown 表头分隔线、HTML span、缺失 HTML 开标签、增添词语以及改写时态。
其中格式边界仍需追查，不能笼统算为模型幻觉。

离线 PDF 诊断还发现已存档 Annual Reviews 文本含 `Itispossiblethathoney` 等
连写。对同一 PDF 第 9 页，现有 pypdf 的 layout 模式保留了对应词间空隙；
该诊断不更改生产 PDF 提取器，尚未验证全语料阅读顺序、表格或字体。
对应被拒绝引文同时增添了 `as`，不能说修复空隙就会使该引文完全准确。
记录在 `pdf-spacing-diagnostic-verified/`；首次脚本按 final_url 而非 requested_url
筛选，未找到重定向后的 PDF，该无结果尝试已标为 withdrawn。

## 第八阶段：坏元数据隔离，避免局部搜索故障中断全流程

上节 GPT 头显在第二轮 Crossref 搜索拿到 HTTP 200 后，报 `INVALID_ARGUMENT`
和 `transport_unavailable`，并被 Workflow 误判为外部状态未知而中断。
同查询的真实诊断请求复现了根因：一个返回条目的 supplemental URL 字段包含
两个用空格拼接的网址，其余四条记录正常。响应原字节保存在
`crossref-url-diagnostic/`，不覆盖历史失败，也不假定新响应与旧响应逐字一致。

修复位置是 provider 元数据投影与 orchestrator discovery 边界：revision 2
保留有效记录、有效链接和 DOI，仅剔除非法 supplemental link，或将可空位置
URL 标成 null；已有 `bibliography.invalid_fields` 记录原始投影路径。URL 不
猜测、不拆分、不修补，原始 provider 对象不修改。revision 1 保持严格拒绝，
但错误正确分类为 `SCHOLAR_PROTOCOL_ERROR` / `invalid_provider_response`。

对于整个响应无法采用的情况，仅在一请求/一 HTTP 200 响应、正常 worker
退出、完整 recording/cleanup、无 publication 的事实齐全时，允许保留先前
候选并继续其他 backend。失败仍存档，不重复调用坏响应，不放行未知效果、
存储承诺或清理状态，也不增加共享预算。这是 orchestrator 的故障隔离，
与模型 API 的有限退避重试分别处理。

修复前 11 个 URL 用例全部失败，backend 继续用例失败；修复后相关组
**165 passed**，随后包含真实 Windows worker/Runtime/SQLite 的组
**52 passed**，验证失败结果可读、有效候选保留、独立 attempt 和共享预算。
既有 closed DTO 与角色资产不变。

真实 CLI `crossref-live-fixed-store` 对同查询成功返回五条记录，仅标记并剔除
`links[0].url` 那个坏链接；完整记录和数据库审计通过。独立重跑
`scholarly-fallback-regression/` 的原始 GPT 头显问题成功并生成英文报告：8 次
fetch 尝试、5 次成功、13 次模型调用；冻结检查、数据库审计通过。
这是新运行，不把原批次的 5/6 改写成 6/6，也不将模型自行报告 sufficient
当作外部事实正确性证明。新报告已读完，126 个 artifacts、6 个读取片段、20 条
引文的审计无 findings，无排除引文、格式修复或瞬时重启；11 份含 question 的
输入原文一致，165 个角色文件与前批相同。最终完整回归 **1700 passed**
（481.92 秒），`git diff --check` 通过。PDF 连写、HTML 行内标签/Markdown 表头
引文边界以及未解决的结构告警仍留作后续系统性检查，整体目标未宣告完成。

## 第九阶段：PDF 连写的逐页修复与独立解析器检查

本阶段继续固定 baseline@12 的两轮/40 URL 策略和六个角色版本，只改变
web.fetch revision 2 的 PDF 文本提取。对历史数据库中 13 份不同原始 PDF
（315 个物理页）只读导出，检查原始与已归档文本的 SHA-256；历史记录不修改。
语料包含睡眠论文、旋转表格、194 页 RFC、EBD 文献、混合现实、乌克兰文及
其他学术资料，不以一个问题的报告表现调整 instruction。

试验环境对比 pypdf plain/layout、PDFium、pdfplumber/pdfminer 和 PyMuPDF。
layout 能恢复部分空格，但在旋转表格及一些页面发生丢字/次序问题；不能直接
全量替换。人工查看了原始 PDF 的第 9 页正文和另一论文的旋转表格截图。
最终生产路径使用 PyMuPDF 1.28.2 的原始顺序文本（sort=False），逐页与
pypdf 6.19.0 比较：非空白字符与顺序须一致，已有词间/换行边界和缩进不得
减少，数字中间不得新增空白。原解析中的单个未解码控制字符可由原生 glyph
替代并单独计数。比较流式执行，避免每页创建两份巨大字符索引数组。
不一致或原生解析器失败时整页回退；严格 PDF admission、物理空白页、字节
配额和原始文件保持不变。revision 1 与旧 snapshots 的内容不改变。

新增可选 `provenance.pdf_extraction`，经 closed tool schema、SQLite snapshot
及 Workflow source descriptor 传递。记录 native/fallback/changed 页数、回退
原因、解码/未解码 glyph 数和 warning 数；明确 `semantic_verification=false`。
采用 PyMuPDF 开源 AGPL-3.0 版本，依赖与 lockfile 同步。

验证证据位于 `local/fidelity-cycle-20261003/`：

- `pdf-recovery-replay-final/`：13 份/315 页均保留原始哈希与物理页数；对照提取
  与历史归档字节一致。22 页采用新提取，293 页回退，逐页字符/顺序保护检查通过。
  Annual Reviews 的 35 字母以上连写计数由 136 降到 60，这只是诊断指标，
  不是准确率；第 9 页先前发现的正文空格恢复。仍有 12 页回退及 4 个未解码
  控制字符，不能宣称 PDF 问题已全部修复。
- `pdf-recovery-tests.log`：181 passed。包括实际字体/定位造成的连写 PDF、数字
  和单位改变、大小写/否定/顺序、缩进/换行丢失、整页回退、空白页、native
  打开/页面失败、页数不一致、加密/坏文件/页数/字节配额和资源恢复。
- `pdf-recovery-live/`：真实 Windows worker fetch 三份 PDF（24/8/194 页），
  经 SQLite 提交并以 4096 字节上限进行 174 次 document.read。三份完整读取与
  归档字节/哈希一致，零验证错误；峰值 Job 内存约 129/88/114 MiB，低于
  原有 512 MiB 上限。数据库完整性、外键、pending operations 和清理检查通过。
- `pdf-recovery-live-distillation/`：固定原文 `What food can help me sleep well?`，
  同一份实际读取结果交给原版 Distiller 4。DeepSeek/GPT 各一次调用、各 6 条
  引文通过来源匹配，零 schema error/invalid finding/restart。两个输出均已读；
  这不验证每条 claim 的完整语义支撑，也不是新一轮完整报告质量比较。冻结
  检查、数据库与 recovery journal 审计通过。独立组件 store 的通用审计不
  识别 baseline digest 格式，12 条引文的验证证据在组件 summary 中。
  与前一完整三题批次逐文件对照，165 份角色资源均未改变。

初次 PDFium 对比脚本误用 page context manager，其失败不作为库能力结论，
已用 `pdfium-comparison-verified/` 替代。首次生产回放比较了带 `sha256:` 与不带
前缀的哈希，属于测试脚本错误，已标记 withdrawn；最终回放按字节验证。
额外 12 个独立进程/不同 hash seed 的 pypdf 对照得到同一文本哈希。

剩余问题包括回退页的连写/未解码 glyph，以及前述 HTML 行内标记和 Markdown
表头引文边界。两模型在本次组件测试没有失败，不代表这些损失已消失；整体
目标仍未宣告完成。本轮最终完整回归 **1730 passed**（454.17 秒），
`git diff --check` 通过。源码与实验输入冻结检查通过；未改写之前的 5/6
完整报告批次，也未将这次两次蒸馏冒充两份新报告。

## 第十阶段：表格引文边界与重复解析开销

三题对照中另两条引文误拒来自格式：航班引文保留了两行的单元格分隔符，但
省略了 Markdown 表头 delimiter；头显引文把同一单元格内嵌套的无属性 span
显示为纯文本。这一阶段保持 baseline@12、原始问题、六角色 instruction 与
输出 schema 不变，修复 source-mapped quotation adapter。

CommonMark parser 确认完整表格后，只允许略过第二行 delimiter，保留每一行
原文、顺序、列分隔符。HTML 只在完整、非代码表格的一个单元格内允许省略
成对、无属性的 span/b/strong/i/em；不删除结构块、属性、脚注链接、sub/sup、
编辑标记或注释，也不跨单元格/行组合文字。结果还原为实际归档的连续片段，
保持 2048 字符上限、原始偏移和哈希。另修复 XHTML gate：fetch 已支持
application/xhtml+xml，蒸馏适配现在与 text/html 使用相同规则；PDF/纯文本
仍不按 HTML 解析。

回放还暴露了独立的主机开销：每条引文重复解析同一 read 及其 document
prefix。某个真实航班来源的 9248 字节 read、144054 字节 prefix，对 7 条
引文反复匹配耗时 28.56 秒；复用原型为 4.05 秒，结果相同。生产实现复测
为 22.18 秒→3.22 秒，结果相同（quote-locator-production.json）。这些是本机
诊断测量，不能视为所有文档的固定加速比。生产新增 PreparedQuoteSource，
在一次 validate_distillation 调用内按 segment 懒加载复用来源投影，以 packed
unsigned index 存原始字符位置；不缓存模型输出或匹配结论，不跨来源/调用
共享状态，不增加 read/context 权限或额度。完整缓存回放检查了精确片段及
字节位置，而不是只比 accepted 数量。

证据位于 `local/fidelity-cycle-20261003/`：

- 新格式用例修复前 8 failed / 41 passed；修复后相关组 188 passed。随后扩展
  真实 SQLite→distillation→Analyst 输入的用例，18 passed：格式引文进入证据，
  数字被改动的引文排除，且不额外调用模型。缓存落地后的相关组 190 passed。
- `markup-boundary-replay/`：三批历史输出共 705 条；694 条既有匹配全部保留，
  新恢复 2 条，9 条未匹配。两处数字变异均拒绝，425 个历史文件哈希未变。
  不改写历史 validation artifacts，不把恢复计数当作模型准确率。
- `markup-boundary-models/`：对两个原始问题的同一份历史真实读取分别调用
  DeepSeek/GPT Distiller 4，共四次真实调用、19 条引文，零 schema/quote error，
  零 restart；数据库和 recovery journal 审计通过。输出已人工读过，存在
  claim 比选中引文更宽的情况，来源网页本身也可能过时；字面匹配不验证事实
  真伪或完整语义支撑。这是组件测试，不是四份新报告。165 份角色资源与
  上次完整三题批次相同。该真实模型轮次在缓存优化之前；缓存后的等价性由
  下述回放与实际存储链路检查承担。
- `quote-locator-candidate-equivalence.json`：原型在 3460 组格式、上下文和
  非法输入组合上与未缓存实现一致。正式缓存边界组 58 passed，验证同一
  来源仅解析一次、不同来源不串用、未知/代码上下文、UTF-8 和长度上限。
- `quote-cache-replay/`：生产缓存对上述 705 条引文返回完全相同的原始片段和
  字节位置；425 文件未变。整个回放 81.42 秒，单个 input 的 packed indexes
  最大 6,086,480 字节；这是索引数据大小，不是整个 Python 进程峰值内存。

9 条未匹配的原文对照保存在 `markup-boundary-remaining-inspection.json`：
包括冒号改句号、重复 the、删除 Apple、更换开头、大小写变化、跨过解释性
内容、缺失 HTML wrapper，以及 PDF 连写同时增添 as、was 改 is。它们不通过
模糊匹配放行。已知 PDF 连写仍继续修复；不把模型改写误归为工具错误。

有一组超长参数测试未指定简短 pytest id，触发 Windows 环境变量 32767 字符
限制，产生的是测试 harness error；已加显式短 id，最终 58 项通过。只用于
定位慢调用的重复进度探针在取得定位后终止，未作为完整回放结果。

对 PDF 回退页的新诊断发现，一处旧提取器生成的多余空格会让整页新提取回退，
例如单词/单位内部或括号后空格。`pdf-spacing-insertion-probe/` 是尚未入生产
的候选：只按另一解析器的明确词间空隙添加空格，保留全部旧字符与排版，
对 13 份 PDF 进行离线检查；问题论文的长连写从 60 降到 20，但仍保留旧的
错误空格和未解码 glyph，也改变了另一篇论文的部分词间空格，需要继续验证。
这不是本轮已交付修复，整体目标仍 active。

格式修复、缓存前完整回归为 1781 passed（512.32 秒）。缓存与 XHTML gate
之后的最终完整回归 **1792 passed**（450.62 秒），`git diff --check` 通过。

## 第十一阶段：PDF 整页回退中的局部空格与字形恢复

继续保持 baseline@12、40 个 attempted URLs、两轮、256k 单 Agent allowance
以及六角色 instruction/schema 不变。第十阶段候选继续验证后，生产提取版本
更新为 `pdf_text/3+pymupdf/1.28.2+pypdf/6.19.0`，未增加解析器依赖。

根因是一处不兼容排版就让整页放弃新的词间距。现在先尝试原有整页校验；
失败时再完整流式对齐两份非空白字符序列，只补另一解析器明确给出的 ASCII
空格，限相邻字母/数字之间且不拆开连续数字。每一个旧空格、换行、缩进和
尾部排版仍保留。字符或顺序在页内任何位置不一致，整页都不采用局部候选，
不会保留失败前的部分改动。C0/C1 未解码控制字形仍可被逐字替换并单独计数，
但 replacement character、私用字形或不可见字符不再算成功解码。增长继续
受 UTF-8 页/文档字节上限约束。

诊断 `page-text-preservation/2` 增加 recovered_pages、inserted_spaces 和
recovery_reasons；native + recovered + fallback 等于物理页数。旧 method /1
仍通过自己的封闭 schema，不能混用字段。诊断继续明确
semantic_verification=false；未解码控制字形为零不代表所有字体都正确。

证据位于 `local/fidelity-cycle-20261003/`：

- `pdf-spacing-guards-tests.log`：44 项 PDF 检查通过，包括真实定位字体、数字/
  否定词/字符顺序、后段失败时原子回退、不可见字形、UTF-8 增长和资源关闭。
  较早的相关测试组 `pdf-spacing-tests.log` 为 192 passed。
- `pdf-spacing-replay/`：同一批 13 份原始 PDF、315 个物理页，原始文件与历史
  文本哈希核对通过。22 页使用整页原生文本，19 页局部恢复，274 页回退。
  新增 1057 个词间空格；问题综述剩余 60 处长度至少 35 的英文连写降为 0，
  11 个控制字形成功解码。字母串统计只衡量格式，不是准确率。
- `pdf-spacing-character-audit.json`：41 页相对旧 pypdf 文本发生变化，全部
  非空白字符数量相同，其中 30 页字符本身完全相同，其余涉及已计数的控制
  字形替换。逐页完整的字符/排版检查另保存在回放断言中。
- `pdf-spacing-live/`：真实 Windows worker fetch 24/8/194/9 页的四份 PDF，
  经实际 SQLite 和 4096 字节分页接口完成 189 次全文读取，档案及全文哈希、
  页码和 UTF-8 索引检查全部通过。Windows Job 峰值约 130/88/113/145 MiB，
  低于原有 512 MiB 上限。生产文件冻结校验通过。

人工查看了问题综述第 10 页与 Nature 第 2 页的渲染页。Nature 的
`d a n c eﬂoor`、`T h i s` 散字在旧档案中已存在，新结果继承了旧空格，
不是此次引入的回归。此前临时归因已在对话中纠正。当前修复也保留了部分
标点后的缺空格，例如 `sleep.In`；不能凭“长连写为零”宣布提取完整。

独立 PDFium 样本能显示上述词的正常间距，但同页多处换行连字符解码成
控制字符，整页严格一致性检查失败。`pdf-spacing-secondary-disagreements.json`
保留了这项诊断，七种拉丁连字展开仅用于离线比较，不改变归档输出。
未将 PDFium 加入生产依赖，未启用自动删除旧空格、词典猜词或模糊引文匹配。
后续仍需处理这些已确认的提取损失；整体目标保持 active。

真实模型与正式蒸馏阶段的结果分别记录，不把失败轮次覆盖成成功：

- `pdf-spacing-live-distillation/` 直接调用 Distiller 4：DeepSeek 的两篇共
  15 条引文通过；GPT 第一次输出在一个对象中重复 `claim`，严格 JSON 校验
  正确拒绝，原始 3265 字节响应完整保留。API 正常结束，没有截断或调用故障；
  GPT 的第二篇未执行。这一组件调用没有进入 baseline 的格式修复循环。
- 原始组件脚本复用了全文验证的逐次读取，其中含分页边界重叠行，误把唯一
  文档字节数填成了这些片段的 read_bytes。生产 source_access 本来就会验证
  并去重。正式阶段测试首次准备时由断言发现此事，尚未调用模型；日志为
  `pdf-spacing-formal-distillation.log`。这是测试脚本问题，历史输入不改写。
- `pdf-spacing-formal-distillation-verified/` 在已关闭的真实 fetch store 副本
  上运行生产 `distill_sources(isolate_errors=True)`。对两个原始问题保留实际
  字节范围，验证并去掉重复边界后，两模型接收相同来源。两模型均完成，两篇
  各一条逻辑蒸馏任务，共五次模型调用：DeepSeek 睡眠任务的首个 JSON 缺少
  分隔符，现有两次上限内的格式修复成功；其余三任务一次完成。原始 store、
  instruction 和生产文件冻结校验通过。它是正式阶段测试，不是全 workflow
  或四份研究报告。
- 正式阶段保留 28 条引文、排除 1 条，零隔离来源。数据库审计验证 58 个
  artifacts、82 个 segment、28 个 findings；integrity/外键/未决操作/哈希与
  来源绑定均正常。API recovery journal 为五次已结算调用、零 API restart。
  这里的格式修复与 API restart 是不同机制，前者由 distillation 两次循环承担。

排除的 GPT 引文揭示了尚未修复的提取损失：档案是
`tryptophan,serotonin,and melatonin`，模型引文补回两个逗号后的空格，因而被
严格匹配拒绝。它不是模型增词或数字错误；`review-diagnostics.json` 保留了
原始引文与对应来源。当前版本只补字母/数字之间的空格，尚未处理这类标点
间距，后续必须验证数字、标识符和原始定位再修复，不能改 instruction 强迫
Agent 适应坏文本。已读过四份正式蒸馏结果；部分 claim 仍宽于选中引文，
字面绑定通过不证明语义支撑完整。

本阶段最终完整回归 **1806 passed**（429.56 秒），日志为
`pdf-spacing-full-tests.log`；`git diff --check` 通过。修复、真实工具和模型
验证均已结束，没有遗留运行中的测试或模型任务。PDF 标点间距及旧词内散字
仍为明确的后续项，未把整体目标标为完成。

## 第十二阶段：独立解析器与字符坐标恢复 PDF 间距

继续冻结 baseline@12 的研究策略、40 URL/两轮/256k allowance、六角色
instruction/schema 和用户原始问题。本阶段改动仅在提取工具及其依赖、测试
和文档。pypdfium2 5.13.0 加入正式依赖，其他已锁定包版本未变。

`pdf_text/5+pymupdf/1.28.2+pypdf/6.19.0+pypdfium2/5.13.0` 保留 pypdf 的
完整字符/顺序核对；PDFium 只提供独立间距证据，不直接提供输出字形。两个
解析器整页非空白字符序列必须对齐，七种拉丁展示连字仅用于比较展开。
PDFium 的单字符 C0/C1 占位允许对齐，但相邻边界没有修改权限。删除词内
单个 ASCII 空格和恢复标点空格都需独立边界证据；未知结果保留旧文本。

Nature 第 5 页另有一整行狭窄词距：PyMuPDF 将词连写，PDFium 识别了多数
空隙。人工查看原始渲染页及字形坐标后，增加了有界坐标校验：同一水平
baseline/font/size 的字母间存在正间隙，才能确认 PDFium 单独观察到的空格。
同一行至少三个已观察到的词间隙还可校准大小相同的遗漏间隙（误差不超过
字号的 0.2%）。不跨行、字体、字号、方向借证据，不按词典拆词。字符字典
禁用图片，且仅在页文本不超过 32768 UTF-8 字节时读取；失败单独诊断。
这使 `Beesthatusethisstrategysampleadancefromthedanceﬂoor` 恢复为正常间距。
原始 pypdf 此处也是散字与连写混合，不能把历史坏文本描述成正常词句。

连续数字及明确数值形式受到保护；逗号列表和串联文献字段不能直接当作一个
数值。早期 /4 候选的数值识别过宽，将 `3,18,31`、日期逗号和文献年份间隔
也保护起来。虽然它通过 1853 项测试并完成五份 PDF 真实读取，人工检查发现
它妨碍正常格式恢复，因此由 /5 修正，历史实验保留。`pdf-consensus-numeric-repairs.json`
里 50 个“corrected_tokens”是该临时脚本的命名，**不是已证实的 50 个数字错误**；
其中很多实际是引用列表，不能把这个数当作准确度提升。

诊断版本为 `page-text-preservation/4`。除插入/删除空格及独立解析器结果外，
还记录几何校验页数、确认边界数和尺寸/不可用/字符不一致原因；历史 /1–/3
继续按各自封闭 schema 接受。semantic_verification 仍为 false。确认边界数
可包括原来已有的空格，不与实际输出插入数相加。

证据位于 `local/fidelity-cycle-20261003/`：

- `pdf-geometry-tests.log`：111 项针对性检查通过，覆盖整页后段不一致的原子
  回退、独立解析器失效/关闭、UTF-8 上限、数字保护及逗号列表反例、字体/
  字号/baseline/旋转隔离、非有限坐标和几何字典上限。
- `pdf-geometry-replay/`：13 份相同原始 PDF、315 页、全部原始/历史文本哈希
  核对。22 页采用整页原生文本、59 页局部恢复、234 页保留旧文本；57 页相对
  /3 改变。局部恢复插入 2342 个空格、移除 475 个多余空格；全部非空白字符、
  页码、换行/缩进和 9976 个明确数值片段检查通过。61 页尝试独立对照，57 页
  对齐、4 页内容不一致；11 页进行坐标校验，确认 174 个边界。生产冻结校验
  通过，回放耗时 12.89 秒。控制字形替换仍单独计数。
- `pdf-geometry-quote-repair.json`：第十一阶段 GPT 因逗号空格被误拒的原始
  引文在 /3 中匹配不到，在新档案中唯一匹配到第 10 页；两条改动食物/成分
  名称的负例仍被拒绝。没有改 quotation validator 或角色 instruction。

这些检查不证明所有 PDF 的版面或语义都完整；234 页回退中既有正常文本，
也有读取顺序/字形分歧，需结合实际读取与模型结果继续判断。

最终 /5 的真实验证（不同于上面的 /4 候选）：

- `pdf-geometry-live/`：五份 24/8/194/9/18 页 PDF，经 Windows worker、SQLite
  和 4096 字节分页接口完成 205 次全文读取；五份档案/全文哈希、索引、页码、
  UTF-8 检查均通过，生产冻结校验通过。Windows Job 峰值分别为约
  138.0/88.6/113.5/149.2/100.8 MiB，未提高 512 MiB 上限。
- `pdf-geometry-model-inputs/`：从上述实际读取构建睡眠、蜜蜂、EBD 三份输入，
  按真实偏移验证并去除重复窗口边界；两模型使用相同来源和原始问题。
  EBD 仍为 `What is EBD (Environment Based Design)?`，没有改写或加提示。
- `pdf-geometry-formal-distillation/`：在已关闭的真实 fetch store 副本上运行
  正式 distillation stage，两模型各完成三份蒸馏，共六次真实模型调用，零
  格式修复、零 API restart、零来源隔离；保留 45 条引文、排除 4 条。数据库
  审计核对 72 个 artifacts、5 个 snapshots、114 个 segments、45 个 findings，
  integrity/外键/未决操作/哈希/来源绑定与 recovery journal 全部正常。
  生产文件、角色资产和原始 store 均未改变。这是阶段检查，不是六份报告。

四条排除结果均已逐字追查，不能归为模型能力不足：

| 任务 | 原因 | 已确认的证据 |
| --- | --- | --- |
| 睡眠 DeepSeek | 引文跨越两个连续已读片段 | 拼接相邻已授权的原始字节后，当前匹配器可精确匹配 |
| 蜜蜂 GPT | `dan-` 换行后接 `ceﬂoor`，ASCII-only 软换行规则不接受展示连字 | 仅在离线探针中把七种展示连字纳入字母边界，原始引文即可匹配；未改变归档字形 |
| EBD GPT，设计原则 | 重复页眉插入一个跨页句子中 | 原始文本完整保留 `Transactions of the SDPS ... pp. 55`，模型引用的是去掉页眉后的正文句子 |
| EBD GPT，三个活动 | 引文跨越连续已读片段 | 拼接相邻原始读取后，当前匹配器可精确匹配 |

`remaining-quote-boundaries.json` 保存原文、匹配结果和实际片段 ID。现行
ExtractedFinding 只带一个 segment_id，证据收缩和 ContextSelection 也使用
单次 read_action_id；后续修复必须同时保留多段读取的独立来源证明，不能
伪造一个覆盖多个读取的 action，也不能把未交给 Agent 的相邻内容拿来匹配。
页眉需基于文档结构处理，不能为 EBD 写一个关键词删除规则。以上四条仍未
在生产修复，整体目标保持 active；/5 修复的是前述间距提取损失。

最终全量回归：`pdf-geometry-full-tests.log` 记录 1873 项测试全部通过，
耗时 415.99 秒；`git diff --check` 通过。这些回归结果不代表上述四条
已确认的引文损失已修复。

## 第十三阶段：跨读取引用绑定与连字软换行

第十二阶段的两条引文跨越连续已读片段。现行单片段验证把这些实际已交付
的字节误判为不存在。新增共享组件 `workflows/components/quote_bindings.py`，
仅在同一次蒸馏输入内按已验证字节偏移形成连续窗口；不从完整档案或其他
chunk 补入内容。边界两侧各保留最多 2048 字符，原始返回引文仍最多 2048
字符。空隙、重叠、非唯一跨段匹配不能授权拼接。

Agent 仍输出原来的 segment_id/quote。宿主把首段作为锚点，另外记录各段的
真实范围、哈希及独立 read_action_id。删除无效 finding 后重新建立绑定索引。
证据压缩逐段保留这些字段，ContextSelection 不伪造跨调用 action。审计器
同时检查绑定、实际模型输入、读取清单和不可变档案字节。旧记录仍可审计。

另外把七种拉丁展示连字加入软换行的字母范围，不转换字形，不忽略大小写，
不拼接数字或标识符。这修复 `dan-` 换行后接 `ceﬂoor` 的误拒。
baseline@12 的轮次/预算、六个角色版本及 instruction/schema 均未改变。

证据仍位于 `local/fidelity-cycle-20261003/`：

- `cross-read-tests-final.log`：141 项针对性检查通过；随后增加了正式证据
  压缩和 SQLite 审计检查，`cross-read-integration.log` 的 21 项全部通过。
  后者包含实际 Engine/Runtime/Storage，外部模型与 fetch 响应受控；验证
  两段独立读取在压缩后保留，伪造 action/哈希、漏读、空隙、重叠、歧义、
  UTF-8、多段短读取及两个接近 64 KiB 的读取边界也被覆盖。
- `cross-read-replay/results.json`：对第十二阶段相同六份原始输出的 49 条
  引文逐条回放，45 条保留增加到 48 条，三个已确认误拒全部恢复，剩下
  一条页眉插入。每条保留结果经 `_quote_units` 核对，历史文件哈希不变。
- `cross-read-history-replay/summary.json`：705 条历史引用的返回原始字串与
  字节位置全部相同，425 个原始文件未改动，耗时 60.203 秒。此回放检查
  单段匹配回归，不用于宣称跨段功能完整。
- `cross-read-formal-distillation/`：新六次真实模型调用全部完成，零格式
  修复、零 API restart、零来源隔离，保留 33 条引文、排除 4 条。强制
  30000 字节的阶段证据压缩后，各来源生成 4659–8823 字节上下文；所有
  ContextSelection 均逐一核对原始档案字节和所属读取 action。
  数据库审计 78 个 artifacts、5 个 snapshots、114 个 segments、33 个
  findings 全部正常，recovery journal 为六次逻辑调用/六次实际尝试。
  新输出没有跨段引文，不能把这轮描述为实际触发了跨段修复。
- `cross-read-saved-stage-verified/`：把第十二阶段的六份原始模型输出作为
  明确标注的回放响应，执行正式 distill_sources、证据压缩和 SQLite 写入。
  六份调用输入与历史输入逐字段相同，零新模型调用，保留 48 条、排除
  页眉插入的一条；两条真实历史跨段引文在该链路产生独立读取绑定。
  审计 60 个 artifacts、5 个 snapshots、114 个 segments、48 个 findings
  全部通过。原始 fetch store 哈希不变。最初的 `cross-read-saved-stage/`
  包装脚本因变量定义顺序错误在调用业务前停止；保留失败目录，新目录
  验证成功，不能把回放计为六次新模型调用。
- `cross-read-full-tests.log`：最终全量 1907 项通过，耗时 451.32 秒；
  `git diff --check` 通过。上述针对性检查有重叠，不叠加为测试总数。

新一轮四条排除结果的原因：

| 输出 | 逐字核对的原因 | 分类 |
| --- | --- | --- |
| 睡眠 DeepSeek | 跨页句子间夹入页脚、页码及下载水印 | PDF 结构处理损失，未修复 |
| EBD DeepSeek，定义 | 档案保留 `Environment -Based` 和 `step- by-step`；PyMuPDF/PDFium 都没有这些额外空格 | PDF 连字符间距损失，已由独立解析结果确认，尚未修复 |
| EBD DeepSeek，原则 | 同第十二阶段，跨页句子中插入重复页眉 | PDF 结构处理损失，未修复 |
| 睡眠 GPT | 引文将原文 `tryptophan` 的首字母改成大写 | 模型引用改写，仍严格拒绝；不以全局大小写折叠放宽事实引用 |

`pdf-remaining-layout.json` 的只读坐标探针确认，普通正文也会出现在页面
顶部/底部的 10% 范围内。因此不能简单裁掉页面边缘来解决页眉问题；需要
复用真实版面、跨页重复及字节映射证据，并保留原始档案。该探针不是已
上线的结构修复。整体目标继续 active。
`pdf-hyphen-spacing-probe.json` 同时保存三个解析器在该段的结果：pypdf
引入连字符两侧空格，PyMuPDF 与 PDFium 在词内连字符上相互一致；这为
下一轮通用间距修复提供证据，不授权全局删除标点旁空格。

## 第十四阶段：PDF 版面标记与连字符间距

当前采用 `pdf_text/7+pymupdf/1.28.2+pypdf/6.19.0+pypdfium2/5.13.0`，
诊断 `page-text-preservation/6`，结构标记 `repeated-page-margins/2`。
原始 PDF 与归档正文完整保留。新的 `pdf_layout.py` 先组合完整视觉行，
再依据边缘位置、相对字号、至少三页的重复以及一致的页码变化判断页边
文字。短旋转图表标签不会被当作长侧边水印。标记以原文字节范围和哈希
绑定，包含物理分页位置；大小/数量限制与遗漏明确计数。

`pdf_quotations.py` 只为同一次实际输入中完整读取的标记提供比较投影，
而且匹配必须跨越已知物理分页。返回的仍是完整连续原文，包含其中的页眉、
页脚和水印，2048 字符上限及各段读取 action 不变。单词、数字、标点或
大小写均不做模糊匹配。段落中的行内连字符空格另外经过两个独立解析器及
同字体/字号/baseline 的紧邻字形坐标确认后恢复，不处理数值或标识符。

早期 `/6` 提取与 layout `/1` 候选在人工复核中发现三处 RFC 正文 `MAY`
误标。原因是 PDF 把小号粗体词拆成独立文本块，候选规则没有先重建完整
视觉行。新增 MAY/MUST/NOT/optional 四种混合字号行和短图表轴标签反例，
旧候选五项均失败。修正版基于整行关系解决该问题，没有添加 RFC/关键词
排除规则。旧 layout `/1` 保留为诊断数据，禁止用于引用省略。早期
`pdf-layout-live/` 的五次抓取和 205 次读取仍可审计，但不能作为最终结构
识别效果的证据；中间全量测试日志也不替代最终版本检查。

最终版本的证据位于 `local/fidelity-cycle-20261003/`：

- `pdf-layout-v2-tests-final.log`：195 项针对性检查通过；
  `pdf-layout-v2-full-tests.log`：**1948 项全量通过，557.82 秒**。
- `pdf-layout-v2-replay/`：同一组 13 份 PDF、315 页，9976 个明确数值片段
  保持原样，非空白字符及顺序、页码、换行与缩进检查通过。相对 /5，
  14 页有间距变化，共额外删除 25 个确认多余的空格。结构识别检查 311 页，
  跳过 4 页，保留 280 个标记；RFC 受 32 KiB 元数据上限遗漏 15 个标记，
  已明确记录，无候选数量截断。人工查看标记类型及原文字串，三处 MAY
  均不再被标记。回放耗时 19.546 秒，生产冻结校验通过。
- `pdf-layout-v2-history-replay/`：705 条历史引用的原始返回字串及位置相同，
  425 个历史文件未修改，耗时 89.969 秒。该检查用于排除单段匹配回归。
- `pdf-layout-v2-isolated/`：仅补充从原始 PDF 重新计算的结构标记，历史
  Agent 输入、输出及读取字节不变，没有伪造新 fetch 或提取身份。第十二
  阶段引文 48→49 条；第十三阶段 33→35 条。共恢复三条页边文字造成的
  误拒，所有返回引文仍经过真实片段的 `_quote_units` 校验。这是离线
  变量隔离检查，不是新模型调用。
- `pdf-layout-v2-live/`：五份 PDF 实际下载、SQLite 存档及 205 次 4096 字节
  全文读取通过，原始/全文哈希、索引、UTF-8、页码、生产冻结及关闭检查
  通过。Windows Job 峰值分别为 145334272、97112064、121856000、157097984、
  106557440 字节，512 MiB 上限未提高。
- `pdf-layout-v2-formal-distillation/`：两模型各完成睡眠、蜜蜂、EBD 三个
  正式蒸馏任务，六次真实模型调用，零格式修复、零 API restart、零来源
  隔离；保留 40 条引文，排除 5 条。每份证据强制压缩后核对原始读取
  action、范围及哈希。SQLite 审计 78 个 artifacts、5 个 snapshots、
  114 个 segments、40 个 findings 全部通过。原始问题、角色与 instruction
  未变。这是阶段验证，不能算作六份新报告或覆盖完整 workflow 的结论。

新模型输出仍暴露以下问题，整体目标保持 active：

| 排除项 | 原因与状态 |
| --- | --- |
| 睡眠 DeepSeek | 模型把原文 `Refeeding` 写为小写；对应页脚/水印其实已标记。属于引用大小写改写，仍拒绝 |
| 蜜蜂 DeepSeek，图注 | 模型把原文 `The` 写为小写，仍拒绝 |
| 蜜蜂 DeepSeek，指数分布 | 原文词距为 `theﬁrst`，模型引用为 `the ﬁrst`；同段公式还有 `/C0` 字符映射，待继续修复/验证 |
| 蜜蜂 DeepSeek，反馈机制 | 原文同页出现 `pro ﬁtable` 与 `proﬁtable` 两种间距，模型复制得不一致；PDF 字体/词距仍需继续追查 |
| EBD DeepSeek，结论 | 页脚 `pp. 68` 未被当前结构规则识别，跨页句子仍被误拒；不能把之前恢复的定义段视为全篇解决 |

`pdf-layout-v2-exact-boundaries.json` 保存经水印信息遮盖的定位摘录。
`pdf-layout-v2-remaining-readers.json` 对比三个解析器后，又发现更底层的
线索：pypdf 在 CFF Type1 字体解析时明确报告缺少可选 `fontTools`，
`pdf-font-dependency-probe.json` 也确认当前环境未安装它。其本地源码
`pypdf/_cmap.py` 与 `_font.py` 的分支与警告一致。是否补齐后能修复公式
映射、以及对现有原文保留和旧 revision 的影响，尚未隔离验证；不能提前
宣称依赖补齐已经解决问题。本轮没有变更依赖或放宽引用大小写检查。

当新提取修正了旧档案的空格时，照抄旧空格的历史输出不再是新输入的可比
样本。因此不把“旧输出直接匹配新字节”的探针统计当作准确度变化；保留
上述同字节变量隔离、真实新输入实验以及各自失败记录。

## 第十五阶段：排除字体依赖假设，修复跨页页脚漏标

先在原有 native uv 环境上使用忽略目录中的临时 dependency overlay，
只增添之前库比较已经使用的 `fontTools==4.66.1`。没有更改 manifest、
lockfile 或生产依赖。`fonttools-isolated-without/` 与
`fonttools-isolated-with/` 对同一组 13 份、315 页原始 PDF 分别提取：
pypdf 每页文本、旧 revision 正文、新 revision 正文全部相同。生产文件
冻结验证通过。因此缺少该可选依赖不是这批样本损失的解决办法；上一阶段
的警告只是调查线索，不能算根因或修复证据。

EBD 的 `pp. 68` 漏标原因另有实证：物理第 16 页的中心区域包含大量表格，
10pt 字体对应 1689 个字符，11pt 正文对应 1628 个字符。原算法取前者为
正文基准，而页脚约 9.96pt，未达到“比正文小”的阈值。同一页脚在其他页面
已能识别。这是通用的页面字号估计问题，不需要添加期刊名、EBD 或问题
关键词规则。

当前提取身份改为 `pdf_text/8+pymupdf/1.28.2+pypdf/6.19.0+pypdfium2/5.13.0`，
诊断 `page-text-preservation/7`，版面 `repeated-page-margins/3`。先组合完整
视觉行，再收集边缘候选；至少三页必须独立满足旧有几何与字号条件，才能
将相同文字、位置、字号和一致页码序列的其他完整页边行纳入同一组。
弱字号候选不能建立分组，也不能挤占已独立确认候选的数量限额。不同文字、
位置、字号、带正文的完整行，以及不一致页码均不能借用其他页的确认结果。
原文字节不改、不删。`/2` 元数据继续可用，已撤回的 `/1` 仍不能授权引用
省略；历史诊断各版本保留独立闭合 schema。

验证结果均在 `local/fidelity-cycle-20261003/`，基于冻结后的生产代码：

- `pdf-layout-v3-negative-before.log`：新增测试在旧实现中两项失败，分别
  复现表格主导页漏标，以及弱候选中的页码矛盾未参与一致性检查。
  `pdf-layout-v3-tests.log`：PDF 提取、间距、几何、版面、引用与跨读取绑定
  共 **224 项通过，15.63 秒**。本阶段未重复全量套件；此前 1948 项全量
  结果属于上一版本，不能移作本版本的全量结论。
- `pdf-layout-v3-replay/`：13 份、315 页全部正文和索引与上一阶段逐字节
  相同，物理分页相同，新增 14 处标记、没有删除旧标记，共 294 处。
  复核新增原文字串：7 处食品期刊页眉、1 处睡眠综述页眉、5 处 EBD 页脚、
  1 处会议页脚。RFC 没有新增标记；其 15 处大小上限遗漏计数保持不变。
  回放总计 18.125 秒。
- `pdf-layout-v3-isolated/`：保持上一阶段六次模型调用的实际输入、输出、
  正文和读取 action 不变，仅离线替换重新计算的版面标记进行变量隔离。
  EBD DeepSeek 的结论引用从拒绝恢复为接受，5→6 条；其他五次结果完全
  相同，总计 40→41/45。新增保留引用通过 `_quote_units`，返回原文仍
  包含真实页脚。这不是新的模型调用或改写旧 fetch 记录。
- `pdf-layout-v3-live/`：EBD PDF 新的真实下载与 SQLite 存档、16 次全文
  分页读取通过，原始/正文哈希、索引、UTF-8、页码与关闭检查通过。
  Windows Job 峰值 106024960 字节，原 512 MiB 上限不变。
  实际读取共 52411 字节，校验重叠后 52191 唯一字节、16 个输入片段。
- `pdf-layout-v3-formal-distillation/`：同一真实输入运行正式
  `distill_sources` 与强制 30000 字节压缩的 `deliver_evidence`。
  原问题仍严格为 `What is EBD (Environment Based Design)?`，instruction、
  角色 pin、两轮/40 URL/256k 策略不改。GPT 保留 5 条、DeepSeek 保留 11 条，
  两次真实调用均成功，零格式修复、零 API restart、零来源隔离、零引用排除。
  SQLite 审计核对 30 个 artifacts、1 个 snapshot、32 个 segments、
  16 个 findings，无完整性或引用绑定问题；恢复日志为 2 个逻辑调用、
  2 次实际调用。原始抓取 store 不变。该结果仅验证阶段执行和证据传递，
  不代表生成了两份完整报告，也不能用引用条数评价报告准确度。

仍未完成的工具损失：蜜蜂 PDF 的两处词距/字符映射问题。
`pdf-font-opaque-probe.json` 将调查缩小到物理第 6 页：pypdf 的字体映射和
实际 `visitor_text` 输出包含 `/C0` 等未解码字形名，而另一解析器输出控制
字符。当前的完整字符对齐会在这种差异下保留整页旧文本，间距协助解析器
也未被调用；增添 fontTools 并未改变这个结果。下一步应处理带有明确字体
来源的未解码字形对齐边界，同时保持原文字形，不得通过删掉公式、替换为
猜测的符号或放宽大小写来提高引用通过率。睡眠/蜜蜂图注的两条大小写改写
仍属于模型引用改写，不纳入工具修复。整体目标继续，尚需剩余工具修复和
更广场景的完整 workflow 验证。

## 第十六阶段：隔离未解码字形，恢复普通正文间距

当前 PDF 提取身份为 `pdf_text/9+pymupdf/1.28.2+pypdf/6.19.0+pypdfium2/5.13.0`，
诊断 `page-text-preservation/8`，版面标记仍为 `/3`。新增 `pdf_glyphs.py`
直接追踪实际文本操作数、字符码及字体 Differences，覆盖保存/恢复字体状态
和嵌套 Form。它使用已锁定 pypdf 的 encoding adapter，不添加依赖。只有
完整原文字符流、完整 native 字符流及 native 字形字典在其余位置全部对齐，
且未知字形名称对应同一字体的一个 native 控制字形时，才允许通过该位置。
原字形名称和两侧间距不改，不把公式猜成数学符号；普通文本中的相似名称
不具备这种权限。大小、操作数、字体数和嵌套深度均有明确上限。

另一项通用修复是字体切换处的空格。某些出版 PDF 为连字使用单独字体，
旧的同字体约束会漏掉普通单词之间的空隙。现在只允许 PDFium 已独立读出
空格、两端字母字号/基线相同、物理正字距与本行前一个字体至少三个已观测
空格的校准值相符的情况。不猜字体家族，不把跨字体的未观测空格推断出来。

`local/fidelity-cycle-20261003/` 下的验证证据：

- `pdf-glyph-tests-final.log`：244 项针对性检查通过，17.77 秒。
  包括真实 PDF 操作数和 Form、普通文本伪装字形名、错误字体、最后位置
  不一致、大小上限、未知字形相邻空格保护，以及跨字体校准的正反例。
- `pdf-glyph-full-tests.log`：PDF 生产修复的全量 **1976 项通过，531.87 秒**。
  这次全量运行早于下面的 Writer 输入留存补丁；后续补丁单独验证，不能把
  这个数字算成最终所有新改动的完整套件覆盖。
- `pdf-glyph-replay/`：13 份 PDF、315 页、9976 个数值片段通过字符顺序、
  数值、页码、原有换行和缩进检查。与 /8 正文相比仅蜜蜂论文的 4 页发生
  间距变化，新增 25 个空格，删除 40 个确认多余的空格；其他 12 份正文
  不变。`pro ﬁtable` 与 `theﬁrst` 两处已恢复为一致词距。未知公式字形
  名称原样保留。总计 6 页尝试不透明字形绑定，5 页成功，16 个名称保留；
  成功绑定不等于正文一定改变，樱桃论文的 4 页没有发生间距修改。
- `pdf-glyph-live/`：蜜蜂论文新的真实下载、SQLite 归档及 15 次全文读取
  通过。Windows Job 峰值 158588928 字节，原 512 MiB 上限未改。读取共
  53873 字节，去掉经校验的重复交界后为 53614 唯一字节，15 个片段。
- `pdf-glyph-formal-distillation/`：两模型同证据正式蒸馏及压缩交付完成，
  DeepSeek 一次调用保留 6 条，GPT 两次调用保留 5 条，零引用排除、零来源
  隔离、零 API restart。GPT 第一次返回重复 JSON key，被严格解析器拒绝；
  第二次通过，失败原文及修复输入保留。SQLite 核对 34 个 artifacts、
  1 个 snapshot、30 个 segments、11 个 findings，无字节或引用绑定问题。
  3 个逻辑角色调用对应 3 次实际模型调用。角色、instruction 和问题原文
  未变，原抓取 store 未改。这是阶段验证，不是两份完整报告，也不通过
  新旧引文条数的变化宣称报告质量提升。

审计暴露了额外的观测缺陷：旧 `role_repairs` 只统计
`workflow.role.repair`，而蒸馏拥有自己的有限修复循环，未发这个通用事件，
所以这份真实数据库的修复计数错误地为 0。新审计读取实际 Agent 节点绑定
的结构化输入，以携带 `repair.attempt > 1` 的逻辑节点计数，不重复计算节点
内部的 API restart；通用事件计数另存为 `role_repair_events`，不能读取的
旧节点输入计为 `role_repair_inputs_unavailable`。原始审计 JSON 保留；
`store-audit-corrected.json` 对同一未修改数据库正确返回一次修复。

进一步的集成检查发现 Writer 节点没有结构化 `input_ref`（Runtime 的模型
请求仍保留，不能称为输入完全丢失）。现已让 baseline 11–12 在调用前保存
包含默认字段、research time、已有 report/repair 信息的完整 Writer 输入，
并绑定到该节点，保持实际输入及旧 revision 行为不变。测试逐字比较该引用
经 ResearchRunService 读取的内容与 HTTP provider 实际收到的 task，覆盖
首次 Writer 和报告修订。`writer-input-audit-final-tests.log` 三项通过，
14.81 秒；相关 systemic/decision 检查另有 47 项通过。中间失败来自新测试
对 `_json` helper 和 `NodeView` 的错误调用，已修正并保留日志，不作为生产
失败或通过结果删除。完整 Writer 调用的真实模型验证将随完整流程复测进行。

尚不能宣称全部 PDF 信息无损：`pdf-glyph-remaining.json` 确认蜜蜂论文第 7
页的复杂公式在解析器之间存在真实字符/读取顺序差异（原提取为连字形状，
另一提取为数学字符）。该页仍保留原文并记录回退；公式未解码也明确暴露。
不能通过放宽引用检查消除这一问题。下一步同时回到完整流程覆盖，
`post-pdf-cross-topic/` 对原始头显、航班、睡眠三题各运行两个模型，仍是
baseline 12、40 URL 总上限、两轮及原始 Agent instruction。该批次正在
执行，结果未审阅，不作为已经通过的验收。代码和请求保持冻结至全部终止。

## 第十七阶段：完整三题复测与两模型共有的内联正文损失

`post-pdf-cross-topic/` 的六次完整 baseline 12 已全部终止，原进程正常退出，
`progress.json` 的 `frozen_inputs_unchanged=true`。这批运行使用 HTML /8、
PDF /9 和第十六阶段的 Writer 输入记录修复；下面新增的 HTML /9 补丁是在
六次运行全部结束之后实施，不能把这些完整报告称为补丁后的报告验收。
原三题逐字保持不变，无手工种子 URL/query；40 次 URL 尝试上限、两轮、
256k Agent 额度及全部角色版本、instruction 未变。

| 题目 | 模型 | 运行 / 报告 | 成功 fetch / 尝试 | 自动 coverage 标签 |
| --- | --- | --- | --- | --- |
| 头显 | GPT | succeeded / 已产出 | 6 / 9 | sufficient |
| 头显 | DeepSeek | succeeded / 已产出 | 22 / 27 | partial |
| 航班 | GPT | succeeded / 已产出 | 5 / 5 | partial |
| 航班 | DeepSeek | REPORT_REVIEW_FAILED / 无最终报告 | 7 / 8 | partial |
| 睡眠 | GPT | succeeded / 已产出 | 6 / 12 | partial |
| 睡眠 | DeepSeek | succeeded / 已产出 | 11 / 26 | partial |

已逐份阅读五份最终报告并审阅航班失败记录。coverage 标签不是独立事实评分。
头显 DeepSeek 抓取较多来源，报告包含来源之间的价格、芯片代际冲突；GPT
较短，并使用更少来源，不能据此把 sufficient 解读为更准确。头显 DeepSeek
还有两个 chunk 因原有 20 次蒸馏上限未使用，保留为预算/方法限制。航班
DeepSeek 四次报告审核仍不通过，记录了引用布局、航司组合等审核意见；
所有 Writer/Reviewer 输入都有绑定，不能把未通过自动归因于 API 丢失。
未为通过审核而放宽检查或调整这道题的 instruction。

六份数据库合计核对 1210 个 artifacts、57 个 snapshots、141 个读取片段、
343 个 findings；integrity、外键、待提交操作和来源引用审计均无异常。
118 个实际角色输入均能读取，原问题未改，其完整模板渲染摘要匹配实际调用
事件；包括首次 Writer 及报告修订。实际修复节点 8 个、API restart 0 个、
来源隔离 0 个。唯一排除引文是 DeepSeek 把 Expedia 的起点和终点两个表格
行压成一个行内引文，改变了原行边界；原始两个行均已交付，未放宽校验。

### 新确认的共享系统错误

两个睡眠 run 对 Healthline 同一页面都得到 14059 字节，52 个符合检查长度
的正文段落只有 34 个完整匹配。原始 HTML 的自定义内联组件包着来源链接，
Trafilatura 将部分链接移动到后文之后，或直接丢掉组件后面的文字。例如
某综述的研究数量、效果与无改善结果，以及一项研究使用提取物的条件在网页
原始字节里存在，但旧归档正文只剩链接。两模型共同收到损坏正文，属于工具
损失，不能归因于搜索策略浅或模型没读懂。

HTML 提取身份升级为 `trafilatura_markdown/9+trafilatura/2.2.0+markdownify/1.2.3`。
在工作 DOM 中，仅将明确正文块内、没有显式 role、后代均为普通内联元素的
custom element 转为 span；从内向外处理，原属性、子节点、正文和 tail 不变。
块组件、代码和文章边界不改，原始归档仍保存原响应。没有域名、题目、医学
关键词、特定标签名或来源句子的规则；没有新增依赖或模型 instruction。

`post-pdf-cross-topic/` 下的修复验证：

- `html-component-tests.log`：67 项通过。包含多种自定义名称、段落/列表/
  表格/定义项中的链接与否定条件、嵌套包装、属性保留、隐藏内容、块组件、
  语义 role 和代码反例，以及既有 HTML fidelity/structure 检查。
- `html-component-integration-tests.log`：164 项通过。覆盖 fetch /2、真实
  worker 协议、HTML/Markdown 引文与蒸馏集成；未重复宣称全量 1976 项覆盖
  这个后续补丁。
- `inline-component-replay/`：56 份已冻结 HTML 原文先精确重现旧文本，再
  回放新提取。只有两个模型的这两份同页记录改变，其余 54 份正文完全相同；
  受影响页恢复为 16437 字节、52/52 段匹配，无 URL token 丢失。旧归档
  内容未写入或覆盖。该覆盖计数仍是启发式检查，不代表语义完全无损。
- `inline-component-live/`：一次新真实下载、SQLite 归档与五次 bounded
  document.read 完成，16437 字节完整验证；Windows Job 峰值 64454656
  字节，512 MiB 上限未改，HTML 正文/结构警告均消失，资源正常关闭。
- `inline-component-formal-distillation/`：在已关闭抓取 store 的副本上，
  使用同一原问题、计划、五个实际读取片段和 Distiller 4，两个真实模型分别
  调用一次，保留 7 / 5 条 findings；零引文排除、零修复、零来源隔离。
  两者都使用了先前被丢掉的综述正文；压缩交付仍有原始偏移、hash 与 read
  action 绑定。SQLite 核对 30 个 artifacts、1 个 snapshot、10 个片段、
  12 个 findings，无异常；冻结验证通过，原抓取 store 未改。这是同证据
  阶段验证，尚不是新的完整报告，也不按引文数量宣称质量提升。

### 仍待处理的独立问题与边界

Flightconnections 的警告在两模型中重复。原始 DOM 检查发现，未恢复结构中
包含账户菜单、日期过滤器和订阅弹窗，因此不能把它们全部算作航线正文损失。
现有启发式警告还可能把页面 UI 差异传给 Writer/Reviewer，下一步需要校准
诊断范围。VRDB 的未恢复列表则确实包含设备适用对象的正文，需要单独分析。
Google Flights 的范围保留检查、Sleep Foundation 的结构恢复后 prose
诊断也仍有未解决项。`html-loss-inspection/` 保存原始范围、初次抽取和逐块
检查；不靠删除警告或放宽源文本匹配来宣布修复。复杂 PDF 公式问题仍保留。

用户提供的流程截图作为后续 method 设计参考：可观察到按 Q1–Q8 分别运行
Extend、Verify/Synthesize 阶段，以及 Q8 的 r2。标题描述核验后继续探索到
饱和，但截图没有给出饱和判定、API 重试或持久化恢复实现。研究补充轮次
属于 workflow；已确认失败后的有限等待/重试、记录和资源回收属于 application
orchestrator，应供各 method 共用。这次没有用该流程替换 baseline，也没有
把截图上的运行计数或 token 显示当作已验证的并发/上下文窗口配置。

## 第十八阶段：最终文本诊断与正文 section 中的遗漏列表

本轮代码将 HTML 提取身份更新为
`trafilatura_markdown/10+trafilatura/2.2.0+markdownify/1.2.3`，没有改变
baseline 12、Agent 角色、instruction、问题原文、两轮或任何正式预算。
证据位于 `local/fidelity-cycle-20261003/html-diagnostics-followup/`。

### 三处修复及其依据

1. **警告停留在中间结果。** Sleep Foundation 食物页经过结构恢复，最终
   归档已经补回多段正文，旧 `matched_blocks` 却停留在恢复前的 58/75，
   给两个模型都传递了“substantial unmatched prose”。新的
   `dom-prose-overlap/2` 对最终交付 Markdown 的文字再做比较，包含表格与
   literal HTML，得出 74/75，旧的严重遗漏警告消失。原归档正文一个字节
   都没有改变。`intermediate_matched_*` 保留中间值；primary 值、恢复
   尝试及结构诊断仍在，旧 `/1` 记录继续被 schema 接受。
2. **恢复计数没有检查最终子树。** 旧选择器只数整体标记为保留的结构，
   没数通过所有子节点完整保留下来的列表。现在对实际裁剪后子树核对标签、
   属性、子结构和文字，代码文字保留空白要求。Flightconnections 在正文
   不变时从 8 个已恢复/6 个未恢复校正为 9/5，没有掩盖其余范围不明项。
3. **明确正文 section 里的列表被漏掉。** VRDB 页一个列表的六项只剩数字，
   描述文字原本就在原始 HTML 中。旧规则只找相邻单段正文，不能利用同一
   authored section 内已保留的多段介绍。现在该 section 需有至少两段
   自身已保留正文且覆盖率达到既有强覆盖门槛；嵌套 section 不能借父级
   锚点。只补回结构及其路径上的独立标题，不导入相邻卡片的标题。最终
   文本从 10526 增至 12082 字节，六项描述和原有标题恢复，结构 4/4 完整。
   规则不识别域名、设备、问题词或具体 class 名。

诊断仍不等价于语义损失计数。最终检查也观察到少量呈现差异，例如已经
转为 Markdown 有序列表的原始数字不在 HTML text nodes 中，以及旧库留下
的字面粗体标记。这些没有被忽略来凑 100%；`semantic_verification=false`
仍是契约。最终文字比较既可清除恢复后的旧警告，也可揭示渲染阶段新差异。
引文验证没有复用或放宽这些启发式规则。

### 验证结果

- `tests-final.log`：130 项通过。覆盖最终恢复/最终丢失两个方向、历史诊断
  schema、HTML/表格/代码、大小写和 source boundary、通过子节点保留的
  结构计数、嵌套/弱 section 不能借远端正文、标题与相邻卡片边界，以及
  原有 HTML/fetch 检查。
- `integration-tests.log`：220 项通过；它早于最后的相邻卡片标题收窄补丁。
  最终生产代码在 `full-tests.log` 获得 **2006 项全量通过，506.84 秒**，
  包含上述最终补丁以及上一阶段的 Writer/自定义内联组件修复。
- `before/` 与 `final/`：同一批 56 份冻结 HTML 原文回放，仅 VRDB 正文
  改变，其余 55 份字节不变；旧 archives 全部未修改。Sleep Foundation
  两份同页记录仅诊断改变，Flightconnections 两份记录仅恢复计数改变。
  单次回放耗时为旧 7.588 秒、新 8.943 秒，是本机这次运行的观察，不作
  性能保证。初版候选多带了一个相邻卡片标题，检查差异后收窄规则，并在
  最终检查中覆盖该反例；`after/` 保留该中间记录，最终以 `final/` 为准。
- `html-final-live/`：三个页面新的真实抓取、SQLite 归档和完整读取通过。
  VRDB 4 次读取、12082 字节；Sleep Foundation 13 次读取，44723 交付
  字节经核验去掉 237 重叠后为 44486 字节；Flightconnections 8 次读取。
  三个 Windows Job 峰值分别为 65810432、71544832、110780416 字节，
  原 512 MiB 上限不变。抓取诊断经真实 worker/result schema 和归档链路
  返回；正常关闭，冻结验证通过。
- `html-final-formal-distillation/`：头显与睡眠各用同一份新抓取证据、旧
  计划和原问题，调用 DeepSeek/GPT 的 Distiller 4。四次真实模型调用都
  得到有效蒸馏，findings 分别为 6/3 和 12/5，零引文排除、零角色修复、
  零 API restart。DeepSeek 实际引用了刚恢复的目标用户列表；GPT 同样
  收到完整列表，却没有利用其中一条对比陈述，这是模型选择差异，未改
  instruction。SQLite 审计 50 个 artifacts、3 个 snapshots、34 个
  segments、26 个 findings，完整性、外键、待提交及引用审计无异常。

### 保留的失败：额外 8KB 阶段额度不足

上述阶段测试额外设了 8000 字节 synthesis 上限，以验证压缩后的 quote
绑定。这比正式 baseline 的 524288 字节小。DeepSeek 的睡眠蒸馏成功，
但交付报 `NO_EVIDENCE`，因此该阶段 run 的历史 status 仍为 failed，不能
把“四次蒸馏有效”写成“四次整条阶段流程成功”。

没有重抽模型输出来掩盖失败。`html-final-delivery-replay/` 在关闭 store
的副本上使用原四份模型输出与原读取片段，只改变交付上限，新增模型调用
为零。DeepSeek 睡眠证据完整块 52729 字节，压缩块 9342 字节：8000 时
稳定重现 `NO_EVIDENCE`；30000 时交付压缩块，524288 时交付完整块。
其余三份在这三档均成功。所有成功交付都核对原偏移、原 hash、实际
read_action_id 和完整引用；没有 stale extraction warnings。新副本审计
71 个 artifacts，源 store 未改。这个失败属于测试额外小额度，未通过
修改正式预算或裁掉引用解决；阶段结果不是新的完整研究报告。

### 当前余项与完整复测

Google Flights 已定位到另一类真实工具损失：初次解析把单独的文本块与
换行粘连，保留检查会遇到 `theAdjust`、`theYou` 以及价格尾数/航班频次
的合并 token。原 DOM 有完整条件和独立字段，现有完整 token 保留检查
因此拒绝结构恢复。`inspection/.../unit-differences.json` 保存具体差异。
下一步需利用原始 DOM 边界恢复文字和字段，不能把数字校验放宽成任意
字符子序列，也不能借提高通过率丢掉原限制语句。

Flightconnections 剩余五个范围不明结构仍包含账户/日期/订阅 UI，保持
警告，尚未解决通用范围分类；复杂 PDF 公式的读取顺序/字形限制仍存在。
已启动 `post-html-cross-topic/` 完整原三题 × 两模型复测，正式参数未变。
结果尚待审阅，不能将本轮阶段验证当成六次完整报告已通过。代码、依赖、
角色和请求冻结到该批次全部终止；保留原运行进程，不因观察等待超时重启。

## 第十九阶段：测试误判、DOM 字段粘连与真实交付复验

`post-html-cross-topic/` 原批次已正常结束，`frozen_inputs_unchanged=true`。
该批次使用 HTML /10，以下 /11 修改均在批次终止之后进行。原三题逐字
保持不变，无手工种子 URL/query；baseline 12、角色、instruction、40 次
URL 尝试、两轮和正式上下文额度均未改变。

### 六次完整运行的实际结果

| 题目 | 模型 | 研究运行 / 最终报告 | 成功 fetch / 尝试 | 自动 coverage 标签 |
| --- | --- | --- | --- | --- |
| 头显 | GPT | succeeded / 已产出 | 9 / 13 | sufficient |
| 头显 | DeepSeek | succeeded / 已产出，原验收脚本误判 | 20 / 24 | partial |
| 航班 | GPT | succeeded / 已产出 | 5 / 5 | partial |
| 航班 | DeepSeek | REPORT_REVIEW_FAILED / 无接受的最终报告 | 16 / 18 | partial |
| 睡眠 | GPT | succeeded / 已产出 | 3 / 8 | sufficient |
| 睡眠 | DeepSeek | succeeded / 已产出 | 15 / 31 | partial |

已阅读五份接受的最终报告，并审阅航班失败的审核意见。头显 DeepSeek
报告明确记录代际、价格和来源冲突；GPT 较短。睡眠 DeepSeek 涵盖更多
具体研究与相互冲突的结果；GPT 使用较少来源，仍有研究设计及主客观指标
的限定。航班 GPT 给出较短的预订步骤和连接例子；DeepSeek 在四次审核后
仍因归因、航段支持及限制表达等意见失败。没有为通过而修改 instruction
或放宽审核。上述观察不是外部事实核查，coverage 标签不代表准确率排名。

六个原库合计审计 1341 个 artifacts、68 个 snapshots、193 个实际读取
片段、423 个 findings，完整性、外键、待提交与绑定检查均无异常。129 个
角色输入的原问题及完整模板渲染摘要匹配实际调用。11 个修复输入、零
来源隔离、零 API restart。两个排除引文单独保留：头显 GPT 去掉表格
单元格粗体后被拒，需继续检查格式适配；睡眠 DeepSeek 引文漏掉链接的
左方括号且增加了该处原文没有的开引号，原段落已经交付，不能直接将其
视为工具丢字。头显 DeepSeek 还有一个 chunk 未进入蒸馏，原因是原有
20 次蒸馏上限，继续归为方法预算限制。

### 修复验收脚本误判，并用原结果补验

`examples/live_research_check.py` 原先硬编码第一次 `report.1.review`
必须成功。头显 DeepSeek 的第一次输出格式失败，但
`report.1.review.repair-2` 成功，后续发布和 SQLite 报告均完成。脚本
已通过 HTTP 读取报告，却在节点名检查处失败，跳过末尾的本地报告导出。
因此原记录的 exit 1、report_exists false 不能用来声称研究没有报告。

现在验收逻辑要求成功的逻辑角色，接受精确 `.repair-N` 后缀（N≥2），
排除验证子节点、相似前缀及失败节点；发布节点仍精确匹配。下载的报告
和事件在后续独立断言前保存，只有全部通过后才写 acceptance.json。
同时将服务器约 3 秒的轮询次数上限改成 60 秒墙钟启动等待：原实验大库
重开确实触发了旧超时，新的等待仍有明确上限。

证据位于 `dom-boundary-followup/`。第一次补验因旧启动超时失败，保留
`recovery.log` 与副本。第二次在新副本上用相同请求和 client_request_id
补验：`recovered-headsets-deepseek-evidence-2/` 保存 13723 字节报告，
其 hash 匹配原 SQLite report_ref；HTTP 分块、SSE 回放/续读、幂等请求、
关闭重开后的同报告检查全部通过，新增模型调用 **0**。原 store 全文件
hash 不变，原批次失败记录未覆盖。这是恢复验收，不是重新生成研究报告。

### HTML /11：用完整 DOM 文本槽解释粘连

旧保留检查会把价格尾数与频次、删除按钮标签后的两段文字当作合并 token，
即使完整字段仍在源 DOM，也拒绝恢复。新的 `html_alignment.py` 只在
原 token 检查失败时使用：选中文本必须由一个原始正文块内、按顺序的完整
text/tail 槽组成，可以略过完整槽但不能猜测或截取槽内数字/单词。独立
段落、列表项、单元格及代码边界不跨越；leaf div 不借父容器的其他块。
共享工作量、选中长度、槽数和状态数均有限，超限不能成为保留成功依据。
它仅许可重新渲染源结构，不修改单独的引文匹配规则。

- `tests-verified.log`：167 项通过，包含数字、大小写、否定、顺序、
  部分槽、跨项/单元格/代码、额度耗尽反例，既有 HTML/fetch 检查及
  验收脚本回归。早期新测试缺少真实文档根及正文锚点的失败日志保留；
  最终测试使用完整 DOM 和已选正文，未放宽页面范围规则。
- `integration-tests.log`：263 项通过，覆盖真实 worker、fetch 后端、
  markup/引文、蒸馏、baseline 及 examples。上一阶段 2006 项全量结果
  不冒充这个后续补丁的全量测试。
- `before/`、`after/`、`comparison.json`：两批共 123 份冻结 HTML
  原文前后回放，120 份正文逐字节不变，三份改变。Google Flights 从
  10374 到 14298 字节，3 个受损结构恢复；Trip.com 航线页从 22679
  到 37447 字节，6 个恢复；机场页从 16239 到 19585 字节，1 个恢复，
  其余 6 个范围未确认结构继续警告。手工检查差异包含原说明、标签、
  日期/价格/航段字段，也有源页面原有营销和相关链接，不能把字数增加
  全部算作有效事实增加。所有原归档不变；单次回放约 27.1 / 19.8 秒，
  不是可靠性能比较。
- `dom-slot-live/`：三个页面新真实抓取、原始响应归档和完整 bounded
  reads 成功。Google 4 次读取、14297 唯一字节；机场页 9 次、19585；
  航线页 14 次、37447。分别核对并去除 51/168/60 个重叠字节，实际
  read action、偏移、hash 保留。新页面与旧归档不要求内容完全相同。
  Windows Job 峰值为 77725696 / 77955072 / 81088512 字节，原
  512 MiB 上限不变，资源正常关闭，冻结验证通过。
- `dom-slot-formal-distillation/`：在已关闭新抓取库的副本上，三个
  来源使用原问题和已有计划、相同证据，分别交给两模型 Distiller 4。
  六次真实调用全部有效并完成交付；两模型 findings 为 Google 7/5、
  机场页 8/4、航线页 6/6。零引文排除、零格式修复、零 API restart，
  正式 synthesis 上限 524288 字节，未沿用上一轮额外的 8000 字节
  压力测试限制。交付引用与实际读取偏移/hash/action 逐项核对；审计
  70 个 artifacts、3 个 snapshots、54 个片段、36 个 findings 无
  异常，原抓取库未改。两模型已使用恢复后的航段字段，但有的引文只有
  “1 stop”等短内容；定位正确不等价于完全支持整条 claim。这是模型
  证据选择与后续审核问题，未靠放宽工具验证处理。

### 保留的后续问题

上述六次完整报告用的是 /10；/11 只有原文回放、真实抓取与同证据双模型
阶段验证，尚不能声称 /11 已完成新的六份报告比较。Flightconnections
及 Trip.com 机场页的 UI/正文范围分类、Good Housekeeping 页 unmatched
prose 警告、表格粗体引文的可能误拒，以及复杂 PDF 公式读取限制仍待查。
前面五份报告可读、SQLite 审计无异常，不等价于工具语义无损。

## 第二十阶段：引文格式误拒、遗漏正文及异常解析隔离

上一阶段有真实代码、归档回放和交付验证的进展。本轮继续沿原目标处理
工具/格式/读取损失；baseline 12、六个角色的 instruction、原始问题、
两轮、40 次 URL 尝试及正式上下文额度均未改。证据位于
`local/fidelity-cycle-20261003/quote-diagnostics-followup/`。

### 引文：保留原字节并修复格式映射

头显 GPT 被排除的引文原文在归档中完整存在。进一步定位发现两层原因：
真正的 Markdown 表格没有 cell emphasis 映射；该历史页面还被库输出成
缺少分隔行的管道文本，行尾一个空格被 Markdown parser 的 softbreak
消费，使旧字符记账检查放弃了整段 emphasis 映射。

现在对真实解析出的表格，逐物理单元格核对原内容后才去掉比较用的强调
标记，管道、数据行、顺序与事实文字都保留；不使用 parser 补齐/截断的
虚拟单元格。分隔行可保留或省略。旧管道段落仍作为段落处理，不推断新
表头；softbreak 前原有空白也纳入字符偏移。返回值仍是完整连续原文切片，
长度、UTF-8 偏移及读片段边界不变。

新增反例还实际触发 pinned Markdown parser 对畸形嵌套块的 IndexError。
可选格式解析遇到 IndexError/RecursionError 时现在禁用该投影，继续允许
原文精确匹配，不使这类 parser 异常直接中断引文验证。没有近似文字匹配。

- `quote-replay.json`：两个关闭的完整研究批次，共 122 份真实蒸馏输出、
  769 条 findings，用相同计划、source、实际读取和 raw output 回放。
  仅上述头显引文从排除变为接受，其余判定不变，包括睡眠模型的破损链接
  引文及旧批次跨表格行的错误引文。源文件 hash 不变，模型调用 **0**。
- `quote-delivery-replay/`：在已关闭头显 GPT 原库副本上重用原模型输出，
  六条 finding 均通过校验。额外 8000 字节上限交付 5565 字节、选择
  542 原文字节；正式 524288 上限交付 23636 字节、选择 19027 原文字节。
  恢复的引文均在交付中，偏移、hash、实际 read action 逐项匹配，原
  store 全文件 hash 不变，新增模型调用 **0**。副本审计 175 artifacts、
  9 snapshots、13 片段、52 findings 无异常。原 run 的历史排除事件
  仍保留，因此全库 excluded_quotes 仍为 1，未伪造历史通过记录。
- `softbreak-performance.json`：同时移除了逐换行复制剩余长字符串的
  开销，改成 regex 原字符串偏移匹配。73KB/295KB/1.18MB 的原字符
  映射逐项相同；记录单次本机耗时，仅用于证明这处可避免的复制开销，
  不作为稳定性能指标。

### HTML /12：警告对应真实正文丢失

Good Housekeeping 页的遗漏不是 UI：五段标题下导语/限制说明，以及
Sweet Potatoes 条目的正文仍在原始响应中，旧正文只有 13/19 个符合
诊断长度的段落。它没有被判为损坏的 list/table/code，所以旧结构恢复
路径没有补回这些普通段落。

新的最终正文恢复仅在 substantial omission、且源明确给出一个 article/
main 时尝试。保留已交付内容，投影遗漏原始段落及其本地标题；独立嵌套
article、无标记 body、多 main 不授权补入正文，未选链接卡片不随整页
带入。候选最终渲染必须保住原文字、目的链接、代码、已匹配段落，且
覆盖严格增加，才能替换。原始响应不变，文本/index/进程上限仍有效。
提取身份为 `trafilatura_markdown/12+trafilatura/2.2.0+markdownify/1.2.3`；
可选 `prose_render_recovery_attempted/applied` 记录这次额外恢复，最终
匹配重算，同时保留 primary 和 intermediate 数字。

- `html-comparison.json`：123 份冻结 HTML 原文相对 /11 回放，122 份
  正文逐字节不变。只有上述页面从 7650 到 9996 字节，匹配 13/19 到
  19/19，六段恢复；原有图像 title/alt 的 Markdown 呈现有变化，但目的
  链接和段落保留。检查差异后，未采用导入整 main、连相关卡片一起渲染
  的早期候选。最终 `after/` 为准，原 archives 均未修改。
- `prose-live/`：一次新真实 fetch 与 SQLite 归档、3 次完整读取通过，
  9996 字节、无重叠、无验证错误。Windows Job 峰值 69812224 字节，
  512 MiB 上限未变，正常关闭，冻结检查通过。
- `prose-formal-distillation/`：在关闭抓取库副本上使用原睡眠问题、同
  计划、同三个真实读片段和 Distiller 4，DeepSeek/GPT 各一次真实调用。
  分别 8/5 findings，两次交付都成功，零引文排除、零修复、零 API
  restart。DeepSeek 引用了补回的导语、限制说明与研究描述；GPT 也
  引用了补回的研究描述。定位恢复不等于这些消费文章的医学结论已经外部
  验证，不能按 finding 数量宣称报告质量提升。审计 30 artifacts、
  1 snapshot、6 片段、13 findings 无异常，原抓取库不变。

### 回归状态与新暴露的问题

`final-targeted.log` 最终 **413 项通过**，覆盖原文偏移、表格/代码/
段落边界、数值/否定/顺序、真实 parser 反例、档案到 Analyst 的交付，
以及 HTML 恢复、最终渲染丢字/丢链接/丢代码、嵌套文章与额度反例。
首轮全量 `full-tests.log` 为 2081 passed / 1 failed（489.43 秒），
唯一失败是新增测试把原段落末尾空格也要求保留；修正后已包含在上述
413 项。首轮日志保留。随后消除 softbreak 大字符串复制，并启动
`full-tests-final.log` 的最终全量回归已结束：**2082 passed（499.72 秒）**。

继续读取真实剩余结构，发现不能统称为 UI：

1. Flightconnections 五个未恢复结构主要对应账户设置、最多中转次数、
   日期选项、日期筛选与订阅功能介绍。还需要通用范围诊断，未加入该站
   class 名或关键词排除规则。
2. Trip.com 机场页的六个结构中，五个是路由/相关链接导航；另一个确实
   是航段列表。`trip-schedule-slots.json` 显示原 DOM 的 10 组记录均
   有时长未进入当前正文，如同一组三段中的 2h 5m、10h 50m、4h 55m。
   原 ol 的直接子节点是 div，现有正文段落锚点不能确认恢复该结构。
   这是独立的真实工具损失，仍待修复，不能靠清除 warning 或改变
   instruction 掩盖。
3. 历史工具的无分隔行表格输出还需从提取/渲染层继续检查，本轮只修复
   对既有档案的格式兼容；复杂 PDF 公式限制也仍保留。

已启动 `post-prose-cross-topic/`：原头显、航班、睡眠三题，加测试集中
已有的 Python 3.12 sqlite3 问题，四题 × 双模型，全部无手工种子。
目的是覆盖消费/出行/健康及代码、技术文档的完整链路。代码、依赖、角色
和请求在该批次结束前冻结，保留原进程；当前结果尚待审阅，不能将本轮
阶段验证当作八次完整报告已经通过。

## 第二十一阶段：记录字段和分组恢复，以及四题双模型复核

`post-prose-cross-topic/` 八次完整研究已终止并通过冻结检查，使用 HTML
/12、baseline 12、原角色和两轮/40 次 URL 上限，无手工种子。头显 GPT、
航班双模型、睡眠双模型、sqlite 双模型共七份报告发布；头显 DeepSeek
在四轮报告审核后失败。自动 sufficient/partial 标签不代表外部事实正确。

### 完整运行审计

八库审计共 1476 artifacts、64 snapshots、185 个已核对片段和350 条
findings，未发现完整性、外键、pending operations 或绑定异常。另行
重建了 141 个实际角色输入：原始问题均未变，模板渲染 digest 均匹配
派发事件，所有 input_ref 可读。审计记录 26 条引文排除、8 个带 repair
的输入、零隔离、无 provider replacement；排除的具体格式原因继续复核，
不能仅凭审计通过推断它们均合理。

头显 DeepSeek Reviewer 称 29 attempted / 20 distilled / 15 substantive
及结构、蒸馏上限说明没有被提供，但这些都在 `report.4.review.input.json`
的 quality 中，且实际派发 digest 对应。这是已收到信息后的审核误判，
不能归咎于 host 漏传；最终结构校验为空，未通过的原 draft 和错误均保留。
同批102次URL尝试中38次明确失败。64份已存来源中两份因20次蒸馏调用
上限未进入 Distiller，限制明确记录，未伪装成完整覆盖。

### HTML /13：从每条已选记录确认恢复范围

机场页的列表是原生 `ol > div` 记录，每条记录内又包含分段 `ul`。
原正文遗漏10组中的时长与 Nonstop 字段，单纯补回全文后，Markdown
renderer 还会将组内列表摊平。现在在独立 `html_records.py` 中以每条
记录自己的唯一完整字段作为锚点，要求原顺序、至少80%字符覆盖，且匹配
仅由原始DOM完整文字槽组成。选中单元可由多个槽合并，但不能取字段子串、
改变数字/大小写/顺序，或从另一条记录借常见字段。所有记录必须满足，
输入/槽/状态/总匹配工作量有界。原保留检查继续有效。

直接子节点不是纯 li 的列表以原结构的安全HTML呈现，不发明li或序号。
此策略也保住网页目录中原有的非常规嵌套。没有站点、class或问题关键词
规则，没有改变 instruction、角色schema或workflow。提取身份更新为
`trafilatura_markdown/13+trafilatura/2.2.0+markdownify/1.2.3`。

证据在 `local/fidelity-cycle-20261003/record-structure-followup/`：

- `comparison.json`：186份旧原始HTML重放，176份正文逐字节不变；10份
  变化对应两个Trip页面、PCGuide目录和SQLAlchemy目录的多次归档。
  机场页19585→63558字节、恢复结构1→2，仍有5个未确认结构；航线页
  37447→82870主要因保留HTML分组。PCGuide12584→12774，SQLAlchemy
  158675→160313。字数增加多数是结构标记，不等于事实量增加。全部旧
  原文不变；单次回放耗时只作运行记录，不作性能排名。
- `record-group-verification.json`：10份发生变化的来源、24个非常规列表，
  逐项核对源DOM与最终HTML的直接子记录、内部列表层级及原字段文字。
- `record-live/`：新真实机场页fetch、SQLite提交、23次bounded读取通过，
  63558唯一字节，307重叠字节经原偏移/hash确认后去重；资源回收和冻结
  检查通过，Windows Job峰值82919424字节，512MiB上限不变。
- `record-formal-distillation/`：同计划、原航班问题和相同实际读取交给两
  模型Distiller4，分别10/5 findings，各一次真实模型调用，交付均成功。
  无引文排除、格式repair或API replacement。恢复字段存在于实际输入；
  部分模型引文仍只有航班号或机场名，不能单独支持整条claim，未把精确
  定位当作语义充分。审计30 artifacts、1 snapshot、46片段、15 findings
  无异常，原关闭抓取库不变。这是阶段验证，不是新的两份完整报告。
- `focused-tests.log`：80项通过；最终 `integration-tests.log`：759项通过，
  覆盖toolset与HTML/Markdown引文、读取边界、真实档案到Analyst的交付。
  沿用上一阶段最终全量2082通过记录，不将其说成/13新全量结果。

### 继续暴露的问题

该批头显页面 `r1.source-008` 的原始 Wikipedia infobox 有 Operating
system、System on a chip 标签及Weight单元格，包括型号区别与不含电池
说明；这些没有进入现有正文。`candidate_loses_destinations` 阻止了结构
恢复。这是另一个已确认提取缺口，继续定位；不是Reviewer误判的同义项。
Flightconnections等页面的UI/正文范围诊断、无分隔行旧表格渲染及复杂PDF
公式限制继续保留。未宣布工具已无损。

## 第二十二阶段：代码内链接阻塞无关主表恢复

在第二十一阶段确认的Wikipedia表格缺口中，保留检查实际只报一个丢失
目的链接：引用区 `<code><a ...>cite web</a></code>` 内的URL。
Markdown code span无法表达链接，renderer丢掉它后，严格guard拒绝整份
候选，间接留下信息框字段缺失。现在保留为安全的inline HTML，同时保持
代码原文、URL及相邻行文。没有放宽目的链接guard或按Wikipedia例外处理。
提取身份更新为 HTML /14；角色、baseline和额度未变。

证据在 `local/fidelity-cycle-20261003/link-code-followup/`：

- `comparison.json`：186份原始HTML回放相对/13，185份正文逐字节不变，
  仅该页88054→95201字节。字段标签和原Weight单元格内的M2/M5、排除
  电池说明恢复；原文中的内容、括号和可能错误均未由工具纠正。结构
  诊断从candidate_loses_destinations改为recovered，37/37段落保留。
- `link-live/`：新真实fetch、SQLite归档、24次完整读取通过，95201唯一
  字节，516重叠字节按真实读取边界去重。Windows Job峰值89804800字节，
  512MiB上限不变，关闭资源及冻结检查通过。
- `link-formal-distillation/`：原头显问题、同计划和相同新读取，双模型
  各一次真实Distiller4，分别8/4 findings，证据交付成功。没有引文排除、
  repair或replacement。审计30 artifacts、1 snapshot、48片段、12
  findings无异常，原库不变。模型没有必然选取新补回的重量单元格，不能
  声称报告准确度因此已经提升；能确认的是该单元格已在实际输入中。
- `focused-tests.log`123项通过，随后 `integration-tests.log`762项通过；
  验证链接/代码同时保留、相邻正文、跨页面恢复以及原保护反例。

Astra随后只读重放了上批26条引文排除：23条为可见文字相同的格式差异，
3条改动了大小写、表格行边界或代码注释的原始引号。所有23条都在原来
已引用的片段内，跨度小于2048字符，未发现读取缺口或parser异常。
`quote-exclusion-audit/analysis.json`和七个通用反例保留完整定位。
这说明此前审计通过仅证明已接受数据正确交付，不能证明过滤器没有误拒。
后续按通用格式兼容修复，仍保持代码字面值与结构边界；不修改instruction。

## 第二十三阶段：已读证据的格式误拒

本轮先由Astra只读调查，随后由GPT-6.1-sol实现Markdown映射，root处理
HTML映射与集成。用户指定的execution/exploration模型分工已写入AGENTS。
没有角色instruction、schema、问题原文、workflow或预算变更。

### 修复边界

- Markdown使用pinned CommonMark parser确认完整语法，再把inline code
  delimiter、带title/括号URL的HTTP(S)链接、强调标记映射回原字符位置。
  代码body必须和解析结果逐字相同；entity、escape或padding/newline
  normalization不能授权猜测。强调、链接、独立code、链接label内code
  四类策略最多16种，先去重位置集合；不是每个标记任意组合。多行平铺
  列表项保留marker/缩进，顺序、嵌套列表和table行/列边界不被抹掉。
- 独立 `html_inline_quotations.py` 对完整平衡的p/cell/definition/list
  item或pre生成原位置视图。可见链接、inline code、presentation标签
  可以省去，实体拼写和字面值不变；跨cell/paragraph的plain-text拼接
  不被允许。table视图保留关系标签。语法高亮pre只去已验证表现标签，
  不对code内容做Markdown解释。未知属性/隐藏内容/不支持子树保留原样。
- 未改动的br、sup等兄弟节点仍保留，不能让旁边一个独立链接无法映射。
  Markdown中的成对裸sup/sub也只记账、从不删除，不因此放弃其余普通
  行文的映射。未匹配/带未知属性标签继续保守处理。
- 另一个反例揭示：移除inline-code反引号后，不能把其内部的HTML示例
  当成新HTML去解释。现在HTML和Markdown以原始来源视图分别解析，不
  将后者的格式投影再作为HTML文档。原文精确匹配不受影响。

### 实际重放与交付

证据在 `local/fidelity-cycle-20261003/quote-format-followup/`。

`quote-replay-final.json` 重放三个已关闭批次的184份真实模型蒸馏输出、
1145条findings，读取其原计划、source、input_ref、实际读片段、raw
output和hash。最近批次26条排除降至3：23条格式差异全部恢复；改动
You/you、合并table行界pipe、改写代码注释引号的3条仍排除。历史另外
两条错误仍排除；此前阶段已恢复的表格强调引文仍接受。所有原文件hash
不变，模型调用0。这证明格式恢复，不证明claim与quote语义相符。

`delivery-final-sqlite-deepseek/` 与 `delivery-final-headsets-deepseek/`
分别在两个关闭数据库的完整副本上复用原始模型输出，执行正式校验和
证据交付。SQL的11条原排除全部恢复，头显来源的4条原排除恢复；两个
原输出共19条finding均完整进入上下文，引用原文字、原UTF-8偏移、hash
与实际read action逐项校验。正式synthesis上限524288字节/131072 tokens
不变；实际交付182829/43070字节，选取173939/37400原文字节。

两个副本审计共565 artifacts、30 snapshots、66片段、177 findings，
无完整性、外键、pending操作或绑定异常。原库全文件hash不变、新增模型
调用0。原历史排除事件保留，因此副本excluded_quotes仍为11/6，未倒改
原实验。首轮头显交付探测确实失败（还有两处格式未支持），旧目录与log
保留；最终使用独立新副本验证成功。

### 测试记录与后续

- subagent的Markdown173项、组合引文351项通过；随后root的较大范围
  workflows/methods/agent_catalog回归1127项通过（383.09秒）。
- 边界反例额外发现code中的table被重新解释，已修复；最初HTML边界
  测试2个失败的日志保留，一个涉及旧的code表现标签策略，一个是嵌套
  code保护缺口。对应保护和新契约反例随后通过。
- 最终 `final-targeted.log` **423项通过（54.47秒）**，覆盖HTML/Markdown/
  PDF原文字、数学标记/否定/数值、隐藏属性、代码、关系边界、跨实际读取
  以及真实Storage到Analyst的交付。1127是最后几处边界收尾前的较大范围
  结果，不能冒称最后源码重新执行了全量；最终423包含这些边界改动。

完整报告仍以post-prose批次的七成功/一审核失败为已审阅记录。这些新增
原文回放、真实fetch/双模型阶段与数据库交付检查，不代替一次新完整运行。
UI/正文警告范围、旧无分隔行表格和复杂PDF公式仍有未解决边界；不能宣布
工具损失已经全部消除。

已启动 `post-format-cross-topic/`：仍为头显、航班、睡眠、sqlite四题×
双模型，无手工种子、相同baseline12/角色和额度。它验证HTML/14及本轮
引文修复后的完整运行；代码、依赖、角色和请求再次冻结。新进程保留，
当前结果待收尾与审阅，不把启动或阶段检查当作八次报告成功。

## 第二十四阶段：完整格式回归与表格最终渲染

`local/fidelity-cycle-20261003/post-format-cross-topic/` 已于
2026-10-04 04:52:53 UTC 全部结束，`frozen_inputs_unchanged=true`。仍为
baseline12、40次总fetch、两轮、既有六个角色和原问题；无人工查询/URL种子。
本批次使用HTML/14和阶段23引文匹配；后续HTML/15不倒改这次实验。

| 场景 | DeepSeek | GPT | 尝试/保存来源（DS；GPT） |
| --- | --- | --- | --- |
| 头显 | 成功，sufficient | 成功，sufficient | 12/12；13/9 |
| 航班 | References格式误拒，未发布 | 成功，partial | 21/18；5/5 |
| 睡眠 | 成功，sufficient | 成功，sufficient | 14/9；5/2 |
| SQLite | Reviewer拒绝，未发布 | 成功，sufficient | 4/4；9/9 |

六份已发布报告及两份最后被拒草稿均已阅读。不能由这次不同搜索结果和
单次生成推导模型排名，也不能把sufficient解释成事实正确。头显DS引用的
VRCompare刷新率异常在原始HTML中已存在；抽取没有制造该数字。SQLite
DS的四轮机械校验均通过，最终Reviewer仍要求修改表格中的方法归属、
事务异常触发描述和参考文献标题；这些未归因为host丢失输入。

八个关闭数据库审计共1505 artifacts、68 snapshots、231读取片段、379
保留findings，完整性/外键/pending/引用绑定检查均无异常。149个实际角色
输入都有input_ref，原问题与rendered-input dispatch digest均对应；无
provider错误或替换、无distiller隔离。12个带repair的输入不是API重试。
83次尝试中15次未成功获取，均有记录。

六条引文排除已逐条核对：五条涉及改写文字/代码/URL（The→the、改写
camera句子、改变tracking URL、代码注释的引号、删去Connection前缀或
句内词语）；一条仅把原文弯引号写成直引号，仍是保守匹配的格式边界。
不能宣称格式损失归零。原始排除与模型输出保留于
`excluded-quote-review.json`，不会为了清零而改写历史。

### 新确认的表格损失与HTML/15

三话题的九份归档中，11张HTML表格原首行全部是td。库保留了XML行和
单元格，但输出的pipe文本缺少Markdown表头分隔行，最终渲染不是表格。
另外，中性反例确认混合首行、后续行头和不齐整行会被Markdown改变单元格
角色或补空格。原有诊断只比较中间树，漏报最终表示损失。

HTML/15只把具有完整th首行、等宽且全部td后续行的简单表格交给Markdown；
其他形状使用既有的经过清理的原HTML表示。保留td/th角色、原行长、值、
顺序、链接和code，不猜测表头、不补单元格；原选择与文本/链接/code保留
校验不变。无站点、关键词、问题或角色instruction规则。

证据在 `local/fidelity-cycle-20261003/table-render-audit/`。生产代码回放
186份HTML与离线候选的文本和诊断逐份相同：171份文本不变、15份变化。
独立解析原HTML和最终Markdown所得DOM，核对变化页中的17张表、263个
单元格，角色/文字/顺序全部保留；其中最初11张失去结构的表共205个单元格。
原始文件hash不变。FlightConnections文本175312→196425字节，存在渲染
表示和上下文成本，未扩大任何读取/上下文预算。99项定向测试通过。

随后 `table-live/` 对三个代表性URL执行真实web.fetch@2、SQLite存档和
69次document.read，文本分别20475/196425/6333字节。归档hash、全部
读取偏移与原字节一致；航班分页的606重叠字节经核对后去重。另行比较
真实下载HTML与最终文本DOM：四张表、73个单元格角色/文字/顺序一致。
最高worker job内存150085632字节，低于536870912字节上限。

`table-formal-distillation/` 在已关闭fetch库的完整副本上，让DS/GPT接受
每题相同实际文本、原问题和原plan，执行正式蒸馏及deliver_evidence。
每题每模型一次调用，共六次，两个run成功；37条保留findings全部交付，
源片段read_action/hash/UTF-8偏移核验通过，原库全文件hash未变，无repair
或隔离。GPT在SQLite的一条quote加了原文不存在的`older`，该条仍被排除。
副本审计70 artifacts、3 snapshots、138片段、37findings，无完整性或绑定
异常。这是获取与蒸馏阶段验收，不冒称六次完整报告或报告准确度提升。

最终较大范围回归 `tests/toolset tests/workflows tests/methods tests/agent_catalog`
**1687项通过（455.43秒）**，日志 `integration-tests.log`；这是HTML/15的
生产检查，早于后续References校验修复。`git diff --check`通过。

### 已定位但另行处理的边界

- 航班DS的15条References均以`[source-id](supplied-url)`表示，四份草稿
  都被只识别独立标签的regex误判为全部缺失。最终Reviewer已accept，
  host机械校验独立阻止发布；这属于非模型格式错误，修复证据另记。
- `remaining-structure-audit/`人工检查九个警告页面的45个遗漏ul块，未确认
  新的文章正文损失：它们是账户/日期/订阅控件、tab条和目录、或HTML应用
  shell链接。两份Trip的role=tablist可明确判为控件；tabpanel可能含正文，
  不能整体排除。当前警告仍保留，不能用站点词或链接密度静默清零。
- VRCompare原表格含没有文字标签的SVG图标，库及HTML清理会去掉图形，
  使字段变空。原HTML仍存档；不可按产品知识把空白补成yes/no。
  `svg-fidelity-audit/`记录复现与候选边界，尚未成为生产修复。

## 第二十五阶段：References链接格式误拒

证据在 `local/fidelity-cycle-20261003/reference-format-fix/`。旧机械校验的
`(?!\()`把`[source-id](URL)`排除在References条目外；不是来源缺失。
现在用固定版本Markdown解析器识别原始普通source-ID链接标签和目标，
也继续支持`[source-id] URL`及独立标签后面的`[Title](URL)`。正文仍要求
独立标签。保持source-ID逐字相等、每条唯一、正文与References集合相等、
URL绑定到该来源原地址/最终地址的检查；不猜测URL或放宽成模糊匹配。
代码、图片、转义/嵌套假标签和错误URL仍拒绝；可选parser的IndexError/
RecursionError返回结构修复反馈。raw HTML段落和reference alias尚不支持。

生产回放17份真实草稿，从各自Writer实际输入的host descriptor及source
manifest恢复允许URL，从writer-context-plan恢复允许ID，绝不从待检报告
反推白名单。航班DS四份草稿、每份15条false missing全部消失；其他13份
草稿结果不变。2461份导出/原库文件hash不变，0模型/网络调用。原失败run
仍保留failed状态，不倒改记录或假装恢复执行。首轮候选测试4失败/202通过
的日志保留，修复了Title链接误识别和嵌套标签；最终生产定向**95项通过**。

另在关闭原库的完整副本上执行新`component.references`运行，仅重做正式
Writer7/Reviewer6阶段，沿用原问题、证据、plan、analysis与partial质量。
DeepSeek新Writer及Reviewer各一次调用，第一稿通过并发布；新报告已读取，
原库hash不变、实验源码冻结。报告使用独立References标签，因此这两次
新调用验证集成出版流程；真实链接格式修复的直接证据仍是上述四稿回放。
这不是重新搜索/获取的完整baseline运行，也不改变原报告的证据局限。
额外核对两个新角色的实际input_ref与dispatch digest：原question、plan、
analysis、evidence、quality和research_context一致，Reviewer读到的report
与最终artifact字节相同，原源ID/URL机械校验通过。副本审计347 artifacts、
18 snapshots、104片段、100个历史findings，无完整性/外键/pending/绑定异常；
计数包括复制的历史，新增模型调用仅两次。模型接受不证明报告推论正确。

## 第二十六阶段：40来源预算与底层32条上限不一致

复核报告阶段的DTO时发现：baseline12参数允许40个总URL，但共享
FetchManifest/SourceManifest最大32条，ResearchQuality四个计数最大32。
中性边界探测确认33和40均抛校验错误；此前八次实验最高21次尝试，没有
覆盖此边界。问题在共享契约，与模型选择、搜索深度或网页访问限制无关。

现将这六个约束统一引用`MAX_RESEARCH_SOURCES=40`；旧方法的参数上限
和Runtime grants不变，41仍拒绝。重新生成OpenAPI，仅出现四个quality
maximum及SourceManifest maxItems的32→40变化；没有改变字段名称/结构。
前端服务指南要求旧32条客户端更新生成的schema。

`local/fidelity-cycle-20261003/source-capacity-fix/`保留前后边界结果和日志。
**31项测试通过**：含0/32/33/40/41容器边界、四种成功计数边界、旧方法
限额保持，以及真实Engine/SQLite中的40条已记录失败来源，经HTTP run/
sources响应、状态投影、终态事件和关闭重开完整读回。首次新测试误把
终态event当完整quality对象而失败，改为核验其既有quality_status字段及
HTTP/持久化的完整计数；未为测试改动事件接口。这是容量与记录的受控
验收，不宣称执行过40次真实网页请求。

## 第二十七阶段：SVG值静默变空与提取诊断的传递

证据在 `local/fidelity-cycle-20261003/svg-label-fix/`。原VRCompare的四个
图形单元格在 /15 变空且warning=0；`reproduction.json`绑定同一原HTML
hash，确认 /16 不猜测其含义、四格仍为空，但已有未解析SVG诊断。
**这不是恢复了那四个图形值**。没有文字标签的图形仍是已知工具局限。

/16 在已有内容选择及保存检查后，为已选表格恢复明确的SVG文字元数据：
aria-label、有界且在原文档唯一的表格内aria-labelledby、直接title/desc和tooltip
title。输出是转义后的作者文字，保留所在单元格及原有文本顺序；路径、
class、symbol ID不转成yes/no。冲突、隐藏、presentation、超限或子树不
支持时保持未解析。代码不执行SVG、不解析远程use、不做图形识别。没有
把生成的“unknown”标记插入可引用正文。

新增可选 `html_extraction.graphics` 区分已选范围的审计和未绑定选择的
候选数量，semantic_verification=false。最多检查20000节点、128 SVG，
保留32条诊断、每值256字符、每个IDREF列表4项；详细条目是选中DOM的
路径及解析后SVG子树hash，不是原文件字节定位。source descriptor与
Distiller的既有feedback字段仅携带整篇覆盖计数，角色修复后仍保留，
不泄露未读标签/DOM路径。没有修改角色bundle、方法深度、预算或模型。

`corpus-release/summary.json`是最终标签处理版本的186份原始HTML回放：
**186份正文与/15逐字节相同**，100份新增图形覆盖诊断；该语料没有可
恢复的明确标签，因此不把新增诊断数当作已恢复的事实数。中性fixture
覆盖有/无表头、三个容器、不同标签来源、转义、原始重复文字及顺序、
相同路径不同标签、隐藏/冲突/IDREF及资源界限。

`live/`通过实际web.fetch@2、worker、SQLite和4次完整document.read
抓取VRCompare：15156正文UTF-8字节全部读回，原件/正文/索引hash与
范围验证通过。选中范围44个SVG仍未解析，旧归档保持不变。最终提取器
再处理该实际原件，正文和完整HTML诊断与真实存档一致。

`formal-distillation/`在已关闭真实抓取库的副本上，使用完全相同的原始
问题 `compare meta quest 3 and apple vision pro`、plan及4段证据，分别
执行正式Distiller4→deliver_evidence。DeepSeek/GPT各一次模型调用，
保留7/5条findings，12条均按真实read action/UTF-8范围/hash交付。额外
核对实际input_ref与rendered dispatch digest，确认覆盖计数到达两个
模型及后续证据包。无角色重试、quarantine或原库变化。30 artifacts、
1 snapshot、8记录片段、12 findings的SQLite审计无异常。

DeepSeek另有一条quote漏了`<span>`开始标签却保留结束标签，配对校验
仍拒绝。原字节完整可访问，未为此接受破损关系标记。其240Hz陈述来自
原网页已存值，host不按产品常识改写网页。两个输出已读取；本次只测
蒸馏与交付，**没有产生两个新的完整baseline报告**。受控完整流程另
验证SVG作者标签可引用、生成占位词不能引用，以及失败修复后诊断保留。

首轮扩展回归1913通过、3失败；三个失败均为旧的故障注入测试桩只收
`scope`、没有转发新增诊断参数。更新桩的调用签名，保留原文本/目的地/
代码损失仍拒绝的断言。随后补上原文档ID唯一性检查（含隐藏/导航中
重复ID及扫描超限），最终工具、源访问、图形交付**670项通过**。
最终186原件回放与真实存档匹配验证也在该版本通过；没有把首轮日志
改写为全通过，或宣称最后一次重新跑了全部1916项。

## 第二十八阶段：普通段落双引号排版误拒

`local/fidelity-cycle-20261003/prose-quote-fix/`记录GPT-6.1-sol执行子任务
及根对集成的复核。匹配只适用于明确HTML来源、有已知文档起点上下文、
逐字符可映射的顶层Markdown段落；成对弯/直双引号可等价，query也必须
包含两个端点。字词、大小写、数值、URL、其他标点不变，返回原档案
子串及偏移。代码、链接目的地/标题、raw HTML、其他block、转义/entity
以及含歧义的数学/prime语法不获得这一等价；不做全局标点替换。

**86项中性新测试及509项相关测试通过**。回放68个真实已存蒸馏记录、
385个原始finding，仅恢复Cleveland Clinic的第5条排版误拒，原来6个
excluded变5个；已通过的finding及范围不变。改动tracking URL的第6条
仍拒绝，417份输入/证据文件hash不变。恢复的261字节原始引用绑定文档
UTF-8范围[1620,1881)，保留原弯引号和不换行空格。此回放无模型/网络
调用，不修改原run状态或历史报告。
根另在真实Engine/SQLite的受控完整流程中验证该排版引用由Distiller
一直交付到Analyst，保留原弯引号，改写数值的引用仍排除；新增这项
交付测试通过。此测试使用受控模型响应，与前述两个真实模型调用分开。


## 第二十九阶段：冻结的16次完整运行与分行References误拒

`local/fidelity-cycle-20261003/post-boundary-full-suite/`保存2026-10-04
05:47:04Z—06:12:10Z的完整矩阵：8个既有场景×DeepSeek Flash/GPT-6-luna。
原问题、scoped变体、角色pin、40次URL总额、两轮、256k allowance均未改。
最多两个run并行、每模型一个；`progress.json`确认冻结文件hash不变。
200次URL尝试、141份成功快照，13个正式报告、3个审稿失败。失败仍原样
保存，不把后续组件复测算作新的整轮成功。所有正式报告及三次失败的
最终稿均经根或探索子agent阅读。

16份原有SQLite审计全部通过：3073 artifacts、406段读取、740条保留
finding、10条排除引用、1个蒸馏quarantine；integrity/fk/pending/hash
无异常。这些数字是存档及引用边界检查，不等价于原网页提取完整或
报告事实正确。GPT航班run真实遭遇Writer和Reviewer各一次HTTP429，
分别记录8/11秒Retry-After；两个wait/restart/recovered事件链保留，
随后替换调用成功并生成报告。失败调用没有伪造output或已知token用量。

`headset-review-causality/REPORT.md`独立检查普通头显DeepSeek失败：
四次Writer和四次Reviewer收到相同252639字节证据，25段保存原文、
104条保留引用、每次前稿及全部反馈均完整。审稿中“缺Safari”“没有
该引用”等指控与已交付原文冲突，修订还引入了真实的相机描述错引。
这是模型阅读/修订与有界审稿耗尽，不能归因于host丢失证据。
scoped头显同样没有机械References错误，仍保留其语义审稿失败；
没有针对设备问题调角色instruction或放宽Reviewer门槛。

SQLite DeepSeek的四份稿均将`[source-id]`和其准确URL放在同段的相邻
两行。旧validator只取ID所在行，误报全部六个URL缺失；Reviewer第2、
4次其实已accept。新检查以解析的Markdown block为界，延续到下个
source label之前，不跨段落、list item、heading或代码块借用URL；
错URL、重复ID、跨来源绑定仍拒绝。没有改变实际稿件或补造来源。

`multiline-references/replay-result.json`用实际input_ref、原始输出、
Writer所收descriptor和原SQLite artifacts回放全部31稿：四份SQLite
稿的24条误报消失，其余27稿结果不变，5025份文件hash不变。106项
中性格式/绑定测试通过。报告审核的语义结果没有被离线重跑或改写。

`multiline-references/live-report-stage/`在原已关闭库副本上，保持原
question/plan/analysis/evidence/quality/research_context，重新调用
正式Writer7和Reviewer6：两次真实DeepSeek调用，报告成功。逐个核对
实际input_ref、渲染dispatch digest和报告artifact；新库203 artifacts、
6 snapshots、18读取段、46原findings审计通过。只重跑报告阶段，未重新
搜索/抓取，也未声称这份新稿的所有语义/代码示例均正确。

独立的`synthesis-delivery-audit/`另从实际Analyst/Writer/Reviewer输入
反向核对selected原字节/range/read action/hash、task及provider dispatch。
首版覆盖87份结构输入、89次派发、2184次selection交付、31稿，无交付
mismatch；三个失败run没有正式报告、一次429 Writer没有输出，均明确
记为不可用，未假造通过。首版参考文献解析同样不支持分行，因此其
SQLite草稿URL观察不能当成真实错引；后续独立解析修正应单列保存。


独立auditor随后另存`synthesis-delivery-audit/superseding-v2/`，不覆盖
首版证据：以独立Markdown段落解析恢复SQLite四稿24个精确URL绑定，
32个Reference正负控制和7个恢复链负控制通过。另对GPT航班失败Writer
逐条核对invocation intent/outcome、child terminal、role完成、restart/
recovered和替换export，确认完全记录的HTTP429确实没有输出，修正首版
“覆盖不可用”的分类。最终overlay为13份已发布报告可审计、3份历史
终稿不存在；89次派发、2184次片段交付、259次Reference绑定，零交付
mismatch。仅SQLite完整重审、航班局部receipt检查，其他结果沿用已验
原件；16份原库hash均不变。报告相关回归另有113通过、34未选中。


## 第三十阶段：动态页面缺失的工具归因与内存边界

`meta-render-probe/`和`dynamic-render-audit/`均位于
`local/fidelity-cycle-20261003/`，保存原件、解析结果、捕获计数和真实
ProcessRunner Job结果。两模型scoped头显run的Meta购买页都重定向到
加拿大，静态原件约808/812KB，正文906字节，缺价格。**更正：本阶段曾
误写“原HTML也没有该价格”。第33阶段重新检查证实，两份原HTML的显式
JSON-LD已有Meta Quest 3 512GB对应的CAD 829.99报价；静态正文节点没有
这个价格。因此该案例还存在已下载结构化数据未进入可读档案的提取损失。**
静态提取已成功，当前fetch loop立即返回，没有尝试浏览器；这仍是auto
策略对其他动态内容的已知限制。以下真实浏览器内存测量不因此撤销。

直接进程隔离探测中，2MiB资源上限使一个脚本失败，仍只得到906字节；
8MiB探测得到1060字节，出现CA$829.99。各次都是新HTTP响应，不是完全
相同响应的确定性A/B；加拿大页面所得价格不能当成美国价格，也不证明
页面完整。不能仅根据这个没有生产Job边界的成功就部署上限改动。

Astra探索子agent进一步使用原生ProcessRunner、512MiB整个Windows Job
限额、60秒父deadline、原40请求/32MiB流量上限测量：

| 探测 | 结果 | Job峰值 | 内容/清理 |
| --- | --- | --- | --- |
| 原2MiB资源上限 | 成功 | 443.145 MiB | 静态预检为EXTRACTION_EMPTY；渲染后906字节正文；保留脚本受限诊断；清理完成 |
| 仅脚本8MiB | memory_limit | 530.363 MiB | 已获得906字节静态正文，之后整个Job被终止；无最终proposal；清理完成 |

530.363MiB是Windows报告的终止时峰值，不是授权增加512MiB额度。探测
另有一次仅静态预检的EXTRACTION_EMPTY，未运行浏览器；其初始body未保存
这一限制已记入evidence-summary。后续两次保存了静态原件再尝试渲染。
没有隐藏失败、反复更换输出目录直到成功，也没有新增生产依赖。

纯策略candidate通过49项离线检查：通用的薄正文/大量脚本结构提示、
单次可选捕获、预算预留、原内容顺序保存和失败回退。包含明确false
positive，提示不能判断缺失了哪些事实。该候选尚未成为生产协议。

关键约束是worker只在结束时返回一次proposal。Chromium让整个Job因
内存终止时，同进程try/except无法交回已成功的静态正文。后续必须先
解决renderer失败域以外的静态proposal保留/验证，再讨论通用触发器、
版本化尝试/选择provenance和消费者诊断。不能吞掉unknown cleanup、
编造终态用量、重置预算，或把被终止的半份结果直接算成功。此处只给出
实测原因和待实现边界，没有宣称动态页面瓶颈已解决。

## 第三十一阶段：三类引用格式修复的完整固定输入回放

`boundary-fixes/replay_result.json`保存根对最终集成的复测：140个实际
蒸馏记录、750条原始finding、141份完整native原件/正文/index。before
使用与16次冻结矩阵protocol逐项hash相同的三个原始quotation模块，
after使用当前集成；只在独立进程切换模块，不改旧库或原输入。

| 误拒类型 | 当前规则 | 实际恢复 |
| --- | --- | --- |
| HTML关系标签之间的换行 | 完整、明确嵌套的table，在cell/row/section事件边界只允许五种HTML ASCII whitespace；标签/属性/空单元格均保留 | DeepSeek普通头显source-006 finding2，原字节[2702,2779) |
| 含br的inline wrapper让独立链接也失效 | 无属性br保留为原标签，只恢复其前后独立的平衡inline presentation；不得跨br拼接 | DeepSeek scoped source-005 finding5，原链接及连续原文子串保留 |
| U+2011不换行连字符被写为ASCII连字符 | HTML provenance+已知Markdown上下文，普通段落/平面无序list中完全包含的小写词或1–3位整数/词compound；其他上下文保持literal | GPT scoped source-013 finding0，原U+2011及UTF-8[697,757) |

所有匹配返回不可变原文范围。表格不得重排、合并、删空cell或改数值；
vertical tab不是HTML whitespace，不获新等价。parser有32768事件/128
深度界限，cell边缘空白按连续区间保存，避免为每个字符分配tuple。
不换行连字符不做全局Unicode folding：代码、URL、HTML属性、数学、
数字范围、未知上下文保持原样；完整compound边界防止8-core误匹配到
18-core。已有有效匹配优先，普通小写标识符与自然语言同形这一限制
明确保留，不宣称语义识别。双引号原规则未扩展到list。

最终回放**排除10→7，恰好恢复这3条**；原先740条有效finding、validation
changes及quote_bindings全部不变，所有读取的存档文件hash不变。中间根
回放脚本曾因候选脚本改名残留导致FileNotFoundError/NameError；修正
harness后完整before/after通过，未为此修改production或历史数据。

最终quotation及跨读取/HTML蒸馏回归**915通过，73.68秒**。其中三种
新格式均通过真实Engine/SQLite的受控完整流程，引用由Distiller交付
到Analyst，原标签/换行/连字符保留，改16GB为160GB的对照仍排除。
这些fixtures使用受控模型和fetch响应，区别于第29阶段真实网络/模型
矩阵及后续两个真实报告阶段调用。没有再次重跑16个完整workflow。

余下7条排除仍逐条保留：两条实际改词/重复文字、两条删表格空cell、
一条破损emphasis，以及SQLite GPT两条混合code/link/escaped Markdown
导致的保守比较限制。后两条仍是待修的格式损失；没有用“七条都是模型
错误”掩盖它们。第30阶段动态获取、无文字标签SVG、既有PDF公式等限制
也未因此消失。baseline搜索深度与模型误判仍单独归因，不据此过拟合
instruction或改实验原问题。

## 第三十二阶段：两类混合Markdown引用格式损失

证据在`local/fidelity-cycle-20261004/mixed-markdown-fix/`。执行子agent
GPT-6.1-sol修改`markdown_quotations.py`、`quotations.py`及独立测试；根
检查差异后集成，没有改Agent instruction、预算或历史记录。

SQLite GPT source-001后面的escaped underscore曾让整段保守退回literal，
连带阻止前面已能精确映射的链接代码被引用。现在逐字符核对CommonMark
转义，保留原反斜杠和文字，不解码内容；独立链接/code映射仍可用。
source-002同时保留一个code delimiter、省略另一个，旧规则不能组合。
现在只在已知HTML来源/Markdown上下文的顶层段落中，使用一次query解析
和最多四种共享source policy处理，不枚举每个code span的子集。
原代码body必须完整，query显式URL/title保持literal，已有匹配优先。

`replay_result.json`验证140条实际蒸馏记录、750条finding、141份完整
native exports及280个诊断artifact。排除**7→5，恰好恢复两条目标**；
原743条有效finding、validation changes、quote_bindings不变。1145份
输入文件hash及10份冻结源/验证器/harness文件不变。980项native回归
通过，另有399项focused检查；不是980+399个互不重叠测试。没有新增
真实模型调用或完整workflow重跑。

余下五条仍保留：两条改词/重复、两条删除表格空cell、一条破损emphasis。
最后一条仍处于保守的格式支持边界，不把五条笼统称为模型能力问题。

## 第三十三阶段：纠正原件归因，保留显式JSON-LD并验证交付

证据在`local/fidelity-cycle-20261004/jsonld-fix/`，独立Astra探索核对在
同级`jsonld-review/`。根重新检查发现，第30阶段只检查正文和几个预期
价格，漏掉了显式`application/ld+json`。两份原件的raw SHA-256分别为：

- scoped GPT：`fdda868765add2ff61bf6032708f507dda7938d0f301ced0fb1243da79f76f25`
- scoped DeepSeek：`85ec4ca1cebf05a48cf3b8cbd7bfa4d0fa44300bb072c46220d91e30791be5d6`

它们的同一3967-byte JSON-LD声明`Meta Quest 3 512GB`及其Offer的`CAD`
`829.99`；ItemPage的mainEntity/about也引用这个Product。原件script
范围[1724,5691)，script hash为
`3d465b5fc1ebe993cc9a4114efebc9920b34c9f0535f6cd31ed7cb6f667afacd`。
该声明可绑定记录中的512GB产品；不能据此证明当前UI所选variant、库存、
含税/结账价格或美国价格。两个重复档案不构成独立证据。旧原件不改写，
第30阶段错误判断已就地标明撤回，真实renderer内存证据仍保留。

实现是通用的HTML extraction /17与`html_structured_data.py`：保留整条
原始JSON记录/图关系/限定条件，另加publisher-declared、非可见正文的
标记。LF之外不重新序列化数值或解码转义；不挑字段、实体、领域或价格，
不执行hydration JS，不扩展JSON-LD、不获取远程context。32候选script、
单条64KiB、总supplement含framing128KiB、验证树深度64；省略理由有界。
超文本/index/provenance额度时保留正文，尽量写完整省略诊断；极端exact
provenance cap下仅保留正的通用parser warning，缺少结构化诊断不代表
完整提取。旧档案及非HTML输入不强制新增字段。

正文的byte prefix、coverage诊断、classification均独立，空文档/挑战/
JavaScript shell不能被metadata掩盖。content_hint的字节与reference-line
比例只看原正文，避免大JSON把短文/摘要“升级”。Distiller收到分开的
有界coverage与script-range metadata；修复仍保留它们。压缩后的synthesis
excerpt另外标注body/supplement/mixed来源，标注在原文字节之外，不补未读
的实体、币种或条件，也不把模型claim当作已验证事实。

| 检查 | 结果与边界 |
| --- | --- |
| `corpus-final/summary.json`固定原件回放 | 323份HTML，217份增加supplement，共359个完整script，零省略；所有原正文prefix、诊断、分类和原件hash保持不变。323按档案计，包含重复网页；不是323个独立网站。最终生产文件hash冻结通过 |
| 初始集成回归 | 436通过；覆盖HTML、fetch、archive access及baseline相关流程 |
| 最终边界回归 | 103通过，包含新增exact provenance cap、压缩引用来源、未读值不泄露、两种诊断并存的1024字feedback上限，以及真实SQLite/受控角色修复交付；和436有重叠 |
| `live/`真实工具 | Meta与Python 3.12官方文档均成功，分别2/49次4096-byte读取，原件/正文/index/完整读回核对通过；无模型调用 |
| `live-final/`最终生产版 | Meta原正文906bytes，完整档案5216bytes，新增4310bytes含3967byte JSON；2次read读全。Windows Job峰值67227648bytes，512MiB额度不变；无需Chromium，清理完成 |
| `formal-distillation/` | 从已关闭的真实fetch库复制，原问题逐字为`compare meta quest 3 and apple vision pro`，历史plan/as_of不改；两个模型各一次Distiller4，正式distill_sources及deliver_evidence成功。不是Planner→Writer完整workflow |
| `delivery-verification.json` | 两个实际结构化role inputs逐字相同，5216原文字节/2个真实read segments完整；独立重建task、子agent、provider request body摘要及context字节数全部匹配。只证明本地记录的派发承诺，不证明远端attention |
| `store-audit.json` | integrity ok、FK零异常、pending零；30 artifacts、1 snapshot、4次segment交付、8条有效finding；引用/read/hash审计无异常，原fetch库hash保持不变 |

实际阅读两模型输出：DeepSeek保留6条finding，其中CAD价格明确标为
publisher-declared JSON-LD；GPT保留2条可见特征，主动不采用未验证价格。
GPT同样收到完整原件补充段，没有工具截断证据。DeepSeek另把原文的
`MerchantReturnFiniteReturnWindow`写成`ReturnPolicyFiniteReturnWindow`，
该finding正确排除；不得用宽松匹配“修复”改写的标识符。
DeepSeek还错误地把完整交付的JSON-LD称为partial，GPT未采用价格；这两项
保留为模型解释/选择观测，不据此给instruction加入头显特例。

当前证明的是结构化数据不再静默丢失以及真实交付链可验证，未宣称报告
质量已整体提高。未改六个角色版本、原测试问题、两轮/40次fetch/256k额度。
第30阶段renderer失败域与静态结果保留、无标签SVG、PDF不透明公式以及
保守格式边界仍待处理；没有把活动目标标为完成，也没有再次跑16套完整
workflow或修改旧成功/失败状态。

## 第三十四阶段：父进程监督fetch、完整对照测试与停止点

本轮代码和文档已收尾，随后冻结生产源码，按用户要求完成一次最终测试后
停止扩展修复。证据在`local/fidelity-cycle-20261004/render-supervision/`；
`final-evaluation.json`是六次完整运行的汇总，`final-matrix/`保存原请求、
事件、原始档案、草稿/报告及逐库审计。没有修改问题原文、Agent instruction、
六个角色版本、两轮研究、40个attempted URLs或262144-token Agent额度。
`baseline@13`仅将fetch pin从2升级到3；旧方法、工具和历史实验保持可用。

### 已完成的边界

`web.fetch@3`的父进程先验证静态proposal，必要时才在独立worker中尝试
Chromium。单次durable intent预先授权两个不同阶段；共享原60秒、40个
HTTP请求、32MiB网络decoded bytes、stdout/stderr额度，仅提交一次最终
snapshot。每个worker的512MiB Windows Job不变。脚本单资源上限在新工具
修订中为8MiB，受总额度约束；旧@2仍是2MiB。子阶段不会自动重跑。

有效静态结果可以在renderer确认终止/清理后保留；取消、未知清理、损坏
协议、错误身份、目的地策略故障不能伪装成成功。进程真实退出/峰值/请求
与响应hash都记录到`process.stages`。渲染流量未知时总计为null，已知下界
另列，不能把静态计数或零当成总计。静态与渲染原件不拼接。替换必须保留
原正文块、literal代码缩进、声明日期及完整JSON-LD，并增加正文信息。

独立Astra复核和Sol故障注入额外发现四处问题，已在冻结前修复：代码缩进
被空白归一化掩盖；curl shell后HTTPX503漏走旧有Chromium恢复路径；失败
worker的backend/计数未在提交前校验；替换原件时声明日期可能丢失。正文
检查保留解析上下文，仅允许不改变既有inline token的原样段落前缀扩展。
保守拒绝仍会损失部分可用渲染内容，不能称为无损通用转换。

| 验收 | 结果及解释 |
| --- | --- |
| 专项故障/集成回归 | 199通过：161项supervisor、23项真实SQLite集成、15项独立复核回归。此前两个失败计数断言保持严格并已通过 |
| 新方法与反馈 | 方法13只改fetch pin；supervision、graphics、32条JSON-LD ranges加修复反馈仍满足既有Distiller合同。相关3项通过，与全量有重叠 |
| 全量与必要复测 | 最终生产源码下3228通过、1条旧测试仍断言fetch@3不存在；更新为默认仍@1、显式@3存在、@4不存在后，该组23项及最后失败项复测通过。最终覆盖3229项，无未解决测试失败。较早的过渡版全量17项失败完整保留，其中16项属于已修正的过严正文块比较；不把多轮重叠测试相加 |
| `live-final/` | Meta和Python 3.12文档均成功，2/49次读取完整，原件/正文/index与hash一致，清理完成且源码冻结通过。Meta renderer真实memory_limit后保留107-byte正文加4310-byte JSON-LD supplement，共4417bytes；并不证明动态内容完整 |
| `browser-acceptance-final/` | 合成HTTP内容、真实Engine/SQLite/worker/Chromium。2560170-byte脚本实际执行，新增正文被选用并完整读回，Job峰值418590720bytes、原512MiB上限不变。不是公共网站成功率样本 |
| 保守拒绝对照 | 早期受控样例的renderer成功但提取器漏了静态标题，正确保留静态版本；原失败断言与档案留在`browser-acceptance/`。后续正例改变fixture为不含标题的独立控制，没有为通过测试放宽生产保真检查 |

### 六次最终完整workflow

原始三个问题逐字不变，不预置URL或手选query，不自动重跑失败运行。在线
搜索和模型路径不同，以下是一次验收批次，不是固定证据的模型排名或因果A/B。

| 问题 / 模型 | Fetch成功/尝试 | 发布结果 | 实际判读 |
| --- | --- | --- | --- |
| 头显 / GPT | 5/7 | 英文报告，sufficient | 简明、有价格冲突及估计值限制；主要依赖比较页，官方代际覆盖仍弱 |
| 头显 / DeepSeek | 21/27 | 未发布，REPORT_REVIEW_FAILED | 已阅读最后草稿：引用r1.source-003却未列References，四次审核后仍混淆两个未蒸馏chunk与读取次数。抓取/存档通过；不归因为工具丢失引用条目 |
| 航班 / GPT | 7/7 | 英文报告，partial | 区分YUL/YHU/YMQ、总时长与不含中转的飞行时间；披露Flightconnections和Trip页面结构风险，仍缺具体行程的官方规则证据 |
| 航班 / DeepSeek | 18/18 | 未到Writer，provider.transport | 第二轮Analyst发生ReadError；18份来源仍完整保留。不是fetch失败，也不是已证实的模型能力或context超限 |
| 睡眠 / GPT | 4/12 | 英文报告，sufficient | 结论谨慎，区分主观问卷和活动记录仪结果；最终主要引用一篇综述，覆盖较窄 |
| 睡眠 / DeepSeek | 9/9 | 英文报告，sufficient | 内容较广，保留观察性研究/无对照/摘要限制；大量二手健康摘要仍不等于原始试验的独立核验 |

四份已发布报告和DeepSeek最后一份头显草稿均已实际阅读。共120次模型调用、
80次URL尝试、64份成功snapshot；64/80不是通用网站可达率。失败16次为
8个FETCH_HTTP_ERROR、3个REDIRECT_LIMIT、3个SOURCE_REQUIRES_RENDERING、
1个UNSUPPORTED_CONTENT和1个EXTRACTION_EMPTY。六库审计全部通过：1229份
artifact、173次读取片段、366条有效finding，integrity ok、FK/pending/引用
关联检查均无异常。真实workflow中5个来源成功用renderer恢复，1个Meta
来源在真实内存终止后保留静态结果；这些诊断均进入实际Distiller输入。

`dispatch-verification.json`独立核对120次本地role→子agent→provider
request承诺、199个实际输入segment的hash及6次supervision反馈，无差异。
这证明本地存档与派发准备一致，不证明远端收到了全部内容、模型attention
或事实本身正确。初版审计harness曾错误地假设workflow action ID对每个
node唯一，已改用role pin、输入digest与child run绑定；没有修改生产数据。

370条被处理finding中4条被严格引用检查排除：MakeMyTrip的`stopovers`被
改成`layover duration`，是实际改词；其余三条涉及连续HTML span的间距、
部分保留Markdown链接，以及链接前原文无空格等保守格式边界。尚未支持
的格式表达仍可能损失有效finding，不能把四条全部归为模型能力问题。
两个模型均见到Flightconnections仍有5个未解决结构块；GPT的Trip页面另有
5个。诊断只是风险提示，并非逐条已证实的语义遗漏计数。

### 仍存在的限制及是否继续

1. **传输错误的可观测性和恢复边界值得小范围继续。** `transport-review/`
   独立核对第二轮Analyst在16.429秒后ReadError，记录/清理完成，但远端
   completion和usage未知，provider IDs/status均未保留。现有恢复规则
   正确拒绝未知结果的重放。当前adapter在整个响应生命周期外统一捕获
   HTTP错误，日志不足以区分未收header、读取body中断或错误响应读取失败。
   先保留安全的阶段、状态/请求ID、收字节数、分类cause，再用故障注入评估
   可恢复范围；不能凭一次事件声称高频瓶颈，也不能简单扩大重试次数。
2. **失败后的质量快照新鲜度需要明确。** 航班DeepSeek的`quality`仍是第
   一轮10份来源的checkpoint，`sources`已有18份。两者并非数据丢失，
   但界面/API缺少显式round/as-of标记，容易造成额度和进度误读。
3. **动态网页完整性仍受限。** Meta超内存后的静态fallback有用但不完整；
   短正文触发器有false negative/positive，保真检查也会拒绝漏标题或改
   版式的渲染结果。值得在实际动态来源占比足够大时评估独立renderer
   profile，暂不为单一站点加规则或无条件增加512MiB限额。
4. **复杂格式仍有边界。** 不明SVG图形、PDF公式/字形、部分HTML列表表格、
   上述三类引用格式仍未通用解决。保留fixture和明确警告；只有目标研究
   经常依赖这些内容时，才优先新增专门视觉/文档读取能力。
5. **可达性、研究覆盖和写作仍决定报告上限。** 网站拒绝/重定向、学术
   backend准入或额度限制仍存在。报告审核失败、20次蒸馏额度、官方来源
   和原始试验覆盖不足属于另外的责任边界；没有为此改baseline机制或
   过拟合instruction。`sufficient`是workflow质量状态，不是准确率认证。

建议停止无边界的工具层场景穷举和零碎格式修补。若继续，限定为一次
传输诊断、质量快照新鲜度与恢复边界的工程任务；是否扩大renderer或
引入视觉读取，应由实际任务失败占比决定。本轮未commit/push，所有实验
和子任务已结束，未安排自动继续或追加实验。
