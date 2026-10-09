# Baseline 系统性错误审计

本页保留修复前的发现与复现。后续实现见 [baseline 11 契约](usage/baseline-reliability.md)，
修复、测试和新发现见 [迭代记录](systemic-repair-results.md)。

2026-10-03。本阶段的目标是发现模型之外的系统拖累：查询是否被改坏、档案是否被正确读取、必要元数据是否交给 Agent、格式错误是否得到可定位的反馈，以及局部失败是否被放大成整场失败。模型对比提供故障样本；本页不据此给模型排名。

审计复用 [六次 baseline 10 实验](model-report-comparison.md) 的原始档案、事件和输出，补充离线故障注入及真实 Chromium 的受控 HTTP relay。三题原始输入保持为：

- `compare meta quest 3 and apple vision pro`
- `How do I flight from GuangZhou to Montreal?`
- `What food can help me sleep well?`

本次新增诊断脚本和文档，未修改生产实现或历史实验输入、输出，没有新增模型调用。下列问题仍待修复。受控探针观察到缺陷，不代表系统通过验收。

“实测”指六次完整运行或另行标明的 Writer 草稿中发生；“注入”指用生产函数接收受控响应复现；“契约”指输入、指令或校验代码存在可核对的缺口。不能把注入错误说成数据库实际发生了串档。

| 问题 | 已确认的行为和影响 | 证据范围 | 修复后的验收条件 |
| --- | --- | --- | --- |
| S01 读取能力没有完整交付 | SourceRecord 有总行数和物理页数；Analyst 只拿到已交付片段的 range，没有完整边界和支持的 range 类型。URL 含 `/content/pdf/`，实际档案却是 HTML。头显实验对它申请 pages 后终止。 | 实测 + 注入。错误请求是模型产生的；系统缺少明确的能力交付和申请校验。 | 证据带行数、页数、可用 range 类型、内容类型和实际落地 URL；不支持的请求在调工具前得到具体反馈。 |
| S02 补读绕过首次读取的完整性检查 | `_fulfill_reads` 没有复用 `_outcome` / `_slice`。错误 snapshot、错误 requested_range、虚报 byte_length、范围外 span、超出 byte cap 的正文，五类注入全部被补读接受，首次读取的校验器则全部拒绝。 | 注入。没有证据表明本轮真实数据已经读串。 | 首读和补读共用生命周期、身份、字节范围和 continuation 校验；五类错误均拒绝，合法对照仍通过。 |
| S03 单 URL 上限被当成整场额度耗尽 | acquisition 对所有 `limit_exhausted` 都抛出“shared execution limit”。睡眠 GPT 在第四次 fetch 失败时已有三个成功档案，仍整场终止。注入也证明下一 URL 保持 pending、不再执行。 | 实测 + 注入。 | 错误标注 resource / fetch / run 范围；已结算的单 URL 失败可隔离，保留已有证据；全局耗尽、取消、未知提交和未完成清理仍停止。 |
| S04 非必要浏览器资源失败也废弃可用正文 | Chromium 已收到可用 HTML，一个辅助脚本的 RESPONSE_LIMIT 就使整个 capture 失败。相同页面的辅助脚本 FETCH_UNAVAILABLE 则允许成功。错误记录缺少明确的触发资源、上限类型和阈值。 | 真实 Chromium + 受控 relay。真实睡眠日志不能确定哪个资源触发，不能将注入原因冒充实测根因。 | 分开标注主文档、必要和辅助资源；非必要资源失败不废弃可用正文，局限被记录；必要内容未渲染不能假装完成。错误保存触发 URL、resource type、cap 和 scope。 |
| S05 一个蒸馏任务失败取消其他独立任务 | `bounded_map` 的 fail-fast 被直接用于文档蒸馏；一份文档的错误导致同批未完成任务取消，结果无法进入后续综合。睡眠 DeepSeek 的局部引文失败因此终止整场研究。 | 实测 + 注入。通用 mapper 的取消收束本身不是缺陷，问题在独立文档任务的隔离策略。 | 文档分别返回成功、隔离或无法确定状态；可隔离内容错误不取消独立文档。全局预算、用户取消和基础设施故障仍统一收束。 |
| S06 引文表示与原文表示不一致 | Healthline 存档含 `[increases](URL)`，重试输出为可见文本 `increases`，当前匹配拒绝该引文。拒绝不匹配原文是正确的，但 Markdown 展示与引用定位绑在一起增加了格式失败。 | 实测 + 原输出回放；原文对照匹配，改事实的负对照拒绝。 | 引文绑定不可变 snapshot 和字节区间；若提供可见文本，必须有可逆的原文映射。不能用模糊匹配或无映射的删除标记放宽证据标准。 |
| S07 修复重新破坏已经匹配的结果 | 首次 10 条引文中 9 条匹配；修复输入没有上一版完整输出，只给错误 index、引文和原文。重试生成 6 条，5 条匹配，原本正确的 tryptophan 引文丢失 Markdown 链接。角色指令要求删除失败项且不要重构，host feedback 却允许改成较短引文，并要求 4–6 条。 | 实测 + 输入和指令核对。引文匹配不等于 claim 语义正确。 | 修复携带原输出和字段级错误；限定修复范围，已验证项保持稳定；instruction、feedback 的删除/重写规则一致，不因修复强行补数量。 |
| S08 格式恢复和错误细节不一致 | Distiller 的两次尝试只覆盖语义引文校验；JSON/schema 错误在 try 外抛出，注入仅调用一次。Selector 实测有 16 个跨列表重复 ID，严格拒绝正确，但无有预算的修复；decision 丢掉字段路径和冲突 ID。补读把 UNSUPPORTED_RANGE 压成 SOURCE_READ_FAILED。 | 实测 + 注入 + 契约。重复 ID 本身不能归为工具错误。 | 保留原错误码、字段路径、冲突 ID 和输出引用；各角色使用明确、有限且计入原预算的格式修复策略。持续无效仍拒绝，不静默任选分类。 |
| S09 搜索准备改变查询语义 | `site:apple.com ... after:2025-10-15 -rumor` 被改成普通词，排除词变成正向关键词；`C++` 变成 `c`；产品名引号丢失。真实航班查询的 quoted title 后 `booking advice` 也被删除。 | 注入 + 实测查询档案。六次实测没有上述 site/date/operator 组合，不能据此解释全部覆盖不足。 | 原查询可原样执行；变体作为额外查询单独留存、计费，保留操作符和实体。后端不支持的语法做明确适配，不能静默破坏。 |
| S10 引用的机械规则依赖 Reviewer 判断 | `citation_issues` 只检查整篇出现的 ID，不区分正文与 References，也不校验 ID 对应 URL。没有 References、只在 References 引用、正确 ID 配错误 URL 三种探针均返回空问题列表。 | 注入。Writer-only 草稿去掉唯一未知 `[quality]` 后也通过检查，但缺参考条目和标签格式问题仍在。该草稿未通过正式验收。 | 正文 ID、参考文献 ID、允许来源 ID 做集合和唯一性检查；URL 从 host 来源表绑定。Reviewer 处理语义问题，不能替代确定性检查。 |
| S11 时间和来源元数据在交接时缺失 | 角色任务没有统一的显式研究基准时间。档案的 retrieved_at、final_url、media_type 没进入 evidence block；Selector 部分书目信息没有以结构化 source card 贯穿后续角色。正文可能含日期，但不保证有。 | 契约 + 注入。不能据此断言报告旧价格或混代只由系统造成。 | 请求和角色输入有统一 as_of；保留抓取时间、已知发布日期、原始/实际 URL 和内容类型，缺失标 unknown；抓取日期不能冒充发布日期或现价有效期。 |

## 四次终止说明了什么

| 实验 | 直接触发 | 系统应承担的部分 |
| --- | --- | --- |
| 头显 DeepSeek | 对没有物理页映射的档案请求 pages | 交付能力描述、申请前检查、保留具体错误和可恢复反馈。 |
| 航班 DeepSeek | 同一 candidate 出现在互斥分类 | 严格拒绝，同时提供可定位、有限次数的修复机会；避免三份列表造成不必要的协调负担。 |
| 睡眠 DeepSeek | 修复后引文与保存的 Markdown 不匹配 | 引用表示契约、稳定修复、独立文档隔离。 |
| 睡眠 GPT | Fetch 返回 RESPONSE_LIMIT | 记录具体限制范围；避免单次获取问题废弃已有资料。 |

这四次失败都有需要检查的系统边界，但不意味着修复后四次都会生成合格报告。模型仍可能重复输出无效决定或得出错误结论。更强模型绕过脆弱路径，也不能证明该路径可靠。

## 修复顺序与验收方法

先处理 S02 的读取一致性，以及 S03–S05 的错误范围和隔离，避免错误证据进入综合或局部故障丢掉整场成果。随后完成 S01、S06–S08 的角色契约、引文表示和修复机制，再补齐 S09–S11 的查询保真、机械引用验收和时间元数据。每组修复单独回放对应失败，再跑三个原问题，保持模型、轮数和预算可比。

验收同时保留正确响应、局部故障、全局故障三个方向的控制。局部失败可继续时必须显式降级并记录缺口；未知持久化、取消、清理失败或未验证证据不能被“容错”掩盖。

最终报告只是其中一层。每题还应记录：原查询与执行查询是否等价、来源是否完整存档、首读/补读是否验证、实际交付哪些字节和元数据、修复有没有破坏已验证项、局部失败影响多少来源、最终引用是否符合确定性规则。完成这些之后，剩余的研究策略和事实推理差异才有条件单独讨论。

仍需扩大测试：PDF 表格/OCR/多栏、网页日期与 canonical 元数据抽取、重复来源/转载独立性、token 估算与真实上下文准入、工具生命周期和 Hooks 异常。它们是待测范围，不冒充已发现漏洞。相同主机的两篇文章并不自动是同一证据；`substantive_sources` 也不应解释为独立机构数量。

## 复现与证据

[诊断脚本](../examples/benchmarks/probe_systemic_errors.py) 调用生产函数并输出观察结果；它不是将错误行为写成正确要求的回归测试。使用项目原有的 native Windows uv 环境：

```powershell
uv --cache-dir .uv-cache run --locked --offline python -X utf8 -m examples.benchmarks.probe_systemic_errors --experiment local/model-report-comparison-20261003 --output local/systemic-error-audit-20261003/probes.json --browser
```

`--experiment` 可省略，以仅运行合成探针；`--browser` 需要项目 Chromium，使用仓库测试的内存 relay，不访问公开网站。本次两项均执行：8 组基础受控观察、6 组历史档案观察和 2 个 Chromium 场景；组数不是独立 bug 数。合法读取对照通过，未知引用和改事实引文对照被拒绝，普通辅助资源故障对照保留正文。

- [完整探针结果及生产 Python 文件 hashes](../local/systemic-error-audit-20261003/probes.json)
- [六次完整运行与六次 Writer 草稿汇总](../local/model-report-comparison-20261003/comparison.json)
- [原始页面范围错误与重复分类输出](../local/model-report-comparison-20261003/failure-audit.json)
- [真实修复输入与反馈](../local/model-report-comparison-20261003/sleep-deepseek-diagnostics/r1.recovery.distill.r1.recovery.source-007.chunk-001.2.input.json)
- [修复前输出](../local/model-report-comparison-20261003/sleep-deepseek-diagnostics/distiller.09.output.json)和[修复后输出](../local/model-report-comparison-20261003/sleep-deepseek-diagnostics/distiller.10.output.json)

上一轮 12 个 SQLite 数据库完整性、外键、未收束操作和 ready artifact hash 检查通过。本次复用该已记录结论，没有重跑这组检查。它支持档案留存可靠，不证明角色获得所有必要信息或报告事实正确。`local/` 证据未纳入 Git，新 checkout 需要原实验导出；合成探针不依赖这些导出。

关键代码：[证据交付](../src/deepresearch/methods/baseline/stages/evidence_delivery.py)、[补读与工作流](../src/deepresearch/methods/baseline/parallel_workflow.py)、[首次读取校验](../src/deepresearch/workflows/components/source_access.py)、[获取错误处理](../src/deepresearch/workflows/components/acquisition.py)、[浏览器捕获](../src/deepresearch/engine/toolset/browser_capture.py)、[蒸馏与修复](../src/deepresearch/methods/baseline/stages/distillation.py)、[角色校验](../src/deepresearch/methods/baseline/stages/roles.py)、[查询准备](../src/deepresearch/workflows/components/retrieval.py)、[引用检查](../src/deepresearch/methods/baseline/stages/reporting.py)。
