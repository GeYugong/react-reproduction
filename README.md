# ReAct 主线复现

使用同一个非 GPT 模型复现 ReAct 在 HotpotQA、FEVER、ALFWorld 和 WebShop 上的主要实验。研究范围包括七种知识问答策略，以及交互任务中的 Act / ReAct 对照。

- [实验方案](EXPERIMENT_PLAN.md)：研究问题、实验矩阵、方法、用量记录和执行顺序。
- [实验配置](configs/experiment.json)：与方案对应的参数和运行门槛。
- [过程记录](records/worklog.jsonl)、[API 预检](records/api_preflight.jsonl)、[来源清单](records/source_manifest.json)。
- [评估样本清单](data/eval_manifest.json)、[原始论文](paper/Yao_et_al_2023_ReAct.pdf)。

当前状态：方案已确认，进入作者代码适配与环境联调；正式实验尚未开始。
