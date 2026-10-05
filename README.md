# ReAct 复现

使用 `qwen3.6-35b-a3b` 复现 [ReAct](https://github.com/ysymyth/ReAct) 在知识问答、事实验证和交互式任务上的主要实验。基于作者代码与提示，保存模型响应、环境交互轨迹、评估结果和用量记录。

| 任务 | 评估规模 | 方法 |
| --- | --- | --- |
| HotpotQA | 500 题 | Standard、CoT、CoT-SC、Act、ReAct 及两种 hybrid |
| FEVER | 500 题 | Standard、CoT、CoT-SC、Act、ReAct 及两种 hybrid |
| ALFWorld | 134 个 unseen games | Act、ReAct |
| WebShop | 完整商品库、500 个固定目标 | Act、ReAct |

- [实验方案](EXPERIMENT_PLAN.md)：方法、环境、运行方式、评估口径与限制。
- [实验配置](configs/)与[运行脚本](scripts/)：各任务的固定参数和执行入口。
- [结果汇总](results/qwen36/summary.json)：两张主表、正式用量与原始归档索引；[完整结果](results/qwen36/)包含配对置信区间和代表性轨迹。
- [样本清单](data/eval_manifest.json)、[来源清单](records/source_manifest.json)与[原始产物索引](records/)。
- [论文](paper/Yao_et_al_2023_ReAct.pdf)：*ReAct: Synergizing Reasoning and Acting in Language Models*。
