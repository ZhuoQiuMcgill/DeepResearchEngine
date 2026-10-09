# Baseline 系统修复与回归记录

2026-10-03。本轮以非模型因素为验收对象：档案读取、信息交付、格式恢复、局部失败隔离与追溯。
不根据这些样本给模型排名。历史实验、失败输出和拒绝的报告均保留，没有用成功重跑覆盖失败。

实现入口为 [baseline@11 使用契约](usage/baseline-reliability.md)。Planner 5、Selector 4、
Distiller 4、Analyst 6、Writer 7、Reviewer 6 使用同一 Runtime，工具仍是 search 4 / fetch 2。
早期版本和角色资源保留。当前示例请求显式选择 revision 11；公共请求的默认 revision 仍为 1。

## 实验边界

每批六次完整运行，两模型分别回答三条原始问题：

- `compare meta quest 3 and apple vision pro`
- `How do I flight from GuangZhou to Montreal?`
- `What food can help me sleep well?`

实际模型为 `deepseek-flash`（thinking disabled）和 `gpt-6-luna`（reasoning low）。
每次使用新请求身份和独立 SQLite。预算保持两轮、全局最多 20 个尝试 URL、20 次蒸馏调用、
4 个并行 Distiller、每轮最多两条主查询、4 次报告写作/审阅。Agent 窗口 262,144 token；
交付证据预算 131,072 estimated token / 524,288 UTF-8 bytes；源档扫描最多 1,048,576 bytes。
修复调用计入原有执行预算，不重置额度。

每批开始前记录 302 个源文件/角色资源/配置的 SHA-256；每次运行前和批次结束后核对。
批内不修改生产代码或 instruction。两模型各自实时搜索，得到的证据不同；这是端到端系统
故障检查，不能声称控制了证据后的模型因果比较。执行耗时也不作为模型性能排名。

## 修复和验收点

| 范围 | 改动 | 验证方式 |
| --- | --- | --- |
| S01 / S02 源读取 | 交付行数、物理页数、range 类型和上限；补读复用首次读取的生命周期、snapshot、range、字节、span、continuation 校验；UTF-8 余量不足明确返回 partial | 篡改 snapshot/range/长度/span/上限、未知提交、未完成清理等负例均拒绝；合法分页和不足一个码点的预算有正例 |
| S03 / S04 抓取隔离 | 错误保留 resource/fetch 范围、触发 URL、资源类型、上限类别；辅助资源超限可保留可用 DOM，附带缺失警告；单 URL 已结算失败不废弃其他来源 | 实际 Chromium + 受控 relay；global/cancel/unknown/cleanup 负对照；真实流程保留失败 URL 并继续 |
| S05 文档蒸馏隔离 | 每份文档最多两次；持续格式/绑定错误隔离该 chunk，保留独立成功结果；按 source/chunk/content hash 记住隔离结果，后续批次不重复尝试 | 真实 Runtime/SQLite、并行及后续批次控制实验；第一批睡眠 DeepSeek 实际隔离一个 chunk 后继续 |
| S06 / S07 引文与修复 | 简单 Markdown 链接可见文字映射回原文连续区间；不做模糊事实匹配；仅删除无法定位的 finding，已验证项不要求模型重写；保留原输出和变更记录 | 可见文字/原文正例；改数字、删事实的负例；正确 finding 保持不变 |
| S08 角色契约 | Runtime 拒绝的输出可作为诊断档案交给有 repair 契约的角色；保留字段错误和上版输出，最多两次；非法输出仍无有效 export | 真正穿过 Runtime 提前拒绝路径，覆盖 Planner/Selector/Analyst/Reviewer；不只是 monkeypatch decision 的成功路径 |
| S09 查询 | 主查询原样执行；恢复变体有独立记录和预算 | `site:`、引号、`C++`、排除词、日期操作符的控制用例；最终结果档案核对 original_query/query |
| S10 引用机械门槛 | 正文/References ID 集合、每项唯一性、ID→URL 绑定；URL 中合法括号不误删；Reviewer 不能覆盖失败结果 | 缺 References、只列参考、错 URL、重复项等负例；普通和括号 URL 正例 |
| S11 研究时间和来源 | 各角色共享已保存的 UTC as_of；交付原始/实际 URL、media type、抓取时间、已知书目信息和读取能力；缺失值不编造 | Runtime 输入与档案审计；日期提取追加检查见后文 |
| 新发现：修复分支崩溃 | Runtime 拒绝时没有成功 outcome，旧分支仍读取 outcome.output_ref，导致 TypeError；改读已保存的诊断引用 | 第一批头显/航班 DeepSeek 实测；四角色回归复现后通过 |
| 新发现：网络与提交混淆 | 已结束的只读 GET 未收到回复，被误标为整个存储提交未知；现在保留 remote delivery unknown，同时保留明确的 not_committed 并继续其他 URL | 第一批睡眠 DeepSeek 实测；未知 commit/status、未清理等负例仍停止；不自动重试该 URL |
| 新发现：Selector 输入追溯 | 汇总指向未补充默认字段的初始输入；修复后的记录现在指向最终实际调用输入，另存 initial_input_ref | 第一批 18 个 Selector 记录复现；第二批逐项对照调用事件/输入内容 |
| 新发现：Planner 超预算恢复 | 查询数量检查原在有界修复外；移入校验回调，修复成功前不发搜索 | 超预算查询→具体反馈→合法查询的 Runtime 控制实验 |
| 新发现：错误诊断不够具体 | HTTP header 超限曾标成 body limit；保留正确 header_bytes 上限以及安全的 libcurl 数字错误码 | header 负例、敏感异常文本不输出测试；真实失败网址重新记录到错误码 60 |

## 两批完整运行

| 话题 / 模型 | 历史 baseline 10 | 第一批 baseline 11 | 第二批 baseline 11 |
| --- | --- | --- | --- |
| 头显 / DeepSeek | 读取失败 | 报告修复 TypeError | 已生成并接受报告 |
| 头显 / GPT | 已生成报告 | 已生成报告 | 已生成并接受报告 |
| 航班 / DeepSeek | Selector 分类重复，失败 | 报告修复 TypeError | 已生成并接受报告 |
| 航班 / GPT | 已生成报告 | 已生成报告 | 已生成并接受报告 |
| 睡眠 / DeepSeek | 引文验证失败 | 网络失败被误判为提交未知 | 已生成并接受报告 |
| 睡眠 / GPT | 单 URL RESPONSE_LIMIT 中断 | 已生成报告 | 已生成并接受报告 |

第二批六次均为 succeeded / recording complete / report accepted；其中航班 DeepSeek
的覆盖状态为 partial，其余五次为 sufficient。这是 host 的覆盖判断，不是事实质量评分。

| 话题 | DeepSeek 正式报告 / fetch 成功与尝试 / 草稿次数 | GPT 正式报告 / fetch 成功与尝试 / 草稿次数 |
| --- | --- | --- |
| 头显 | [报告](../local/systemic-repair-r2-20261003/headsets-deepseek-evidence/report.md) · 15/20 · 4 次 | [报告](../local/systemic-repair-r2-20261003/headsets-gpt-evidence/report.md) · 7/10 · 2 次 |
| 航班 | [报告](../local/systemic-repair-r2-20261003/flights-deepseek-evidence/report.md) · 8/8 · 1 次 | [报告](../local/systemic-repair-r2-20261003/flights-gpt-evidence/report.md) · 5/6 · 2 次 |
| 睡眠 | [报告](../local/systemic-repair-r2-20261003/sleep-deepseek-evidence/report.md) · 8/10 · 1 次 | [报告](../local/systemic-repair-r2-20261003/sleep-gpt-evidence/report.md) · 4/7 · 1 次 |

第二批未触发格式 repair 或隔离分支，不能仅凭这次成功声称逐个实时重现并排除了旧根因。
相应因果证据来自保留的失败输入及真实 Runtime/Storage 回归；实时搜索结果变化也影响成功率。

第一批目录：`local/systemic-repair-20261003/`；第二批：
`local/systemic-repair-r2-20261003/`。各自 `protocol.json`、`progress.json`、
`*-request.json`、`*-store/`、`*-evidence/`、`*-diagnostics/` 保存配置、原始失败、
SQLite、报告和逐阶段证据。历史六次运行仍在 `local/model-report-comparison-20261003/`。

第二批在第一批结束后才修改七个生产文件并重新冻结。未调整角色 instruction、问题、
模型配置或预算来掩盖失败。第二批头显 DeepSeek 使用四次写作/审阅才接受；它不是首次草稿即通过。

## 存储和交付审计

第一批六个 SQLite 的 integrity_check 均为 ok，无外键违规或待结算 operation。
核对 1,035 份 READY artifact 的长度与 SHA-256、49 个 snapshot、93 个读取 segment 记录、
276 条已保留引文绑定；没有发现档案字节或引文串档。另查出 18 个 Selector 记录各有
“缺默认字段”“不等于实际输入”两项追溯问题，共 36 个标记。数据库健康不能替代链路语义检查。

第二批六个 SQLite 同样全部健康，无外键违规或待结算 operation；1,028 份 READY artifact、
47 个 snapshot、107 个读取 segment 记录和 261 条引文绑定通过校验，16 个 Selector 输入
记录均与实际调用一致，最终六份报告的引用结构/URL 绑定通过。主查询保持原样；每次全局
抓取尝试不超过 20，轮数不超过 2。

新增 [离线审计器](../examples/benchmarks/audit_research_store.py) 只读已结束的 store，
不调用模型或网络，核对 artifact、读取 action、segment 字节、引用定位、Selector 输入、
主查询和最终 References。它输出结构性问题，不评分事实正确性。使用创建 store 的同一
操作系统/Python，避免跨系统 SQLite 锁语义差异。

```shell
uv run --locked python examples/benchmarks/audit_research_store.py local/systemic-repair-r2-20261003/headsets-deepseek-store --output local/headsets-audit.json
```

控制实验还特意损坏临时测试 store 的报告文件：SQLite integrity_check 仍为 ok，审计器正确
报告 artifact_hash 错误。没有修改真实实验文件。

## 回归测试

第二批代码的全量测试：**1,433 passed in 383.73s**。随后新增的真实 Runtime/SQLite
离线审计测试：**1 passed**。此前针对修复路径的 432 项测试以及括号 URL/header/错误码
4 项边界检查通过。日期元数据追加修复后的相关回归 **174 passed in 46.05s**，
包括整个 fetch 2、实际 Chromium 边界、baseline 系统回归、source access 和离线审计。首次全量中的版本列表断言和旧角色错误码兼容性失败均已修复并重测。

## 报告阅读后继续发现的问题

第二批 GPT 头显报告写“CNET 文章未提供发布日期”。回读保留的原始 HTML，存在
`article:published_time=2024-02-23T13:00:00-05:00` 和
`parsely-pub-date=2024-02-23T13:00:08Z`。两个值并非同一时间，不能任选其一冒充确定日期。
UploadVR HTML 同时含 article:published_time 和 article:modified_time，正文提取没有将它们
交给 Agent。这是实际元数据丢失，不能归咎于模型不读。

日期修复在第二批结束后进行。HTML 提取现在保留明确的 head/meta 日期声明为
`provenance.document_dates`，分别记录 published / modified、字段名和原值；冲突全部保留，
标记 `document_declared_not_verified`，不拿 HTTP Last-Modified 或抓取时间推断发布日期。
相关卡片的 `<time>` 不当作当前文章的日期。每组最多八项，遗漏数量明确记录。该字段对旧
档案和非 HTML 来源是可选的；不承诺完整解析 JSON-LD/PDF 日期。

真实 CNET fetch 再次成功，输出记录了上述两个日期值并提交到独立 SQLite；档案校验通过。
随后以相同头显问题/配置/预算追加一次 GPT 完整流程，独立目录
`local/systemic-repair-dates-20261003/`，冻结 303 个源文件。它不替换第二批六题样本。
定点运行 `run_8a41021c7b5d4268b34e44a37ee2267e` 已成功并接受
[最终报告](../local/systemic-repair-dates-20261003/headsets-gpt-evidence/report.md)：两轮、16 次 fetch
尝试、12 份成功档案、24 次模型调用、两次报告草稿。九份来源保留了显式日期；两次报告审阅的
实际 evidence 输入均含全部 12 份来源的 document_dates 字段，其中九份 published 非空。

本次还真实触发一次 Selector INVALID_SELECTION，第二次带原输出与具体错误修复成功，
继续完成研究。250 份 artifact、12 个 snapshot、18 个读取 segment 记录、47 条引文绑定
及 Selector 输入追溯全部通过审计。批次结束 hash 核对通过；未改写任何旧档案或报告。

报告接受依然不证明事实正确、价格有效或覆盖穷尽。当前仍需区分：外部 403/挑战页/TLS/
不支持的内容格式造成的来源缺口；来源自身版本和日期冲突；模型对表格、引文及证据充分性的
语义判断；baseline 仅两轮的覆盖策略。不能因为系统不再崩溃就宣称这些因素已经消失。


人工阅读六份报告后的归因边界：

- **日期丢失属于系统问题，已修复。** 原始 HTML 有字段，交付层却没给；这能用同一档案直接复现。
- **部分语义错误不能归咎于工具读取。** 第二批头显 DeepSeek 报告说一个 Vision Pro refresh-rate 表格单元为空，实际存档及交给 Distiller/Writer 的行都含 `100 Hz ...`，Distiller 也正确提取该行。该处是综合/审阅的语义错误；引用 ID 和原文存在的机械校验不会发现它。
- **航班建议仍有推断过度。** DeepSeek 从没有直飞推到需要自己拼接行程，现有证据并未确立必须分开购票。GPT 明确保留了聚合站之间关于直飞信息的冲突。这里不能用读取成功率替代建议正确性。
- **食物报告仍多依赖二手介绍。** 两模型在来源选择、机制铺陈和谨慎限定上不同；引文可访问不代表某食物的功效得到临床确认。本轮验证的是系统交付和来源支持，不把引文存在等同于功效确证。
- **外部获取仍有损失。** 第二批保留的失败包括 HTTP 拒绝、redirect limit 和不支持的媒体类型；修复保证诚实记录和正确隔离，不能保证每个网站都可访问。
