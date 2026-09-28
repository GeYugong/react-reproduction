"""Freeze source provenance and evaluation IDs without running experiments."""

from __future__ import annotations

from collections import Counter
import datetime as dt
import hashlib
import json
from pathlib import Path
import random
import subprocess


ROOT = Path(__file__).resolve().parents[1]
UPSTREAM = ROOT / "vendor" / "ReAct"


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    timestamp = dt.datetime.now(dt.timezone.utc).isoformat()
    revision = subprocess.check_output(["git", "-C", str(UPSTREAM), "rev-parse", "HEAD"], text=True).strip()
    tracked = subprocess.check_output(["git", "-C", str(UPSTREAM), "ls-files"], text=True).splitlines()
    manifest = {
        "recorded_at_utc": timestamp,
        "react": {"url": "https://github.com/ysymyth/ReAct", "commit": revision,
                  "local_path": "vendor/ReAct", "license": "MIT",
                  "files": {name: sha256(UPSTREAM / name) for name in tracked}},
        "alfworld": {"url": "https://github.com/alfworld/alfworld",
                     "commit": "aaba6870f86c5be6a08a491f32a50b906227bc3e",
                     "status": "remote_revision_recorded_not_installed"},
        "webshop": {"url": "https://github.com/princeton-nlp/WebShop",
                    "commit": "64fa2a5c15c7daa698b9ac93f5bb5437b634c9bd",
                    "status": "remote_revision_recorded_not_installed"},
        "paper": {"path": "paper/Yao_et_al_2023_ReAct.pdf",
                  "source": "https://arxiv.org/pdf/2210.03629", "version": "2210.03629v3",
                  "sha256": sha256(ROOT / "paper/Yao_et_al_2023_ReAct.pdf")},
        "verified_code_differences": [
            {"source": "FEVER.ipynb", "finding": "Samples from range(7405), although paper_dev.jsonl contains 9999 records.",
             "decision": "Sample 500 from all 9999 records with seed 233; disclose deviation from notebook."},
            {"source": "FEVER.ipynb", "finding": "Uses range(1, 8), whereas the paper's hybrid fallback uses 5 FEVER steps.",
             "decision": "Use 5 steps for FEVER Act/ReAct and hybrid gating."},
            {"source": "alfworld.ipynb", "finding": "range(1, 50) permits 49 model decisions, including think actions.",
             "decision": "Count both thoughts and environment actions in the 49-decision limit."},
            {"source": "WebShop.ipynb", "finding": "range(15) includes initial reset; only 14 generated decisions are executed. A final generated action is discarded.",
             "decision": "Execute at most 14 model decisions; omit the discarded final API call."},
            {"source": "WebShop.ipynb", "finding": "Slices prompt tail by character count using 6400-len(init_prompt).",
             "decision": "Preserve this prompt-window rule for the main comparison; retain full raw history separately."},
        ],
    }
    write_json(ROOT / "records/source_manifest.json", manifest)
    hp = json.loads((UPSTREAM / "data/hotpot_dev_v1_simplified.json").read_text(encoding="utf-8"))
    fv = [json.loads(line) for line in (UPSTREAM / "data/paper_dev.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()]
    selection = {"schema_version": 1, "seed": 233, "source_commit": revision,
                 "policy": "Python random.Random(233).shuffle(range(N)); first 500; no resampling per method",
                 "datasets": {}}
    for dataset, rows, field, filename in [
        ("hotpotqa", hp, "question", "hotpot_dev_v1_simplified.json"),
        ("fever", fv, "claim", "paper_dev.jsonl"),
    ]:
        order = list(range(len(rows)))
        random.Random(233).shuffle(order)
        selected = []
        for index in order[:500]:
            row = rows[index]
            selected.append({"row_index": index, "id": row.get("id", f"hotpot_dev_row_{index}"),
                             "task_sha256": hashlib.sha256(row[field].encode("utf-8")).hexdigest()})
        data = {"population_size": len(rows), "sample_size": 500,
                "source_file": "vendor/ReAct/data/" + filename,
                "source_sha256": sha256(UPSTREAM / "data" / filename), "samples": selected,
                "excluded_dev_smoke_rows": order[500:520]}
        if dataset == "fever":
            data["sample_label_counts"] = dict(Counter(rows[i]["label"] for i in order[:500]))
        selection["datasets"][dataset] = data
    selection["datasets"]["alfworld"] = {"sample_size": 134, "split": "eval_out_of_distribution",
        "status": "pending_gamefile_inventory", "selection": "all official unseen games; verify count before running"}
    selection["datasets"]["webshop"] = {"sample_size": 500, "goal_indices": list(range(500)),
        "status": "pending_full_catalog_goal_hashes", "selection": "official fixed goal indices 0..499; verify against test split"}
    write_json(ROOT / "data/eval_manifest.json", selection)
    events = [
        ("repository_initialized", "在 react 目录初始化独立 main 分支；方案审阅前不创建提交。"),
        ("sources_audited", "克隆官方 ReAct；核对四个 notebook、提示词、评估封装、数据条数与论文设置；记录上游修订及 SHA-256。"),
        ("evaluation_ids_frozen", "HotpotQA 从 7405 条、FEVER 从完整 9999 条各固定抽取 500 条；随机种子 233；两者另留互斥的 20 条联调样本。"),
        ("execution_environment_inspected", "本地已发现 WSL Ubuntu；尚未安装 ALFWorld/WebShop 依赖，尚未运行正式 benchmark。"),
    ]
    path = ROOT / "records/worklog.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = {json.loads(line)["event"] for line in path.read_text(encoding="utf-8").splitlines()} if path.exists() else set()
    with path.open("a", encoding="utf-8") as handle:
        for event, description in events:
            if event not in existing:
                handle.write(json.dumps({"recorded_at_utc": timestamp, "phase": "plan", "event": event,
                    "description": description, "timestamp_semantics": "recorded retrospectively during planning",
                    "evidence": ["records/source_manifest.json", "data/eval_manifest.json"]}, ensure_ascii=False) + "\n")
    print(json.dumps({"source_commit": revision, "hotpotqa": len(hp), "fever": len(fv),
                      "fever_sample_labels": selection["datasets"]["fever"]["sample_label_counts"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
