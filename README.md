# ReAct 复现

使用 **`qwen3.6-35b-a3b`**，在 HotpotQA、FEVER、ALFWorld 和 WebShop 上复现 [ReAct](https://github.com/ysymyth/ReAct) 的主要方法与对照实验，比较显式推理、环境交互及二者结合的效果。

四项基准的正式评估与审计均已完成，共生成 **6,268 条任务轨迹**。仓库提供结果表、配对置信区间、代表性轨迹、运行配置和原始产物归档。实验范围、执行细节与修订记录见[实验方案](EXPERIMENT_PLAN.md)。

## 实验结果

### 知识问答与事实验证

每项任务固定 500 题。数值为百分比，越高越好；粗体为本列最高值。

| 方法 | HotpotQA · EM | FEVER · 标签准确率 |
| --- | ---: | ---: |
| Standard | 27.4 | 51.0 |
| CoT | 33.0 | 63.4 |
| CoT-SC | 34.4 | 63.6 |
| Act | 40.0 | 56.0 |
| ReAct | 42.6 | 61.2 |
| CoT-SC → ReAct | 41.4 | 64.2 |
| ReAct → CoT-SC | **45.4** | **65.4** |

HotpotQA 使用答案精确匹配（EM）；FEVER 只评估标签准确率，不是同时要求证据正确的完整 FEVER score。

[主表 CSV](results/qwen36/main-qa.csv) · [HotpotQA 统计与用量](results/qwen36/hotpotqa.json) · [FEVER 统计与用量](results/qwen36/fever.json)

### 交互式任务

ALFWorld 使用 134 个 unseen games；WebShop 使用完整商品库上的同一组 500 个测试目标。

| 方法 | ALFWorld · 成功率 (%) | WebShop · 平均得分 | WebShop · 成功率 (%) |
| --- | ---: | ---: | ---: |
| Act | 7.46（10/134） | **71.27** | **43.6（218/500）** |
| ReAct | **12.69（17/134）** | 57.72 | 35.6（178/500） |

WebShop 平均得分为环境奖励均值 × 100，成功率为获得满分奖励的任务比例。达到步数上限的失败任务均保留在分母中。

[主表 CSV](results/qwen36/main-interactive.csv) · [ALFWorld 统计与用量](results/qwen36/alfworld.json) · [WebShop 统计与用量](results/qwen36/webshop.json)

### 结果说明

- **知识任务中，ReAct → CoT-SC 的点估计最高。** 相比 ReAct，HotpotQA 提升 2.8 个百分点，配对 95% 置信区间为 [1.4, 4.2]；FEVER 提升 4.2 个百分点，区间为 [2.6, 6.0]。
- **ReAct 并非在所有对照中都明显占优。** HotpotQA 上 ReAct 相比 Act 提升 2.6 个百分点，但区间为 [−0.6, 5.8]，包含零；FEVER 上 ReAct 的点估计低于 CoT。
- **ALFWorld 有提升，但绝对成功率仍低。** ReAct 相比 Act 提升 5.22 个百分点，区间为 [1.49, 9.70]，收益主要来自 examine 类任务。
- **WebShop 上 Act 更好。** ReAct 的平均得分低 13.55 分，区间为 [−16.22, −11.01]；成功率低 8.0 个百分点。ReAct 有 112/500 条轨迹达到决策上限，Act 为 5/500。

置信区间使用相同评估样本上的 10,000 次配对 bootstrap，随机种子为 233。结果反映本次固定模型、提示和环境设置下的表现，不代表跨模型或多次独立运行的平均效果。

## 实验设计

| 项目 | 设置 |
| --- | --- |
| 模型 | `qwen3.6-35b-a3b` |
| 方法 | Standard、CoT、CoT-SC、Act、ReAct；知识任务另含两种 hybrid |
| 提示 | 基于作者固定修订中的提示，保存来源和哈希 |
| CoT-SC | 每题 21 次采样，温度 0.7；其他基础方法温度 0 |
| 决策上限 | HotpotQA 7；FEVER 5；ALFWorld 49；WebShop 14 |
| 样本 | 固定评估 IDs；联调样本与正式评估分离 |
| WebShop 环境 | 1,181,430 个环境商品，1,181,370 个可检索文档；60 条空白检索文本商品保留在环境中 |
| 记录 | 请求与响应、环境动作、完整轨迹、评分、用量、错误及恢复记录 |

CoT-SC → ReAct 在 21 次采样的最高票数不超过 10 时转向 ReAct；ReAct → CoT-SC 在 ReAct 未产生有效 Finish 时使用 CoT-SC。两种 hybrid 根据投票或终止状态路由，**不使用标准答案选择分支**。汇总时复用对应正式批次的基础方法结果，逻辑用量计入实际经过的各分支。

## 查看结果与轨迹

- [总汇总 JSON](results/qwen36/summary.json)：两张主表、正式运行用量及归档索引。
- 代表性轨迹：[HotpotQA](results/qwen36/hotpotqa-representative-trajectories.json)、[FEVER](results/qwen36/fever-representative-trajectories.json)、[ALFWorld](results/qwen36/alfworld-representative-trajectories.json)、[WebShop](results/qwen36/webshop-representative-trajectories.json)。
- [实验配置](configs/)、[评估样本清单](data/eval_manifest.json)、[来源清单](records/source_manifest.json)。

| 基准 | 正式运行审计 | 原始产物索引 |
| --- | --- | --- |
| HotpotQA | [审计记录](records/hotpotqa-formal-qwen36-v1-audit.json) | [归档与 SHA-256](records/hotpotqa-formal-qwen36-v1-archive.json) |
| FEVER | [审计记录](records/fever-formal-qwen36-v1-audit.json) | [归档与 SHA-256](records/fever-formal-qwen36-v1-archive.json) |
| ALFWorld | [审计记录](records/alfworld-formal-qwen36-v2-audit.json) | [归档与 SHA-256](records/alfworld-formal-qwen36-v2-archive.json) |
| WebShop | [审计记录](records/webshop-formal-qwen36-v1-audit.json) | [归档与 SHA-256](records/webshop-formal-qwen36-v1-archive.json) |

## 复核与再生成

阅读主表和统计文件无需运行模型。完整原始运行已压缩保存于 [artifacts/](artifacts/)；按各归档索引的 `parts` 顺序以二进制拼接，核对整体 SHA-256 后解压到仓库目录。不要将多个分片分别当作独立 ZIP 解压。

恢复对应原始运行并准备好依赖后，可使用以下脚本重新生成统计；这些脚本不发起模型请求：

```bash
python scripts/report_qa.py --dataset hotpotqa
python scripts/report_qa.py --dataset fever
python scripts/report_alfworld.py
python scripts/report_webshop.py
```

报告脚本会检查相应正式运行的完整性与审计记录。环境回放还需要对应数据和依赖；重新生成模型轨迹则需要单独配置 API 凭据并使用独立的运行标识。QA、ALFWorld、WebShop 使用隔离环境，具体参数、资源来源和执行要求见[实验方案](EXPERIMENT_PLAN.md)及[运行脚本](scripts/)。环境依赖、完整商品库和索引不能视为克隆仓库后即已安装就绪。

## 用量与限制

正式运行记录到 **56,217,642 tokens**，其中输入 53,449,817、输出 2,767,825。该数值汇总服务端返回的用量，包含已记录的重试响应；缺失用量不按零计算。联调调用单独记录，货币费用待对账。

本项目复现方法与对照关系。模型和环境与原论文不同，绝对分数不能视为原论文成绩的严格重复；固定样本上的 bootstrap 也不能覆盖模型重复采样或服务变化带来的全部不确定性。模型通过 API 提供，上游不可变权重身份无法独立验证；未返回的原生 reasoning 用量字段视为未知。环境镜像来源、异常响应和恢复处理保留在实验方案与原始记录中。

## 仓库结构

```text
configs/               各任务运行配置
prompts/               提示资源
src/                   方法实现与作者代码
scripts/               运行、审计和统计入口
data/                  评估清单与数据资源
results/qwen36/        主表、统计和代表性轨迹
records/               来源、审计、用量与归档索引
artifacts/             压缩原始产物及分片
EXPERIMENT_PLAN.md     实验设计、执行细节与研究记录
```

## 论文与来源

Yao et al. **ReAct: Synergizing Reasoning and Acting in Language Models.** ICLR 2023.

[论文 PDF](paper/Yao_et_al_2023_ReAct.pdf) · [作者代码](https://github.com/ysymyth/ReAct) · [固定来源与修订清单](records/source_manifest.json)

作者代码的许可证与来源声明随对应文件保留；第三方数据和环境资源遵循其各自许可。
