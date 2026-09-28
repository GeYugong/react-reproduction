# ReAct 主线复现实验方案

状态：方案已确认，开始实现与环境联调。本文区分已完成的准备工作、预定实验设置和未解决的执行条件，不将接口测试计作 benchmark 结果。

## 1. 研究目标与范围

本实验复现 ReAct 的主要方法与相对行为：在相同底座模型和相同任务上，显式推理文本与环境交互相结合，是否改善知识问答、事实验证和交互式任务的表现。核心比较为 ReAct 与 Act、ReAct 与 CoT，以及两个混合策略与其单独组成方法。

原论文主体使用 PaLM-540B；第 10 页 Reproducibility Statement 指出该模型当时未公开可访问。公开代码为 GPT-3 prompting 实现，不能将更换模型后的绝对分数视为原论文分数的严格重复。本实验复现方法、控制变量和趋势，允许出现排序变化或负结果。

范围包括四个 benchmark、Table 1 的七种 prompting 方法、ALFWorld / WebShop 的 Act 与 ReAct。不训练或微调模型，不重训 BUTLER、IL 或 RL，不纳入 GPT 模型、ReAct-IM、人工编辑 Thought、六种 ALFWorld 提示排列的全面复测。

## 2. 主模型与接口预检

### 2.1 模型选择

方案中的唯一主模型改为网关 ID **`qwen-3.8-27b`**，接口为 `https://aigw.saurlax.com/v1/chat/completions`。所有正式方法均使用该 ID，不进行跨模型拼表，不使用 `auto`，不允许在请求失败后自动切换模型。

选择依据为接口可用性和文本协议兼容性，不依据评估集成绩选择模型。预检使用虚构档案查询与字符串输出任务，未调用正式 benchmark。原始请求、响应、状态码和 token 用量见 `records/api_preflight.jsonl`。

当前冻结的是网关别名，不是可校验权重哈希的模型快照。响应中的模型名称不足以独立证明实际权重身份。按网关目录中的非 GPT 别名运行，禁止自动模型回退，并逐请求核对返回模型名；实际权重身份和网关内部路由不可独立验证时，明确列为限制，不阻塞已授权的实验。若网关不能提供不可变版本，报告明确标注 API 版本不可完全冻结这一限制，记录实验窗口与所有响应模型标识。

### 2.2 已观察到的接口情况

| 候选模型 | 观察 | 处理 |
| --- | --- | --- |
| `qwen-3.8-27b` | 默认客户端请求曾返回 403；设置 `User-Agent: ReAct-Reproduction/0.1` 后简单请求及五项文本协议测试均为 200，未观察到额外推理 | 当前主模型；使用 `enable_thinking: false` 与 `reasoning_effort: "none"`，独立联调已启动 |
| `deepseek-v4-flash` | 返回 HTTP 400，错误提及 `Codex Responses` 仅支持流式 | 上游映射存疑，排除 |
| `glm-5.3-flash` | 两种推理关闭参数均未稳定生效 | 已明确排除，不再作为主模型或自动回退模型 |
| `glm-5.3` | 出现额外推理、Act 前缀缺失和停止词正文为空 | 排除 |
| `step-3.7-flash` / `step-5-preview` | 输出上限内仍出现额外推理，未稳定产生可执行正文 | 排除 |
| `grok-4.6` | 设置 User-Agent 后流式请求成功，但报告 50 个 reasoning token | 排除 |

**Qwen 已通过合成协议预检，HotpotQA 独立样本联调正在运行。** 五项检查包括 Search、基于外部 Observation 的 Finish、无 Thought 的 Act、温度 0.7 请求和停止词截断。温度检查只证明接口接受参数，不能证明服务端采样分布正确。预检请求均显式发送 `enable_thinking: false`。响应未提供原生 reasoning token 明细时记录为未知，不能据此证明模型内部完全不推理。

首次真实联调中，单独 `enable_thinking: false` 未阻止原生推理，第一请求的 256 个输出 token 均被报告为 reasoning，批次 v1 停止且没有完成题目。用相同联调输入补充 `reasoning_effort: "none"` 后返回正常文本动作；v2 采用两项控制共同运行。控制修订只使用独立联调题，不使用正式评估成绩。

主实验继续核验独立联调样本。正式批次若出现非空额外推理字段或非零原生 reasoning token，暂停并记录协议异常。GLM 不再用于后续实验，也不通过改变研究问题来保留 GLM。模型协议和实际非 GPT 上游映射属于不同核验事项；当前成功响应只证实网关返回的 Qwen 别名，不能证明不可变权重身份。

部分 Qwen 响应的 `total_tokens` 与输入、输出 token 之和不一致；逐字段保留原值并标记差异，不能自行补成原生推理用量或用其推算实付价格。

另外，模型列表不提供价格；网关模型广场 API 使用该 Key 返回 401。有效费率与实付金额尚未取得，成功预检已经产生 token 用量，费用标记为待对账，不能记为零。当前经费不设金额上限，价格缺失不再作为停机条件；方案审阅和模型协议核验仍须完成。

## 3. 实验矩阵与样本

| Benchmark | 方法 | 评估规模 | 主指标 | 核心问题 |
| --- | --- | ---: | --- | --- |
| HotpotQA | Standard、CoT、CoT-SC、Act、ReAct、CoT-SC → ReAct、ReAct → CoT-SC | 500 dev | Answer EM | 内部知识与外部检索如何互补 |
| FEVER | 同上七种 | 500 dev | Label Accuracy | 外部证据是否帮助事实分类 |
| ALFWorld | Act、ReAct | 134 unseen games | Success Rate | Thought 是否帮助目标分解和状态跟踪 |
| WebShop | Act、ReAct | 500 test instructions | Score、Success Rate | Thought 是否帮助满足商品约束 |

HotpotQA 另报答案 F1。FEVER 只做三分类准确率，不将其称作要求同时提交证据的完整 FEVER score。ALFWorld 按六类任务补充分组成功率，但总分按全部 episode 汇总。

### 3.1 抽样规则

- HotpotQA 使用官方 ReAct 仓库的 `hotpot_dev_v1_simplified.json`，共 7,405 条。按 `random.Random(233).shuffle` 固定顺序，取前 500 条，与公开 notebook 一致。原数据没有原始 `_id`，因此使用文件哈希、行号和问题文本哈希联合标识，避免虚构原始 ID。
- FEVER 使用同一仓库 `paper_dev.jsonl` 的完整 9,999 条，以同样的种子 233 抽取 500 条。本次固定样本为 SUPPORTS 173 条、REFUTES 167 条、NOT ENOUGH INFO 160 条。公开 notebook 写死 `range(7405)`，未覆盖全部数据；本实验修正这一抽样范围，并公开此差异。
- 两者的具体评估 ID 已写入 `data/eval_manifest.json`。同一数据集的所有方法复用相同 ID，不因模型、结果或方法重新抽样。另保留排列中的第 501–520 条用于联调，与正式评估互斥。
- ALFWorld 在环境安装后列出全部 unseen gamefile，核对恰为 134 个，并保存文件哈希、任务类型与固定执行次序；正式运行前完成清单。
- WebShop 使用完整商品库，固定官方测试目标索引 0–499，并在安装后验证其对应测试划分、目标文本和哈希。`reset` 的会话名必须映射到同一目标，不能仅将随机会话命名为 `fixed_*` 就视为固定任务。

## 4. Prompt 与方法控制

实现优先从作者代码修改：保留并按许可归档 `wikienv.py`、`wrappers.py`、四个 notebook 的核心循环与官方 prompts；新增代码仅承担统一 API 接入、结构化记录、断点续跑、方法组合与环境兼容。每项改动记录上游文件和修订，不优先重写已有实验逻辑。

### 4.1 来源及示例

官方 ReAct 代码锁定到 `6bdb3a1fd38b8188fc7ba4102969fe483df8fdc9`。原文件及数据哈希见 `records/source_manifest.json`；`vendor/` 是可重建的上游缓存，不作为本项目原创代码提交。

| 数据集 | 官方源 | 选定示例 |
| --- | --- | --- |
| HotpotQA | `prompts/prompts_naive.json` | Standard=`webqa_simple6`，CoT=`cotqa_simple6`，Act=`webact_simple6`，ReAct=`webthink_simple6` |
| FEVER | `prompts/fever.json` | 相应 `webqa_simple3`、`cotqa_simple3`、`webact_simple3`、`webthink_simple3` |
| ALFWorld | `prompts/alfworld_3prompts.json` | 六类任务分别使用同类 `*_1`、`*_0`，顺序固定为 1 → 0；Act/ReAct 配对 |
| WebShop | `WebShop.ipynb` | `prompt1` 与 `prompt1_actonly`，一个商品选择示例 |

HotpotQA 为 6-shot，FEVER 为 3-shot，ALFWorld 为 2-shot，WebShop 为 1-shot。直接提取官方示例，不按评估成绩改写。提取后检查各组任务和答案是否对应，保存源 key、原文哈希、最终提示哈希和所有格式变换。需要兼容 chat 接口的改动限定为角色包装与文本续写指令，不添加新知识、额外示例或更强规划提示。

CoT 使用官方已整理的连贯推理示例，不能机械删除工具文本后留下指向不存在 Observation 的残句。CoT-SC 与 CoT 完全共享示例，仅改变采样策略。所有提示和问题保持英文。

### 4.2 生成与执行

Standard 直接回答；CoT 生成分析及最终答案；Act 生成文本动作；ReAct 生成显式 Thought 和动作。Act/ReAct 共享解析器、环境执行器、错误处理和 observation 规则。不得使用 native function calling、自动规划框架、额外反思模型、任务分解模型或 LLM 评分器。

模型输出至下一条动作后停止。程序只执行解析出的动作，Observation 只来自环境。若服务忽略 stop，客户端在第一条 Observation 标记前截断并记录异常；不能把模型伪造的 Observation 作为环境反馈。

一般方法温度为 0、top_p 为 1；CoT-SC 温度为 0.7。API 的温度 0 不保证服务端逐位确定性。输出上限预设为 Standard 128、CoT/CoT-SC 512、Act/ReAct 单次 256 token。该上限高于公开 notebook 的单次 100 token，以容纳 chat 模型的格式包装，属于明确报告的协议差异；在独立联调集上冻结，不能看正式成绩后调整。

解析器只做固定的语法处理，如去除外围空白、统一动作名大小写；不纠正搜索实体、不根据标准答案修复输出。模型格式错误占用一次决策机会，写入错误日志，使用预定义反馈继续至上限；不增加未计费或未记录的修复请求。HTTP 429、5xx 和网络异常最多重试两次，固定退避；不重试语义上的错误答案。所有尝试独立记账。

## 5. 知识问答与混合策略

### 5.1 Wikipedia 环境

沿用官方 `wikienv.py` 与 `wrappers.py` 的检索和评分语义：`Search[entity]` 返回匹配页面的前五句，未精确匹配时提供最多五个相近标题；`Lookup[string]` 在当前页面依次返回含关键词的句子；`Finish[answer]` 结束任务。正式评估只给问题或 claim，不提供 gold 支持段落、答案或 FEVER 证据标注。

主方案采用官方在线 Wikipedia 路径并增加共享持久缓存。保存请求 URL、规范化查询、原始响应、页面内容、抓取时间、内容哈希及解析后的结果。同一查询或已抓取页面跨方法复用首次保存版本，缓存键必须包含解析器版本。仅缓存 observation 文本不足以恢复 Lookup，必须保存完整页面状态。

这种做法冻结已访问内容，不等于拥有某个日期的完整百科快照。报告保留网页漂移及首次抓取顺序的限制。若网络无法稳定访问，不静默换搜索引擎、向量检索或题目附带段落；先完成并记录兼容性修订，再冻结新环境。网站限流和解析失败属于基础设施错误，不能冒充“未搜索到实体”。

### 5.2 步数与结束条件

HotpotQA 的 Act/ReAct 上限均为 7 次决策，FEVER 均为 5 次决策，Finish 也占一次。公开 FEVER notebook 为 7 次；本实验按论文第 5 页的 FEVER 设置选择 5 次，并使 Act/ReAct 的预算相同。

终止原因区分有效 Finish、空 Finish、格式错误、步数耗尽、API/环境错误和人工中断。空答案不视为有效完成；错误但非空的合法答案仍是已完成，不能因为评分错误就触发另一个方法重答。

### 5.3 CoT-SC 与离线组合

每题完整采样 21 条独立 CoT，温度 0.7；采样序号 0–20 进入缓存键。不得因请求体相同就把一次返回复制为 21 票，也不以提前多数为由省略后续采样。使用与评估一致的答案归一化进行投票，保存原始答案、归一化答案、票数及每次用量。

无效答案不形成有效票；分母仍为 21，不通过丢弃无效输出抬高置信度。若最高票并列，选择并列答案中最早采样出现的一个；所有答案无效则输出明确失败。FEVER 只接受规范化后的三个合法标签。

- **CoT-SC → ReAct**：最高有效票数少于 10.5，即不超过 10 票时，使用同题保存的 ReAct 结果；至少 11 票则使用 CoT-SC。路由只依赖一致性，不查看答案对错。
- **ReAct → CoT-SC**：ReAct 未在规定步数内产生合法非空 Finish 时使用 CoT-SC；已经 Finish 的错误答案不回退。未恢复的网络故障不伪装成方法性超时，标记整项运行的基础设施状态。

两个分支均从原始问题及各自提示独立开始，回退不携带另一分支的检索历史。满足相同模型、提示、样本、参数及环境版本的条件后，两个 hybrid 可离线组合，无需重复生成。

缓存节省的是实际复现费用。报告 hybrid 的部署开销时，仍按执行路径累加前一分支以及实际触发的后一分支 token、请求数和耗时，不能宣称 hybrid 推理成本为零。

## 6. 交互任务

### 6.1 ALFWorld

仅使用文本环境，在全部 134 个 unseen games 上比较 Act/ReAct。每类任务选择相同示例轨迹，固定顺序 1 → 0。报告单一固定提示配置的结果，不标为论文的 average 或 best-of-6。

允许连续环境动作以及稀疏 `think:`。Thought 不改变世界状态；可以产生固定的本地确认文本，但不能访问评估器内部状态。控制器不向模型提供 gold 子目标或额外 admissible-action 列表，除非原始 observation 本身包含。

与公开 notebook 的 `range(1, 50)` 对齐，最多 49 次模型决策，Thought 和环境动作均占用决策机会。另行记录真实环境动作数。使用 `info['won']` 判断任务成功，保存 reset 状态、gamefile、种子及逐步返回。

### 6.2 WebShop

使用官方本地研究环境和完整商品库；安装脚本的 small / 1,000 商品配置只用于安装检查，不能用于主表。正式启动前核验商品文件、索引、目标列表及目标排序哈希，并关闭环境的随机价格变化或固定其随机种子。

保留作者文本页面解析与 `search[...]`、`click[...]`、`think[...]` 交互协议，不将网站换成真实电商购买流程。Act/ReAct 对每个目标重置为相同初始状态，使用独立会话防止跨方法状态残留。

公开 notebook 的 15 次循环包含初始 reset，实际最多执行 14 个生成决策，且最后可能多生成一个不再执行的动作。本实验保留 **14 次已执行决策** 的语义并省去最后那次无效请求，Thought 也计数。记录该边界，避免写成 15 次环境动作。

上下文窗口沿用 notebook 的 6,400 字符拼接规则：保留完整示例前缀，再取剩余可用字符数的任务历史尾部。完整未截断轨迹另存；每次保存实际发送上下文及被截掉的长度。窗口按字符计算，不误记为 6,400 token。

Score = 100 × 平均环境 reward；SR = 100 × reward 等于 1 的任务比例。部分满足约束只计入 Score，不能算成功。环境异常、运行中断和任务失败分别记录。

## 7. 评估、统计与结果解释

正式评估采用固定样本一次运行，完整保留失败样本。对同题方法差值做 10,000 次配对 bootstrap，种子 233，给出 95% 区间；区间反映该评估集上的抽样不确定性，不代表模型多次运行的全部随机性。多种方法比较作为描述性结果报告，不挑选显著的比较宣称普遍因果规律。

记录 EM/Accuracy/SR/Score，以及每题请求数、环境动作数、总决策数、输入/输出/缓存/原生推理 token、延迟、费用、解析失败和重试。字面报告 native token 字段；字段缺失记 null，不能记为 0。

主表不悄悄移除接口失败题。完成质量控制后仍有未恢复失败时，报告覆盖率和按完整分母计算的端到端结果；可额外报告共同完成样本上的配对分析，并明确其分母。中断导致的不完整评估必须标注为未完成，不补零伪装完整 benchmark。

第一张主表：

| 方法 | 论文 HotpotQA EM | 本实验 EM | 论文 FEVER Acc | 本实验 Acc |
| --- | ---: | --- | ---: | --- |
| Standard | 28.7 | 未运行 | 57.1 | 未运行 |
| CoT | 29.4 | 未运行 | 56.3 | 未运行 |
| CoT-SC | 33.4 | 未运行 | 60.4 | 未运行 |
| Act | 25.7 | 未运行 | 58.9 | 未运行 |
| ReAct | 27.4 | 未运行 | 60.9 | 未运行 |
| CoT-SC → ReAct | 34.2 | 未运行 | 64.6 | 未运行 |
| ReAct → CoT-SC | 35.1 | 未运行 | 62.0 | 未运行 |

第二张主表包含 Act/ReAct 的 ALFWorld SR、WebShop Score/SR。论文 ALFWorld 的 45% / 71% 是各自 best-of-6 结果，不能与本实验单提示分数不加说明地直接比较；WebShop 论文 Act 为 62.3/30.1，ReAct 为 66.6/40.0。BUTLER、IL、IL+RL 仅作为文献参考，并标注未重训。

每个任务保留 3–5 个代表性成功/失败案例，说明选择规则。可选的 HotpotQA 失败分析从 CoT、ReAct 错误集合各随机抽取至多 50 个，记录抽样种子并标注 hallucination、reasoning error、search error、标签歧义；不足 50 则分析全部。不把 FEVER 准确率直接等同于幻觉率。未经人工完成的标注不能声称已经人工验证。

## 8. 经费与调用规模

本实验经费不设金额上限。保持四个 benchmark、21 次 CoT-SC 和既定样本规模，仍采用缓存、断点续跑与 hybrid 离线组合避免重复请求。所有模型预检、正式生成、失败、重试与复核均进入用量台账；不扩展到研究范围以外的付费服务。

当前不存在可靠的实付费用总额；预检响应仅有 token 用量，待按网关实际费率或账单对账。费率未取得时保留数量与费用状态，不填造价格，不将成功或失败请求默认视为免费。

未计重试时的请求量上界为：

- 知识任务：Standard 1,000 + CoT 1,000 + CoT-SC 21,000 + Act 6,000 + ReAct 6,000 = **35,000 次**。
- ALFWorld：134 × 2 × 49 = **13,132 次**。
- WebShop：500 × 2 × 14 = **14,000 次**。
- 合计最多 **62,132 次生成请求**。hybrid 不增加实际请求；多数任务提前结束后，实际次数会更少。不能把 8,268 个方法×任务结果误当成模型调用次数。

费用按每次实际 token 和网关有效价格计算，包括输入、输出、缓存读取、缓存写入、计入账单的原生推理及可能的按次费用。输出 token 若已包含 reasoning token，不重复收费。美元或网关额度计价必须记录实际人民币换算口径、倍率和优惠；不直接使用模型厂商官网价格替代中转站价格。

调度器不设置金额停机阈值，但保留每题步数、单次输出上限、重试次数和并发限制。每个批次记录已结算与待对账请求，持续累计 token 与估算/实付费用，二者分开。价格未知不阻塞已授权的实验；模型身份、协议异常、数据不一致和方案审批仍按各自规则处理。

先用独立联调样本测量延迟与 token，再安排批次。任何样本量、模型或方法变动都必须更新配置、原因与方案版本，不能因为某种方法效果较差而停止收集或改变实验矩阵。

## 9. 记录与仓库组织

只维护两份叙述文档：本方案和简短 README。后续实验进展与最终结果继续更新本方案对应章节，不另建每阶段总结文档。原始过程使用 JSON/JSONL，汇总表使用 CSV，图表作为结果资产保存。

```text
react/
├── README.md
├── EXPERIMENT_PLAN.md
├── configs/experiment.json
├── paper/Yao_et_al_2023_ReAct.pdf
├── scripts/                    # 来源冻结、预检及后续运行入口
├── src/                        # 后续实现共享 API、解析器、用量台账与任务适配
├── prompts/                    # 后续提取的冻结提示与来源映射
├── data/eval_manifest.json
├── records/                    # 过程、API 预检、来源、成本和产物索引
├── results/                    # 后续两张主表、指标与案例
├── runs/raw/                   # 后续完整逐请求日志和轨迹
└── vendor/                     # 可重建的上游代码缓存
```

`src/` 已归档作者环境与评分源文件，`prompts/` 已提取作者提示；执行器适配和结果目录尚待完成。原始运行文件与下载数据不直接塞入 Git；每批必须登记产物路径、大小、SHA-256、完成状态和备份位置。Git 忽略不等于删除，原始轨迹必须完整保留，并至少有一份独立副本后才视为已归档。

### 9.1 每次运行

保存 run_id、阶段、开始/结束时间及 UTC 偏移、命令、Git SHA、dirty diff 哈希、Python/依赖锁定信息、系统环境、配置、模型与接口、样本清单、提示哈希、环境及数据哈希、随机种子、价格版本、用量与费用前后状态、失败原因和恢复方法。

### 9.2 每条 episode 与模型请求

episode 至少包括 dataset/id/method/model/task、全部轨迹、final_answer、独立评估阶段附加的 ground_truth/metrics、决策数、工具调用数、终止原因和请求 ID。gold 只供评分，不进入推理上下文或缓存路由。

逐请求记录实际 messages、生成参数、完整返回内容、返回模型名、请求 ID、finish_reason、HTTP 状态、usage、耗时、重试序号、解析结果和费用状态。逐环境动作记录动作前后状态、原始/处理后 observation、reward、done 和异常。为后续 context compression 保留完整历史与每一步实际送入模型的上下文，能区分模型原文、解析结果和环境原文。

日志不保存鉴权头、Key 或 Cookie。密钥只通过运行进程环境变量读取，`.env*` 已加入 Git 忽略。原始请求中的 role 字段属于模型协议数据；项目叙述采用研究记录口吻，不使用对话式建议或虚构完成过程。

## 10. 环境、顺序与提交节点

本地仓库为 `D:\0code\Research\feng\react`，已初始化 `main`；方案确认后创建首次提交。本机已发现 WSL Ubuntu，主运行环境优先在 WSL 的项目目录中建立，分别隔离 `react-qa`、`react-alfworld`、`react-webshop`。QA 计划 Python 3.11，ALFWorld 按已锁定源要求使用 Python 3.9+ 的独立环境，WebShop 按官方基线 Python 3.8.13 与 Java 环境检查；实际依赖版本在安装联调通过后锁定。方案确认后开始安装环境与联调；正式任务遵循开跑条件。

若之后迁往 A40_Cluster_1，项目和环境只放在 `/public/home/mty/GeYugong/react/` 内，不修改共享 conda 环境；迁移记录系统、依赖、数据与缓存哈希。

执行顺序及提交节点：

1. 审阅方案，解决上游身份与原生推理控制；确认后创建首次提交：`docs(plan): define ReAct mainline reproduction protocol`。
2. 提取并核对提示，建立共享 API/执行器/缓存/日志/用量台账；在独立联调样本打通 Search → Observation → Lookup → Finish，验证代理无权读取 gold；通过后提交 `feat(core): add audited ReAct execution and usage accounting`。
3. 独立样本联调四个环境和成本，固定配置、环境锁文件、所有评估 ID 与提示哈希。此阶段不按正式测试成绩调参。
4. HotpotQA 依次完成 Standard/CoT/Act/ReAct，再完成 CoT-SC 并离线组合两个 hybrid；完成后提交相应实现与汇总。
5. 迁移相同框架至 FEVER，完成第一张主表；完成后提交实现与汇总。
6. 完成 ALFWorld Act/ReAct 134 games，随后完成 WebShop Act/ReAct 500 instructions；各阶段结束并核验后提交实现与汇总。
7. 生成两张主表、成本统计、配对区间、代表性轨迹和限制分析，更新本文结果章节并提交 `docs(results): report ReAct reproduction outcomes and limitations`。

首次提交必须在方案确认之后；后续有意义的实现或实验阶段完成且核验后再提交，不逐次 API 调用提交。提交信息使用英文并遵循 `type(scope): description`。远端使用已创建的 GitHub private 仓库 `GeYugong/react-reproduction`，重要阶段完成并提交后同步 `origin/main`；不修改无关目录。

## 11. 当前准备状态与开跑条件

已完成：独立 Git 仓库、官方源代码核对和修订固定、HotpotQA/FEVER 评估清单、非 GPT 候选接口预检、主模型选择及本方案草稿。方案已提交并同步私有远端，作者环境源文件和提示已归档。WSL 的 QA 与 ALFWorld 独立 Python 3.11 环境依赖安装完成，版本见 `configs/*-requirements.lock`；ALFWorld 游戏数据与 WebShop 环境尚未就绪，依赖安装成功不等于环境联调通过。QA runner 已实现并启动 `hotpot-pilot-qwen-v3`：20 道独立样本 × ReAct / Act / Standard / CoT。正式 500 题和另外三个 benchmark 尚未开始，结果分析尚待完成。

正式运行前必须全部满足：

- 方案审阅通过并形成 Git 提交。
- 请求固定为 `qwen-3.8-27b`，返回别名一致，无自动回退；无法独立验证实际上游身份的限制已记录。
- Qwen 原生推理控制在独立联调中继续通过，未出现额外推理协议异常。
- 用量台账能够记录全部请求及 token，价格和账单缺失时明确标记待对账。
- 当前批次对应的环境与数据安装通过，提示和任务清单可按哈希重建；其他 benchmark 的安装不阻塞已就绪批次。
- 独立样本联调完成，输出格式、评分、缓存、hybrid 路由和费用核算通过检查。

## 12. 依据

- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, ICLR 2023，arXiv:2210.03629v3。第 3–6 页方法和知识任务，第 7–8 页交互任务，第 10 页可复现性声明，附录 C 提示示例。原文与文件哈希已归档。
- [ReAct 官方代码](https://github.com/ysymyth/ReAct/tree/6bdb3a1fd38b8188fc7ba4102969fe483df8fdc9)，已在本地核对源文件和数据。
- [ALFWorld 官方代码](https://github.com/alfworld/alfworld/tree/aaba6870f86c5be6a08a491f32a50b906227bc3e)，已克隆指定修订并安装文本环境依赖，游戏数据及运行验证尚待完成。
- [WebShop 官方代码](https://github.com/princeton-nlp/WebShop/tree/64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd)，核对完整数据、环境安装和会话目标映射要求，尚未安装。
- 网关接口的实际证据以 `records/api_preflight.jsonl` 为准；模型名称与计费状态不能仅依赖公开网页或模型自述。

### 当前联调运行

命令：`.venv-qa/bin/python scripts/run_qa.py --dataset hotpotqa --phase pilot --methods react act standard cot --limit 20 --run-id hotpot-pilot-qwen-v3`。完整记录位于 `runs/raw/hotpot-pilot-qwen-v3/`；进度见 `records/hotpot-pilot-qwen-v3.json`。每次请求缓存键包含样本、方法、采样序号或决策步和完整请求体，重跑时校验配置与源文件指纹。进程异常保留已经完成的 episode，并单独记录停止原因。
