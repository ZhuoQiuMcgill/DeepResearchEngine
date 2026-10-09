# DeepSeek 与 GPT：三个话题的报告对比

后续阶段的主目标是发现模型之外的系统性错误。本页保留原实验观察；
[系统性错误审计](systemic-error-audit.md) 将这些失败用于接口、读取、修复和错误传播的复现与验收设计。

实验日期：2026-10-03。问题保持用户原文，所有输出为英文。

**本次样本中，GPT 的报告在证据选择、事实限定和引用格式上更好；DeepSeek 通常写得更长、列得更多，但也保留了更多矛盾和噪声。完整 workflow 的稳定性还受到模型输出契约、引用校验和抓取错误处理的共同影响。**

这里有两个独立实验，不能把它们的产出混在一起：

- **完整 baseline@10：6 次新运行，只有 2 份正式报告。** DeepSeek 0/3；GPT 2/3。四次失败全部保留，没有重跑后择优替换。
- **同证据 Writer 对比：额外 6 次单独的 Writer 调用，得到 6 份草稿。** 每个话题给两模型完全相同的证据和任务，便于比较报告本身。这些草稿没有经过完整研究流程和 Reviewer，不是补成功的 baseline 报告。

## 1. 对比条件

| 项目 | 配置 |
| --- | --- |
| DeepSeek | `deepseek-flash`，官方 endpoint，`thinking: disabled` |
| GPT | `gpt-6-luna`，官方 endpoint，Responses API，`reasoning_effort: low` |
| 完整 workflow | `baseline@10`；Planner 4、Selector 3、Distiller 3、Analyst 5、Writer 6、Reviewer 5 |
| 工具 | `web.search@4`、`web.fetch@2`；本地 SearXNG；curl_cffi / HTTPX / Chromium |
| 共同预算 | 最多两轮、全程最多 20 个 fetch URL、最多 4 次报告尝试、4 个并行 Agent、最多 20 次蒸馏调用 |
| Context | 单 Agent 262,144；证据 131,072 token / 524,288 bytes；估算器为 UTF-8 bytes/4，不是经校验的模型 tokenizer |
| 原始问题 | `compare meta quest 3 and apple vision pro` / `How do I flight from GuangZhou to Montreal?` / `What food can help me sleep well?` |

每次完整运行使用独立数据库，顺序运行避免相互争抢搜索服务；各题交替模型先后顺序。固定 269 个源文件、角色资源及配置/依赖文件的 SHA-256，结束后重新校验，全部一致。两模型使用相同角色内容，但 provider 协议和 reasoning 设置不同，因此这是当前项目配置的对比，不代表两模型家族的全部能力。

每格只有一次采样。完整运行会自主生成不同搜索词、选择不同来源，因此不能把最终差异全部归因于模型阅读同一材料的能力。评阅由本次主助手完成、模型身份可见；不是盲评、人工评测或统计显著性实验。没有以篇幅或内部 `quality.status` 代替准确性评分。

## 2. 完整 workflow：实际交付了什么

耗时是已记录的 `workflow.accepted` 到 `workflow.finished`；token 是 provider 返回的输入与输出总量，包括重复读取上下文。

| 话题 | 模型 | 正式报告 | 模型调用 | 成功抓取 / 尝试 | 耗时 | 已知总 token |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 头显 | DeepSeek | 未生成：读取范围错误 | 12 | 10 / 14 | 88.3 s | 89,966 |
| 头显 | GPT | [已生成](../local/model-report-comparison-20261003/headsets-gpt-evidence/report.md) | 13 | 6 / 8 | 113.0 s | 158,564 |
| 航班 | DeepSeek | 未生成：Selector 分类冲突 | 13 | 8 / 8 | 83.8 s | 195,352 |
| 航班 | GPT | [已生成](../local/model-report-comparison-20261003/flights-gpt-evidence/report.md) | 10 | 4 / 4 | 62.8 s | 56,484 |
| 睡眠 | DeepSeek | 未生成：蒸馏引用校验失败 | 14 | 8 / 10 | 59.9 s | ≥104,160 |
| 睡眠 | GPT | 未生成：浏览器抓取响应超限 | 2 | 3 / 4 | 33.0 s | 12,414 |

DeepSeek 睡眠运行有一次模型调用没有返回 token 用量，上表是已知下限，不能把缺失算成零。失败运行可能较早停止，不能用其耗时/token 宣称模型更高效。成功抓取数量也不等于独立可靠来源数量。

### 失败来自哪里

| 运行 | 已核实原因 | 归因及影响 |
| --- | --- | --- |
| DeepSeek 头显 | Analyst 对 Springer 的 HTML 摘要申请 `pages [3,13)`。快照无物理页码，`document.read` 返回 `UNSUPPORTED_RANGE`，workflow 以 `SOURCE_READ_FAILED` 终止。此前 18 次 document.read 成功，第二轮已经抓到 Apple 官方规格。 | 模型把摘要当成可按页读取的全文；workflow 将无效补读视为致命错误。不能说档案不可访问或搜索没返回资料。 |
| DeepSeek 航班 | 第二轮 Selector 输出是合法 JSON，但有 **16 个候选 ID** 同时出现在多张分类列表里；其中一个既 selected 又 rejected。离线重放原输出可复现 schema 校验失败。 | 输出语义契约问题，非本次 JSON 围栏问题。不是搜索或抓取失败，8 个来源已成功存档。 |
| DeepSeek 睡眠 | 蒸馏第一次有引文不匹配，修复时又把原文中的 `[increases](URL)` 改成普通 `increases`，引文无法逐字匹配 Markdown 原文，第二次校验后终止。 | 模型没有保留精确引用格式，且原文展示与校验耦合。该处并不能据此认定是捏造医学事实。 |
| GPT 睡眠 | `10.1201/b19308-29` 跳转 Taylor & Francis；静态两个后端均无可提取正文，浏览器阶段返回 `RESPONSE_LIMIT`。该阶段观察到 14 次请求、3,550,745 decoded bytes；记录不足以定位触发超限的具体子资源。 | 工具/编排边界问题：单次抓取的 `limit_exhausted` 被 acquisition 提升为整条 workflow 终止。不是 GPT 写报告失败；当时尚未调用 Writer。 |

失败证据：[头显/航班离线复核](../local/model-report-comparison-20261003/failure-audit.json)、[DeepSeek 睡眠原始输出](../local/model-report-comparison-20261003/sleep-deepseek-diagnostics/distiller.10.output.json)、[该次原始输入与修复反馈](../local/model-report-comparison-20261003/sleep-deepseek-diagnostics/r1.recovery.distill.r1.recovery.source-007.chunk-001.2.input.json)、[GPT 睡眠事件](../local/model-report-comparison-20261003/sleep-gpt-diagnostics/events.json)。

### 两份正式 GPT 报告也不是无问题

**头显：**804 words，使用场景讲得清楚，能限定启发式研究的摘要证据。但其价格段依赖第三方 2026 文章：Quest 3 $499.99、Vision Pro M5 $3,699，并没有完成官方核实。评阅时 [Meta 美国官方页面](https://www.meta.com/quest/quest-3/) 显示 Quest 3 512GB 为 $599.99；[Apple M5 发布公告](https://www.apple.com/newsroom/2025/10/apple-vision-pro-upgraded-with-the-m5-chip-and-dual-knit-band/) 则给出 $3,499 起。因此报告把更低 Vision Pro 价格解释成旧型号/旧时期的差异，依据不充分。Apple 当前商城没有向评阅工具返回可读价格，不能把发布价冒充已验证的当前成交价。报告虽然加了限定语，仍未解决用户需要的现价、同代产品比较。

**航班：**376 words，正确区分飞行时间和含 layover 的总时间，还识别出同一来源前后矛盾。但主要是路线概览，没有给出具体航司和中转证件核查；两个 Skyscanner URL 也不是两个独立信息源。它被内部标为 `sufficient`，不能据此认定旅行决策所需信息已经覆盖完整。

## 3. 同证据条件下，报告质量怎样

为避免四次中途失败导致无文可比，追加了 Writer-only 实验：

- 每题取两次原运行中**已经成功存档、完整读过、SHA-256 校验通过**的来源并集；按 exact URL 去重，同 URL 选择最长完整版本，再按 URL 排序。
- 头显 13 份来源 / 164,859 evidence bytes；航班 10 份 / 222,769 bytes；睡眠 9 份 / 222,190 bytes。未把评阅时额外查到的官方资料加入输入。
- 两模型共用相同的中性 plan、只授权 source ID 的 analysis 占位记录、原文证据、空 feedback 和 `partial` 标签；不使用任一模型的蒸馏摘要或事实结论。
- 均调用原有 `baseline.writer@6`，262,144 context、8,192 output token 上限，每格一次调用。六次 `agent.started.task_input_digest` 证明每题两份输入完全一致；六次 instruction digest 一致。
- 没有运行 Reviewer、修复或重新搜索，因此以下六份是**未验收草稿**。它们与上一节正式报告的上下文不同，不能用于测量 Writer 替换后完整 workflow 的提升。

| 话题 | DeepSeek 草稿 | GPT 草稿 | 本次质量判断 |
| --- | --- | --- | --- |
| Quest 3 / Vision Pro | [1,214 words](../local/model-report-comparison-20261003/writer-pairs/headsets-deepseek-draft.md) | [942 words](../local/model-report-comparison-20261003/writer-pairs/headsets-gpt-draft.md) | **GPT 明显更好**：使用官方 M5 信息较一致；DeepSeek 主表与后文混用代际，并有引用格式错误。 |
| 广州 → 蒙特利尔 | [1,255 words](../local/model-report-comparison-20261003/writer-pairs/flights-deepseek-draft.md) | [468 words](../local/model-report-comparison-20261003/writer-pairs/flights-gpt-draft.md) | **GPT 更好用于决策**：重点、步骤更清楚。DeepSeek 路线和数字更多，但重新混淆了飞行时长与总耗时。 |
| 食物与睡眠 | [845 words](../local/model-report-comparison-20261003/writer-pairs/sleep-deepseek-draft.md) | [680 words](../local/model-report-comparison-20261003/writer-pairs/sleep-gpt-draft.md) | **倾向 GPT**：证据强弱、研究对象与普通食物之间的界限更清楚。DeepSeek 食物种类和机制覆盖更多。 |

### 头显：会不会正确使用已经拿到的证据

GPT 的主表使用 M5+R1、750–800 g、一般使用最长 2.5 小时和视频最长 3 小时，并区分屏幕总像素和单眼分辨率；与输入中的 [Apple 官方 M5 规格](https://www.apple.com/apple-vision-pro/specs/)一致。它还保留“没有随附运动控制器”和“支持外接控制器”的区别。

DeepSeek 主表仍写 M2+R1、600–650 g，后文才引入 M5 的续航；开头说 Quest 3 在续航上占优，又在表中列出 Quest 3 2.2h / Vision Pro M5 2.5h。它在局限里承认混代，却没有把主比较改成同代或明确分栏。这不是缺资料：同一输入已经含官方 M5 页面。

DeepSeek 还有可自动核验的格式问题：正文引用不存在的 `[quality]`；正文用了 `source-007`，References 缺该条；References 列了正文没用的 `source-012`；参考文献标签省掉规定的方括号。GPT 三篇均没有这些 source-ID/References 集合问题。

GPT 也有不足：仍转述旧 Quest 3 容量/价格；在生产力段把 EveryMac 的描述归为 Apple 页面，归属不够准确。同证据结果支持“本次 GPT 更好”，不支持“GPT 报告已经完全正确”。

### 航班：列更多信息，还是给出可靠行动

DeepSeek 记录了更多中转点、距离、时区和报价，也明确提醒报价非实时。但它把一个飞行时间计算器与航线数据库当成“直飞是否存在”的冲突，增加了不必要的歧义；虽随后限定计算器不是排班证明，仍占据大量篇幅。

更具体的问题是：DeepSeek 前面正确写 FlightConnections 的 16h20m–23h55m **不含停留时间**，后面又把约 16–28 小时写成连接行程的总时长。这是同一报告内部的事实限定丢失。

GPT 保留 CAN/YUL、主要中转点、航司和示例耗时，给出核对日期、落地机场、单票/分开出票以及证件的操作顺序，省去不可靠的即时价格。它对这些来源仍只能做到路线建议，没有官方逐日航班或个性化签证结论。真正订票前需要日期、护照/身份与中转方式；官方核查入口是 [加拿大入境文件查询](https://www.canada.ca/en/immigration-refugees-citizenship/services/visit-canada/check-visa-eta.html)，涉及美国中转时还需核实[美国中转要求及例外](https://travel.state.gov/content/travel/en/us-visas/other-visa-categories/transit.html)。这不是根据广州出发推断用户国籍。

### 睡眠：营养机制不等于已证明的食物疗效

DeepSeek 覆盖酸樱桃、奇异果、鱼、坚果、乳制品、蛋白食物、镁食物和茶，解释机制也较多；末尾明确写证据有限、相关性不等于因果，这是优点。

问题是限定主要集中在末尾。坚果段提到褪黑素+镁+锌的试验时，省去了原文的 **supplements**，容易让读者把补充剂组合试验当成吃坚果的效果。部分生理机制也写得比临床效果证据更确定。

GPT 明确写出“有这些营养素不代表吃一份就能助眠”，以及儿童 DHA **补充剂**研究不能直接推出吃鱼对所有人有效；同时给出简单食物选择、晚餐与刺激物的考虑。原 DHA 研究确实涉及特定儿童样本，客观睡眠改善来自较小的 actigraphy 子样本，不能泛化成所有人吃鱼的效果。[原研究](https://pubmed.ncbi.nlm.nih.gov/24605819/)

两份都没有建立每种食物的完整试验质量矩阵，也不能当成个体化医学建议。GPT 的优势主要是表述与证据校准；DeepSeek 的优势是材料覆盖广。

## 4. 同证据 Writer 的开销与格式

| 话题 | DeepSeek token / 耗时 | GPT token / 耗时 | 格式核查 |
| --- | ---: | ---: | --- |
| 头显 | 46,056 / 11.2 s | 44,330 / 14.7 s | DeepSeek 有未知标签、漏参考、冗余参考；GPT 无这些错误 |
| 航班 | 63,669 / 11.9 s | 59,881 / 7.1 s | 两份均通过现有基础检查，引用集合一致 |
| 睡眠 | 54,598 / 8.4 s | 55,143 / 10.8 s | 两份均通过现有基础检查，引用集合一致 |

六份均完成 Agent 执行和持久化，但执行成功不代表草稿通过 Reviewer。不同模型的 tokenization 和 reasoning 计数不同；这里不据此推断货币成本或统计性速度优势。

## 5. 对当前项目意味着什么

这次实验支持把 GPT 视为这组三题中更好的 Writer 候选，尤其是有版本冲突、研究对象限制和引用格式要求的时候。但直接切模型还不足以保证 baseline 交付。

| 层 | 这次暴露的问题 | 后续改进方向（本轮未改实现） |
| --- | --- | --- |
| Source access 接口 | 模型能对 HTML 申请不存在的物理页码 | 显式提供可读 range kind/边界；申请前校验，反馈可恢复的请求错误 |
| Selector 输出 | 同一候选出现在多个互斥分类 | 保留严格契约，用精确错误反馈做有预算的修复 |
| 蒸馏引用 | Markdown 链接被自然语言模型化简后无法 exact-match | 把引用定位与展示文本分开，同时保留原文 hash/offset 与可验证映射 |
| Fetch 与 acquisition | 单响应大小上限终止整场研究 | 区分单 URL/子资源失败与全局预算耗尽；记录触发资源和具体阈值 |
| Evidence quality | 错误/过时网页可被忠实转述；内部 sufficient 未验证真伪 | 强化时间、型号、官方来源与冲突核实；不要只增加搜索数量 |

不能把失败统一说成工具故障，也不能统一说成模型能力差。四个终止原因分别落在范围契约、分类契约、精确引用格式和抓取错误传播上。

## 6. 可复核记录

- [完整实验协议与文件 hashes](../local/model-report-comparison-20261003/protocol.json)
- [六次完整运行状态](../local/model-report-comparison-20261003/progress.json)
- [Writer 配对协议](../local/model-report-comparison-20261003/writer-pairs/protocol.json)
- [同证据原始输入：头显](../local/model-report-comparison-20261003/writer-pairs/headsets-input.json)、[航班](../local/model-report-comparison-20261003/writer-pairs/flights-input.json)、[睡眠](../local/model-report-comparison-20261003/writer-pairs/sleep-input.json)
- [汇总指标、模型身份、引用检查及数据库审计](../local/model-report-comparison-20261003/comparison.json)
- [完整运行驱动](../local/model-report-comparison-20261003/run_all.py)、[配对输入构造](../local/model-report-comparison-20261003/prepare_writer_pairs.py)、[Writer 调用驱动](../local/model-report-comparison-20261003/run_writer_pairs.py)、[只读验证脚本](../local/model-report-comparison-20261003/summarize.py)

12 个数据库均通过 `integrity_check` 和外键检查；没有未收束的 operations；全部 ready artifact 的 byte length/SHA-256 已验证。两个正式报告通过 HTTP 分块读取、SSE 重放、幂等提交和服务重启后报告字节一致性检查。原始请求、模型输入摘要、输出、失败和已知/未知用量均保留。证据在被 Git 忽略的 `local/model-report-comparison-20261003/`，本页是仓库内的对比记录；本轮没有推送。
