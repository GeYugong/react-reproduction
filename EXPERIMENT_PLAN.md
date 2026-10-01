# ReAct 主线复现实验方案

状态：方案已确认，开始实现与环境联调。本文区分已完成的准备工作、预定实验设置和未解决的执行条件，不将接口测试计作 benchmark 结果。

## 1. 研究目标与范围

本实验复现 ReAct 的主要方法与相对行为：在相同底座模型和相同任务上，显式推理文本与环境交互相结合，是否改善知识问答、事实验证和交互式任务的表现。核心比较为 ReAct 与 Act、ReAct 与 CoT，以及两个混合策略与其单独组成方法。

原论文主体使用 PaLM-540B；第 10 页 Reproducibility Statement 指出该模型当时未公开可访问。公开代码为 GPT-3 prompting 实现，不能将更换模型后的绝对分数视为原论文分数的严格重复。本实验复现方法、控制变量和趋势，允许出现排序变化或负结果。

范围包括四个 benchmark、Table 1 的七种 prompting 方法、ALFWorld / WebShop 的 Act 与 ReAct。不训练或微调模型，不重训 BUTLER、IL 或 RL，不纳入 GPT 模型、ReAct-IM、人工编辑 Thought、六种 ALFWorld 提示排列的全面复测。

## 2. 主模型与接口预检

### 2.1 当前模型与完整重启

本轮唯一主模型为 **`qwen3.6-35b-a3b`**，接口 `https://aigw.saurlax.com/v1/chat/completions`。使用 `enable_thinking: false`、`reasoning_effort: "none"` 与 `User-Agent: ReAct-Reproduction/0.1`；不允许跨模型自动回退。原先的 `qwen-3.8-27b` 因通路额度限制退役，按完整重做决定，将四个 benchmark 的所有方法从头运行。

旧结果、模型响应、CoT-SC 票数和 hybrid 均不进入新主表。旧记录及 checkpoint 保留为历史审计，旧配置保存于 `configs/archive/experiment-qwen38.json`。固定数据 IDs、作者 prompts、环境软件和已缓存百科页面复用；新模型使用包含 `qwen36` 的独立 run_id。原先积累的已访问百科内容只作为共享环境资源，不能据此宣称完整百科快照。

当前冻结的是网关别名，不是可校验的权重快照。响应模型标识须与请求一致；实际上游权重和未来额度不可独立确认，作为限制公开，不依据模型自述或第三方聊天宣称已验证。

### 2.2 换模实测

| 候选 | 真实独立联调提示的观察 | 决定 |
| --- | --- | --- |
| `grok-4.6` | HTTP 200，但关闭参数下仍有原生 reasoning，并出现越过 stop 和输出上限的响应 | 排除 |
| `deepseek-v4-flash` | 流式请求收到上游订阅额度耗尽的 HTTP 402 | 当前不可用 |
| `step-3.7-flash`、`step-5-preview` | HTTP 200，但输出上限内只有原生 reasoning，没有可执行正文 | 排除 |
| `qwen3.6-35b-a3b` | 真实 6-shot 首步产生正确格式的文本动作，HTTP 200，无额外 reasoning；Act、温度、stop 检查通过 | 进入新一轮独立联调 |
| GLM 系列 | 前期关闭推理不稳定，已明确排除 | 不重新采用 |

合成 Search/Finish 任务中，新模型曾生成带参数名的字符串，如 `Finish[shelf="K-17"]`；未把这两项记为严格通过，也不引入语义修复。真实 few-shot 联调将进一步验证协议兼容性。选模不使用正式评估成绩，接口成功不等于全部实验已通过。

独立联调出现非空额外推理字段、非零 reasoning token 或返回模型名改变时停止并记录。reasoning 明细缺失记未知，不等于数学证明内部推理为零。费率和实付费用仍待对账；服务方所述部分通路无限额度仅为选型线索，不是持续可用性的保证。

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

当前开展 `qwen36-restart-20260929` 全新实验。旧 Qwen 3.8 批次停止并保留；不得因之后额度恢复而继续将其作为主实验。新模型分别启动 HotpotQA 和 FEVER 的 20 题四方法联调，再各进行 2 题 × 21 次 CoT-SC。运行脚本自动核验题号互斥、请求模型、原生推理、评分和票数；通过后使用独立冻结配置自动开始对应 500 题的全部基础方法与 CoT-SC。正式准确率不作为继续收集或修改协议的条件。

同时最多两个模型生成进程。每个数据集的冻结配置单独保存，后续阶段配置更新不改变已运行批次。全部正式输出重新生成，hybrid 仅由同一新模型的 CoT-SC 与 ReAct 离线组合。

FEVER 与 HotpotQA 均已完成各 80 条四方法联调和两题各 21 次 CoT-SC，分别启动 `fever-formal-qwen36-v1` 与 `hotpotqa-formal-qwen36-v1`，各包括同一 500 题的五种生成方法及后续两个离线 hybrid。`configs/experiment.json` 是本轮基础模板，正式开跑状态以数据集独立冻结配置与运行记录为准，不能因基础模板仍标记 pilot 而中断已验收批次。

ALFWorld 已准备 134 个 unseen games 和作者执行循环，仍需新模型联调与正式运行。WebShop 完整商品索引、磁盘商品存储、固定目标和本地服务均已通过环境验收；60 条空白检索文本只从索引省略，仍保留在环境中。交互任务待模型并发槽空闲后启动新模型联调。

后续历史章节保存旧阶段的事实，仅作为过程审计，不代表本轮新模型的完成状态。最新进度以 `records/model_restart.json`、`records/active_jobs.json` 和 `*-qwen36-campaign.json` 为准。

## 12. 依据

- Yao et al., *ReAct: Synergizing Reasoning and Acting in Language Models*, ICLR 2023，arXiv:2210.03629v3。第 3–6 页方法和知识任务，第 7–8 页交互任务，第 10 页可复现性声明，附录 C 提示示例。原文与文件哈希已归档。
- [ReAct 官方代码](https://github.com/ysymyth/ReAct/tree/6bdb3a1fd38b8188fc7ba4102969fe483df8fdc9)，已在本地核对源文件和数据。
- [ALFWorld 官方代码](https://github.com/alfworld/alfworld/tree/aaba6870f86c5be6a08a491f32a50b906227bc3e)，文本环境、游戏数据及无模型 reset 检查完成，模型结果另行核验。
- [WebShop 官方代码](https://github.com/princeton-nlp/WebShop/tree/64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd)，完整数据、依赖和索引已准备；服务与模型运行按各自验收记录推进。
- 网关接口的实际证据以 `records/api_preflight.jsonl` 为准；模型名称与计费状态不能仅依赖公开网页或模型自述。

### 当前联调运行

命令：`.venv-qa/bin/python scripts/run_qa.py --dataset hotpotqa --phase pilot --methods react act standard cot --limit 20 --run-id hotpot-pilot-qwen-v3`。完整记录位于 `runs/raw/hotpot-pilot-qwen-v3/`；进度见 `records/hotpot-pilot-qwen-v3.json`。每次请求缓存键包含样本、方法、采样序号或决策步和完整请求体，重跑时校验配置与源文件指纹。进程异常保留已经完成的 episode，并单独记录停止原因。

### 联调验收与首个正式阶段

HotpotQA v3 联调 80/80 条完成，207 次请求全部 HTTP 200，额外原生推理未观察到。ReAct 9/20、Act 9/20、Standard 6/20、CoT 3/20，仅作为联调记录，不作正式结论。两条 CoT 的 invalid_answer 均因 512-token 上限截断且原文无 Answer 标记；保留失败，不修改解析或上限。全部题号与正式集互斥、评分复算、日志用量、文本检索和 hybrid 路由边界检查通过。验收与归档见 `records/pilot_audit.json`。

按原参数启动 `hotpot-formal-qwen-v1`，500 题 × Standard / CoT / Act / ReAct；并发另一路顺序验证 HotpotQA 的 2 题 × 21 次 CoT-SC 以及 FEVER 20 题四方法。全局最多两个串行生成进程。CoT-SC 与 FEVER 正式阶段需各自联调核验后启动。所有原始轨迹和失败均保留，当前联调原始文件及引用百科页面已打包到私有仓库形成远端副本。

### 第二次自动检查

HotpotQA 正式 Standard 与 CoT 各 500 条已完成，Act/ReAct 阶段继续运行，当前不对中间分数作结论。CoT-SC 联调确认两题各 21 次独立请求，42 次均成功，投票复算一致；已启动同一正式 500 题的 CoT-SC。FEVER 20 题四方法联调的 142 次请求均成功，无额外原生推理，评分复算通过；等待模型并发槽空闲后运行正式批次。附加验收见 `records/additional_pilot_audit.json`，原始材料已归档。

ALFWorld 三份官方文本数据归档已下载并校验，作者环境筛选后恰为 134 个 unseen games，排序清单及哈希写入样本清单。首次 reset 与 look 动作通过，不包含模型调用，仍需实现与联调模型执行循环。WebShop 创建独立 Python 3.8.20 下载环境（原方案 3.8.13 的补丁版本更新），按作者 setup.sh 的完整数据 ID 下载，尚未完成搜索索引与服务依赖。

WebShop 原始 Google Drive 完整商品文件无法匿名下载：gdown 失败，独立 Windows HTTP 请求为 404。保留失败记录，使用 [HongbangYuan/webshop 固定修订镜像](https://huggingface.co/datasets/HongbangYuan/webshop/tree/0129d4a81dbdb827e76afd20a1e2c38b61098613) 恢复数据下载；两个大文件的 SHA-256 与另一镜像维护者[公开来源说明](https://huggingface.co/datasets/sparklabutah/timewarp-env-data/blob/main/README.md)一致。完整文件约 5.48 GB 与 186 MB，下载后核验大小和 SHA-256。原始 Drive 字节当前无法独立比对，镜像来源作为复现限制披露；不能将该核验写作直接验证作者原始下载。

### 网关额度中断与恢复点

2026-09-28 23:43:58 UTC，两个正式进程均收到 HTTP 402，错误为 `payment_required`、参数 `quota`。主批次已完成 1,102/2,000 条；CoT-SC 完成 33/500 题，下一题已缓存 13/21 次采样。两进程均已停止，不循环重试付费接口；需要网关账单/额度恢复后用原 run_id 续跑，成功请求直接复用缓存。原始记录及百科页面另行形成私有远端 checkpoint 归档，哈希、请求与用量见 `records/billing_checkpoint.json`。预算不设上限不等于网关账户拥有可用额度，实付金额仍待对账。

不依赖 API 的准备继续：WebShop 三份完整数据已下载并核验，正在流式验证 JSON 与商品数量；安装作者服务所需依赖和 en_core_web_sm 3.3.0，锁定实际版本，Java/索引尚待完成。ALFWorld 根据作者 notebook 新增执行循环，保留稀疏 think、49 次决策及环境 won 判据；在 seen split 两题上分别完成 Act/ReAct 的无模型 reset 检查，并通过离线步数、稀疏思考与终止条件测试。上述检查不是模型实验成绩。

### WebShop 检索环境准备

在项目 envs/java 内安装 Temurin Java 11，下载包 SHA-256 与供应方元数据一致，java -version 通过；不修改系统级 Java 配置。安装和导入检查发现作者额外要求的 FAISS 与 PyTorch 尚未齐备，补齐 faiss-cpu 1.7.4、CPU torch 1.11.0，并将 Transformers 固定到作者 requirements.txt 的 4.19.2。

全商品索引导出采用每批 1000 条调用作者原始 load_products，复用相同属性和人工目标映射；检索文本拼接与保存字段沿用作者 convert_product_file_format.py。该改动仅用于限制内存峰值，不缩小商品库。导出后记录实际商品数与文档哈希，使用作者 Lucene 参数构建全索引，并与作者原始转换循环核对前 1000 条文档。构建与一致性检查尚待运行完成，不将脚本创建记作环境验收通过。

### 全量换模重启

新模型方案已获准执行，无需重复方案审批。模型和全量重新生成策略见第 2、11 节；每两小时自动任务已同步更新，禁止恢复旧 Qwen 3.8 主线。新 run_id 独立缓存，旧模型产物保留但不参与任何新主表。

### 新模型轨迹复查与 WebShop 索引验收

新模型联调过程中增加独立离线审计：重新解析模型输出、复算评分与投票、只读已冻结 Wikipedia HTML 回放全部已完成环境动作，比较 observation 和环境状态；递归检查响应中的 reasoning/thinking 字段及内容标记。checkpoint 审计只覆盖当时已经完成的轨迹，不标为整批验收。原生推理遥测缺失仍记为未知，不能将字段缺失当作零 token 或上游计算已被独立证明关闭。

WebShop 的 1,181,436 条原始商品经作者清洗导出 1,181,430 条文档。Lucene 实际入索引 1,181,370 条，其余 60 条全部为空白 contents；empty=60，errors、unindexable、skipped 均为 0。扫描全量导出并核对哈希、检查 60 个空白 ASIN 未入索引、验证检索返回后，原索引通过验收，无需重建。首次失败保留在 `records/webshop_index_initial_failure.json`，当前验收包含所有索引文件哈希。前 1,000 条导出文档与作者原始转换循环逐字段一致。

服务存储采用 JSONL 字节偏移与 SQLite 查找表，避免完整商品对象同时驻留内存；仍保留全部 1,181,430 个商品，包括 60 个不可检索空文本商品。价格通过作者 `generate_product_prices` 按完整商品顺序一次生成，生成前固定种子 42；目标使用作者 `get_goals`，按原始种子 233 打乱。0–499 对应作者 test 范围，500、501 为独立联调目标。价格、完整目标及排序哈希冻结后由所有方法共享，不能按成绩重新生成。该固定价格种子是相对原 Flask 入口未固定初始价格随机性的明确适配。

spaCy 3.3.0 / Pydantic 1.8.2 首次导入因 typing-extensions 4.13.2 的兼容问题失败，按 [spaCy 官方问题记录](https://github.com/explosion/spaCy/issues/12659) 将后者固定为 4.5.0；保留原 traceback 和恢复日志，实际依赖锁随环境更新。服务准备完成不等同于 WebShop 模型实验完成。

WebShop 服务验收完成：1,181,430 个商品、12,087 条目标，前 1,000 个商品对象和随机价格与作者函数一致；500、501 两个联调目标在 Act/ReAct 独立会话中的初始 observation 相同。搜索、详情、子页面、选项和购买路径通过，零奖励和满奖励与作者评分函数一致。满奖励使用后端已知目标测试，仅验证奖励接口，不属于模型轨迹或 benchmark 成绩。完整目标、偏移/价格数据库及原始验收材料归档为 `artifacts/webshop-environment-v1.zip`，大型可重建商品 JSONL 和 Lucene 文件另存哈希。

WebShop 服务与生成均使用 `.venv-webshop/bin/python`，保持作者 BeautifulSoup 4.11.1；共享 API 模块所需 Gym 固定为作者 0.24.0，未使用其 `gym.make`。服务入口为 `scripts/serve_webshop.py`，仅监听 127.0.0.1:3000，健康状态记录于 `records/webshop_service.json`。模型执行器保留 14 次已执行决策和 6,400 字符上下文规则，拒绝 Act 中的 think，并完整保存 HTTP、上下文截断与状态变化。ALFWorld 相应保留 49 次决策并拒绝 Act 中的 think，两个任务的模型联调配置分别冻结，尚未产生新模型正式成绩。

新模型 FEVER 四方法联调共 146 次成功响应，21 次 CoT-SC 联调共 42 次，评分、完整样本覆盖、输出解析、投票和环境回放通过。所有 CoT 输出均有可解析的答案；一处模型生成的 Observation 未被用作环境反馈。基础联调和 SC 原始材料分别独立归档。没有观察到原生推理异常，缺失的遥测仍保持未知。

2026-09-29 06:00 UTC 检查：新模型 HotpotQA 基础联调共 215 次成功响应，SC 联调 42 次，完整离线审计与归档完成；175 次环境动作、132 次百科页面读取回放一致。两条 CoT 无效答案均达到 512-token 上限且无 Answer 标记，保持为原始失败，不改变协议。HotpotQA 正式批次在完成 197 条后因同一请求三次 60 秒读取超时中断；保留错误日志和恢复记录后，按原配置、原 run_id 续跑，原超时请求已成功返回。超时请求费用仍未知，不能视为免费。FEVER 正式批次持续推进，当前两路正式结果的 checkpoint 审计通过；全部 500 题七方法尚未完成，不据中间成绩作比较结论。

2026-09-29 13:44 UTC 检查：两路正式任务均在 13:35 UTC 连续三次读取超时后停止，HotpotQA 保留 1,279 条、FEVER 保留 1,552 条完整 episode。时间高度接近，怀疑共同网络或网关链路中断，尚不能独立定位根因。中断快照见 records/qa-timeout-recovery-20260929T1344.json；按原模型、配置和 run_id 恢复，已有成功调用与完整轨迹复用。恢复期间进度文件先遍历已有 episode，短暂计数下降不代表已保存结果丢失。超时请求费用保持未知。
13:49 UTC，两路原中断题均已成功完成，分别达到 1,280 和 1,553 条，并开始下一题。恢复期间仍出现读取超时，表明链路尚不稳定；网关首页在 Windows 与 WSL 均返回 HTTP 200，不等同于模型端点健康。

2026-09-29 14:46 UTC 检查：上次恢复后，两路分别于 13:51 UTC 在 Wikipedia 检索遇到 Network is unreachable，中断时保留 1,280 与 1,553 条完整 episode。使用同一 Python requests 环境访问两条失败 URL，均恢复 HTTP 200；保留中断快照后按原配置与 run_id 恢复，复用已成功的模型响应。未更改提示、步数、采样或评分。证据见 records/qa-wikipedia-recovery-20260929T1446.json。
14:48 UTC，两路均通过原先失败的 Wikipedia 动作，回放成功缓存后进入后续模型生成步骤，检索恢复得到实际轨迹确认。

2026-09-29 15:46 UTC 状态核验：HotpotQA 在 1,296 条后触发作者 clean_str 的 UnicodeDecodeError；已冻结的 Greek alphabet 页面含不完整反斜线 Unicode 转义。兼容修复保留原转换成功时的行为，仅在 UnicodeError 时原样返回已解析的 Unicode 正文，不丢弃段落或换题。该页 170 个原成功段落输出一致，1 个原失败段落保留原文后 Search 成功。修复依据运行时异常，与成绩无关。FEVER 状态记录为 1,672 条，但操作系统未发现原 runner，故不能以 running 字段作为存活证据。所有恢复必须保留旧 manifest，并登记源文件哈希修订；已完成轨迹离线回放验收后再续跑。
修复后回放验收：HotpotQA 1,296 条、1,373 个环境动作，FEVER 1,672 条、2,016 个环境动作均与既有轨迹一致，评分和响应协议复核通过。两个正式 run 的原 manifest 完整保存在各自 unicode-revision.json，源文件旧副本保存在原始运行目录；只登记 wikienv.py 的兼容修复哈希，配置、样本、提示、主执行器不变。此为运行异常修复，不是按正式成绩调参。正式恢复直接使用 run_qa.py；历史 pilot manifest 保持原版本，不再经旧 campaign 控制器重放。WebShop 服务进程也未找到，重新启动后健康端点通过，冻结数据库与目标哈希一致。

2026-09-29 20:00 UTC 方法覆盖检查：FEVER 的 Standard、CoT、Act、ReAct 各 500 条已生成，原执行器已自动进入 CoT-SC；已完成的首 14 题均包含 21 个采样序号，投票复算一致。HotpotQA 的 Standard、CoT、Act 各 500 条已生成，正在 ReAct。此检查仅确认覆盖与已完成 SC 投票，不代表完整七方法验收。证据见 records/qa-method-transition-20260929T2000.json。

2026-09-30 04:08 UTC 检查：两路均已进入 CoT-SC，但状态文件停留在 04:02 UTC，最新请求约 04:06 UTC 后无后续，操作系统未找到两个 runner 或 WebShop 服务，也无新的 Python 异常退出记录。中断原因未确定，不能将 running 字段视为进程存活。保留现场快照后，按原配置和 run_id 直接恢复，复用已完成 episode 及未完成题的成功 SC 采样缓存，另行恢复 WebShop 服务。
恢复验收：两路均收到新的 HTTP 200 响应并继续 SC 采样，WebShop 健康端点通过且冻结哈希一致。覆盖检查确认两个数据集的四种基础方法各 500 条均已生成，快照中的 HotpotQA 6 题及 FEVER 138 题 CoT-SC 均为 21 次采样且投票复算一致；此为阶段覆盖检查，不是整批验收。

2026-09-30 06:09 UTC 检查：HotpotQA 在 25 题完整 CoT-SC 后，下一题第 15 次采样（索引 14）遇到 TLS unexpected EOF，原始异常与未知费用记录保留。FEVER 同模型接口仍持续返回 HTTP 200。按原 run_id 和冻结配置恢复 HotpotQA，复用已成功采样；未关闭 TLS 校验，也未切换模型或修改采样参数。证据见 records/hotpotqa-tls-recovery-20260930T0609.json。
06:10 UTC，原失败采样返回 HTTP 200，已继续下一次采样，恢复得到实际日志确认。

2026-09-30 10:13 UTC 检查：HotpotQA 在第 59 题 CoT-SC 的采样索引 20 连续读取超时，58 题完整结果及当前题成功采样保留；FEVER 持续运行。中断快照记录后，使用相同 run_id、冻结配置和成功响应缓存恢复，未改变生成参数；失败请求费用仍未知。证据见 records/hotpotqa-timeout-recovery-20260930T1013.json。
10:15 UTC，原中断题完成，HotpotQA 达到 2,059 条，下一题已返回成功响应并继续采样。

2026-09-30 12:14 UTC 检查：两路在约 12:03 UTC 同时收到网关 502，分别保留 HotpotQA 80 题及 FEVER 262 题完整 CoT-SC，当前题成功响应仍在缓存。保存中断快照后各启动一次有限重试恢复，使用原配置与 run_id，不改变采样与模型。证据见 records/qa-502-recovery-20260930T1214.json。
12:17 UTC，两路均越过原失败采样，后续采样返回 HTTP 200，恢复得到原始日志确认。

2026-09-30 16:18 UTC 检查：两路于 16:05 UTC 连续读取超时后停止，保留 HotpotQA 122 题与 FEVER 323 题完整 CoT-SC。停止时间相差约 8 秒，共同链路异常为推测，具体根因未验证。中断记录见 records/qa-timeout-recovery-20260930T1618.json；按原配置与 run_id 各执行一次有限恢复，复用当前题成功采样，失败请求费用仍未知。
16:21 UTC，两路均越过原失败采样并返回 HTTP 200；FEVER 原中断题完成，后续题开始采样。恢复日志确认成功，保留失败记录。

2026-10-01 03:34 UTC，FEVER 正式批次五种生成方法各 500 条全部完成，全量离线验收通过：14,368 次成功响应、2,868 个环境动作、1,963 次检索回放，未发现已返回字段中的原生 reasoning 异常；缺失遥测仍不能证明上游完全关闭内部推理。准确率为 Standard 51.0%、CoT 63.4%、CoT-SC 63.6%、Act 56.0%、ReAct 61.2%、CoT-SC→ReAct 64.2%、ReAct→CoT-SC 65.4%。固定样本配对 bootstrap 区间和逐题分支见 results/qwen36/fever.json 及 fever-episodes.json。137 条步数耗尽与 1 条无效答案均保留于分母。累计已返回 token 6,057,248；83 次传输异常和缺失用量的失败响应费用仍未知，金额待对账。完整原始运行及 Wikipedia 证据正在归档，大文件采用有序二进制分片与 SHA256 记录。FEVER 模型进程退出后启动 ALFWorld 独立联调，与仍在运行的 HotpotQA 保持两路并发；ALFWorld 尚未通过联调，不启动正式批次。

2026-10-01 04:29 UTC，ALFWorld 独立联调 4 条轨迹通过协议、样本隔离、环境奖励、Act 控制及用量验收；156 次成功响应的 finish_reason 均为 stop，未发现已返回字段中的原生 reasoning 异常。Act 与 ReAct 各成功 1/2，失败轨迹保留，不以成绩作为放行门槛。模型生成的环境反馈式文字仅作为动作提交，真实观察仍来自环境；未据此调整提示或参数。已冻结 configs/alfworld-qwen36-formal.json，启动 alfworld-formal-qwen36-v1，覆盖 134 个 unseen games 的两种方法。联调全轨迹已归档。FEVER 全量归档为 157,022,689 字节，拆为 4 个有序分片；分片 SHA256、合并后的完整 SHA256 与 ZIP 成员 CRC 全部验证通过。索引见 records/fever-formal-qwen36-v1-archive.json。

04:30 UTC，ALFWorld 正式 v1 在首次 reset 顺序断言失败，完成 0 条且模型调用为 0；上述启动记录不代表成功生成。根因是 TextWorld 默认打乱游戏顺序，而执行器错误要求字典序。修复为两种方法均 seed=233，并验证每个实际游戏属于冻结集合且不重复；模型提示、步数、奖励和 134 个游戏不变。失败 v1 保留，使用新的 v2 run_id，放行前执行全部 268 次无模型 reset 检查。核验期间仅 HotpotQA 与 WebShop 独立联调占用模型名额。

04:38 UTC，268 次离线 reset 全部通过，两组均无重复地覆盖冻结 134 个游戏且顺序完全相同，记录见 records/alfworld-order-revision.json。正式 v2 使用修复后的源码重新启动，旧 v1 的零调用失败证据保留。WebShop 联调 4 条轨迹与 20 次响应全部通过审计，目标 500/501 的实际奖励在 Act 和 ReAct 下均为 0.6/1.0；包含真实搜索、商品查看、选项选择与购买终止。联调轨迹已归档，正式配置冻结，等待 HotpotQA 或 ALFWorld 释放并发名额。

2026-10-01 15:38 UTC 检查：ALFWorld v2 在 77 条完整结果后停止。HTTP 200 返回体末尾拼接 WebSocket abnormal closure 错误对象，JSON 在偏移 665 处出现 Extra data；执行器将其保存为 non_json_response 后触发通用模型别名异常，不构成模型被替换的证据。异常响应未进入成功缓存或环境动作，原始日志保留；见 records/alfworld-malformed-response-20261001T1538.json。以相同 run_id、冻结源码和配置执行一次有限恢复，复用已完成轨迹及当前题成功采样，失败请求费用仍待对账。
15:42 UTC，原失败步骤已通过，后续步骤 36 返回 HTTP 200 并执行真实环境动作，恢复得到日志确认。
